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

SIZE LAW: ~730 lines, grandfathered - Camera (device+warmup) and the
Rotor (rotation+async opens) share the module-level _open_lock and the
enumeration cache; splitting now buys two files that must re-declare
that shared state. The known seam paid its first dividend Oct 12: the
async-open lifecycle came out of the Rotor into AsyncOpener, shared
with the single-camera preview lease (the owner's reopen spiral hit both
seams). Rotor+camera basics remain the split candidates.
"""

from __future__ import annotations

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
        publish lock; see the class docstring)."""
        t0 = time.monotonic()
        try:
            cam = self._factory(index)
            if cam is not None:
                try:
                    cam.warm_up()      # settled frames or an honest
                except Exception:      # hole: an unwarmed eye reads
                    pass               # dark and lies (gate finding 3)
        except Exception:
            cam = None
        me = threading.current_thread()
        with self.lock:
            job = self.inflight.get(index)
            mine = job is not None and job.thread is me
            if mine:
                self.inflight.pop(index, None)   # my row ends with me
            stale = (not mine or self.gen != gen
                     or time.monotonic() >= deadline)
            if cam is not None and not stale:
                self._store(index, cam)
        if cam is None:
            return                     # the factory logged the abstain
        if stale:
            cam.release()
            log.info("camera %d open went stale; released its own handle",
                     index)
        else:
            log.info("camera %d open published after %.1f s",
                     index, time.monotonic() - t0)

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
        grace tombstones too - a new lease gets a fresh chance at an
        eye this lease gave up on."""
        with self.lock:
            self.gen += 1
            self.dropped.clear()

    def rearm(self):
        """Attach-time amnesty: clear the grace tombstones WITHOUT the
        gen bump, so in-flight opens survive the warm window's re-attach
        (gate finding 2: attach preserved the tombstones, blinding the
        attached lease - an eye dropped at grace could never retry until
        a real release landed)."""
        with self.lock:
            self.dropped.clear()


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

    def rearm(self):
        self._opener.rearm()             # attach-time tombstone amnesty

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
