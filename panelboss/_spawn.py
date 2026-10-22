"""Every child process this windowless app starts, through ONE door.

Why a door and not per-site flags (the owner's strobe report, Oct 13
night - "a cascade of cmd windows too fast to read"): a windowless
parent (pythonw) gets a fresh, VISIBLE console for every console-app
child, and on Windows 11 25H2 any console that IS created is hosted
by Windows Terminal, which pops AND steals focus (measured; the
lesson power.py carried alone). One flag pair, applied in one place,
is the only shape that cannot drift: a call site cannot forget what
it never gets to type. The belt is BOTH halves -

  CREATE_NO_WINDOW     (process-creation flag: no console is
                        allocated for the child at all)
  STARTF_USESHOWWINDOW
  + wShowWindow=SW_HIDE(STARTUPINFO: if the child is a shell that
                        allocates its OWN conhost/WT window, it is
                        born hidden)

The declared exceptions to the door are the updater, ONE PER INSTALL
KIND: update.bat (source) and the frozen copy's apply.bat handoff
BOTH RUN IN THEIR OWN VISIBLE CONSOLE (the window is the progress UI
and it carries the relaunch); each call site passes an explicit
creationflags=0 with a "# CONSOLE: deliberate" marker, and
scripts/startup_test.py + scripts/gaming_test.py fail the build if
any other bare subprocess/os.system verb appears in the package.
"""
import subprocess
import sys


def win_flags():
    """The belt pair, importable so the pin can read the construction
    without spawning anything."""
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return subprocess.CREATE_NO_WINDOW, si


def run(args, **kw):
    """subprocess.run through the no-window door. Caller kwargs pass
    through; a caller's own creationflags are OR-ed into the belt,
    never replaced - the door can only ever make a verb quieter."""
    if sys.platform.startswith("win"):
        flags, si = win_flags()
        kw["creationflags"] = kw.get("creationflags", 0) | flags
        kw.setdefault("startupinfo", si)
    return subprocess.run(args, **kw)


def popen(args, **kw):
    """subprocess.Popen through the same door, same law."""
    if sys.platform.startswith("win"):
        flags, si = win_flags()
        kw["creationflags"] = kw.get("creationflags", 0) | flags
        kw.setdefault("startupinfo", si)
    return subprocess.Popen(args, **kw)
