"""Away mode (dim-mode wave + the off-door corrections), offline: the
migration truth rows, the substitution at the off-broadcast site, the
refusal degradation AND the unverified-trust word (the two honest
halves), the vcp door's retry law, the preview adopt-vs-revert law,
the LL-hook lifecycle (the owner's mouse-lag pin: mode off never
installs, a spell installs once, a steady spell no churn, the lift
unhooks), the LOCK-ON-AWAY law (the real engage locks the session
once rows went dark; the preview, the default, and an all-refused
engage never do; a refused lock warns and stands) and its
lock-aware wake (the watcher's session-unlock ear lifts a live
spell; the lock edge says nothing), and the static ban that keeps
dim mode out of the power
verbs. No Tk, no display hardware, no live app.
Run from repo root:
python scripts/awaymode_test.py
"""
import ctypes
import ctypes.wintypes
import logging
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import panelboss.wm as wm                                   # noqa: E402
from panelboss import config, display, profiles             # noqa: E402
from panelboss.state import PresenceMonitor                 # noqa: E402
from panelboss.wm import _bright                            # noqa: E402
REFUSAL = _bright.REFUSAL        # single-sourced wording - the
NO_DOOR = _bright.NO_DOOR        # correction's whole point


class Recorder(logging.Handler):
    def __init__(self):
        super().__init__(logging.INFO)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


class FakeBright:
    """set() rides the two honest halves: ('', True) = MOVED and
    confirmed; ('', False) = SENT-and-unverified (`stays` - the
    courtesy/stay class, TRUST territory); (REFUSAL, False) = the
    SEND failed after the budget (`refuses`). get() answers whatever
    is current (the ledger's honest prior); `no_door` gdis never
    reached the handles at all - the only gray class. vcp()/
    vcp_read()/reachable() answer the off sub-mode's ladder and
    RECORD every call (the try-counting pins the engage/lift shapes;
    `vcp_refuses` is the honest-no class, `vcp_deaf` the AOC-class
    write-ACKed-power-read-deaf). Appends to the shared call log:
    the restore-order assertion needs every source's steps in ONE
    vcp_refuses is the honest-no class, `vcp_deaf` the AOC-class
    write-ACKed-power-read-deaf). Appends to the shared call log:
    the restore-order assertion needs every source's steps in ONE
    chronology."""

    VCP_POWER = _bright.VCP_POWER          # the engine reads the door's
    VCP_POWER_OFF = _bright.VCP_POWER_OFF  # constants through the
    VCP_POWER_ON = _bright.VCP_POWER_ON    # fake's surface too
    VCP_TRIES = _bright.VCP_TRIES
    CONFIRM_SLEEP_SEC = 0                  # the suite does not sleep
                                           # through the settle

    def __init__(self, cur=None, refuses=(), stays=(), no_door=(),
                 vcp_refuses=(), vcp_deaf=(), calls=None):
        self.cur = dict(cur or {})
        self.refuses = set(refuses)
        self.stays = set(stays)
        self.no_door = set(no_door)
        self.vcp_refuses = set(vcp_refuses)
        self.vcp_deaf = set(vcp_deaf)
        self.power = {}                         # (gdi, code) -> last value
        self.calls = calls if calls is not None else []

    def reachable(self, gdi):
        return gdi not in self.no_door

    def get(self, gdi):
        self.calls.append(("get", gdi))
        return self.cur.get(gdi)

    def set(self, gdi, pct):
        self.calls.append(("set", gdi, pct))
        if gdi in self.no_door:
            return NO_DOOR, False
        if gdi in self.refuses:
            return REFUSAL, False
        self.cur[gdi] = pct
        return ("", False) if gdi in self.stays else ("", True)

    def restore(self, gdi, pct):
        self.calls.append(("restore", gdi, pct))
        if gdi not in self.no_door and gdi not in self.refuses:
            self.cur[gdi] = pct

    def vcp(self, gdi, code, value, tries=_bright.VCP_TRIES):
        self.calls.append(("vcp", gdi, code, value, tries))
        if gdi in self.no_door:
            return False, NO_DOOR
        if gdi in self.vcp_refuses:
            return False, "%s (error 0xC0262582 after %d tries)" % (
                REFUSAL, tries)
        self.power[(gdi, code)] = value
        return True, ""

    def vcp_read(self, gdi, code):
        self.calls.append(("vcp_read", gdi, code))
        if (gdi, code) not in self.power or gdi in self.vcp_deaf:
            return False, None
        return True, self.power[(gdi, code)]


