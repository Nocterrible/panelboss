"""No-window, no-camera checks for the companions frame-shape fixes
(Oct 12 W2A): the letterbox abstains on a 0-dimension frame and accepts
grayscale polls, the motion detector survives a zero ratio, the onnx
head confesses at build, and the faces gallery saves atomic. No real
camera, no window, no model download: probe (4) drives the validator
through a fake session, probe (5) tests FaceGate._save in isolation
(via __new__, because the insightface dep is optional and not needed
for the save path). One PASS line per numbered section; exit 0 is the
only green shape (pinlifecycle_test's verdict shape)."""
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))

import numpy as np                      # noqa: E402

from panelboss import detector, faces, inference, motion  # noqa: E402


def main():
    # 1) _letterbox accepts a 2-D grayscale frame AND a 3-channel one:
    #    both land on the 3-channel canvas, no broadcast raise, and the
    #    gray path keeps the letterbox geometry (720x1280 -> 360x640 at
    #    r=0.5, centered: top=140, left=0)
    gray = np.zeros((720, 1280), np.uint8)
    canvas, left, top, r = detector._letterbox(gray, (640, 640))
    assert canvas.shape == (640, 640, 3) and canvas.dtype == np.uint8
    assert (left, top, r) == (0, 140, 0.5), (left, top, r)
    bgr = np.zeros((480, 640, 3), np.uint8)
    canvas2, l2, t2, r2 = detector._letterbox(bgr, (640, 640))
    assert canvas2.shape == (640, 640, 3) and canvas2.dtype == np.uint8
    assert (l2, t2, r2) == (0, 80, 1.0), (l2, t2, r2)
    print("[PASS] 1: _letterbox - 2-D and 3-channel frames both land "
          "on the 3-ch canvas, geometry intact")

    # 2) _letterbox on a 0x0 frame ABSTAINS: a flat 114 canvas and the
    #    identity (left, top, r) so _scale degenerates cleanly - no
    #    ZeroDivisionError, no raise
    zero = np.zeros((0, 0), np.uint8)
    c, l, t, r = detector._letterbox(zero, (640, 640))
    assert c.shape == (640, 640, 3) and (l, t, r) == (0, 0, 0.0)
    zero_c = np.zeros((0, 0, 3), np.uint8)
    c2, l2, t2, r2 = detector._letterbox(zero_c, (640, 640))
    assert c2.shape == (640, 640, 3) and (l2, t2, r2) == (0, 0, 0.0)
    print("[PASS] 2: _letterbox abstains on 0x0 (both dim variants) "
          "with the identity transform")

    # 3) MotionDetector at ratio 0.0: the config normalizer clamps the
    #    real load path, a hand-built cfg reaches detect() raw - two
    #    identical gray frames abstain (frac 0 < the >0 floor, no
    #    xs.min() on the empty mask), and _region itself abstains on an
    #    all-zero mask
    md = motion.MotionDetector({"ratio": 0.0})
    assert md.ratio > 0.0, md.ratio
    f1 = (np.arange(180 * 320, dtype=np.uint8).reshape(180, 320))
    boxes, scores = md.detect(f1)
    boxes, scores = md.detect(f1.copy())
    assert boxes.shape == (0, 4) and scores.shape == (0,), (
        boxes.shape, scores.shape)
    region = md._region(np.zeros((10, 10), np.uint8), (180, 320))
    assert region == (0.0, 0.0, 320.0, 180.0), region
    print("[PASS] 3: ratio 0.0 abstains (no empty-mask xs.min()), "
          "_region abstains on the zero mask")

    # 4) the onnx head confesses at BUILD (inference.validate_head,
    #    called right after the session is constructed): (1, 84, 8400)
    #    passes; (1, 1000), (1, 85, 8400) and (84,) all raise the NAMED
    #    ValueError. Both through the validator directly and through
    #    the real get_session wiring (a fake onnxruntime module stands
    #    in, so no model file is needed).
    class _Head:
        def __init__(self, shape):
            self.shape = shape

    class _Sess:
        def __init__(self, shape):
            self._shape = shape

        def get_outputs(self):
            return [_Head(self._shape)]

        def get_providers(self):
            return ["CPUExecutionProvider"]

    inference.validate_head(_Sess((1, 84, 8400)))
    for bad in ((1, 1000), (1, 85, 8400), (84,)):
        try:
            inference.validate_head(_Sess(bad))
        except ValueError as e:
            assert "expected detection head (N, 84, 8400)" in str(e) \
                and str(bad) in str(e), str(e)
        else:
            raise AssertionError("head %s passed validation" % (bad,))

    import types
    real_rt = sys.modules.get("onnxruntime")

    def _wiring(shape, expect_error):
        rt = types.ModuleType("onnxruntime")
        rt.get_available_providers = lambda: ["CPUExecutionProvider"]
        rt.InferenceSession = lambda path, providers=None: _Sess(shape)
        sys.modules["onnxruntime"] = rt
        try:
            try:
                inference.get_session("fake.onnx", device="cpu")
            except ValueError as e:
                assert expect_error, str(e)
                assert "expected detection head (N, 84, 8400)" in str(e)
                return
            assert not expect_error
        finally:
            if real_rt is not None:
                sys.modules["onnxruntime"] = real_rt
            else:
                del sys.modules["onnxruntime"]

    _wiring((1, 84, 8400), False)
    _wiring((1, 1000), True)
    print("[PASS] 4: the head validates at build - (1,84,8400) passes, "
          "(1,1000)/(1,85,8400)/(84,) confess with the named ValueError, "
          "wired through get_session")

    # 5) the gallery save is atomic and lock-guarded: _save writes the
    #    tmp name then os.replace (config.write_config's shape), sweeps
    #    the litter on a failed replace, and the save/read pair holds
    #    the one gate lock while _match stacks the same dict
    d = tempfile.mkdtemp(prefix="panelboss_companions_")
    g = faces.FaceGate.__new__(faces.FaceGate)   # isolation: no insightface
    g._lock = threading.RLock()
    g.db = os.path.join(d, "faces.npz")
    g.stored = {"alice": np.array([1.0, 0.0], dtype=np.float32)}
    g._save()
    data = np.load(g.db, allow_pickle=True)
    assert list(data.files) == ["alice"] and \
        (data["alice"] == g.stored["alice"]).all()
    data.close()        # np.load holds the file open; Windows refuses a
                        # replace onto a destination another handle owns
    real_replace = os.replace

    def _explode(*a, **k):
        raise OSError("simulated crash mid-replace")

    faces.os.replace = _explode
    try:
        try:
            g._save()
        except OSError:
            pass
        else:
            raise AssertionError("failed replace did not raise")
    finally:
        faces.os.replace = real_replace
    litter = [f for f in os.listdir(d) if ".tmp." in f]
    assert not litter, litter
    errors = []

    def _vote():
        for _ in range(50):
            try:
                g._match(np.array([1.0, 0.0], dtype=np.float32))
            except Exception as e:      # noqa: BLE001
                errors.append(e)

    threads = [threading.Thread(target=_vote) for _ in range(4)]
    for t in threads:
        t.start()
    for _ in range(50):
        g.stored["bob%d" % len(g.stored)] = \
            np.array([0.0, 1.0], dtype=np.float32)
        g._save()
    for t in threads:
        t.join()
    assert not errors, errors[:3]
    assert not [f for f in os.listdir(d) if ".tmp." in f]
    final = np.load(g.db, allow_pickle=True)
    assert "alice" in final.files and "bob50" in final.files
    print("[PASS] 5: faces save is tmp+replace under the gate lock - "
          "failed replace sweeps the litter, 4 voting threads + 50 "
          "enrolls never tear the dict")

    # 6) THE PUMP ROW LEFT THIS CARD (owner ruling, Oct 22): the
    #    [dimmer].input_pump switch moved home to the dimmer card, so
    #    _build_companion no longer builds it. The PRESENT half of the
    #    law pins in dimmer_test; this pin inverts it here - the row
    #    must be ABSENT from the companion builder.
    oled = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "panelboss", "ui", "window", "_oled.py"), encoding="utf-8").read()
    _comp = oled[oled.index("def _build_companion"):]
    _comp = _comp[:_comp.index("\n    def ")]
    assert "keep Windows awake" not in _comp, \
        "the pump row is back on the companion card"
    assert "TIP_COMP[\"pump\"]" not in _comp, \
        "the pump tip is back on the companion card"
    assert "oled_comp_pump_box" not in _comp, \
        "the pump switch is back on the companion card"
    print("[PASS] 6: the pump row is absent from the companion card "
          "(it lives on the dimmer card now)")

    print("companions OK")


if __name__ == "__main__":
    main()
