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
import subprocess
import time

TASK_NAME = "ICU-Presence-PowerRequests"

# consent dialogs wait for humans; this is how long we give the task
# store to reflect a create/delete before calling it a refusal
CONFIRM_TIMEOUT = 180
REMOVE_TIMEOUT = 90
CHECK_SEC = 2.0

# section names that mean "the screens themselves are being held awake";
# System/Awaymode/multimedia only hold sleep off, the monitor can still
# darken, so they are listed for information but never block polling
DISPLAY_WORDS = ("display", "monitor", "console")

# an assistant dump older than this is a broken/removed task, not news
STALE_SEC = 60


def result_path():
    """Where the scheduled task drops its report; per-user, stable."""
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(root, "ICU-PresenceDetector", "power_requests.txt")


def _own_pid_tokens():
    pid = os.getpid()
    return ("0x%x" % pid, "0x%X" % pid, str(pid))


def _parse(text):
    """Sections at column 0 ending in ':'; items inside them. Newer
    powercfg uses DISPLAY: / SYSTEM: headers with [PROCESS] lines and a
    reason line below; both layouts parse."""
    display = []
    other = []
    section = "unknown"
    mine = _own_pid_tokens()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower() in ("none", "none.", "no"):
            continue
        if not line[0].isspace() and stripped.endswith(":"):
            section = stripped[:-1]
            continue
        low = stripped.lower()
        if any(token in low for token in mine):
            continue                     # our own keep-awake, not news
        if low.startswith("[process] "):
            stripped = stripped[len("[PROCESS] "):]
            low = stripped.lower()
        if any(word in section.lower() for word in DISPLAY_WORDS):
            display.append(stripped)
        else:
            other.append("%s: %s" % (section, stripped))
    return {"error": None, "display": display, "other": other}


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
            # single % on purpose: this is a plain string (no % format
            # operator), and inside a .bat %%~dp0 is the literal text
            # "%~dp0" - the task then "successfully" wrote
            # C:\Windows\System32\%~dp0power_requests.txt forever
            f.write("@echo off\r\npowercfg /requests > "
                    "\"%~dp0power_requests.txt\" 2>&1\r\n")
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
    """{"error": None or str, "display": [str], "other": [str]}.

    display: processes holding a DISPLAY-class request (the gate)
    other:   everything else, shown in the window as context
    """
    ignore = tuple(s.lower() for s in ignore)
    # 1. elevated app: ask powercfg directly
    direct = None
    try:
        out = _run(["powercfg.exe", "/requests"])
        text = out.stdout.decode("utf-8", "replace")
        if out.returncode == 0 and "administrator" not in text.lower():
            direct = _parse(text)
        else:
            direct = {"error": "powercfg /requests requires administrator "
                              "privileges (tick the power assistant box to "
                              "read it through a scheduled task)",
                      "display": [], "other": []}
    except Exception as e:
        direct = {"error": "powercfg failed: %s" % e,
                  "display": [], "other": []}
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
        time.sleep if False else None
        time.sleep(0.4)
    try:
        age = time.time() - os.path.getmtime(path)
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return {"error": "the power assistant has not reported yet; the "
                         "checkbox registers a scheduled task, tick it "
                         "off and on again if nothing arrives",
                "display": [], "other": []}
    if age > STALE_SEC:
        return {"error": "the power assistant went quiet (task deleted?), "
                         "re-tick it in the window",
                "display": [], "other": []}
    if "administrator" in text.lower() or not text.strip():
        return {"error": "the scheduled task cannot reach powercfg either",
                "display": [], "other": []}
    return _filtered(_parse(text), ignore)


def _filtered(result, ignore):
    """The ignore list trims known noise from both buckets."""
    if not ignore:
        return result
    keep = lambda line: not any(n in line.lower() for n in ignore)
    return {"error": result["error"],
            "display": [x for x in result["display"] if keep(x)],
            "other": [x for x in result["other"] if keep(x)]}
