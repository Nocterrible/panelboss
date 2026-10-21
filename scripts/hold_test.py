"""The hold policy, its migration, and the self-filter that keeps the
app from defending itself: set_hold's ES flags, the per-phase policy
tuples for BOTH switches (screen, sleep), the one-old hold_timers
key seeding them, and _parse hiding OUR [PROCESS] line even though
the flat dump (measured on this box) prints no PID - only the image
path, and of the BASE install the venv launcher re-exec'd."""
import logging
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

# 2c) THE THIRD STATE (the 'while present' wave, Oct 21): the hold
#     rides the state machine's camera verdict and nothing else (the
#     packet's ONE opinion - camera_present is the read-only door,
#     _note_verdict the single record seam). Drive _apply_hold at the
#     verdict's edges; the ES tuple is the row's whole truth.
m.paused = False
m.snooze_until = 0.0
m.state = "counting"
cfg["power"]["hold_display"] = "present"
cfg["power"]["hold_sleep"] = "on"
m._note_verdict(True)                          # (a) the eye sees a person
m._apply_hold(0.0)
assert held[-1] == (True, True), \
    "present + camera-present: the display timer was let go"
m._note_verdict(False)                         # (b) a real absent verdict
m._apply_hold(0.0)
assert held[-1] == (False, True), \
    "present + camera-absent: the display timer is still held"
m._note_verdict(None)                          # (c) dark: no verdict at all
m._apply_hold(0.0)
assert held[-1] == (False, True), \
    "present + no verdict: unknown == absent did not hand the timer over"
m.state = "off"
cfg["power"]["hold_display"] = "on"
cfg["power"]["hold_sleep"] = "present"
m._apply_hold(0.0)
assert held[-1] == (False, False), \
    "hold_sleep 'present' in the dark: a silent eye must not hold the box"
cfg["power"]["hold_sleep"] = "on"
m._apply_hold(0.0)
assert held[-1] == (False, True), "dark: the booleans still ride on/off"
print("third state OK (present holds on verdict True alone; absent and "
      "no-verdict both hand the timer to the plan, dark included)")

# 2d) the DARK-CAMERA balloon - the owner amendment included: the news
#     is UNCONDITIONAL (no row-dependence gate), fires on the
#     seen-to-dark edge (a verdict that WAS present going no-verdict),
#     once per dark episode, re-armed by a recovery to present, silent
#     per-poll and on repeat-dark-within-one-episode. The notifier
#     seam is the pystray path cli wires to tray.notify (the
#     instance-guard loser line's own balloon road). The desk below
#     has NO present row and still learns its eye went quiet.
notes = []
m.notifier = notes.append
cfg["power"]["hold_display"] = "off"
cfg["power"]["hold_sleep"] = "off"
m._note_verdict(True)                          # seen: silent, no edge yet
assert notes == [], "the balloon spoke without a dark edge"
m._note_verdict(None)                          # first dark: exactly one
assert len(notes) == 1 and "camera stopped seeing" in notes[0], notes
m._note_verdict(None)                          # per-poll dark: silent
m._note_verdict(False)                         # absent is the eye TALKING
assert len(notes) == 1, notes
m._note_verdict(None)                          # dark again, no seen between
assert len(notes) == 1, notes
m._note_verdict(True)                          # recovery re-arms...
m._note_verdict(None)                          # ...the next episode speaks
assert len(notes) == 2 and notes[0] == notes[1], notes
assert len(notes[0]) < 200, "the balloon is one line, not a paragraph"
m.notifier = None
print("dark-camera balloon OK (unconditional, one per episode, re-armed "
      "by present, silent per-poll and on repeat-dark, off/off hears it)")

# 2e) THE ROSTER SHUFFLES, THE EYE DOES NOT GO DARK (the gate MEDIUM,
#     measured with the notifier ATTACHED - the reviewer's inference
#     converted): the owner's desk runs TWO camera legs (cam0/cam2,
#     today's census), and the rotation votes ONE eye per poll. A
#     staggered boot - eye 0 present, eye 2 still opening - must flap
#     NOTHING: no present-clear, no balloon across the alternating
#     abstains (the spoken-stamp ledger the wear clock keeps is the
#     guard's only input; the test seeds it the exact way _note_vote
#     writes it). Then EVERY eye falls silent (stamps age out) - that
#     IS the dark: the edge fires, one balloon; recovery re-arms.
import time as _time
cfg["camera"]["index"] = [0, 2]               # the owner's roster shape
cfg["power"]["hold_display"] = "present"      # the row under test
cfg["power"]["hold_sleep"] = "off"
m.state = "counting"
m.paused = False
m.snooze_until = 0.0
notes2 = []
m.notifier = notes2.append
m.last_vote = {0: _time.monotonic(), 2: _time.monotonic() - 1e-9}
m._note_verdict(True)                         # eye 0 saw somebody
m._apply_hold(0.0)
held_round = held[-1]
assert held_round[0] is True, "present row did not hold on a seen eye"
for _round in range(3):                       # alternating walks: the
    m.last_vote[0] = _time.monotonic()        # seen eye keeps voting,
    m._note_verdict(True)                     # the opening eye keeps
    m._note_verdict(None)                     # abstaining
assert notes2 == [], ("the shuffling roster filed balloons", notes2)
assert m.camera_present is True, \
    "a half-spoken round's abstain cleared the presence record"
