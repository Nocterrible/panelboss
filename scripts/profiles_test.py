"""Offline checks for the profile engine: pin hits, both HDR paths
(read-and-command where the driver answers, belief fallback where
it cannot), the store (quarantine included), the mismatch gate, the
whole apply flow against a FAKE wm - the two-pass order, the verify
loop, the best-effort road, and the naive re-open of a missing app.
The real desk is never touched: no real apply_layout ever runs
here."""
import os
import sys
import tempfile
import types

sys.path.insert(0, r"F:\Projects\ICU-PresenceDetector")

from panelboss import profiles

# 1) pin hits: how one saved seat recognises its live windows. A
# process pin owns EVERY window of that app (the promise the UI
# warns about); 'process + title' matches exactly the one window it
# was pinned from; 'title' is gentle and misses the renamed tab;
# earlier pins answer first; windows that answer no pin are left in
# peace. Legacy rows without a match inherit the profile's.
LIVE = [{"proc": "opera.exe", "title": "renamed!", "hwnd": 1},
        {"proc": "opera.exe", "title": "A", "hwnd": 2},
        {"proc": "code.exe", "title": "x", "hwnd": 3},
        {"proc": "calc.exe", "title": "free", "hwnd": 4}]


def P(row, taken=(), fb="process", live=None):
    return sorted(l["hwnd"] for l in profiles.pin_hits(
        row, LIVE if live is None else live, taken, fb))


assert P({"proc": "opera.exe", "match": "process"}) == [1, 2]
assert P({"proc": "opera.exe", "title": "A",
          "match": "process + title"}) == [2]
assert P({"proc": "opera.exe", "title": "A", "match": "title"}) == [2]
assert P({"proc": "opera.exe", "title": "renamed!",
          "match": "title"}) == [1]
assert P({"proc": "opera.exe", "match": "process"}, taken={2}) == [1]
assert P({"proc": "", "match": "process"}) == []  # an empty pin
assert P({"proc": "code.exe"}, fb="process + title") == []
assert P({"proc": "opera.exe", "title": "A"},
         fb="process + title") == [2]              # legacy row
assert 4 not in (P({"proc": "opera.exe"}) + P({"proc": "code.exe"})
                 + P({"proc": "nope.exe", "title": "nada"})), \
    "the unpinned calc window got shoved"
print("pin hits OK (process owns all, p+t exact, first pin first, "
      "legacy fallback)")

# 2) the HDR belief dance: press only on disagreement, adopt loudly
# from unknown, TOGGLE FLIPS (off->on - the direction an early
# draft had backwards), leave alone never presses.
H = profiles.hdr_action
assert H("on", "unknown") == ("press", "on")
assert H("on", "on") == (None, "on")
assert H("off", "on") == ("press", "off")
assert H("on", "off") == ("press", "on")
assert H("toggle", "off") == ("press", "on")
assert H("toggle", "on") == ("press", "off")
assert H("toggle", "unknown") == ("press", "on")
assert H("leave alone", "off") == (None, "off")
print("hdr belief OK (press only on disagreement, toggle flips)")

# 2b) hdr_plan: the driver's ANSWER decides - panels that cannot do
# HDR ("na") or will not say ("unknown") are never commanded, on/off
# fixes only the disagreements, toggle flips exactly what it sees.
P = profiles.hdr_plan
S = {"A": "off", "B": "on", "C": "na", "D": "unknown"}
assert P("leave alone", S) == []
assert P("skip", S) == []
assert P("on", S) == [("A", "on")], P("on", S)
assert P("off", S) == [("B", "off")], P("off", S)
assert sorted(P("toggle", S)) == [("A", "on"), ("B", "off")]
assert P("on", {"A": "na"}) == []
print("hdr plan OK (na/unknown never commanded, toggle flips what it sees)")

# 2c) hdr_snap_plan: each panel back to ITS OWN captured state -
# panels the capture has no state for (old profiles) and panels
# that cannot do HDR or will not say now are never commanded
SP = profiles.hdr_snap_plan
D = [{"id": "A", "hdr_state": "on"}, {"id": "B", "hdr_state": "off"},
     {"id": "C", "hdr_state": None}, {"id": "D"}]
