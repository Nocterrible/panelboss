"""One-shot evidence probe for wm.foreground() and wm.has_xinput().

Exit 0 when all four lines pass; 1 on the first failed assertion.
Line 3 spawns a child that dlopens xinput1_3.dll, polls detection, then
kills and reaps it (no orphan).
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, r"F:\Projects\ICU-PresenceDetector")

from awaywatch import wm

failures = []


def check(label, ok, detail=""):
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {label}" + (f" - {detail}" if detail else ""))
    if not ok:
        failures.append(label)


# 1. foreground() must return a complete dict for the current fg window.
fg = wm.foreground()
print(f"foreground() -> {fg}")
check("foreground() complete",
      fg is not None and fg["proc"] and fg["rect"][2] > 0 and "pid" in fg,
      repr(fg))

# 2. Our own process never loads xinput -> False.
check("has_xinput(self) is False", wm.has_xinput(os.getpid()) is False)

# 3. Positive control: a child with xinput1_3.dll loaded must be
# detected. CAREFUL: the venv python.exe is a redirector - Popen'ing
# sys.executable yields a SHIM pid, the interpreter that actually
# loads xinput is its child. The child reports its own pid; that is
# the process to interrogate, and the whole tree dies together.
pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "_xchild.pid")
try:
    os.remove(pid_file)
except OSError:
    pass
child = subprocess.Popen(
    [sys.executable, "-c",
     "import ctypes, os, sys, time; ctypes.WinDLL('xinput1_3.dll'); "
     "open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(30)",
     pid_file])
try:
    deadline = time.monotonic() + 5.0
    target = None
    while time.monotonic() < deadline and target is None:
        try:
            with open(pid_file) as fh:
                target = int(fh.read().strip())
        except (OSError, ValueError):
            time.sleep(0.1)
    hit = False
    while time.monotonic() < deadline and not hit:
        hit = bool(target) and wm.has_xinput(target)
        if not hit:
            time.sleep(0.1)
finally:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(child.pid)],
                   capture_output=True)  # shim + interpreter: no orphan
    try:
        os.remove(pid_file)
    except OSError:
        pass
check("has_xinput(xinput child) is True", hit, f"target={target}")

# 4. Dead pid -> False (OpenProcess gives a valid handle; First must fail).
check("has_xinput(999999) is False", wm.has_xinput(999999) is False)

if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("all checks passed")