m._apply_hold(0.0)
assert held[-1] == held_round, "the hold flapped across the walk"
# now EVERY eye falls silent: the stamps age past the guard's window
m.last_vote = {0: _time.monotonic() - 1e5, 2: _time.monotonic() - 1e5}
m._note_verdict(None)
assert len(notes2) == 1 and "camera stopped seeing" in notes2[0], notes2
assert m.camera_present is None, "the wholly silent roster did not read dark"
m._note_verdict(None)                         # still one episode
assert len(notes2) == 1, notes2
m.last_vote[2] = _time.monotonic()            # eye 2 came up seeing
m._note_verdict(True)
m.last_vote = {0: _time.monotonic() - 1e5,    # and BOTH fall silent
               2: _time.monotonic() - 1e5}    # again: the episode
m._note_verdict(None)                         # re-arms, it speaks again
assert len(notes2) == 2, notes2
cfg["camera"]["index"] = 0                    # the single-eye world
m._note_verdict(True)                         # re-arm...
m._note_verdict(None)                         # the single dead desk...
assert len(notes2) == 3, \
    "the single-eye exemption moved: no roster, no guard, its balloon"
m.notifier = None
print("rotation fixture OK (staggered boot flaps nothing, half-spoken "
      "rounds file no balloon, wholly silent roster is the dark, "
      "single-eye desk keeps its exemption honest)")

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
# the tri-state boundary (Oct 21): the seeded booleans read their
# canonical words at load - hold_state's table, behavior identical
assert c["power"]["hold_display"] == "off"
assert c["power"]["hold_sleep"] == "off"
with open(mpath, "w", encoding="utf8") as fh:
    fh.write("[meta]\ndefaults = 2\n\n"     # stamped: this fixture tests
                                             # the fossil's seeding, not the
                                             # wave-B boundary (an unstamped
                                             # file would answer the reset
                                             # too, and the two laws would
                                             # argue in the middle of a test)
             "[power]\nhold_timers = false\nhold_display = true\n")
c = config.get_config(dir=mdir, verbose=False)
assert c["power"]["hold_display"] == "on", "the file's own answer wins"
assert c["power"]["hold_sleep"] == "off"
print("migration OK (legacy seeds both, file wins, fossil dropped)")

# 3b) the tri-state migration TABLE, every row of it, at the load
#     boundary (the config_norm recorder idiom: the warning must SPEAK
#     for the junk row). The owner's live boolean rows survive the
#     upgrade behavior-identical: 'on' and 'off' drive the same ES
#     tuples the booleans drove, and the file's bytes sit untouched
#     until some later ordinary save (the load never rewrites them).
_tri = os.path.join(os.environ.get("TEMP", "."), "panelboss_hold_tri")
os.makedirs(_tri, exist_ok=True)
_tpath = os.path.join(_tri, "config.toml")


class _Rec(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.msgs = []

    def emit(self, record):
        self.msgs.append(record.getMessage())


_rec = _Rec()
logging.getLogger("config").addHandler(_rec)
with open(_tpath, "w", encoding="utf8") as fh:
    fh.write("[meta]\ndefaults = 2\n\n[power]\n"
             "hold_display = true\nhold_sleep = false\n")
c = config.get_config(dir=_tri, verbose=False)
assert c["power"]["hold_display"] == "on", c["power"]      # true -> on
assert c["power"]["hold_sleep"] == "off", c["power"]       # false -> off
assert _rec.msgs == [], _rec.msgs     # valid rows speak no warnings
with open(_tpath, encoding="utf8") as fh:
    assert "hold_display = true" in fh.read(), \
        "the load rewrote the owner's file bytes"
_rec.msgs.clear()
with open(_tpath, "w", encoding="utf8") as fh:
    fh.write("[meta]\ndefaults = 2\n\n[power]\nhold_display = 'yes please'\n")
c = config.get_config(dir=_tri, verbose=False)
assert c["power"]["hold_display"] == "on", c["power"]      # junk -> on
assert any("hold_display" in w and "on" in w for w in _rec.msgs), _rec.msgs
_rec.msgs.clear()
with open(_tpath, "w", encoding="utf8") as fh:
    fh.write("[meta]\ndefaults = 2\n")
c = config.get_config(dir=_tri, verbose=False)
assert c["power"]["hold_display"] == "off", c["power"]     # absent -> stock
assert c["power"]["hold_sleep"] == "off", c["power"]
assert c["power"]["hold_display"] == "off"
# the words drive EXACTLY the tuples the booleans drove (section 2's
# ground truth): the owner's lit-desk hold cannot shift on upgrade
_tri_m = PresenceMonitor(config.get_config(dir=_tri, verbose=False),
                         detector=None)
_held = []
display.set_hold = lambda *a, **k: _held.append(a)
for value, want in (("on", (True, False)), (True, (True, False)),
                    ("off", (False, False)), (False, (False, False)),
                    ("present", (False, False))):   # no verdict yet
    _tri_m.power_cfg["hold_display"] = value
    _tri_m.state = "counting"
    _tri_m._apply_hold(0.0)
    assert _held[-1] == want, (value, _held[-1], want)
print("tri-state migration OK (absent->off, true->on, false->off, "
      "junk->on LOUD, file bytes untouched; the words drive the "
      "booleans' tuples)")

# 3c) the GRAY-OUT LAW as data (the UI grays the 'while present'
#     segment from this flag alone - gray, never hidden - and the
#     detection tab's consent key is the ONLY input): detection off,
#     or never consented (the key absent reads False at load - section
#     3b's stock rows ARE that truth), the option loses its state.
assert config.hold_present_available({"enabled": True}) is True
assert config.hold_present_available({"enabled": False}) is False
assert config.hold_present_available({}) is False
assert config.hold_present_available(None) is False
print("gray law data OK (the flag is the consent key, and the paint "
      "suite owns the segment; offline this is the whole contract)")

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
