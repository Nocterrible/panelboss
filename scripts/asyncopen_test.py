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
drop stales its own eye ONLY - a sibling mid-open still publishes."""
import logging
import os
import sys
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

    def read(self, timeout=3):
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

print("ASYNC OPEN PROBE OK")
