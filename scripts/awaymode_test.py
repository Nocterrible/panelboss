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
spell; the lock edge says nothing), the TWO OFF FLAVORS (the D6
trust word vs the disconnect's PROVEN word; the marshal exact on a
fake CCD - PATH-MINUS, validate-gated, the measured 0x6A0, SAVE on
every write, wrong-victim self-restore, EDID-token join over the
lying gdi slot - and the boot belt's second door; the gate-fix
words: wrong-victim vs verify-blind vs slot/token DISAGREEMENT as
three honest classes, the belt's two try-blocks, and the lock
predicate as a WHITELIST; the PREVIEW WORD SEAM (menu labels map
to engine words, the fall-through confesses, and the restore's
verify earned the same patience the retract's won against a slow
store), and the static ban that keeps
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
    BELT_STAGGER_SEC = _bright.BELT_STAGGER_SEC

    def settle_left(self):        # the door's public window query:
        v = getattr(self, "_settle_once", 0.0)        # the round-2 pins script exactly
        self._settle_once = 0.0        # ONE answer - a waiting write
        return v        # re-asks into a quiet bus
   # the belt's spacing,
                                                  # same surface law
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


class FakeSDC:
    """The wm._sdc MODULE fake (the suite patches it exactly like
    _bright: led.keep(wm, "_sdc", fake) and the engine's late imports
    re-read the attribute every call). The victim-map injects the
    desk's truths: `victim` maps EDID short -> target key (None =
    no path answers; the string "WRONG" = the dossier's accepted-
    but-a-DIFFERENT-panel-left shape, which the real module answers
    with its own restore before reporting). `active` is the store's
    live set - the retract removes, the revive raises. Every call is
    recorded; the restored RECORD rides the log so the hand-back law
    is countable."""

    def __init__(self, victim=None, active=()):
        self.victim = dict(victim or {})
        self.active = set(active)
        self.retracts = []                 # row shorts, in call order
        self.restores = []                 # the record each owed it
        self.revives = []                  # the belt's rows

    def retract(self, m):
        self.retracts.append(m["short"])
        key = self.victim.get(m["short"])
        if key is None:
            return False, "no CCD path answers this row"
        if key == "WRONG":
            self.restores.append({"selfrestore": m["short"]})
            return False, "no-drop rc 0x0 (wrong victim; restored)"
        self.active.discard(key)
        return True, {"paths": b"P" * 72, "modes": b"", "victim": {key},
                      "at": 1.0}

    def restore(self, saved):
        self.restores.append(saved)
        return True, ""

    def revive(self, row):
        self.revives.append(row)
        key = self.victim.get(row["short"])
        if key is None or key == "WRONG" or key in self.active:
            return None                    # lit, or nothing to answer
        self.active.add(key)
        return True, "rc 0x0 gle=0"


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


def make_monitor(tmp, away, bright=None, hdrs=None, sdc=None,
                 remote=False):
    """A PresenceMonitor with the desk, the power verbs, the input arm,
    the DDC/CI layer, the CCD door and the SESSION TRANSPORT fake
    (remote=False/True/None - the query's answer; the suite owns its
    desk's truth: the box that RUNS the gauntlet may itself live in an
    RDP session, and the real query would then exempt every row.
    The sdc fake rides the same late-import re-read law as _bright -
    offdisc rows talk to m._fake["sdc"]). The camera bookkeeping stays REAL
    except the two hold/rearm seams (no detector to hold)."""
    led = Ledger()
    cfg = config.get_config(dir=tmp, verbose=False)
    cfg["guards"]["fullscreen"] = False
    cfg["power"]["restore_windows"] = False
    cfg["away"] = config.normalize_away(away)
    bright = bright or FakeBright({"D1": 80, "D2": 70, "D3": 50})
    bright.calls = led.calls            # every fake writes ONE chronology
    overlay = FakeOverlay(led.calls)
    sdc = sdc or FakeSDC()
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
    led.keep(display, "park_cursor",
             lambda x, y: led.calls.append(("park", int(x), int(y))))
    led.keep(display, "set_hold", lambda *a, **k: None)
    led.keep(wm, "_sdc", sdc)               # the offdisc door, faked
    #                              like _bright: the engine re-reads
    #                              the attribute on every late import
    led.keep(wm, "session_is_remote", lambda: remote)  # the transport
    #                              answer: the gauntlet's own box may
    #                              BE an RDP session - the suite owns
    #                              its desk's truth, never the host's
    led.keep(profiles, "hdr_away_restore",
             lambda off: led.calls.append(
                 ("hdr_restore", [dict(e) for e in off])))
    led.keep(profiles, "hdr_away_off",
             lambda: led.calls.append(("hdr_away_off",)) or [])
    m = PresenceMonitor(cfg, detector=None)
    m._off_phase_hold = lambda _keep, _phase: None
    m._rearm = lambda _table: None
    m._ledger = led
    m._fake = {"calls": led.calls, "bright": bright, "overlay": overlay,
               "sdc": sdc}
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
                                                "off": False,
                                                "offdisc": False},
                                         "BBB": {"blackout": False,
                                                 "off": False,
                                                 "offdisc": False}}
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
        # the Oct-22 default flip: the unset-row default word is
        # "offdisc" (the card's selector is dead; the key lives as
        # the row-fallback word)
        assert c["away"]["mode"] == "offdisc" \
            and c["away"]["monitors"] == {}
        assert "[away]" not in open(os.path.join(tmp2,
                                                "config.toml")).read()
        print("ok - consent-silent files untouched (E-day law)")

        tmp3 = tempfile.mkdtemp(prefix="pb_away_t")
        with open(os.path.join(tmp3, "config.toml"), "w") as fh:
            fh.write("[gaming]\nhdr = { AAA = false }\n")
        c = config.get_config(dir=tmp3, verbose=False)   # parses at all?
        assert c["away"]["mode"] == "offdisc"
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
        line = [l for l in rec.lines if l.startswith("away: dark")]
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


