"""Drive the wake-burst logic without cameras or displays."""
import logging
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
import numpy as np
from panelboss import config

cfg = config.get_config(verbose=False)
_scratch = os.path.join(os.environ.get("TEMP", "."), "panelboss_test_config.toml")
try:
    os.remove(_scratch)     # consume fresh, never stale (Oct 12 audit:
except OSError:             # shared scratch residue is a false-red
    pass                    # class)
config.write_config = (                       # never scribble the live
    lambda c, path=None, _w=config.write_config: _w(c, _scratch))
cfg["power"]["assistant_task"] = False       # never consult the real
cfg["recovery"]["wake_policy"] = "re_off"     # task store in a test
cfg["recovery"]["wake_burst_count"] = 2
cfg["recovery"]["wake_burst_window_sec"] = 120
cfg["inference"]["min_hits"] = 2             # the two-hit resume below
# is the test's own shape; the LIVE config on this box says 4 and this
# test reads the live file (Oct 12: pre-cooloff suite failure, pinned)
cfg["inference"]["confidence"] = 0.45        # the strict floor the
# tiered-wake pins below judge against: the same live-file hazard as
# min_hits above (the owner's slider range reaches 0.95 - a ghost vote
# must not red the suite because the desk is tuned strict)


class StubDetector:
    conf = 0.45

    def detect(self, frame, conf=None):
        return np.empty((0, 4)), np.empty((0,))


from panelboss.state import PresenceMonitor

mon = PresenceMonitor(cfg, StubDetector())
notes = []
mon.notifier = notes.append

# first unexpected wake: normal re_off, no pause
mon.state = "off"
mon._notice_screens(1000.0, 1.0)
assert not mon.re_off_paused, "1st wake must not pause"
assert not notes, "1st wake must not notify"

# second inside the window: pause + notify
mon.state = "off"
mon._notice_screens(1060.0, 1.0)
assert mon.re_off_paused, "2nd wake must pause"
assert notes, "pause must notify"
assert mon.grace_until > 1060.0, "paused must hold screens lit"
print("burst pauses + notifies:", notes[0][:60], "...")

# staying paused: another wake while paused keeps the light on
notes.clear()
mon.state = "off"
mon._notice_screens(1100.0, 1.0)
assert mon.re_off_paused and not notes, "paused wake stays quiet and lit"

# a confirmed person re-arms
mon.state = "counting"
mon.hits = 0
mon._schedule_on_poll(1110.0, True, 0.8)   # hit 1
assert mon.re_off_paused
mon._schedule_on_poll(1120.0, True, 0.8)   # hit 2 == min_hits
assert not mon.re_off_paused, "person seen must resume"
assert any("resumed" in n for n in notes), "resume notifies"
print("resume-on-person OK:", notes[-1])

# manual pause via the queue: no toast (wake_times is empty)
notes.clear()
mon.events.put(("reoff", True))
mon._drain_tray()
assert mon.re_off_paused and not notes, "manual pause is quiet"

# manual resume
mon.events.put(("reoff", False))
mon._drain_tray()
assert not mon.re_off_paused

# burst window expiry: two wakes 300 s apart must NOT pause
mon.wake_times = []
mon.state = "off"
mon._notice_screens(20000.0, 1.0)
mon.state = "off"
mon._notice_screens(20300.0, 1.0)
assert not mon.re_off_paused, "stale wakes must not count"

# a policy change re-arms a paused machine
mon.state = "off"
mon._notice_screens(20400.0, 1.0)
mon.state = "off"
mon._notice_screens(20430.0, 1.0)
assert mon.re_off_paused
mon.events.put(("wake_policy", "leave_on"))
mon._drain_tray()
assert not mon.re_off_paused, "policy change must re-arm"
assert cfg["recovery"]["wake_policy"] == "leave_on"