class FakeOverlay:
    def __init__(self, calls=None):
        self.calls = calls if calls is not None else []

    def show(self, gdi, rect, on_click=None):
        self.calls.append(("show", gdi, tuple(rect)))

    def hide(self, gdi):
        self.calls.append(("hide", gdi))

    def hide_all(self):
        self.calls.append(("hide_all",))


class FakeHookU32:
    """Records the raw-registration pair AND the LL-hook trio (which
    must NEVER be touched - the shape is gone, the pin keeps it gone).
    LockWorkStation is the lock-on-away recorder (this wave's
    extension): every call logs its answer, `lock=False` plays the
    refused class. Everything else passes through to the real user32."""

    def __init__(self, real, lock=True):
        self.real = real
        self.registers = []
        self.unregisters = []
        self.hook_calls = []           # must stay empty. the point.
        self.cursor = []               # jail's Get/SetCursorPos calls
        self.locks = []                # lock-on-away: one entry per call
        self._lock = bool(lock)        # the answer it gives from here

    def LockWorkStation(self):
        self.locks.append(self._lock)
        return self._lock

    def RegisterRawInputDevices(self, arr, n, size):
        # read the flags off the caller's array: RIDEV_REMOVE=1 means
        # this Register IS the unregister (one entry point, this OS)
        (self.unregisters if (arr and arr[0].flags == 1)
         else self.registers).append(n)
        return True

    def SetWindowsHookExW(self, *a):
        self.hook_calls.append(("set",) + a)
        return 1

    def UnhookWindowsHookEx(self, *a):
        self.hook_calls.append(("unhook",) + a)
        return True

    def CallNextHookEx(self, *a):
        self.hook_calls.append(("next",) + a)
        return 0

    def GetCursorPos(self, pt):
        self.cursor.append(("get",))
        p = ctypes.cast(pt, ctypes.POINTER(ctypes.wintypes.POINT))[0]
        p.x, p.y = 777, 431                   # the desk's saved point
        return True

    def SetCursorPos(self, x, y):
        self.cursor.append(("set", x, y))
        return True

    def __getattr__(self, name):
        return getattr(self.real, name)   # everything else rides real


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
    led.keep(display, "jail_cursor",
             lambda rect: led.calls.append(("jail", tuple(rect))))
    led.keep(display, "unjail_cursor",
             lambda: led.calls.append(("unjail",)))
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
        assert c["away"]["monitors"] == {"AAA": {"blackout": False,
                                                "off": False},
                                         "BBB": {"blackout": False,
                                                "off": False}}
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
    rec = Recorder()
    slog = logging.getLogger("state")
    was = slog.level
    slog.setLevel(logging.INFO)           # root sits at WARNING here
    slog.addHandler(rec)
    try:
        m._screens_off(1.0)
        line = [l for l in rec.lines if l.startswith("away: dim")]
        assert len(line) == 1 and "0 rows blackout-degraded" in line[0], \
            line        # a CONFIG blackout row is not a degradation
        #                   (gate finding 2: the predicate counts only
        #                   refused words, never the honest plain ones)
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
        m._screens_off(2.0)
        m._away_lift()
        print("ok - dim mode substitutes, powers nothing, restores in order")
        print("ok - spell, lift, spell again (ledgers clear and refill)")
    finally:
        slog.removeHandler(rec)
        slog.setLevel(was)
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
        rec = m._away_apply_row(dict(DESK[1]), "dim", 10)
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
            rec2 = m2._away_apply_row(dict(DESK[2]), "dim", 10)
            assert m2._away_release("CCC", rec2) == "reverted"
            assert m2._fake["bright"].cur["D3"] == 50, "revert = the prior"
            print("ok - a preview alone reverts exactly its own record")
        finally:
            m2._ledger.undo()
    finally:
        m._ledger.undo()


