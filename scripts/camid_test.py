"""Camera identity, offline: the PnP payload parse, the name-unique
index mapping, the hidden picker filter, and the camera_identity
event's config write. No real camera, no window: a subprocess
stand-in feeds camera_devices, and the state side rides
camera_policy_test's FakeCam fixture.
"""
import json
import os
import sys
import tempfile
import threading
import types

try:
    import tomllib
except ModuleNotFoundError:                # the config.py fallback:
    import tomli as tomllib                # pre-3.11 venvs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# the scratch config dir BEFORE the config import: the state handler
# writes through write_config, which lands on CONFIG_DIR
SCRATCH = tempfile.mkdtemp(prefix="panelboss_camid_")
os.environ["PANELBOSS_CONFIG_DIR"] = SCRATCH

import numpy as np

from panelboss import camera as cam_mod
from panelboss import config
from panelboss import display
from panelboss.ui.window import _camid
import panelboss.state as state_mod

# the IR rows come from the optional bridge's live enumeration: the
# offline suite controls that oracle per section (absent for the
# deterministic core, present with a stub group for the IR sections)
_real_present, _real_names = cam_mod.optional_present, cam_mod.hello_ir_names
cam_mod.optional_present = lambda pkg: False
cam_mod.hello_ir_names = lambda: []

display.wake = lambda *a, **k: None
display.turn_off = lambda *a, **k: None
display.set_hold = lambda *a, **k: None
display.foreground_is_fullscreen = lambda: False


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


# 1) the payload parse: CREATE_NO_WINDOW rides the call (the visible-
#    console incident), camera_names keeps its shape and order, a lone
#    device unwraps, error prose reads as no cameras at all
PS_DEV = [{"FriendlyName": "Realtek USB 3.0 Webcam", "Status": "OK",
           "InstanceId": "USB\\VID_0BDA&PID_565C\\5&1"},
          {"FriendlyName": "Logi C270", "Status": "OK",
           "InstanceId": "USB\\VID_046D&PID_081B\\1"},
          {"FriendlyName": "Logi C270", "Status": "OK",
           "InstanceId": "USB\\VID_046D&PID_081B\\2"},
          {"FriendlyName": "OBS Virtual Camera", "Status": "OK",
           "InstanceId": "SW\\VCAM\\"}]
calls = []


def fake_run(cmd, **kw):
    calls.append(kw)
    return types.SimpleNamespace(stdout=fake_run.payload)


fake_run.payload = b""
_real_subprocess = cam_mod.subprocess
cam_mod.subprocess = types.SimpleNamespace(run=fake_run,
                                           CREATE_NO_WINDOW=0x08000000)
fake_run.payload = json.dumps(PS_DEV).encode()
devs = cam_mod.camera_devices()
assert calls[0].get("creationflags") == 0x08000000, calls
assert [d["instance"] for d in devs] == [d["InstanceId"] for d in PS_DEV]
# the namespace classifier rides every row: USB\ is glass, the rest is
# software (measured Oct 13: Broadcast ROOT\UNNAMED_DEVICE, DroidCam
# SWD\SGDEVAPI\... - the fixture's SW\VCAM stands in for the OBS entry)
assert [d["virtual"] for d in devs] == [False, False, False, True], devs
assert cam_mod.is_virtual_camera("USB4\\ROOT\\0") is False
assert cam_mod.is_virtual_camera("usb\\vid_1532") is False   # case-free
assert cam_mod.is_virtual_camera("ROOT\\UNNAMED_DEVICE\\0003") is True
assert cam_mod.is_virtual_camera("") is True                 # no claim
assert cam_mod.camera_names() == [d["FriendlyName"] for d in PS_DEV]
fake_run.payload = json.dumps(PS_DEV[0]).encode()      # the lone device
assert len(cam_mod.camera_devices()) == 1
fake_run.payload = b"Get-PnpDevice : The term is not recognized"
assert cam_mod.camera_devices() == []                  # prose, not JSON
fake_run.payload = b""
assert cam_mod.camera_names() == []
print("pnp payload OK (no-window flag, order kept, lone device unwraps,"
      " dead engine answers [])")

# 2) the mapping: name-unique devices get the scanned index, the
#    duplicated model gets none (the wizard's step line says SO), and
#    the hidden list filters the picker by instance
FOUND = [(6, True, 1280, "Realtek USB 3.0 Webcam"),
         (1, True, 640, "Logi C270"),
         (0, True, 100, "OBS Virtual Camera")]
