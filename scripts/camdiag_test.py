"""Camera diagnostic, offline: the config record, the state round-trip,
and the picker's pure pieces. No real camera, no window: the state side
rides camera_policy_test's FakeCam fixture the way camid_test does, and
the wizard-side tests drive the importable helpers directly. Section 6
drives the REAL scan worker on live threads against faked driver doors.
SIZE LAW: ~424 - one scenario chain per section, the fleet's test idiom
(camera_policy_test is the precedent); the chain is the reader.
"""
import os
import sys
import tempfile
import threading
import time
import types
import queue

try:
    import tomllib
except ModuleNotFoundError:                # the config.py fallback:
    import tomli as tomllib                 # pre-3.11 venvs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# the scratch config dir BEFORE the config import: the state handler
# writes through write_config, which lands on CONFIG_DIR
SCRATCH = tempfile.mkdtemp(prefix="panelboss_camdiag_")
os.environ["PANELBOSS_CONFIG_DIR"] = SCRATCH

import numpy as np

from panelboss import camera as cam_mod
from panelboss import config
from panelboss import display
from panelboss.ui.window import _camid
import panelboss.state as state_mod

# the IR rows come from the optional bridge's live enumeration: the
# offline suite fixes that oracle to absent (deterministic core)
cam_mod.optional_present = lambda pkg: False
cam_mod.hello_ir_names = lambda: []

display.wake = lambda *a, **k: None
display.turn_off = lambda *a, **k: None
display.set_hold = lambda *a, **k: None
display.foreground_is_fullscreen = lambda: False


