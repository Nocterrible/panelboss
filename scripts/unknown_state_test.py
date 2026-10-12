"""The boot-in-the-dark scenarios, no cameras or displays:
1) fresh input with unknown screens -> harmless power-on, becomes
   active (this was the stuck case: restart while monitors were dark)
2) idle + unknown + somebody visible -> power-on anyway
3) idle + unknown + nobody -> absent countdown ends in a normal off
4) external dark (0.0 broadcast) while counting -> adopted off, camera
   wakes on presence - driven through the CURRENT vote seam (Oct 12):
   a patched cam_mod.Camera, the real _poll, background opens joined
   between ticks (the blackvote/asyncopen house fixture pattern),
   because an unregistered eye never earns round credit
5) our own OFF echo (0.0 while already off) -> no re-adoption churn
"""
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

from panelboss import camera as cam_mod
from panelboss import config, display
from panelboss.state import PresenceMonitor

_real_camera = cam_mod.Camera


class _FakeCam:
    """An eye that sees somebody: a bright frame (asyncopen's GRAY=128
    proves 128 clears BLACK_CEIL) and NO driver sleep - the doctrine
    below needs votes now; the open's asynchrony is what drain_vote
    joins."""

    def __init__(self, index=0, warmup=4, width=1280, height=720, **kw):
        self.index = index

    def warm_up(self, frames=None):
        return 1

    def read(self, timeout=3, screen=None):
        return np.full((8, 8, 3), 128, np.uint8)

    def release(self):
        pass

    def is_open(self):
        return True


class _Somebody:
    def detect(self, frame):
        return [[0, 0, 8, 8]], np.array([0.9])


def drain_vote(m):
    """Join the background opens the VOTE path spawned (blackvote's
    seam): tick 1 spawns and abstains, tick 2 votes."""
    for op in (getattr(m, "_single_opener", None),
               getattr(getattr(m, "camera", None), "_opener", None)):
        if op is None:
            continue
        while True:
            with op.lock:
                th = [j.thread for j in list(op.inflight.values())
                      if j is not None and j.thread.is_alive()]
            if not th:
                break
            th[0].join(10)


def scratch_cfg(camera_toml):
    d = tempfile.mkdtemp(prefix="panelboss_unknown_")
    with open(os.path.join(d, "config.toml"), "w", encoding="utf8") as fh:
        fh.write("[camera]\n" + camera_toml)
    cfg = config.get_config(dir=d, verbose=False)
    cfg["power"]["skip_camera_when_blocked"] = False   # never consult
    cfg["power"]["assistant_task"] = False             # the real
    cfg["power"]["restore_windows"] = False            # powercfg / wm
    return cfg

cfg = config.get_config(verbose=False)
# state.flushes the WHOLE cfg on some paths - redirect every write to
# scratch, or these tests flip the live assistant flag off again
# (measured: they did, minutes before "the setting does not persist")
_scratch = os.path.join(os.environ.get("TEMP", "."), "panelboss_test_config.toml")
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

# 4) external dark while counting -> adopted; presence wakes. The
# vote rides the real seam: fbfe9d1 made the open async and f8c7bd8
# made _off_phase consume votes through _round_tally, where a present
# vote from an eye that never registered itself (_note_vote's
# _vote_index) earns no round credit - the old instance-level
# `m4._poll = lambda: (True, 0.9)` bypassed that registration (and the
# round doctrine says an unregistered vote must not count), so the
# fake, not the wake, was stale.
cam_mod.Camera = _FakeCam
m4 = PresenceMonitor(scratch_cfg('index = 1\nmode_on = "boot_per_poll"\n'
                                 'mode_off = "boot_per_poll"\n'),
                     _Somebody())              # the REAL _poll votes here
m4._release_camera = lambda: None
m4._hold_camera = lambda: None
m4._drain_tray = lambda: None
m4._notice_screens(200.0, 0.0)
assert m4.state == "off", m4.state
m4.next_poll = 200.0                        # pretend the off-cadence
                                             # deadline came due already
sent.clear()
t = 210.0
for _ in range(4 * m4.cfg["inference"]["min_hits"] + 4):
    m4._off_phase(t, idle=30.0)             # opening eye: abstain
    drain_vote(m4)                          # the background open lands
    if m4.state != "off":
        break                               # the adopted desk woke
    t += 1.0
assert m4.state == "counting" and sent == ["wake"], (m4.state, sent)
cam_mod.Camera = _real_camera
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