mapped = _camid.identity_map(devs, FOUND)
assert mapped == {PS_DEV[0]["InstanceId"]: 6,
                  PS_DEV[3]["InstanceId"]: 0}, mapped
assert _camid.step_warning(devs, devs[1]) == _camid.DUP
assert _camid.step_warning(devs, devs[0]) == ""
# the relaxed preview map: the duplicated "Logi C270" name has ONE
# scanned feed, so both twins light up (shared=True, confessed); the
# unique names map plain (shared=False); with TWO feeds for one name
# the ordinal order is a coin flip and nothing maps
pm = _camid.preview_map(devs, FOUND)
assert pm == {PS_DEV[0]["InstanceId"]: (6, False),
              PS_DEV[1]["InstanceId"]: (1, True),
              PS_DEV[2]["InstanceId"]: (1, True),
              PS_DEV[3]["InstanceId"]: (0, False)}, pm
pm2 = _camid.preview_map(devs, FOUND + [(2, True, 640, "Logi C270")])
assert PS_DEV[1]["InstanceId"] not in pm2
assert pm2[PS_DEV[0]["InstanceId"]] == (6, False)
# 2b) the BIND: the human answer outranks every guess. A binding maps
#     its instance, evicts a name-guess standing on the same index,
#     ignores a bind to an absent instance (unplugged: waits in the
#     toml), survives hand-edited string values, and feeds the picker
#     suppression + bind_candidates (open indexes nobody claims).
mapped_b = _camid.identity_map(devs, FOUND,
                               {PS_DEV[2]["InstanceId"]: 1})
assert mapped_b == {PS_DEV[0]["InstanceId"]: 6,
                    PS_DEV[3]["InstanceId"]: 0,
                    PS_DEV[2]["InstanceId"]: 1}, mapped_b
mapped_dead = _camid.identity_map(devs, FOUND, {"USB\\GONE": 0})
assert mapped_dead == mapped                      # absent instance: no
                                                  # claim, guess intact
mapped_str = _camid.identity_map(devs, FOUND, {PS_DEV[1]["InstanceId"]: "1"})
assert mapped_str[PS_DEV[1]["InstanceId"]] == 1   # toml is input
assert _camid.bind_candidates(devs, FOUND, {}) == [1]   # the duplicated
                                                        # model's feed:
                                                        # unowned by the
                                                        # join, a bind
                                                        # candidate -
                                                        # the twin shape
assert _camid.bind_candidates(devs,                   # here is claimed
                              [(9, True, 640, ""), (3, False, 0, "")],
                              {}) == [9]
assert _camid.bind_candidates(devs, FOUND, {PS_DEV[2]["InstanceId"]: 1}) \
    == []                    # the second C270 twin bound to the feed
                             # its name could never claim: nothing left
                             # unowned (and mapped_b above proves the
                             # eviction of the first twin's guess)
assert _camid.hidden_indices(devs, FOUND,
                             [PS_DEV[3]["InstanceId"]]) == {0}
assert _camid.hidden_indices(devs, FOUND,           # a bind lets a hide
                             [PS_DEV[2]["InstanceId"]],   # reach the index
                             {PS_DEV[2]["InstanceId"]: 1}) == {1}   # twins never could
assert _camid.hidden_indices(devs, FOUND, ["USB\\UNSEEN"]) == set()
# the label-first caption rule (display_names): user label via the
# honest identity first, positional fallback only where the name is
# still unknown, never a claim a bind could have made
dn = _camid.display_names(devs, FOUND, {"labels": {
    PS_DEV[0]["InstanceId"]: "desk eye"}, "bindings": {}})
assert dn[6] == "desk eye"
assert dn[1] == "Logi C270"                     # ambiguous: the scan's
                                                # own guess, no label
assert dn[0] == "OBS Virtual Camera"
dn_b = _camid.display_names(devs, FOUND, {"labels": {"USB\\LATER": "boss"},
                                          "bindings": {PS_DEV[2]["InstanceId"]: 1}})