# ---- OR/AND presence tally (owner door-cam doctrine, Oct 12) -----------
# Presence is an OR, absence an AND: the door camera must never veto
# the desk camera. A streak resets only when EVERY eye on duty has had
# its turn since the last sighting and all of them saw nobody. (The old
# code reds the headline below: hits went 1,0,1,0 and never woke.)
mon2 = PresenceMonitor(cfg, StubDetector())
mon2._indexes = lambda: [0, 1]           # two eyes on duty...
mon2._table_mode = lambda i, t: "watch"  # ...in every table
wakes = []
mon2._wake = lambda now, score: wakes.append(now)
verdicts = iter([(0, (True, 0.9)),      # door: somebody (hit 1, round ends)
                 (1, (False, 0.0)),     # desk: empty (verdict only, round {1})
                 (0, (True, 0.9))])     # door again: hit 2 == min_hits -> WAKE
def fake_poll():
    idx, verdict = next(verdicts)
    mon2._vote_index = idx               # what _note_vote does inside _poll
    return verdict
mon2._poll = fake_poll
mon2.state = "off"
mon2.hits = 0
mon2.next_poll = 0.0                     # recheck due every call
mon2._off_phase(30000.0, 10.0)
assert mon2.hits == 1 and not wakes, "door positive counts immediately"
mon2._off_phase(30010.0, 10.0)
assert mon2.hits == 1, "one empty eye must NOT veto the seen door"
mon2._off_phase(30020.0, 10.0)
assert len(wakes) == 1, "the second door sighting must wake at min_hits"
print("OR wake OK (empty desk cannot veto a seen door)")

# mirror: the full rotation comes back empty -> that IS absence; the
# streak resets and the desk stays asleep (sleep must stay possible)
mon2.hits = 1                            # one stale sighting to erase
mon2._round = None
empty = iter([(0, (False, 0.0)), (1, (False, 0.0))])
def fake_poll2():
    idx, verdict = next(empty)
    mon2._vote_index = idx
    return verdict
mon2._poll = fake_poll2
n_wakes = len(wakes)                     # the OR scenario already woke once
mon2._off_phase(30100.0, 10.0)
assert mon2.hits == 1, "half a round does not reset"
mon2._off_phase(30110.0, 10.0)
assert mon2.hits == 0 and len(wakes) == n_wakes, \
    "full empty round resets, no wake"
print("AND sleep OK (full empty round resets)")

# the dark room is OURS: the off-phase round closes ONLY on a strict-tier
# frame (the measured burn-in re-light loop: every re-engage line logged
# 'waking ... (score 0.23-0.30)' - the assist tier rubber-stamping the
# occupant the blinded eye cannot see). An assist hit still ACCRUES (the
# economy of the lit desk is untouched; the strict frame that closes the
# round rides the same streak) but alone it must not re-light the desk.
mon2.hits = 1
mon2._round = None
ghost = iter([(0, (True, 0.30)), (0, (True, 0.60))])   # 0.30 < strict 0.45
def fake_poll_ghost():
    idx, verdict = next(ghost)
    mon2._vote_index = idx               # what _note_vote does inside _poll
    return verdict
mon2._poll = fake_poll_ghost
n_wakes = len(wakes)
mon2._off_phase(30500.0, 10.0)           # assist frame: hit accrues...
assert mon2.hits == 2 and len(wakes) == n_wakes and mon2.state == "off", \
    "the assist tier closed the off-phase round - the ghost re-lit the desk"
mon2._off_phase(30510.0, 10.0)           # strict frame: the round closes
assert len(wakes) == n_wakes + 1, \
    "a strict-tier frame at min_hits must still wake (existing behavior)"
print("tiered wake OK (assist accrues but refuses while dark; "
      "strict accepts)")

# hygiene: an on-phase positive wipes stale off-phase round bookkeeping
mon2.state = "counting"
mon2._round = {1}
mon2._schedule_on_poll(31000.0, True, 0.9)
assert mon2._round is None, "round state must not cross the wake boundary"

