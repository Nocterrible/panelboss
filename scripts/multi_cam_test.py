"""Multi-camera presence, offline: the rotating adapter, the abstain
currency, and the name matching. No real devices: the camera layer is
patched per index, every frame encodes the index of the camera that
made it, and a fake detector reads that back to decide presence.
"""
import os
import sys
import tempfile
import types as _types

try:
    import tomllib as _t
except ImportError:
    import tomli as _t

sys.path.insert(0, r"F:\Projects\ICU-PresenceDetector")

import numpy as np

from panelboss import camera as cam_mod
from panelboss import config
from panelboss import display
from panelboss.state import PresenceMonitor

# the display calls are stubs for every state-level scenario (the
# unknown_state_test pattern); sent records what would have hit the
# panels
sent = []
display.wake = lambda *a, **k: sent.append("wake")
display.turn_off = lambda *a, **k: sent.append("off")
display.set_hold = lambda *a, **k: None
display.foreground_is_fullscreen = lambda: False

# --------------------------------------------------------------- fakes --
# one fake camera per index: FAKE_OPEN decides which indexes can open
# at all (False = the silent cv2 corpse), PRESENCE decides which of
# the open ones has a person in front of them
FAKE_OPEN = {}
PRESENCE = {}
instances = []


class FakeCam:
    def __init__(self, index=0, warmup=4, width=1280, height=720,
                 verbose=False):
        self.index = index
        self.warmup = warmup
        self.opened = bool(FAKE_OPEN.get(index, True))
        self.frames = 0
        instances.append(self)

    def warm_up(self, frames=None):
        frames = self.warmup if frames is None else frames
        got = 0
        for _ in range(frames):
            if self.read(timeout=2) is not None:
                got += 1
        return got

    def read(self, timeout=3):
        if not self.opened:
            return None
        self.frames += 1
        return np.full((8, 8, 3), self.index + 1, np.uint8)

    def release(self):
        self.opened = False

    def is_open(self):
        return self.opened


class DeadEye:
    """The single eye that dies in warm-up: the open itself looks
    fine (the constructor succeeds) and then the first frame request
    blows up. A raise is a different vote from the all-dead abstain:
    the rotation has live siblings a dead one must never veto, but a
    LONE dead camera has no live one to veto - on the shipped
    single-camera desk its failure is an ABSENT vote (nobody at the
    desk), and it must stay one."""
    def __init__(self, index=0, warmup=4, width=1280, height=720,
                 verbose=False):
        self.index = index

    def warm_up(self, frames=None):
        raise RuntimeError("the eye died in warm-up")

    def read(self, timeout=3):
        return None

    def release(self):
        pass

    def is_open(self):
        return False


class CamDetector:
    """Presence decided by the camera that made the frame: the fake
    knows which one from the encoded pixels."""
    conf = 0.45

    def detect(self, frame, conf=None):
        index = int(frame[0, 0, 0]) - 1
        if PRESENCE.get(index, False):
            return [[0, 0, 8, 8]], np.array([0.9])
        return np.empty((0, 4)), np.empty((0,))


def fresh_monitor(cfg):
    mon = PresenceMonitor(cfg, CamDetector())
    mon._drain_tray = lambda: None    # the tray is not under test
    return mon


def scratch_cfg(index_toml, mode_on="boot_per_poll", mode_off="always_on"):
    d = tempfile.mkdtemp(prefix="panelboss_multi_")
    with open(os.path.join(d, "config.toml"), "w", encoding="utf8") as fh:
        fh.write("[camera]\nindex = %s\nmode_on = \"%s\"\n"
                 "mode_off = \"%s\"\n" % (index_toml, mode_on, mode_off))
    cfg = config.get_config(dir=d, verbose=False)
    cfg["power"]["skip_camera_when_blocked"] = False   # never consult the
    cfg["power"]["assistant_task"] = False             # real powercfg
    cfg["power"]["restore_windows"] = False            # no wm snapshot
    return cfg


