"""Portable mode, offline: the store root at every branch (no flag -> the
historic path byte-equal; flag beside a simulated frozen exe -> that folder;
unwritable -> the fallback naming BOTH paths), the routed sites (the env
seam still winning, the model root riding the door), the update honesty
(APPLY verbs unreachable behind the portable branch - source-ban school),
and the theater-bridge door classifier (absent/other/here, pure). No Tk/
registry. Run from repo root:  python scripts/portable_test.py
"""
import json, logging, os, subprocess, sys, tempfile; from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panelboss import config, inference, nmhost, portable; from panelboss.ui.window._oled import _OledMixin  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
os.environ.pop("PANELBOSS_CONFIG_DIR", None); os.environ.pop("PANELBOSS_LOG_DIR", None)   # suite owns its env
src_of = lambda rel: open(os.path.join(REPO, rel), encoding="utf-8").read()


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


def window(src, start, end): return src[src.index(start):src.index(end, src.index(start))]


def test_update_ban():
    src = src_of(os.path.join("panelboss", "ui", "window", "_general.py"))
    win = window(src, "def _update_now", "def _check_updates")
    assert win.index("portable.is_portable()") < win.index("_msi_handoff"), \
        "the APPLY route walked in front of the guard - reachable again"
    for verb in ("write_apply", "fetch_and_verify", "msiexec"):
        assert verb not in win, "%s snuck into the guarded window" % verb
    assert "webbrowser.open" in win and "RELEASE_PAGE" in win, "the branch must webbrowser the page"
    assert '"portable updates: close the app, "' in src and '"replace the folder"' in src, "the note is gone"
    print("ok - the portable branch stands before _msi_handoff; no APPLY verb lives in the guarded window; the note states the ritual")


def test_bridge_classifier():
    d = tempfile.mkdtemp(prefix="pb_bridge_")
    here = os.path.join(d, "extension", "host", "panelboss-host.exe")
    other = os.path.join(d, "msi", "panelboss-host.exe")
    mani = os.path.join(d, "host-manifest.json")
    assert nmhost.classify_bridge(None, here) == ("absent", None)
    assert nmhost.classify_bridge(mani, here) == ("absent", None)   # vanished
    open(mani, "w").write("{not json")
    assert nmhost.classify_bridge(mani, here) == ("absent", None)   # junk
    for path, want in ((other, "other"), (other.upper(), "other"), (here, "here"), (here.upper(), "here")):
        open(mani, "w", encoding="utf-8").write(json.dumps({"path": path}))
        got = nmhost.classify_bridge(mani, here)
        assert got[0] == want and (want != "other" or got[1] == path), (path, got)
    was = nmhost._REG_READ                  # the call site rides the
    was_exe = nmhost._BUNDLED_HOST_EXE      # suite's own registry seam
    try:
        nmhost._REG_READ = lambda: mani
        nmhost._BUNDLED_HOST_EXE = here
        assert nmhost.bridge_door()[0] == "here"
        nmhost._REG_READ = lambda: None
        assert nmhost.bridge_door()[0] == "absent"
    finally:
        nmhost._REG_READ = was
        nmhost._BUNDLED_HOST_EXE = was_exe
    win = window(src_of(os.path.join("panelboss", "nmhost.py")), "def classify_bridge", "def bridge_door")
    assert ".install" not in win and "install(" not in win, \
        "the classifier reached for the installer - it may only report"
    assert _OledMixin.BRIDGE_OTHER_NOTE == \
        ("the theater bridge is registered for a different PanelBoss "
         "install - the door fits one key."), _OledMixin.BRIDGE_OTHER_NOTE
    oled = src_of(os.path.join("panelboss", "ui", "window", "_oled.py"))
    assert 'text="register theater bridge"' in oled, "the label is gone"
    assert "if portable.is_portable():" in oled, "the row lost its gate"
    assert "the bridge refused: %s" in oled, "the refusal word is gone"
    print("ok - the door classifier is pure and case-insensitive; the DIFFERENT-PATH branch carries no register call; the button label and its portable gate stand in source")


if __name__ == "__main__":
    for t in (test_historic, test_flagged_layout, test_readonly_falls_back_loud, test_update_ban, test_bridge_classifier):
        t()
    subprocess.check_call([sys.executable, os.path.join(HERE, "config_writer_test.py")], stdout=subprocess.DEVNULL)
    print("ok - the config writer invariants ride unchanged under the door")
    print("PORTABLE TESTS OK")
