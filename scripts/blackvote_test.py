"""The black-frame doctrine, offline: a vote frame whose brightest
pixel is under camera.BLACK_CEIL carries no light, and no light
carries no verdict (owner doctrine Oct 12: absence of evidence is NOT
evidence of absence - another app holding the sensor, the owner's
NVIDIA Broadcast during work calls, and a genuinely dark room are
indistinguishable and both mean "cannot see", never "empty desk").
The fixture pattern is camera_policy_test's (fake clock, the patched
cam_mod.Camera seam); the log-capture pattern is asyncopen_test's.
Scenarios: A the single blinded eye abstains and confesses the
blind/seeing edges exactly once each; B (the headline) a permanently
black eye can no longer cap a live sibling's presence streak - the
shape that slept the owner's screens on an occupied desk; C an
all-blind desk confirms NOTHING (no absence clock ever starts).
F/G/H (Oct 12 screening): F a stream that lights up inside the 2 s
budget is no longer ignored at the start; G a screened-out black eye
abstains and confesses but never joins the round; H the preview's
screen=0 opt-out keeps the mosaic's cadence. SIZE LAW: ~450 lines
justified - one FakeCam/queue-cap scaffold shared by every scenario;
splitting the blocks buys N files that each re-declare it.
"""
import logging
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from panelboss import camera as cam_mod
from panelboss import config
from panelboss import display
import panelboss.state as state_mod

sent = []
display.wake = lambda *a, **k: sent.append("wake")
display.turn_off = lambda *a, **k: sent.append("off")
display.set_hold = lambda *a, **k: None
display.foreground_is_fullscreen = lambda: False

recs = []


class Grab(logging.Handler):
    def emit(self, record):
        recs.append(record.getMessage())


logging.basicConfig(level=logging.INFO)
_h = Grab()
logging.getLogger("state").addHandler(_h)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t

    def perf_counter(self):
        return self.t

    def sleep(self, s):
        self.t += s


clock = Clock()
state_mod.time = clock

BLACK = {}         # index -> the eye serves the black hole
PRESENCE = {}      # index -> the bright frame carries a person


class FakeCam:
    """Two frame shapes: BLACK serves the all-zero hole (what
    Broadcast hands out mid-call), a normal eye serves bright gray
    (max 128+ > BLACK_CEIL) encoding its index for the fake
    detector."""

    def __init__(self, index=0, warmup=4, width=1280, height=720,
                 verbose=False):
        self.index = index

    def warm_up(self, frames=None):
        for _ in range(1 if frames is None else frames):
            self.read(timeout=2)
        return 1

    def read(self, timeout=3):
        if BLACK.get(self.index, False):
            return np.zeros((720, 1280, 3), np.uint8)
        return np.full((8, 8, 3), 128 + self.index, np.uint8)

    def release(self):
        pass

    def is_open(self):
        return True


class Det:
    conf = 0.45

    def detect(self, frame, conf=None):
        if PRESENCE.get(int(frame[0, 0, 0]) - 128, False):
            return [[0, 0, 8, 8]], np.array([0.9])
        return np.empty((0, 4)), np.empty((0,))


_real_camera = cam_mod.Camera
cam_mod.Camera = FakeCam


def fresh_monitor(cfg):
    mon = state_mod.PresenceMonitor(cfg, Det())
    mon._drain_tray = lambda: None    # the tray is not under test
    return mon


def drain_vote(m):
    """Join the background opens the VOTE path spawned (the
    camera_policy_test seam): tick 1 spawns and abstains, tick 2
    votes - this suite needs votes NOW."""
    for op in (getattr(m, "_single_opener", None),
               getattr(getattr(m, "camera", None), "_opener", None)):
        if op is None:
            continue
        while True:
            with op.lock:
                th = [j.thread for j in list(op.inflight.values())
                      if j is not None and j.thread.is_alive()]
            if not th:
                break
            th[0].join(10)


def scratch_cfg(camera_toml):
    d = tempfile.mkdtemp(prefix="panelboss_blackvote_")
    with open(os.path.join(d, "config.toml"), "w", encoding="utf8") as fh:
        fh.write("[camera]\n" + camera_toml)
    cfg = config.get_config(dir=d, verbose=False)
    cfg["power"]["skip_camera_when_blocked"] = False   # never consult
    cfg["power"]["assistant_task"] = False             # the real
    cfg["power"]["restore_windows"] = False            # powercfg / wm
    return cfg


def n_blind():
    return sum("serving black" in m for m in recs)


def n_back():
    return sum("frames came back" in m for m in recs)


