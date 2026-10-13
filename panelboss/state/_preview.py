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


def _tile_rgb(frame):
    """One mosaic tile: camera frame -> PIL RGB image, or None when the
    frame has no honest tile. THE MONO-DRIVER CLASS (same as detector's
    letterbox fix, W2A - closed at BOTH ends now): the letterbox fix
    let grayscale frames survive DETECTION, so they now reach this
    compositor too, and cvtColor(BGR2RGB) RAISES on a 2-D frame. Branch
    on ndim: 2-D (mono/IR) converts GRAY2RGB, 3-D (BGR) keeps the old
    path; anything else (a 2-channel depth frame) cannot be painted
    honestly, so the caller abstains the tile - the labeled hole the
    wall already renders for the cameras it does not hold."""
    import cv2
    from PIL import Image
    if frame.ndim == 2:
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB))
    if frame.ndim == 3 and frame.shape[2] == 3:
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    return None


class _PreviewMixin:

    def _preview(self, now):
        """Debug frames while the lease is live: the camera is held,
        detection runs, and the gate and timers are on holiday; the
        phase machine resumes untouched when the lease runs out. The
        tick NEVER blocks on an open - neither the multi-camera wall
        (labeled holes, progressive fill) nor the single-eye desk (the
        SAME AsyncOpener discipline the mosaic's rotor uses: the worker
        opens and warms in the background and the tick re-reads it each
        poll, so the first leased tick is milliseconds and the tile -
        or the previous wall - simply survives until the frame lands).
        Both paths feed the SAME one slot framebox, so the window's
        single draw path never learns the difference."""
        if self.detector is None:
            return              # no model yet (warm-up) or ever (the
                                # fail-open build failure): abstain
        rot = self.camera
        if len(self._indexes()) > 1 or getattr(rot, "rotating", False):
            # a rotor goes through the mosaic EVEN when the config row
            # now says one camera (satellites F2): the hot-plug rotor
            # _rotor keeps alive would take the plain single read below,
            # and RotatingCamera.read has no screen parameter - one
            # TypeError per leased tick, the release/reopen spiral all
            # over again. The mosaic already walks a 1-eye rotor as one
            # labeled tile, so the smaller branch is here, not a second
            # read shape in the single path.
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
        op = self._opener()              # the SAME AsyncOpener the vote
        # path builds (state._cams): one async discipline per seam
        if self.camera is None or not self.camera.is_open():
            if self.camera is not None:
                self._release_camera()   # a present-but-dead handle:
                # the honest release + detector reset before replacing
                # it (also bumps the opener's gen, so a racing worker
                # releases its own fresh handle instead of orphaning)
            indexes = self._indexes()
            self.camera = op.open_async(indexes[0] if indexes else 0)
            if self.camera is None:
                # OPENING, not waiting: the sync hold here was the
                # owner's spiral (a 20-27 s open blocking this very
                # tick: no pin, no lease renewal landing, the next poke
                # killed the open mid-flight and the retry never ended).
                # The background open pins the lease while it lives and
                # publishes under the same grace + tombstone discipline
                # the mosaic's rotor has always used.
                if op.inflight_live(now):
                    self._pin_lease()
                return
        # screen=0: the wall shows whatever the stream serves at lease
        # cadence - screening a preview tile would stall the mosaic
        # (the vote path keeps its 2 s; it runs every 10-60 s)
        frame = self.camera.read(screen=0)
        if frame is None:
            return
        boxes, scores = self.detector.detect(frame)
        self.framebox.put(frame, boxes, scores)

    def _preview_open(self, index):
        """The single-eye desk's AsyncOpener factory: build the one
        camera the current config names (the same _new_camera the old
        sync hold called) and never hand out a corpse - cv2 builds
        silent dead handles rather than raising, so the open is proven
        with is_open() and the corpse released on the spot; the rotor's
        _open does the same for its eyes."""
        try:
            cam = self._new_camera()
        except Exception as err:
            log.info("camera %s will not open (%s); the preview retries "
                     "next tick", index, err)
            return None
        if not cam.is_open():
            cam.release()
            log.info("camera %s will not open; the preview retries next"
                     " tick", index)
            return None
        return cam

    def _pin_lease(self):
        """An open in flight PINS the lease, one renewal at a time: the
        UI heartbeat is gated on the live switch and the window being
        normal, so a 1.5 s lease can expire mid-open and the pre-cooloff
        release would bump the gen - the worker then releases the handle
        it just paid for, an eye slower than the lease never publishes
        (the c97dae5 regression) and the next toggle restarts the driver
        tax (the owner's live spiral). When the workers land or the open
        dies by its grace, the pin stops and the lease expires on its
        own - into the warm window now, not into a reopen."""
        self.preview_until = max(self.preview_until,
                                 time.monotonic() + 1.0)
        if not self._pin_logged:
            self._pin_logged = True
            log.info("preview lease pinned by an open in flight")

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
        still the lease-end _release_camera the single path already
        uses - but a NATURAL lease end now defers it by the cooloff
        window (_boot.PREVIEW_COOLOFF_SEC) so the next toggle attaches
        instead of reopening; a real release still lets go of every
        sub-cam the rotor holds, and _invalidate makes an open that
        outran the window release its own fresh handle."""
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
                # - and the label CARRIES THE AGE ("opening 12s"): a
                # 20 s-old hole reads as dead next to a 1 s-old one,
                # and the owner deserves to tell patience from a hang.
                rot.open_async(index)
                frames[index] = None
                age = rot.inflight_age().get(index)
                labels[index] = ("opening" if age is None
                                 else "opening %ds" % min(int(age), 999))
                continue
            # screen=0: the wall must never stall the lease cadence on
            # an intermittently black stream - screening is the VOTE's
            # medicine, not the mosaic's
            frame = cam.read(screen=0)
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
            tile = _tile_rgb(frame)
            if tile is None:
                # no honest tile exists (a 2-channel depth pin): the
                # eye ABSTAINS - the labeled hole the wall already
                # renders for the cameras it does not hold - and the
                # label says what the frame really is
                frames[index] = None
                labels[index] = "no rgb tile (%s)" % (
                    "x".join(str(s) for s in frame.shape),)
            else:
                frames[index] = tile
                labels[index] = label
        # an open in flight PINS the lease (see _pin_lease): without it
        # a 1.5 s heartbeat lapse kills a slow eye's 20+ s open mid-
        # flight and the spiral begins. When the workers land or the
        # rotor's grace dies, the pin stops and the lease expires on its
        # own.
        if rot.inflight_live(time.monotonic()):
            self._pin_lease()
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
