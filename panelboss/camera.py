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

from . import config

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
                             capture_output=True, timeout=10,
                             # windowless parents get a FRESH VISIBLE
                             # console for every console-app child:
                             # without this flag each scan and each
                             # tray-menu rebuild popped a powershell
                             # window (the user counted them)
                             creationflags=subprocess.CREATE_NO_WINDOW)
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
    name_contains = config.normalize_name_contains(name_contains)
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


def open_camera(cam_cfg, policy=None):
    """The one way to get a camera. Index -2 is the Hello IR bridge;
    a single index is the old cv2 path with the old arguments; several
    indexes are one RotatingCamera (one camera votes per poll,
    round-robin). Name matching is resolved HERE, at open time, not at
    config load: the device tree can change under a long-running app,
    and a fresh probe is the only honest answer. `policy` (optional) is
    a per-index vote policy - a callable index->mode or an
    index->mode dict - consulted by the rotating vote at read time, so
    the caller can change it (display state, degradation) without
    rebuilding the rotor."""
    indexes = config.normalize_index(cam_cfg.get("index", 0))
    names = config.normalize_name_contains(cam_cfg.get("name_contains"))
    if indexes == [HELLO_IR]:
        return HelloIrCamera(warmup=cam_cfg.get("warmup_frames", 4))
    if names and all(i >= 0 for i in indexes):
        # sentinels (-1 default, -2 IR) mean "this one device"; a name
        # match never drags a second eye next to them
        indexes = _extend_by_name(indexes, names)
    warmup = cam_cfg.get("warmup_frames", 4)
    width = cam_cfg.get("width", 1280)
    height = cam_cfg.get("height", 720)
    if len(indexes) == 1:
        return Camera(index=indexes[0],
                      warmup=warmup,
                      width=width,
                      height=height)
    return RotatingCamera(indexes, warmup=warmup,
                          width=width, height=height,
                          policy=policy)


class Camera:
    """One open device. Kept alive between polls when configured so, or
    booted per poll to let the LED rest."""

    rotating = False

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


_enum_cache = None       # (monotonic, {index: name}); the tree changes
                         # slowly and PnP + a probe round is not cheap


def _device_tree(max_index=8):
    """index -> best name we have for it. PnP order is assumed to match
    the OpenCV indexes (the same assumption find_camera has always
    made); a probe label covers the devices PnP does not list. Cached
    about a minute per process: a rotation rebuild is not worth a
    fresh PnP spin every time."""
    global _enum_cache
    now = time.monotonic()
    if _enum_cache is not None and now - _enum_cache[0] < 60:
        return _enum_cache[1]
    tree = {i: n for i, n in enumerate(camera_names())}
    for index, _opened, _width in enumerate_cameras(0, max_index):
        if index not in tree:
            tree[index] = "camera %d" % index
    _enum_cache = (now, tree)
    return tree


def _probe(index):
    """Is this index openable right now? Built through the module
    Camera so a test can swap in a fake; in production this is the
    same one-shot open the real Camera does."""
    cam = Camera(index=index)
    try:
        return cam.is_open()
    finally:
        cam.release()


def _extend_by_name(indexes, substrings):
    """Openable indexes whose names contain any of the substrings
    (case-insensitive), in device order. Explicit indexes always stay
    first; a match the user already listed is not added twice."""
    tree = _device_tree()
    extra = []
    for index in sorted(tree):
        if index in indexes:
            continue
        name = tree[index].lower()
        if any(s.lower() in name for s in substrings):
            if _probe(index):
                extra.append(index)
    return list(indexes) + extra


