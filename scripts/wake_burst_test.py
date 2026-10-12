"""Drive the wake-burst logic without cameras or displays."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
import numpy as np
from panelboss import config

cfg = config.get_config(verbose=False)
_scratch = os.path.join(os.environ.get("TEMP", "."), "panelboss_test_config.toml")
config.write_config = (                       # never scribble the live
    lambda c, path=None, _w=config.write_config: _w(c, _scratch))
cfg["power"]["assistant_task"] = False       # never consult the real
cfg["recovery"]["wake_policy"] = "re_off"     # task store in a test
cfg["recovery"]["wake_burst_count"] = 2
cfg["recovery"]["wake_burst_window_sec"] = 120
cfg["inference"]["min_hits"] = 2             # the two-hit resume below
# is the test's own shape; the LIVE config on this box says 4 and this
# test reads the live file (Oct 12: pre-cooloff suite failure, pinned)


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

print("BURST TEST OK")