def test_remote_desk_exempt():
    """THE REMOTE-DESK STAND-DOWN (the owner's black remote screen,
    Oct 15): a row is exempt from EVERY off leg - off, offdisc AND
    the blackout-degradation paint - whenever its bus root says
    virtual or the session answers remote. D6-attempt-once is
    REJECTED by measurement (the fake DDC bus ACKs and LIES:
    reachable=True, nphys=1): an attempt that looks like success and
    leaves a dead canvas is the exact bug class. The exemption rides
    the None-row leg verbatim (hide the cover, touch no door) with
    its own sibling word; the refused query (None) is NOT remote."""
    tmp = tempfile.mkdtemp(prefix="pb_away_rx")
    vdesk = [dict(m, virtual=(m["short"] == "AAA")) for m in DESK]
    sdc = FakeSDC(victim={"AAA": "T-A", "BBB": "T-B"}, active={"T-A",
                                                               "T-B"})
    # a virtual row configured the hardest way possible (offdisc
    # beats off): the legs must still stand down, the word says so
    m = make_monitor(tmp, {"mode": "dim",
                           "monitors": {"AAA": {"mode": "offdisc"},
                                        "BBB": {"mode": "off"}}},
                     sdc=sdc)
    try:
        m._ledger.keep(wm, "monitors", lambda: [dict(r) for r in vdesk])
        m._screens_off(1.0)
        assert m.away_status["AAA"] == "exempt (virtual/remote)", \
            m.away_status
        assert m.away_status["BBB"] == "off (unverified)", m.away_status
        assert sdc.retracts == [], "the fake bus never heard a retraction"
        assert not [c for c in m._fake["calls"] if c[0] == "vcp"
                    and c[1] == "D1"], "no D6 on the virtual row either"
        assert m.state == "off" and not sdc.revives
        print("ok - the virtual row stands down every off leg; its "
              "neighbor's legs ride on")
        m._away_lift()
        # ALL rows exempt (the remote session exempts the whole desk):
        # the engage returns the exemption dict - and the stock path
        # skips the SC_MONITORPOWER broadcast too (no painting into
        # nothing)
        m2 = make_monitor(tmp, {"mode": "off", "monitors": {}},
                          sdc=sdc, remote=True)
        try:
            m2._screens_off(2.0)
            assert set(m2.away_status.values()) == {"exempt (virtual/remote)"}, \
                m2.away_status
            calls = m2._fake["calls"]
            assert ("turn_off",) not in calls, \
                "the remote desk skipped the broadcast"
            assert not [c for c in calls if c[0] in ("get", "set",
                                                     "vcp", "show")], \
                "no painting, no door, no code on a remote desk"
            assert m2.state == "off", "the spell still counts as dark"
            print("ok - a remote session exempts the WHOLE desk and "
                  "the stock broadcast stands down too")
            m2._away_lift()
            # a REFUSED query (None) is unknown, not remote: the
            # physical desk keeps its dark (the belt's own religion -
            # unknown never grants the exemption)
            m3 = make_monitor(tmp, {"mode": "dim", "monitors": {}},
                              remote=None)
            try:
                m3._screens_off(3.0)
                assert set(m3.away_status.values()) == {"dim"}, \
                    m3.away_status
                print("ok - a refused session query does not exempt: "
                      "unknown is not remote")
            finally:
                m3._ledger.undo()
            # THE BELT READS THE FLAG TOO: the boot power-on and the
            # disconnect-restore both skip the virtual row (the door
            # is a lie; the belt that knocks on a lie is the bug)
            m4 = make_monitor(tmp, {"mode": "dim",
                                    "monitors": {"AAA": {"mode": "off"},
                                                 "BBB": {"mode": "offdisc"}}},
                              sdc=sdc)
            try:
                m4._ledger.keep(wm, "monitors",
                                lambda: [dict(r) for r in vdesk])
                m4._away_boot_belt()
                assert not [c for c in m4._fake["calls"]
                            if c[0] == "vcp" and c[1] == "D1"], \
                    "the belt sent no power code to the virtual row"
                assert not [r for r in sdc.revives
                            if r["short"] == "AAA"], sdc.revives
                print("ok - the belt's two doors both stand down on the "
                      "virtual row (flag) - no code, no revive")
            finally:
                m4._ledger.undo()
        finally:
            m2._ledger.undo()
    finally:
        m._ledger.undo()


def test_legacy_global_off_fallback():
    """The owner ruling, Oct 22: the global key is a fallback WORD,
    not a switch - a legacy file saying mode="off" feeds the row word
    "off" (the VCP door, byte-identical behavior of that word) to
    every unset row. The SC_MONITORPOWER broadcast survives only for
    the empty desk (and the fossil there stays honored)."""
    tmp = tempfile.mkdtemp(prefix="pb_away_o")
    m = make_monitor(tmp, {"mode": "off"})
    try:
        m._screens_off(1.0)
        calls = m._fake["calls"]
        assert ("turn_off",) not in calls, \
            "the away engine owns the dark on a desk with rows"
        for gdi in ("D1", "D2", "D3"):
            assert ("vcp", gdi, 0xD6, 4, _bright.VCP_TRIES) in calls, \
                "the legacy word still means the VCP door, byte-for-byte"
        assert set(m.away_status.values()) == {"off (unverified)"}
        assert ("arm", True) in calls
        m._away_lift()
        print('ok - legacy global mode="off": the rows speak, the '
              "broadcast stands down")
        # the empty desk keeps the old path verbatim (fossil honored)
        m._ledger.keep(wm, "monitors", lambda: [])
        m._screens_off(9.0)
        assert ("turn_off",) in m._fake["calls"], \
            "a desk with no rows still takes the stock broadcast"
        print("ok - the empty desk answers the broadcast")
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
        """The door's SETTLE gate reads time.monotonic() at every
        entry (Oct 19 wave), so the clock fake carries the contract:
        monotonic steps forward with headroom past any window the
        failure path's invalidate re-arms (the import seed itself is
        closed by the pinned _settle_until below)."""
        def __init__(self):
            self.slept = []
            self.now = 1000.0

        def sleep(self, s):
            self.slept.append(s)

        def monotonic(self):
            self.now += 10.0          # every read lands past a 5 s
            return self.now           # re-arm: the window never gates
                                      # this pin's own retry law

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
    led.keep(_bright, "_settle_until", 0.0)     # the gate is a law of
    #                              its own (bright_door_test pins it);
    #                              this pin rides the retry budget
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
        line = [l for l in rec.lines if l.startswith("away: dark")]
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
    silent, and nothing raises into boot. The stagger seam is faked
    here too: the belt law's sleeps must not burn real CI seconds."""
    tmp = tempfile.mkdtemp(prefix="pb_away_belt")
    bright = FakeBright({"D1": 80, "D3": 50}, no_door=["D2"])
    away = {"mode": "dim",
            "monitors": {"AAA": {"off": True}, "BBB": {"off": True},
                         "CCC": {"off": True}}}
    m = make_monitor(tmp, away, bright=bright)
    from panelboss.state import _away as away_mod
    m._ledger.keep(away_mod, "_bus_sleep", lambda s: None)
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


def test_belt_stagger():
    """The door wave (captain's law, Oct 19): three off rows on three
    live doors get TWO stagger sleeps between the asks - counted on
    rows ASKED, never on rows walked (skips buy the bus no second) -
    recorded through the _bus_sleep seam, so no real second passes."""
    tmp = tempfile.mkdtemp(prefix="pb_away_stagger")
    away = {"mode": "dim",
            "monitors": {"AAA": {"off": True}, "BBB": {"off": True},
                         "CCC": {"off": True}}}
    m = make_monitor(tmp, away)            # the default fake: 3 doors
    from panelboss.state import _away as away_mod
    sleeps = []
    m._ledger.keep(away_mod, "_bus_sleep", lambda s: sleeps.append(s))
    try:
        m._away_boot_belt()
        assert sleeps == [1.5, 1.5], sleeps
        assert sleeps == [_bright.BELT_STAGGER_SEC] * 2, \
            "the belt rides the door's constant"
        print("ok - belt stagger: three asks, two 1.5 s spacings through "
              "the seam, no real time spent")
    finally:
        m._ledger.undo()


def test_belt_waits_settle():
    """Round-2 handback law (gate): the belt waits the settle window
    OUT before its asks - neither the import seed nor a prior row's
    refusal may swallow later rows. One scripted settle_left answer
    (the door fake's round-2 seam) proves the wait happens once,
    BEFORE the stagger, and both rows still reach the quiet bus."""
    tmp = tempfile.mkdtemp(prefix="pb_away_settle")
    away = {"mode": "dim",
            "monitors": {"AAA": {"off": True}, "CCC": {"off": True}}}
    m = make_monitor(tmp, away)
    m._fake["bright"]._settle_once = 3.0
    from panelboss.state import _away as away_mod
    sleeps = []
    m._ledger.keep(away_mod, "_bus_sleep", lambda s: sleeps.append(s))
    try:
        m._away_boot_belt()
        assert sleeps == [3.05, 1.5], sleeps
        calls = m._fake["calls"]
        assert ("vcp", "D1", 0xD6, 1, _bright.VCP_TRIES) in calls, calls
        assert ("vcp", "D3", 0xD6, 1, _bright.VCP_TRIES) in calls, calls
        print("ok - belt: the settle wait precedes the stagger; both "
              "rows reach a quiet bus")
    finally:
        m._ledger.undo()


