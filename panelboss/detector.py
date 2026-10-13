"""Person detection.

decode: transpose(1, 2, 0) -> (8400, 84); the first 4 columns are
cx, cy, w, h already in input-pixel space, the remaining 80 are COCO
class scores (person is class 0, always after the boxes). We only keep
people: a chair with a jacket on it does not count as presence.

NMS is implemented here with numpy instead of cv2.dnn so the module
survives OpenCV API churn.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from . import inference

log = logging.getLogger("detector")


class PersonDetector:

    def __init__(self, model="yolo11n", device="auto",
                 device_id=0, conf=0.45, diff_level=22, verbose=False):
        self.session = inference.get_session(
            inference.find_model(model), device=device,
            device_id=device_id)
        self.input_name = self.session.get_inputs()[0].name
        self.conf = conf
        self.classes = [0]              # person, after the boxes
        self.input_size = (640, 640)    # static shape from header
        self.diff_level = int(diff_level)   # the assist tier's motion gate
        self._prev_gray = None         # last polled frame, gray: the
                                       # assist tier diffs against it

    def detect(self, frame, conf=None):
        """Boxes (x1y1x2y2) in frame space plus their scores."""
        img, left, top, r = _letterbox(frame, self.input_size)
        if r == 0.0:
            # gate fix: zero ratio (0-size frame) makes _scale divide by
            # zero - inf/NaN boxes can survive _nms's self-keep and vote
            # present as garbage. Abstain NOW, before the inference:
            # no boxes, no scores, no vote.
            return np.empty((0, 4)), np.empty(0)
        img = img[..., ::-1]                  # BGR -> RGB, first
        blob = np.transpose(img, (2, 0, 1)).astype(np.float32)
        blob = blob[np.newaxis] / 255
        outputs = self.session.run(None, {self.input_name: blob})
        dets = np.transpose(outputs[0], (0, 2, 1)).squeeze(0)  # 8400
        boxes, scores = dets[:, :4], dets[:, 4:]
        classes = scores.argmax(axis=1)
        scores = scores.max(axis=1)
        keep = scores >= (conf if conf is not None else self.conf)
        keep = keep & np.isin(classes, self.classes)  # person first
        boxes, scores = boxes[keep], scores[keep]
        boxes = _scale(boxes, left, top, r, frame.shape[:2])
        keep = _nms(boxes, scores, iou_thresh=0.5)
        return boxes[keep], scores[keep]

    def detect_lively(self, frame, conf=None):
        """(boxes, scores, present): a clear hit (conf) is present on its
        own; a borderline one (conf/2) counts only if its region moved
        since the last polled frame - a jacket frozen on the chair never
        moves, so it stays absent. On the very first frame there is no
        reference to diff against, so the assist boxes still come back
        (present=False) and the debug view can see the candidates."""
        c = conf if conf is not None else self.conf
        gray = (frame if frame.ndim == 2
                else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        boxes, scores = self.detect(frame, c)
        if len(boxes):                         # the strict tier answered
            self._prev_gray = gray
            return boxes, scores, True
        # the assist floor is clamped: conf is user-tunable, and a
        # slider at 0.3 would otherwise open the gate to 0.15 where
        # yolo noise boxes live - the weak motion check would then
        # rubber-stamp pixels that never were a person
        assist, ascores = self.detect(frame, max(0.20, c * 0.5))
        moved = False
        if (len(assist) and self._prev_gray is not None
                and self._prev_gray.shape == gray.shape):
            moved = self._moved(gray, assist, self._prev_gray)
        self._prev_gray = gray                 # the next poll diffs against
                                               # THIS frame, whatever tier
        return assist, ascores, moved

    def reset(self):
        """Camera released or re-pointed: forget the reference frame.
        Diffing a reopened (or re-indexed, or post-standby) stream
        against a reference of unknown age is exactly the phantom
        motion the assist tier must not trust."""
        self._prev_gray = None

    def _moved(self, gray, boxes, prev_gray):
        """True when any assist box's region changed enough since
        prev_gray: pixels above diff_level inside the box (expanded 25%)
        beat 0.3% of that area. Static blobs - a jacket, a lamp - never
        pass."""
        h, w = gray.shape[:2]
        for x1, y1, x2, y2 in boxes:
            bw, bh = x2 - x1, y2 - y1
            ex, ey = int(round(bw * 0.25)), int(round(bh * 0.25))
            xa, ya = max(0, int(x1 - ex)), max(0, int(y1 - ey))
            xb, yb = min(w, int(x2 + ex)), min(h, int(y2 + ey))
            if xb <= xa or yb <= ya:
                continue
            changed = np.count_nonzero(
                cv2.absdiff(gray[ya:yb, xa:xb],
                            prev_gray[ya:yb, xa:xb]) > self.diff_level)
            if changed > 0.003 * (xb - xa) * (yb - ya):
                return True
        return False

    def is_present(self, frame, conf=None):
        """(bool, max_score) presence and the confidence."""
        boxes, scores = self.detect(frame, conf)
        if not len(scores):
            return False, 0.0
        return len(boxes) > 0, float(np.max(scores))


def build(cfg):
    """The one factory every caller uses: motion mode never touches
    onnxruntime at all (no model load, no provider probe), and the
    person mode path stays exactly the old constructor call."""
    mode = (cfg.get("detection") or {}).get("mode", "person")
    if mode == "motion":
        from . import motion
        log.info("detection mode: motion (no model will be loaded)")
        return motion.MotionDetector(cfg.get("detection"))
    return PersonDetector(
        model=cfg["inference"]["model"],
        device=cfg["inference"]["device"],
        device_id=cfg["inference"]["device_id"],
        conf=cfg["inference"]["confidence"],
        diff_level=(cfg.get("detection") or {}).get("diff_level", 22))


def _letterbox(frame, size):
    """Fit the frame into the model's square WITHOUT stretching it: scale
    by r = the min fit, center on a grey 114 canvas. Returns
    (canvas, left, top, r) so _scale can map boxes back to frame space.
    The old stretch squashed a 16:9 face into an oval and cost the model
    its sensitivity (measured on the same frame: 0.14 stretched vs 0.25
    letterboxed - both under the 0.45 floor, but letterbox is the one a
    borderline hit can reach)."""
    h, w = frame.shape[:2]
    sh, sw = size
    if h < 1 or w < 1:
        # a 0-height / 0-width frame can not be fit into the canvas:
        # ABSTAIN, like a black frame - no scale exists, so say "no
        # detections" instead of dividing by zero. (The ndim == 2 guard
        # in detect_lively used to be dead: detect() died here first.)
        return (np.full((sh, sw, 3), 114, np.uint8), 0, 0, 0.0)
    r = min(sh / h, sw / w)
    nw, nh = int(round(w * r)), int(round(h * r))
    if frame.ndim == 2:
        # grayscale poll: the canvas is 3-channel, so the paste needs a
        # color frame (cv2's cvtColor copies, no caller-buffer aliasing)
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    img = cv2.resize(frame, (nw, nh))
    canvas = np.full((sh, sw, 3), 114, np.uint8)
    top = (sh - nh) // 2
    left = (sw - nw) // 2
    canvas[top:top + nh, left:left + nw] = img
    return canvas, left, top, r


def _scale(boxes, left, top, r, frame_shape):
    """cx cy w h (canvas space) -> x1 y1 x2 y2 (frame space). Undo the
    letterbox: strip the padding (left, top) first, then divide by the
    fit scale r. A box at the canvas center lands at the frame center."""
    h, w = frame_shape
    cx = (boxes[:, 0] - left) / r
    cy = (boxes[:, 1] - top) / r
    bw = boxes[:, 2] / r
    bh = boxes[:, 3] / r
    out = np.empty_like(boxes)
    out[:, 0] = cx - bw / 2                   # x1 always first
    out[:, 1] = cy - bh / 2
    out[:, 2] = cx + bw / 2
    out[:, 3] = cy + bh / 2
    out[:, [0, 2]] = out[:, [0, 2]].clip(0, w)
    out[:, [1, 3]] = out[:, [1, 3]].clip(0, h)
    return out


def _nms(boxes, scores, iou_thresh=0.5):
    """Greedy by score; pairwise IoU, keeps at most 100."""
    order = np.argsort(-scores)[:100]
    boxes, scores = boxes[order], scores[order]
    x1, y1, x2, y2 = (boxes[:, 0], boxes[:, 1],
                    boxes[:, 2], boxes[:, 3])
    areas = (x2 - x1) * (y2 - y1)
    keep = np.ones(len(x1), dtype=bool)     # start with everything
    for i in range(len(x1)):
        if not keep[i]:
            continue
        inter_x = np.minimum(x2[i], x2) - np.maximum(x1[i], x1)
        inter_y = np.minimum(y2[i], y2) - np.maximum(y1[i], y1)
        inter = np.maximum(inter_x, 0) * np.maximum(inter_y, 0)
        iou = inter / (areas[i] + areas - inter + 1e-9)
        keep = keep & (iou <= iou_thresh)   # union last
        keep[i] = True                        # the kept box survives
    return order[keep]
