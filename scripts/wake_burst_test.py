"""Drive the wake-burst logic without cameras or displays."""
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
