"""The instance guard's CONTRACT, at the process level (the twin law).

Boots the REAL app twice against a scratch state dir and pins what the
guard promises:

  * exactly two "boot (pid" lines in the scratch log - both spawns
    reached the log line BEFORE any guard decision (cli.py:52-57)
  * exactly one "instance guard: won" - one process passed
    _single_instance (cli.py:247-249)
  * exactly one "already running" - the twin confessed and stood down
    (cli.py:231), no second camera, no second tray icon
  * a live census sees exactly one pythonw PAIR remaining: the venv
    pythonw is a redirector that re-execs the base pythonw as its
    child (measured Oct 12: parent + child, both named pythonw.exe),
    so the survivor is two processes. The twin's stand-down dialog
    is dismissed BY THIS SUITE: the app's MessageBoxTimeoutW call
    (cli.py:239-245) passes its 5000 ms into the wLanguage slot and
    a pointer into dwTimeout, so the box never self-dismisses
    (measured: the twin sat behind it indefinitely) - in production
    a human clicks it; here the suite plays that role before the
    census.

Skips (rc 0, marker "SKIP guard") when a live instance already holds
the mutex - the guard is GLOBAL per user, so a live tray would make
BOTH spawns lose and the census measure the developer's app, not the
law. run_all.ps1 reads the marker and refuses to certify the skip as
a complete green.

Census is ctypes Toolhelp32 (psutil is NOT installed in this venv -
the packet's named alternative). Cleanup kills both the venv pid and
the re-exec'd child whatever the test verdict; scratch removal is
best-effort. No -u: pythonw has no stdio to buffer; the log file IS
the interface.
"""
import ctypes
import ctypes.wintypes as wt
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYW = os.path.join(ROOT, ".venv", "Scripts", "pythonw.exe")
FAILED = []


def _fail(msg):
    print("FAIL: " + msg)
    FAILED.append(msg)


k32 = ctypes.windll.kernel32

# skip probe first: the guard is global per user, a live tray poisons
# the whole census - 3-line shape from gaming_ui_test.py:87-93, the
# Global\ name and the bare belt the OLD builds still hold
_held = None
try:
    k32.OpenMutexW.restype = ctypes.c_void_p
    _held = k32.OpenMutexW(0x00100001, False, "Global\\PanelBoss")
    if not _held:      # the transition belt: an OLD build still
        _held = k32.OpenMutexW(   # running under
            0x00100001, False, "PanelBoss")           # the bare name
except Exception:
    pass
if _held:
    print("SKIP guard: a live instance holds the mutex")
    sys.exit(0)


class _PE(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD),
                ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                ("th32ParentProcessID", wt.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wt.DWORD),
                ("szExeFile", wt.WCHAR * 260)]


# 64-bit discipline (cli.py:183-188): default restypes truncate HANDLEs
k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.c_void_p]
k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.c_void_p]
k32.OpenProcess.restype = wt.HANDLE
k32.OpenProcess.argtypes = [wt.DWORD, wt.INT, wt.DWORD]
k32.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]
k32.CloseHandle.argtypes = [wt.HANDLE]


def _tree(roots):
    """live processes that ARE one of `roots` or a DIRECT child of one
    - the redirector and its re-exec'd interpreter, the pair."""
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)      # TH32CS_SNAPPROCESS
    out = []
    pe = _PE()
    pe.dwSize = ctypes.sizeof(_PE)
    if k32.Process32FirstW(snap, ctypes.byref(pe)):
        while True:
            if pe.th32ProcessID in roots or pe.th32ParentProcessID in roots:
                out.append((pe.th32ProcessID, pe.th32ParentProcessID,
                            pe.szExeFile))
            if not k32.Process32NextW(snap, ctypes.byref(pe)):
                break
    k32.CloseHandle(snap)
    return out


def _kill_tree(roots):
    # child first: the redirector must never outlive the interpreter
    # it waits on (sort key False = child, True = the spawned root)
    for pid, _pp, _n in sorted(_tree(roots), key=lambda p: p[1] not in roots):
        h = k32.OpenProcess(0x0001, False, pid)      # PROCESS_TERMINATE
        if h:
            k32.TerminateProcess(h, 1)
            k32.CloseHandle(h)


