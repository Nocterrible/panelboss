"""powercfg /requests, parsed, with an opt-in scheduled-task assistant.

Catching the case where some *other* app already pins the display
awake (a player, a game, a WebView2 video wake lock): there is no
point polling the camera to defend a screen someone else has claimed.

The trouble: powercfg /requests needs elevation; unelevated it prints
"This command requires administrator privileges" and exits 1. There is
no official non-admin user-mode API (measured, Windows 11 26220).

The workaround (classic "elevated shortcut without the UAC prompt"):
register a Task Scheduler task that runs as SYSTEM (session 0, no
console ever) ONCE per tick of the checkbox - which costs one consent,
and only when the user ticks the power assistant box. Afterwards the
non-elevated app may start its own task with `schtasks /Run` silently,
and the task dumps fresh powercfg output to a file we read.

Two machine-specific walls this path had to solve, both measured:
  * `schtasks /Create` rejects /SC ONDEMAND outright (invalid schedule
    type). A DAILY trigger at 03:07, which we never rely on, passes
    parsing; the app drives cadence with /Run.
  * tasks created from an elevated context get a security descriptor
    of exactly "O:BA" - invisible AND unrunnable to the same user's
    filtered (medium-IL) token. The fix that worked: the task's own SD
    (not the file NTSD - icacls on the task file does nothing for
    TaskScheduler!) rewritten via the Schedule.Service COM object:
    `SetSecurityDescriptor(sddl, 0)` - flag 1 errors - granting the
    installing user GRGX (query + execute).
Elevation itself goes through ShellExecuteW("runas") on a generated
.ps1 - Start-Process -Verb RunAs from a pythonw process, under the
"Never notify" UAC slider, was the thing that hung; ShellExecuteW just
returns and the truth is polled from the task store either way.

Everything still fails open: any problem means "unblocked", camera
polling continues, and the error string is what the window shows.
"""

import ctypes
import os
import re
import subprocess
import sys
import time

TASK_NAME = "PanelBoss-PowerRequests"

# consent dialogs wait for humans; this is how long we give the task
# store to reflect a create/delete before calling it a refusal
CONFIRM_TIMEOUT = 180
REMOVE_TIMEOUT = 90
CHECK_SEC = 2.0

# section names that mean "the screens themselves are being held awake";
# System/Awaymode/multimedia only hold sleep off, the monitor can still
# darken, so they are listed for information but never block polling
DISPLAY_WORDS = ("display", "monitor", "console")

# the DISPLAY request's section header, locale-proof: the words above
# are English (localized powercfg headers the gate would otherwise
# miss - audit MED: English-only DISPLAY_WORDS parsing kills the
# display-gate on a localized Windows), and this is the Display
# subgroup GUID, MEASURED off this box (powercfg /query SCHEME_CURRENT:
# Subgroup GUID: 7516b95f-f776-4464-8c53-06167f40cc99 (Display)); the
# scheme/subgroup GUIDs are locale-independent, the words around them
# are not (the precedent power_plan.py sets for /list). On this
# (English) box the words still match first, so behavior is identical
# (the suite proves it); where a header carries its GUID instead of
# (or beside) the label, the GUID answers.
_DISPLAY_GUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}",
                           re.IGNORECASE)
_DISPLAY_GUIDS = {"7516b95f-f776-4464-8c53-06167f40cc99"}
import logging

log = logging.getLogger("power")
_LOCALE_CONFESSED = False             # one confession per process;
                                      # the flag, not the silence


def _is_display_section(sec):
    low = sec.lower()
    if any(w in low for w in DISPLAY_WORDS):
        return True
    m = _DISPLAY_GUID.search(low)
    return bool(m) and m.group(0) in _DISPLAY_GUIDS

# an assistant dump older than this is a broken/removed task, not news
STALE_SEC = 60

# the line the dump task writes between the two reports; requests end,
# overrides end, both parsed from the same file
OVERRIDE_MARK = "REQUESTSOVERRIDEMARK"

# request types as powercfg spells them in the override listing
OVERRIDE_TYPES = ("SYSTEM", "DISPLAY", "AWAYMODE", "AWAYMODEIDLERESCHEDULE",
                  "EXECUTION", "PERFBOOST", "CONSOLE")