# a black-served device that OPENS: the fake cv2 the real door and the
# real Camera run against in scenario E (gate finding 1: prove the
# blinded eye's frame reaches _poll's abstain branch THROUGH the door,
# not just through a patched Camera). Every cv2 surface the open path
# touches is here; the frames are always black.
class _BlackCap:
    def __init__(self, *a, **k):
        pass

    def set(self, *a):
        pass

    def get(self, prop):
        return {cam_mod.cv2.CAP_PROP_FRAME_WIDTH: 1280,
                cam_mod.cv2.CAP_PROP_FRAME_HEIGHT: 720}.get(prop, 0)

    def isOpened(self):
        return True

    def read(self):
        return True, np.zeros((720, 1280, 3), np.uint8)

    def release(self):
        pass


class _FakeCv2:
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_PROP_FOURCC = 6
    CAP_DSHOW = 700

    class VideoWriter:
        @staticmethod
        def fourcc(*c):
            return 0

    VideoCapture = _BlackCap


try:
    # ---- A) the single blinded eye: abstain, not absent; and the
    # transition confessions fire exactly once per edge
    BLACK[2] = True
    m = fresh_monitor(scratch_cfg('index = 2\nmode_on = "boot_per_poll"\n'))
    m.state = "counting"
    p, s = m._poll()                 # tick 1: the eye opens, plain abstain
    assert (p, s) == (None, 0.0)
    drain_vote(m)
    p, s = m._poll()                 # the black hole serves its lie
    assert p is None and s == 0.0, (p, s)   # EXACTLY (None, 0.0): the
    # black frame is (False, 0.0)'s corpse - busy-and-died votes absent,
    # a blinded eye has no verdict at all
    slot = m.framebox.get()
    assert slot is not None and len(slot[1]) == 0 and slot[0].max() == 0, \
        "the debug view keeps the black truth: the frame, zero boxes"
    assert n_blind() == 1, "the first blind vote confesses, once"
    assert n_back() == 0
    drain_vote(m)
    m._poll()                        # reopen, abstain
    drain_vote(m)
    m._poll()                        # second blind vote
    assert n_blind() == 1, "the second blind vote says nothing new"
    BLACK[2] = False
    PRESENCE[2] = True
    drain_vote(m)
    m._poll()                        # reopen, abstain
    drain_vote(m)
    p, s = m._poll()                 # Broadcast let go: the vote returns
    assert p is True and s == 0.9, (p, s)
    assert n_back() == 1, "the recovery confesses, once"
    slot = m.framebox.get()
    assert len(slot[1]) == 1 and slot[0].max() == 130, \
        "the bright frame and its box reach the wall again"
    print("black abstain OK (blind = (None, 0.0), wall honest, "
          "blind/back edges each log exactly once)")

    # ---- B) THE HEADLINE: the reset bug is dead. Eye 3 permanently
    # blind, eye 4 permanently sees the owner; before the doctrine eye
    # 3's confident ABSENT zeroed the streak every other turn (hits
    # capped at 1, min_hits=2 unreachable, the desk slept on the
    # owner's own presence). Oct 12 (vote async): the rotor's open
    # cycles push the wake past four RAW polls (opening eyes abstain,
    # as multi_cam block 4 already documents); the guarantee asserted
    # is the SHAPE - hits strictly rise on every eye-4 turn and never
    # fall on an eye-3 turn - with the wake landing inside the window.
    BLACK[3] = True
    BLACK[4] = False
    PRESENCE[4] = True
    cfg = scratch_cfg('index = [3, 4]\nmode_on = "boot_per_poll"\n'
                      'mode_off = "boot_per_poll"\n')
    cfg["inference"]["min_hits"] = 2
    m = fresh_monitor(cfg)
    m.state = "off"
    m.hits = 0
    m.absent_since = None
    seen = []                        # (voter, hits) per turn, for the
    woke = False                     # failure message
    for i in range(10):
        m.next_poll = 0.0            # as _screens_off would have left it
        before = m.hits
        m._off_phase(clock.t + i, idle=90.0)
        drain_vote(m)
        if m.state != "off":
            # the wake: eye 4's second vote (only it can vote True
            # here), and _wake released the rotor on the spot
            assert before + 1 == cfg["inference"]["min_hits"], seen
            seen.append((4, before + 1))
            woke = True
            break
        rot = m.camera
        voter = getattr(rot, "last_index", None) if rot is not None else None
        # THE HEADLINE ASSERT: no turn ever reset the streak - the
        # blind eye's confident ABSENT (which forced hits to 0 and
        # capped it at 1) is dead
        assert m.hits >= before, ("the blind eye reset the streak - the "
                                  "old bug", seen)
        if m.hits > before:
            assert voter == 4, ("the blind eye voted present", seen)
            seen.append((voter, m.hits))
    assert woke and [h for (v, h) in seen] == [1, 2], \
        seen                             # strictly rising on eye-4 turns
    assert m.state == "counting" and sent == ["wake"], \
        (m.state, sent, seen)        # the desk reached the present side
    print("streak OK (a permanently blind sibling no longer caps the "
          "live eye: %s -> wake)" % ([h for (v, h) in seen],))

    # ---- C) an all-blind desk CONFIRMS NOTHING: several counting
    # turns, and the absence clock never starts (the off-timer feed is
    # the False vote; a blind eye never casts one)
    BLACK[2] = True
    PRESENCE[2] = False
    sent.clear()
    m = fresh_monitor(scratch_cfg('index = 2\nmode_on = "boot_per_poll"\n'))
    m.state = "counting"
    for i in range(6):
        m.next_poll = 0.0
        m._on_phase(clock.t + 3 * i, idle=90.0)
        drain_vote(m)
    assert m.absent_since is None, "a blind eye started the absence clock"
    assert m.state == "counting" and "off" not in sent
    assert not any("nobody at the desk" in r for r in recs), \
        "no absence was ever confirmed"
    print("all-blind OK (the black eye feeds no off-timer: no clock, "
          "no confirmation, no dark panels)")

    # ---- E) (gate finding 1, evidence) the blinded frame REACHES the
    # vote through the real door, on the real Camera: _delivers judges
    # DSHOW opened-but-dark (b099bcf's contract, unchanged), the auto
    # door adopts it on bare isOpened(), and the black frame it serves
    # abstains at _poll - the doctrine holds end to end, not just
    # around a patched Camera. (The owner's Broadcast eye rode exactly
    # this path live at 12:20: "camera 0 open published after 38.5 s"
    # after "DSHOW opened but served black".)
    _cv = cam_mod.cv2
    _bd_saved = dict(cam_mod._bad_doors)
    cam_mod.cv2 = _FakeCv2
    cam_mod._bad_doors.clear()
    cam_mod.Camera = _real_camera        # the whole real open path now
    try:
        with cam_mod._open_lock:             # the door's stated contract
            cap, door = cam_mod._open_door(5, 1280, 720)
        assert door == "auto" and cap.isOpened(), \
            "the blinded DSHOW hole must fall back to an adopted auto cap"
        assert (5, 1280, 720) in cam_mod._bad_doors, \
            "_delivers must still tombstone the opened-but-dark DSHOW"
        m = fresh_monitor(scratch_cfg('index = 5\n'
                                      'mode_on = "boot_per_poll"\n'))
        m.state = "counting"
        BLACK[5] = False                 # FakeCam is out of the way:
        PRESENCE[5] = False              # the auto cap serves black
        m._poll()                        # tick 1 spawns the real open
        drain_vote(m)
        p, s = m._poll()                 # tick 2 votes the black frame
        assert (p, s) == (None, 0.0), \
            "the frame that lived through the door must abstain, not " \
            "vote absent, at the vote too"
    finally:
        cam_mod.cv2 = _cv
        cam_mod._bad_doors.clear()
        cam_mod._bad_doors.update(_bd_saved)
        cam_mod.Camera = FakeCam
    print("door-to-vote OK (a black-serving auto cap is adopted, its "
          "frame reaches _poll and abstains: finding 1 answered)")

    # ---- F/G/H) the Oct 12 screening (owner: "take a 2 second sample
    # ... feed anything bright to the model"): a stream that lights up
    # inside the window is NOT a blind eye. The scaffolding below is a
    # queue fake under the REAL Camera methods; the scenarios share it.
    import time as wall
    _cam_recs = []

    class CamGrab(logging.Handler):
        def emit(self, record):
            _cam_recs.append(record.getMessage())

    logging.getLogger("camera").addHandler(CamGrab())

    _BLACK8 = np.zeros((8, 8, 3), np.uint8)
    SEQ = {}           # index -> ([queued frames], tail kind), read by
                       # _ScreenCam's cap - the dict idiom the BLACK/
                       # PRESENCE maps above already speak

    class _SeqCap:
        """cv2-cap shaped queue: serves the queued frames, then the
        tail (bright gray encoding the index, or the black hole)."""

        def __init__(self, frames, tail):
            self.frames = list(frames)
            self.tail = tail

        def read(self):
            if self.frames:
                return True, self.frames.pop(0)
            return True, self.tail

        def isOpened(self):
            return True

        def set(self, *a):
            pass

        def get(self, prop):
            return {3: 1280, 4: 720}.get(prop, 0)

        def release(self):
            pass

    class _ScreenCam(_real_camera):
        """The REAL warm_up/read screening over a queue cap; __init__
        replaces the door (scenario E already proved the door), so the
        blacks reach the screening untouched by _delivers' consumption."""

        def __init__(self, index=0, warmup=4, width=1280, height=720,
                     verbose=False):
            self.index = index
            self.warmup = warmup
            self.started = wall.perf_counter()
            frames, kind = SEQ.get(index, ([], "bright"))
            tail = (_BLACK8 if kind == "black"
                    else np.full((8, 8, 3), 128 + index, np.uint8))
            self.cap = _SeqCap(frames, tail)

    cam_mod.Camera = _ScreenCam

    # ---- F) STARTUP BLACK, the fix's headline: the same device that
    # served black on one open and bright minutes later (the owner's
    # intermittent-cam measurement). black, black, bright -> warm_up
    # eats the blacks, the handle confesses the intermittence EXACTLY
    # once, and the next _poll votes PRESENT with a score - the eye is
    # no longer ignored at the start.
    SEQ[8] = ([_BLACK8, _BLACK8], "bright")
    PRESENCE[8] = True
    cam = _ScreenCam(index=8)
    assert cam.warm_up() > 0, "the blacks are consumed INSIDE warm_up"
    assert sum("intermittently black: 2 black frames" in r
               for r in _cam_recs) == 1, _cam_recs
    m = fresh_monitor(scratch_cfg('index = 8\nmode_on = "always_on"\n'))
    m.state = "counting"
    _cam_recs.clear()                  # the monitor's handle confesses
    p, s = m._poll()                   # its own once; watch that one
    assert (p, s) == (None, 0.0)       # tick 1: the eye opens
    drain_vote(m)                      # warm_up screens the blacks
    p, s = m._poll()                   # the vote AFTER screening
    assert p is True and s == 0.9, (p, s)
    assert sum("intermittently black" in r for r in _cam_recs) == 1, \
        _cam_recs                      # once per handle, not per frame
    print("startup screening OK (black, black, bright: warm_up ate the "
          "blacks, INFO once, the first vote PRESENT - no longer "
          "ignored at the start)")

    # ---- G) screened-out black: an eye that stays blind loses the
    # argument, not the doctrine - read returns the black frame when
    # the window closes, _poll abstains (None, 0.0), _note_vote still
    # confesses it, and the abstaining eye still never joins the round
    # (gate-fix-2).
    SEQ[6] = ([], "black")
    cam = _ScreenCam(index=6)
    t0 = wall.perf_counter()
    frame = cam.read(timeout=3, screen=0.2)
    dt = wall.perf_counter() - t0
    assert frame is not None and int(frame.max()) < cam_mod.BLACK_CEIL, \
        "budget exhausted on all-black returns the black frame anyway"
    assert 0.15 <= dt <= 1.5, dt       # the window closed, it did not
                                       # run the old 3 s deadline
    _ss = cam_mod.SCREEN_SEC
    cam_mod.SCREEN_SEC = 0.2           # the scenario's screen knob
    try:
        m = fresh_monitor(scratch_cfg('index = 6\n'
                                      'mode_on = "boot_per_poll"\n'))
        m.state = "counting"
        m._poll()
        drain_vote(m)                  # the worker's warm_up screens
        blind0 = n_blind()             # out on black first
        p, s = m._poll()               # the blind vote, post-screening
        assert (p, s) == (None, 0.0), (p, s)
        assert n_blind() == blind0 + 1, \
            "the screened-out eye still confesses through _note_vote"
        assert m.absent_since is None, \
            "the abstaining eye still never joins the round"
    finally:
        cam_mod.SCREEN_SEC = _ss
    print("screened-out black OK (black frame returned after the "
          "window, abstain + confession intact, no round, no absence "
          "clock)")

    # ---- H) the preview opt-out: screen=0 is the mosaic's cadence
    # promise - a lying (black) stream must not stall the wall tick.
    cam = _ScreenCam(index=6)          # SEQ[6] still serves black only
    t0 = wall.perf_counter()
    frame = cam.read(timeout=3, screen=0)
    dt = wall.perf_counter() - t0
    assert frame is not None and int(frame.max()) < cam_mod.BLACK_CEIL
    assert dt < 0.05, dt               # the budget was never touched
    print("preview opt-out OK (screen=0 on a black stream returns in "
          "%.0f ms: the mosaic keeps its cadence even when the stream "
          "lies)" % (dt * 1000,))

    print("BLACK VOTE TEST OK")
finally:
    cam_mod.Camera = _real_camera
