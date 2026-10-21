"""The cleanup contract (MSI wave, Oct 21), fake-first: the CCD
disconnects are restored FIRST (the ordering is the law), the Run
key goes next, the task last - and the task delete is asked only
for OUR name. A no-op world answers honest per-item lines and the
verb exits 0 through the real dispatcher. Nothing touches the live
desk: winreg is swapped (startup imports it per call), power._run
is the seam power_task_test uses, and wm._sdc / wm.monitors are
swapped exactly like awaymode_test swaps them - module attributes,
late imports, the belt's religion."""
import logging
import os
import sys

logging.disable()             # the refusal branches log by design
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panelboss import cleanup, cli, power, startup   # noqa: E402
import panelboss.wm as wm                            # noqa: E402

timeline = []                 # WHO ACTED, in order - the ordering pin


class R:
    def __init__(self, rc):
        self.returncode = rc


class FakeKey:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeWinreg:
    """startup's whole world: one Run key, both names, and the one
    error absent-is-normal rides (FileNotFoundError IS an OSError,
    so every real code path stays the real code path)."""
    HKEY_CURRENT_USER = -2147024601
    KEY_READ = 131097
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self, values):
        self.values = dict(values)

    def OpenKey(self, root, path, access=0):
        assert path == startup.RUN_PATH, path
        return FakeKey()

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
    """The schtasks door: /Query answers the store, /Delete removes
    ONLY the task it recognises as ours (the name is pinned to
    power.TASK_NAME by the twin of config.py's cleanup seam)."""

    def __init__(self, installed):
        self.installed = installed
        self.calls = []

    def __call__(self, args, **kw):
        verb = args[1]
        name = args[3] if len(args) > 3 else ""
        self.calls.append((verb, name))
        if verb == "/Query":
            return R(0 if self.installed else 1)
        if verb == "/Delete":
            ours = self.installed and name == power.TASK_NAME
            if ours:
                self.installed = False
                timeline.append("task")
            return R(0 if ours else 1)
        return R(0)


class FakeSDC:
    def __init__(self, stored_dark):
        self.stored_dark = set(stored_dark)

    def revive(self, row):
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


CFG = {"away": {"monitors": {"AOC2790": {"offdisc": True}}}}

# 1) the full world: the ORDER is the law - CCD first (the belt dies
#    with the app), then the Run key, then our task.
spawn = install_fakes(True, {startup.VALUE_NAME: "cmd --autostart"},
                      ["AOC2790"])
lines = cleanup.run(CFG)
assert timeline == ["sdc", "runkey", "task"], timeline
assert lines[0] == "disconnected displays restored: 1", lines
assert lines[1] == "run key: removed", lines
assert lines[2] == "removed task " + power.TASK_NAME, lines
assert ("/Delete", power.TASK_NAME) in spawn.calls, spawn.calls
print("ok - full world: sdc first, run key next, our task last")

# 2) no task in the store: the honest 'no task' line, and NO delete
#    request ever leaves the process (task_installed gates it).
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
assert "dry" in lines[0] or "configured" in lines[0], lines
print("ok - dry run: reads the desk, touches none of it")

# 5) a dead CCD door never takes the other doors down with it.
timeline.clear()
install_fakes(True, {startup.VALUE_NAME: "x"}, [])


class Boom:
    def revive(self, row):
        raise OSError("the CCD door is welded")


wm._sdc = Boom()
lines = cleanup.run(CFG)
assert lines[0].startswith("ccd restore FAILED"), lines
assert "run key: removed" in lines[1], lines
assert lines[2] == "removed task " + power.TASK_NAME, lines
print("ok - dead CCD door: the Run key and the task still go")

# 6) the exit code: 0 always, through the real dispatcher (the MSI
#    contract: a no-op may not fail an uninstall).
rc = cli.main(["cleanup"])
assert rc == 0, rc
print("ok - the verb exits 0 through the real dispatcher")