def test_handback_waits_settle():
    """The lift's D6=1 is the ONLY way back for an offed panel (the
    asymmetry law's own words) - and the wake arms the window it
    would be swallowed by (powering panels ARE a display change).
    Round 2: the lift waits the window out, sends once more, and the
    ledgers still clear unconditionally."""
    tmp = tempfile.mkdtemp(prefix="pb_away_hw")
    m = make_monitor(tmp, {"mode": "dim"})
    m._fake["bright"]._settle_once = 2.0
    from panelboss.state import _away as away_mod
    sleeps = []
    m._ledger.keep(away_mod, "_bus_sleep", lambda s: sleeps.append(s))
    try:
        m.away_status = {"AAA": "off (unverified)"}
        m._away_off = {"D1": 1.0}
        m._away_lift()
        assert sleeps == [2.05], sleeps
        assert ("vcp", "D1", 0xD6, 1, _bright.VCP_TRIES) in \
            m._fake["calls"], m._fake["calls"]
        assert m._away_off == {}, "the ledger clears whatever happened"
        print("ok - lift: the wake's echo cannot swallow the one-shot "
              "hand-back - the wait comes first")
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
    gray is ONLY the never-reached class - and gray reaches the D6
    flavor alone: the DISCONNECT rides the adapter's CCD door, needs
    no DDC/CI, and is offered everywhere (a refused sdc leg keeps
    the choice too - the dated word is the state machine, gray would
    be pre-judgment). No Tk: the card's menu rule is a module
    function."""
    from panelboss.ui.window._away import (
        off_choice, DISC_TEXT, DDC_TEXT, MODE_BY_LABEL, preview_label)
    import panelboss.ui.window._away as _am
    from panelboss.wm import _bright as _b
    aoc = FakeBright({"D1": 75})                # answers 0x10: bus proven
    assert off_choice(aoc, "D1") == ["dim", DDC_TEXT, DISC_TEXT, "blackout"]
    dead = FakeBright({}, no_door=["DX"])       # the gray class - D6 only
    assert off_choice(dead, "DX") == ["dim", DISC_TEXT, "blackout"]
    assert DISC_TEXT == "off (disconnect)"     # the shipped label
    assert DDC_TEXT == "off (DDC fast)"        # the FILE word stays "off"
    assert set(MODE_BY_LABEL) == set(off_choice(aoc, "D1"))
    assert MODE_BY_LABEL[DDC_TEXT] == "off"    # byte-identical word
    assert DISC_TEXT in off_choice(_b, "NO-SUCH-DISPLAY99")  # answers
    #                                          per door for D6, always
    #                                          offers the disconnect
    # THE PREVIEW LABEL CARRIES ITS OWN DURATION (owner law, Oct 22):
    # derived from PREVIEW_SEC - the fake-constant swap proves the
    # seam (a literal "15s" beside a 10 s timer fails this pin).
    assert preview_label() == "preview (%ds)" % _am.PREVIEW_SEC
    _was, _am.PREVIEW_SEC = _am.PREVIEW_SEC, 15
    try:
        assert preview_label() == "preview (15s)"
    finally:
        _am.PREVIEW_SEC = _was
    assert "threading.Timer(PREVIEW_SEC" in open(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
            __file__))), "panelboss", "ui", "window",
        "_away.py"), encoding="utf8").read(), \
        "the timer left the constant the label rides"
    print("ok - off selectable everywhere the app reached; gray only "
          "for the never-reached; the disconnect is everywhere; the "
          "preview label follows its constant")


def test_nvidia_vendor_gate():
    """THE LAUNCH GATE (owner ruling at 08:2x, Oct 23, decided at the
    dump pile): 'off (DDC fast)' is kernel-freeze-adjacent on NVIDIA
    drivers (0x133 DPC_WATCHDOG, published NVIDIA bucket
    0x133_ISR_nvlddmkm) - an NVIDIA desk must not be able to ENABLE
    it, while AMD (and everyone without an NVIDIA adapter) keeps the
    button. The faked-vendor legs, no Tk: the probe's truth table
    (NVIDIA / AMD / hybrid / fail-closed - the wound KILLS, so a scan
    that cannot prove innocence answers True, the pump's fail-open
    inverted), the block text pinned as the OWNER'S OWN data, and
    the ENGINE ignorant of the gate: an off:True row under a faked
    NVIDIA scan still resolves 'off' and still spends the VCP trio
    (the config is the escape hatch for the bug's survivors), and
    the card's mirror still answers the LABEL - a configured-off row
    rides SELECTED under the gray (gray not lie, the hold rows'
    precedent). The widget halves - the disabled state, the swapped
    tip, the selected-and-gray honesty - ride the built card in
    window_boot_test."""
    from panelboss.ui.window._away import (
        _AwayMixin, DDC_TEXT, DDC_NVIDIA_TIP, DDC_BLOCKED_SUFFIX,
        DDC_BLOCKED_LABEL)
    # (a) the block text, verbatim owner words, pinned as data:
    assert DDC_NVIDIA_TIP == (
        "disabled on nvidia drivers while a kernel DPC-watchdog bug "
        "freezes panels resuming over DDC/CI - returns when the "
        "vendor patches. off (disconnect) darkens the same way.")
    # the label verdict (amendment 3, shape endorsed off the desk
    # shot): the suffix is data, the state key stays the plain word
    assert DDC_BLOCKED_SUFFIX == " - this driver blocks it"
    assert DDC_BLOCKED_LABEL == DDC_TEXT + DDC_BLOCKED_SUFFIX

    # (b) the probe's truth table: a scripted adapter walk behind the
    # same facade seam every suite patch rides (wm.u32 fans out).
    class _Walk:
        def __init__(self, rows, raise_at=None):
            self.rows = list(rows)
            self.raise_at = raise_at

        def EnumDisplayDevicesW(self, dev, i, pdev, flags):
            if i == self.raise_at:
                raise OSError("the desk went out from under the walk")
            if i >= len(self.rows):
                return 0
            d = ctypes.cast(pdev, ctypes.POINTER(wm.DISPLAY_DEVICEW))\
                .contents
            d.DeviceString = self.rows[i]
            d.StateFlags = 1                # attached - the walk
            #                              reads no flags: a parked
            #                              row is still that driver
            return 1

    led = Ledger()
    try:
        led.keep(wm, "u32", _Walk(["NVIDIA GeForce RTX 5090"]))
        assert wm.display_vendor_is_nvidia() is True, \
            "one adapter naming NVIDIA is the desk's verdict"
        led.keep(wm, "u32", _Walk(["Intel UHD 770", "nvidia GeForce "
                                               "GTX 1650"]))
        assert wm.display_vendor_is_nvidia() is True, \
            "the hybrid desk matches on its dGPU row even with the " \
            "panel on the iGPU (conservative by design)"
        led.keep(wm, "u32", _Walk(["AMD Radeon RX 7900",
                                   "Microsoft Basic Render Driver"]))
        assert wm.display_vendor_is_nvidia() is False, \
            "AMD keeps the button"
        led.keep(wm, "u32", _Walk([]))
        assert wm.display_vendor_is_nvidia() is True, \
            "zero adapters proves nothing: fail-CLOSED"
        led.keep(wm, "u32", _Walk(["AMD Radeon RX 7900"], raise_at=0))
        assert wm.display_vendor_is_nvidia() is True, \
            "a scan that dies mid-walk is not innocence: fail-closed"
    finally:
        led.undo()
    # (b2) THE GATE SPEAKS TO THE LOG (owner question at the desk,
    # amendment 3: 'also app writes anything about it to log?'): one
    # INFO per card build/refresh at the probe seam, the VERDICT
    # NAMED - a user's %APPDATA%\PanelBoss log answers 'why is that
    # button gray' without a repro. The three lines are the owner's,
    # pinned verbatim.
    import panelboss.ui.window._away as _am
    rec = Recorder()
    uilog = logging.getLogger("ui")
    was = uilog.level
    uilog.setLevel(logging.INFO)
    uilog.addHandler(rec)
    led3 = Ledger()
    try:
        led3.keep(wm, "display_vendor_scan", lambda: "nvidia")
        assert _am.vendor_gate() is True
        assert ("vendor gate: NVIDIA display driver present - off "
                "(DDC fast) blocked in UI (config word still honored)"
                ) in rec.lines, rec.lines
        led3.keep(wm, "display_vendor_scan", lambda: "fail")
        assert _am.vendor_gate() is True
        assert ("vendor gate: driver scan failed - off (DDC fast) "
                "blocked (fail-closed)") in rec.lines, rec.lines
        led3.keep(wm, "display_vendor_scan", lambda: "clear")
        assert _am.vendor_gate() is False
        assert ("vendor gate: no NVIDIA adapter found - off (DDC "
                "fast) available") in rec.lines, rec.lines
    finally:
        uilog.removeHandler(rec)
        uilog.setLevel(was)
        led3.undo()
    # (c) the engine is ignorant of the gate: under a faked NVIDIA
    # answer the off row still resolves 'off' and the VCP trio still
    # runs; the card mirror still answers the LABEL (the grayed
    # segment rides selected, not deselected).
    tmp = tempfile.mkdtemp(prefix="pb_away_nvg")
    led2 = Ledger()
    led2.keep(wm, "display_vendor_is_nvidia", lambda: True)
    m = make_monitor(tmp, {"mode": "dim", "monitors": {
        "AAA": {"blackout": False, "off": True, "offdisc": False}}})
    try:
        rec = m._away_apply_row(dict(DESK[0]), "off", 10)
        assert rec["status"].startswith("off"), rec
        assert any(c[0] == "vcp" for c in m._fake["calls"]), \
            "a faked-NVIDIA desk still spends the power codes - the " \
            "gate is UI-only, the config is the escape hatch"
        stub = type("S", (), {"cfg": m.cfg})()
        assert _AwayMixin._away_row_mode(stub, "AAA") == DDC_TEXT, \
            "the card still answers the label: selected under gray"
        print("ok - launch gate: probe answers NVIDIA/AMD/fail-closed, "
              "the block text is the owner's data, and the engine and "
              "the card mirror stay ignorant of the gate")
    finally:
        m._ledger.undo()
        led2.undo()


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
        d._session_change(disp.WTS_REMOTE_CONNECT, 5)   # transport flip
        ev = d.queue.get_nowait()    # (lParam carries the sessionId):
        assert ev[0] == "displaychange", ev     # the desk re-derives
        print("ok - the ear: lock edge silent, unlock edge posts, the "
              "transport flips re-derive the desk")
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


class FakeDesk:
    """The REAL wm/_sdc's FFI trio replaced by a fake CCD: three paths
    (targets 11/12/13, gdi slots DISPLAY1/2/3, EDID model tokens
    DELA283/AOC2790/IOC912B). The supplied array IS the new active
    set (what USE_SUPPLIED means); `refuse` answers VALIDATE with an
    rc (the last-display guard's door); `wrong` plays the dossier's
    trap - the retraction lands on the PRIMARY while the victim stays;
    `gdi_of` RENUMBERS slots (gate fix 2's shape: the token names one
    panel, the live slot names another -> the cross-check refuses);
    `blind_after` goes the re-query dark (every capture answers None
    after the first write - the verify-blind class must not be
    sentenced as wrong-victim).
    apply log: (flags, supplied target ids) per call, in order."""
    TARGETS = {11: r"\\?\DISPLAY#DELA283#1&2&0#{guid}",
               12: r"\\?\DISPLAY#AOC2790#1&2&1#{guid}",
               13: r"\\?\DISPLAY#IOC912B#1&2&2#{guid}"}

    def __init__(self, live=(11, 12, 13), refuse=0, wrong=False,
                 gdi_of=None, blind_after=False, slow_views=0):
        self.live = set(live)
        self.refuse = refuse
        self.wrong = wrong
        self.blind_after = blind_after
        self.blinded = False
        # slow_views = the dossier follow-up shape: the ACTIVE view
        # lags N looks before surfacing a REACTIVATED target (the
        # restore patience pin - _victim_active must re-look)
        self.slow_views = slow_views
        slots = {11: r"\\.\DISPLAY1", 12: r"\\.\DISPLAY2",
                 13: r"\\.\DISPLAY3"}
        slots.update(gdi_of or {})
        self.NAMES = {tid: (slots[tid], path)
                      for tid, path in self.TARGETS.items()}
        self.applied = []

    def _path(self, tid):
        from panelboss.wm import _hdr
        p = _hdr.DC_PATH()
        p.src.adapter.low, p.src.adapter.high = 1, 0
        p.src.id = tid
        p.tgt.adapter.low, p.tgt.adapter.high = 1, 0
        p.tgt.id = tid
        p.flags = 1 if tid in self.live else 0
        return p

    def capture(self, flags):
        from panelboss.wm import _sdc as sdc_mod
        if self.blinded:
            return None                             # the blind class
        ids = ({11, 12, 13} if flags == sdc_mod.QDC_ALL
               else {i for i in (11, 12, 13) if i in self.live})
        if flags != sdc_mod.QDC_ALL and self.slow_views > 0 \
                and 12 in self.live:
            self.slow_views -= 1
            ids = ids - {12}              # the store is slow to
            #                             surface a REACTIVATION -
            #                             an absence never lags
        paths = [self._path(i) for i in sorted(ids)]
        pb = b"".join(bytes(bytearray(p)) for p in paths)
        return pb, b"\0" * 64, paths

    def names(self, psrc, ptgt):
        return self.NAMES[ptgt.id]

    def apply(self, path_bytes, modes_bytes, flags):
        from panelboss.wm import _hdr
        ids = tuple(_hdr.DC_PATH.from_buffer_copy(
            path_bytes[i * 72:(i + 1) * 72]).tgt.id
            for i in range(len(path_bytes) // 72))
        self.applied.append((flags, ids))
        if flags == sdc_V:                                  # validate
            return (self.refuse, 87) if self.refuse else (0, 0)
        if self.refuse:
            return self.refuse, 5
        self.live = set(ids)
        if self.wrong and 12 not in ids:                    # the victim
            self.live = (self.live - {11}) | {12}           # stayed; the
            #                                    primary left (dossier)
        if self.blind_after:
            self.blinded = True         # the write took; the eyes go
        return 0, 0                     # dark after it (blind class)


sdc_V = None                      # the VALIDATE verb set, captured at
#                                first use (patch-time, from the module)


def test_sdc_marshal():
    """The real marshal over the fake CCD: PATH-MINUS drops the
    victim's path and keeps the rest IN ORDER (the falsified
    ALLOW_PATH_ORDER means the driver may not reshuffle - it gets
    the order it was given); VALIDATE gates every apply (the owner
    strobe law); the verb set is EXACTLY the measured 0x6A0 (APPLY
    is 0x80 not 0x1, and no 0x2000 anywhere); every write carries
    SAVE; the wrong-victim class restores its own damage BEFORE
    reporting; a lying gdi slot resolves by EDID token; an already-
    retracted target is the same verified word with no glass spent;
    and the belt's revive raises the stored-dark path back."""
    from panelboss.wm import _sdc as sdc_mod
    global sdc_V
    sdc_V = sdc_mod.VALIDATE_FLAGS
    led = Ledger()
    desk = FakeDesk()
    led.keep(sdc_mod, "_capture", desk.capture)
    led.keep(sdc_mod, "_names", desk.names)
    led.keep(sdc_mod, "_apply_cfg", desk.apply)
    led.keep(sdc_mod, "VERIFY_WAIT_SEC", 0)          # the suite does
    #                                                 # not sleep watch
    row = {"short": "AOC2790", "gdi": r"\\.\DISPLAY2"}
    try:
        assert sdc_mod.RETRACT_FLAGS == 0x6A0        # the measured combo
        assert not sdc_mod.RETRACT_FLAGS & 0x00002000   # falsified, out
        assert sdc_mod.SDC_APPLY == 0x80             # the dossier's (i)
        ok, saved = sdc_mod.retract(row)
        assert ok is True, saved
        assert desk.applied[0][0] == sdc_V, "validate gates the apply"
        assert desk.applied[1] == (sdc_mod.RETRACT_FLAGS, (11, 13)), \
            desk.applied                       # victim dropped, order kept
        assert saved["victim"] == {(1, 0, 12)}
        assert len(saved["paths"]) == 3 * 72, "the FULL capture is saved"
        assert 12 not in desk.live, "the store agrees: the verified word"
        ok, why = sdc_mod.restore(saved)
        assert ok, why
        assert desk.applied[-1][0] == sdc_mod.RETRACT_FLAGS, \
            "the restore carries SAVE too (the dark-boot footgun law)"
        assert 12 in desk.live
        print("ok - marshal: PATH-MINUS exact, validate-gated, the 0x6A0 "
              "combo, restore SAVES")

        # the validate refusal (the last-display guard's door): no
        # apply, no glass, the rc named in the word
        desk.refuse = 0x57
        desk.live = {11, 12, 13}
        n0 = len(desk.applied)
        ok, why = sdc_mod.retract(row)
        assert not ok and why == "validate rc 0x57 gle=87", why
        assert len(desk.applied) == n0 + 1 and desk.applied[-1][0] == sdc_V, \
            "a refused shape spends the VALIDATE and NOTHING else"
        print("ok - validate refusal: no apply follows, rc in the word")

        # the wrong-victim trap: accepted, the PRIMARY left, the victim
        # stayed - the module restores its own damage BEFORE reporting,
        # and the word names the class exactly (gate fix 1)
        desk2 = FakeDesk(wrong=True)
        led.keep(sdc_mod, "_capture", desk2.capture)
        led.keep(sdc_mod, "_apply_cfg", desk2.apply)
        ok, why = sdc_mod.retract(row)
        assert not ok and why == "no-drop rc 0x0 (wrong victim; restored)", \
            why
        assert desk2.applied[-1] == (sdc_mod.RETRACT_FLAGS, (11, 12, 13)), \
            "the self-restore rode the same SAVE flags"
        assert 11 in desk2.live, "the wrong victim came home too"
        print("ok - wrong victim: self-restored with SAVE, the exact word")

        # the VERIFY-BLIND class (gate fix 1's split): the writes take,
        # every re-query after them answers None - the fate is UNKNOWN,
        # and the word must not sentence it as wrong-victim. The
        # self-heal still runs (restore rides the same SAVE flags), and
        # the honest shade is restored-UNVERIFIED, not NOT RESTORED
        desk2b = FakeDesk(blind_after=True)
        led.keep(sdc_mod, "_capture", desk2b.capture)
        led.keep(sdc_mod, "_apply_cfg", desk2b.apply)
        ok, why = sdc_mod.retract(row)
        assert not ok and why == "no-drop rc 0x0 (verify refused; " \
            "restored unverified (blind re-query))", why
        assert len(desk2b.applied) == 3, desk2b.applied  # validate,
        #                              retract, restore - the heal rode
        assert desk2b.applied[-1][0] == sdc_mod.RETRACT_FLAGS, \
            "blind or not, the restore carries SAVE"
        print("ok - verify blind: its own word, self-healed, unverified "
              "not misattributed")

        # the SLOW-REACTIVATION patience (dossier follow-up 1): the
        # store takes two looks to surface the restored target -
        # _victim_active re-looks within the same VERIFY budget
        # _gone earned, and the verdict is WON, not a false
        # 'never came back'
        desk5 = FakeDesk(slow_views=2)
        led.keep(sdc_mod, "_capture", desk5.capture)
        led.keep(sdc_mod, "_names", desk5.names)
        led.keep(sdc_mod, "_apply_cfg", desk5.apply)
        ok, saved = sdc_mod.retract(row)
        assert ok, saved          # _gone is unaffected: an ABSENCE
        #                          never lags, only a reactivation
        ok, why = sdc_mod.restore(saved)
        assert ok is True, why
        assert desk5.slow_views == 0, desk5.slow_views   # both lagged
        #                              looks spent, then the truth
        # a store too slow for the whole budget gets the HONEST
        # still-dark word - patience has a floor, not a shrug:
        desk6 = FakeDesk(slow_views=99)
        led.keep(sdc_mod, "_capture", desk6.capture)
        led.keep(sdc_mod, "_names", desk6.names)
        led.keep(sdc_mod, "_apply_cfg", desk6.apply)
        ok, saved = sdc_mod.retract(row)
        assert ok, saved
        ok, why = sdc_mod.restore(saved)
        assert not ok and why == "the target never came back", why
        print("ok - slow store: patience wins the restore verdict; an "
              "exhausted budget still says 'never came back'")

        # the DISAGREEMENT (gate fix 2): the slot renumbered behind us -
        # DISPLAY2 now carries the IOC's path while the AOC sits on
        # DISPLAY3. The token says key 12, the live slot says key 13:
        # NO victim, NO glass, the refuse word names the dispute
        desk2c = FakeDesk(gdi_of={12: r"\\.\DISPLAY3",
                                  13: r"\\.\DISPLAY2"})
        led.keep(sdc_mod, "_capture", desk2c.capture)
        led.keep(sdc_mod, "_names", desk2c.names)   # the RENUMBERED
        #                              slot map must reach the joins
        #                              (every desk brings its own trio)
        led.keep(sdc_mod, "_apply_cfg", desk2c.apply)
        ok, why = sdc_mod.retract({"short": "AOC2790",
                                   "gdi": r"\\.\DISPLAY2"})
        assert not ok and why == "the gdi slot names one panel, the EDID " \
            "token another (no gamble)", why
        assert desk2c.applied == [], "a disputed identity spends ZERO glass"
        ok, saved = sdc_mod.retract({"short": "AOC2790", "gdi": ""})
        assert ok and desk2c.applied[-1][1] == (11, 13), \
            "slot unnamed (the belt's shape): the token alone carries"
        print("ok - disagreement: slot vs token -> refuse, zero glass; "
              "token alone still carries")

        # the ghost: the gdi slot LIES (DISPLAY99 answers nothing in
        # the CCD), the EDID token carries the victim
        desk3 = FakeDesk()
        led.keep(sdc_mod, "_capture", desk3.capture)
        led.keep(sdc_mod, "_names", desk3.names)
        led.keep(sdc_mod, "_apply_cfg", desk3.apply)
        ok, _saved = sdc_mod.retract({"short": "AOC2790",
                                      "gdi": r"\\.\DISPLAY99"})
        assert ok and desk3.applied[-1][1] == (11, 13), "token join took"
        print("ok - ghost row: gdi lies, the EDID token is the join")

        # already retracted (the crash-before-lift shape): the ALL view
        # carries the dark path - verified word, ZERO glass spent
        desk4 = FakeDesk(live=(11, 13))
        led.keep(sdc_mod, "_capture", desk4.capture)
        led.keep(sdc_mod, "_names", desk4.names)
        led.keep(sdc_mod, "_apply_cfg", desk4.apply)
        n0 = len(desk4.applied)
        ok, saved = sdc_mod.retract(row)
        assert ok and len(desk4.applied) == n0, "no apply on a dark target"
        assert len(saved["paths"]) == 3 * 72, "the raise-ready capture"
        print("ok - already dark: verified with no glass spent")

        # the belt's door: the stored-dark path raised back with SAVE
        ok, why = sdc_mod.revive({"short": "AOC2790", "gdi": ""})
        assert ok, why
        assert desk4.applied[-1][0] == sdc_mod.RETRACT_FLAGS
        assert 12 in desk4.live, "the belt re-raised the path"
        assert sdc_mod.revive({"short": "AOC2790", "gdi": ""}) is None, \
            "a lit row answers silence (the belt does not chat)"
        print("ok - revive: stored-dark raised with SAVE, lit says nothing")
    finally:
        led.undo()


def test_offdisc_flavors():
    """The two off flavors earn different epistemic words (the whole
    point of the widening): the power code's dark is TRUSTED - "off
    (unverified)", the register cannot certify; the disconnect's is
    PROVEN - "off (disconnected)", the CCD re-query is the witness.
    Also pinned: the retracted row is counted in the summary and
    claims the corner jail ONLY while no row paints (the park law,
    Oct 17, overrode that half), the wrong-victim class degrades to
    blackout confessed and owes the lift NOTHING, and the preview
    walks the same door while the lock interlock holds (a preview
    that retracted still never locks)."""
    import panelboss.display as disp
    tmp = tempfile.mkdtemp(prefix="pb_away_od")
    sdc = FakeSDC(victim={"AAA": "T-A", "CCC": "T-C"},
                  active={"T-A", "T-C"})
    bright = FakeBright({"D1": 80, "D2": 70, "D3": 50}, vcp_deaf=["D3"])
    m = make_monitor(tmp, {"mode": "dim",
                           "monitors": {"AAA": {"mode": "offdisc"},
                                        "CCC": {"mode": "off"}}},
                     bright=bright, sdc=sdc)
    fake = FakeHookU32(disp.u32)
    m._ledger.keep(disp, "u32", fake)
    rec = Recorder()
    slog = logging.getLogger("state")
    was = slog.level
    slog.setLevel(logging.INFO)           # root sits at WARNING here
    slog.addHandler(rec)
    try:
        m._screens_off(1.0)
        assert m.away_status["AAA"] == "off (disconnected)", m.away_status
        assert m.away_status["CCC"] == "off (unverified)", m.away_status
        assert m.away_status["BBB"] == "dim", m.away_status  # absent row
        assert sdc.retracts == ["AAA"], sdc.retracts
        assert ("park", 5020, 1918) in m._fake["calls"], \
            "a spell with a painted row parks; the jail defers (Oct 17)"
        assert not [c for c in m._fake["calls"] if c[0] == "jail"], \
            "ONE pointer move per engage: the park replaces the jail " \
            "whenever any row paints, retracted rows included"
        line = [l for l in rec.lines if l.startswith("away: dark")]
        assert len(line) == 1 and "1 disconnected" in line[0], line
        assert fake.locks == [], "no lock asked (lock off), no lock rung"
        m._away_lift()
        assert len(sdc.restores) == 1 and \
            sdc.restores[0]["victim"] == {"T-A"}, sdc.restores
        lifted = [l for l in rec.lines if l.startswith("away: lifted")]
        assert len(lifted) == 1 and \
            "1 disconnect hand-back(s)" in lifted[0], lifted
        print("ok - two flavors, two words: disconnected is PROVEN, "
              "unverified is TRUSTED")

        # the wrong-victim shape AT THE ENGINE: refused word, fallback
        # overlay worn, the door's own restore, and NO ledger debt
        sdc2 = FakeSDC(victim={"AAA": "WRONG"}, active=set())
        m2 = make_monitor(tmp, {"mode": "dim",
                                "monitors": {"AAA": {"mode": "offdisc"}}},
                          sdc=sdc2)
        try:
            m2._screens_off(1.0)
            w = m2.away_status["AAA"]
            assert w.startswith("offdisc refused (no-drop") and \
                w.endswith("- blackout instead)"), w
            shows = [c for c in m2._fake["calls"] if c[0] == "show"]
            assert ("show", "D1", (0, 0, 1920, 1080)) in shows, \
                "the refused disconnect wears the fallback, confessed"
            assert len(sdc2.restores) == 1, "the door restored its own damage"
            assert not m2._away_disc, "a refused row owes the lift nothing"
            m2._away_lift()
            assert len(sdc2.restores) == 1, "and the lift sends nothing more"
            print("ok - refused offdisc: blackout fallback, dated, owes none")
        finally:
            m2._ledger.undo()

        # the preview walks the SAME door: retract, no lock, revert
        # pays its own hand-back; adoption folds the record into the
        # spell's ledger (the witness law the HDR fold already lives by)
        sdc3 = FakeSDC(victim={"CCC": "T-C"}, active={"T-C"})
        m3 = make_monitor(tmp, {"mode": "dim",
                                "monitors": {"CCC": {"mode": "offdisc"}},
                                "lock": True}, sdc=sdc3)
        f3 = FakeHookU32(disp.u32)
        m3._ledger.keep(disp, "u32", f3)
        try:
            r3 = m3._away_apply_row(dict(DESK[2]), "offdisc", 10)
            assert r3["status"] == "off (disconnected)", r3
            assert f3.locks == [], "a preview that retracts never locks"
            assert m3._away_release("CCC", r3) == "reverted"
            assert len(sdc3.restores) == 1, "the revert pays its own hand-back"
            r4 = m3._away_apply_row(dict(DESK[2]), "offdisc", 10)
            m3._screens_off(5.0)                 # the real away arrives
            assert m3._away_release("CCC", r4) == "adopted"
            assert m3._away_disc.get("D3"), "the record rode the fold"
            m3._away_lift()                      # the spell pays it back
            assert len(sdc3.restores) == 2, sdc3.restores   # revert + lift
            assert f3.locks == [True], "the REAL engage locked; the " \
                #                    previews never did (offdisc included)
            print("ok - offdisc preview: no lock, revert pays, adoption "
                  "folds the record to the lift")
        finally:
            m3._ledger.undo()
    finally:
        slog.removeHandler(rec)
        slog.setLevel(was)
        m._ledger.undo()


def test_offdisc_preview_word_seam():
    """The debugger's root cause pinned at the seam (offdisc-preview
    fix): the row-menu answers LABELS, the engine dispatches on
    WORDS. (a) the REAL card method, driven unbound on a fake self
    (no Tk): the triple reads to the LABEL; (b) the LABEL->WORD map
    is EXHAUSTIVE against the menu it maps (the two must move
    together or a preview yanks the wrong leg); (c) the mapped word
    walks the real engine into the real door: retracted, PROVEN
    word, and ZERO brightness entries (the silent dim leg never
    ran); (d) the fall-through confession: a label aimed straight
    at the engine (the pre-fix card's exact call) still defaults to
    dim - and SAYS so, naming the word and the row."""
    from panelboss.ui.window._away import (
        _AwayMixin as UIM, DISC_TEXT, MODE_BY_LABEL, off_choice)
    tmp = tempfile.mkdtemp(prefix="pb_away_seam")
    stub = type("S", (), {"cfg": {"away": {
        "mode": "dim",
        "monitors": {"AOC2790": {"blackout": False, "off": False,
                                 "offdisc": True}}}}})()
    assert UIM._away_row_mode(stub, "AOC2790") == DISC_TEXT
    assert MODE_BY_LABEL[DISC_TEXT] == "offdisc"
    assert MODE_BY_LABEL["dim"] == "dim"
    assert set(MODE_BY_LABEL) == set(off_choice(FakeBright({"D1": 1}),
                                                "D1")), \
        "the menu and the map moved apart - the preview would guess"
    sdc = FakeSDC(victim={"AOC2790": "T-A"}, active={"T-A"})
    m = make_monitor(tmp, {"mode": "dim", "monitors": {}}, sdc=sdc)
    try:
        rec = m._away_apply_row({"short": "AOC2790", "gdi": "DX",
                                 "x": 0, "y": 0, "w": 1, "h": 1},
                                MODE_BY_LABEL[DISC_TEXT], 10)
        assert rec["status"] == "off (disconnected)", rec
        assert sdc.retracts == ["AOC2790"], sdc.retracts
        assert not any(c[0] in ("get", "set", "restore")
                       for c in m._fake["calls"]), \
            "the wrong leg touched no brightness at all"
        print("ok - word seam: the mapped label reaches the real door, "
              "the menu and the map are exhaustive together")
    finally:
        m._ledger.undo()
    rec = Recorder()
    slog = logging.getLogger("state")
    was = slog.level
    slog.setLevel(logging.WARNING)           # root sits at WARNING here
    slog.addHandler(rec)
    m2 = make_monitor(tmp, {"mode": "dim", "monitors": {}})
    try:
        r2 = m2._away_apply_row({"short": "AAA", "gdi": "D1", "x": 0,
                                 "y": 0, "w": 1, "h": 1}, DISC_TEXT, 10)
        assert r2["status"] == "dim", r2      # the default stands...
        line = [l for l in rec.lines if "unknown sub-mode" in l
                and "off (disconnect)" in l and "AAA" in l]
        assert len(line) == 1, rec.lines      # ...and now confesses
        print("ok - fall-through: the dim default stands, the unknown "
              "word names itself and its row (silent-wrong-leg is dead)")
    finally:
        slog.removeHandler(rec)
        slog.setLevel(was)
        m2._ledger.undo()


def test_offdisc_belt():
    """The belt's second door (the survives-the-app answer from inside
    the app): boot with a configured-offdisc row whose target sits
    INACTIVE in the store - the belt raises it back and says so ONCE.
    A lit row, a no-path row, and a desk with no offdisc rows all
    answer silence - the belt's first live act on a fresh desk must
    be NOTHING."""
    tmp = tempfile.mkdtemp(prefix="pb_away_ob")
    rec = Recorder()
    slog = logging.getLogger("state")
    was = slog.level
    slog.setLevel(logging.INFO)           # root sits at WARNING here
    slog.addHandler(rec)
    try:
        sdc = FakeSDC(victim={"CCC": "T-C"}, active=set())   # stored dark
        m = make_monitor(tmp, {"mode": "dim",
                               "monitors": {"CCC": {"mode": "offdisc"}}},
                         sdc=sdc)
        try:
            m._away_boot_belt()
            assert sdc.revives == [{"short": "CCC", "gdi": ""}], sdc.revives
            assert "T-C" in sdc.active, "the belt re-raised the path"
            line = [l for l in rec.lines
                    if "boot disconnect-restore for CCC" in l]
            assert len(line) == 1 and line[0].endswith("sent"), line
        finally:
            m._ledger.undo()
        print("ok - belt door two: stored-dark raised, one honest line")
        rec.lines.clear()
        sdc2 = FakeSDC(victim={"CCC": "T-C"}, active={"T-C"})    # lit
        m2 = make_monitor(tmp, {"mode": "dim",                 # AAA: none
                                "monitors": {"CCC": {"mode": "offdisc"},
                                             "AAA": {"mode": "offdisc"}}},
                          sdc=sdc2)
        try:
            m2._away_boot_belt()
            assert len(sdc2.revives) == 2, sdc2.revives
            assert not [l for l in rec.lines if "disconnect-restore" in l], \
                rec.lines
        finally:
            m2._ledger.undo()
        m3 = make_monitor(tmp, {"mode": "dim", "monitors": {}})
        try:
            m3._away_boot_belt()
            assert m3._fake["sdc"].revives == [], \
                "no offdisc rows = the CCD door is never reached"
        finally:
            m3._ledger.undo()
        # TWO DOORS, TWO TRY-BLOCKS (gate fix 3): a D6 row whose bus
        # catches fire must not skip the disconnect pass
        class Boom(FakeBright):
            def vcp(self, *a, **k):
                raise RuntimeError("the bus is on fire")
        sdc4 = FakeSDC(victim={"CCC": "T-C"}, active=set())  # stored dark
        m4 = make_monitor(tmp, {"mode": "dim",
                                "monitors": {"AAA": {"mode": "off"},
                                             "CCC": {"mode": "offdisc"}}},
                          bright=Boom({"D1": 80}), sdc=sdc4)
        try:
            m4._away_boot_belt()
            assert len(sdc4.revives) == 1 and "T-C" in sdc4.active, \
                "the disconnect door ran DESPITE the D6 row's raise"
            line = [l for l in rec.lines
                    if "boot disconnect-restore for CCC" in l]
            assert len(line) == 1, rec.lines
        finally:
            m4._ledger.undo()
        print("ok - lit/unreachable/no-rows: all silence (fresh desks "
              "never touch the door)")
        print("ok - two doors, two try-blocks: a raising D6 row cannot "
              "skip the disconnect pass")
    finally:
        slog.removeHandler(rec)
        slog.setLevel(was)


def test_static_ban():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "panelboss", "state", "_away.py"),
               encoding="utf8").read()
    assert "display.wake(" not in src and "turn_off(" not in src, \
        "the away engine must not own a power verb"
    assert "SC_MONITORPOWER" not in src and "0xF170" not in src, \
        "the off sub-mode's power is the VCP door, never the broadcast"
    ui = open(os.path.join(root, "panelboss", "ui", "window", "_away.py"),
              encoding="utf8").read()
    assert "lambda e=None, w=seg:" in ui, \
        "the tip anchor DEFAULT-CAPTURES the loop var (gate fix 4: " \
        "late binding would anchor every row's paragraph to the last " \
        "picker) - pinned statically; the live build is hdrwake's job"
    from panelboss.state._away import _row_went_dark
    assert _row_went_dark("off (disconnected)") and \
        _row_went_dark("off (unverified)") and _row_went_dark("blackout") \
        and _row_went_dark("dim") and _row_went_dark("dim (unverified)"), \
        "the five applied words all earn the lock"
    for w in ("off refused - blackout instead (rc 0x57)",
              "offdisc refused (no-drop rc 0x0 (wrong victim; restored) "
              "- blackout instead)",
              "blackout (send refused after 3 tries)", "gone",
              "off (some future word)", "dim (a future shade)"):
        assert not _row_went_dark(w), w
    pwr = open(os.path.join(root, "panelboss", "state", "_power.py"),
               encoding="utf8").read()
    body = pwr[pwr.index("def _screens_off"):]
    body = body[:body.index("\n    def ")]
    guard, verb = body.index("self._away_engage()"), body.index(
        "display.turn_off()")
    assert guard < verb, "the power verb sits behind the engage guard"
    assert re.search(r"if self\._away_engage\(\):", body), "guard pinned"
    print("ok - static ban: the off path reaches the verb only un-dimmed")
    print("ok - the lock predicate is a WHITELIST: refusals, gone, and "
          "future words never yank the session (gate fix 5)")


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
    led.keep(wm, "session_is_remote", lambda: False)  # the suite owns
    #                              its desk's truth: the gauntlet box
    #                              may BE a remote session (the stock
    #                              law is a LOCAL-desk law)
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
        led.keep(wm, "_sdc", FakeSDC())       # the suite owns the CCD
        #                              door: the default desk retracts
        eng = m._away_engage()                # fresh default: unset rows
        assert eng and all(s.startswith("offdisc refused")  # fall to the
                           for s in eng.values()), eng      # disconnect,
        #                              refused here (no path answers) ->
        #                              confessed blackout; the ears ride
        #                              every spell from Oct 22
        assert d._pump_pause() == disp.ARMED_PAUSE_SEC
        d._service_ears()
        d._service_ears()
        assert fake.registers == [2], fake.registers
        assert fake.hook_calls == [], "the LL chain is gone for good"
        m._away_lift()
        d._service_ears()
        assert fake.unregisters == [2]
        fake.registers.clear()
        fake.unregisters.clear()      # section 2 pins the dim spell
        #                              with a fresh recorder
        print("ok - the away engine never stands down: ears ride the "
              "spell, registered once, and the LL trio stays dead")
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
    """Every accepted row shape folds to the TRIPLE (both young keys
    answer False by never having needed migration; the old pair-shape
    files read without migration - absent offdisc is simply False)."""
    n = config.normalize_away
    assert n({"mode": "dim", "monitors": {"A": "off"}})["monitors"] == \
        {"A": {"blackout": False, "off": True, "offdisc": False}}
    assert n({"mode": "dim",
              "monitors": {"A": {"mode": "blackout"}}})["monitors"] == \
        {"A": {"blackout": True, "off": False, "offdisc": False}}
    assert n({"mode": "dim", "monitors": {"A": True}})["monitors"] == \
        {"A": {"blackout": True, "off": False, "offdisc": False}}
    assert n({"mode": "dim", "monitors": {"A": "offdisc"}})["monitors"] == \
        {"A": {"blackout": False, "off": False, "offdisc": True}}
    assert n({"mode": "dim", "monitors": {"A": "off-disc"}})["monitors"] == \
        n({"mode": "dim", "monitors": {"A": "offdisc"}})["monitors"]
    #                              the hyphen is a spelling, not a mode
    assert n({"mode": "dim",
              "monitors": {"A": {"mode": "off-disc"}}})["monitors"] == \
        {"A": {"blackout": False, "off": False, "offdisc": True}}
    assert n({"mode": "dim",
              "monitors": {"A": {"blackout": False, "offdisc": True}}}) \
        ["monitors"] == {"A": {"blackout": False, "off": False,
                               "offdisc": True}}    # the triple branch
    assert n({"mode": "dim", "monitors": {"A": {"blackout": True}}}) \
        ["monitors"] == {"A": {"blackout": True, "off": False,
                               "offdisc": False}}   # PAIR files read
    #                                    un-migrated (the no-migration
    #                                    promise, pinned at the loader)
    assert n({"mode": "dim", "monitors": {"A": "sideways"}})["monitors"] \
        == {}                      # warned, dropped, dim default
    assert n({"mode": "dim",
              "monitors": {"A": {"mode": "sideways"}}})["monitors"] == \
        {"A": {"blackout": False, "off": False, "offdisc": False}}    # the
    #                                    dict branch answers with the
    #                                    SAME honesty (gate finding 5a):
    #                                    warn, fold to dim, name the row
    print("ok - row shorthands fold to the triple shape losslessly")


