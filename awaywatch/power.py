"""powercfg /requests, parsed, with an opt-in scheduled-task assistant.

Catching the case where some *other* app already pins the display
awake (a player, a game, a WebView2 video wake lock): there is no
point polling the camera to defend a screen someone else has claimed.

The trouble: powercfg /requests needs elevation; unelevated it prints
"This command requires administrator privileges" and exits 1. There is
no official non-admin user-mode API (measured, Windows 11 26220).

The workaround (classic "elevated shortcut without the UAC prompt"):
register a Task Scheduler task ONCE with /RL HIGHEST - which costs one
UAC prompt, and the settings window only does that when the user ticks
the power assistant box. Afterwards a NON-elevated app may start its
own task with `schtasks /Run` silently, and the task dumps fresh
powercfg output to a file we read. Everything still fails open: any
problem means "unblocked", camera polling continues, and the error
string is what the settings window shows.
"""

import os
import subprocess
import time

TASK_NAME = "ICU-Presence-PowerRequests"

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
    return subprocess.run(args, capture_output=True, timeout=timeout)


def _need_elevation(args):
    """One UAC prompt is the deal we struck with the user (they ticked
    the box). Returns the process exit code, or -1 on trouble."""
    quoted = ", ".join("'" + a.replace("'", "''") + "'" for a in args)
    ps = ("exit (Start-Process -FilePath schtasks.exe -ArgumentList @(%s) "
          "-Verb RunAs -Wait -PassThru).ExitCode" % quoted)
    try:
        return _run(["powershell.exe", "-NoProfile", "-NonInteractive",
                     "-Command", ps], timeout=120).returncode
    except Exception:
        return -1


def task_installed():
    try:
        return _run(["schtasks.exe", "/Query", "/TN", TASK_NAME],
                    timeout=20).returncode == 0
    except Exception:
        return False


def install():
    """Register (elevated, one prompt) + start the assistant. Returns
    (ok, message)."""
    path = result_path()
    folder = os.path.dirname(path)
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception:
        pass
    action = 'cmd /c powercfg /requests > "%s" 2>&1' % path
    args = ["/Create", "/TN", TASK_NAME, "/SC", "ONDEMAND", "/RL",
            "HIGHEST", "/TR", action, "/F"]
    try:
        rc = _run(["schtasks.exe"] + args, timeout=20).returncode
    except Exception:
        rc = 1
    if rc != 0:
        rc = _need_elevation(args)
    if rc != 0:
        return False, ("registering the power assistant requires "
                       "administrator privileges (one UAC confirm), and it "
                       "was refused or cancelled")
    return _start()


def uninstall():
    if not task_installed():
        return True, "nothing was registered"
    args = ["/Delete", "/TN", TASK_NAME, "/F"]
    try:
        rc = _run(["schtasks.exe"] + args, timeout=20).returncode
    except Exception:
        rc = 1
    if rc != 0:
        rc = _need_elevation(args)
    if rc != 0:
        return False, ("removing the power assistant requires "
                       "administrator privileges (one UAC confirm)")
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