assert SP(D, {"A": "off", "B": "on", "C": "on", "D": "off"}) == \
    [("A", "on"), ("B", "off")], SP(D, {"A": "off", "B": "on"})
assert SP(D, {"A": "on", "B": "off", "C": "off", "D": "on"}) == []
assert SP(D, {"A": "na", "B": "unknown"}) == []
print("hdr snap plan OK (per-monitor targets; unrecorded and mute "
      "panels left in peace)")

# 3) the store: roundtrip, quarantine of an unparsable file, and a
# single rotted profile dropped without killing its neighbours
tmp = tempfile.mkdtemp()
p = os.path.join(tmp, "profiles.json")
data = {"hdr_key": "win+alt+b", "hdr_now": "off", "last": {},
        "profiles": {"good": {"fp": "F", "wins": [],
                              "displays": [{"id": "X"}]}}}
profiles.save(data, tmp)
assert "good" in profiles.load(tmp)["profiles"]
with open(p, "w", encoding="utf-8") as fh:
    fh.write("{oops hand-edited")
fresh = profiles.load(tmp)
assert fresh["profiles"] == {}, fresh
import glob
assert glob.glob(os.path.join(tmp, "*.corrupt-*")), "wreckage eaten"
with open(p, "w", encoding="utf-8") as fh:
    fh.write('{"profiles": {"good": {"displays": [], "wins": []},'
             ' "rot": "not even a dict"}, "last": {}, '
             '"hdr_key": ""}')
half = profiles.load(tmp)
assert "rot" not in half["profiles"] and "good" in half["profiles"]
assert half["hdr_key"] == "win+alt+b", "empty hotkey accepted"
print("store OK (atomic, quarantine, rotted rows dropped alone)")

# 4) the gate: identity only. positions/modes may differ freely -
# they are what the profile APPLIES, not what it demands.
prof = {"displays": [{"id": "MONITOR\\AAA", "short": "AAA"},
                     {"id": "MONITOR\\BBB", "short": "BBB"}]}
assert profiles.desk_mismatch(prof, [{"id": "MONITOR\\BBB"},
                                     {"id": "MONITOR\\AAA"}]) == ""
s = profiles.desk_mismatch(prof, [{"id": "MONITOR\\CCC"}])
assert "AAA" in s and "BBB" in s and "CCC" in s, s
print("gate OK (identity set; swapped panel named both ways)")

# 5) target fingerprint: order-proof, dark panels excluded
t1 = profiles.target_fp([{"id": "B", "x": 0, "y": 0, "w": 9,
                           "h": 9, "on": True},
                         {"id": "A", "x": 9, "y": 0, "w": 9, "h": 9,
                          "on": True, "primary": True}])
t2 = profiles.target_fp([{"id": "A", "x": 9, "y": 0, "w": 9,
                          "h": 9, "primary": True},
                         {"id": "B", "x": 0, "y": 0, "w": 9,
                          "h": 9, "on": False}])
assert t1.count("B@") == 1 and "@9,0 9x9P" in t2 and "B@" not in t2, \
    (t1, t2)
print("target fp OK (lit panels only, order-proof)")


# 6) the whole apply flow against a fake wm ---------------------------
class FakeWM:
    """records every call the apply makes; the desk answers whatever
    fp list it is handed, one string per poll. hdr rows (the driver
    answers for 24H2+) are optional: none = the OS stays silent and
    the apply must fall back to the belief path."""

    def __init__(self, mons, fps, layout_ok=True, hdr=None):
        self.mons, self.fps = mons, list(fps)
        self.layout_ok = layout_ok
        self.calls, self.entries = [], []
        self.pressed, self.placed, self.rescued = [], [], []
        self.hdr, self.sets = hdr or [], []
        self.launches = []

    def monitors(self):
        return self.mons

    def fingerprint(self):
        self.calls.append("fp")
        return self.fps.pop(0) if len(self.fps) > 1 else self.fps[0]

    def apply_layout(self, entries):
        self.entries = entries
        order = [e["gdi"] for e in entries]
        self.calls.append(("layout", order))
        return self.layout_ok, (["skip all"] if self.layout_ok
                                else ["refused 87"])

    def press_keys(self, combo):
        self.pressed.append(combo)
        return ""

    def hdr_states(self):
        return [dict(r, mode=2 if r["state"] == "on" else 0,
                     precise=True) for r in self.hdr]

    def hdr_set(self, gdi, on):
        self.sets.append((gdi, on))
        for r in self.hdr:
            if r["gdi"] == gdi:
                r["state"] = "on" if on else "off"
        return ""

    def list_windows(self):
        return [{"proc": "opera.exe", "title": "A", "hwnd": 2,
                 "rect": [0, 0, 5, 5], "zoomed": False}]

    def place(self, hwnd, rect, zoomed):
        self.placed.append((hwnd, rect))
        return "ok"

    def rescue_lost(self):
        self.rescued.append(1)
        return ["stuck window"]


