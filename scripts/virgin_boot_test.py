"""The virgin boot, proven (amendment 7 item 4): a first launch must
boot DARK and stay dark. Section A drives the true virgin - a fresh
PANELBOSS_CONFIG_DIR, every camera door monkeypatched to RAISE, and
the audit is that nothing raises: get_config writes stock defaults
(the INFO must speak), the duty gate abstains before any open, and
the tray's camera menu renders the info row without enumerating.
Section B is the RESURRECTION TRAP that fooled the witnessed launch:
migrate_once copytree'd a 3-day-old %APPDATA%\\ICU-PresenceDetector
(index = 2, gaming/restore on, device_id = 1) into a fresh dir and
consent HONORED the stranger's file in silence. The fix retires the
source the moment the copy lands - so boot #2 (file moved away, the
shape of a real virgin retry) must boot dark, not resurrect.
Offline: no window, no cameras, no registry writes (the legacy Run
value is absent on this box; the winreg probe reads, never writes)."""
import logging
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SCRATCH = tempfile.mkdtemp(prefix="panelboss_virgin_")
os.environ["PANELBOSS_CONFIG_DIR"] = SCRATCH

import numpy as np                                    # noqa: E402

from panelboss import camera as cam_mod               # noqa: E402
from panelboss import config                          # noqa: E402
from panelboss import tray                            # noqa: E402
import panelboss.state as state_mod                   # noqa: E402

cam_mod.optional_present = lambda pkg: False          # no bridge oracle


class _Recorder(logging.Handler):
    """INFO here is the evidence: the breach class was SILENCE, so
    every assertion about speaking reads the records back."""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())


_rec = _Recorder()
logging.getLogger("config").addHandler(_rec)
logging.getLogger("migrate").addHandler(_rec)
logging.getLogger("config").setLevel(logging.INFO)
logging.getLogger("migrate").setLevel(logging.INFO)

fails = []


def check(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


class Det:
    conf = 0.45

    def detect(self, frame, conf=None):
        return np.empty((0, 4)), np.empty((0,))


# ---- A) the TRUE VIRGIN: dark by construction, doors fused shut -----
VIRGIN = tempfile.mkdtemp(prefix="panelboss_virgin_cfg_")


def _no_door(*a, **k):
    raise AssertionError("a camera door opened on a dark boot")


for _name in ("Camera", "HelloIrCamera", "enumerate_cameras", "camera_names",
              "camera_devices", "hello_ir_names", "open_camera"):
    setattr(cam_mod, _name, _no_door)

_rec.records.clear()
cfg = config.get_config(dir=VIRGIN, verbose=False)
check(cfg["camera"]["enabled"] is False,
      "virgin config: camera.enabled lands False")
check(any("wrote stock defaults" in r for r in _rec.records),
      "virgin config: the stock-defaults INFO speaks (the line whose "
      "ABSENCE proved the 15:19 file predated the boot)")
m = state_mod.PresenceMonitor(cfg, Det())              # doors still raised
check(m._poll() == (None, 0.0),
      "duty gate: _poll abstains BEFORE the first open call")
menu = tray.Tray._camera_menu(type("S", (), {"config": cfg})())
items = tuple(menu.items)
check(len(items) == 1 and items[0].text == "detection is off"
      and items[0].enabled is False,
      "tray menu: one honest info row, no enumeration behind it")

# ---- B) the RESURRECTION TRAP: today's exact ICU shape --------------
_appdata_real = os.environ.get("APPDATA")
APPD = tempfile.mkdtemp(prefix="panelboss_virgin_appdata_")
ICU = os.path.join(APPD, "ICU-PresenceDetector")
os.makedirs(ICU)
with open(os.path.join(ICU, "config.toml"), "w", encoding="utf8") as fh:
    fh.write("[camera]\nindex = 2\n\n[inference]\ndevice_id = 1\n"
             "\n[gaming]\nenabled = true\n\n[restore]\nenabled = true\n")
os.environ["APPDATA"] = APPD
new_dir = os.path.join(APPD, "PanelBoss")

_rec.records.clear()
config.migrate_once()                                  # boot #1
check(os.path.isfile(os.path.join(new_dir, "config.toml")),
      "trap: the ICU settings landed in the fresh dir")
check(not os.path.isdir(ICU)
      and any(n.startswith("ICU-PresenceDetector-retired-")
              for n in os.listdir(APPD)),
      "trap: the source is RETIRED on use - the migration can never "
      "fire twice on one box")
cfg2 = config.get_config(dir=new_dir, verbose=False)
check(cfg2["camera"]["enabled"] is True,
      "trap: consent honored from the stranger's non-stock file")
check(cfg2["gaming"]["enabled"] is False
      and cfg2["restore"]["enabled"] is False,
      "trap: the default-off law strips the stranger's POWER behaviors "
      "(amendment 2: an upgrade keeps names and the roster, not modes)")
check(any("enabled absent" in r and "consent honored from file" in r
          for r in _rec.records),
      "trap: the consent migration NAMES its evidence (the silence "
      "was the breach class, not the consent)")

os.remove(os.path.join(new_dir, "config.toml"))        # boot #2: the
_rec.records.clear()                                   # virgin retry
config.migrate_once()
cfg3 = config.get_config(dir=new_dir, verbose=False)
check(cfg3["camera"]["enabled"] is False,
      "boot #2 boots DARK: the retired twin is out of reach, stock "
      "defaults answer")
check(any("wrote stock defaults" in r for r in _rec.records),
      "boot #2: the stock-defaults INFO speaks again")
check(cfg3["camera"]["index"] == [0],
      "boot #2: no index resurrection (stock [0], not the ghost's 2)")
if _appdata_real:
    os.environ["APPDATA"] = _appdata_real

shutil.rmtree(APPD, ignore_errors=True)
print("ALL-VIRGIN-BOOT-TESTS-OK" if not fails
      else "virgin-boot FAILED: %s" % fails)
sys.exit(1 if fails else 0)