def test_park_replaces_jail():
    """(iv) The pointer law (owner, Oct 17): a painted engage parks
    the cursor bottom-middle of the LOWEST panel, EXACTLY once; the
    jail keeps the sleep rows it was written for. The suite desk's
    lowest row is the portrait CCC (bottom 1920, center 5020)."""
    tmp = tempfile.mkdtemp(prefix="pb_away_pk")
    m = make_monitor(tmp, {"mode": "dim", "monitors": {}})
    try:
        m._screens_off(1.0)
        parks = [c for c in m._fake["calls"] if c[0] == "park"]
        jails = [c for c in m._fake["calls"] if c[0] == "jail"]
        assert parks == [("park", 5020, 1918)], parks
        assert not jails, jails
        m2 = make_monitor(tmp, {"mode": "dim",
                                "monitors": {"AAA": {"mode": "off"}}})
        try:
            m2._screens_off(1.0)                     # one off row, the
            parks2 = [c for c in m2._fake["calls"] if c[0] == "park"]
            assert parks2 == [("park", 5020, 1918)], \
                "one painted row is enough for the park; one move only"
            assert not [c for c in m2._fake["calls"] if c[0] == "jail"], \
                "the park replaces the jail for painted modes, not adds"
        finally:
            m2._ledger.undo()
        m3 = make_monitor(tmp, {"mode": "off"})      # the legacy word:
        try:                                         # sleep rows jail,
            m3._screens_off(1.0)                     # they never park
            assert not [c for c in m3._fake["calls"] if c[0] == "park"]
        finally:
            m3._ledger.undo()
        print("ok - park: once, at the lawful point, replacing the "
              "jail on painted modes; sleep rows keep the jail")
    finally:
        m._ledger.undo()