assert dn_b[1] == "Logi C270"                   # a label for an identity
# a label on the synthetic idx: key resolves to its index (the owner's
# "name it before you bind it" flow), and a real instance label still
# outranks it there
dn_i = _camid.display_names([], [(5, True, 640, "")],
                            {"labels": {"idx:5": "Desk"}, "bindings": {}})
assert dn_i[5] == "Desk"
dn_i2 = _camid.display_names([{"name": "Cam", "instance": "USB\\A",
                               "status": "OK"}],
                             [(5, True, 640, "")],
                             {"labels": {"idx:5": "Desk", "USB\\A": "Real"},
                              "bindings": {"USB\\A": 5}})
assert dn_i2[5] == "Real"
                                                # that claims nothing
                                                # that claims nothing
                                                # shows nowhere: the
                                                # positional fallback,
                                                # not a borrowed name
print("mapping OK (unique names pick the right index, the duplicated"
      " model is admitted, hidden filters the picker)")

# 3) migration: an old file without the keys reads with the defaults
d2 = tempfile.mkdtemp(prefix="panelboss_camid_old_")
with open(os.path.join(d2, "config.toml"), "w", encoding="utf8") as fh:
    fh.write("[camera]\nindex = 6\n")
old = config.get_config(dir=d2, verbose=False)
assert old["camera"]["labels"] == {} and old["camera"]["hidden"] == []
assert old["camera"]["bindings"] == {}            # the twin-bind table
print("migration OK (absent keys read as the stock empty tables)")

# 4) the state side: camera_identity events land in the live cfg AND
#    in the toml (state owns the write); an empty label clears, a
#    second hide does not duplicate
with open(os.path.join(SCRATCH, "config.toml"), "w", encoding="utf8") as fh:
    fh.write("[camera]\nindex = 6\n")
cfg = config.get_config(dir=SCRATCH, verbose=False)
_real_camera = cam_mod.Camera
cam_mod.Camera = FakeCam
try:
    m = state_mod.PresenceMonitor(cfg, Det())
    m.events.put(("camera_identity", {"instance": "USB\\R1",
                                      "label": "desk eye"}))
    m.events.put(("camera_identity", {"instance": "USB\\V2",
                                      "hide": True}))
    m._drain_tray()
    assert cfg["camera"]["labels"] == {"USB\\R1": "desk eye"}
    assert cfg["camera"]["hidden"] == ["USB\\V2"]
    on_disk = tomllib.load(open(os.path.join(SCRATCH, "config.toml"), "rb"))
    assert on_disk["camera"]["labels"] == {"USB\\R1": "desk eye"}
    assert on_disk["camera"]["hidden"] == ["USB\\V2"]
    m.events.put(("camera_identity", {"instance": "USB\\R1", "label": " "}))
    m.events.put(("camera_identity", {"instance": "USB\\V2",
                                      "hide": True}))
    m._drain_tray()
    assert cfg["camera"]["labels"] == {}, cfg["camera"]["labels"]
    assert cfg["camera"]["hidden"] == ["USB\\V2"]
    assert tomllib.load(open(os.path.join(SCRATCH, "config.toml"),
                             "rb"))["camera"]["hidden"] == ["USB\\V2"]
    back = config.get_config(dir=SCRATCH, verbose=False)
    assert back["camera"]["hidden"] == ["USB\\V2"]     # round trip
    assert back["camera"]["labels"] == {}
    # unhide: the door, not the cell (gate finding 5) - removal is
    # idempotent and survives the toml round trip like its inverse
    m.events.put(("camera_identity", {"instance": "USB\\V2",
                                      "unhide": True}))
    m.events.put(("camera_identity", {"instance": "USB\\GONE",
                                      "unhide": True}))   # never hidden
    m._drain_tray()
    assert cfg["camera"]["hidden"] == [], cfg["camera"]["hidden"]
    assert tomllib.load(open(os.path.join(SCRATCH, "config.toml"),
                             "rb"))["camera"]["hidden"] == []
    # bind: the twin answer round-trips through the loop-owned toml,
    # and a non-numeric bind clears the claim (empty-label semantics)
    m.events.put(("camera_identity", {"instance": "USB\\R1", "bind": 6}))
    m._drain_tray()
    assert cfg["camera"]["bindings"] == {"USB\\R1": 6}
    assert tomllib.load(open(os.path.join(SCRATCH, "config.toml"),
                             "rb"))["camera"]["bindings"] == {"USB\\R1": 6}
    m.events.put(("camera_identity", {"instance": "USB\\R1", "bind": ""}))
    m._drain_tray()
    assert cfg["camera"]["bindings"] == {}
    # migration: name the placeholder first (the owner's exact flow -
    # "idx:0" was all the identity that existed), THEN bind: the name
    # follows the camera onto the durable identity or it orphans when
    # the synthetic row retires
    m.events.put(("camera_identity", {"instance": "idx:0", "label": "Desk"}))
    m._drain_tray()
    assert cfg["camera"]["labels"].get("idx:0") == "Desk"
    m.events.put(("camera_identity", {"instance": "USB\\R1", "bind": 0}))
    m._drain_tray()
    assert cfg["camera"]["labels"] == {"USB\\R1": "Desk"}, cfg["camera"]["labels"]
    assert cfg["camera"]["bindings"] == {"USB\\R1": 0}
    m.events.put(("camera_identity", {"instance": "USB\\R1", "bind": ""}))
    m._drain_tray()
    print("identity event OK (labels/hidden stored by instance, toml"
          " round-trips, empty label clears, hide and unhide are"
          " idempotent)")
