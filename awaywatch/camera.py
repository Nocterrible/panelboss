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
