"""The cleanup contract (MSI wave, Oct 21), fake-first: the CCD
disconnects are restored FIRST (the ordering is the law), the Run
key next, the task last - and only when the name is OURS. A no-op
world answers honest per-item lines and exits 0 through the real
dispatcher. All fakes: winreg swapped, power._run the
power_task_test seam, wm._sdc / wm.monitors swapped like awaymode_test."""
import logging
import os
import sys

logging.disable()             # the refusal branches log by design
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panelboss import cleanup, cli, power, startup   # noqa: E402
import panelboss.wm as wm                            # noqa: E402

timeline = []                 # WHO ACTED, in order - the ordering pin
CFG = {"away": {"monitors": {"AOC2790": {"offdisc": True}}}}


class R:
    def __init__(self, rc):
        self.returncode = rc


class FakeWinreg:
    """One Run key, both names, and the one error absent-is-normal
    rides (FileNotFoundError IS an OSError, so the real code paths
    stay the real code paths)."""
    HKEY_CURRENT_USER = -2147024601
    KEY_READ = 131097
    KEY_SET_VALUE = 2
    REG_SZ = 1

    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def __init__(self, values):
        self.values = dict(values)

    def OpenKey(self, root, path, access=0):
        assert path == startup.RUN_PATH, path
        return FakeWinreg._Key()

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], FakeWinreg.REG_SZ

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]
        timeline.append("runkey")


class FakeSpawn:
    """The schtasks door: Query answers, Delete removes ONLY our task."""
    def __init__(self, installed):
        self.installed = installed
        self.calls = []

    def __call__(self, args, **kw):
        verb, name = args[1], args[3] if len(args) > 3 else ""
        self.calls.append((verb, name))
        if verb == "/Query":
            return R(0 if self.installed else 1)
        ours = verb == "/Delete" and self.installed and \
            name == power.TASK_NAME
        if ours:
            self.installed = False
            timeline.append("task")
        return R(0 if (ours or verb != "/Delete") else 1)


class FakeSDC:
    def __init__(self, stored_dark, boom=False):
        self.stored_dark = set(stored_dark)
        self.boom = boom
    def revive(self, row):
        if self.boom:
            raise OSError("the CCD door is welded")
        timeline.append("sdc")
        if row["short"] in self.stored_dark:
            self.stored_dark.discard(row["short"])
            return True, "sent (fake)"
        return None                       # lit: the belt's silence


def install_fakes(installed, values, stored_dark):
    sys.modules["winreg"] = FakeWinreg(values)
    spawn = FakeSpawn(installed)
    power._run, power._elevate_ps, power._poll = spawn, lambda *a, **k: False, \
        lambda *a, **k: True
    wm._sdc = FakeSDC(stored_dark)
    wm.monitors = lambda: [{"short": "AOC2790", "gdi": "DISPLAY1",
                            "virtual": False}]
    return spawn


# 1) full world: the ORDER is the law - CCD first (the belt dies with
#    the app), Run key, task.
spawn = install_fakes(True, {startup.VALUE_NAME: "cmd --autostart"}, ["AOC2790"])
lines = cleanup.run(CFG)
assert timeline == ["sdc", "runkey", "task"], timeline
assert lines[0] == "disconnected displays restored: 1", lines
assert lines[1] == "run key: removed", lines
assert lines[2] == "removed task " + power.TASK_NAME, lines
assert ("/Delete", power.TASK_NAME) in spawn.calls, spawn.calls
print("ok - full world: sdc first, run key next, our task last")
# 2) no task: honest 'no task', and no delete ever leaves the process.
timeline.clear()
spawn = install_fakes(False, {}, [])
lines = cleanup.run({})
assert lines[1] == "run key: already absent", lines
assert lines[2] == "no task", lines
assert not any(v == "/Delete" for v, _n in spawn.calls), spawn.calls
assert timeline == [], timeline
print("ok - no task: 'no task', and the store was never asked to die")
# 3) a legacy-only entry still gets its tombstone removed.
timeline.clear()
install_fakes(False, {startup.LEGACY_VALUE_NAME: "old --autostart"}, [])
lines = cleanup.run({})
assert lines[1] == "run key: removed", lines
assert timeline == ["runkey"], timeline
print("ok - legacy name: disable sweeps both names, one honest line")
# 4) dry run on the same busy world: every truth read, zero writes.
timeline.clear()
spawn = install_fakes(True, {startup.VALUE_NAME: "x"}, ["AOC2790"])
lines = cleanup.run(CFG, dry=True)
assert not timeline, timeline
assert spawn.installed and ("would remove" in lines[1]), lines
assert "configured" in lines[0], lines
print("ok - dry run: reads the desk, touches none of it")
# 5) a dead CCD door never takes the other doors down with it.
timeline.clear()
install_fakes(True, {startup.VALUE_NAME: "x"}, [])
wm._sdc = FakeSDC([], boom=True)
lines = cleanup.run(CFG)
assert lines[0].startswith("ccd restore FAILED"), lines
assert "run key: removed" in lines[1], lines
assert lines[2] == "removed task " + power.TASK_NAME, lines
print("ok - dead CCD door: the Run key and the task still go")
# 6) exit 0 always, through the real dispatcher (the MSI contract:
#    a no-op may not fail an uninstall).
assert cli.main(["cleanup"]) == 0
print("ok - the verb exits 0 through the real dispatcher")
