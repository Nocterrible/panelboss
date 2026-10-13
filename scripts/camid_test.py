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
assert _camid.hidden_indices(devs, FOUND,
                             [PS_DEV[3]["InstanceId"]]) == {0}
assert _camid.hidden_indices(devs, FOUND, ["USB\\UNSEEN"]) == set()
print("mapping OK (unique names pick the right index, the duplicated"
      " model is admitted, hidden filters the picker)")

# 3) migration: an old file without the keys reads with the defaults
d2 = tempfile.mkdtemp(prefix="panelboss_camid_old_")
with open(os.path.join(d2, "config.toml"), "w", encoding="utf8") as fh:
    fh.write("[camera]\nindex = 6\n")
old = config.get_config(dir=d2, verbose=False)
assert old["camera"]["labels"] == {} and old["camera"]["hidden"] == []
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
    print("identity event OK (labels/hidden stored by instance, toml"
          " round-trips, empty label clears, hide and unhide are"
          " idempotent)")
finally:
    cam_mod.Camera = _real_camera
    cam_mod.subprocess = _real_subprocess

# 5) the candidate filter: an unhealthy PnP entry (Status="Error")
#    earns no wizard step and no wasted open while the OK entries -
#    any case - stay candidates; a hidden entry drops WITHOUT being
#    counted unhealthy (the count confesses what the filter skipped)
DEV_MIX = [{"name": "Ok Cam", "instance": "USB\\OK", "status": "OK"},
           {"name": "Bad Cam", "instance": "USB\\BAD", "status": "Error"},
           {"name": "Also Ok", "instance": "USB\\OK2", "status": "ok"}]
probe = types.SimpleNamespace(app=types.SimpleNamespace(
    cfg={"camera": {"hidden": ["USB\\GONE"], "labels": {}}}))
cands, skipped = _camid.IdentifyWindow._candidates(
    probe, DEV_MIX + [{"name": "Gone", "instance": "USB\\GONE",
                       "status": "OK"}])
assert [d["instance"] for d in cands] == ["USB\\OK", "USB\\OK2"]
assert skipped == 1
print("filter OK (the Error entry gets no step, OK entries ride in any"
      " case, the skipped count counts only PnP-status drops)")

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
    _start_step = lambda self: None          # widget churn is not the
    _work = None                             # duty here

    def __init__(self, app):
        self.app = app
        self._dying, self._pos = False, 0
        self._ladder_busy = False
        self._ladder_left, self._ladder_prev = 0, None
        self._fetched = False
        self._devs, self._cands, self._skipped = [], [], 0
        self.scheduled = []
        self.note, self.idline = Label(), Label()

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

print("ALL CAMID TESTS OK")
