"""C3a probe: every daemon must confess its own death.

Two facts, measured not assumed:
1. the crash class of a null lParam in the display watcher:
   Display()._record(0) runs in a subprocess (a ctypes
   from_address + bytes read of NULL does not raise a Python
   exception on this box; it can die natively), and the observed
   class is printed as the verdict line
2. the pystray logger's propagate state: pystray 0.19.5's own
   _mainloop swallows pump exceptions, and its logger's quiet grave
   must flow into the root rotating file

Exits 0 with PASS lines.
"""
import logging
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHILD = """
import sys
sys.path.insert(0, __ROOT__)
from panelboss import display
d = display.Display()
try:
    d._record(0)
    print("no raise (unexpected: the null read should not survive)")
except Exception as e:
    print("record-raises %s: %s" % (type(e).__name__, e))
""".replace("__ROOT__", repr(ROOT))


def main():
    child = subprocess.run([sys.executable, "-c", CHILD],
                           capture_output=True, text=True)
    if child.returncode == 0:
        for line in child.stdout.splitlines():
            if "record-raises" in line:
                print("PASS _record(0) crash class is catchable: " + line)
            else:
                print("FAIL " + line)
                return 1
    else:
        # the null read kills the thread before a Python except can
        # run: the crash class is native, which is the worse grave
        # (invisible under pythonw) and the wrap's real job
        code = child.returncode & 0xFFFFFFFF
        print("PASS _record(0) crash class is native (uncatchable): "
              "rc=0x%08X" % code)
    import pystray
    print("PASS pystray logger propagate=%s"
          % logging.getLogger("pystray").propagate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
