"""Webcam handling.

- find_camera: prefers name_contains, then index, then the first device
  that opens (the config index always comes after the name match)
- warmup: auto-exposure starts as soon as the device opens; we discard the
  first frames so the detector never sees a half-dark image
- modes: boot-per-poll while the screens are on (the record LED blinks so
  you can always notice something watching the camera), held open between
  polls while the screens are dark - and the held stream rides THROUGH the
  standby transition: an open issued DURING the panels' sleep can come
  back open-yet-frozen forever (measured), so we never close across it,
  and any handle that stops delivering frames is released and reopened
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time

import cv2

log = logging.getLogger("camera")

# the NVIDIA virtual camera driver dies when two threads open devices
# at the same time (measured: interprocess mutex timeout, then OpenCV
# raises a C++ exception); every open and every enumerate goes through
# this lock, so at most one thread touches the device tree
_open_lock = threading.RLock()


def camera_names():
    """Friendly names via PnP. Enum order does not necessarily match the
    OpenCV indexes; it is used for reporting and the optional name_contains
    match only."""
    cmd = ("(Get-PnpDevice -Class Camera).FriendlyName")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                              capture_output=True, timeout=10)
        try:
            names = out.stdout.decode("utf-8").splitlines()
        except UnicodeDecodeError:               # the console encoding is
            names = out.stdout.decode("cp850",   # never utf-16, whatever
                errors="replace").splitlines()     # the driver claims
    except Exception:
        return []
    return [n.strip().rstrip(",") for n in names if n.strip()]


def enumerate_cameras(start=0, stop=8):
    """Which indexes can be opened at all."""
    found = []
    for index in range(start, stop):
        with _open_lock:                 # one open at a time, always
            cap = cv2.VideoCapture(index)
            opened = cap.isOpened()
            width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            cap.release()
        found.append((index, opened, width))
    return found


def find_camera(index=-1, name_contains=None, fallback=0):
    """Returns the first usable index. names beat indexes beat fallback."""
    name_contains = name_contains or []
    names = camera_names()
    indexes = [i for i, opened, _ in enumerate_cameras() if opened]
    # apply name matcher
    if name_contains:
        matches = [n for n in names
                   if any(c.lower() in n.lower() for c in name_contains)]
        if matches:
            idx = names.index(matches[0])
            indexes.insert(0, idx)
    if index is not None and index >= 0:
        indexes.insert(0, index)   # the config index comes second
    indexes.append(fallback)       # and we always fall back to something
    for idx in indexes:
        with _open_lock:                 # one open at a time, always
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                cap.release()
                log.debug(f"camera {idx} opens cleanly")
                return idx
    raise RuntimeError("no camera opened; check privacy settings")


HELLO_IR = -2                  # the [camera] index sentinel selecting the
                               # Windows Hello IR sensor via the optional
                               # whircam bridge (WinRT MediaFrameSourceGroup:
                               # Hello cameras hide from plain enumeration
                               # behind driver flags, but the sensor opens
                               # SharedReadOnly even while Hello stays armed)


def optional_present(package):
    """Is an optional dependency (whircam today, others later) present
    in this venv? find_spec answers WITHOUT importing it - the whole
    point is that the feature is about to ask for what is not there."""
    import importlib.util
    return importlib.util.find_spec(package) is not None


_ir_names_cache = None


def hello_ir_names():
    """Display names of IR-capable camera groups; [] when whircam is not
    installed or the platform has none. The result is cached for the
    process: the tray rebuilds its menu on every right click and this
    spins up WinRT enumeration (~1 s) exactly once."""
    global _ir_names_cache
    if _ir_names_cache is None:
        try:
            import whircam
            _ir_names_cache = [g.name for g in whircam.find_groups()]
        except Exception:
            _ir_names_cache = []      # no bridge, no groups, no driver:
        log.debug("hello IR groups: %s", _ir_names_cache)   # all the same
    return _ir_names_cache


class HelloIrCamera:
    """Camera-compatible adapter over the optional whircam bridge.

    Frames arrive as 3-channel BGR (grayscale under near-IR illumination)
    so both detectors keep their contract; the pump thread belongs to
    whircam, release() is what retires it. read() maps whircam's pump
    crash onto the SAME currency the state machine already speaks: a
    None frame releases the handle and the next poll opens a fresh one."""

    def __init__(self, group=None, warmup=4, timeout=8.0, verbose=False):
        try:
            import whircam
        except ImportError as exc:
            raise RuntimeError("the hello IR camera needs the optional "
                               "whircam package: pip install whircam") \
                from exc
        with _open_lock:                 # open timing varies wildly; the
            self._cam = whircam.IRCam(group=group,   # lock at least keeps
                                      format_output="bgr",   # the device
                                      timeout=timeout)         # tree sane
        self.warmup = warmup
        self.width = int(self._cam.width)
        self.height = int(self._cam.height)
        log.info("hello IR camera open (group=%s, %dx%d)",
                 group or "auto", self.width, self.height)

    def warm_up(self, frames=None):
        frames = self.warmup if frames is None else frames
        got = 0
        for _ in range(frames):
            if self.read(timeout=2) is not None:
                got += 1
        return got

    def read(self, timeout=3):
        try:
            ok, frame = self._cam.read(timeout=timeout)
        except RuntimeError:            # pump crashed mid-poll: dead
            return None                 # handle, same as a cv2 stall
        return frame if ok else None

    def release(self):
        if getattr(self, "_cam", None) is not None:
            try:
                self._cam.release()
            except Exception:
                pass                    # release is a courtesy call; the
                                        # handle is ours to forget anyway
            self._cam = None

    def is_open(self):
        cam = getattr(self, "_cam", None)
        return cam is not None and bool(cam.is_opened)


def open_camera(cam_cfg):
    """The one way to get a camera. index -2 is the Hello IR bridge;
    everything else is the old cv2 path with the old arguments."""
    index = cam_cfg.get("index", 0)
    if index == HELLO_IR:
        return HelloIrCamera(warmup=cam_cfg.get("warmup_frames", 4))
    return Camera(index=index,
                  warmup=cam_cfg.get("warmup_frames", 4),
                  width=cam_cfg.get("width", 1280),
                  height=cam_cfg.get("height", 720))


class Camera:
    """One open device. Kept alive between polls when configured so, or
    booted per poll to let the LED rest."""

    def __init__(self, index=0, warmup=4, width=1280, height=720,
                 verbose=False):
        self.index = index
        self.warmup = warmup
        self.started = time.perf_counter()
        with _open_lock:                 # the driver hates concurrent
            self.cap = cv2.VideoCapture(index)   # opens: lock the whole
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)   # device tree
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        elapsed = time.perf_counter() - self.started
        log.debug("camera %s opened after %.2f s", index, elapsed)

    def warm_up(self, frames=None):
        """Discard the auto-exposure settle frames."""
        frames = self.warmup if frames is None else frames
        got = 0
        for _ in range(frames):
            ok, _frame = self.cap.read()
            if ok:
                got += 1
        return got

    def read(self, timeout=3):
        """One frame, or None when the device died mid-poll."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ok, frame = self.cap.read()
            if ok:
                return frame
            time.sleep(0.05)
        return None

    def release(self):
        if self.cap is not None:
            # ask even a never-opened or open-yet-frozen cap to let go;
            # cv2 handles all three without complaint
            self.cap.release()

    def is_open(self):
        return self.cap is not None and self.cap.isOpened()
