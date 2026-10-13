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

SIZE LAW: ~1000 lines, grandfathered - Camera (device+warmup) and the
Rotor (rotation+async opens) share the module-level _open_lock and the
enumeration cache; splitting now buys two files that must re-declare
that shared state. The known seam paid its first dividend Oct 12: the
async-open lifecycle came out of the Rotor into AsyncOpener, shared
with the single-camera preview lease (the owner's reopen spiral hit both
seams). Rotor+camera basics remain the split candidates.
"""

from __future__ import annotations

from contextlib import contextmanager

import json
import logging
import subprocess
import threading
import time

import cv2

from . import config

log = logging.getLogger("camera")

# an open in flight may pin the preview lease (and with it the LED),
# but only this long: the worst real open measured was 38 s, so this
# is double that and then some; a slow eye must not pin forever
OPEN_GRACE_SEC = 90

# a slow driver OPEN is not a reason for the whole subsystem to wedge:
# the NVIDIA driver's measured open window is 16-27 s (38 s for one
# enumeration), so a 30 s deadline sits just above it - a healthy open
# still lands, but a hung holder (a dead driver that grabs the lock and
# never lets go) stops blocking every other poll forever. Every
# acquisition of _open_lock now runs through _open_timed and ABSTAINS
# (returns the caller's None/busy shape, never raises, never blocks the
# loop) when the deadline passes instead of queuing behind the hang.
OPEN_LOCK_TIMEOUT = 30.0

# the NVIDIA virtual camera driver dies when two threads open devices
# at the same time (measured: interprocess mutex timeout, then OpenCV
# raises a C++ exception); every open and every enumerate goes through
# this lock, so at most one thread touches the device tree
_open_lock = threading.RLock()


@contextmanager
def _open_timed():
    """_open_lock with a deadline. Yields True when the lock was
    acquired, False when OPEN_LOCK_TIMEOUT passed first (the holder is
    a hung driver open): the caller abstains that tick - it never
    raises and never blocks the poll loop behind the holder. A single
    thread re-acquires (RLock) so an open that holds the lock and then
    releases the cap it just opened does not self-deadlock; the
    deadline guards only the cross-thread case where a DIFFERENT thread
    is wedged in a slow open and this one would queue behind it."""
    got = _open_lock.acquire(timeout=OPEN_LOCK_TIMEOUT)
    if not got:
        log.warning("camera open locked past %ds; skipping this round",
                    int(OPEN_LOCK_TIMEOUT))
        yield False
    else:
        try:
            yield True
        finally:
            _open_lock.release()

BLACK_CEIL = 16      # a frame whose brightest pixel is below this is
                     # evidence of "cannot see", never of "empty desk"
                     # (owner doctrine Oct 12; _delivers and the vote
                     # path share the number so the two verdicts can
                     # never drift apart)

SCREEN_SEC = 2.0     # the black-screening budget: a stream that
                     # serves black is re-read until this window
                     # closes before we call the eye blind (owner:
                     # "take a 2 second sample... feed anything
                     # bright to the model"). The budget only pays
                     # when black actually happens: a bright frame
                     # short-circuits at the first read.


def _set_props(cap, width, height):
    if width:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)


def _delivers(cap, patience=2.0):
    """Opened AND serving bright pixels. DSHOW grew a black-hole mode
    on this machine's cam0 at 1280x720 (measured Oct 12): isOpened True
    forever, frames black forever - the very silent-ignorance shape an
    unproven open is made of. A door that opens but delivers nothing
    is a dead door. The cost of the check is bounded: 4 frames inside
    the patience window (a fast stream answers in ~0.1 s, the black
    hole answers in ~one patience); a legitimately dark room trips the
    same fallback and just lands on the auto door - today's behavior,
    never worse."""
    if not cap.isOpened():
        return False
    deadline = time.monotonic() + patience
    for _ in range(4):
        if time.monotonic() >= deadline:
            break
        try:
            ok, frame = cap.read()
        except Exception:               # this driver family raises C++
            return False                # errors through cv2 (documented
            # above); a cap whose read raises delivers nothing by
            # definition - the verdict is the door's, not an exception
            # for the tray menu to swallow
        if ok and int(frame.max()) >= BLACK_CEIL:
            return True
    return False


_bad_doors = {}         # (index, w, h) -> monotonic of the last DSHOW
                        # attempt that OPENED but served black: the
                        # black-hole open poisons the following MF open
                        # too (measured 18.7 s inside the app vs 6 s
                        # alone), so re-paying it every poll would make
                        # DSHOW-first a net loss on this box. A door
                        # watched dying is not retried for a minute -
                        # same cache philosophy (and same slow-tree
                        # excuse) as _enum_cache below.


def _open_door(index, width=None, height=None):
    """(cap, door) for one index. DSHOW first; the auto door only as
    the fallback. The auto backend tries Media Foundation FIRST and MF
    is poisoned on this box by a zombie NVIDIA vcam plugin: it fails on
    every device after ~6 s of interprocess mutex timeout (measured
    Oct 12); DSHOW opens the same device in 0.6 s and never touches MF.
    The auto door is therefore the ONLY place MSMF is ever tried, and
    the fallback is per-index: an MSMF-only device on a mixed desk
    still opens, paying MF's slowness - that's the device, not the
    app. width/height, when given, are set on EVERY door tried before
    the live-frame verdict, so a mode that only one backend survives
    (the black hole above) still routes to the door that delivers.
    May return a not-opened cap (same shape as VideoCapture's);
    callers must already hold _open_lock."""
    key = (index, width, height)
    dead = _bad_doors.get(key)
    if dead is None or time.monotonic() - dead >= 60:
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        _set_props(cap, width, height)
        if _delivers(cap):
            return cap, "dshow"
        black = cap.isOpened()          # the opened-and-dark verdict
        if black and width:
            # the black hole has a classic cause: UVC streams HD in
            # MJPEG, and DSHOW's uncompressed default at that size
            # opens-and-lies. FOURCC AFTER open is too late for the
            # DSHOW graph (measured: the set is accepted, the hole
            # stays); the codec must ride the OPEN parameters, like
            # the Windows Camera app's graph does.
            cap.release()
            cap = cv2.VideoCapture(
                index, cv2.CAP_DSHOW,
                [cv2.CAP_PROP_FOURCC,
                 cv2.VideoWriter.fourcc(*"MJPG"),
                 cv2.CAP_PROP_FRAME_WIDTH, int(width),
                 cv2.CAP_PROP_FRAME_HEIGHT, int(height)])
            if _delivers(cap):
                return cap, "dshow/mjpg"
        if black or cap.isOpened():     # tombstone the VERDICT, not
            # the last object: the first cap's opened-dark counts even
            # when the MJPG retry could not open (driver busy) - the
            # poison it inflates (measured MF 6 -> 18 s) is the reason
            # the tombstone exists at all (gate finding 1).
            _bad_doors[key] = time.monotonic()
            log.info("camera %d@%sx%s: DSHOW opened but served black;"
                     " auto door for a minute", index,
                     width or "default", height or "")
        cap.release()
    started = time.perf_counter()
    cap = cv2.VideoCapture(index)          # the auto door: MSMF et al.
    _set_props(cap, width, height)
    if cap.isOpened():
        log.info("camera %d: the DSHOW door did not deliver, fell back"
                 " to the auto door (%.1f s)", index,
                 time.perf_counter() - started)
    return cap, "auto"


def camera_devices():
    """[{name, instance, status}] - every PnP camera, one query. The
    InstanceId is the identity the wizard keys labels and hides on:
    friendly names collide across identical models and OpenCV indexes
    DRIFT on replugs (measured Oct 12: roster [6,1] -> [6,1,0,2] ->
    [0,2]); the instance path is pinned to the device. -Compress keeps
    the payload ONE JSON document, so commas and spaces in names
    cannot break a line-split parse; a lone device arrives unwrapped.
    CREATE_NO_WINDOW is mandatory: a windowless parent gets a fresh
    VISIBLE console per console-app child (camera_names' successor of
    the powershell-window incident - the user counted them)."""
    cmd = ("(Get-PnpDevice -Class Camera | Select-Object "
           "FriendlyName,InstanceId,Status | ConvertTo-Json -Compress)")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                             capture_output=True, timeout=10,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            text = out.stdout.decode("utf-8")
        except UnicodeDecodeError:               # the console encoding is
            text = out.stdout.decode(            # never utf-16, whatever
                "cp850", errors="replace")       # the driver claims
        data = json.loads(text) if text.strip() else []
    except Exception:
        return []                              # dead engine, no names,
    if isinstance(data, dict):                 # or error prose where
        data = [data]                          # JSON should have been
    return [{"name": str(d.get("FriendlyName") or "").strip(),
             "instance": str(d.get("InstanceId") or "").strip(),
             "status": str(d.get("Status") or "").strip()}
            for d in data if isinstance(d, dict)]


def camera_names():
    """Friendly names via PnP (the names of camera_devices(), same
    order). Enum order does not necessarily match the OpenCV indexes;
    it is used for reporting and the optional name_contains match
    only."""
    return [d["name"] for d in camera_devices() if d["name"]]


def enumerate_cameras(start=0, stop=8):
    """Which indexes can be opened at all. Probed through the same
    DSHOW-first door the real opens use, so a picker index always means
    the device the opener will open: the DSHOW tree is the source of
    truth, and an index only the auto door opens keeps its auto-door
    meaning because Camera falls back to auto FOR THAT INDEX ONLY.
    Such an index is logged ("MSMF-only; slow door") and still pays
    MF's slowness - the device's cost, not the app's."""
    found = []
    for index in range(start, stop):
        with _open_timed() as got:       # one open at a time, but with a
            if not got:                  # deadline: a hung holder must not
                found.append((index, False, 0.0))
                continue                 # wedge the enumeration forever;
                # the row takes the dead-probe shape (an unopened cap
                # reports 0.0 too - cli.py:int() would frown at None)
            cap, door = _open_door(index)
            opened = cap.isOpened()
            width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            cap.release()
        if opened and door == "auto":
            # honest confession: could be a true MSMF-only device OR
            # one the default-size DSHOW probe could not serve (the
            # HD-MJPG-only case); the open at the real configured
            # size will retry the codec door anyway
            log.info("index %d opened through the auto door only;"
                     " slow door", index)
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
        with _open_timed() as got:       # one open at a time, but with a
            if not got:                  # deadline: a hung holder must not
                continue                 # wedge the whole find forever
            cap, _door = _open_door(idx)
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
        with _open_timed() as got:     # open timing varies wildly; the
            # deadline keeps a hung open from wedging every other
            # acquire (audit MED); on timeout the abstain is the
            # not-opened shape: is_open() False, the caller's corpse
            # arm releases the husk and retries next tick
            if not got:
                self._cam = None
                self.warmup = warmup
                self.width = 0
                self.height = 0
                return
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

    def read(self, timeout=3, screen=None):
        # NOTE (Oct 12 screening): this read keeps its own shape - the
        # pump's timeout semantics differ from the cv2 stream's - it
        # just ACCEPTS the screen kwarg so the preview seam's uniform
        # screen=0 opt-out cannot TypeError on an IR desk. No screening
        # here: the bridge either has a frame or it does not.
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
        self.cap = None
        # the driver hates concurrent opens: lock the device tree - but
        # with the deadline (audit MED: the unbounded acquire turned ONE
        # hung open into a whole-subsystem wedge). A locked round is the
        # documented not-opened shape, the same corpse _open_door can
        # already return: is_open() is False, the caller's corpse arm
        # releases it and retries next tick. Never raise, never block.
        with _open_timed() as got:
            if not got:
                self.width = 0
                self.height = 0
                return
            self.cap, _door = _open_door(index, width, height)
            self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        elapsed = time.perf_counter() - self.started
        log.debug("camera %s opened after %.2f s", index, elapsed)

    def _read_raw(self):
        """one frame from the cap, no screening, exception-honest
        (the zombie-driver shape _delivers already guards)."""
        try:
            ok, frame = self.cap.read()
        except Exception:
            return None
        return frame if ok else None

    def warm_up(self, frames=None):
        """Discard the auto-exposure settle frames - screened
        through: a stream that starts black (AE settle, MJPEG
        keyframe wait) gets SCREEN_SEC of re-reads BEFORE the handle
        is published, so the AsyncOpener worker never hands the vote
        a black-headed stream. Once lit (or screened out), finish
        discarding the warmup frames - a bright stream's behavior and
        count are the old ones."""
        frames = self.warmup if frames is None else frames
        blacks = 0
        first = None
        screen_until = time.monotonic() + SCREEN_SEC
        while first is None and time.monotonic() < screen_until:
            frame = self._read_raw()
            if frame is not None:
                if int(frame.max()) >= BLACK_CEIL:
                    first = frame
                else:
                    blacks += 1
            if first is None:
                time.sleep(0.03)
        if blacks and not getattr(self, "_screen_logged", False):
            self._screen_logged = True
            log.info("camera %d stream intermittently black: "
                     "%d black frames screened in %.1f s",
                     self.index, blacks,
                     time.perf_counter() - self.started)
        got = 1 if first is not None else 0
        for _ in range(max(frames - got, 0)):
            if self._read_raw() is not None:
                got += 1
        return got

    def read(self, timeout=3, screen=None):
        """One frame. A BLACK frame (the stream intermittently dark -
        AE settle, MJPEG keyframe wait, KVM USB jitter - or a genuinely
        dark room) is screened through: keep sampling while the screen
        budget lasts; the first BRIGHT frame wins. Budget exhausted on
        all-black = return the black frame anyway (the caller's abstain
        doctrine then applies - blind AFTER screening is an honest
        verdict, blind on first sight was the bug). screen=0 opts out
        (the preview tiles: a human decides what black means, and the
        mosaic must never stall the lease cadence)."""
        screen = SCREEN_SEC if screen is None else screen
        deadline = time.monotonic() + timeout
        screen_until = (time.monotonic() + min(screen, timeout)
                        if screen else 0.0)
        last = None
        blacks = 0
        while True:
            frame = self._read_raw()
            if frame is not None:
                last = frame
                if int(frame.max()) >= BLACK_CEIL:
                    if blacks and not getattr(self, "_screen_logged",
                                              False):
                        self._screen_logged = True
                        log.info("camera %d stream intermittently "
                                 "black: %d black frames screened in "
                                 "%.1f s", self.index, blacks,
                                 time.perf_counter() - self.started)
                    return frame
                blacks += 1
            if time.monotonic() >= (screen_until if last is None or
                                    blacks else deadline):
                break
            time.sleep(0.03)
        return last

    def release(self):
        """Lock-free ownership (W3A, gate 2a/2b/2c). WHY no lock:
        every release CALLER lives on the monitor loop thread
        (state._cams._release_camera is loop-owned; the quit-path
        exception is fixed by the cli handoff), and concurrent-open
        protection is the OPEN's job - the opener already self-releases
        corpses via gen-bump invalidation, one layer down. The old
        shape queued release() behind the AsyncOpener's 16-27 s open on
        the same deadlined lock (stalling the exact windows the opener
        exists to avoid) and, on a skipped lock, DROPPED the handle:
        the "next release() retries" was a lie - CPython's destructor
        runs cv2's release unlocked anyway.
        """
        cap, self.cap = self.cap, None   # TAKE ownership first: one owner
        if cap is not None:              # releases - the null-first swap
            cap.release()                # is the race fix (gate 2b) and
                                         # the one-owner law (F3), no lock
                                         # needed: the attribute swap is
                                         # atomic under the GIL

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


class _OpenJob:
    """One row of AsyncOpener.inflight: the worker, its grace deadline
    (time.monotonic, absolute), the window it was granted (for an
    honest confession line whatever the deadline came from), the
    monotonic it was registered at (so an "opening" tile can age: 20 s
    into a slow open reads differently than 1 s in), and whether that
    deadline's confession was already logged. Mutable so inflight_live()
    can flip logged_stale under the very lock the worker publishes
    under."""
    __slots__ = ("thread", "deadline", "grace", "logged_stale",
                 "registered")

    def __init__(self, thread, deadline, grace, registered):
        self.thread = thread
        self.deadline = deadline
        self.grace = grace
        self.logged_stale = False
        self.registered = registered


class AsyncOpener:
    """The background-open lifecycle, factored out of RotatingCamera so
    the two preview-lease seams share ONE async discipline: the rotor's
    per-index registry (publishing into the caller's cameras dict via
    lookup/store) and the single-camera desk's registry (publishing into
    this object's own held dict, which the tick re-reads every poll).
    The owner's live spiral proved the block-on-open design wrong for
    BOTH seams: a 20-27 s driver open, released mid-flight by the next
    toggle, restarted from zero and died again - forever.

    One worker thread per index. The registration carries a grace
    deadline (OPEN_GRACE_SEC, or the caller's absolute monotonic
    override - the probes lean on it) and a generation stamp. The
    worker runs the factory, warms the result, and publishes under the
    very lock invalidate() uses, so a concurrent release can neither
    miss a handle about to be published nor be missed: a lease that
    ended mid-open makes this thread release the handle it just paid
    for - no orphan LED. Three ways to be stale: the gen moved, the
    deadline passed, or the row is no longer mine - dropping a row (not
    bumping gen) is how the engine abandons ONE open without invalidating
    its siblings'. A deadline-dropped eye is tombstoned until
    invalidate(): the respawn would re-pin the lease forever (gate
    finding 1). A failed open records nothing: the next tick retries,
    exactly as the old synchronous block retried, and the factory
    already logged the abstain."""

    def __init__(self, factory, lookup=None, store=None):
        # factory(index) -> opened camera or None (None = declined; the
        # factory logs its own honest abstain)
        self._factory = factory
        self.held = {}                 # index -> published camera: the
                                       # default store, what the
                                       # single-camera seam reads back
        if lookup is None:
            lookup = self.held.get
        if store is None:
            store = self.held.__setitem__
        self._lookup = lookup          # the rotor passes its cameras
        self._store = store            # dict, so votes see the publishes
        self.inflight = {}             # index -> _OpenJob
        self.dropped = set()           # indices past grace: no respawn
                                       # until the next invalidate()
        self.failed = set()            # indices whose LAST attempt died
                                       # at the open: the VOTE reads
                                       # this to keep the single desk's
                                       # shipped fail-closed contract -
                                       # a dead open is not an opening
                                       # eye (publish clears it)
        self.gen = 0                   # invalidate() bumps it: every
                                       # open still in flight goes STALE
        self.lock = threading.Lock()

    def open_async(self, index, deadline=None):
        """A live handle now, or a background open and None for this
        tick. The tick must never block on a slow driver (a 38 s
        enumeration was measured), so the eye that is not open yet opens
        on its own thread and the caller labels it "opening" until it
        lands."""
        cam = self._lookup(index)
        if cam is not None and cam.is_open():
            return cam
        if deadline is None:
            deadline = time.monotonic() + OPEN_GRACE_SEC
        with self.lock:
            cam = self._lookup(index)
            if cam is not None and cam.is_open():
                return cam
            if index in self.dropped:
                return None            # grace already ran THIS lease:
                                       # no respawn, no fresh pin
            if self.inflight.get(index) is not None:
                return None            # an open for this eye is running
            gen = self.gen
            now = time.monotonic()
            th = threading.Thread(target=self._bg,
                                  args=(index, gen, deadline),
                                  daemon=True, name="cam-open-%s" % index)
            self.inflight[index] = _OpenJob(th, deadline,
                                            deadline - now, now)
        log.info("camera %d opening in background", index)
        try:
            th.start()
        except Exception:              # thread exhaustion (or a policy
            with self.lock:            # refusal): the registration must
                self.inflight.pop(index, None)   # not strand the eye
            raise                      # "opening" with no worker
        return None

    def _bg(self, index, gen, deadline):
        """open_async's worker: factory, warm up, and only THEN decide
        whether the handle is still wanted (the stale checks share the
        publish lock; see the class docstring). The factory is wrapped
        in BaseException, not Exception: cv2's C++ raise paths can
        surface an error a bare except misses, and a worker that dies
        on one leaves its inflight row "opening" FOREVER - every later
        tick then waits on a dead eye. The row is reaped in a finally
        so a dying worker clears its own opening flag, and the
        BaseException is re-raised AFTER the reap so the daemon still
        dies honestly instead of swallowing a SystemExit."""
        t0 = time.monotonic()
        cam = None
        fatal = None
        try:
            cam = self._factory(index)
            if cam is not None:
                try:
                    cam.warm_up()      # settled frames or an honest
                except Exception:      # hole: an unwarmed eye reads
                    pass               # dark and lies (gate finding 3)
        except Exception:              # the open DIED at the factory:
            cam = None                 # the old shape, the abstain
            # already logged, the row reaped by the publish block below
        except BaseException as err:   # the gap around cv2's C++ raise
            fatal = err                # paths (audit MED): a worker that
            cam = None                 # dies on this must still reap its
                                       # own row - an inflight row left
                                       # behind reads "opening" forever
                                       # and every later tick queues on
                                       # an eye that will never publish
        me = threading.current_thread()
        try:
            with self.lock:
                job = self.inflight.get(index)
                mine = job is not None and job.thread is me
                if mine:
                    self.inflight.pop(index, None)   # my row ends with me
                stale = (not mine or self.gen != gen
                         or time.monotonic() >= deadline)
                if cam is not None and not stale:
                    self._store(index, cam)
                    self.failed.discard(index)       # the eye lives again
                elif cam is None and mine:
                    self.failed.add(index)           # the open DIED at the
                    # factory: the next vote can tell a dead eye from an
                    # opening one (the single desk keeps its fail-closed
                    # vote; a replaced row belongs to whoever replaced it)
            if cam is not None:
                if stale:
                    cam.release()
                    log.info("camera %d open went stale; released its own"
                             " handle", index)
                else:
                    log.info("camera %d open published after %.1f s",
                             index, time.monotonic() - t0)
        finally:
            if fatal is not None:     # a BaseException still propagates:
                raise fatal            # the daemon dies, but only after its
                                       # opening flag has been reaped

    def inflight_live(self, now=None):
        """True while any registered worker is still alive AND inside
        its grace deadline - the preview lease's pinning question. A row
        whose deadline passed is dropped with exactly ONE confession per
        index; the thread may linger in the driver, but its publish will
        find itself de-registered and release its own handle. A row
        whose thread died without publishing is cleaned silently."""
        if now is None:
            now = time.monotonic()
        live = False
        with self.lock:
            for index, job in list(self.inflight.items()):
                if job.thread.is_alive() and now < job.deadline:
                    live = True
                    continue
                self.inflight.pop(index, None)
                if now >= job.deadline and not job.logged_stale:
                    job.logged_stale = True
                    self.dropped.add(index)  # the drop is final THIS
                    log.info("camera %d open exceeded %.1f s grace; "
                             "dropping", index, job.grace)  # lease: the
        return live                           # respawn would re-pin
                                              # forever (gate finding 1)

    def inflight_age(self, now=None):
        """Seconds since registration, per still-living row: the mosaic
        puts the elapsed into the label - an "opening" tile that is 20 s
        old reads as dead next to one that is 1 s old."""
        if now is None:
            now = time.monotonic()
        with self.lock:
            return {index: max(0.0, now - job.registered)
                    for index, job in self.inflight.items()
                    if job.thread.is_alive()}

    def invalidate(self):
        """Make every open still in flight stale: whoever finishes from
        here on releases its own fresh handle and drops it. Clears the
        grace tombstones AND the failed-open record too - a new lease
        gets a fresh chance at an eye this lease gave up on."""
        with self.lock:
            self.gen += 1
            self.dropped.clear()
            self.failed.clear()

    def rearm(self, index=None):
        """Attach-time amnesty: clear the grace tombstones WITHOUT the
        gen bump, so in-flight opens survive the warm window's re-attach
        (gate finding 2: attach preserved the tombstones, blinding the
        attached lease - an eye dropped at grace could never retry until
        a real release landed). index=... : a VOTED eye surrenders only
        its own tombstone (gate LOW: whole-set here let a sibling's
        vote respawn a grace-dropped eye's pin loop - the loop the
        tombstone exists to end); None = amnesty for all (lease attach)."""
        with self.lock:
            if index is None:
                self.dropped.clear()
            else:
                self.dropped.discard(index)

    def evict(self, index):
        """Forget ONE eye's row and let go of its handle, under the
        publish lock: the VOTE's boot_per_poll arm hands a landed
        handle back the moment it has read it (the LED still blinks
        every vote) so the next open_async spawns a FRESH open - one
        open-read-release per vote, the exact old synchronous promise,
        just never on the loop thread. The store keeps a None row (the
        shape the engine's own dead-handle arms already write). An
        in-flight worker for the same eye is de-registered the same
        way: it finds its row gone, calls itself stale, and releases
        its own handle - orphan-LED discipline, scoped to one eye."""
        with self.lock:
            cam = self._lookup(index)
            if cam is not None:
                self._store(index, None)
            self.inflight.pop(index, None)
        if cam is not None:
            cam.release()


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
    release - the open and the warm ride the AsyncOpener's worker
    thread (Oct 12), so a slow driver never blocks the vote loop. The
    policy is consulted at read/open time, so the caller
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
        # the preview lease's async-open seam: ONE shared lifecycle (see
        # AsyncOpener) drives this rotor's per-index registry, publishing
        # into the same cameras dict the vote reads
        self._opener = AsyncOpener(self._open, lookup=self.cameras.get,
                                   store=self.cameras.__setitem__)

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

    # The async-open machinery lives in AsyncOpener (shared with the
    # single-camera preview lease - the owner's spiral hit both seams).
    # These delegates keep the rotor's call sites unchanged; the
    # properties keep the internals under the names the probes have
    # always poked.
    @property
    def _inflight(self):
        return self._opener.inflight

    @property
    def _dropped(self):
        return self._opener.dropped

    @property
    def _gen(self):
        return self._opener.gen

    @property
    def _async_lock(self):
        return self._opener.lock

    def open_async(self, index, deadline=None):
        """The preview lease's seam: a live handle now, or a background
        open and None for this tick. The tick must never block on a
        slow driver (a 38 s enumeration was measured), so the eye that
        is not open yet opens on its own thread and the mosaic labels
        it "opening" until it lands. The open itself is the SAME _open
        the vote calls, so the driver sees the same serialised opens -
        only the tick's wait is gone. The registration's grace deadline
        lets the lease pin itself while a row is live, so a slow eye
        must not pin the LED forever through its own zombie open."""
        return self._opener.open_async(index, deadline)

    def inflight_live(self, now=None):
        """True while any registered worker is alive and inside its
        grace deadline - the preview lease's pinning question."""
        return self._opener.inflight_live(now)

    def inflight_age(self, now=None):
        """index -> seconds since registration, for the "opening Ns"
        tile label."""
        return self._opener.inflight_age(now)

    def _invalidate(self):
        self._opener.invalidate()

    def rearm(self, index=None):
        self._opener.rearm(index)        # tombstone amnesty (scoped)

    # the _inflight/_dropped/_gen/_async_lock shims below are READ-ONLY
    # properties (gate nit): pokes may MUTATE the returned objects but
    # cannot REBIND them - by design, so no probe can fork the identity
    # of the lock or the dict the worker publishes under.

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
        which every eye is off abstains outright. EVERY open rides
        the AsyncOpener now (Oct 12): an eye that is not open yet
        opens on the worker thread and the cycle abstains - the eye
        is opening, not dead - because the synchronous open here was
        the owner's complaint (17.4 s of driver tax measured ON the
        vote thread). The always_on eye that has a live handle votes
        with it and keeps it; the boot_per_poll eye reads its landed
        handle and hands it straight back (evict): one
        open-read-release per vote, the LED blinks every vote."""
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
        cam = self._opener.open_async(index)
        frame = None
        if cam is None:
            if index in self._opener.dropped:
                self._opener.rearm(index)  # the VOTE retries like the old
            # synchronous boot did: the no-respawn tombstone guards the
            # preview lease from its own re-pin loop, and a vote never
            # pins anything - an eye that once blew its grace must not
            # go permanently blind on a desk that only votes
            log.debug("eye %s still opening; abstain", index)
        elif mode == "boot_per_poll":
            try:
                frame = cam.read(timeout=timeout)
            finally:
                self._opener.evict(index)   # the LED rests; the user
            # can always notice the blink
        else:
            frame = cam.read(timeout=timeout)
            if frame is None:
                # a handle that stopped flowing IS a dead handle,
                # whatever is_open() swears; evict (release + drop the
                # row) so the next vote opens a fresh one
                self._opener.evict(index)
        # in a rotation any cycle without a frame - an eye still
        # opening, an open that failed, an open that stalled - is an
        # abstain: the desk has several eyes and this one simply could
        # not look
        self.last_index = index
        self.last_opened = frame is not None
        self.cursor = (self.cursor + 1) % n
        return frame

    def release(self):
        self._invalidate()               # FIRST: an open still in
        # flight must release its own fresh handle - a lease that dies
        # mid-open leaves no orphan LED behind.
        for cam in list(self.cameras.values()):
            if cam is not None:
                cam.release()
        self.cameras.clear()

    def is_open(self):
        return any(cam is not None and cam.is_open()
                   for cam in self.cameras.values())