class Clock:
    def __init__(self):
        self.t = 1000.0

    def time(self):
        # the state fanout (state/__init__ _StatePackage) rebinds the
        # time name in EVERY part, and the camera_diag branch is now a
        # time.time() call site: the fixture answers like the module
        # it replaces, or the drain dies on the fake
        return self.t

    def monotonic(self):
        return self.t

    def perf_counter(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeCam:
    def __init__(self, index=0, warmup=4, width=1280, height=720,
                 verbose=False):
        self.index = index
        self.opened = True

    def warm_up(self, frames=None):
        return 1

    def read(self, timeout=3, screen=None):
        return np.full((8, 8, 3), 128 + self.index, np.uint8)

    def release(self):
        self.opened = False

    def is_open(self):
        return self.opened


class Det:
    conf = 0.45

    def detect(self, frame, conf=None):
        return np.empty((0, 4)), np.empty((0,))


# 1) config migration: an old file without camera.diag reads with the
#    stock empty table, exactly the way bindings landed (no migration
#    code by design - the absent key reads {})
d2 = tempfile.mkdtemp(prefix="panelboss_camdiag_old_")
with open(os.path.join(d2, "config.toml"), "w", encoding="utf8") as fh:
    fh.write("[camera]\nindex = 6\n")
old = config.get_config(dir=d2, verbose=False)
assert old["camera"].get("diag") == {}, old["camera"].get("diag")
print("migration OK (absent camera.diag reads as the stock empty table)")


# 2) the state side: camera_diag lands in the live cfg AND the toml
#    (state owns the write, the UI never edits it); a junk record
#    (a string where ints belong) degrades to {}-plus-at harmlessly
def _monitor():
    m = state_mod.PresenceMonitor(cfg, Det())
    m.ui_events = queue.Queue()
    return m


with open(os.path.join(SCRATCH, "config.toml"), "w", encoding="utf8") as fh:
    fh.write("[camera]\nindex = 6\n")
cfg = config.get_config(dir=SCRATCH, verbose=False)
_real_camera = cam_mod.Camera
cam_mod.Camera = FakeCam
try:
    m = _monitor()
    clock = Clock()
    state_mod.time = clock                   # the record's at stamp
    m.events.put(("camera_diag", {"indices": [0, 2], "noimg": [2]}))
    m._drain_tray()
    diag = cfg["camera"].get("diag") or {}
    assert diag.get("indices") == [0, 2], diag
    assert diag.get("noimg") == [2], diag
    assert diag.get("at", 0) > 0, diag
    on_disk = tomllib.load(open(os.path.join(SCRATCH, "config.toml"), "rb"))
    assert on_disk["camera"]["diag"]["indices"] == [0, 2]
    assert on_disk["camera"]["diag"]["noimg"] == [2]
    back = config.get_config(dir=SCRATCH, verbose=False)
    assert back["camera"]["diag"].get("indices") == [0, 2]
    assert back["camera"]["diag"].get("noimg") == [2]     # round trip
    # the junk arm: the lists must be ints, a string is no record
    # ({}-plus-at: no indices/noimg keys at all, so the picker stays
    # silent and the next scan re-sweeps - harm is silence, harmlessness
    # is the absence)
    m.events.put(("camera_diag", {"indices": [0, "x"], "noimg": ["y"]}))
    m._drain_tray()
    diag = cfg["camera"].get("diag") or {}
    assert "indices" not in diag and "noimg" not in diag, diag
    assert diag.get("at", 0) > 0, diag
    # (b) amendment 2: the show verb - the per-device door. Un-hide
    # AND mark shown, through the loop-owned toml; idempotent on a
    # double click (the shown list is a set, not a counter)
    m.events.put(("camera_identity", {"instance": "USB\\BACK",
                                      "hide": True}))
    m._drain_tray()
    assert cfg["camera"]["hidden"] == ["USB\\BACK"]
    m.events.put(("camera_identity", {"instance": "USB\\BACK",
                                      "show": True}))
    m._drain_tray()
    assert cfg["camera"]["hidden"] == []            # the door opened
    assert cfg["camera"]["shown"] == ["USB\\BACK"]  # the decision stuck
    m.events.put(("camera_identity", {"instance": "USB\\BACK",
                                      "show": True}))
    m._drain_tray()
    assert cfg["camera"]["shown"] == ["USB\\BACK"]  # idempotent
    assert tomllib.load(open(os.path.join(SCRATCH, "config.toml"),
                             "rb"))["camera"]["shown"] == ["USB\\BACK"]
    assert config.get_config(dir=SCRATCH,            # sticky through
                             verbose=False)["camera"]["shown"] \
        == ["USB\\BACK"]                             # the disk
finally:
    cam_mod.Camera = _real_camera
print("identity event OK (diag stored as ints, toml round-trips, junk"
      " record degrades to {}-plus-at, the show verb un-hides and"
      " sticks, idempotent)")

# 3) the wizard's pure pieces: the pre-mark (feature law 3), the
#    stickiness law (amendment 2: a human touch - label, bind, or
#    shown - outranks the sweep forever, and the sweep can only
#    INFORM such a row through the suffix), and the suffix itself
#    (one static, both panes). A bound device row keeps its namespace
#    verdict either way. Offline: no window, no camera, the dshow
#    oracle answers {} on this box (and the import-error arm covers
#    the boxes where it answers nothing at all).
DEV_BOUND = [{"name": "Bound Cam", "instance": "USB\\BOUND",
              "status": "OK", "virtual": False}]
FOUND_BOUND = [(2, True, 640, "Bound Cam")]
DIAG = {"at": 1.0, "indices": [2], "noimg": [2]}
rows = _camid.all_rows(DEV_BOUND, FOUND_BOUND,
                       {"labels": {}, "bindings": {}, "hidden": [],
                        "shown": [], "diag": DIAG})
bound = [r for r in rows if r["instance"] == "USB\\BOUND"][0]
assert bound["idx"] == 2 and bound["virtual"] is False, rows
rows = _camid.all_rows([], FOUND_BOUND, {"diag": DIAG})
assert str(rows[0]["instance"]) == "idx:2", rows      # unnamed feed:
assert rows[0]["virtual"] is True, rows               # the sweep's word
                                                      # marks it back
# (a) all three touch-kinds block the pre-mark
for touched in ({"labels": {"idx:2": "x"}},
                {"bindings": {"idx:2": 2}},
                {"shown": ["idx:2"]}):
    cfg2 = {"diag": DIAG}
    cfg2.update(touched)
    rows2 = _camid.all_rows([], FOUND_BOUND, cfg2)
    assert rows2[0]["virtual"] is False, touched
# (c) shown survives an UNRELATED scan: the record re-measured a
#     wider set and still calls the index dark - the touched row
#     stays visible (its dark verdict rides the suffix, not the hide)
rows = _camid.all_rows([], FOUND_BOUND,
                       {"diag": {"at": 2.0, "indices": [0, 2],
                                 "noimg": [2]}, "shown": ["idx:2"]})
assert rows[0]["virtual"] is False, rows
# 4) the suffix: the set's dark index wears it, the bright one never
#    does, and a window without a record never grows one
assert _camid.diag_suffix({"diag": DIAG}, 2) == \
    " (no image during diagnostic)"
assert _camid.diag_suffix({"diag": DIAG}, 1) == ""
assert _camid.diag_suffix({}, 2) == ""
assert _camid.diag_suffix(None, 2) == ""
print("pre-mark + stickiness OK (dark synthetic marked, bound keeps the"
      " namespace verdict, label/bind/show each veto the sweep, the"
      " suffix tells the touched rows what the hide may not)")

# 5) the sweep trigger, pure (feature law 2 + amendment 3): first
#    launch sweeps, the same set does not, a changed set does - and
#    the rescan button's force ORs at the worker's own decision point
#    (split from the thread exactly for this test), so the deliberate
#    re-measure verb outranks a matching record
from panelboss.ui.window import _preview
_Scan = _preview._CameraMixin
F02 = [(0, True, 640, ""), (2, True, 640, "")]


def _win(camera_cfg):
    # the bare namespace carries ONLY what the worker calls through
    # self for: the cfg, and the real decision method rebound onto the
    # fake window (the probe seam exists exactly for this handoff)
    w = types.SimpleNamespace(cfg={"camera": camera_cfg})
    w._diag_needed = lambda found: _Scan._diag_needed(w, found)
    return w


assert _Scan._scan_probe(_win({}), F02) is True                 # launch
assert _Scan._scan_probe(_win({"diag": {"at": 1.0,               # same
                                        "indices": [2, 0],       # set:
                                        "noimg": [0]}}),         # no
                              F02) is False                      # re-
                                                                 # sweep
assert _Scan._scan_probe(_win({"diag": {"at": 1.0,               # set
                                        "indices": [0, 1],       # moved
                                        "noimg": [1]}}),
                         F02) is True
assert _Scan._scan_probe(_win({"diag": {"at": 1.0,               # force
                                        "indices": [2, 0],       # beats
                                        "noimg": []}}),          # the
                              F02, force=True) is True           # record
print("sweep trigger OK (first launch and reindex sweep, a matching"
      " record does not, and force sweeps whatever the record says)")

# 6) the real scan worker, end to end offline (the amendment-1 shape
#    on live threads): fakes answer the PnP door and the camera opens,
#    index 1 stalls past its 15 s budget (the FakeDead below is the
#    only feed that has NO frame to serve), and the sweep must deliver
#    the veil, per-index progress, and the record - all through
#    ui_events, the widget thread touching nothing
_real_cd, _real_ec, _real_cam = (cam_mod.camera_devices,
                                 cam_mod.enumerate_cameras,
                                 cam_mod.Camera)
calls = {"opened": []}


class SpyCam(FakeCam):
    # records the opens (the sweep's "every index once" claim) and
    # answers index 1's read with NOTHING: opens, but serves no frame
    # (the FakeCam base serves for index 0 - a bright feed, the pair
    # the sweep must tell apart without touching a real driver)
    def __init__(self, index=0, **kw):
        calls["opened"].append(index)
        FakeCam.__init__(self, index=index)

    def read(self, timeout=3, screen=None):
        if self.index == 1:
            return None
        return FakeCam.read(self, timeout, screen)


cam_mod.camera_devices = lambda: list(DEV_BOUND)
cam_mod.enumerate_cameras = lambda *a, **k: [(0, True, 1280.0),
                                             (1, True, 1280.0)]
cam_mod.Camera = SpyCam
wins = types.SimpleNamespace(
    cfg=config.get_config(dir=SCRATCH, verbose=False),
    ui_events=queue.Queue())
# the worker calls its decision through self (a real window carries
# the methods on the class); the bare namespace carries the seam by
# hand - exactly the handoff the probe method was split for
wins._diag_needed = lambda found: _Scan._diag_needed(wins, found)
wins._scan_probe = lambda found, force=False: _Scan._scan_probe(wins,
                                                                found,
                                                                force)
deadline = time.time() + 60
try:
    _Scan._scan_cameras(wins)            # the real unbound method,
                                         # fakes for the whole driver
                                         # side: the window's binding
                                         # is a bound-method alias of
                                         # exactly this
    seen = []
    diag_msg = None
    while time.time() < deadline:
        try:
            message, value = wins.ui_events.get(timeout=1.0)
        except queue.Empty:
            continue
        if message == "cameras":
            break                        # the report is the tail
        seen.append((message, value))
        if message == "camera_diag":
            diag_msg = value
    assert diag_msg is not None, ("the sweep never reported: %r" % seen)
    assert sorted(calls["opened"]) == [0, 1]   # every openable probed,
                                               # once each
    assert diag_msg["noimg"] == [1], diag_msg  # the stall confessed,
                                               # the feed did not
    assert diag_msg["indices"] == [0, 1], diag_msg
    veils = [v for m, v in seen if m == "cameras_veil"]
    assert veils and veils[0] == "testing cameras, please wait"
    assert any("(probing" in v for v in veils), veils              # the
                                                                 # BEGIN
    assert any("(1 of 2 done)" in v for v in veils), veils   # beat
    assert any("(2 of 2 done)" in v for v in veils), veils   # (A4)
finally:
    cam_mod.camera_devices, cam_mod.enumerate_cameras = _real_cd, _real_ec
    cam_mod.Camera = _real_cam
print("scan worker OK (threaded sweep on live threads: every index"
      " probed once, the stall confessed, progress re-posts truthful,"
      " the record lands before the report)")

# 7) the IR seat's duty card (owner amendment 5: an on-duty camera
#    with no card is an unremovable camera). Pure spec, no widgets:
#    the bridge oracle is stubbed the way camid_test section 7 drives
#    it, and duty_roster reads the cfg shapes verbatim (list AND the
#    bare-int sentinel history).
from panelboss.ui.window import _camedit


def _ir_spec(index, names, extra=None):
    cfgc = {"index": index, "labels": {}, "hidden": [],
            "on": {}, "off": {}}
    cfgc.update(extra or {})
    cam_mod.hello_ir_names = lambda: list(names)
    return _camedit.ir_row_spec(cfgc)


_real_ir = cam_mod.hello_ir_names            # the section-top stub
try:
    assert _ir_spec([0, 2], ["Face IR"]) is None          # not rostered
    assert _ir_spec([-2, 0, 2], ["Face IR"]) == ("Face IR", False)
    assert _ir_spec([-2], ["Face IR"],
                    {"labels": {"ir:Face IR": "Night eye"}}) \
        == ("Night eye", False)                            # the wizard
                                                           # label lands
    assert _ir_spec([-2], ["Face IR"],
                    {"hidden": ["ir:Face IR"]}) == ("Face IR", True)
    assert _ir_spec(-2, []) == ("hello IR (bridge missing)", False)
finally:
    cam_mod.hello_ir_names = _real_ir
print("IR seat spec OK (duty-gated, label over group name, hidden"
      " honest, missing bridge confesses itself)")

# 8) the consent gate (redesign law 1): the load migration's truth
#    table (the ONLY judge of an absent key is the file itself -
#    set-up files upgrade to enabled, virgin files boot dark, an
#    explicit value always wins), the camera_enabled branch round-
#    trip, and the duty gate on the fakes. All offline.
def _gate(body):
    d = tempfile.mkdtemp(prefix="panelboss_camdiag_gate_")
    with open(os.path.join(d, "config.toml"), "w", encoding="utf8") as fh:
        fh.write(body)
    return config.get_config(dir=d, verbose=False)["camera"]["enabled"]


assert _gate("[camera]\nindex = 0\n") is False              # absent+virgin
assert _gate('[camera]\nindex = 0\nlabels = { "USB\\\\A" = "desk" }\n'
             ) is True                                      # set-up file
assert _gate('[camera]\nindex = 0\nbindings = { "USB\\\\A" = 1 }\n'
             ) is True                                      # binds count
assert _gate("[camera]\nindex = 0\n\n[camera.diag]\nat = 1.0\n"
             "indices = [0]\nnoimg = []\n") is True          # a swept box
assert _gate('[camera]\nindex = 0\nhidden = ["USB\\\\A"]\n'
             ) is True                                      # hidden-only
assert _gate('[camera]\nindex = 0\nshown = ["USB\\\\A"]\n'
             ) is True                                      # shown-only
assert _gate("[camera]\nindex = 3\n") is True               # roster-only
assert _gate("[camera]\nindex = [0]\n") is False            # [0] is stock
assert _gate('[camera]\nindex = 6\nenabled = false\nlabels = '
             '{ "USB\\\\A" = "desk" }\n') is False           # explicit sticks
assert _gate("[camera]\nindex = 6\nenabled = true\n") is True
print("consent migration OK (absent+virgin false, set-up upgrades"
      " true, explicit either way always wins)")

_real_camera8 = cam_mod.Camera
opened8 = []


class SpyCam8(FakeCam):
    def __init__(self, index=0, **kw):
        opened8.append(index)
        FakeCam.__init__(self, index=index)


cam_mod.Camera = SpyCam8
try:
    m8 = _monitor()
    m8.camera_cfg["enabled"] = False               # the duty gate:
    assert m8._poll() == (None, 0.0)               # abstain BEFORE
    assert opened8 == [] and m8.camera is None     # any open call
    m8.events.put(("camera_enabled", True))        # the branch: loop-
    m8._drain_tray()                               # owned write +
    assert cfg["camera"]["enabled"] is True              # toml truth
    assert tomllib.load(open(os.path.join(SCRATCH, "config.toml"),
                             "rb"))["camera"]["enabled"] is True
    m8.camera = FakeCam(index=9)                   # pretend duty
    m8.events.put(("camera_enabled", False))       # holds an eye:
    m8._drain_tray()                               # disable DRAINS
    assert cfg["camera"]["enabled"] is False             # right there
    assert m8.camera is None, "a mid-duty disable must release"
    assert cfg["camera"]["index"], "the roster survives the flush"
finally:
    cam_mod.Camera = _real_camera8
print("consent branch OK (gate abstains without touching a door,"
      " camera_enabled round-trips the toml, disable drains duty and"
      " keeps the roster)")

print("ALL CAMDIAG TESTS OK")