def result_path():
    """Where the scheduled task drops its report; per-user, stable."""
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(root, "PanelBoss", "power_requests.txt")


def _own_tokens():
    """What marks OUR process inside a dump. Measured: the flat layout
    prints no PID for execution-state holders - just "[PROCESS]
    \\Device\\HarddiskVolume8\\Users\\...\\python.exe" - and the venv
    launcher re-execs the base install, so powercfg names THAT image
    while sys.executable says venv. Device paths carry no drive letter,
    so the driveless tail is the token that actually hits. Without this
    the app's own display hold would block its own camera forever."""
    pid = os.getpid()
    toks = {"0x%x" % pid, "0x%X" % pid, str(pid)}
    exes = {sys.executable, os.path.realpath(sys.executable)}
    base = getattr(sys, "base_prefix", None)
    if base:                       # the venv stub's true successor
        for name in ("python.exe", "pythonw.exe"):
            exes.add(os.path.join(base, name))
    for exe in exes:
        toks.add(exe.lower())
        toks.add(exe.split(":", 1)[-1].strip("\\").lower())
    return tuple(t for t in toks if t)


def _tidy(text):
    """Drop the \\Device\\HarddiskVolume8\\ / \\??\\ noise: nobody reads
    volumes, they read the tail of the path."""
    return re.sub(r"^(?:\\Device\\[^\\]+|\\\?\?)\\", "", text)


def _guess_caller(text):
    low = text.lower()
    if low.startswith("process") or ".exe" in low or "\\" in low:
        return "process"
    return "other"


def _object_for(caller, text):
    """What powercfg /requestsoverride wants as the object name: an
    image name for processes (their own old manual entries used bare
    names), the friendly name without the ROOT(...) parenthetical for
    drivers - measured against the entries this machine already has."""
    base = text.split(" - ", 1)[0].strip()
    low = base.lower()
    for mark in ("[process] ", "[driver] ", "[service] "):
        if low.startswith(mark):
            base = base[len(mark):].strip()
            break
    if caller == "process":
        tail = base.replace("/", "\\").split("\\")[-1].strip()
        for tok in tail.split():
            if tok.lower().endswith(".exe"):
                return tok
        return tail or base
    if caller in ("driver", "service"):
        return base.split(" (")[0].strip()
    return base