finally:
    cam_mod.Camera = _real_camera
    cam_mod.subprocess = _real_subprocess

# 5) the candidate filter: an unhealthy PnP entry (Status="Error")
#    earns no wizard step and no wasted open while the OK entries -
#    any case - stay candidates; a hidden entry drops WITHOUT being
#    counted unhealthy (the count confesses what the filter skipped);
#    a software-namespace entry is hidden by default and counted, and
#    the reveal tick admits it back into the steps
DEV_MIX = [{"name": "Ok Cam", "instance": "USB\\OK", "status": "OK"},
           {"name": "Bad Cam", "instance": "USB\\BAD", "status": "Error"},
           {"name": "Also Ok", "instance": "USB\\OK2", "status": "ok"}]
DEV_SOFT = {"name": "Filter Cam", "instance": "SWD\\VCAM\\1", "status": "OK"}
probe = types.SimpleNamespace(app=types.SimpleNamespace(
    cfg={"camera": {"hidden": ["USB\\GONE"], "labels": {}}}))
cands, skipped, vhidden = _camid.IdentifyWindow._candidates(
    probe, DEV_MIX + [DEV_SOFT] + [{"name": "Gone", "instance": "USB\\GONE",
                                    "status": "OK"}])
assert [d["instance"] for d in cands] == ["USB\\OK", "USB\\OK2"]
assert skipped == 1 and vhidden == 1
probe._show_virtual = True
cands, skipped, vhidden = _camid.IdentifyWindow._candidates(
    probe, DEV_MIX + [DEV_SOFT])
assert [d["instance"] for d in cands] == ["USB\\OK", "USB\\OK2",
                                          "SWD\\VCAM\\1"]
assert skipped == 1 and vhidden == 0
print("filter OK (the Error entry gets no step, OK entries ride in any"
      " case, software cams hide by default and answer to the tick,"
      " both counts confess what was skipped)")

# 5b) the parity merge (the owner's UAT law): every OPEN scanned index
#     earns a wizard step - claimed ones through their PnP row, the
#     rest as a synthetic "idx:N" row that previews by its own index
#     and takes policy by it. A closed index gets nothing; an index
#     whose positional name is real rides that name, else "camera N".
FOUND_MIX = [(9, True, 640, ""), (0, True, 640, "Ok Cam"),
             (7, True, 640, "DroidCam Video"), (3, False, 0, "")]
merged = _camid.all_rows(DEV_MIX, FOUND_MIX)
assert [r["instance"] for r in merged[:3]] == ["USB\\OK", "USB\\BAD",
                                               "USB\\OK2"]      # PnP first
synth = {r["instance"]: r for r in merged if str(r["instance"]).startswith("idx:")}
assert set(synth) == {"idx:9", "idx:7"}, merged                # 0 claimed,
                                                               # 3 closed
assert synth["idx:9"]["name"] == "camera 9"                    # blank gets
                                                               # the honest
                                                               # placeholder
assert synth["idx:7"]["name"] == "DroidCam Video"
assert all(not r["virtual"] for r in synth.values()), \
    "unknown identity must not default-hide: the UAT law is PnP-seen"