# ---- LAW 1 (the ghost law, the 00:47 autopsy, measured 0.6 s): the
# on-phase absence clock GRADES the tier. The door eye scores
# person@0.30 on an empty scene; the ungraded reset beat the 10 s
# absence clock by 0.6 s and the screens stayed lit on nobody. The
# dark room already refuses the assist tier (Oct 22 above); the lit
# desk now refuses it the same way: a sub-floor True informs (hits
# accrue, the hold record stays), but ONLY a strict True resets the
# confirmed-absence clock or voids the re-off budget.
ghosted = []
mon5 = PresenceMonitor(cfg, StubDetector())          # cfg pins 0.45
mon5._screens_off = lambda now: ghosted.append(now)
mon5._blind_since = 30000.0                          # a running streak
mon5._schedule_on_poll(31010.0, True, 0.30)          # the ghost hits
assert mon5._blind_since is None, \
    "an assist True must still break the no-verdict streak (the two "\
    "clocks measure different silences: a verdict, any verdict, is "\
    "silence-over for the fallback; a PERSON is not)"
assert mon5.absent_since == 31010.0, \
    "the ghost did not start the absence clock"
assert mon5.last_present == 31010.0 and mon5.hits == 1, \
    "the ghost must still INFORM (hold rows, hits)"
ghost_since = mon5.absent_since
mon5.re_off_deadline = 31025.0                        # woke into a budget
mon5._schedule_on_poll(31020.0, True, 0.30)
assert mon5.absent_since == ghost_since, \
    "an assist True reset the confirmed-absence clock"
assert mon5.re_off_deadline == 31025.0, \
    "an assist True voided the re-off budget"
mon5._schedule_on_poll(31030.0, True, 0.9)            # a person speaks
assert mon5.absent_since is None and mon5.re_off_deadline == math.inf, \
    "a strict True must reset both (the counter-pin)"
print("ghost law OK (assist informs but does not reset; strict resets)")

# the false streak accumulates THROUGH a ghost: 3x False + True@0.30
# + False -> the off engages on the ORIGINAL absent_since
mon5b = PresenceMonitor(cfg, StubDetector())
ghosted2 = []
mon5b._screens_off = lambda now: ghosted2.append(now)
CONF = cfg["timers"]["absent_confirm_sec"]     # the clock's own number,
# read not assumed (the live desk runs 10; a fresh file would say 60)
mon5b._schedule_on_poll(32010.0, False, 0.0)          # clock at 32010
mon5b._schedule_on_poll(32015.0, False, 0.0)
assert mon5b.absent_since == 32010.0, mon5b.absent_since
mon5b._schedule_on_poll(32010.0 + CONF - 2, True, 0.30)   # the ghost,
# two seconds shy of the deadline it is about to fail to move
assert mon5b.absent_since == 32010.0, \
    "the ghost reset a False streak's clock"
assert ghosted2 == [], "the desk engaged before its own deadline"
mon5b._schedule_on_poll(32010.0 + CONF + 1, False, 0.0)
assert ghosted2 == [32010.0 + CONF + 1], \
    "the desk did not engage on the ORIGINAL absent_since (the ghost "\
    "bought the screens exactly what a False bought: nothing)"
print("ghost law OK (False streak accrues through the ghost; the off "\
      "lands on the original clock)")

# the hold-side survival: a ghost vote through the REAL record seam
# leaves _camera_present True - the motionless reading human's screen-
# lit row must not notice the grading (hold_test 2c owns the verdict
# record's third state; this is its ghost-side pair)
mon5c = PresenceMonitor(cfg, StubDetector())
mon5c._screens_off = lambda now: None
mon5c._note_verdict(True)                             # the tier-blind gate
mon5c._schedule_on_poll(33010.0, True, 0.30)          # assist presence
assert mon5c.camera_present is True, \
    "the graded absence arm moved the hold rows' truth"
assert mon5c.absent_since == 33010.0                  # clock still runs
print("ghost law OK (hold rows see _camera_present=True on assist hits)")

# fail-closed ABSENT (gate finding 1): a stall/dead verdict carries no
# recorded eye (no _note_vote frame); it resets at once, as the shipped
# AND did - a camera that cannot answer must never buy stale hits shelter
mon2.hits = 1
mon2._round = {0}
mon2._vote_index = None
mon2._round_tally(False)
assert mon2.hits == 0 and mon2._round is None, "index-less ABSENT resets"
print("fail-closed ABSENT OK (stalled eye shelters no streak)")

print("BURST TEST OK")