def _parse(text):
    """Sections at column 0 ending in ':'; entries inside them.

    Newer powercfg (measured) prints FLAT: "[PROCESS] <path>" and
    "[DRIVER] <name>" markers at column 0 with the reason alone on the
    next line - indentation exists only in old layouts, so the pairing
    rule is positional: a non-marker line directly after an entry line
    (one per entry) is that entry's reason and joins it, giving one
    honest line like "Users\\...\\opera.exe - Video Wake Lock".
    Whatever the shape, both layouts land in the same buckets, and
    every emitted line is ALSO recorded structured (caller/object/
    request) for the overrides manager - powercfg needs those, not the
    pretty text."""
    display = []
    other = []
    entries = []
    section = "unknown"
    saw_section = False               # locale-honesty confession state
    saw_guid = False                  # (gate MED: an unrecognized
    saw_nonascii = False              # header must at least confess,
                                      # and only on EVIDENCE: a header
                                      # with non-ASCII characters is
                                      # proof of a localized build;
                                      # plain absence of English words
                                      # proves nothing - an English
                                      # box with no display request
                                      # must NOT confess)
    mine = _own_tokens()              # header must at least confess)
    pending = None                  # entry awaiting its reason line
    pending_mine = False
    pending_caller = "other"

    def put(item, caller=None):
        item = _tidy(item)
        caller = caller or _guess_caller(item)
        entries.append({"caller": caller, "object": _object_for(caller, item),
                        "request": section.upper(), "text": item,
                        "overridden": False})
        if _is_display_section(section):
            display.append(item)
        else:
            other.append("%s: %s" % (section, item))

    def flush():
        nonlocal pending, pending_mine, pending_caller
        if pending is not None and not pending_mine:
            put(pending, pending_caller)
        pending = None
        pending_mine = False

    for line in text.splitlines():
        stripped = line.strip()
        low = stripped.lower()
        if not stripped or low in ("none", "none.", "no"):
            flush()                        # the reason never came: fine
            continue
        if not line[0].isspace() and stripped.endswith(":"):
            flush()
            section = stripped[:-1]
            saw_section = True
            if any(ord(c) > 127 for c in stripped):
                saw_nonascii = True     # POSITIVE evidence of a
                                        # localized powercfg build
            if _DISPLAY_GUID.search(stripped):
                saw_guid = True
            continue
        if low.startswith(("[process]", "[driver]", "[service]")):
            flush()
            pending_caller = low[1:].split("]")[0].strip()
            # [PROCESS] is pure prefix noise; [DRIVER] stays - it is
            # the only hint of WHO (the (ROOT\MEDIA...) suffix is it)
            pending = (stripped.split("]", 1)[1].strip()
                       if pending_caller == "process" else stripped)
            pending_mine = any(t in low for t in mine)
            continue
        if any(t in low for t in mine):
            flush()                        # our own keep-awake...
            pending = stripped             # ...and now its reason too
            pending_mine = True
            pending_caller = _guess_caller(stripped)
            continue
        if pending is not None:
            if not pending_mine:
                put("%s - %s" % (pending, stripped), pending_caller)
            pending = None
            continue
        put(stripped)
    flush()
    global _LOCALE_CONFESSED
    if (saw_section and other and not display
            and (saw_nonascii or saw_guid) and not _LOCALE_CONFESSED):
        # third-gate ledger 6: confess only on EVIDENCE the box is
        # localized (a header with non-ASCII text, or a header
        # carrying its subgroup GUID) - the earlier trigger (any
        # unrecognized header) fired on every English box holding a
        # non-display request, which made the confession noise.
        # RESIDUAL, named: an ASCII-lettered localized header
        # ("Affichage:") stays blind in silence - the wordless GUID
        # arm of _is_display_section is the durable fix path when a
        # real localized /requests dump can be measured.
        _LOCALE_CONFESSED = True
        log.info("display-gate: header seen that this locale's words "
                 "do not cover - a display request may sit unbucketed; "
                 "assuming display state is gateable")
    return {"error": None, "display": display, "other": other,
            "overridden": [], "requests": entries,
            "override_entries": []}


def _overrides(text):
    """powercfg -requestsoverride with no arguments (measured, on the
    machine where audio drivers sat under [DRIVER] ... SYSTEM): bare
    [CATEGORY] headers, then "<friendly name> <TYPE>" per line."""
    entries = []
    cat = "other"
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            cat = stripped[1:-1].strip().lower()
            continue
        toks = stripped.split()
        types = set(t.upper() for t in toks if t.upper() in OVERRIDE_TYPES)
        name = " ".join(t for t in toks if t.upper() not in types)
        if name:
            entries.append({"cat": cat if cat in
                            ("process", "driver", "service") else "other",
                            "name": name.lower(), "types": types})
    return entries


def _ov_hit(item, ovs, words):
    low = item.lower()
    for o in ovs:
        if o["name"] in low and any(w in o["types"] for w in words):
            return True
    return False


def _report(text):
    """One assistant dump (requests, marker, overrides) -> the buckets.

    A holder the user silenced with powercfg -requestsoverride leaves
    the red bucket entirely and returns as "*OVERRIDE <line>": the
    point of an override is that Windows itself ignores that request,
    so it must not pause the camera either - the window only lists it
    grey to explain why something looks blocked but is not. The same
    verdict is stamped onto the structured entries (one matcher, no
    string-identity games), and the override list itself rides along
    for the manager window."""
    req, found, ovr = text.partition(OVERRIDE_MARK)
    result = _parse(req)
    if not found:                          # a dump from the old .bat
        return result
    ovs = _overrides(ovr)

    display, other, overridden = [], [], []
    for x in result["display"]:
        if _ov_hit(x, ovs, ("DISPLAY", "CONSOLE")):
            overridden.append("*OVERRIDE " + x)
        else:
            display.append(x)
    for x in result["other"]:
        sect = x.split(":", 1)[0].strip().upper()
        if sect and _ov_hit(x, ovs, (sect,)):
            overridden.append("*OVERRIDE " + x)
        else:
            other.append(x)
    for e in result["requests"]:
        sect = e["request"]
        e["overridden"] = _ov_hit(
            e["text"], ovs, ("DISPLAY", "CONSOLE")
            if _is_display_section(sect) else (sect,))
    result["display"] = display
    result["other"] = other
    result["overridden"] = overridden
    result["override_entries"] = ovs
    return result


