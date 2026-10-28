"""Portable mode, offline: the store root at every branch (no flag -> the
historic path byte-equal; flag beside a simulated frozen exe -> that folder;
unwritable -> the fallback naming BOTH paths), and the routed sites (the env
seam still winning, the model root riding the door). No Tk/registry. Run
from repo root:  python scripts/portable_test.py
"""
import logging, os, subprocess, sys, tempfile; from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panelboss import config, inference, portable  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.pop("PANELBOSS_CONFIG_DIR", None); os.environ.pop("PANELBOSS_LOG_DIR", None)   # suite owns its env


class Recorder(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING); self.lines = []

    def emit(self, record): self.lines.append(record.getMessage())


def decide(d):
    """root()/is_portable()/replay() + the routed doors under a SIMULATED
    frozen pair (the fake exe lives in d; the dev tree's flagged root is
    the REAL repo, untouched). Returns the five answers; cache/sys undo."""
    saved = (portable._root, portable._portable, portable._pending,
             getattr(sys, "frozen", False), sys.executable)
    portable._root = portable._portable = portable._pending = None
    rec = Recorder()
    plog = logging.getLogger("portable")
    plog.addHandler(rec)
    try:
        sys.frozen = True; sys.executable = os.path.join(d, "PanelBoss.exe")
        got = portable.root(); portable.replay()
        return (got, portable.is_portable(), rec.lines,
                inference._default_models_root(), config._store_dir())
    finally:
        plog.removeHandler(rec)
        portable._root, portable._portable, portable._pending = saved[:3]
        sys.executable = saved[4]
        if saved[3]: sys.frozen = True
        elif hasattr(sys, "frozen"): del sys.frozen


def historic():
    appdata = os.environ.get("APPDATA")
    return Path(appdata) / "PanelBoss" if appdata else Path.home() / ".config" / "PanelBoss"


def test_historic():
    assert str(portable.root()) == str(historic()), portable.root()
    assert portable.is_portable() is False
    assert config._store_dir() == str(portable.root())
    assert config.LOG_DIR == os.path.join(config.CONFIG_DIR, "logs")
    print("ok - no flag: the store root is the historic path, byte-equal to the pre-portable expression, CONFIG_DIR/LOG_DIR follow")


def test_flagged_layout():
    d = tempfile.mkdtemp(prefix="pb_port_")
    Path(d, portable.FLAG).write_text("")
    try:
        got, flag, warns, models, store = decide(d)
        assert got == Path(d) and flag is True, (got, flag)
        assert store == d and warns == [], (store, warns)
        assert not Path(d, portable.WTEST).exists(), "the probe left residue"
        assert models == os.path.join(d, "models"), models
        os.environ["PANELBOSS_CONFIG_DIR"] = os.path.join(d, "env")
        assert config._store_dir() == os.path.join(d, "env"), "the env seam stopped winning"
        print("ok - the flag beside the exe: store root = that folder, models ride it, PANELBOSS_CONFIG_DIR still wins")
    finally:
        os.environ.pop("PANELBOSS_CONFIG_DIR", None)


def test_readonly_falls_back_loud():
    d = tempfile.mkdtemp(prefix="pb_port_ro_")
    Path(d, portable.FLAG).write_text("")
    Path(d, portable.WTEST).mkdir()   # the read-only class, played by a
    got, flag, warns, _m, store = decide(d)   # DIRECTORY in the probe's name
    assert got == historic() and flag is False, (got, flag)
    assert store == str(historic()) and len(warns) == 1, (store, warns)
    assert "not writable" in warns[0] and str(Path(d)) in warns[0] \
        and str(historic()) in warns[0], "the word names both paths: %r" % warns
    print("ok - an unwritable flagged folder falls back to APPDATA with one warning naming both paths (the app lives)")


if __name__ == "__main__":
    for t in (test_historic, test_flagged_layout, test_readonly_falls_back_loud):
        t()
    subprocess.check_call([sys.executable, os.path.join(HERE, "config_writer_test.py")], stdout=subprocess.DEVNULL)
    print("ok - the config writer invariants ride unchanged under the door")
    print("PORTABLE TESTS OK")
