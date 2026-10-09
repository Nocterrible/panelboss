""""Start with Windows": the per-user Run key.

One registry value, written on tick and deleted on untick: the
classic per-user autostart. No admin, no task scheduler, and it is
exactly what Task Manager's "Startup apps" page and Settings list, so
the user can verify this app's entry in system UI without trusting
this README.

The registry is the truth, not the config file: enabled() reads it
back every time (the same lesson the power switch learned from the
task store - entries outlive or predate any rumor). Writes verify
themselves by a re-read, and every failure comes back as a message,
never a raised exception: the app fails open.

The stored command always points at THIS running copy: frozen exe ->
the exe; repo -> venv pythonw + run.py. Move the folder and the old
entry keeps firing at logon (the mutex politely refuses the second
instance); flipping the switch off and on re-points it.
"""

import logging
import os
import sys

log = logging.getLogger("startup")

RUN_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "ICU Presence Detector"      # the name Task Manager shows


def command():
    """The exact string the Run key value holds for this install."""
    if getattr(sys, "frozen", False):         # PyInstaller: the exe IS
        return '"%s"' % sys.executable         # the launcher
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pyw = os.path.join(root, ".venv", "Scripts", "pythonw.exe")
    if not os.path.isfile(pyw):               # moved venv: the running
        pyw = sys.executable                    # interpreter knows best
    return '"%s" "%s"' % (pyw, os.path.join(root, "run.py"))


def enabled():
    """The stored command line, or None. Any ICU entry counts, even a
    stale one from a deleted folder: the checkbox lights anyway, and
    toggling re-points the entry here."""
    try:
        import winreg as reg
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_PATH,
                         access=reg.KEY_READ) as key:
            value, _ = reg.QueryValueEx(key, VALUE_NAME)
        return value or None
    except OSError:
        return None                            # absent is the normal
    except Exception:                          # hive policy, locked
        log.exception("startup query failed")  # down-key, whatever
        return None


def enable():
    """Returns (ok, message); the write is read back to prove it."""
    try:
        import winreg as reg
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_PATH,
                         access=reg.KEY_READ | reg.KEY_SET_VALUE) as key:
            reg.SetValueEx(key, VALUE_NAME, 0, reg.REG_SZ, command())
            stored, _ = reg.QueryValueEx(key, VALUE_NAME)
    except OSError as exc:
        return False, "registry refused the write: %s" % exc
    except Exception as exc:
        log.exception("startup enable failed")
        return False, "registry refused the write: %s" % exc
    ok = (stored or "") == command()
    log.info("start with Windows: %s", command() if ok else "failed")
    return ok, command() if ok else "registry did not keep the entry"


def disable():
    """Returns (ok, message); absent counts as success."""
    try:
        import winreg as reg
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_PATH,
                         access=reg.KEY_SET_VALUE) as key:
            reg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        return True, "nothing was registered"
    except OSError as exc:
        return False, "registry refused the delete: %s" % exc
    except Exception as exc:
        log.exception("startup disable failed")
        return False, "registry refused the delete: %s" % exc
    log.info("start with Windows: removed")
    return True, "removed"
