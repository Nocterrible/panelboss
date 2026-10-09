"""Offline checks for motion mode: the differencer, the factory, the
mode-switch event. No camera, no model, no window."""
import os
import sys
import time

sys.path.insert(0, r"F:\Projects\ICU-PresenceDetector")

import numpy as np

from awaywatch import config, detector
from awaywatch.motion import MotionDetector
from awaywatch.state import PresenceMonitor


def scene(x=60, size=(480, 640, 3), step=40):
    """A dark frame with one bright rectangle at column x, moved by
    shaking the box between frames; the blur floor means a frozen
    frame is a guaranteed zero diff."""
    frame = np.zeros(size, np.uint8)
    frame[140:260, x:x + step] = (255, 255, 255)
    return frame


# 1) movement is present, stillness only holds, and the hold expires
det = MotionDetector({"ratio": 0.001, "diff_level": 10, "hold_sec": 0.4})
boxes, scores = det.detect(scene(60))
assert len(boxes) == 0, "the first frame has no reference to diff"
boxes, scores = det.detect(scene(300))           # the box teleports
assert len(boxes) == 1 and len(scores) == 1, (boxes, scores)
x1, y1, x2, y2 = boxes[0]
h, w = scene().shape[:2]
assert -1 <= x1 < x2 <= w + 1 and -1 <= y1 < y2 <= h + 1, (boxes, w, h)
assert scores[0] > 0.5, scores                   # fresh motion scores high
hold_seen = time.monotonic()
boxes, scores = det.detect(scene(300))           # same frame: no motion
assert len(boxes) == 1, "stillness inside the hold must keep presence"
assert scores[0] <= 0.2, "holding must not pretend fresh motion"
time.sleep(0.5)
boxes, _ = det.detect(scene(300))                # hold expired
assert len(boxes) == 0, "presence outlived hold_sec"
boxes, scores = det.detect(scene(120))           # moving again
assert len(boxes) == 1, "motion after the hold must be believed"
print("differencer OK (move, hold, expiry, re-move)")

# 2) reset drops the reference: a different camera must not read as
#    one giant motion (that false hit would cost hold_sec of presence)
det.reset()
time.sleep(0.5)                                   # the old hold expires;
                                                  # reset clears the scene
                                                  # reference, not history
boxes, _ = det.detect(np.full((480, 640, 3), 9, np.uint8))   # new scene
assert len(boxes) == 0, "the first frame of the new scene diffed anyway"
print("reset OK")

# 3) the factory: motion must not touch onnxruntime, person must
calls = []
detector.PersonDetector = lambda **kw: calls.append(kw) or "PERSON"
cfg = config.get_config(verbose=False)
_saved_wc = config.write_config
config.write_config = lambda c, path=None: _saved_wc(
    c, os.path.join(os.environ.get("TEMP", "."), "icu_test_config.toml"))
try:
    cfg["detection"]["mode"] = "motion"
    det = detector.build(cfg)
    assert det.__class__.__name__ == "MotionDetector", det
    assert not calls, "motion mode loaded the model anyway"
    cfg["detection"]["mode"] = "person"
    assert detector.build(cfg) == "PERSON", calls
    assert calls and "model" in calls[0], calls
    print("factory OK (motion skips onnx, person gets its kwargs)")

    # 5) the tray event rebuilds through the factory and persists
    class StubDetector:
        conf = 0.45

        def detect(self, frame, conf=None):
            return np.empty((0, 4)), np.empty((0,))

    cfg["detection"]["mode"] = "person"
    mon = PresenceMonitor(cfg, StubDetector())
    mon.events.put(("detection_mode", "motion"))
    mon._drain_tray()
    assert mon.detector.__class__.__name__ == "MotionDetector", mon.detector
    cfg["detection"]["mode"] = "person"          # back the same way
    mon.events.put(("detection_mode", "person"))
    mon._drain_tray()
    assert mon.detector == "PERSON", mon.detector
    print("mode switch event OK")
finally:
    config.write_config = _saved_wc

# 6) the tray writes the config dict and queues the event (no GUI)
from awaywatch import tray
t = tray.Tray(__import__("queue").Queue(), cfg)
t._mode("motion")
assert cfg["detection"]["mode"] == "motion"
assert t.events.get() == ("detection_mode", "motion"), t.events
print("tray wiring OK")
# 7) hello IR adapter against a fake whircam: the whole Camera contract
import types as _types
fake = _types.ModuleType("whircam")


class FakeIRCam:
    instances = []

    def __init__(self, group=None, format_index=None, timeout=8.0,
                 format_output="bgr"):
        self.group, self.format_output = group, format_output
        self.opened, self.frames = True, 0
        FakeIRCam.instances.append(self)

    @property
    def width(self):
        return 640

    @property
    def height(self):
        return 360

    @property
    def is_opened(self):
        return self.opened

    def read(self, timeout=None):
        self.frames += 1
        if self.frames <= 3:
            return True, np.zeros((360, 640, 3), np.uint8)
        return False, None

    def release(self):
        self.opened = False


class FakeGroup:
    def __init__(self, name):
        self.name = name


fake.find_groups = lambda: [FakeGroup("USB Camera"), FakeGroup("Both")]
fake.IRCam = FakeIRCam
sys.modules["whircam"] = fake

from awaywatch import camera as cam_mod
cam_mod._ir_names_cache = None
assert cam_mod.hello_ir_names() == ["USB Camera", "Both"]
c = cam_mod.open_camera({"index": cam_mod.HELLO_IR, "warmup_frames": 2})
assert isinstance(c, cam_mod.HelloIrCamera) and c.is_open()
assert c.warm_up() == 2, "warm-up must count settled frames"
inst = FakeIRCam.instances[-1]
assert c.read() is not None and inst.format_output == "bgr"
inst.frames = 5                                   # exhausted stream
assert c.read() is None                           # no frame = None, no raise
c.release()
c.release()                                       # idempotent
assert not c.is_open()


class Crasher(FakeIRCam):
    def read(self, timeout=None):
        raise RuntimeError("pump crashed")


fake.IRCam = Crasher
c2 = cam_mod.open_camera({"index": cam_mod.HELLO_IR})
assert c2.read(timeout=1) is None, "a crashed pump must read as dead"
c2.release()
# and the cv2 path keeps its exact old kwargs (patched Camera records them)
_real_camera = cam_mod.Camera
seen = {}
cam_mod.Camera = lambda **kw: seen.update(kw) or "CV2"
try:
    got = cam_mod.open_camera({"index": 3, "warmup_frames": 1,
                               "width": 800, "height": 600})
    assert got == "CV2" and seen == {"index": 3, "warmup": 1,
                                     "width": 800, "height": 600}, seen
finally:
    cam_mod.Camera = _real_camera
print("hello IR adapter OK (open, warmup, read, crash, release, factory)")

print("ALL MOTION TESTS OK")