def test_unverified_trust():
    """The correction made testable: a write that lands and a
    readback that stays a stranger is UNVERIFIED-TRUST, not refusal -
    the row keeps its sub-mode and says so (the class this desk
    demonstrably has; wm/_bright.py's header carries the education)."""
    tmp = tempfile.mkdtemp(prefix="pb_away_u")
    bright = FakeBright({"D1": 80, "D2": 70, "D3": 50}, stays=["D3"])
    m = make_monitor(tmp, {"mode": "dim", "monitors": {}}, bright=bright)
    try:
        m._screens_off(1.0)
        assert m.away_status["CCC"] == "dim (unverified)", m.away_status
        assert m.away_status["BBB"] == "dim", m.away_status
        shows = [c for c in m._fake["calls"] if c[0] == "show"]
        assert not any(c[1] == "D3" for c in shows), \
            "an unverified DIM row wears no overlay - it stays DIM"
        m._away_lift()
        assert ("restore", "D3", 50) in m._fake["calls"], \
            "trust mode still owes the honest hand-back"
        print("ok - a deaf readback is TRUST with a word, not a blackout")
    finally:
        m._ledger.undo()


def test_vcp_retry_law():
    """Direct at the door itself (the fake-desk fakes replace _bright
    wholesale and cannot prove ITS law): a transient NAK is retried
    with the 0.3 s backoff and takes; a refusal is reported only
    after the FULL budget, error and try-count in its word."""
    class FakeTime:
        def __init__(self):
            self.slept = []

        def sleep(self, s):
            self.slept.append(s)

    class FakeK32:
        def SetLastError(self, _v):
            pass

        def GetLastError(self):
            return 0xC0262582

    class ScriptedDX:
        def __init__(self, answers):
            self.answers = list(answers)
            self.calls = []

        def SetVCPFeature(self, _h, code, value):
            self.calls.append((code, value))
            return 1 if self.answers.pop(0) else 0

    led = Ledger()
    pm = type("PM", (), {"hMonitor": 42})()
    led.keep(_bright, "_phys", lambda gdi: (0, 1, [pm]))
    led.keep(_bright, "k32", FakeK32())
    clock = FakeTime()
    led.keep(_bright, "time", clock)
    dx = ScriptedDX([False, True])           # the measured class: NAK, then take
    led.keep(_bright, "dx", dx)
    sent, why = _bright.vcp("D1", _bright.VCP_POWER, _bright.VCP_POWER_OFF)
    assert sent and why == "", (sent, why)
    assert len(dx.calls) == 2, "the transient NAK got its retry"
    assert clock.slept == [_bright.VCP_RETRY_SEC], clock.slept
    dx2 = ScriptedDX([False, False, False])
    _bright.dx = dx2
    sent, why = _bright.vcp("D1", _bright.VCP_POWER, _bright.VCP_POWER_OFF)
    assert not sent and "after 3 tries" in why and "0xC0262582" in why, why
    assert len(dx2.calls) == _bright.VCP_TRIES, "the budget was spent first"
    led.undo()
    print("ok - vcp door: transient retried at 0.3 s; refusal only after "
          "a spent budget, error and count in its word")