# request types powercfg /requestsoverride actually accepts (measured:
# it rejects the rest, and PERFBOOST/ACTIVELOCKSCREEN lines are not
# overridable objects anyway)
OVERRIDEABLE = ("DISPLAY", "SYSTEM", "AWAYMODE", "AWAYMODEIDLERESCHEDULE",
                "EXECUTION")


def apply_script(ops):
    """The elevated half: one generated .ps1 (the quoting layers that
    killed every inline attempt are skipped by writing a file).

    op = {"caller", "object", "types"}: ONE set form per object -
    the set form REPLACES the whole typelist (measured), so callers
    ship the COMPLETE wanted list, survivors included; an empty list
    clears the override (the documented DELETE keyword does not
    exist in this build - Invalid Parameters, measured in a hidden
    elevated run - and the empty set form deletes the registry
    DWORD outright). Types beyond the accepted five (perfboost,
    console) are silently DROPPED by the set form (measured:
    DISPLAY PERFBOOST stored 0x1), so ops never carry them."""
    lines = ["$ErrorActionPreference='SilentlyContinue'"]
    for op in ops:
        obj = str(op["object"]).replace("'", "''")
        types = sorted(set(op.get("types") or []))
        lines.append('& powercfg.exe /requestsoverride %s "%s"%s'
                     % (str(op["caller"]).upper(), obj,
                        (" " + " ".join(types)) if types else ""))
    return "\r\n".join(lines) + "\r\n"


def _entry_types(ents, op):
    """What the dump currently says THIS object is overridden for
    (empty set when absent) - the end-state check compares whole
    typelists, not single types, because the set form replaces all."""
    obj = str(op["object"]).replace("/", "\\").split("\\")[-1].lower()
    obj = obj.split()[0] if obj.split() else obj
    for o in ents:
        if o["cat"] != str(op["caller"]).lower():
            continue
        n = o["name"]
        if n == obj or n in obj or obj in n:
            return set(o["types"])
    return set()


def apply_overrides(ops, assistant=True, timeout=120):
    """Set the wanted typelists elevated, then BELIEVE ONLY THE DUMP:
    elevation is a handoff, so every few seconds the assistant task
    re-reads powercfg and each object's live typelist must equal the
    wanted one (empty wanted = entry gone) - consent refused shows
    up as the honest timeout error."""
    if not ops:
        return True, "nothing to change", {}
    if not _elevate_ps(apply_script(ops), name="overrides_apply.ps1"):
        return False, ("applying overrides needs administrator "
                       "privileges; the confirm was refused, cancelled, "
                       "or never clicked"), {}
    end = time.time() + timeout
    fresh = {}
    while time.time() < end:
        time.sleep(3)
        fresh = requests(assistant=assistant)
        ents = fresh.get("override_entries") or []
        if all(_entry_types(ents, op) & set(OVERRIDEABLE)
               == set(op.get("types") or []) for op in ops):
            return True, "overrides updated", fresh
    return False, ("applying overrides needs administrator "
                   "privileges; the confirm was refused, cancelled, "
                   "or never clicked"), fresh


def _run(args, timeout=15):
    """CREATE_NO_WINDOW is a PROCESS creation flag - STARTUPINFO
    .dwFlags knows nothing about it (that wrong slot is exactly why
    the popups survived the first fix). On Windows 11 25H2 any console
    that does get created is hosted by Windows Terminal, which pops
    AND steals focus, so this flag is load-bearing for the every-couple
    -seconds probes."""
    return subprocess.run(args, capture_output=True, timeout=timeout,
                          creationflags=subprocess.CREATE_NO_WINDOW)


