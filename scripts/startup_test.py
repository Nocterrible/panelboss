"""The Run-key contract, executed IN the user's hive under a scratch
value name (self-cleaning): enable writes and proves the write by
reading back; disable is idempotent; every failure comes back as a
message, never an exception; the tray toggle flips whatever the
registry holds and the window resyncs from the same truth."""
import logging
import queue
import sys

logging.disable()             # the refusal branches log by design

sys.path.insert(0, r"F:\Projects\ICU-PresenceDetector")
from awaywatch import startup, tray

real_exe = sys.executable
real_reg = sys.modules["winreg"]
startup.VALUE_NAME = "ICU Presence Detector TEST SCRATCH"

# 1) the stored command: quoted (paths love spaces), venv pythonw,
#    run.py, absolute - the Run key has no cwd to lean on
cmd = startup.command()
assert cmd.startswith('"') and cmd.endswith('"')
assert "pythonw.exe" in cmd and "run.py" in cmd, cmd

# 2) frozen: the exe IS its own launcher, args be damned
sys.frozen = True
sys.executable = r"C:\a b\ICU-Presence-Detector.exe"
assert startup.command() == r'"C:\a b\ICU-Presence-Detector.exe"'
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

print("startup OK (command, frozen, round trip, 2 refusals, tray flip)")
