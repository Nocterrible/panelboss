"""The hold policy and the self-filter that keeps the app from defending
itself: set_hold's ES flags, the per-phase policy tuples, and _parse
hiding OUR [PROCESS] line even though the flat dump (measured on this
box) prints no PID - only the image path, and of the BASE install the
venv launcher re-execed."""
import os
import sys

sys.path.insert(0, r"F:\Projects\ICU-PresenceDetector")
from awaywatch import config, display, power
from awaywatch.state import PresenceMonitor

# 1) set_hold's flags, captured at the syscall seam
seen = []
real_set = display.k32.SetThreadExecutionState
display.k32.SetThreadExecutionState = seen.append
try:
    display.set_hold(False, False)
    assert seen == [display.ES_CONTINUOUS], seen
    display.set_hold(True, False)
    assert seen[-1] == display.ES_CONTINUOUS | display.ES_DISPLAY_REQUIRED
    display.set_hold(True, True)
    assert seen[-1] == (display.ES_CONTINUOUS | display.ES_DISPLAY_REQUIRED
                        | display.ES_SYSTEM_REQUIRED)
    display.set_hold(False, True)
    assert seen[-1] == display.ES_CONTINUOUS | display.ES_SYSTEM_REQUIRED
finally:
    display.k32.SetThreadExecutionState = real_set
print("set_hold flags OK (four combinations, no stray bits)")

# 2) the policy, at every state the loop can live in
cfg = config.get_config(verbose=False)
_scratch = os.path.join(os.environ.get("TEMP", "."), "icu_test_config.toml")
config.write_config = (
    lambda c, path=None, _w=config.write_config: _w(c, _scratch))
cfg["power"]["assistant_task"] = False
cfg["power"]["hold_timers"] = True
held = []
display.set_hold = lambda *a, **k: held.append(a)
m = PresenceMonitor(cfg, detector=None)
m._apply_hold(0.0)                       # unknown + hold on: trust nothing
assert held[-1] == (True, True), held
m.state = "active"
m._apply_hold(0.0)
assert held[-1] == (True, True)
m.state = "off"
m._apply_hold(0.0)
assert held[-1] == (False, True), "dark: box up, screens free"
cfg["power"]["hold_timers"] = False      # legacy shape
m._apply_hold(0.0)
assert held[-1] == (False, True), "dark keeps the system hold either way"
m.state = "counting"
m._apply_hold(0.0)
assert held[-1] == (False, False), "legacy: the plan owns the lit desk"
cfg["power"]["hold_timers"] = True
m._apply_hold(0.0)
assert held[-1] == (True, True)
m.paused = True
m._apply_hold(0.0)
assert held[-1] == (False, False), "paused = exactly like not running"
m.paused = False
m.snooze_until = 10.0
m._apply_hold(5.0)
assert held[-1] == (False, False), "snooze releases the plan back"
print("policy OK (both feature modes, pause, snooze, dark)")

# 3) the self-filter, against the shapes powercfg REALLY prints
tail = sys.executable.split(":", 1)[-1].strip("\\").lower()
own = power._parse("DISPLAY:\n[PROCESS] \\Device\\HarddiskVolume8\\%s\n\n"
                   "SYSTEM:\n[PROCESS] \\Device\\HarddiskVolume8\\%s\n\n"
                   % (tail, tail))
assert own["display"] == [], own["display"]
assert own["other"] == [], own["other"]
base = getattr(sys, "base_prefix", None)
if base:                                 # the image powercfg actually sees
    btail = os.path.join(base, "pythonw.exe").split(":")[-1]
    btail = btail.strip("\\").lower()
    r = power._parse("DISPLAY:\n[PROCESS] \\Device\\Vol1\\%s\n\n" % btail)
    assert r["display"] == [], r["display"]
stranger = power._parse(
    "DISPLAY:\n[PROCESS] \\Device\\HarddiskVolume8\\Users\\v\\opera.exe"
    "\nVideo Wake Lock\n")
assert len(stranger["display"]) == 1 and "opera" in stranger["display"][0], \
    stranger["display"]
print("self-filter OK (our venv path, our base path, opera survives)")

print("ALL HOLD TESTS OK")