def test_park_point_geometry():
    """(v) The pure helper: the lowest panel wins; tied bottoms break
    toward the panel nearest the desk's horizontal middle; the point
    is center-x, two above the bottom edge."""
    lowest = [{"x": -100, "y": 0, "w": 100, "h": 1200},
              {"x": 0, "y": 0, "w": 1920, "h": 1080}]
    assert PresenceMonitor.park_point(lowest) == (-50, 1198)
    tied = [{"x": 0, "y": 0, "w": 400, "h": 1080},
            {"x": 3000, "y": 20, "w": 800, "h": 1060}]
    #               desk 0..3800, mid 1900: centers 200 vs 3400 - the
    #               right panel sits nearer the middle, it takes the park
    assert PresenceMonitor.park_point(tied) == (3400, 1078)
    print("ok - park_point: lowest panel, center-x, two above the edge")


def test_deep_key_gone():
    """The stage-two timer RETIRED (owner, Oct 19): Windows' own
    screen-off timer does the disconnect, and the monitor power
    state machine owns the device lifetime a cached DDC handle
    could not promise. A retired key must not fail silent: normalize
    warns naming it, and the next save removes it from the file."""
    rec = Recorder()
    clog = logging.getLogger("config")
    was = clog.level
    clog.setLevel(logging.WARNING)
    clog.addHandler(rec)
    try:
        got = config.normalize_away({"off_after_min": 30})
        assert "off_after_min" not in got, got
        assert [l for l in rec.lines if "off_after_min" in l
                and "gone" in l], rec.lines
    finally:
        clog.setLevel(was)
        clog.removeHandler(rec)
    print("ok - the retired deep-sleep key warns naming itself and "
          "dies at the next save")