assert all(r["idx"] == int(str(r["instance"])[4:]) for r in synth.values())
assert _camid.hidden_indices(DEV_MIX, FOUND_MIX, ["idx:9"]) >= {9}
assert _camid.hidden_indices(DEV_MIX, FOUND_MIX, ["idx:9", "USB\\OK"]) == {9, 0}
bound = _camid.all_rows(DEV_MIX, FOUND_MIX, {"bindings": {"USB\\OK2": 9}})
assert [r["instance"] for r in bound if str(r["instance"]).startswith("idx:")] \
    == ["idx:7"], bound                           # 9 became a real
assert [r for r in bound if r["instance"] == "USB\\OK2"][0]["idx"] == 9  # device row
assert all("idx" not in r or r["idx"] is not None for r in bound)  # no leak-through
print("merge OK (open indexes walk, closed do not, claimed are not"
      " duplicated, idx: keys hide by index, a bind flips a synthetic"
      " into its device row)")

# 6) the unhide recheck ladder: a stuck drain is ridden EXACTLY the
#    cap (8 rides at 500 ms after the first 250 ms reload), a second
#    click mid-ladder schedules no second ladder, the reload stands
#    the moment the visible count changes, and an empty app cache
#    routes the powershell PnP query OFF the calling (tk) thread
class Events:
    def __init__(self):
        self.items = []

    def put(self, item):
        self.items.append(item)


class App:
    def __init__(self, devs, hidden):
        self._devs, self._cams = devs, []
        self.cfg = {"camera": {"hidden": list(hidden), "labels": {}}}
        self.monitor = types.SimpleNamespace(events=Events())


class Label:
    def __init__(self):
        self.text = None

    def configure(self, **kw):
        self.text = kw.get("text", self.text)


class FakeWin:
    # the real ladder, driven by hand: no tk loop, no camera
    _reload_steps = _camid.IdentifyWindow._reload_steps
    _ladder_check = _camid.IdentifyWindow._ladder_check
    _ladder_start = _camid.IdentifyWindow._ladder_start
    _ladder_stop = _camid.IdentifyWindow._ladder_stop
    _candidates = _camid.IdentifyWindow._candidates
    _unhide_all = _camid.IdentifyWindow._unhide_all
    _gather_reload = _camid.IdentifyWindow._gather_reload
    _rebuild_hidden_list = lambda self, rows: None   # the reload lands
    _placeholder = lambda self: None                 # here: no tk
    _start_step = lambda self: None          # widget churn is not the
    _work = None                             # duty here

    def __init__(self, app):
        self.app = app
        self._dying, self._pos = False, 0
        self._ladder_busy = False
        self._ladder_left, self._ladder_prev = 0, None
        self._fetched = False
        self._devs, self._cands = [], []
        self._skipped, self._vhidden = 0, 0
        self._frame, self._busy = None, False
        self._held, self._nostream = False, False
        self._busy_note = None
        self.scheduled = []
        self.note, self.idline = Label(), Label()
        self.preview = Label()

    def after(self, delay, hook):
        self.scheduled.append((delay, hook))

    def fire(self):                          # tk runs the next job
        delay, hook = self.scheduled.pop(0)
        hook()
        return delay


app = App(DEV_MIX, ["USB\\OK2"])             # OK visible, BAD unhealthy
w = FakeWin(app)                             # (no step), OK2 hidden
w._reload_steps()                            # the pump's first sync
assert [d["instance"] for d in w._cands] == ["USB\\OK"]
w._ladder_start()
assert w.fire() == 250                       # the first reload: no drain
w._unhide_all()                              # a double-click mid-ladder
assert w.scheduled == [(500, w._reload_steps)]   # rides the ONE ladder
rides = 0
while w.scheduled:
    delay, hook = w.scheduled.pop(0)
    assert delay == 500
    hook()
    rides += 1
assert rides == 8                            # exactly the cap, then stop
assert not w._ladder_busy and w._ladder_left == 0
assert w.scheduled == []                     # no reload-queue pileup
app2 = App(DEV_MIX, ["USB\\OK2"])
w2 = FakeWin(app2)
w2._reload_steps()
w2._ladder_start()
w2.fire()                                    # riding, drain pending
app2.cfg["camera"]["hidden"] = []            # the drain lands
w2.fire()                                    # changed count: it stands
assert not w2._ladder_busy and w2.scheduled == []
assert [d["instance"] for d in w2._cands] == ["USB\\OK", "USB\\OK2"]
real_devices = _camid.camera.camera_devices
seen = []


