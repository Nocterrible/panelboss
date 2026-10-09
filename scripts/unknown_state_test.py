"""The boot-in-the-dark scenarios, no cameras or displays:
1) fresh input with unknown screens -> harmless power-on, becomes
   active (this was the stuck case: restart while monitors were dark)
2) idle + unknown + somebody visible -> power-on anyway
3) idle + unknown + nobody -> absent countdown ends in a normal off
4) external dark (0.0 broadcast) while counting -> adopted off, camera
   wakes on presence
5) our own OFF echo (0.0 while already off) -> no re-adoption churn
"""
import os
import sys
import types

sys.path.insert(0, r"F:\Projects\ICU-PresenceDetector")
from awaywatch import config, display
from awaywatch.state import PresenceMonitor

cfg = config.get_config(verbose=False)
# state.flushes the WHOLE cfg on some paths - redirect every write to
# scratch, or these tests flip the live assistant flag off again
# (measured: they did, minutes before "the setting does not persist")
_scratch = os.path.join(os.environ.get("TEMP", "."), "icu_test_config.toml")
config.write_config = (
    lambda c, path=None, _w=config.write_config: _w(c, _scratch))
# pin the assistant OFF for these scenarios: the live config now
# honestly says true, and then every _on_phase would consult the REAL
# task store - state would correctly wait for whatever apps hold the
# real display right now, and the asserts would be testing the desk,
# not the code
cfg["power"]["assistant_task"] = False
sent = []
display.wake = lambda *a, **k: sent.append("wake")
display.turn_off = lambda *a, **k: sent.append("off")
display.set_hold = lambda *a, **k: None
display.foreground_is_fullscreen = lambda: False

m = PresenceMonitor(cfg, detector=None)
m._release_camera = lambda: None
m._hold_camera = lambda: None
m._drain_tray = lambda: None
m._grab = lambda: None

# 1) typing after a boot that could not know the screen state
assert m.state == "unknown", m.state
m._poll = lambda: (True, 0.9)
m._on_phase(100.0, idle=0.2)
assert m.state == "active" and sent == ["wake"], (m.state, sent)
print("boot-into-typing OK: power-on sent, state active")

# 2) idle at a dark-but-unproven desk, camera sees a person
sent.clear()
m2 = PresenceMonitor(cfg, detector=None)
m2._release_camera = lambda: None
m2._drain_tray = lambda: None
m2._poll = lambda: (True, 0.9)
m2._on_phase(100.0, idle=90.0)              # unknown -> counting -> poll
assert m2.state == "active" and sent == ["wake"], (m2.state, sent)
print("boot-dark-person OK: power-on sent on the first present frame")

# 3) idle + nobody: the unknown resolves through the normal off path
sent.clear()
m3 = PresenceMonitor(cfg, detector=None)
m3._release_camera = lambda: None
m3._hold_camera = lambda: None
m3._drain_tray = lambda: None
m3._poll = lambda: (False, 0.1)
m3._on_phase(100.0, idle=90.0)
for t in range(101, 160):
    m3._on_phase(float(t), idle=90.0)
assert m3.state == "off" and sent[-1] == "off", (m3.state, sent)
print("boot-dark-nobody OK: absence ends in a normal off (%s)" % sent)

# 4) external dark while counting -> adopted; presence wakes
m4 = PresenceMonitor(cfg, detector=None)
m4._release_camera = lambda: None
m4._hold_camera = lambda: None
m4._drain_tray = lambda: None
m4._poll = lambda: (True, 0.9)
m4._notice_screens(200.0, 0.0)
assert m4.state == "off", m4.state
m4.next_poll = 200.0                        # pretend the off-cadence
                                             # deadline came due already
sent.clear()
m4._off_phase(210.0, idle=30.0)
for _ in range(cfg["inference"]["min_hits"] + 1):
    m4._off_phase(211.0 + _, idle=30.0)
assert m4.state == "counting" and sent == ["wake"], (m4.state, sent)
print("external-dark adopted OK: camera woke it for a person")

# 5) our own off echo does not re-adopt or double-hold
m5 = PresenceMonitor(cfg, detector=None)
m5._release_camera = lambda: None
m5._hold_camera = lambda: None
m5.state = "off"
hold_calls = []
m5._hold_camera = lambda: hold_calls.append(1)
m5._notice_screens(300.0, 0.0)
assert m5.state == "off" and hold_calls == []
print("off-echo ignored OK")

print("ALL UNKNOWN-STATE TESTS OK")
