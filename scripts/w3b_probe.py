"""W3B probe: the second-final-gate deltas' regression nets, offline
(no window, no powercfg, no display). Run from repo root:
python scripts/w3b_probe.py
"""
import io
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------- (a) --
# the mosaic tile feeder (mono-driver class, same as detector's
# letterbox fix): a 2-D grayscale frame must COMPOSE (GRAY2RGB), an
# exotic (h, w, 2) depth tile must ABSTAIN (None) - never raise.
import numpy as np                                # noqa: E402
from panelboss.state import _preview              # noqa: E402

gray = np.arange(40, dtype=np.uint8).reshape(5, 8)
tile = _preview._tile_rgb(gray)
assert tile is not None and tile.mode == "RGB" and tile.size == (8, 5), \
    (tile and (tile.mode, tile.size))
arr = np.asarray(tile)
assert arr.shape == (5, 8, 3)                      # gray survived to a
print("ok - 2-D grayscale tile converts GRAY2RGB (mono-driver, feed end)")
bgr = np.dstack([gray, gray + 1, gray + 2])        # classic BGR still
t2 = _preview._tile_rgb(bgr)                       # flips to RGB
assert t2 is not None and np.asarray(t2)[0, 0].tolist() == \
    bgr[0, 0][::-1].tolist(), (np.asarray(t2)[0, 0], bgr[0, 0])
print("ok - 3-D BGR keeps the BGR2RGB flip")
depth = np.zeros((5, 8, 2), np.uint8)              # the exotic shape
assert _preview._tile_rgb(depth) is None           # abstains, no raise
try:
    import cv2
    cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)           # cv2 itself agrees
except Exception as e:                             # the 3-D path is
    raise AssertionError(str(e))                   # the trusted shape
print("ok - (h, w, 2) depth tile abstains instead of raising")

# ---------------------------------------------------------------- (b) --
# runtime handback (gate MED, ledger 1): a FAILED set_plan must keep
# BOTH the marker and the saved guid (the boot reconcile is the retry
# path and it only fires while the marker stands); success clears.
# Marker scenarios mirrored from w2c_probe; the exec seam is monkeyed
# exactly the same way.
import panelboss.gaming as gaming                  # noqa: E402
import panelboss.gaming_watch as gw                # noqa: E402
import panelboss.power_plan as ppl                 # noqa: E402

FAST = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
BAL = "381b4222-f694-41f0-9685-ff5bb260df2e"
real = (ppl.plans, ppl.active, ppl.set_plan, ppl._run)
ppl.plans = lambda: []
cur = [FAST]
ppl.active = lambda: cur[0]

logs = io.StringIO()
h = logging.StreamHandler(logs)
h.setLevel(logging.ERROR)
gaming_log = logging.getLogger("gaming")
gaming_log.addHandler(h)
gaming_log.setLevel(logging.DEBUG)

# failure: set_plan raises -> marker KEPT, state KEPT, error logged
GCFG = {"power_plan": "high performance"}
gaming.mark_plan_owned(GCFG, BAL)
side = {"power_plan": {"saved": BAL, "active": FAST}}


def _boom(g):
    raise RuntimeError("powercfg vanished")


ppl.set_plan = _boom
gw._apply_power_plan(side, GCFG, False, {})
assert gaming.plan_owned(GCFG) and gaming.plan_prev(GCFG) == BAL, GCFG
assert side["power_plan"] == {"saved": BAL, "active": FAST}, side
assert "handback" in logs.getvalue().lower(), logs.getvalue()
print("ok - handback FAILED (raised): both keys stand, error logged")

# failure: set_plan returns False -> same rule
logs.truncate(0), logs.seek(0)
ppl.set_plan = lambda g: False
gw._apply_power_plan(side, GCFG, False, {})
assert gaming.plan_owned(GCFG), GCFG
assert "handback" in logs.getvalue().lower(), logs.getvalue()
print("ok - handback FAILED (False): both keys stand, error logged")

# success: the marker clears, the state empties
gaming_log.removeHandler(h)
ppl.set_plan = lambda g: cur.__setitem__(0, g) or True
gw._apply_power_plan(side, GCFG, False, {})
assert not gaming.plan_owned(GCFG), GCFG
assert side["power_plan"] == {"saved": "", "active": ""}, side
print("ok - handback SUCCESS: the marker clears as before")

# and the boot rule still repairs the survivor: marker stands, desk
# still wears the fast plan -> boot hands it back and clears
ppl.plans = lambda: [{"guid": FAST, "name": "High performance"},
                     {"guid": BAL, "name": "Balanced"}]
gaming.mark_plan_owned(GCFG, BAL)
cur[0] = FAST


def _sp(g):
    cur[0] = g
    return True


ppl.set_plan = _sp
gw._boot_reconcile({"gaming": GCFG})
assert cur[0] == BAL and not gaming.plan_owned(GCFG), (cur, GCFG)
print("ok - the kept token is real: the boot reconcile retries and wins")
ppl.plans, ppl.active, ppl.set_plan, ppl._run = real

print("W3B PROBE OK")