def spy_devices():
    seen.append(threading.current_thread().name)
    return DEV_MIX


_camid.camera.camera_devices = spy_devices
try:
    app2._devs = []
    w2._reload_steps()                       # empty cache: off-thread
    for t in threading.enumerate():          # route, never a freeze
        if t.name == "camid-reload":
            t.join(5)
    assert seen == ["camid-reload"], seen
    assert app2._devs == DEV_MIX
finally:
    _camid.camera.camera_devices = real_devices
print("ladder OK (stuck drain rides exactly the 8-cap with no pileup,"
      " the changed count stands at once, the PnP query answers off"
      " the calling thread)")

# 7) the worker's bounded attempt (the UAT "all say no live view"):
#    a door that opens but never samples must not hold the device nor
#    the silence - handle back, verdict flagged for the pump; the
#    corpse arm marks HELD (the BUSY wording is earned only by proof);
#    a worker whose step was retired mid-open confesses nothing.
class DeadCam:
    instances = []

    def __init__(self, index=0, warmup=4, width=1280, height=720):
        self.released = False
        DeadCam.instances.append(self)

    def is_open(self):
        return True

    def read(self, timeout=3, screen=None):
        return None

    def release(self):
        self.released = True


class HeldCam(DeadCam):
    def is_open(self):
        return False


class FlashCam(DeadCam):
    """One frame, then the silence the pump cannot tell apart from a
    still-opening door - the latch's exact reason to exist. The test
    has no owner to click next, so the second read performs the step
    retirement (the owner's click) from the outside."""

    hook = None

    def __init__(self, *a, **k):
        DeadCam.__init__(self, *a, **k)
        self._n = 0

    def read(self, timeout=3, screen=None):
        self._n += 1
        if self._n == 1:
            import numpy
            return numpy.zeros((8, 8, 3), numpy.uint8)
        if FlashCam.hook:
            FlashCam.hook()
        return None


_saved_cam, _saved_budget = _camid.camera.Camera, _camid.FRAME_BUDGET
try:
    _camid.FRAME_BUDGET = 0.2
    _camid.camera.Camera = DeadCam
    w3 = FakeWin(App(DEV_MIX, []))
    w3._gen, w3._busy = 5, True
    _camid.IdentifyWindow._work(w3, 5, 0)
    assert w3._nostream and not w3._busy and not w3._held
    assert DeadCam.instances[-1].released, "the handle escaped the budget"
    DeadCam.instances = []
    _camid.camera.Camera = HeldCam
    w4 = FakeWin(App(DEV_MIX, []))
    w4._gen, w4._busy = 5, True
    _camid.IdentifyWindow._work(w4, 5, 0)
    assert w4._held and w4._busy and not w4._nostream
    assert HeldCam.instances[-1].released
    _camid.camera.Camera = DeadCam
    DeadCam.instances = []
    w5 = FakeWin(App(DEV_MIX, []))
    w5._gen = 5
    _camid.IdentifyWindow._work(w5, 4, 0)   # step retired under the
    assert not (w5._nostream or w5._busy or w5._held)  # worker: stay mute
    assert DeadCam.instances[-1].released
    _camid.camera.Camera = FlashCam
    DeadCam.instances = []
    w6 = FakeWin(App(DEV_MIX, []))
    w6._gen, w6._busy = 5, True
    FlashCam.hook = lambda: setattr(w6, "_dying", True)   # the next
    try:
        _camid.IdentifyWindow._work(w6, 5, 0)             # click lands
    finally:                                              # mid-ride
        FlashCam.hook = None
    assert not w6._nostream, "a step that showed a frame is not no-stream"  # one frame
    assert DeadCam.instances[-1].released                                   # then dark:
    assert w6._frame is not None, "the flash frame must reach the mailbox"  # verdict NO
finally:
    _camid.camera.Camera = _saved_cam
    _camid.FRAME_BUDGET = _saved_budget
print("worker OK (a silent door returns the handle and flags the verdict,"
      " one frame then dark is NOT a no-stream, the corpse arm marks"
      " HELD, a retired step stays mute)")