class RotatingCamera:
    """One camera at a time, a rotating vote. The desk has several eyes
    on it; per poll exactly one of them votes (round-robin) and the
    frame it returns is the frame the detector sees. A camera that
    cannot open, or opens but stalls, ABSTAINS on its turn: a dead eye
    can never veto a live one, and a wall of dead opens never looks
    like an empty desk.

    An optional per-index `policy` (callable index->mode, or an
    index->mode dict) decides, per eye, whether it votes at all this
    display state: "off" eyes are skipped by the walk (they can still
    be opened by a preview lease, they just never vote), "always_on"
    eyes stay open between polls, "boot_per_poll" eyes open, vote,
    release. The policy is consulted at read/open time, so the caller
    may change it - a display-state flip, an always_on degradation -
    without rebuilding the rotor."""

    rotating = True

    def __init__(self, indexes, warmup=4, width=1280, height=720,
                 verbose=False, policy=None):
        self.indexes = [int(i) for i in indexes]
        self.cursor = 0                  # whose turn is next
        self.warmup = warmup
        self.width = width
        self.height = height
        self.cameras = {}                # index -> held sub-camera; the
                                         # always_on mode keeps them open
                                         # between polls
        self.policy = policy             # per-index mode source, or None
                                         # (one mode for the whole rotor)
        self.last_index = None           # the camera that last voted
        self.last_opened = False         # True only when that vote came
                                         # with a frame
        self.started = time.perf_counter()

    def _mode_for(self, index, mode):
        """This index's vote mode right now. No policy: the single mode
        the caller passed (the old whole-rotor behavior). Callable:
        the caller's live view of the desk. Dict: the table value,
        falling back to the caller's mode for an index the table does
        not list."""
        if self.policy is None:
            return mode
        if callable(self.policy):
            return self.policy(index)
        return self.policy.get(index, mode)

    def _open(self, index):
        """One sub-camera, or None when it will not open. cv2 usually
        does not raise on a bad index - it builds a silent corpse - so
        the open is proven with is_opened() and the corpse released on
        the spot; a driver that DOES raise is the same verdict. That
        is what makes a dead camera abstain on its turn instead of
        eating the whole read timeout, or wedging the rotation."""
        try:
            cam = Camera(index=index,
                         warmup=self.warmup,
                         width=self.width,
                         height=self.height)
        except Exception as err:
            log.info("camera %s will not open (%s); it abstains on its"
                     " turns", index, err)
            return None
        if not cam.is_open():
            cam.release()
            log.info("camera %s will not open; it abstains on its turns",
                     index)
            return None
        return cam

    def warm_up(self, frames=None):
        """Settle the auto-exposure of ONE camera only: the one whose
        turn is next. Opening all of them here would cost N x the open
        time right at the standby transition, and the open that is
        proven safe is the one issued AFTER the panels are dark; the
        rest settle on their own turns. With a per-index policy the
        look-ahead skips "off" eyes, and only an always_on eye is
        pre-opened here - a boot_per_poll eye's one open belongs to
        its own vote and must not be left lying open."""
        n = len(self.indexes)
        if self.policy is None:
            index = self.indexes[self.cursor % n]
        else:
            index = None
            for step in range(n):
                candidate = self.indexes[(self.cursor + step) % n]
                if self._mode_for(candidate, "always_on") != "off":
                    index = candidate
                    break
            if index is None:
                return 0
            if self._mode_for(index, "always_on") != "always_on":
                return 0
        cam = self.cameras.get(index)
        if cam is None or not cam.is_open():
            cam = self._open(index)
            self.cameras[index] = cam
        if cam is None:
            return 0
        frames = self.warmup if frames is None else frames
        got = 0
        for _ in range(frames):
            if cam.read(timeout=2) is not None:
                got += 1
        return got

    def read(self, mode="always_on", timeout=3):
        """One frame from one camera, or an abstain (None). The cursor
        moves at the END of the cycle, so a warm_up() that pre-opened
        the cursor's camera finds it open and ready, and the next
        cycle is already the next camera's turn. With a per-index
        policy, "off" eyes are skipped by the walk (they never vote,
        though a preview lease may still open one) and a cycle in
        which every eye is off abstains outright."""
        n = len(self.indexes)
        index = None
        for _ in range(n):
            candidate = self.indexes[self.cursor % n]
            if self._mode_for(candidate, mode) != "off":
                index = candidate
                break
            self.cursor = (self.cursor + 1) % n
        if index is None:
            # every eye is switched off for this display state: there
            # is simply no vote to cast this cycle
            self.last_index = None
            self.last_opened = False
            return None
        mode = self._mode_for(index, mode)
        if mode == "boot_per_poll":
            cam = self._open(index)
            frame = None
            if cam is not None:
                cam.warm_up()
                frame = cam.read(timeout=timeout)
                cam.release()           # the LED rests; the user
                # can always notice the blink
        else:
            cam = self.cameras.get(index)
            if cam is None or not cam.is_open():
                cam = self._open(index)
                self.cameras[index] = cam
            frame = None
            if cam is not None:
                frame = cam.read(timeout=timeout)
                if frame is None:
                    # a handle that stopped flowing IS a dead handle,
                    # whatever is_open() swears; release the corpse
                    cam.release()
                    self.cameras[index] = None
        # in a rotation any cycle without a frame - an open that
        # failed, an open that stalled - is an abstain: the desk has
        # several eyes and this one simply could not look
        self.last_index = index
        self.last_opened = frame is not None
        self.cursor = (self.cursor + 1) % n
        return frame

    def release(self):
        for cam in self.cameras.values():
            if cam is not None:
                cam.release()
        self.cameras.clear()

    def is_open(self):
        return any(cam is not None and cam.is_open()
                   for cam in self.cameras.values())
