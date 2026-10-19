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
VALUE_NAME = "PanelBoss"                       # the name Task Manager shows
# the pre-rename value name: recognized so an old install's entry is
# found and replaced, never kept twice
LEGACY_VALUE_NAME = "ICU Presence Detector"
# Windows never tells a launched app WHY the shell launched it
# (explorer.exe parents everything: Run key, Startup folder,
# double-click). So the entry stamps the fact itself - every serious
# app in the Run key passes itself a flag (Opera: --autostart,
# Battle.net: --autostarted); now this one does too, and cli reads
# it as proof rather than inference.
FLAG = " --autostart"


def command():
    """The exact string the Run key value holds for this install."""
    if getattr(sys, "frozen", False):         # PyInstaller: the exe IS
        return '"%s"%s' % (sys.executable, FLAG)   # the launcher
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pyw = os.path.join(root, ".venv", "Scripts", "pythonw.exe")
    if not os.path.isfile(pyw):               # moved venv: the running
        pyw = sys.executable                    # interpreter knows best
    return '"%s" "%s"%s' % (pyw, os.path.join(root, "run.py"), FLAG)


def selfheal():
    """An old flagless entry learns the stamp in place, because
    recognizing the logon copy must be a fact. Touched only when the
    stored string differs from ours by exactly the missing flag - a
    different path means the app moved, and that difference is
    meaningful (the switch note explains it); it is left alone.
    Returns True after a rewrite, False on a failed one, None when
    there was nothing to do.

    THE REGISTRATION LAW (defect 4, the wave-C fossil): this is the
    ONLY boot-path writer of the Run value, and it never REGISTERS a
    fresh entry - an absent box stays absent, so a virgin launch is
    dark. A present entry is re-STAMPED (ours, flagless) or re-POINTED
    by migrate_once (legacy name), never created here. Both branches
    log by name: 'autostart selfheal: <decision>' is the line to grep
    when the switch and the registry disagree - if a future change
    resurrects the entry at boot, this is where it shows."""
    stored = enabled()
    if stored is None:
        log.info("autostart selfheal: no entry, no registration (dark "
                 "by law; only the opt-in switch writes the Run value)")
        return None
    if stored + FLAG != command():
        log.info("autostart selfheal: entry not ours or already stamped "
                 "(left alone; a moved path is meaningful, see the switch "
                 "note)")
        return None
    ok, msg = enable()
    log.info("old autostart entry taught %s: %s", FLAG.strip(), msg)
    return ok


def enabled():
    """The stored command line, or None. Any entry counts, even a
    stale one from a deleted folder: the checkbox lights anyway, and
    toggling re-points the entry here. The pre-rename name counts too:
    a found legacy entry is replaced, never duplicated."""
    try:
        import winreg as reg
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_PATH,
                         access=reg.KEY_READ) as key:
            try:
                value, _ = reg.QueryValueEx(key, VALUE_NAME)
                return value or None
            except OSError:
                value, _ = reg.QueryValueEx(key, LEGACY_VALUE_NAME)
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
            try:
                reg.DeleteValue(key, LEGACY_VALUE_NAME)
            except Exception:
                pass                            # one entry per app: the
                                                # new name replaces it
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


def ensure_crash_dumps():
    """Arms WER LocalDumps for pythonw.exe, fail-open: WER Event 1000
    (Oct 19, pid 23004, python310.dll +0x487d, 0xc0000005) arrived with
    no dump because LocalDumps was never configured. The key name is
    the EXECUTABLE, so a python.exe (console) death writes elsewhere
    and stays uncollected - the tray app's pythonw.exe is the one that
    owns no stderr and cannot confess. Same fail-open re-read style as
    the Run value above: the registry is the truth, written once per
    launch, no harm in re-arming."""
    try:
        import winreg as reg
        folder = os.path.join(os.environ.get("LOCALAPPDATA", "."),
                              "CrashDumps")
        path = (r"Software\Microsoft\Windows\Windows Error Reporting"
                r"\LocalDumps\pythonw.exe")
        # CreateKey, not OpenKey: the WER path does not pre-exist (the
        # Oct 19 dossier's own finding - LocalDumps was never
        # configured), and OpenKey refuses it with WinError 2 (live
        # probe). CreateKey opens-or-creates the whole chain.
        with reg.CreateKey(reg.HKEY_CURRENT_USER, path) as key:
            reg.SetValueEx(key, "DumpType", 0, reg.REG_DWORD, 2)
            reg.SetValueEx(key, "DumpFolder", 0, reg.REG_SZ, folder)
            reg.SetValueEx(key, "DumpCount", 0, reg.REG_DWORD, 10)
            dtype, _ = reg.QueryValueEx(key, "DumpType")
    except OSError as exc:
        log.warning("crash dumps: registry refused the write: %s", exc)
        return
    except Exception:
        log.exception("crash dumps arming failed")
        return
    if dtype != 2:
        log.warning("crash dumps: read-back says %s, not 2", dtype)
    else:
        log.info("crash dumps armed: %s (10 full dumps)", folder)


def disable():
    """Returns (ok, message); absent counts as success."""
    try:
        import winreg as reg
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_PATH,
                         access=reg.KEY_SET_VALUE) as key:
            gone = 0
            for name in (VALUE_NAME, LEGACY_VALUE_NAME):
                # both names, independently: an absent new entry must
                # not hide a legacy twin (the FileNotFoundError on the
                # first delete used to skip the second, leaving the
                # checkbox to re-light itself at the next toggle)
                try:
                    reg.DeleteValue(key, name)
                    gone += 1
                except FileNotFoundError:
                    pass
            if not gone:
                return True, "nothing was registered"
    except OSError as exc:
        return False, "registry refused the delete: %s" % exc
    except Exception as exc:
        log.exception("startup disable failed")
        return False, "registry refused the delete: %s" % exc
    log.info("start with Windows: removed")
    return True, "removed"
