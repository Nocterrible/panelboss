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

print("ALL CAMID TESTS OK")
