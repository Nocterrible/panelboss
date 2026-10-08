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
                 device_id=0, conf=0.45, verbose=False):
        self.session = inference.get_session(
            inference.find_model(model), device=device,
            device_id=device_id)
        self.input_name = self.session.get_inputs()[0].name
        self.conf = conf
        self.classes = [0]              # person, after the boxes
        self.input_size = (640, 640)    # static shape from header

    def detect(self, frame, conf=None):
        """Boxes (x1y1x2y2) in frame space plus their scores."""
        img = cv2.resize(frame, self.input_size)   # stretch, aspect lost
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
        boxes = _scale(boxes, self.input_size, frame.shape[:2])
        keep = _nms(boxes, scores, iou_thresh=0.5)
        return boxes[keep], scores[keep]

    def is_present(self, frame, conf=None):
        """(bool, max_score) presence and the confidence."""
        boxes, scores = self.detect(frame, conf)
        if not len(scores):
            return False, 0.0
        return len(boxes) > 0, float(np.max(scores))


def _scale(boxes, input_size, frame_shape):
    """cx cy w h (input space) -> x1 y1 x2 y2 (frame space)."""
    h, w = frame_shape
    sx = w / float(input_size[1])
    sy = h / float(input_size[0])
    cx = boxes[:, 0] * sx
    cy = boxes[:, 1] * sy
    bw = boxes[:, 2] * sx
    bh = boxes[:, 3] * sy
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
