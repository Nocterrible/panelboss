"""Offline checks for motion mode: the differencer, the factory, the
mode-switch event. No camera, no model, no window."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from panelboss import config, detector
from panelboss.motion import MotionDetector
from panelboss.state import PresenceMonitor


def scene(x=60, size=(480, 640, 3), step=40):
    """A dark frame with one bright rectangle at column x, moved by
    shaking the box between frames; the blur floor means a frozen
    frame is a guaranteed zero diff."""
    frame = np.zeros(size, np.uint8)
    frame[140:260, x:x + step] = (255, 255, 255)
    return frame


# 0) the person-mode letterbox + two-tier rule, offline: patch the
#    session seam so PersonDetector never touches onnxruntime / a model
class _FakeIn:
    name = "images"


class _FakeSession:
    def __init__(self, outputs):
        self._out = outputs

    def get_inputs(self):
        return [_FakeIn()]

    def run(self, names, feed):
        return [self._out]


def person_with(outputs, conf=0.45):
    """A PersonDetector whose session is a canned blob (no model load)."""
    _fs, _fm = detector.inference.get_session, detector.inference.find_model
    detector.inference.get_session = lambda *a, **k: _FakeSession(outputs)
    detector.inference.find_model = lambda *a, **k: "stub.onnx"
    try:
        return detector.PersonDetector(conf=conf)
    finally:
        detector.inference.get_session = _fs
        detector.inference.find_model = _fm


# letterbox geometry round-trip: one person blob at a known canvas
# location must map back to hand-math frame space for a 1280x720 frame
# (the old stretch placed it elsewhere - this pins the regression)
out = np.zeros((1, 84, 8400), np.float32)
out[0, 0, 10] = 320.0        # cx, canvas space
out[0, 1, 10] = 320.0        # cy
out[0, 2, 10] = 200.0        # w
out[0, 3, 10] = 300.0        # h
out[0, 4, 10] = 0.8          # person class score
pd = person_with(out)
frame = np.zeros((720, 1280, 3), np.uint8)
boxes, scores = pd.detect(frame)
assert len(boxes) == 1 and abs(float(scores[0]) - 0.8) < 1e-6, (boxes, scores)
# 1280x720 -> r = min(640/720, 640/1280) = 0.5, left = 0, top = 140
# cx_f = (320-0)/0.5 = 640, cy_f = (320-140)/0.5 = 360
# bw_f = 200/0.5 = 400, bh_f = 300/0.5 = 600
assert np.allclose(boxes[0], [440.0, 60.0, 840.0, 660.0], atol=1), boxes[0]
print("letterbox round-trip OK (canvas -> frame hand-math, 1280x720)")

# two-tier: a 0.24 person sits below the 0.45 strict tier but at/above
# the 0.225 assist tier. Poll the same frame twice -> present stays
# False (a static blob never moves); patch 20x20 inside the box to 255
# -> present True (it moved)
out2 = np.zeros((1, 84, 8400), np.float32)
out2[0, 0, 10] = 320.0       # canvas box, centered
out2[0, 1, 10] = 320.0
out2[0, 2, 10] = 100.0       # w -> 200 in frame space
out2[0, 3, 10] = 100.0       # h -> 200 in frame space
out2[0, 4, 10] = 0.24        # 0.24 < 0.45 strict, >= 0.225 assist
pd2 = person_with(out2, conf=0.45)
frame2 = np.zeros((720, 1280, 3), np.uint8)
b1, s1, p1 = pd2.detect_lively(frame2)
assert len(b1) == 1 and p1 is False, (b1, p1)   # first frame: no reference
b2, s2, p2 = pd2.detect_lively(frame2)
assert p2 is False, "a static assist blob must stay absent"
frame2[280:300, 600:620] = 255       # 20x20 inside the box, set bright
b3, s3, p3 = pd2.detect_lively(frame2)
assert p3 is True, "motion inside the assist box must read present"
print("two-tier OK (static blob absent, moved blob present)")

# the assist floor is clamped at 0.20 no matter how low the user
# winds confidence: a 0.17 blob at conf 0.3 must not even surface
# as an assist candidate (unclamped it would floor at 0.15 - yolo
# noise territory)
out3 = np.zeros((1, 84, 8400), np.float32)
out3[0, 0, 10] = 320.0
out3[0, 1, 10] = 320.0
out3[0, 2, 10] = 100.0
out3[0, 3, 10] = 100.0
out3[0, 4, 10] = 0.17
pd3 = person_with(out3, conf=0.30)
b4, _s4, p4 = pd3.detect_lively(frame2)
assert len(b4) == 0 and p4 is False, (b4, p4)
print("assist floor clamp OK (conf 0.3 still floors at 0.20)")

# a reopened camera must not phantom-present: reset() forgets the
# reference, so the next frame - however different - is trusted
# only from the SECOND poll on, exactly like a cold boot
frame3 = frame2.copy()
frame3[100:200, 100:300] = 255         # a huge change inside the box
pd2.reset()
b5, _s5, p5 = pd2.detect_lively(frame3)
assert len(b5) == 1 and p5 is False, "reopened stream must not trust a diff"
print("detector reset OK (reopened camera cannot phantom-present)")


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
    c, os.path.join(os.environ.get("TEMP", "."), "panelboss_test_config.toml"))
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
from panelboss import tray
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

from panelboss import camera as cam_mod
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
