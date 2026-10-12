"""Wear guard + per-index policy, offline: a fake clock and fake
cameras. state.time gets a shim BEFORE any monitor is built (the wear
timer IS the feature); the camera layer keeps the real module with
FakeCam patched in (the multi_cam_test pattern). Covers: boot arming,
the 3600 s wear timeout, the degraded cadence gate, the edge re-arm on
a display flip, the roster cap, the preview lease (opens the off eyes
the vote walk skips, never a permanently-off one, releases ALL at
lease end), and the mosaic geometry straight out of the framebox.
SIZE LAW note: ~270 lines of one scenario chain riding a single
fake-clock/FakeCam/Det scaffold; splitting per block would clone the
scaffold eight times, costing more than the one long read it saves.
"""
import logging
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from panelboss import camera as cam_mod
from panelboss import config
from panelboss import display
from panelboss import preview_grid as pg
import panelboss.state as state_mod

sent = []
display.wake = lambda *a, **k: sent.append("wake")
display.turn_off = lambda *a, **k: sent.append("off")
display.set_hold = lambda *a, **k: None
display.foreground_is_fullscreen = lambda: False


class Clock:
    """The fake wear clock (state.py's module attribute is swapped to
    this); camera.py keeps the real time module and FakeCam needs
    none of it."""

    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t

    def perf_counter(self):
        return self.t

    def sleep(self, s):
        self.t += s


clock = Clock()
state_mod.time = clock

FAKE_OPEN = {}
instances = []


class FakeCam:
    def __init__(self, index=0, warmup=4, width=1280, height=720,
                 verbose=False):
        self.index = index
        self.warmup = warmup
        self.opened = bool(FAKE_OPEN.get(index, True))
        instances.append(self)

    def warm_up(self, frames=None):
        for _ in range(self.warmup if frames is None else frames):
            self.read(timeout=2)
        return 1

    def read(self, timeout=3):
        if not self.opened:
            return None
        return np.full((8, 8, 3), self.index + 1, np.uint8)

    def release(self):
        self.opened = False

    def is_open(self):
        return self.opened


class Det:
    """Presence evidence off the encoded pixels (the CamDetector
    pattern); the frames here are flat so one pixel is the whole
    verdict."""
    conf = 0.45

    def detect(self, frame, conf=None):
        index = int(frame[0, 0, 0]) - 1
        if PRESENCE.get(index, False):
            return [[0, 0, 8, 8]], np.array([0.9])
        return np.empty((0, 4)), np.empty((0,))


PRESENCE = {}
_real_camera = cam_mod.Camera
cam_mod.Camera = FakeCam


def fresh_monitor(cfg):
    mon = state_mod.PresenceMonitor(cfg, Det())
    mon._drain_tray = lambda: None    # the tray is not under test
    return mon


def drain_open(m):
    """Join the preview lease's background opens: the async contract
    is tick 1 spawns, tick 2 composes; a test that wants "the wall"
    after the spawn has to let the workers land first."""
    rot = m.camera
    while True:
        with rot._async_lock:            # lock-free reads can see a
            th = [j.thread for j in list(rot._inflight.values())   # popped
                  if j is not None and j.thread.is_alive()]        # pre-publish
        if not th:
            return
        th[0].join(10)


def scratch_cfg(camera_toml):
    d = tempfile.mkdtemp(prefix="panelboss_policy_")
    with open(os.path.join(d, "config.toml"), "w", encoding="utf8") as fh:
        fh.write("[camera]\n" + camera_toml)
    cfg = config.get_config(dir=d, verbose=False)
    cfg["power"]["skip_camera_when_blocked"] = False   # never consult
    cfg["power"]["assistant_task"] = False             # the real
    cfg["power"]["restore_windows"] = False            # powercfg / wm
    return cfg


