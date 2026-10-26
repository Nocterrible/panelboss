"""The Run-key contract, executed IN the user's hive under a scratch
value name (self-cleaning): enable writes and proves the write by
reading back; disable is idempotent; every failure comes back as a
message, never an exception; the tray toggle flips whatever the
registry holds and the window resyncs from the same truth."""
import logging
import queue
import os
import sys

logging.disable()             # the refusal branches log by design

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panelboss import startup, tray

real_exe = sys.executable
real_reg = sys.modules["winreg"]
startup.VALUE_NAME = "PanelBoss TEST SCRATCH"
startup.LEGACY_VALUE_NAME = "PanelBoss LEGACY TEST SCRATCH"

# 1) the stored command: quoted (paths love spaces), venv pythonw,
#    run.py, absolute - the Run key has no cwd to lean on
cmd = startup.command()
assert cmd.startswith('"') and cmd.endswith(" --autostart"), cmd
assert "pythonw.exe" in cmd and "run.py" in cmd, cmd

# 2) frozen: the exe IS its own launcher, args be damned
sys.frozen = True
sys.executable = r"C:\a b\PanelBoss.exe"
assert startup.command() == r'"C:\a b\PanelBoss.exe" --autostart'
del sys.frozen
sys.executable = real_exe

# 3) round trip in the real hive
startup.disable()                 # self-heal from any crashed run
assert startup.enabled() is None, "scratch name must be absent first"
ok, msg = startup.enable()
assert ok and msg == startup.command()
assert startup.enabled() == startup.command(), "verify-by-read is the contract"
ok, msg = startup.disable()
assert ok
assert startup.enabled() is None
ok, msg = startup.disable()
assert ok and "nothing" in msg, "absent counts as removed, twice"

# 3b) login recognition: the shell never tells the launched app
#     WHY it launched it, so the entry stamps that fact itself -
#     and selfheal teaches the flagless old ones. An entry that
#     differs by MORE than the flag is a moved app: that difference
#     is meaningful, so it is left alone.
assert startup.command().endswith(startup.FLAG)


def _store(val):
    import winreg as r
    with r.OpenKey(r.HKEY_CURRENT_USER, startup.RUN_PATH,
                   access=r.KEY_READ | r.KEY_SET_VALUE) as k:
        r.SetValueEx(k, startup.VALUE_NAME, 0, r.REG_SZ, val)


_store(startup.command()[:-len(startup.FLAG)])    # the old form
assert startup.enabled() == startup.command()[:-len(startup.FLAG)]
assert startup.selfheal() is True, "flagless entry learns the stamp"
assert startup.enabled() == startup.command(), "verified by re-read"
assert startup.selfheal() is None, "a current entry heals nothing"
_store("junk")                                    # not ours at all
assert startup.selfheal() is None
assert startup.enabled() == "junk", "foreign entry untouched"
startup.disable()

# 3c) THE DISCIPLINE PIN (defect 4, the wave-C fossil): a boot pass
#     must NEVER register a fresh Run value when the box is dark - the
#     value is the opt-in, so absent means absent, and only the switch
#     may create it. The flag here IS the registry value (this design
#     keeps no [ui] autostart config key; the registry is the single
#     truth), so "flag false + value present = the flag loses at next
#     save" is enforced at the ONE boot writer, startup.selfheal(): it
#     re-stamps/re-points an EXISTING entry, never creates one. The
#     named log line proves the decision (grep "autostart selfheal:").
import io as _io, logging as _lg
_buf = _io.StringIO()
_h = _lg.StreamHandler(_buf)
_h.setLevel(_lg.INFO)
_slog = logging.getLogger("startup")
logging.disable(_lg.NOTSET)             # the pin must SEE the line
_old_level = _slog.level
_slog.setLevel(_lg.INFO)
_slog.addHandler(_h)
startup.disable()                        # guarantee a dark box
assert startup.enabled() is None
assert startup.selfheal() is None, "a clean boot must not register"
assert startup.enabled() is None, "selfheal created a fresh value!"
_slog.removeHandler(_h)
_slog.setLevel(_old_level)
logging.disable()                        # back to quiet for the refusals
assert "no entry, no registration" in _buf.getvalue(), (
    "the selfheal decision must be named in the log, got %r"
    % _buf.getvalue())
print("startup discipline pin OK (no registration on a dark box, named line)")

# 4a) refusal modes: an unimportable winreg must not crash the app
sys.modules["winreg"] = None
ok, msg = startup.enable()
assert not ok and "refused" in msg
assert startup.enabled() is None
ok, msg = startup.disable()
assert not ok and "refused" in msg
sys.modules["winreg"] = real_reg


# 4b) a hive that raises on every open gets the same message treatment
class Liar:
    HKEY_CURRENT_USER = 0x80000001
    KEY_READ = KEY_SET_VALUE = 1
    REG_SZ = 1

    def OpenKey(self, *args, **kw):
        raise OSError("the hive is locked down")

    def QueryValueEx(self, *args, **kw):
        raise OSError("no")

    def SetValueEx(self, *args, **kw):
        raise OSError("no")

    def DeleteValue(self, *args, **kw):
        raise OSError("no")


sys.modules["winreg"] = Liar()
ok, msg = startup.enable()
assert not ok and "refused" in msg
assert startup.enabled() is None
ok, msg = startup.disable()
assert not ok and "refused" in msg
sys.modules["winreg"] = real_reg