def _elevate_ps(body, name="assistant_task.ps1"):
    """Run $body elevated. A generated file, not a -Command string: the
    quoting layers (python -> powershell -> Start-Process -> cmd -> the
    /TR value) is where every earlier attempt died. ShellExecuteW
    returns as soon as the handoff happens; never trust its number -
    callers verify against the task store."""
    path = os.path.join(os.path.dirname(result_path()), name)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
    except Exception:
        return False
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", "powershell.exe",
        "-NoProfile -ExecutionPolicy Bypass -File \"%s\"" % path,
        None, 0)
    return ret > 32


def create_script(bat):
    """The elevated half of install(): create the task AND grant the
    non-elevated app query+execute rights on it (SD otherwise O:BA)."""
    return (
        "$ErrorActionPreference='SilentlyContinue'\r\n"
        "& schtasks.exe /Create /TN %(name)s /SC DAILY /ST 03:07 "
        "/RU SYSTEM /RL HIGHEST /TR \"%(bat)s\" /F | Out-Null\r\n"
        "Start-Sleep -Seconds 1\r\n"
        "$svc = New-Object -ComObject Schedule.Service\r\n"
        "$svc.Connect()\r\n"
        "$task = $svc.GetFolder('\\').GetTasks(0) | Where-Object "
        "{ $_.Name -eq '%(name)s' }\r\n"
        "if ($task) {\r\n"
        "  $sid = ((whoami.exe /user /fo csv /nh) -replace '\"','' "
        "-split ',')[1]\r\n"
        "  try { $task.SetSecurityDescriptor("
        "\"D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGX;;;$sid)\", 0) } catch {}\r\n"
        "}\r\n") % {"name": TASK_NAME, "bat": bat}


def delete_script():
    return ("& schtasks.exe /Delete /TN %s /F | Out-Null\r\n" % TASK_NAME)


def _poll(want, timeout):
    """Ask the task store - it cannot lie the way exit codes do."""
    end = time.time() + timeout
    while time.time() < end:
        if task_installed() == want:
            return True
        time.sleep(CHECK_SEC)
    return False


def task_installed():
    try:
        return _run(["schtasks.exe", "/Query", "/TN", TASK_NAME],
                    timeout=20).returncode == 0
    except Exception:
        return False


def _action_bat():
    """The task's action: one no-spaces .bat that runs powercfg and
    writes the dump next to it. /TR can then be a bare path - the
    quoting-free form that the elevation layers survive."""
    return os.path.join(os.path.dirname(result_path()), "power_dump.bat")


def _dump_bat_text():
    """The bat's body: BOTH powercfg reports into one file, marker in
    between (the requests end, the manual overrides end).

    Single % on purpose: this is a plain string (no % format operator
    ever touches it), and inside a .bat %%~dp0 is the literal text
    "%~dp0" - the task then "successfully" wrote
    C:\Windows\System32\%~dp0power_requests.txt forever. Also echo on
    a word, never "=word": a leading = makes echo sulk."""
    return ("@echo off\r\n"
            "powercfg /requests > \"%~dp0power_requests.txt\" 2>&1\r\n"
            "echo " + OVERRIDE_MARK + " >> \"%~dp0power_requests.txt\"\r\n"
            "powercfg /requestsoverride >> "
            "\"%~dp0power_requests.txt\" 2>&1\r\n")


def install():
    """Tick ON: the task exists AND is visible+runnable to this
    (non-elevated) process when this returns True."""
    path = result_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass
    bat = _action_bat()
    try:
        with open(bat, "w") as f:
            f.write(_dump_bat_text())
    except Exception:
        return False, "could not write the assistant action"
    if not _elevate_ps(create_script(bat)):
        return False, ("the power assistant needs administrator "
                       "privileges to register its scheduled task; the "
                       "confirm was refused, cancelled, or never clicked")
    if not _poll(True, CONFIRM_TIMEOUT):
        return False, ("the power assistant needs administrator "
                       "privileges to register its scheduled task; the "
                       "confirm was refused, cancelled, or never clicked")
    return _start()


