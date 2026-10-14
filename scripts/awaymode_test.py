"""Away mode (dim-mode wave), offline: the migration truth rows, the
substitution at the off-broadcast site, the refusal degradation, the
preview adopt-vs-revert law, and the static ban that keeps dim mode
out of the power verbs. No Tk, no display hardware, no live app.
Run from repo root:
python scripts/awaymode_test.py
"""
import logging
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import panelboss.wm as wm                                   # noqa: E402
from panelboss import config, display, profiles             # noqa: E402
from panelboss.state import PresenceMonitor                 # noqa: E402

REFUSAL = "the monitor refuses brightness (DDC/CI)"


class Recorder(logging.Handler):
    def __init__(self):
        super().__init__(logging.INFO)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


class FakeBright:
    """set() returns '' when the panel MOVES, REFUSAL when scripted;
    get() answers whatever is current (the ledger's honest prior).
    Appends to the shared call log: the restore-order assertion needs
    every source's steps in ONE chronology."""

    def __init__(self, cur=None, refuses=(), calls=None):
        self.cur = dict(cur or {})
        self.refuses = set(refuses)
        self.calls = calls if calls is not None else []

    def get(self, gdi):
        self.calls.append(("get", gdi))
        return self.cur.get(gdi)

    def set(self, gdi, pct):
        self.calls.append(("set", gdi, pct))
        if gdi in self.refuses:
            return REFUSAL
        self.cur[gdi] = pct
        return ""

    def restore(self, gdi, pct):
        self.calls.append(("restore", gdi, pct))
        self.cur[gdi] = pct


class FakeOverlay:
    def __init__(self, calls=None):
        self.calls = calls if calls is not None else []

    def show(self, gdi, rect, on_click=None):
        self.calls.append(("show", gdi, tuple(rect)))

    def hide(self, gdi):
        self.calls.append(("hide", gdi))

    def hide_all(self):
        self.calls.append(("hide_all",))


DESK = [
    {"id": "MON-A", "short": "AAA", "gdi": "D1", "x": 0, "y": 0,
     "w": 1920, "h": 1080, "rate": 60, "bits": 8, "primary": True},
    {"id": "MON-B", "short": "BBB", "gdi": "D2", "x": 1920, "y": 0,
     "w": 2560, "h": 1440, "rate": 60, "bits": 8, "primary": False},
    {"id": "MON-C", "short": "CCC", "gdi": "D3", "x": 4480, "y": 0,
     "w": 1080, "h": 1920, "rate": 60, "bits": 8, "primary": False},
]
HDRS = [
    {"gdi": "D1", "model": "MON-A", "supported": True, "state": "off",
     "precise": True},
    {"gdi": "D2", "model": "MON-B", "supported": True, "state": "on",
     "precise": True},
    {"gdi": "D3", "model": "MON-C", "supported": False, "state": "off",
     "precise": True},
]


class Ledger:
    """Patch-keeper: every fake records here and hands back an undo
    that puts the real modules to rights (the suite leaves no residue
    even when a later import lands on the patched seam)."""

    def __init__(self):
        self.calls = []
        self.saved = []

    def keep(self, obj, name, value):
        self.saved.append((obj, name, getattr(obj, name, "_absent")))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, old in reversed(self.saved):
            if old == "_absent":
                try:
                    delattr(obj, name)
                except AttributeError:
                    pass
            else:
                setattr(obj, name, old)
        self.saved = []


def make_monitor(tmp, away, bright=None, hdrs=None):
    """A PresenceMonitor with the desk, the power verbs, the input arm
    and the DDC/CI layer faked. The camera bookkeeping stays REAL
    except the two hold/rearm seams (no detector to hold)."""
    led = Ledger()
    cfg = config.get_config(dir=tmp, verbose=False)
    cfg["guards"]["fullscreen"] = False
    cfg["power"]["restore_windows"] = False
    cfg["away"] = config.normalize_away(away)
    bright = bright or FakeBright({"D1": 80, "D2": 70, "D3": 50})
    bright.calls = led.calls            # every fake writes ONE chronology
    overlay = FakeOverlay(led.calls)
    hdrs = HDRS if hdrs is None else hdrs

    def hdr_set(gdi, on):
        led.calls.append(("hdr_set", gdi, bool(on)))
        return ""

    led.keep(wm, "monitors", lambda: [dict(m) for m in DESK])
    led.keep(wm, "hdr_states", lambda: [dict(r) for r in hdrs])
    led.keep(wm, "hdr_set", hdr_set)
    led.keep(wm, "_bright", bright)          # late imports re-read these
    led.keep(wm, "_overlay", overlay)        # attrs every call
    led.keep(display, "turn_off", lambda: led.calls.append(("turn_off",)))
    led.keep(display, "wake", lambda *a, **k: led.calls.append(("wake",)))
    led.keep(display, "arm_input_lift",
             lambda armed: led.calls.append(("arm", bool(armed))))
    led.keep(display, "set_hold", lambda *a, **k: None)
    led.keep(profiles, "hdr_away_restore",
             lambda off: led.calls.append(
                 ("hdr_restore", [dict(e) for e in off])))
    led.keep(profiles, "hdr_away_off",
             lambda: led.calls.append(("hdr_away_off",)) or [])
    m = PresenceMonitor(cfg, detector=None)
    m._off_phase_hold = lambda _keep, _phase: None
    m._rearm = lambda _table: None
    m._ledger = led
    m._fake = {"calls": led.calls, "bright": bright, "overlay": overlay}
    return m


