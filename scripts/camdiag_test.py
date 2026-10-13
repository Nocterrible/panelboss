"""Camera diagnostic, offline: the config record, the state round-trip,
and the picker's pure pieces. No real camera, no window: the state side
rides camera_policy_test's FakeCam fixture the way camid_test does, and
the wizard-side tests drive the importable helpers directly.
"""
import os
import sys
import tempfile
import time
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
finally:
    cam_mod.Camera = _real_camera
print("identity event OK (diag stored as ints, toml round-trips, junk"
      " record degrades to {}-plus-at)")

print("ALL CAMDIAG TESTS OK")