def test_off_submode():
    """The three panel classes (owner correction (e): the third is
    the REPLY-DEAF POWER WRITE ACCEPTED - the owner-class AOC - and
    UNVERIFIED-TRUST is its DEFAULT word, the shape this desk taught
    twice; vcp_refuses is the honest-no class, and the timestamped
    refusal is about this app's attempt, not the firmware's soul):
    the ladder's call shapes, the blackout fallback's confession,
    the unconditional D6=1 lift, and the jail."""
    tmp = tempfile.mkdtemp(prefix="pb_away_off")
    bright = FakeBright({"D1": 80, "D2": 70, "D3": 50},
                        vcp_deaf=["D2"], vcp_refuses=["D3"])
    away = {"mode": "dim",
            "monitors": {"AAA": {"mode": "off"},
                         "BBB": {"mode": "off"},
                         "CCC": {"mode": "off"}}}
    m = make_monitor(tmp, away, bright=bright)
    rec = Recorder()
    slog = logging.getLogger("state")
    was = slog.level
    slog.setLevel(logging.INFO)           # root sits at WARNING here
    slog.addHandler(rec)
    try:
        m._screens_off(1.0)
        calls = m._fake["calls"]
        assert ("vcp", "D1", 0xD6, 4, _bright.VCP_TRIES) in calls, calls
        # THE UNIVERSAL WORD (gate finding 4): the register cannot
        # certify DPMS state (dossier: it answered "on" through a
        # witnessed blackout), so no answering readback promotes a
        # row and the engage does not even traffic the bus for one.
        assert m.away_status["AAA"] == "off (unverified)", m.away_status
        assert m.away_status["BBB"] == "off (unverified)", m.away_status
        assert not any(c[0] == "vcp_read" and c[1] in ("D1", "D2")
                       for c in calls), \
            "the engage buys no register lie at the door"
        line = [l for l in rec.lines if l.startswith("away: dim")]
        assert len(line) == 1 and "3 VCP-off asked" in line[0] \
            and "1 rows blackout-degraded" in line[0], line
        assert m.away_status["CCC"].startswith(
            "off refused - blackout instead"), m.away_status
        shows = [c for c in calls if c[0] == "show"]
        assert ("show", "D3", (4480, 0, 1080, 1920)) in shows, \
            "the refused off row wears the fallback, confessed"
        assert not any(c[1] in ("D1", "D2") for c in shows), \
            "no paint on a sent-off row - the panel IS the overlay"
        assert not any(c[0] == "hdr_set" and c[1] in ("D1", "D2")
                       for c in calls), \
            "off rows ride the blackout ledger: no HDR, no brightness"
        assert not any(c[0] == "set" and c[1] in ("D1", "D2")
                       for c in calls), calls
        assert ("jail", (0, 0, 1920, 1080)) in calls, \
            "the first covered row claims the corner jail, once"
        assert sum(1 for c in calls if c[0] == "jail") == 1, calls
        m._away_lift()
        for gdi in ("D1", "D2", "D3"):
            assert ("vcp", gdi, 0xD6, 1, _bright.VCP_TRIES) in calls, \
                "the power hand-back is unconditional - even the " \
                "refused row gets it (a late NAK can hide a dark panel)"
        assert ("unjail",) in calls, "the cursor comes home with the spell"
        assert ("hide_all",) in calls
        print("ok - off sub-mode: trust word by default, refusal confessed, "
              "unconditional hand-back, jail once")
    finally:
        slog.removeHandler(rec)
        slog.setLevel(was)
        m._ledger.undo()


def test_boot_belt():
    """Gate finding 1: quit/kill mid-spell dies the in-memory ledger,
    and boot's _force_on asks it nothing. The belt asks the CONFIG:
    empty ledger, off rows set - every reachable row gets its
    idempotent D6=1 (full retry budget), never-reached rows stay
    silent, and nothing raises into boot."""
    tmp = tempfile.mkdtemp(prefix="pb_away_belt")
    bright = FakeBright({"D1": 80, "D3": 50}, no_door=["D2"])
    away = {"mode": "dim",
            "monitors": {"AAA": {"off": True}, "BBB": {"off": True},
                         "CCC": {"off": True}}}
    m = make_monitor(tmp, away, bright=bright)
    try:
        assert not getattr(m, "_away_off", None), "dead-ledger boot"
        m._away_boot_belt()
        calls = m._fake["calls"]
        assert ("vcp", "D1", 0xD6, 1, _bright.VCP_TRIES) in calls, calls
        assert ("vcp", "D3", 0xD6, 1, _bright.VCP_TRIES) in calls, calls
        assert not any(c[0] == "vcp" and c[1] == "D2" for c in calls), \
            "no door means a silent belt, not a bus fight"
        print("ok - boot belt: config rows earn their D6=1 even with a "
              "dead ledger; unreachable rows stay quiet")
    finally:
        m._ledger.undo()


