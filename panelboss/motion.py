"""Motion detection without ML: plain frame differencing.

The pitch for camera-wary users: no model, no faces, nothing learned
about anybody - presence is pixels that changed. The SAME code drives
depth/IR sensors: when a depth sensor exposes a video pin (which most
Windows Hello IR cameras and stereo depth modules do), cv2 opens it
like any other index and hands us frames whose pixels move exactly
like RGB ones - only the lighting is allowed to be pitch dark.

Presence semantics matter more here than in person mode: stillness is
NOT absence (reading a page), so a hit lingers hold_sec after the LAST
motion. Motion stops -> nobody objects to darkness yet; a real person
moves sooner than the screens go dark anyway.

detect() keeps PersonDetector's contract: (boxes x1y1x2y2 in frame
space, scores). While the hold is alive the last motion region is
returned as the box, so state's `present = len(boxes) > 0` and the
preview's box drawing need no special cases.
"""

from __future__ import annotations

import logging
import time

import cv2
import numpy as np

log = logging.getLogger("motion")

SIZE = (320, 180)                      # differencing runs tiny: motion is
                                       # coarse, and it stays this cheap


class MotionDetector:

    def __init__(self, cfg=None):
        cfg = cfg or {}
        # the config normalizer clamps [detection].ratio on the real
        # load path; this floor keeps a hand-built cfg at ratio 0 from
        # reading "any change" as motion (frac >= 0 is always true)
        self.ratio = max(1e-9, float(cfg.get("ratio", 0.003)))
        self.diff_level = int(cfg.get("diff_level", 22))
        self.hold_sec = float(cfg.get("hold_sec", 180))
        self.conf = self.ratio         # the ("confidence", v) hot-write
                                       # still lands here (mode-blind),
                                       # but the gate reads ratio - and
                                       # since W3B the UI mirrors the
                                       # confidence slider to ratio in
                                       # motion mode (gate MED: this
                                       # alias used to make the slider
                                       # a silent no-op in this mode)
        self._prev = None              # blurred gray of the previous frame
        self._last = None              # monotonic stamp of the last motion
        self._box = None               # its region, in frame space

    def reset(self):
        """The camera reopened: a stale reference frame of the OLD scene
        would read as a frame full of motion."""
        self._prev = None

    def detect(self, frame, conf=None):
        gray = (frame.copy() if frame.ndim == 2
                else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        small = cv2.resize(gray, SIZE)
        small = cv2.GaussianBlur(small, (21, 21), 0)
        frac = 0.0
        if self._prev is not None:                 # resize makes every
                                                   # camera comparable
            diff = cv2.absdiff(small, self._prev)
            mask = cv2.threshold(diff, self.diff_level, 255,
                                 cv2.THRESH_BINARY)[1]
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            frac = float(np.count_nonzero(mask)) / mask.size
            if frac >= self.ratio:
                self._last = time.monotonic()
                self._box = self._region(mask, frame.shape[:2])
        self._prev = small
        if self._last is None:
            return np.empty((0, 4)), np.empty((0,))
        if time.monotonic() - self._last > self.hold_sec:
            return np.empty((0, 4)), np.empty((0,))
        score = min(1.0, 0.1 + frac * 10.0)     # 0.1 while merely holding
        return (np.array([self._box], dtype=np.float32),
                np.array([score], dtype=np.float32))

    def _region(self, mask, shape):
        """Bounding box of the changed pixels, mask space -> frame space.
        An all-zero mask has no region: ABSTAIN, never let an empty
        xs.min() raise (a zero ratio would otherwise hit this path)."""
        h, w = shape
        ys, xs = np.nonzero(mask)
        if not len(xs):
            return (0.0, 0.0, float(w), float(h))
        sx = w / float(mask.shape[1])
        sy = h / float(mask.shape[0])
        return (xs.min() * sx, ys.min() * sy,
                (xs.max() + 1) * sx, (ys.max() + 1) * sy)