def _by_root(tree, root_pid):
    return [p for p in tree if p[0] == root_pid or p[1] == root_pid]


scratch = tempfile.mkdtemp(prefix="panelboss_guard_")
# the app's own layout: PANELBOSS_CONFIG_DIR wins over %APPDATA%
# (config.py:39) and LOG_DIR defaults to CONFIG_DIR\logs (config.py:41,
# the file handler at :514-521) -> the scratch log is <scratch>\logs\
# panelboss.log. PANELBOSS_STATE was the packet's name; reality says
# PANELBOSS_CONFIG_DIR - same redirect, honest label.
env = dict(os.environ)
env["PANELBOSS_CONFIG_DIR"] = scratch
log_path = os.path.join(scratch, "logs", "panelboss.log")
p1 = p2 = None
try:
    p1 = subprocess.Popen([PYW, "-m", "panelboss"], cwd=ROOT, env=env)
    time.sleep(2)                       # the packet's ~2 s apart
    p2 = subprocess.Popen([PYW, "-m", "panelboss"], cwd=ROOT, env=env)
    pids = {p1.pid, p2.pid}

    text = ""
    deadline = time.time() + 40
    while time.time() < deadline:
        try:
            with open(log_path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            pass
        if text.count("boot (pid") >= 2 and "already running" in text:
            break
        time.sleep(0.5)

    n_boot = text.count("boot (pid")
    n_won = text.count("instance guard: won")
    n_dup = text.count("already running")
    if n_boot != 2:
        _fail("%d 'boot (pid' lines, want exactly 2 (log tail: %s)"
              % (n_boot, text[-300:].replace("\n", " | ")))
    if n_won != 1:
        _fail("%d 'instance guard: won', want exactly 1" % n_won)
    if n_dup != 1:
        _fail("%d 'already running', want exactly 1" % n_dup)

    # dismiss the twin the way production expects a human to (its
    # dialog is where it stands down): the Oct 12 call at cli.py:239
    # passes 5000 into the wLanguage slot and a POINTER into
    # dwTimeout, so MessageBoxTimeoutW NEVER self-dismisses - the
    # "closes on its own" comment is aspirational. The suite IS the
    # click; the census then measures what survives.
    _kill_tree({p2.pid})
    try:
        p2.wait(10)
    except Exception:
        pass

    # census: the winner's pair is the ONLY survivor - both
    # processes named pythonw.exe (redirector + re-exec'd base
    # interpreter)
    tree = []
    deadline = time.time() + 10
    while time.time() < deadline:
        tree = _tree(pids)
        if len(_by_root(tree, p1.pid)) >= 2 and not _by_root(tree, p2.pid):
            break
        time.sleep(0.5)
    win = _by_root(tree, p1.pid)
    twin = _by_root(tree, p2.pid)
    if len(win) != 2 or not all("pythonw" in p[2].lower() for p in win):
        _fail("census: winner tree is %s, want exactly one pythonw "
              "pair (redirector + re-exec'd interpreter)" % (win,))
    if twin:
        _fail("census: the twin's pair is still live: %s" % (twin,))
    print("census: exactly one pythonw pair remains: %s; twin pair gone"
          % [(p[0], p[2]) for p in win])
finally:
    _kill_tree({p.pid for p in (p1, p2) if p is not None})
    for p in (p1, p2):
        if p is not None:
            try:
                p.wait(10)
            except Exception:
                pass
    # a killed process lingers in the snapshot until the reaper runs:
    # poll the vacancy, don't race it
    left = []
    _end = time.time() + 10
    while time.time() < _end:
        left = _tree({p.pid for p in (p1, p2) if p is not None})
        if not left:
            break
        time.sleep(0.5)
    if left:
        _fail("cleanup: spawned processes still live: %s" % (left,))
    shutil.rmtree(scratch, ignore_errors=True)

if FAILED:
    print("guard test FAILED in", FAILED)
    sys.exit(1)
print("guard OK")
