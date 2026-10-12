"""The debug view's plumbing: the newest-frame slot (FrameBox) and the
leased preview path, single-camera and mosaic. Formerly state.py
lines 33-50 and 736-826."""

import logging
import threading
import time

log = logging.getLogger("state")


class FrameBox:
    """The newest frame slot: the state machine writes after every
    detect, the settings window reads at its own pace. Newest wins,
    so the debug view can drop frames but never shows a stale model
    result next to a fresh picture."""

    def __init__(self):
        self._lock = threading.Lock()
        self.latest = None            # (bgr, boxes, scores, ts)

    def put(self, frame, boxes, scores):
        with self._lock:
            # cv2 hands out buffers it may recycle; the slot is a snapshot
            self.latest = (frame.copy(), boxes, scores, time.monotonic())

    def get(self):
        with self._lock:
            return self.latest


class _PreviewMixin:

    def _preview(self, now):
        """Debug frames while the lease is live: the camera is held,
        detection runs, and the gate and timers are on holiday; the
        phase machine resumes untouched when the lease runs out. One
        camera previews exactly as it always did; several cameras
        push the composed mosaic (preview_grid) into the SAME frame
        slot, so the window's single draw path never learns the
        difference."""
        if self.detector is None:
            return              # no model yet (warm-up) or ever (the
                                # fail-open build failure): abstain
        rot = self.camera
        if len(self._indexes()) > 1:
            if rot is None:
                # the lease owns one rotor and stores it: an unstored
                # one would be rebuilt every tick, leak its opened
                # sub-cams, and dodge the lease-end release
                rot = self.camera = self._new_camera()
            if getattr(rot, "rotating", False):
                # the mosaic opens its own sub-cameras: an all-boot
                # desk's rotor holds nothing open between leases, so
                # the is_open() gate below would starve the wall
                self._preview_mosaic(rot)
                return
        if self.camera is None or not self.camera.is_open():
            # SYNC on purpose: a single-eye desk boots the one eye it
            # will poll anyway, so this wait is the same one the normal
            # poll already pays. If a single-eye desk ever complains,
            # the mosaic path below is the model (rotor.open_async,
            # labeled holes, progressive fill).
            self._hold_camera()
            if self.camera is None or not self.camera.is_open():
                return                                 # still booting
        frame = self.camera.read()
        if frame is None:
            return
        boxes, scores = self.detector.detect(frame)
        self.framebox.put(frame, boxes, scores)

    def _preview_mosaic(self, rot):
        """The wall under a live lease: open EVERY index the lease may
        look at and feed each frame to compose() with the label that
        states what the eye actually is. An index that is "off" for
        the CURRENT display state still opens - it never votes, but a
        preview is allowed to look; only a PERMANENTLY off index (off
        in both tables, an eye this app will never need) stays a
        labeled hole, unopened. A tile whose frame did not arrive is
        labeled, not faked: an eye the lease does not hold yet opens on
        its own thread (rotor.open_async) and carries "opening" until
        it lands, so the wall appears with the fast eye and fills in -
        the tick never blocks on a slow driver. Release of all of it is
        the lease-end _release_camera the single path already uses (the
        rotor lets go of every sub-cam it holds, and _invalidate makes
        an open that was still in flight release its own fresh handle)."""
        import cv2
        import numpy as np
        from PIL import Image
        from .. import config, preview_grid
        frames, labels = {}, {}
        table = "off" if self.state == "off" else "on"
        for index in rot.indexes:
            if (self._table_mode(index, "on") == "off"
                    and self._table_mode(index, "off") == "off"):
                frames[index] = None
                labels[index] = "off"
                continue
            cam = rot.cameras.get(index)
            if cam is None or not cam.is_open():
                # Never wait for an eye: rotor.open_async opens it on
                # its own thread and this tick shows a labeled hole.
                # The fast eye lands on the wall at once, the slow one
                # fills in when its driver lets go (38 s was measured)
                # - the tile says "opening" until then, labeled, not
                # faked.
                rot.open_async(index)
                frames[index] = None
                labels[index] = "opening"
                continue
            frame = cam.read()
            if frame is None:
                frames[index] = None
                labels[index] = "closed"
                continue
            mode = self.effective_mode(index)
            if self._table_mode(index, table) == "always_on" \
                    and mode != "always_on":
                label = "degraded poll"
            else:
                label = config.MODE_LABELS.get(mode, "poll")
            frames[index] = Image.fromarray(
                cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            labels[index] = label
        # every tick composes: an all-"opening" wall beats freezing the
        # last pre-lease frame for 38 s and letting a stale picture read
        # as live (gate finding; preview_grid paints the labeled holes)
        tile_w = max(160, int(self.cfg.get("ui", {}).get(
            "preview_width", 420)) // 2)
        mosaic = preview_grid.compose(frames, labels, tile_w=tile_w)
        if mosaic is None:
            return
        bgr = cv2.cvtColor(np.asarray(mosaic), cv2.COLOR_RGB2BGR)
        boxes, scores = self.detector.detect(bgr)
        self.framebox.put(bgr, boxes, scores)
