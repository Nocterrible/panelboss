"""Async-open probe for RotatingCamera + the progressive preview mosaic.

Fake camera layer only: cam_mod.Camera is swapped for a fake that SLEEPS
1.0 s in its constructor (the slow-driver tax) and hands out solid-gray
frames. Proves: (1) one open thread per index; (2) the mosaic tick that
launches opens returns in milliseconds and puts nothing until a real
frame exists, then composes gray tiles once the opens land; (3) release
mid-flight makes the worker release its own fresh handle (no orphan LED)
and cameras[index] stays None; (4) an open in flight PINS the preview
lease (one renewal, and no pin once the inflight set is empty); (5) a
grace deadline (absolute-arg and monkeypatched-const forms) makes the
worker abandon and self-release, leaving cameras[index] None; (6) that
drop stales its own eye ONLY - a sibling mid-open still publishes;
(7) the lease COOLOFF: a natural lease end keeps the wall warm, an
in-flight open completes and publishes anyway, a re-begin inside the
window ATTACHES with zero respawns (the owner's reopen spiral), and the
cool expiry releases with the gen bump; (8) the single-camera desk is
async too: the leased tick returns in milliseconds against a 1 s fake
open, the worker publishes through the opener, and the same cooloff +
attach contract covers it.
(1)-(6) exercise the rotor; (7)-(8) drive real monitors through _tick.)
"""
import logging
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

from panelboss import camera as cam_mod

logging.basicConfig(level=logging.INFO,
                    format="probe| %(levelname)s %(name)s: %(message)s")


class Grab(logging.Handler):
    msgs = []

    def emit(self, record):
        Grab.msgs.append(record.getMessage())


for _name in ("camera", "state"):
    logging.getLogger(_name).addHandler(Grab())


def saw(sub):
    return any(sub in m for m in Grab.msgs)


SLEEP = 1.0
GRAY = np.full((180, 320, 3), 128, np.uint8)


class FakeCam:
    instances = []
    builds = 0
    sleeps = {}                        # index -> seconds; overrides SLEEP

    def __init__(self, index, warmup=4, width=1280, height=720, **kw):
        FakeCam.builds += 1
        self.index = index
        self.opened = False
        self.released = False
        time.sleep(self.sleeps.get(index, SLEEP))   # the driver's tax
        self.opened = True
        FakeCam.instances.append(self)

    def warm_up(self, frames=None):
        return self.warmup_frames if hasattr(self, "warmup_frames") else 1

    def read(self, timeout=3, screen=None):
        # screen kwarg (Oct 12): the real Camera.read grew black-frame
        # screening and the preview seam passes screen=0; this fake
        # accepts and ignores it (no screening under test here)
        return GRAY.copy()

    def release(self):
        self.released = True
        self.opened = False

    def is_open(self):
        return self.opened


cam_mod.Camera = FakeCam               # _open builds through this name


class FakeDetector:
    def detect(self, frame):
        return [], np.empty(0)


class Shim:
    """Everything _preview_mosaic touches on the monitor."""
    state = "on"
    cfg = {"ui": {"preview_width": 420}}

    def __init__(self):
        from panelboss.state._preview import _PreviewMixin, FrameBox
        self._preview_mosaic = _PreviewMixin._preview_mosaic.__get__(self)
        self._pin_lease = _PreviewMixin._pin_lease.__get__(self)
        self.detector = FakeDetector()
        self.framebox = FrameBox()
        self.preview_until = 0.0       # the lease end the pin pushes out
        self._pin_logged = False       # the once-per-lease confession

    def _table_mode(self, index, table):
        return "always_on"

    def effective_mode(self, index):
        return "always_on"