def test_default_flip():
    """THE DEFAULT FLIP, at all three tiers (owner, Oct 22): an unset
    row -> offdisc; the legacy 'off' word -> the VCP door byte-
    identical; the chain: row value beats the global key beats the
    default. The normalize line the whole ruling hangs on is pinned
    first, as data."""
    n = config.normalize_away
    assert n({})["mode"] == "offdisc" == config.AWAY_ROW_DEFAULT
    tmp = tempfile.mkdtemp(prefix="pb_away_dflt")
    sdc = FakeSDC(victim={"AAA": "T-A", "BBB": "T-B", "CCC": "T-C"},
                  active={"T-A", "T-B", "T-C"})
    m = make_monitor(tmp, {}, sdc=sdc)          # fresh config shape
    try:
        m._screens_off(1.0)
        assert m.away_status == {"AAA": "off (disconnected)",
                                 "BBB": "off (disconnected)",
                                 "CCC": "off (disconnected)"}, \
            m.away_status
        assert sorted(sdc.retracts) == ["AAA", "BBB", "CCC"]
        assert not any(c[0] in ("set", "vcp") for c in m._fake["calls"]), \
            "the default desk spends no brightness and no power code"
        m._away_lift()
        print("ok - unset rows answer the disconnect default (PROVEN "
              "word, adapter door)")
    finally:
        m._ledger.undo()
    # the chain's middle tier: a legacy global key feeds unset rows...
    m2 = make_monitor(tmp, {"mode": "off"})
    try:
        m2._screens_off(1.0)
        assert set(m2.away_status.values()) == {"off (unverified)"}, \
            m2.away_status
        # ...and an explicit row word always outranks it
        m2.cfg["away"] = config.normalize_away(
            {"mode": "off", "monitors": {"BBB": {"mode": "blackout"}}})
        m2._away_lift()
        m2._screens_off(2.0)
        assert m2.away_status["BBB"] == "blackout", m2.away_status
        assert m2.away_status["AAA"] == "off (unverified)"
        m2._away_lift()
        print("ok - the fallback chain: row beats global key beats "
              "default")
    finally:
        m2._ledger.undo()
    # the card-side mirror: _away_row_mode answers the SAME chain
    from panelboss.ui.window._away import _AwayMixin, DDC_TEXT, DISC_TEXT
    stub = type("S", (), {"cfg": {"away": {"mode": "dim", "monitors": {
        "A": {"blackout": False, "off": True, "offdisc": False}}}}})()
    assert _AwayMixin._away_row_mode(stub, "A") == DDC_TEXT
    assert _AwayMixin._away_row_mode(stub, "Z") == "dim"   # global tier
    stub2 = type("S", (), {"cfg": {"away": {}}})()
    assert _AwayMixin._away_row_mode(stub2, "Z") == DISC_TEXT  # default
    print("ok - the card mirrors the chain; a row with no key paints "
          "the word the engine will act on")


def main():
    test_migration()
    test_row_shorthands()
    test_default_flip()
    test_substitution()
    test_legacy_global_off_fallback()
    test_remote_desk_exempt()
    test_refusal_degrades()
    test_unverified_trust()
    test_vcp_retry_law()
    test_off_submode()
    test_boot_belt()
    test_belt_stagger()
    test_belt_waits_settle()
    test_handback_waits_settle()
    test_jail_moves_cursor()
    test_park_replaces_jail()
    test_park_point_geometry()
    test_deep_key_gone()
    test_off_preview_release()
    test_off_selectable_never_pregrayed()
    test_nvidia_vendor_gate()
    test_preview_adopt_law()
    test_lock_on_away()
    test_session_unlock_ear()
    test_sdc_marshal()
    test_offdisc_flavors()
    test_offdisc_preview_word_seam()
    test_offdisc_belt()
    test_hook_lifecycle()
    test_static_ban()
    print("AWAYMODE TESTS OK")


if __name__ == "__main__":
    main()