def test_migration():
    rec = Recorder()
    log = logging.getLogger("config")
    was = log.level
    log.setLevel(logging.INFO)            # root sits at WARNING here
    log.addHandler(rec)
    saved_shorts = config._live_shorts
    config._live_shorts = lambda: ["AAA", "BBB"]
    try:
        tmp = tempfile.mkdtemp(prefix="pb_away_m")
        path = os.path.join(tmp, "config.toml")
        with open(path, "w") as fh:
            fh.write("[power]\nhdr_off_when_away = true\n")
        c = config.get_config(dir=tmp, verbose=False)
        assert c["away"]["mode"] == "dim", c["away"]
        assert c["away"]["monitors"] == {"AAA": {"blackout": False},
                                         "BBB": {"blackout": False}}
        disk = open(path).read()
        assert "[away]" in disk, "the migration must persist its stamp"
        assert "hdr_off_when_away = true" in disk, "fossil readable"
        named = [l for l in rec.lines if l.startswith("away migration: AAA")]
        assert len(named) == 1, named
        print("ok - consent file migrates: rows, INFO per row, stamp on disk")

        rec.lines.clear()
        config.get_config(dir=tmp, verbose=False)
        assert not [l for l in rec.lines if "migration" in l], rec.lines
        print("ok - a stamped file hands off (idempotent)")

        tmp2 = tempfile.mkdtemp(prefix="pb_away_s")
        with open(os.path.join(tmp2, "config.toml"), "w") as fh:
            fh.write("[power]\nhold_display = true\n")
        c = config.get_config(dir=tmp2, verbose=False)
        assert c["away"]["mode"] == "off" and c["away"]["monitors"] == {}
        assert "[away]" not in open(os.path.join(tmp2,
                                                "config.toml")).read()
        print("ok - consent-silent files untouched (E-day law)")

        tmp3 = tempfile.mkdtemp(prefix="pb_away_t")
        with open(os.path.join(tmp3, "config.toml"), "w") as fh:
            fh.write("[gaming]\nhdr = { AAA = false }\n")
        c = config.get_config(dir=tmp3, verbose=False)   # parses at all?
        assert c["away"]["mode"] == "off"
        print("ok - an unknown [gaming] hdr fossil parses and waits")
    finally:
        config._live_shorts = saved_shorts
        log.removeHandler(rec)


def test_substitution():
    tmp = tempfile.mkdtemp(prefix="pb_away_d")
    away = {"mode": "dim", "monitors": {"AAA": {"blackout": True}},
            "dim_level": 12}
    m = make_monitor(tmp, away)
    try:
        m._screens_off(1.0)
        calls = m._fake["calls"]
        assert ("turn_off",) not in calls, "dim mode NEVER powers off"
        assert ("arm", True) in calls, "the lift ears armed"
        assert ("show", "D1", (0, 0, 1920, 1080)) in calls, calls
        assert ("set", "D2", 12) in calls, calls
        assert ("hdr_set", "D2", False) in calls, "a dim row's own HDR off"
        assert ("hdr_set", "D1", False) not in calls, \
            "the blackout row never touches HDR (packet's per-row rule)"
        assert not any(c[0] == "hdr_away_off" for c in calls), \
            "the global sweep belongs to the stock path"
        assert m.away_status == {"AAA": "blackout", "BBB": "dim",
                                 "CCC": "dim"}, m.away_status
        m._away_lift()
        names = [c[0] for c in calls]
        oi = names.index("hide_all")
        bi = min(i for i, n in enumerate(names) if n == "restore")
        hi = names.index("hdr_restore")
        assert oi < bi < hi, "restore order: overlay, bright, HDR"
        assert ("restore", "D2", 70) in calls, "prior answer, not a guess"
        hdr_back = [c for c in calls if c[0] == "hdr_restore"][0][1]
        assert hdr_back == [{"gdi": "D2", "model": "MON-B"}], hdr_back
        print("ok - dim mode substitutes, powers nothing, restores in order")
        m._screens_off(2.0)
        m._away_lift()
        print("ok - spell, lift, spell again (ledgers clear and refill)")
    finally:
        m._ledger.undo()