def uninstall():
    """Tick OFF: the task is gone when this returns True - verified."""
    if not task_installed():
        return True, "nothing was registered"
    try:
        rc = _run(["schtasks.exe", "/Delete", "/TN", TASK_NAME, "/F"],
                  timeout=20).returncode
    except Exception:
        rc = 1
    if rc != 0 or task_installed():
        _elevate_ps(delete_script(), name="assistant_remove.ps1")
    if not _poll(False, REMOVE_TIMEOUT):
        return False, ("removing the power assistant needs administrator "
                       "privileges; the confirm was refused, cancelled, "
                       "or never clicked")
    return True, "assistant removed"


def _start():
    """Launch a dump run; non-elevated may do this to our own task,
    silently, forever."""
    try:
        _run(["schtasks.exe", "/Run", "/TN", TASK_NAME], timeout=20)
        return True, "assistant started"
    except Exception:
        return False, "schtasks /Run failed"


def requests(ignore=(), assistant=False):
    """{"error": None or str, "display": [str], "other": [str],
    "overridden": [str]}.

    display:    processes holding a DISPLAY-class request (the gate)
    other:      everything else, shown in the window as context
    overridden: holders the user manually silenced with powercfg
                -requestsoverride, prefixed "*OVERRIDE " and shown
                grey - they never gate anything
    """
    ignore = tuple(s.lower() for s in ignore)
    # 1. elevated app: ask powercfg directly
    direct = None
    try:
        out = _run(["powercfg.exe", "/requests"])
        text = out.stdout.decode("utf-8", "replace")
        if out.returncode == 0 and "administrator" not in text.lower():
            try:
                ovr = _run(["powercfg.exe", "/requestsoverride"])
                text += "\n%s\n%s" % (
                    OVERRIDE_MARK, ovr.stdout.decode("utf-8", "replace"))
            except Exception:
                pass                       # requests alone still gates
            direct = _report(text)
        else:
            direct = {"error": "powercfg /requests requires administrator "
                              "privileges (tick the power assistant box to "
                              "read it through a scheduled task)",
                      "display": [], "other": [], "overridden": []}
    except Exception as e:
        direct = {"error": "powercfg failed: %s" % e,
                  "display": [], "other": [], "overridden": []}
    if direct["error"] is None or not assistant:
        return _filtered(direct, ignore)
    # 2. assistant: trigger a fresh dump, read the file it writes
    path = result_path()
    _start()
    # the SYSTEM task needs ~1-2 s to rewrite the file; reading the
    # mtime the instant after /Run would call a healthy assistant
    # "quiet" every time we come back from a quiet spell
    end = time.time() + 5
    while time.time() < end:
        try:
            if time.time() - os.path.getmtime(path) < 20:
                break
        except OSError:
            break                      # missing file: handled below
        time.sleep(0.4)
    try:
        age = time.time() - os.path.getmtime(path)
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return {"error": "the power assistant has not reported yet; the "
                         "checkbox registers a scheduled task, tick it "
                         "off and on again if nothing arrives",
                "display": [], "other": [], "overridden": []}
    if age > STALE_SEC:
        return {"error": "the power assistant went quiet (task deleted?), "
                         "re-tick it in the window",
                "display": [], "other": [], "overridden": []}
    if "administrator" in text.lower() or not text.strip():
        return {"error": "the scheduled task cannot reach powercfg either",
                "display": [], "other": [], "overridden": []}
    return _filtered(_report(text), ignore)


def _filtered(result, ignore):
    """The ignore list trims known noise from every bucket (and from
    the structured entries the manager window reads)."""
    if not ignore:
        return result
    keep = lambda line: not any(n in line.lower() for n in ignore)
    return {"error": result["error"],
            "display": [x for x in result["display"] if keep(x)],
            "other": [x for x in result["other"] if keep(x)],
            "overridden": [x for x in result.get("overridden", [])
                           if keep(x)],
            "requests": [e for e in result.get("requests", [])
                         if keep(e["text"])],
            "override_entries": result.get("override_entries", [])}