class FakeIRCam:
    def __init__(self, group=None, format_output="bgr", timeout=8.0):
        self.opened = True

    @property
    def width(self):
        return 640

    @property
    def height(self):
        return 360

    @property
    def is_opened(self):
        return self.opened

    def read(self, timeout=None):
        return False, None

    def release(self):
        self.opened = False


_fake_ir = _types.ModuleType("whircam")
_fake_ir.IRCam = FakeIRCam
_fake_ir.find_groups = lambda: []

_real_camera = cam_mod.Camera
cam_mod.Camera = FakeCam
try:
    # 1) the rotation: nine cycles visit every index twice over, in
    #    both modes, and the cursor survives the per-poll open/release
    for mode in ("boot_per_poll", "always_on"):
        FAKE_OPEN.clear()
        instances.clear()
        rot = cam_mod.RotatingCamera([0, 1, 2], warmup=1, width=8,
                                     height=8)
        turns = []
        for _ in range(9):
            frame = rot.read(mode=mode)
            assert frame is not None, (mode, rot.last_index)
            turns.append(int(frame[0, 0, 0]) - 1)
        assert turns == [0, 1, 2, 0, 1, 2, 0, 1, 2], (mode, turns)
        rot.release()
        assert not rot.is_open(), (mode, rot.cameras)
    print("rotation OK (nine cycles, both modes, every index visited)")

    # 2) a dead camera abstains on its turn and the cursor still moves
    #    on: the live ones keep voting, and the dead one gets an
    #    honest retry every turn
    FAKE_OPEN.clear()
    FAKE_OPEN.update({0: True, 1: False, 2: True})
    PRESENCE.clear()
    instances.clear()
    rot = cam_mod.RotatingCamera([0, 1, 2], warmup=1, width=8, height=8)
    pattern = []
    for _ in range(9):
        frame = rot.read(mode="always_on")
        pattern.append((rot.last_index, rot.last_opened,
                        None if frame is None
                        else int(frame[0, 0, 0]) - 1))
    rot.release()
    assert [p[0] for p in pattern] == [0, 1, 2] * 3, pattern
    assert [p[1] for p in pattern] == [True, False, True] * 3, pattern
    assert [p[2] for p in pattern] == [0, None, 2] * 3, pattern
    assert len([i for i in instances if i.index == 1]) == 3, \
        "a dead camera gets one open attempt per turn (three turns here)"
    print("abstain OK (dead camera never votes, rotation does not stall)")

    # 3) every camera dead, screens on: forty abstains in a row start
    #    no absence clock, log no absence, and never turn the screens
    #    off - a wall of dead opens is not an empty desk
    FAKE_OPEN.clear()
    FAKE_OPEN.update({0: False, 1: False, 2: False})
    PRESENCE.clear()
    instances.clear()
    sent.clear()
    m = fresh_monitor(scratch_cfg("[0, 1, 2]"))
    m.state = "counting"
    for i in range(40):
        t = 100.0 + 3 * i
        m.next_poll = 0                        # the abstain reschedules
                                               # itself; keep the pace
        m._on_phase(t, idle=90.0)
    assert m.state == "counting", m.state
    assert m.absent_since is None, "abstains must not start the clock"
    assert sent == [], sent
    print("all-dead OK (40 abstains: no clock, no off, no wake)")

    # 4) screens off, camera A dead and B sees a person: the abstains
    #    do not reset the hits, and two B votes wake the desk
    FAKE_OPEN.clear()
    FAKE_OPEN.update({0: False, 1: True, 2: False})
    PRESENCE.clear()
    PRESENCE[1] = True
    instances.clear()
    sent.clear()
    m = fresh_monitor(scratch_cfg("[0, 1, 2]", mode_off="always_on"))
    m.state = "off"
    m.next_poll = 160.0               # as _screens_off would have left it
    m.hits = 0
    for i in range(5):
        m._off_phase(160.0 + 0.2 * i, idle=90.0)
    assert m.state == "counting", m.state
    assert sent == ["wake"], sent
    assert m.hits == 0, "a wake always starts clean"
    print("off-phase wake OK (dead A abstains between the B hits)")

    # 5) screens on, A dead and B sees a person: B alone keeps the
    #    desk confirmed - no absence clock ever starts, no off, and
    #    the abstains never count as negative votes
    sent.clear()
    m = fresh_monitor(scratch_cfg("[0, 1, 2]",
                                  mode_on="boot_per_poll"))
    m.state = "counting"
    for i in range(40):
        t = 100.0 + 3 * i
        m.next_poll = 0
        m._on_phase(t, idle=90.0)
    assert m.state == "counting", m.state
    assert m.absent_since is None
    assert "off" not in sent, sent
    print("on-phase OR OK (B alone holds presence through the A deads)")

    # 6) both cameras live, nobody in front of either: the fail-closed
    #    path still converges - the absence clock runs on real frames
    #    and the screens go dark after the confirm window
    FAKE_OPEN.clear()
    FAKE_OPEN.update({0: True, 1: True})
    PRESENCE.clear()
    instances.clear()
    sent.clear()
    m = fresh_monitor(scratch_cfg("[0, 1]",
                                  mode_on="boot_per_poll",
                                  mode_off="always_on"))
    m.state = "counting"
    off_at = None
    for i in range(25):
        t = 100.0 + 3 * i
        m.next_poll = 0
        m._on_phase(t, idle=90.0)
        if m.state == "off":
            off_at = t
            break
    assert m.state == "off" and off_at is not None, (m.state, sent)
    assert off_at == 100.0 + config.DEFAULTS["timers"]["absent_confirm_sec"], \
        (off_at, "the clock must start on the first real absent frame")
    assert sent[-1] == "off", sent
    print("fail-closed OK (both live, no person: off after %.0f s)"
          % (off_at - 100.0))

    # 7) a single dead eye: ONE index whose camera raises on warm-up.
    #    The raise must vote like the shipped single-camera desk -
    #    an ABSENT (nobody at the desk), fail-closed, screens dark
    #    after the confirm window - NOT the all-dead abstain, which
    #    belongs to the rotation, where a dead camera has live
    #    siblings to let vote and must never veto them. The dark
    #    phase stays honest too: each poll's raise is contained by
    #    _grab and votes absent again, so a dead eye can never wake
    #    the desk. (Off mode boot_per_poll: the off transition
    #    releases rather than holds the camera, so the transition
    #    itself never raises.)
    FAKE_OPEN.clear()
    PRESENCE.clear()
    instances.clear()
    sent.clear()
    m = fresh_monitor(scratch_cfg("0", mode_on="boot_per_poll",
                                  mode_off="boot_per_poll"))
    cam_mod.Camera = DeadEye
    try:
        p, s = m._poll()
        assert (p, s) == (False, 0.0), (p, s)   # the absent vote, not the
                                               # abstain's None
        m.state = "counting"
        off_at = None
        for i in range(25):
            t = 100.0 + 3 * i
            m.next_poll = 0
            m._on_phase(t, idle=90.0)
            if m.state == "off":
                off_at = t
                break
        assert m.state == "off" and off_at is not None, (m.state, sent)
        assert off_at == 100.0 + config.DEFAULTS["timers"]["absent_confirm_sec"], \
            (off_at, "the clock must start on the first absent vote")
        assert sent[-1] == "off", sent
        # the dark desk: the eye keeps dying on every off-phase poll;
        # each raise is contained and votes absent, never a wake
        for i in range(3):
            t = off_at + 3.0 * (i + 1)
            m.next_poll = 0
            m._off_phase(t, idle=90.0)
        assert m.state == "off", m.state
        assert "wake" not in sent, sent
    finally:
        cam_mod.Camera = FakeCam
    print("single dead eye OK (fail-closed preserved, no abstain without a rotor)")

    # 8) config normalization: int, list, empty list, the hello-IR
    #    sentinel, and both name_contains shapes
    assert config.normalize_index(3) == [3]
    assert config.normalize_index([0, 1]) == [0, 1]
    assert config.normalize_index([]) == [0]
    assert config.normalize_index(-2) == [-2]
    assert config.normalize_index([2, 0]) == [2, 0]
    assert config.normalize_index(None) == [0]
    assert config.normalize_name_contains("webcam") == ["webcam"]
    assert config.normalize_name_contains("") == []
    assert config.normalize_name_contains(["a", "b "]) == ["a", "b"]
    assert config.normalize_name_contains(None) == []
    assert config.normalize_name_contains("  ") == []
    print("normalize OK (index and name_contains, both shapes)")

    # 9) the factory: a single index keeps the exact old Camera call,
    #    two indexes are one RotatingCamera, and -2 stays the Hello IR
    #    bridge even when it is spelled as a list
    seen = {}
    cam_mod.Camera = lambda **kw: seen.update(kw) or "CV2"
    try:
        got = cam_mod.open_camera({"index": 3, "warmup_frames": 1,
                                   "width": 800, "height": 600})
        assert got == "CV2" and seen == {"index": 3, "warmup": 1,
                                         "width": 800, "height": 600}, seen
        seen.clear()
        got = cam_mod.open_camera({"index": [3], "warmup_frames": 1,
                                   "width": 800, "height": 600})
        assert got == "CV2" and seen == {"index": 3, "warmup": 1,
                                         "width": 800, "height": 600}, seen
    finally:
        cam_mod.Camera = FakeCam
    got = cam_mod.open_camera({"index": [0, 1], "warmup_frames": 1})
    assert isinstance(got, cam_mod.RotatingCamera)
    assert got.indexes == [0, 1] and got.cursor == 0
    got.release()
    _ir_saved = sys.modules.get("whircam")
    try:
        sys.modules["whircam"] = _fake_ir
        got = cam_mod.open_camera({"index": [-2]})
        assert isinstance(got, cam_mod.HelloIrCamera)
        got.release()
    finally:
        if _ir_saved is not None:
            sys.modules["whircam"] = _ir_saved
        else:
            sys.modules.pop("whircam", None)
    print("factory OK (single int, single list, multi, hello IR)")

    # 10) the on-disk config: an int or a list on disk normalizes on
    #    load, and a rewritten config still parses as valid TOML
    for index_toml, index_want in (("0", [0]), ("[0, 1, 2]", [0, 1, 2])):
        cfg = scratch_cfg(index_toml)
        assert cfg["camera"]["index"] == index_want, cfg["camera"]
        assert cfg["camera"]["name_contains"] == []
        path = config.write_config(cfg, os.path.dirname(cfg["_path"]))
        with open(path, "rb") as fh:
            reread = _t.load(fh)
        assert reread["camera"]["index"] == (
            0 if index_want == [0] else index_want), reread["camera"]
        cfg2 = config.get_config(dir=os.path.dirname(path), verbose=False)
        assert cfg2["camera"]["index"] == index_want
    print("config round-trip OK (int and list on disk both survive)")

    # 11) name_contains resolves against the device tree at open time:
    #     case-insensitive, explicit indexes skip the match, old list
    #     shapes read, and the -1 default-device stays a single camera
    _enum_cache_saved = getattr(cam_mod, "_enum_cache", None)
    _names_saved, _enum_saved = cam_mod.camera_names, cam_mod.enumerate_cameras
    cam_mod._enum_cache = None
    cam_mod.camera_names = lambda: ["Realtek USB 3.0 Webcam",
                                    "HID-compliant IR Camera"]
    cam_mod.enumerate_cameras = lambda start=0, stop=8: [
        (0, True, 640.0), (1, True, 1280.0), (2, False, 0.0),
        (3, True, 640.0)]
    try:
        rot = cam_mod.open_camera({"index": [1], "name_contains": "webcam",
                                   "warmup_frames": 1})
        assert isinstance(rot, cam_mod.RotatingCamera)
        assert rot.indexes == [1, 0], rot.indexes
        rot.release()
        # the only webcam is the explicit one: the match is found,
        # but a listed index is not added twice - stays a single cam
        cam = cam_mod.open_camera({"index": 0, "name_contains": "WEBCAM"})
        assert type(cam) is cam_mod.Camera and cam.index == 0
        cam.release()
        rot = cam_mod.open_camera({"index": [1],
                                   "name_contains": ["Webcam"]})
        assert isinstance(rot, cam_mod.RotatingCamera)
        assert rot.indexes == [1, 0], rot.indexes
        rot.release()
        # -1 means "OpenCV picks the default": a sentinel never gets a
        # name-matched companion, even when one is asked for
        cam = cam_mod.open_camera({"index": -1, "name_contains": "webcam"})
        assert type(cam) is cam_mod.Camera and cam.index == -1
        cam.release()
        assert cam_mod._enum_cache is not None
        cam_mod._enum_cache = None     # a fresh resolve re-enumerates
        rot = cam_mod.open_camera({"index": 1, "name_contains": "webcam"})
        assert rot.indexes == [1, 0]
        rot.release()
    finally:
        cam_mod.camera_names, cam_mod.enumerate_cameras = _names_saved, _enum_saved
        cam_mod._enum_cache = _enum_cache_saved
    print("name_contains OK (case-insensitive, explicit skip, list shape)")

    # 12) the config-load merge: a name_contains in the toml resolves
    #     INTO the index list at get_config time, against the same
    #     device tree the open-time resolve uses, so the roster a
    #     rotation counts is complete BEFORE any camera opens; when
    #     the camera extension is dead the merge fails soft and the
    #     explicit indexes stand alone, config still loads; a
    #     sentinel roster (hello IR -2, default device -1) stays
    #     single-eyed through the load - no name-matched companion,
    #     or the bridge route would silently lose its priority
    FAKE_OPEN.clear()
    _enum_cache_saved = getattr(cam_mod, "_enum_cache", None)
    _names_saved, _enum_saved = cam_mod.camera_names, cam_mod.enumerate_cameras
    d = tempfile.mkdtemp(prefix="panelboss_multi_")
    with open(os.path.join(d, "config.toml"), "w", encoding="utf8") as fh:
        fh.write("[camera]\nindex = [1]\nname_contains = \"webcam\"\n")
    cam_mod._enum_cache = None
    cam_mod.camera_names = lambda: ["Realtek USB 3.0 Webcam",
                                    "HID-compliant IR Camera"]
    cam_mod.enumerate_cameras = lambda start=0, stop=8: [
        (0, True, 640.0), (1, True, 1280.0), (2, False, 0.0),
        (3, True, 640.0)]
    try:
        cfg = config.get_config(dir=d, verbose=False)
        assert cfg["camera"]["index"] == [1, 0], cfg["camera"]
        # a sentinel roster stays single-eyed at load too: hello IR
        # and the default device never take a name-matched second
        # eye. The fake tree DOES hold a match at 0, so a merge that
        # slipped past the guard would come back as [-2, 0] / [-1, 0]
        for sentinel in (-2, -1):
            d2 = tempfile.mkdtemp(prefix="panelboss_multi_")
            with open(os.path.join(d2, "config.toml"), "w",
                      encoding="utf8") as fh:
                fh.write("[camera]\nindex = %d\nname_contains = "
                         "\"webcam\"\n" % sentinel)
            cam_mod._enum_cache = None     # a fresh probe against the
                                           # matching tree, not the cache
            cfgs = config.get_config(dir=d2, verbose=False)
            assert cfgs["camera"]["index"] == [sentinel], \
                (sentinel, cfgs["camera"])
        # the extension dies (cv2 gone): the merge fails soft and the
        # explicit indexes stand untouched - the config still loads
        cam_mod._enum_cache = None   # force the failing probe, not the cache
        cam_mod.camera_names = lambda: (_ for _ in ()).throw(
            RuntimeError("no camera extension today"))
        cfg2 = config.get_config(dir=d, verbose=False)
        assert cfg2["camera"]["index"] == [1], cfg2["camera"]
    finally:
        cam_mod.camera_names, cam_mod.enumerate_cameras = _names_saved, _enum_saved
        cam_mod._enum_cache = _enum_cache_saved
    print("config-load merge OK (names merge into the roster at load; a "
          "dead extension leaves the explicit indexes standing; a "
          "sentinel roster stays single-eyed)")

    print("ALL MULTI-CAMERA TESTS OK")
finally:
    cam_mod.Camera = _real_camera