def test_jail_moves_cursor():
    """The jail's own user32 pair (the engine tests fake it by
    record): park at the FAR corner once, restore the saved point,
    and go quiet afterwards - and the LL trio still never moves."""
    import panelboss.display as disp
    led = Ledger()
    fake = FakeHookU32(disp.u32)
    led.keep(disp, "u32", fake)
    try:
        assert disp.jail_cursor((1920, 0, 2560, 1440)) is True
        assert disp.jail_cursor((4480, 0, 1080, 1920)) is True  # once
        assert fake.cursor == [("get",), ("set", 1920 + 2559, 1439)], \
            fake.cursor
        disp.unjail_cursor()
        assert fake.cursor[-1] == ("set", 777, 431), fake.cursor
        disp.unjail_cursor()                       # quiet now
        assert len(fake.cursor) == 3, fake.cursor
        assert fake.hook_calls == [], "jail is not a hook, ever"
        print("ok - jail: far corner once, saved point home, silent after")
    finally:
        led.undo()


def test_off_preview_release():
    """The preview walks the SAME off row: a revert owes its own
    D6=1; an adopted preview owes none (the spell's lift pays it)."""
    tmp = tempfile.mkdtemp(prefix="pb_away_op")
    bright = FakeBright({"D1": 80, "D2": 70, "D3": 50},
                        vcp_deaf=["D2"], vcp_refuses=["D3"])
    m = make_monitor(tmp, {"mode": "dim",
                           "monitors": {"AAA": {"mode": "off"}}},
                     bright=bright)
    try:
        rec = m._away_apply_row(dict(DESK[1]), "off", 10)
        assert rec["status"] == "off (unverified)" and rec["off"] is True
        assert m._away_release("BBB", rec) == "reverted"
        assert ("vcp", "D2", 0xD6, 1, _bright.VCP_TRIES) in m._fake["calls"], \
            "the preview's own hand-back rides the same law"
        m._screens_off(5.0)                      # a real spell arrives
        rec2 = m._away_apply_row(dict(DESK[0]), "off", 10)
        assert m._away_release("AAA", rec2) == "adopted"
        offs = [c for c in m._fake["calls"] if c[0] == "vcp" and c[3] == 1
                and c[1] == "D1"]
        assert not offs, "an adopted preview never powers its panel back on"
        m._away_lift()
        assert ("vcp", "D1", 0xD6, 1, _bright.VCP_TRIES) in m._fake["calls"], \
            "the spell's lift pays the hand-back the preview skipped"
        print("ok - off preview: revert pays now, adoption defers to the lift")
    finally:
        m._ledger.undo()


def test_off_selectable_never_pregrayed():
    """The AOC must see OFF on its menu (the correction's core: my
    morning's NAK-studded probes may not pre-sentence the panel);
    gray is ONLY the never-reached class. No Tk: the card's menu
    rule is a module function."""
    from panelboss.ui.window._away import off_choice
    from panelboss.wm import _bright as _b
    aoc = FakeBright({"D1": 75})                # answers 0x10: bus proven
    assert off_choice(aoc, "D1") == ["blackout", "dim", "off"]
    dead = FakeBright({}, no_door=["DX"])       # the gray class
    assert off_choice(dead, "DX") == ["blackout", "dim"]
    assert off_choice(_b, "NO-SUCH-DISPLAY99") in (
        ["blackout", "dim", "off"], ["blackout", "dim"])  # answers per door
    print("ok - off selectable everywhere the app reached; gray only "
          "for the never-reached")