# 7b) the hello IR rows (the owner: "they don't show up in identify at
#     all"): glass behind a driver flag, invisible to the class-Camera
#     query AND the cv2 scan space, so all_rows appends them from the
#     bridge directly - nameable, hideable, previewable through the
#     adapter. Oracle ON for this section, one stub group.
cam_mod.optional_present = lambda pkg: pkg == "whircam"
cam_mod.hello_ir_names = lambda: ["Face IR"]
try:
    ir_rows = _camid.all_rows(list(DEV_MIX), [], {})
    ir = [r for r in ir_rows if str(r["instance"]).startswith("ir:")]
    assert len(ir) == 1 and ir[0]["idx"] == cam_mod.HELLO_IR, ir_rows
    assert ir[0]["virtual"] is False and ir[0]["ir"] == "Face IR"
    probe2 = types.SimpleNamespace(app=types.SimpleNamespace(
        cfg={"camera": {"hidden": ["ir:Face IR"], "labels": {},
                        "bindings": {}}}))
    c2, _s, _v = _camid.IdentifyWindow._candidates(probe2, ir_rows)
    assert all(not str(r["instance"]).startswith("ir:") for r in c2)
    # the group arm opens the ADAPTER with the NAME, and an adapter
    # that abstains takes the corpse path (HELD), not a crash
    opened = {}

    class IrDead:
        def __init__(self, group=None, warmup=4, timeout=8.0):
            opened["group"] = group
        def is_open(self):
            return False
        def release(self):
            opened["released"] = True
        def read(self, timeout=3, screen=None):
            return None

    _real_ir = _camid.camera.HelloIrCamera
    _camid.camera.HelloIrCamera = IrDead
    try:
        w7 = FakeWin(App(DEV_MIX, []))
        w7._gen, w7._busy = 2, True
        _camid.IdentifyWindow._work(w7, 2, cam_mod.HELLO_IR,
                                    group="Face IR")
    finally:
        _camid.camera.HelloIrCamera = _real_ir
    assert opened.get("group") == "Face IR" and opened.get("released")
    assert w7._held and not w7._nostream
finally:
    cam_mod.optional_present, cam_mod.hello_ir_names = _real_present, _real_names
print("hello IR OK (rows exist with the bridge, hide by ir: key, the"
      " group arm opens the adapter and its abstain rides the corpse path)")

# 8) widget smoke, the lesson the owner's UAT beat into this file: the
#    offline suites construct ZERO widgets, and a double-specified
#    menu_style kwarg killed the window CONSTRUCTOR - the pane closed
#    instantly on open with nothing in the log (tk swallows callback
#    errors on pythonw). Where a display exists, the real window must
#    build, run one step, and die quietly; headless boxes skip, loud
#    about it.
try:
    import queue as _q
    import customtkinter as ctk
    from panelboss.ui import theme
    ctk.set_appearance_mode("dark")

    class _Host(ctk.CTk):                     # the window's master is
        def __init__(self):                   # the app itself: it must
            super().__init__()                # be a real tk widget
            self.withdraw()
            self.cfg = {**cfg, "camera": {**cfg["camera"],
                                          "hidden": ["USB\\OK"]}}
            self.skin = theme.get_skin(cfg["ui"]["skin"])
            # OK hidden: the first step is deterministically the
            # claimless OK2 with the unnamed feed as its bind option
            self._cams = [(0, True, 640, "")]    # one open, UNNAMED
            self._devs = list(DEV_MIX)
            self._scan_cameras = lambda: None
            self.monitor = types.SimpleNamespace(events=_q.Queue())

    _h = _Host()
    _w = _camid.IdentifyWindow(_h)
    _h.update()
    _w._devs = list(DEV_MIX)                    # beat the _gather
    _w._built = True                            # thread: the smoke's
    _w._build()                                 # devs are the fixture
    _h.update()
    assert _w._cands, ("smoke got no steps: devs=%r cams=%r hidden=%r"
                       % (_w._devs, _h._cams,
                          cfg["camera"].get("hidden")))
    assert _w.bind_menu._values, "the twin's bind menu lost its feeds"
    # the reset law, on the real window: entering a step arms the
    # PLACEHOLDER image (never image=None - the CTk trap's freeze
    # shape), straight from _start_step
    assert _w.preview.cget("image") is not None, \
        "the step left the preview on image=None: the freeze's shape"
    # amendment 2 on real widgets: every row the filter dropped is
    # listed with its honest reason (OK is hidden here -> policy
    # line; BAD is unhealthy -> the PnP no-image line) - the pane
    # shows the way back, it does not silently swallow the drop
    texts = []
    for _line in _w._hlist_frame.winfo_children():
        for _w2 in _line.winfo_children():
            try:
                texts.append(str(_w2.cget("text")))
            except Exception:
                pass
    assert any("hidden policy" in t for t in texts), texts
    assert any("PnP" in t for t in texts), texts
    _w.destroy()
    _h.destroy()
    print("window smoke OK (real IdentifyWindow built, stepped, bound,"
          " destroyed)")