# 5) the tray: one click flips reality, the window gets told to resync
startup.disable()                 # crashed-run insurance again
assert startup.enabled() is None
t = tray.Tray(queue.Queue(), None, ui_events=queue.Queue())
assert t._startup_checked(None) is False
t._startup()
assert t._startup_checked(None), "registry now says yes"
assert t.ui_events.get_nowait() == ("startup", None)
t._startup()
assert t._startup_checked(None) is False, "one click flips, always"
assert startup.enabled() is None, "and the click cleans up"

# 6) THE NO-WINDOW DOOR (the owner's strobe report, Oct 13 night):
#    every child verb rides panelboss/_spawn.py's belt pair -
#    CREATE_NO_WINDOW (no console allocated) plus
#    STARTUPINFO.wShowWindow=SW_HIDE (a shell's own conhost/WT
#    window is born hidden). The flags are pinned in the
#    CONSTRUCTION (visible-window behavior is untestable offline,
#    the flags are the law), and one real verb proves the door
#    opens: cmd /c ver through it, no elevation, app-agnostic.
import subprocess as _sp
from panelboss import _spawn
flags, si = _spawn.win_flags()
assert flags == _sp.CREATE_NO_WINDOW == 0x08000000, hex(flags)
assert si.dwFlags & _sp.STARTF_USESHOWWINDOW
assert si.wShowWindow == _sp.SW_HIDE
_r = _spawn.run(["cmd", "/c", "ver"], capture_output=True, timeout=15)
assert _r.returncode == 0 and b"Windows" in _r.stdout, _r


# ---- SPAWN BAN v2 (LOCKSTEP COPY: scripts/gaming_test.py carries the
# same scan - change both or neither). v2 closes the alias holes the
# gate caught (findings 3/4): `import subprocess as sp` and
# `from subprocess import run[, Popen][ as alias]` must not smuggle a
# bare verb past the module-qualified pattern, and creationflags is
# required INSIDE the call's own paren range (a flag mentioned in
# unrelated nearby text is not compliance).
def _spawn_ban(pkg_dir):
    """no bare console verbs anywhere in the package: a call is legal
    only inside the door module, or with an explicit creationflags
    (the updater's declared visible console). The ban scans call
    sites, not trust - the strobe class dies when FORGETTING is
    impossible, not when remembering is polite."""
    import io as _io, re as _re
    verbs = r"(?:run|Popen|call|check_call|check_output)"

    def _range(src, open_idx):
        depth = 0
        for i in range(open_idx, len(src)):
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
                if depth == 0:
                    return src[open_idx:i + 1]
        return ""                       # unbalanced: treated as no flags

    bad = []
    for root, dirs, files in os.walk(pkg_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            if not fn.endswith(".py") or fn == "_spawn.py":
                continue
            src = _io.open(os.path.join(root, fn), encoding="utf8").read()
            pats = [r"subprocess\." + verbs + r"\s*\("]
            for m in _re.finditer(r"import\s+subprocess\s+as\s+(\w+)", src):
                pats.append(_re.escape(m.group(1)) + r"\." + verbs + r"\s*\(")
            for m in _re.finditer(r"from\s+subprocess\s+import\s+([^\n(]+)",
                                  src):
                for part in m.group(1).split(","):
                    names = [n.strip() for n in part.split(" as ")
                             if n.strip()]
                    if names and names[0] in (
                            "run", "Popen", "call", "check_call",
                            "check_output"):
                        pats.append(r"(?<![\w.])" + _re.escape(names[-1])
                                    + r"\s*\(")
            for pat in pats:
                for m in _re.finditer(pat, src):
                    if "creationflags" not in _range(src, m.end() - 1):
                        bad.append("%s:%d %s without creationflags"
                                   % (fn, src[:m.start()].count("\n") + 1,
                                      m.group(0).strip()))
            for m in _re.finditer(r"os\.(?:system|popen)\s*\(", src):
                bad.append("%s:%d raw %s"
                           % (fn, src[:m.start()].count("\n") + 1,
                              m.group(0).strip()))
    return bad


import io as _io
import re as _re
import panelboss as _pb
_banned = _spawn_ban(os.path.dirname(os.path.abspath(_pb.__file__)))
assert not _banned, "console verbs outside the door: %s" % _banned
# and the updater's two spawns, one per install kind, each declared:
# the source copy's update.bat rides creationflags=0 (its console IS
# the progress UI and carries the relaunch), the frozen copy's apply.bat
# handoff rides 0x208 DETACHED|NEW_GROUP (owner live incident Oct 26:
# the bat must outlive the app it kills, and with no console it speaks
# only into the update.log receipt - no pause, no window, no funeral
# race). Both marked for the humans:
_gsrc = _io.open(os.path.join(os.path.dirname(os.path.abspath(_pb.__file__)),
                              "ui", "window", "_general.py"),
                 encoding="utf8").read()
_optouts = _re.findall(r"creationflags=0(?![xX0-9])", _gsrc)
assert len(_optouts) == 1, "exactly one console-flagged spawn (the " \
                           "source updater), found %d" % len(_optouts)
_detaches = _re.findall(r"creationflags=0x208", _gsrc)
assert len(_detaches) == 1, "exactly one detached handoff spawn (the " \
                            "msi updater), found %d" % len(_detaches)
assert "# CONSOLE: deliberate" in _gsrc, "the opt-out must name itself"
print("no-window door OK (belt pair pinned, silence proven, verbs banned,"
      " two declared console exceptions marked)")   # one per install kind

print("startup OK (command, frozen, round trip, 2 refusals, tray flip,"
      " no-window door)")