def test_lock_on_away():
    """lock-on-away (owner-ruled, 2026-10-14): a REAL engage that darked
    at least one applied row locks the workstation ONCE at its end; a
    preview, the default (no lock key), and an all-refused engage never
    do; a refused lock is a warning, never a raise into the spell."""
    import panelboss.display as disp
    tmp = tempfile.mkdtemp(prefix="pb_away_lk")
    rec = Recorder()
    slog = logging.getLogger("state")
    was = slog.level
    slog.setLevel(logging.INFO)           # root sits at WARNING here
    slog.addHandler(rec)
    try:
        # the ON shape: dim desk, lock on - and the preview half of
        # the law first: the very same row applied as a preview must
        # leave the session alone (a yank at setup time is hostility)
        m = make_monitor(tmp, {"mode": "dim", "monitors": {},
                               "lock": True})
        fake = FakeHookU32(disp.u32)
        m._ledger.keep(disp, "u32", fake)
        try:
            m._away_apply_row(dict(DESK[1]), "dim", 10)
            assert fake.locks == [], "a preview never locks"
            m._screens_off(1.0)
            assert fake.locks == [True], fake.locks
            line = [l for l in rec.lines
                    if l == "away: workstation locked (lock-on-away)"]
            assert len(line) == 1, rec.lines
            m._away_lift()
        finally:
            m._ledger.undo()
        print("ok - lock on: a real engage darking rows locks once, "
              "the preview never")

        # the default-off law: key absent = silence, no call at all
        m = make_monitor(tmp, {"mode": "dim", "monitors": {}})
        fake = FakeHookU32(disp.u32, lock=False)
        m._ledger.keep(disp, "u32", fake)
        try:
            m._screens_off(1.0)
            assert fake.locks == [], "default-off never reaches the door"
        finally:
            m._ledger.undo()
        print("ok - lock off (the default): the spell never grabs the "
              "session")

        # the all-refused engage (the shape's honest pin): every dim
        # send refused = every row DEGRADED - the painted fallback is
        # a confession, not an applied dark, so nobody locks
        bright = FakeBright({"D1": 80, "D2": 70, "D3": 50},
                            refuses=["D1", "D2", "D3"])
        m = make_monitor(tmp, {"mode": "dim", "monitors": {}, "lock": True},
                         bright=bright)
        fake = FakeHookU32(disp.u32)
        m._ledger.keep(disp, "u32", fake)
        try:
            m._screens_off(1.0)
            assert all(s.startswith("blackout (")
                       for s in m.away_status.values()), m.away_status
            assert fake.locks == [], "an all-refused engage locks nothing"
        finally:
            m._ledger.undo()
        print("ok - all-refused engage: no applied dark, no lock")

        # a refused lock (Win32 said False): warn once, stand unlocked,
        # and the spell itself is untouched (never raises)
        m = make_monitor(tmp, {"mode": "dim", "monitors": {}, "lock": True})
        fake = FakeHookU32(disp.u32, lock=False)
        m._ledger.keep(disp, "u32", fake)
        try:
            m._screens_off(1.0)
            assert fake.locks == [False], fake.locks
            warn = [l for l in rec.lines
                    if l.startswith("away:") and "lock refused" in l]
            assert len(warn) == 1, rec.lines
            assert m.away_status, "the spell stands, unlocked, honest"
            m._away_lift()
        finally:
            m._ledger.undo()
        print("ok - refused lock: warned once, the spell stands unlocked")
    finally:
        slog.removeHandler(rec)
        slog.setLevel(was)