def wait_inflight(rot, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        th = [j.thread for j in list(rot._inflight.values())
              if j is not None]
        if not any(t.is_alive() for t in th):
            return
        time.sleep(0.02)
    raise AssertionError("inflight opens never finished")


# ---- 1. one thread per index -------------------------------------------
rot = cam_mod.RotatingCamera([2])
assert rot.open_async(2) is None
th1 = rot._inflight.get(2).thread
assert th1 is not None and th1.is_alive()
assert rot.open_async(2) is None        # mid-flight: no second worker
assert rot._inflight.get(2).thread is th1
wait_inflight(rot)
assert FakeCam.builds == 1, "second open_async built a second open"
cam = rot.cameras.get(2)
assert cam is not None and cam.is_open()
assert rot.open_async(2) is cam         # live handle returned directly
assert saw("camera 2 open published after"), "publish logged no line"
print("PROBE 1 OK  one worker per index, live handle returned")

# ---- 2. tick latency + progressive fill ---------------------------------
rot2 = cam_mod.RotatingCamera([0, 3])
shim = Shim()
t0 = time.perf_counter()
shim._preview_mosaic(rot2)
first_ms = (time.perf_counter() - t0) * 1000
assert first_ms < 100, "first tick blocked: %.0f ms" % first_ms
slot = shim.framebox.get()
assert slot is not None, "all-opening tick must STILL compose: a stale " \
    "frame may not read as live (gate finding)"
assert slot[0].shape[1] == 2 * 210, slot[0].shape   # 2 tiles, w=420//2
time.sleep(0.2)
t0 = time.perf_counter()
shim._preview_mosaic(rot2)
second_ms = (time.perf_counter() - t0) * 1000
assert second_ms < 100, "second tick blocked: %.0f ms" % second_ms
assert shim.framebox.get() is not None    # wall of holes, honestly
wait_inflight(rot2)
shim._preview_mosaic(rot2)
out = shim.framebox.get()
assert out is not None, "no mosaic after the opens landed"
bgr = out[0]
assert (bgr == 128).sum() > bgr.shape[0] * bgr.shape[1] * 0.25, \
    "gray tiles missing from the composed wall"
print("PROBE 2 OK  first tick %.0f ms (<100), gray wall after joins"
      % first_ms)

# ---- 3. lease release while an open is mid-flight ------------------------
rot3 = cam_mod.RotatingCamera([5])
rot3.open_async(5)
time.sleep(0.3)                         # still inside the 1.0 s open
th = rot3._inflight.get(5).thread
assert th is not None and th.is_alive()
rot3.release()                          # the lease ends right here
th.join(5)
assert rot3.cameras.get(5) is None
cams5 = [c for c in FakeCam.instances if c.index == 5]
assert cams5 and all(c.released for c in cams5), \
    "the mid-flight open leaked its handle"
print("PROBE 3 OK  mid-flight release self-released %d orphan handle(s)"
      % len(cams5))

# ---- 4. an open in flight pins the lease ----------------------------------
rot4 = cam_mod.RotatingCamera([11])
shim2 = Shim()
shim2._preview_mosaic(rot4)             # launches the 1.0 s fake open
assert shim2.preview_until >= time.monotonic() + 0.9, \
    "the in-flight open did not pin the lease"
assert saw("preview lease pinned by an open in flight")
n_pin = sum(1 for m in Grab.msgs if "pinned by an open" in m)
wait_inflight(rot4)
before = shim2.preview_until
shim2._preview_mosaic(rot4)             # inflight empty: no further pin
assert shim2.preview_until == before, "pinned the lease with nothing live"
assert sum(1 for m in Grab.msgs if "pinned by an open" in m) == n_pin, \
    "the pin confession ran twice on one lease"
print("PROBE 4 OK  in-flight open pins the lease; a landed open does not")

# ---- 5. the grace deadline abandons an open (arg + const forms) ----------
rot5 = cam_mod.RotatingCamera([12])
rot5.open_async(12, deadline=time.monotonic() + 0.2)   # absolute override
th = rot5._inflight.get(12).thread
time.sleep(0.4)                         # deadline passed, open still asleep
assert rot5.inflight_live(time.monotonic()) is False, "zombie still counts"
assert 12 not in rot5._inflight, "the grace deadline never dropped the row"
assert saw("camera 12 open exceeded 0.2 s grace; dropping"), \
    "the drop confession misreported its own window (finding 2)"
assert rot5.open_async(12) is None and 12 not in rot5._inflight, \
    "a grace-dropped eye respawned - the re-pin loop (finding 1)"
th.join(5)
assert rot5.cameras.get(12) is None, "an abandoned open published anyway"
cams12 = [c for c in FakeCam.instances if c.index == 12]
assert cams12 and all(c.released for c in cams12), \
    "the deadline drop leaked its handle"
assert saw("camera 12 open went stale; released its own handle")
rot5.release()                            # lease end: amnesty, new chance
rot5.open_async(12)
assert rot5._inflight.get(12) is not None, \
    "release did not clear the tombstone"
rot5.release()
cam_mod.OPEN_GRACE_SEC = 0.2            # the const form must behave alike
rot5b = cam_mod.RotatingCamera([13])
rot5b.open_async(13)
th = rot5b._inflight.get(13).thread
time.sleep(0.4)
assert rot5b.inflight_live(time.monotonic()) is False
th.join(5)
assert rot5b.cameras.get(13) is None
cams13 = [c for c in FakeCam.instances if c.index == 13]
assert cams13 and all(c.released for c in cams13), \
    "the const-form deadline leaked its handle"
cam_mod.OPEN_GRACE_SEC = 90
print("PROBE 5 OK  grace-deadline open self-released (arg and const forms)")

# ---- 6. one eye's drop must not stale its sibling -------------------------
FakeCam.sleeps = {7: 1.0, 8: 0.6}
rot6 = cam_mod.RotatingCamera([7, 8])
rot6.open_async(7, deadline=time.monotonic() + 0.2)   # doomed eye
rot6.open_async(8)                                    # default 90 s grace
th7 = rot6._inflight.get(7).thread
time.sleep(0.3)                          # 7 past grace, 8 still mid-open
assert rot6.inflight_live(time.monotonic()) is True, \
    "the doomed eye killed the pin its sibling still needed"
assert 7 not in rot6._inflight and 8 in rot6._inflight, \
    "the grace drop took the sibling's row with it"
th7.join(5)
wait_inflight(rot6)
cam8 = rot6.cameras.get(8)
assert cam8 is not None and cam8.is_open(), \
    "sibling failed to publish after the other eye's drop"
assert saw("camera 8 open published after"), "sibling publish logged nothing"
cams7 = [c for c in FakeCam.instances if c.index == 7]
assert cams7 and all(c.released for c in cams7), \
    "the dropped eye leaked its handle past the drop"
print("PROBE 6 OK  grace drop staled its own eye, the sibling published")

# ======================= monitor level: cooloff + single async ==========
# (the camera_policy fixture pattern: stub the display verbs, scratch
# config, fake cameras already patched in; _tick is driven BY HAND)
import panelboss.state._boot as state_boot
from panelboss import config, display
from panelboss.state import PresenceMonitor

display.wake = lambda *a, **k: None
display.turn_off = lambda *a, **k: None
display.set_hold = lambda *a, **k: None
display.foreground_is_fullscreen = lambda: False


def scratch_cfg(camera_toml):
    d = tempfile.mkdtemp(prefix="panelboss_async_")
    with open(os.path.join(d, "config.toml"), "w", encoding="utf8") as fh:
        fh.write("[camera]\n" + camera_toml)
    cfg = config.get_config(dir=d, verbose=False)
    cfg["power"]["skip_camera_when_blocked"] = False   # never consult
    cfg["power"]["assistant_task"] = False             # the real
    cfg["power"]["restore_windows"] = False            # powercfg / wm
    return cfg


def fresh_monitor(camera_toml):
    mon = PresenceMonitor(scratch_cfg(camera_toml), FakeDetector())
    mon.state = "counting"
    mon._poll = lambda: (None, 0.0)   # the phase machine is not under
                                      # test; only the lease path is
    return mon


# ---- 7. the cooloff: a natural lease end keeps the warm wall -----------
FakeCam.builds = 0
FakeCam.instances = []
FakeCam.sleeps = {4: 1.0}
mon7 = fresh_monitor('index = [4, 9]\nmode_on = "always_on"\n'
                     'mode_off = "always_on"\n'
                     '[camera.on]\n9 = "off"\n[camera.off]\n9 = "off"\n')
mon7.events.put(("preview", 10.0))
_t = time.perf_counter()
mon7._tick()
assert (time.perf_counter() - _t) * 1000 < 100, "spawn tick blocked"
b0 = FakeCam.builds
assert b0 == 1, "expected exactly the one slow eye spawned, got %d" % b0
time.sleep(0.25)                          # still INSIDE the 1.0 s open
mon7.events.put(("preview", 0))           # the lease dies (cancel lands
mon7._tick()                              # on the natural-expiry arm)
rot7 = mon7.camera
assert rot7 is not None and mon7.preview_cool > time.monotonic(), \
    "the natural lease end released instead of going warm"
wait_inflight(rot7, timeout=8)            # THE POINT: the slow open's
c4 = rot7.cameras.get(4)                  # driver work COMPLETES and
assert c4 is not None and c4.is_open(), "the warm window lost the open"
assert not c4.released, "a lease end released an in-flight handle again"
mon7.events.put(("preview", 10.0))        # re-toggle inside the window
_t = time.perf_counter()
mon7._tick()
assert (time.perf_counter() - _t) * 1000 < 100, "the attach tick blocked"
assert FakeCam.builds == b0, "ATTACH SPAWNED A REOPEN - the spiral lives"
assert saw("preview lease re-attached a warm wall - no reopen")
assert mon7.framebox.get() is not None, "the warm wall did not compose NOW"
state_boot.PREVIEW_COOLOFF_SEC = 0.3      # one dial; the probe turns it
gen7 = rot7._gen
mon7.events.put(("preview", 0))
mon7._tick()                              # warm once more...
time.sleep(0.35)
mon7._tick()                              # ...and the window closes
assert mon7.camera is None and c4.released, "the cooloff outstayed its end"
assert rot7._gen == gen7 + 1, "the cool expiry skipped the gen bump"
mon7.events.put(("preview", 10.0))        # a begin AFTER the window:
mon7._tick()                              # fresh rotor, fresh spawn
assert FakeCam.builds == b0 + 1 and mon7.camera is not rot7, \
    "no fresh open after the cool window closed"
state_boot.PREVIEW_COOLOFF_SEC = 5.0
print("PROBE 7 OK  cooloff kept the in-flight open; ATTACH AT builds==%d, "
      "ZERO RESPAWNS - the owner's spiral is dead" % b0)

# ---- 8. the single-camera desk is async too ----------------------------
FakeCam.builds = 0
FakeCam.instances = []
mon8 = fresh_monitor('index = 4\nmode_on = "always_on"\n'
                     'mode_off = "always_on"\n')
b8 = FakeCam.builds
mon8.events.put(("preview", 0.3))         # a lease SHORTER than the open
_t = time.perf_counter()
d8 = mon8._tick()
first8 = (time.perf_counter() - _t) * 1000
assert first8 < 100, "the single-camera open blocked the tick: %.0f ms" % first8
assert d8 <= 0.2, "the lease returned a delay over its own cadence"
assert mon8.camera is None and mon8._single_opener is not None
assert saw("camera 4 opening in background")
assert saw("preview lease began; polling now")
assert saw("preview lease pinned by an open in flight")
assert mon8.preview_until >= time.monotonic() + 0.9, \
    "the in-flight single open did not pin the lease"
time.sleep(0.6)
mon8._tick()                              # still opening, pinned again
time.sleep(0.6)                           # (~1.0 s) the worker lands
mon8._tick()
assert FakeCam.builds == b8 + 1
cam8 = mon8.camera
assert cam8 is not None and cam8.is_open(), "the published eye never surfaced"
slot8 = mon8.framebox.get()
assert slot8 is not None and slot8[0].shape == GRAY.shape, \
    "no frame in the box after the publish"
assert saw("camera 4 open published after")
mon8.events.put(("preview", 0))           # the single desk gets the
mon8._tick()                              # SAME cooloff...
assert mon8.preview_cool > time.monotonic() and not cam8.released, \
    "a single-eye lease end released instead of warming"
mon8.events.put(("preview", 5.0))         # ...and the same attach
mon8._tick()
assert FakeCam.builds == b8 + 1, "the single-camera attach reopened"
assert saw("preview lease re-attached a warm wall - no reopen")
state_boot.PREVIEW_COOLOFF_SEC = 0.3
mon8.events.put(("preview", 0))
mon8._tick()
time.sleep(0.35)
gen8 = mon8._single_opener.gen
mon8._tick()
assert cam8.released and mon8.camera is None, "the single cooloff never ended"
assert mon8._single_opener.gen == gen8 + 1, "no gen bump through the seam"
mon8.events.put(("preview", 5.0))         # after the window: fresh open
mon8._tick()
assert FakeCam.builds == b8 + 2, "the post-window begin did not respawn"
state_boot.PREVIEW_COOLOFF_SEC = 5.0
print("PROBE 8 OK  single-camera leased tick %.0f ms against a 1.0 s open;"
      " publish, cooloff, attach, respawn all honest" % first8)

# ---- 9. the VOTE path is async too: abstain, adopt, blink, re-open ----
# (Oct 12: the owner's "20 s to open" complaint was _grab opening the
# boot_per_poll eye ON the tick thread; the vote now rides the SAME
# AsyncOpener the leases use. FakeCam sleeps 1 s as the driver's tax,
# and no _poll call may feel it.)
logging.getLogger("state").setLevel(logging.DEBUG)    # the abstain line
                                                      # logs on "state"
FakeCam.builds = 0
FakeCam.instances = []
FakeCam.sleeps = {6: 1.0}
mon9 = PresenceMonitor(scratch_cfg('index = 6\nmode_on = "boot_per_poll"\n'
                                   'mode_off = "boot_per_poll"\n'),
                       FakeDetector())        # the REAL _poll: the phase
mon9.state = "counting"                      # machine is not under test
_t = time.perf_counter()
p9 = mon9._poll()
ms9a = (time.perf_counter() - _t) * 1000
assert ms9a < 100, "the vote BLOCKED on the open: %.0f ms" % ms9a
assert p9 == (None, 0.0), p9                 # abstain: the eye is opening
op9 = mon9._single_opener
assert op9 is not None and op9.inflight, "the vote spawned no open worker"
assert FakeCam.builds == 1, "the vote opened the eye twice itself"
op9.inflight[6].thread.join(10)              # the fake open lands
_t = time.perf_counter()
p9 = mon9._poll()
ms9b = (time.perf_counter() - _t) * 1000
assert ms9b < 100, "the adopting vote blocked: %.0f ms" % ms9b
assert p9[0] is False and p9[1] == 0.0, p9   # a REAL verdict: the eye looked
cam9 = [c for c in FakeCam.instances if c.index == 6][-1]
assert cam9.released, "the boot vote did not blink the LED"
assert op9.held.get(6) is None, "the vote kept the handle - boot must not"
assert 6 not in op9.inflight, "evict left the row behind: no fresh open"
_t = time.perf_counter()
p9 = mon9._poll()
ms9c = (time.perf_counter() - _t) * 1000
assert ms9c < 100, "the re-open vote blocked: %.0f ms" % ms9c
assert p9 == (None, 0.0), p9                 # abstain again...
assert FakeCam.builds == 2, \
    "boot did not re-spawn: one open per vote is the promise"
assert saw("eye 6 still opening; abstain"), "the abstain said nothing"
print("PROBE 9 OK  boot vote: abstain %.0f ms / vote+evict %.0f ms / "
      "re-abstain %.0f ms, LED blinked, one open per vote"
      % (ms9a, ms9b, ms9c))

print("ASYNC OPEN PROBE OK")
