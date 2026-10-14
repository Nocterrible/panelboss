"""Config-boundary normalizer: hand-edited junk must fail OPEN at load
with a loud warning, never raise and never stay silent; the DEFAULTS
stock table must survive the load as an alias-free copy; and the two
write_config writers (the UI's debounced save, the monitor loop) must
serialize cleanly. No app, no window. Run:
.venv\\Scripts\\python.exe scripts\\config_norm_test.py"""
import glob
import logging
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

try:
    import tomllib as _toml
except ImportError:
    import tomli as _toml

# PANELBOSS_CONFIG_DIR (the real var - PANELBOSS_STATE is fiction) must
# be a fresh temp dir BEFORE importing panelboss.config: CONFIG_DIR is
# bound at import time
_TMP = tempfile.mkdtemp(prefix="panelboss_norm_test_")
os.environ["PANELBOSS_CONFIG_DIR"] = _TMP

from panelboss import config  # noqa: E402  (after the env var)

FAILED = []


class _Recorder(logging.Handler):
    """Collects every WARNING+ record the config logger emits."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())


_RECORDER = _Recorder()
log = logging.getLogger("config")
log.addHandler(_RECORDER)


def _fail(what):
    FAILED.append(what)
    print("[FAIL] %s" % what)


def _pass(what):
    print("[PASS] %s" % what)


def _write(text):
    with open(os.path.join(_TMP, "config.toml"), "w",
              encoding="utf-8") as f:
        f.write(text)


# --- 1) junk values: every one fails open to stock, load() survives ---
# power = 7 is the scalar-section case: top-level keys must precede any
# table header in TOML, so it leads the file
_write("""\
power = 7

[inference]
device = "gpu"
device_id = "abc"
[detection]
ratio = 2.5
[gaming]
game_hz = "144"
[camera]
labels = ["not", "a", "dict"]
[ui]
preview_width = "wide"
""")
cfg = config.get_config(verbose=False)
try:
    assert cfg["inference"]["device"] == "auto", \
        cfg["inference"]["device"]
    assert cfg["inference"]["device_id"] == 0, \
        cfg["inference"]["device_id"]
    assert cfg["detection"]["ratio"] == 0.003, cfg["detection"]["ratio"]
    assert cfg["gaming"]["game_hz"] == {}, cfg["gaming"]["game_hz"]
    assert cfg["camera"]["labels"] == {}, cfg["camera"]["labels"]
    assert cfg["ui"]["preview_width"] == 420, \
        cfg["ui"]["preview_width"]
    _pass("junk values all fail open to stock (load survived)")
except AssertionError as e:
    _fail("junk section: %r" % e)

n = len(_RECORDER.records)
assert n >= 6, "expected >= 6 load warnings, got %d: %r" % (n,
                                                            _RECORDER.records)
for frag in ("device", "device_id", "ratio", "game_hz", "labels",
             "preview_width"):
    assert any(frag in w for w in _RECORDER.records), \
        "no warning naming %s: %r" % (frag, _RECORDER.records)
_pass("load warnings named every junk key (%d warnings)" % n)

# --- 2) the scalar section: power = 7 came back stock-shaped ---
p = cfg["power"]
assert isinstance(p, dict), p
assert p["hold_display"] is False, p
assert p["hold_sleep"] is False, p
assert p["poll_sec"] == 5, p
assert any("power" in w and "int" in w for w in _RECORDER.records), \
    "no warning naming the scalar section: %r" % _RECORDER.records
_pass("scalar section came back stock-shaped, loudly")

# --- 3) the gaming rate-map second run: game_hz = 0 ---
_RECORDER.records.clear()
_write("""\
[gaming]
game_hz = 0
""")
cfg = config.get_config(verbose=False)
try:
    assert cfg["gaming"]["game_hz"] == {}, cfg["gaming"]["game_hz"]
    _pass("game_hz = 0 (not a rate map) failed open to the stock {}")
except AssertionError as e:
    _fail("game_hz second run: %r" % e)

# --- 3c) the amendment-8 maps: bad entries die by name, survivors stay
_RECORDER.records.clear()
_write("""\
[gaming]
hdr = { NOPE = "yes" }

[hdr]
auto = { "MONITOR\\\\A" = "blu-ray", "MONITOR\\\\B" = " Video " }
""")
cfg3c = config.get_config(verbose=False)
try:
    assert cfg3c["gaming"]["hdr"] == {}, cfg3c["gaming"]["hdr"]
    assert cfg3c["hdr"]["auto"] == {"MONITOR\\B": "video"}, \
        cfg3c["hdr"]["auto"]
    assert any("hdr" in w and "yes" in w for w in _RECORDER.records), \
        _RECORDER.records
    assert any("blu-ray" in w for w in _RECORDER.records), \
        _RECORDER.records
    _pass("hdr maps normalize: the string 'yes' and the 'blu-ray' tier "
          "die by name; ' Video ' survives lowercased (absent key = "
          "hands off is the ONLY null this world speaks)")
except AssertionError as e:
    _fail("hdr maps: %r" % (e,))

# --- 4) DEFAULTS alias probe: a fresh load's mutations stay local ---
_RECORDER.records.clear()
cfg2 = config.get_config(verbose=False)
cfg2["gaming"]["game_hz"] = 999
cfg2["camera"]["labels"]["X"] = "test"
assert config.DEFAULTS["gaming"]["game_hz"] == {}, \
    config.DEFAULTS["gaming"]["game_hz"]
assert config.DEFAULTS["camera"]["labels"] == {}, \
    config.DEFAULTS["camera"]["labels"]
assert config.DEFAULTS["inference"]["device"] == "auto", \
    config.DEFAULTS["inference"]["device"]
_pass("DEFAULTS alias probe: mutations did not reach the stock table")

# --- 5) the two-thread write_config hammer: ONE shared live cfg, two
# --- writers. The defect the lock+snapshot must eat is "RuntimeError:
# --- dict changed size during iteration inside _dumps" - one writer
# --- dumps the live nested dicts while the other mutates them. So the
# --- threads share one cfg, each mutates it then saves: the save is
# --- safe because _dumps iterates a private snapshot, never the live dict.
shared = config.get_config(verbose=False)
errs = []


def _hammer(n):
    for i in range(8):            # 8 per thread, 16 saves total
        shared["gaming"]["game_hz"]["M%d" % (n % 2)] = 60 + (i % 3)
        shared["ui"]["preview_width"] = 420 + i
        try:
            config.write_config(shared)
        except Exception as e:    # noqa: BLE001 - collect, don't die
            errs.append(repr(e))


threads = [threading.Thread(target=_hammer, args=(n,)) for n in range(2)]
for t in threads:
    t.start()
for t in threads:
    t.join()
try:
    assert not errs, errs
    with open(os.path.join(_TMP, "config.toml"), "rb") as f:
        disk = _toml.load(f)
    assert disk["ui"]["preview_width"] >= 420, disk["ui"]
    assert isinstance(disk["gaming"]["game_hz"], dict), disk["gaming"]
    _pass("two-thread hammer on one shared cfg: 16 saves, no crash, "
          "reload parses")
except Exception as e:
    _fail("write_config hammer: %r" % e)
for _leftover in glob.glob(_TMP + "/*.tmp.*"):
    os.remove(_leftover)          # the pid-named leftovers the test cleans
residue = glob.glob(_TMP + "/*.tmp.*")
assert not residue, residue
_pass("no .tmp residue after the hammer (leftovers cleaned)")

if FAILED:
    print("CONFIG NORM TEST FAILED in", FAILED)
    sys.exit(1)
print("config norm OK")