try:
    # 1) boot arming and the wear timeout: an always_on eye armed at
    #    boot degrades at timeout+1, and the degraded vote opens
    #    boot-style - the handle is released again on the spot
    m = fresh_monitor(scratch_cfg('index = 2\nmode_on = "always_on"\n'
                                  'mode_off = "boot_per_poll"\n'))
    assert m.armed.get(2) == 1000.0, m.armed      # armed at boot
    assert m.effective_mode(2) == "always_on"
    clock.t = 1000.0 + 3599
    assert m.effective_mode(2) == "always_on", "still inside the hour"
    clock.t = 1000.0 + 3601
    assert m.effective_mode(2) == "boot_per_poll", "3600 + 1 degrades"
    m.state = "counting"
    p, s = m._poll()
    assert instances[-1].index == 2 and not instances[-1].opened, \
        "a degraded open is boot-style: released the moment it voted"
    assert m.last_vote.get(2) == clock.t, m.last_vote
    print("wear guard OK (armed at boot, degrades at timeout+1, "
          "votes boot-style)")

    # 2) the edge re-arm: a display flip into the always table clears
    #    the degradation like a fresh boot
    m.state = "off"
    clock.t += 100
    m._notice_screens(clock.t, 1.0)               # the real wake edge
    assert m.armed.get(2) == clock.t, m.armed
    assert m.effective_mode(2) == "always_on", "the edge cured the wear"
    print("re-arm OK (the wake edge restarts the wear clock)")

    # 3) the degraded cadence gate: a degraded eye votes only once per
    #    always_fallback_poll_sec and reads as OFF in between (the
    #    walk skips it); a NATIVE boot_per_poll eye is never gated
    clock.t += 3601
    assert m.effective_mode(2) == "boot_per_poll"
    assert m._policy(2) == "boot_per_poll", "never voted: due at once"
    m.last_vote[2] = clock.t
    assert m._policy(2) == "off", "not due yet: invisible to the walk"
    clock.t += 9
    assert m._policy(2) == "off", "9 s of a 10 s wait is 9 s short"
    clock.t += 1
    assert m._policy(2) == "boot_per_poll", "the fallback turn"
    m.state = "off"                    # the off table's global is boot
    m.last_vote[2] = clock.t
    assert m._policy(2) == "boot_per_poll", "native poll is never gated"
    m.state = "counting"
    print("cadence OK (degraded votes every fallback_poll_sec; the "
          "native boot_per_poll eye is untouched)")

    # 4) the roster cap: five indexes, four on duty, and the drop is
    #    loud in the log
    recs = []

    class Grab(logging.Handler):
        def emit(self, record):
            recs.append(record)

    h = Grab()
    config.log.addHandler(h)
    cfg5 = scratch_cfg("index = [0, 1, 2, 3, 4]\n")
    config.log.removeHandler(h)
    assert cfg5["camera"]["index"] == [0, 1, 2, 3], cfg5["camera"]["index"]
    assert any("only four" in r.getMessage() for r in recs), recs
    print("roster cap OK (first four on duty, the drop warns)")

    # 5) the preview lease vs the vote walk: an eye off for the on
    #    state never opens for a vote, the LEASE can still open it,
    #    the mosaic lands in the frame slot, and letting go of the
    #    lease lets go of every sub-cam
    cfg = scratch_cfg('index = [1, 2]\nmode_on = "boot_per_poll"\n'
                      '[camera.on]\n2 = "off"\n')
    m = fresh_monitor(cfg)
    m.state = "counting"
    instances.clear()
    for _ in range(4):
        m._poll()
    assert instances and all(c.index == 1 for c in instances), \
        "the off eye never opened for a vote"
    m.detector = Det()
    m._preview(clock.t)                  # async contract: tick 1 spawns
    drain_open(m)
    m._preview(clock.t)                  # tick 2 composes
    assert any(c.index == 2 for c in instances), \
        "the lease CAN open the eye the walk skips"
    slot = m.framebox.get()
    assert slot is not None, "the mosaic reached the frame slot"
    assert slot[0].shape[1] == 2 * (420 // 2), slot[0].shape
    assert slot[0].shape[0] == pg.HEADER_H + 420 // 2, slot[0].shape
    held = [c for c in instances if c.opened]
    assert [sorted(c.index for c in held)] == [[1, 2]], "wall keeps "
    # every leased eye open, the off one labeled rather than faked
    m._release_camera()
    assert not any(c.opened for c in instances), "lease end released ALL"
    print("lease OK (off eye votes never but previews always; mosaic "
          "shape is the roster's; release is total)")

    # 6) permanently off (off in BOTH tables) is the one eye a lease
    #    may not open either: a labeled hole, no device touched
    cfg = scratch_cfg('index = [1, 2]\nmode_on = "boot_per_poll"\n'
                      '[camera.on]\n2 = "off"\n[camera.off]\n'
                      '2 = "off"\n')
    m = fresh_monitor(cfg)
    m.state = "counting"
    instances.clear()
    m._preview(clock.t)                  # spawn tick
    drain_open(m)
    m._preview(clock.t)                  # compose tick
    assert not any(c.index == 2 for c in instances), \
        "a permanently-off eye is never opened, lease included"
    assert m.framebox.get() is not None, "the wall still composed"
    print("permanent off OK (labeled hole, unopened)")

    # 7) the compose itself, headless: sizes follow the roster and the
    #    first frame's aspect, an empty dict is no image at all, the
    #    pasted frame's pixels survive, and a placeholder paints
    from PIL import Image
    frame = Image.new("RGB", (32, 18), (200, 30, 30))
    assert pg.compose({}, {}, 100) is None
    g = pg.compose({5: frame, 6: None}, {5: "always on", 6: "closed"},
                   tile_w=100, cols=2)
    assert g.size == (200, pg.HEADER_H + round(100 * 18 / 32)), g.size
    assert g.getpixel((50, pg.HEADER_H + 25)) == (200, 30, 30)
    g3 = pg.compose({0: frame, 1: None, 2: None},
                    {0: "poll", 1: "off", 2: "degraded poll"}, 100)
    assert g3.size == (200, 2 * (pg.HEADER_H + round(100 * 18 / 32))), \
        "three tiles at two columns is a 2x2 with one empty slot"
    a = pg.compose({0: None}, {0: "closed"}, 100, 1)
    b = pg.compose({0: None}, {0: ""}, 100, 1)
    assert a.tobytes() != b.tobytes(), "the placeholder text is painted"
    print("compose OK (roster order, aspect, hole, placeholder)")

    # 8) the gate regression (finding 1): degrading FROM A HELD always
    #    phase must hand the held handle back before opening the
    #    boot-poll eye, or the LED never rests and real exclusive
    #    drivers refuse the second open - the wear guard's whole point
    cfg = scratch_cfg('index = 2\nmode_on = "always_on"\n'
                      'mode_off = "always_on"\n')
    m = fresh_monitor(cfg)
    instances.clear()
    m.state = "counting"                 # lit and always: the HOLD
    frame, _ = m._poll()                 # phase (same branch the live
    held = instances[-1]                 # desk has ridden all week)
    assert held.opened, "the always phase holds its eye open"
    clock.t += 3601                      # it wears out while held
    m.state = "counting"
    frame, _ = m._poll()                 # the degraded boot branch
    assert not held.opened, \
        "the degrade released the held handle BEFORE opening the new"
    assert len(instances) == 2, len(instances)
    assert not any(c.opened for c in instances), "no leaked handle"
    print("held-degrade OK (held handle handed back first, one live "
          "open at a time, nothing leaked)")

    print("ALL CAMERA POLICY TESTS OK")
finally:
    cam_mod.Camera = _real_camera