class FastTime:
    """the verify loop sleeps in half-seconds waiting for 2 s of
    quiet - the test does not wait in real time"""
    now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, s):
        self.now += s

    def time(self):
        return 1760000000.0


real_wm, real_time = profiles.wm, profiles.time
AAA = {"id": "MONITOR\\AAA", "short": "AAA", "gdi": r"\\.\DISPLAY1",
       "x": 0, "y": 0, "w": 3840, "h": 2160, "rate": 240, "bits": 32,
       "primary": True}
BBB = {"id": "MONITOR\\BBB", "short": "BBB", "gdi": r"\\.\DISPLAY2",
       "x": -3840, "y": 0, "w": 1920, "h": 1080, "rate": 144,
       "bits": 32, "primary": False}
DESK = [dict(AAA), dict(BBB)]
TARGET = profiles.target_fp(DESK)
prof6 = {"fp": TARGET, "match": "process + title", "hdr": "on",
         "displays": [dict(AAA), dict(BBB)],
         "wins": [{"proc": "opera.exe", "title": "A",
                   "rect": [10, 10, 100, 100], "zoomed": False}]}
try:
    profiles.time = FastTime()

    def scenario(fps, mons=DESK, best=False, ok=True, hdr=None,
                 scope="full", login=False):
        tmp6 = tempfile.mkdtemp()
        profiles.save({"hdr_key": "win+alt+b", "hdr_now": "unknown",
                       "last": {}, "profiles": {"p": prof6}}, tmp6)
        data = profiles.load(tmp6)
        f = FakeWM(mons, fps, ok, hdr)
        profiles.wm = f
        ok_, say, info_ = profiles.apply(data, "p", best_effort=best,
                                         scope=scope, login=login,
                                         dir=tmp6)
        return ok_, say, f, profiles.load(tmp6), info_

    # matched desk: layout asked; the fake OS stays silent about HDR
    # (no rows) so the belief fallback must fire: unknown->press->
    # "on" persisted; window placed, rescue ran, last-used recorded
    ok6, say6, f6, disk, info6 = scenario([TARGET])
    assert ok6, say6
    assert info6["no_shows"] == [], info6
    assert ("layout", [AAA["gdi"], BBB["gdi"]]) in f6.calls or \
        ("layout", [BBB["gdi"], AAA["gdi"]]) in f6.calls, f6.calls
    assert f6.pressed == ["win+alt+b"], f6.pressed
    assert f6.placed == [(2, (10, 10, 100, 100))], f6.placed
    assert f6.rescued, "auto-rescue skipped"
    assert disk["hdr_now"] == "on", "belief not persisted"
    assert disk["last"].get(TARGET) == "p"
    # 2 s of quiet were actually demanded before believing
    assert f6.calls.count("fp") >= 2, f6.calls

    # 24H2+ reality: the driver ANSWERS. AAA is off and the profile
    # wants on -> commanded, read back, VERIFIED; BBB cannot do HDR
    # at all and is left in peace; the hotkey is never touched and
    # the stored belief is calibrated from the read, not guessed
    rows = [{"gdi": AAA["gdi"], "supported": True, "state": "off"},
            {"gdi": BBB["gdi"], "supported": False, "state": "off"}]
    ok6, say6, f6, disk, _ = scenario([TARGET], hdr=rows)
    assert ok6, say6
    assert f6.sets == [(AAA["gdi"], True)], f6.sets
    assert f6.pressed == [], "hotkey while the driver could answer"
    assert "AAA on (verified)" in say6, say6
    assert disk["hdr_now"] == "on", "belief not calibrated from read"

    # everything already obeys: no command travels at all
    rows = [{"gdi": AAA["gdi"], "supported": True, "state": "on"},
            {"gdi": BBB["gdi"], "supported": True, "state": "on"}]
    ok6, say6, f6, _, info6 = scenario([TARGET], hdr=rows)
    assert f6.sets == [] and "already on" in say6, say6

    # SNAP: every panel back to the state the profile SAW - AAA was
    # captured on and BBB off, the desk answers exactly backwards,
    # so two opposite commands fly and BOTH verify
    prof6["hdr"] = "snap"
    prof6["displays"][0]["hdr_state"] = "on"
    prof6["displays"][1]["hdr_state"] = "off"
    rows = [{"gdi": AAA["gdi"], "supported": True, "state": "off"},
            {"gdi": BBB["gdi"], "supported": True, "state": "on"}]
    ok6, say6, f6, disk, _ = scenario([TARGET], hdr=rows)
    assert ok6, say6
    assert sorted(f6.sets) == sorted([(AAA["gdi"], True),
                                      (BBB["gdi"], False)]), f6.sets
    assert "AAA on (verified)" in say6 and "BBB off (verified)" \
        in say6, say6

    # a profile captured before snapshots existed: nothing to
    # restore, said out loud, and not one command is sent
    for d in prof6["displays"]:
        d.pop("hdr_state")
    ok6, say6, f6, _, _ = scenario([TARGET], hdr=rows)
    assert f6.sets == [] and "predates the hdr snapshot" in say6, \
        say6

    # an unreadable OS (no driver rows): restore-by-coin-flip is
    # refused - the hotkey stays unpressed for a per-monitor wish
    prof6["displays"][0]["hdr_state"] = "on"
    ok6, say6, f6, _, _ = scenario([TARGET])
    assert f6.sets == [] and f6.pressed == [], (f6.sets, f6.pressed)
    assert "24H2" in say6, say6
    prof6["hdr"] = "on"
    for d in prof6["displays"]:
        d.pop("hdr_state", None)

    # a deaf driver: accepts the command, never obeys - the honest
    # complaint is "never confirmed", not a verification lie
    class DeafWM(FakeWM):
        def hdr_set(self, gdi, on):          # accepts, never obeys
            self.sets.append((gdi, on))
            return ""
    tmp6 = tempfile.mkdtemp()
    profiles.save({"hdr_key": "win+alt+b", "hdr_now": "unknown",
                   "last": {}, "profiles": {"p": prof6}}, tmp6)
    f6 = DeafWM(DESK, [TARGET], True,
                [{"gdi": AAA["gdi"], "supported": True,
                  "state": "off"}])
    profiles.wm = f6
    ok6, say6, _info6 = profiles.apply(profiles.load(tmp6), "p",
                                       dir=tmp6)
    assert ok6 and "never confirmed" in say6, say6
    assert f6.pressed == [] and f6.sets == [(AAA["gdi"], True)]

    # different desk, no mercy: refused, nothing touched
    ok6, say6, f6, _, info6 = scenario(["other fp"],
                                        mons=[dict(AAA)], best=False)
    assert not ok6 and "different desk" in say6 and f6.entries == []
    assert info6.get("no_shows", []) == [], "refused apply chased windows"

    # same but try-anyway: the missing panel asked of nothing, the
    # present one kept, windows placed on the shrunken desk
    ok6, say6, f6, _, info6 = scenario(["other fp"], mons=[dict(AAA)],
                                        best=True)
    assert ok6 and "never matched" in say6, say6
    assert [e["gdi"] for e in f6.entries] == [AAA["gdi"]], \
        f6.entries
    assert f6.placed, "best effort must still place windows"
    assert info6["no_shows"] == [], info6

    # the driver refuses: no verify, no windows, honest sentence
    ok6, say6, f6, _, info6 = scenario([TARGET], ok=False)
    assert not ok6 and "layout refused" in say6 and not f6.placed
    assert info6.get("no_shows", []) == [], "refused apply chased windows"

    # 6b) the open pin: a seat whose app is not running starts the
    # exe it saved (or the launcher the user browsed to), waits as
    # long as the pin's own `wait` says, and moves the window the
    # moment it wakes. If it never wakes the miss is LOUD once (info
    # no_shows) and silent forever once the user accepted the quiet.
    prof7 = {"fp": TARGET, "match": "process", "hdr": "leave alone",
             "displays": [dict(AAA), dict(BBB)],
             "wins": [{"proc": "opera.exe", "title": "A",
                       "rect": [10, 10, 100, 100], "zoomed": False,
                       "monitor": "AAA", "exe": r"C:\x\opera.exe",
                       "match": "process", "open": True,
                       "wait": 10}]}

    def run7(mutate=None, refuse="", wake_after=None, login=False,
             seed_login=None):
        tmp7 = tempfile.mkdtemp()
        pr = dict(prof7)
        row = dict(prof7["wins"][0])
        if mutate:
            mutate(row)
        pr["wins"] = [row]
        payload = {"hdr_key": "win+alt+b", "hdr_now": "unknown",
                   "last": {}, "profiles": {"p": pr}}
        if seed_login is not None:
            payload["login"] = seed_login
        profiles.save(payload, tmp7)

        class W(FakeWM):
            pass

        def w_init(self, *a, **k):
            FakeWM.__init__(self, *a, **k)
            self.polls = 0
            self.launch_times = []

        def w_launch(self, exe):
            self.launches.append(exe)
            self.launch_times.append(profiles.time.monotonic())
            return refuse

        def w_windows(self):
            self.polls += 1
            if wake_after is not None and self.polls > wake_after:
                return [{"proc": "opera.exe", "title": "A",
                         "hwnd": 7, "rect": [0, 0, 5, 5],
                         "zoomed": False}]
            return []

        W.__init__ = w_init
        W.launch = w_launch
        W.list_windows = w_windows
        w7 = W(DESK, [TARGET])
        profiles.wm = w7
        w7.t0 = profiles.time.monotonic()
        ok7, say7, info7 = profiles.apply(profiles.load(tmp7), "p",
                                          login=login, dir=tmp7)
        return ok7, say7, info7, w7

    # wakes on the next poll: the exe ran once, the window was moved,
    # and the wait ended the moment it showed - not a second longer
    ok7, say7, info7, w7 = run7(wake_after=1)
    assert ok7 and w7.launches == [r"C:\x\opera.exe"], (say7,
                                                        w7.launches)
    assert w7.placed == [(7, (10, 10, 100, 100))], w7.placed
    assert info7["no_shows"] == [], info7
    assert w7.polls <= 3, "waited far past the window's arrival"

    # never wakes: the miss is LOUD once, and patience obeyed the
    # pin's own wait (10 s here, not the 30 s default)
    ok7, say7, info7, w7 = run7()
    assert ok7 and info7["no_shows"] == [
        {"proc": "opera.exe", "title": "A"}], info7
    assert "within 10 s" in say7, say7
    assert w7.polls <= 12, "ignored the pin's own wait"

    # the user once said "let it be": the same miss is silent now
    ok7, say7, info7, w7 = run7(lambda r: r.update(quiet=True))
    assert ok7 and info7["no_shows"] == [] and "not open" in say7, \
        (info7, say7)

    # the shell refuses to run the exe at all: still a loud miss,
    # with the reason spoken
    ok7, say7, info7, w7 = run7(refuse="the shell refused")
    assert "would not start: the shell refused" in say7, say7
    assert info7["no_shows"], "a refused launch is still a miss"

    # browsed to a launcher instead of the app's own exe: THAT is
    # what gets run, and the seat still lands
    ok7, say7, info7, w7 = run7(
        lambda r: r.update(exe=r"C:\launch\door.exe"),
        wake_after=1)
    assert w7.launches == [r"C:\launch\door.exe"], w7.launches
    assert w7.placed, "launched via the launcher but never moved"

    # the app DID show, answering an earlier pin of the same
    # process: the later pin's silence is not a miss worth nagging
    class ShowWM(FakeWM):
        def list_windows(self):
            return [{"proc": "opera.exe", "title": "whoever",
                     "hwnd": 8, "rect": [0, 0, 5, 5],
                     "zoomed": False}]

    tmp7 = tempfile.mkdtemp()
    pr = dict(prof7)
    a = dict(prof7["wins"][0])
    b = dict(a, title="second seat", open=False)
    pr["wins"] = [a, b]
    profiles.save({"hdr_key": "win+alt+b", "hdr_now": "unknown",
                   "last": {}, "profiles": {"p": pr}}, tmp7)
    w7 = ShowWM(DESK, [TARGET])
    profiles.wm = w7
    ok7, say7, info7 = profiles.apply(profiles.load(tmp7), "p",
                                      dir=tmp7)
    assert ok7 and info7["no_shows"] == [], (say7, info7)
    assert w7.placed == [(8, (10, 10, 100, 100))], w7.placed
    print("open pins OK (wake, per-pin wait, loud once then quiet, "
          "refused launch, launcher browse, no double-nag)")

    # 6b-login) the logon special. First login: two full minutes of
    # calibration before ANY launch, and whatever shows up is timed
    # from ITS LAUNCH - counting our own wait as the app's slowness
    # would make every login grow. Nothing showing up is nothing
    # learned.
    ok7, say7, info7, w7 = run7(login=True)               # never wakes
    assert w7.launches == [r"C:\x\opera.exe"], w7.launches
    assert abs((w7.launch_times[0] - w7.t0)
               - profiles.LOGIN_CALIBRATION) <= 1, w7.launch_times
    assert "waited 120 s before launching" in say7, say7
    assert "within 70 s" in say7, say7      # 10 pin + 60 login grace
    assert info7["no_shows"], "login misses stay loud for the balloons"
    assert info7["login"]["took"] == {}, info7
    assert info7["login"]["delay_next"] == profiles.LOGIN_CALIBRATION

    # an app that showed up 1 s after its calibration launch: the
    # lesson is 1 s, and the next login drops to the 30 s floor
    ok7, say7, info7, w7 = run7(login=True, wake_after=1)
    assert ok7 and w7.placed, say7
    assert abs(info7["login"]["took"]["opera.exe"] - 1.0) <= 1.0, info7
    assert info7["login"]["delay_next"] == profiles.LOGIN_DELAY, info7
    assert "next login: 30 s" in say7, say7

    # lessons from disk shape the next login: a 50 s boot means
    # 70 s of patience (metric + buffer); a nightmare 700 s boot
    # is capped at 10 min
    ok7, say7, info7, w7 = run7(
        login=True, seed_login={"max": 50.0,
                                "took": {"opera.exe": 50.0}, "at": 1})
    assert abs((w7.launch_times[0] - w7.t0) - 70.0) <= 1, \
        w7.launch_times
    ok7, say7, info7, w7 = run7(
        login=True, seed_login={"max": 700.0,
                                "took": {"opera.exe": 700.0},
                                "at": 1})
    assert w7.launch_times[0] - w7.t0 <= profiles.LOGIN_CAP + 1, \
        w7.launch_times

    # 6c) scope: half a lever. windows-only never asks a driver
    # anything; monitors-only never touches a window; and the desk
    # gate guards BOTH halves - a seat saved on one desk must never
    # be forced onto another.
    ok6, say6, f6, _, info6 = scenario([TARGET], scope="windows")
    assert ok6 and "monitors untouched" in say6, say6
    assert f6.entries == [], "windows-only asked the drivers"
    assert f6.placed, "windows-only failed to place"
    ok6, say6, f6, _, info6 = scenario([TARGET], scope="monitors")
    assert ok6 and "monitors only" in say6, say6
    assert f6.entries, "monitors-only lost the layout"
    assert f6.placed == [] and info6["no_shows"] == []
    ok6, say6, f6, _, info6 = scenario(["other fp"], mons=[dict(AAA)],
                                       best=False, scope="windows")
    assert not ok6 and "different desk" in say6 and not f6.placed, say6

    # the login picker's "the last one for this desk": judged by
    # panel IDENTITY (a cold boot may not have reached the modes
    # yet), freshest match wins, a half-missing desk picks the
    # profile that fits what IS there
    tmpn = tempfile.mkdtemp()

    def _pr(fp, used, disp):
        return {"fp": fp, "used": used, "displays": disp,
                "wins": [], "hdr": "leave alone"}

    profiles.save({"hdr_key": "win+alt+b", "hdr_now": "unknown",
                   "last": {}, "profiles": {
                       "old": _pr("X", 100, [AAA, BBB]),
                       "new": _pr("Y", 200, [AAA, BBB]),
                       "elsewhere": _pr("Z", 300, [dict(BBB)])}},
                  tmpn)
    dn = profiles.load(tmpn)
    assert profiles.name_for_desk(dn, [dict(AAA), dict(BBB)]) == "new"
    assert profiles.name_for_desk(dn, [dict(BBB)]) == "elsewhere"
    assert profiles.name_for_desk(dn, []) is None
    print("login restore OK (storm delay, stretched patience, "
          "scopes, identity picker)")