except Exception as _exc:
    if isinstance(_exc, AssertionError):
        raise
    # ONLY no-display (TclError) and no-ctk (ImportError) may skip:
    # the gate's lesson - a broad catch once shipped the bug class
    # this smoke exists to catch, so everything else re-raises loud
    if type(_exc).__name__ not in ("TclError", "ImportError"):
        raise
    print("window smoke skipped: %s (no display?)" % type(_exc).__name__)

# 9) the crash law (the re-landed wave, owner crash report): a
#    toplevel's command handler must NEVER destroy it from its own
#    stack - the withdraw-then-schedule idiom is asserted on a spy
#    (no tk needed for the retire ordering), and the source ban
#    sweeps the pane so the direct call cannot creep back. Plus the
#    orphan-proof label key: an identity with no PnP join renames
#    through "idx:N" instead of dying silent.
class CloseSpy:
    _close = _camid.IdentifyWindow._close

    def __init__(self):
        self._dying, self._gen = False, 4
        self.withdrawn = 0
        self.scheduled = []
        self.destroyed = 0

    def withdraw(self):
        self.withdrawn += 1

    def after(self, delay, hook):
        self.scheduled.append((delay, hook))

    def destroy(self):
        self.destroyed += 1


_c = CloseSpy()
_c._close()
assert _c.withdrawn == 1 and _c.destroyed == 0, \
    "close must withdraw and SCHEDULE the destroy, never eat its own"
assert _c.scheduled and _c.scheduled[0][0] == 0, "the retire rides the " \
    "loop's next clean turn"
_c.scheduled[0][1]()
assert _c.destroyed == 1
assert _c._dying and _c._gen == 5, "workers retire BEFORE the withdraw"
with open(_camid.__file__, encoding="utf8") as fh:
    assert "command=self.destroy" not in fh.read(), \
        "a command handler destroys its own toplevel directly again"
print("crash law OK (withdraw+schedule on the spy; the source stays "
      "free of command=self.destroy)")

import queue as _q9
_real_camera9 = cam_mod.Camera
cam_mod.Camera = FakeCam
try:
    m9 = state_mod.PresenceMonitor(cfg, Det())
    m9.ui_events = _q9.Queue()
    m9.events.put(("camera_identity", {"index": 7, "label": "Orphan"}))
    m9.events.put(("camera_identity", {"index": "x", "label": "junk"}))
    m9._drain_tray()
    assert cfg["camera"]["labels"].get("idx:7") == "Orphan"
    assert "idx:x" not in cfg["camera"]["labels"]   # the int guard
                                                    # eats junk
    assert tomllib.load(open(os.path.join(SCRATCH, "config.toml"),
                             "rb"))["camera"]["labels"]["idx:7"] \
        == "Orphan"                                 # through the toml
    # and a bind later MIGRATES the orphan key like the ghost it is:
    # name first, bind after (the owner's exact flow), the label
    # follows onto the durable instance (section 4 left a "USB\\R1"
    # label in this shared cfg - the asserts are about the keys in
    # play, not the whole table)
    m9.events.put(("camera_identity", {"instance": "USB\\LATE",
                                       "bind": 7}))
    m9._drain_tray()
    assert cfg["camera"]["labels"].get("USB\\LATE") == "Orphan"
    assert "idx:7" not in cfg["camera"]["labels"], cfg["camera"]["labels"]
finally:
    cam_mod.Camera = _real_camera9
print("idx-key label OK (an inst-less identity persists by its scan "
      "index, the int guard eats junk, and the bind migration adopts "
      "the orphan)")

print("ALL CAMID TESTS OK")