def test_stock_path():
    tmp = tempfile.mkdtemp(prefix="pb_away_o")
    m = make_monitor(tmp, {"mode": "off"})
    try:
        m._screens_off(1.0)
        calls = m._fake["calls"]
        assert ("turn_off",) in calls, "stock mode powers off"
        assert not m.away_status
        assert ("arm", True) not in calls
        m._away_lift()                        # no-op by law
        assert ("hide_all",) not in m._fake["overlay"].calls
        print("ok - stock mode is the old path, untouched")
    finally:
        m._ledger.undo()


def test_refusal_degrades():
    tmp = tempfile.mkdtemp(prefix="pb_away_r")
    bright = FakeBright({"D1": 80, "D2": 70, "D3": 50}, refuses=["D2"])
    m = make_monitor(tmp, {"mode": "dim", "monitors": {}}, bright=bright)
    try:
        m._screens_off(1.0)
        assert m.away_status["BBB"] == "blackout (%s)" % REFUSAL, \
            m.away_status
        shows = [c for c in m._fake["calls"] if c[0] == "show"]
        assert ("show", "D2", (1920, 0, 2560, 1440)) in shows, shows
        # and the spell lifts the degraded row too: the confession rode
        # the status word, the overlay came down at the wake
        m._away_lift()
        assert ("hide_all",) in m._fake["calls"]
        print("ok - a refusing panel degrades to blackout, confessed")
    finally:
        m._ledger.undo()


def test_preview_adopt_law():
    tmp = tempfile.mkdtemp(prefix="pb_away_p")
    m = make_monitor(tmp, {"mode": "dim", "monitors": {}})
    try:
        rec = m._away_apply_row(dict(DESK[1]), False, 10)
        assert rec["status"] == "dim" and m._fake["bright"].cur["D2"] == 10
        m._screens_off(5.0)                   # the real away arrives
        assert m._away_release("BBB", rec) == "adopted"
        hides = [c for c in m._fake["overlay"].calls if c[0] == "hide"]
        assert ("hide", "D2") not in hides, "adopt never un-darks a real away"
        m._away_lift()
        restores = [c for c in m._fake["bright"].calls if c[0] == "restore"]
        assert ("restore", "D2", 70) in restores, \
            "the ledger's TRUE prior hands back, not the spell's read"
        print("ok - preview folds into the real spell; the spell hands back")

        m2 = make_monitor(tmp, {"mode": "dim", "monitors": {}})
        try:
            rec2 = m2._away_apply_row(dict(DESK[2]), False, 10)
            assert m2._away_release("CCC", rec2) == "reverted"
            assert m2._fake["bright"].cur["D3"] == 50, "revert = the prior"
            print("ok - a preview alone reverts exactly its own record")
        finally:
            m2._ledger.undo()
    finally:
        m._ledger.undo()


def test_static_ban():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "panelboss", "state", "_away.py"),
               encoding="utf8").read()
    assert "display.wake(" not in src and "turn_off(" not in src, \
        "the away engine must not own a power verb"
    pwr = open(os.path.join(root, "panelboss", "state", "_power.py"),
               encoding="utf8").read()
    body = pwr[pwr.index("def _screens_off"):]
    body = body[:body.index("\n    def ")]
    guard, verb = body.index("self._away_engage()"), body.index(
        "display.turn_off()")
    assert guard < verb, "the power verb sits behind the engage guard"
    assert re.search(r"if self\._away_engage\(\):", body), "guard pinned"
    print("ok - static ban: the off path reaches the verb only un-dimmed")


def main():
    test_migration()
    test_substitution()
    test_stock_path()
    test_refusal_degrades()
    test_preview_adopt_law()
    test_static_ban()
    print("AWAYMODE TESTS OK")


if __name__ == "__main__":
    main()