finally:
    profiles.wm, profiles.time = real_wm, real_time
print("apply flow OK (gate, mercy, belief fallback, real-hdr set+"
      "verify+calibration, refusal honesty, rescue)")

# 7) the two-pass order inside wm.apply_layout itself, with the
# config API faked: enables first, new primary LAST with
# CDS_SET_PRIMARY, disables after, one commit at the end.
from panelboss import wm


class FakeU32:
    def __init__(self):
        self.calls = []

    def EnumDisplaySettingsW(self, dev, which, dm):
        return 0                 # the driver "says nothing" - the
                                 # apply works from a fresh DEVMODE

    def ChangeDisplaySettingsExW(self, dev, dm, hwnd, flags, win):
        self.calls.append((dev, flags))
        return 0


try:
    fu = FakeU32()
    real_u32, real_monitors = wm.u32, wm.monitors
    wm.u32 = fu
    wm.monitors = lambda: [{"gdi": r"\\.\DISPLAY3"}]
    entries = [{"gdi": r"\\.\DISPLAY2", "on": True,
                "primary": False, "x": -100, "y": 0, "w": 100,
                "h": 100, "rate": 60},
               {"gdi": r"\\.\DISPLAY1", "on": True, "primary": True,
                "x": 0, "y": 0, "w": 100, "h": 100, "rate": 60},
               {"gdi": r"\\.\DISPLAY3", "on": False, "primary": False,
                "x": 0, "y": 0, "w": 0, "h": 0}]
    ok7, lines = wm.apply_layout(entries)
    seq = fu.calls
    assert ok7, lines
    names = [c[0] for c in seq]
    assert names == [e["gdi"] for e in entries] + [None], names
    flags = dict((c[0], c[1]) for c in seq if c[0])
    assert flags[entries[1]["gdi"]] & wm.CDS_SET_PRIMARY, \
        "primary handed over without the flag"
    assert flags[entries[0]["gdi"]] & wm.CDS_NORESET and \
        not flags[entries[0]["gdi"]] & wm.CDS_SET_PRIMARY
    assert seq[-1][0] is None and seq[-1][1] == 0, "commit missing"
finally:
    wm.u32, wm.monitors = real_u32, real_monitors
print("two-pass order OK (non-primary first, primary last, "
      "disable next, one commit)")

# 8) windows_now tags each window with the monitor it sits on
class TagWM:
    def monitors(self):
        return [dict(AAA)]

    def list_windows(self):
        return [{"proc": "a", "title": "t", "hwnd": 1,
                 "rect": [500, 500, 100, 100], "zoomed": False},
                {"proc": "b", "title": "u", "hwnd": 2,
                 "rect": [90000, 90000, 10, 10], "zoomed": False}]


try:
    profiles.wm = TagWM()
    tagged = profiles.windows_now()
    assert tagged[0]["monitor"] == "AAA", tagged[0]
    assert tagged[1]["monitor"] == "", "off-desk window claimed a monitor"
finally:
    profiles.wm = real_wm
print("monitor tagging OK")
print("ALL PROFILES TESTS OK")