def test_session_unlock_ear():
    """The lock-aware wake's second eye (3b landed): the watcher's
    WM_WTSSESSION_CHANGE arm IGNORES the lock edge and posts
    session_unlock on the unlock edge; the state machine's arm lifts a
    LIVE dim spell on that word, with its own log line, and goes quiet
    for a desk that is not under a spell (the stock dark answers to
    the idle gate alone)."""
    import panelboss.display as disp
    led = Ledger()
    d = disp.Display()                    # the thread never runs
    led.keep(disp, "watcher", d)          # the ears are fed by hand
    try:
        d._session_change(0x07)                       # WTS_SESSION_LOCK
        assert d.queue.empty(), "locking under a dark spell says nothing"
        d._session_change(disp.WTS_SESSION_UNLOCK)
        ev = d.queue.get_nowait()
        assert ev[0] == "session_unlock" and ev[1] == 1.0, ev
        print("ok - the ear: lock edge silent, unlock edge posts")
        m = make_monitor(tempfile.mkdtemp(prefix="pb_away_su"),
                         {"mode": "dim", "monitors": {}})
        m._ledger.keep(disp, "watcher", d)
        rec = Recorder()
        slog = logging.getLogger("state")
        was = slog.level
        slog.setLevel(logging.INFO)       # root sits at WARNING here
        slog.addHandler(rec)
        try:
            m._screens_off(1.0)
            assert m.state == "off" and m.away_status
            m._drain_display(1.5)         # the queue holds nothing yet
            assert m.away_status, "no word, no lift"
            d.queue.put(("session_unlock", 1.0, 1.5))
            m._drain_display(1.6)
            assert not m.away_status, "the unlock lifted the spell"
            named = [l for l in rec.lines
                     if l == "away: lifted on session unlock"]
            assert len(named) == 1, rec.lines
            assert ("wake",) in m._fake["calls"], "the wake seam ran"
            d.queue.put(("session_unlock", 1.0, 1.7))
            m._drain_display(1.8)         # no spell now: the word passes
            assert [l for l in rec.lines
                    if l == "away: lifted on session unlock"], "one word"
            assert len([l for l in rec.lines
                        if l == "away: lifted on session unlock"]) == 1, \
                "an unspelled desk takes the word without a lift"
            print("ok - the arm: a live spell lifts on unlock, a bare "
                  "desk ignores the word")
        finally:
            slog.removeHandler(rec)
            slog.setLevel(was)
            m._ledger.undo()
    finally:
        led.undo()


def test_static_ban():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "panelboss", "state", "_away.py"),
               encoding="utf8").read()
    assert "display.wake(" not in src and "turn_off(" not in src, \
        "the away engine must not own a power verb"
    assert "SC_MONITORPOWER" not in src and "0xF170" not in src, \
        "the off sub-mode's power is the VCP door, never the broadcast"
    pwr = open(os.path.join(root, "panelboss", "state", "_power.py"),
               encoding="utf8").read()
    body = pwr[pwr.index("def _screens_off"):]
    body = body[:body.index("\n    def ")]
    guard, verb = body.index("self._away_engage()"), body.index(
        "display.turn_off()")
    assert guard < verb, "the power verb sits behind the engage guard"
    assert re.search(r"if self\._away_engage\(\):", body), "guard pinned"
    print("ok - static ban: the off path reaches the verb only un-dimmed")


