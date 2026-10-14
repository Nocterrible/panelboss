"""The hold policy, its migration, and the self-filter that keeps the
app from defending itself: set_hold's ES flags, the per-phase policy
tuples for BOTH switches (screen, sleep), the one-old hold_timers
key seeding them, and _parse hiding OUR [PROCESS] line even though
the flat dump (measured on this box) prints no PID - only the image
path, and of the BASE install the venv launcher re-exec'd."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panelboss import config, display, power
from panelboss.state import PresenceMonitor

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

# 2) the policy, at every state the loop can live in, for each switch
cfg = config.get_config(verbose=False)
_scratch = os.path.join(os.environ.get("TEMP", "."), "panelboss_test_config.toml")
try:
    os.remove(_scratch)     # consume fresh, never stale: this shared
except OSError:             # scratch is the false-red class (Oct 12
    pass                    # audit) - gaming_ui and profiles_ui already
                            # delete at setup; every consumer must
config.write_config = (
    lambda c, path=None, _w=config.write_config: _w(c, _scratch))
cfg["power"]["assistant_task"] = False
cfg["power"]["hold_display"] = True
cfg["power"]["hold_sleep"] = True
held = []
display.set_hold = lambda *a, **k: held.append(a)
m = PresenceMonitor(cfg, detector=None)
m._apply_hold(0.0)                       # unknown + both on: trust nothing
assert held[-1] == (True, True), held
m.state = "off"
m._apply_hold(0.0)
assert held[-1] == (False, True), "dark: box up, screens given away"
cfg["power"]["hold_display"] = False
cfg["power"]["hold_sleep"] = False      # the user wants normal behavior
m._apply_hold(0.0)
assert held[-1] == (False, False), "dark without hold_sleep: sleep wins"
m.state = "counting"
m._apply_hold(0.0)
assert held[-1] == (False, False), "the lit desk belongs to the plan"
cfg["power"]["hold_display"] = True     # the classic combo: no screen
m._apply_hold(0.0)                       # timeout, sleep still scheduled
assert held[-1] == (True, False), held
m.paused = True
m._apply_hold(0.0)
assert held[-1] == (False, False), "paused = exactly like not running"
m.paused = False
m.snooze_until = 10.0
m._apply_hold(5.0)
assert held[-1] == (False, False), "snooze releases the plan again"
print("policy OK (each switch alone, together, pause, snooze, dark)")

# 2b) the pause gate RELEASE re-arms the phase machine (audit HIGH:
#     without it math.inf outlives the gate and the camera never polls
#     again - a lit desk stays lit all night, a dark desk only wakes on
#     physical input). Drive the same m._tick() as the run loop: state
#     "off" + idle 90.0 keeps the on-phase's own "typing won" branch
#     (next_poll = math.inf while idle) out of the picture, so the only
#     finite next_poll after the unpause tick is the gate's re-arm.
m.state = "off"
m.paused = True
m._tick()
assert m.next_poll == math.inf, "the pause gate must hold the camera"
m.paused = False
m._tick()
assert m.next_poll != math.inf, \
    "the unpause left next_poll stuck at math.inf - no re-arm, no polls"
print("gate re-arm OK (pause sets inf, unpause re-arms the phase clock)")

# and the released eye carries no verdict debt (DELTA 2): a credit
# armed before the release must die with the eye, not be consumed as
# an ABSENT by a later fail-closed tick
m._vote_index = 0
m._round = {0}
m._release_camera()
assert m._vote_index is None, "a released eye kept its in-flight credit"
assert m._round is None, "a released eye kept a half-collected AND round"
print("release clear OK (released eye: no vote credit, no round debt)")

# 3) migration: one old hold_timers answer seeds both new keys, keys
#    the file sets itself always win, and the fossil never survives a
#    rewrite (the writer persists whatever the dict holds)
mdir = os.path.join(os.environ.get("TEMP", "."), "panelboss_hold_cfg")
os.makedirs(mdir, exist_ok=True)
mpath = os.path.join(mdir, "config.toml")
with open(mpath, "w", encoding="utf8") as fh:
    fh.write("[meta]\ndefaults = 2\n\n[power]\nhold_timers = false\n")
c = config.get_config(dir=mdir, verbose=False)
assert "hold_timers" not in c["power"], c["power"]
assert c["power"]["hold_display"] is False
assert c["power"]["hold_sleep"] is False
with open(mpath, "w", encoding="utf8") as fh:
    fh.write("[meta]\ndefaults = 2\n\n"     # stamped: this fixture tests
                                             # the fossil's seeding, not the
                                             # wave-B boundary (an unstamped
                                             # file would answer the reset
                                             # too, and the two laws would
                                             # argue in the middle of a test)
             "[power]\nhold_timers = false\nhold_display = true\n")
c = config.get_config(dir=mdir, verbose=False)
assert c["power"]["hold_display"] is True, "the file's own answer wins"
assert c["power"]["hold_sleep"] is False
print("migration OK (legacy seeds both, file wins, fossil dropped)")

# 4) the self-filter, against the shapes powercfg REALLY prints
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