def test_hook_lifecycle():
    """The owner's mouse-lag pin (UAT, Oct 14): a mode-off desk must
    NEVER see SetWindowsHookExW - invisibility by construction, not
    by a flag check inside the callback. A dim spell installs the
    pair EXACTLY once; a steady spell never churns the chain; the
    lift sends the ears home; a new spell re-installs."""
    import panelboss.display as disp
    led = Ledger()
    fake = FakeHookU32(disp.u32)
    led.keep(disp, "u32", fake)
    led.keep(disp, "watcher", disp.watcher)
    led.keep(wm, "monitors", lambda: [dict(m) for m in DESK])
    led.keep(wm, "hdr_states", lambda: [])
    led.keep(wm, "hdr_set", lambda gdi, on: "")
    led.keep(wm, "_bright", FakeBright({"D1": 80, "D2": 70, "D3": 50}))
    led.keep(wm, "_overlay", FakeOverlay())
    led.keep(profiles, "hdr_away_restore", lambda off: None)
    tmp = tempfile.mkdtemp(prefix="pb_away_h")
    cfg = config.get_config(dir=tmp, verbose=False)
    cfg["guards"]["fullscreen"] = False
    cfg["power"]["restore_windows"] = False
    m = PresenceMonitor(cfg, detector=None)
    m._off_phase_hold = lambda _keep, _phase: None
    m._rearm = lambda _table: None
    d = disp.Display()                        # the thread never runs:
    disp.watcher = d                          # the pump is called by hand
    try:
        assert m._away_engage() == {}         # stock mode, the default law
        assert d._pump_pause() == disp.IDLE_PAUSE_SEC, "deaf and noteless"
        d._service_ears()
        d._service_ears()
        assert fake.registers == [], fake.registers
        assert fake.hook_calls == [], "the LL chain is gone for good"
        print("ok - mode off NEVER registers the ears (no tax, ever)")
        m.cfg["away"] = {"mode": "dim", "monitors": {}, "dim_level": 10}
        m._away_engage()
        assert d._pump_pause() == disp.ARMED_PAUSE_SEC, \
            "a note in flight already quickens the pump"
        d._service_ears()
        assert d._pump_pause() == disp.ARMED_PAUSE_SEC, \
            "live ears pump at input latency"
        assert fake.registers == [2], fake.registers      # mouse+keyboard
        d._service_ears()
        d._service_ears()
        assert len(fake.registers) == 1, \
            "a steady spell never re-registers"
        assert d._lift_armed is True
        m._away_lift()
        d._service_ears()
        assert fake.unregisters == [2] and d._hooked is False
        assert d._pump_pause() == disp.IDLE_PAUSE_SEC, \
            "the lift returns the loop to its deep sleep"
        m._away_engage()
        d._service_ears()
        assert len(fake.registers) == 2, "a new spell earns new ears"
        m._away_lift()
        d._service_ears()
        assert len(fake.unregisters) == 2
        print("ok - spell registers once, steady no churn, lift "
              "unregisters, re-spell re-registers")
        print("ok - cadence: armed (or noting) pumps at 20 ms, deaf at "
              "100 ms - and the LL trio is never touched")
        assert fake.hook_calls == [], "the tombstone: no phase, ever"
    finally:
        led.undo()


def test_row_shorthands():
    """Every accepted row shape folds to the pair (the off key is
    YOUNG - it migrates by never having needed migration)."""
    n = config.normalize_away
    assert n({"mode": "dim", "monitors": {"A": "off"}})["monitors"] == \
        {"A": {"blackout": False, "off": True}}
    assert n({"mode": "dim",
              "monitors": {"A": {"mode": "blackout"}}})["monitors"] == \
        {"A": {"blackout": True, "off": False}}
    assert n({"mode": "dim", "monitors": {"A": True}})["monitors"] == \
        {"A": {"blackout": True, "off": False}}
    assert n({"mode": "dim", "monitors": {"A": "sideways"}})["monitors"] \
        == {}                      # warned, dropped, dim default
    assert n({"mode": "dim",
              "monitors": {"A": {"mode": "sideways"}}})["monitors"] == \
        {"A": {"blackout": False, "off": False}}    # the dict branch
    #                                    answers with the SAME honesty
    #                                    (gate finding 5a): warn, fold
    #                                    to dim, name the row
    print("ok - row shorthands fold to the pair shape losslessly")


def main():
    test_migration()
    test_row_shorthands()
    test_substitution()
    test_stock_path()
    test_refusal_degrades()
    test_unverified_trust()
    test_vcp_retry_law()
    test_off_submode()
    test_boot_belt()
    test_jail_moves_cursor()
    test_off_preview_release()
    test_off_selectable_never_pregrayed()
    test_preview_adopt_law()
    test_lock_on_away()
    test_session_unlock_ear()
    test_hook_lifecycle()
    test_static_ban()
    print("AWAYMODE TESTS OK")


if __name__ == "__main__":
    main()
