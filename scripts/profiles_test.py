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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panelboss import profiles
from panelboss.wm import _displaycfg as DC    # the fake must speak the
#                                    engine's REAL refusal words (Oct 14)

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

# 3b) KEPT ASIDE, NEVER FOLDED AWAY (owner law, Oct-24 losslessness):
# the rotted entry rides _fossils through a FULL load+save cycle
# verbatim, and the picker's table stays clean of it. A too-strict
# fold may cost invisibility, never the record.
with open(p, "w", encoding="utf-8") as fh:
    fh.write('{"profiles": {"good": {"displays": [], "wins": []},'
             ' "rot": {"displays": "not-a-list"}}, "last": {}}')
got = profiles.load(tmp)
assert "rot" not in got["profiles"] and "good" in got["profiles"]
assert got["_fossils"]["rot"] == {"why": "dropped rotted profile",
                                  "raw": {"displays": "not-a-list"}}, \
    got["_fossils"]
assert profiles.save(got, tmp)
back = profiles.load(tmp)
assert back["_fossils"] == got["_fossils"], "the fossil rotted on rewrite"
assert "rot" not in back["profiles"], "the picker grew it back"
# the login/last drops fossil too - same law, different door
with open(p, "w", encoding="utf-8") as fh:
    fh.write('{"profiles": {}, "last": "not-a-table",'
             ' "login": "junk"}')
got2 = profiles.load(tmp)
assert got2["_fossils"]["login"] == {
    "why": "dropped rotted login record", "raw": "junk"}, got2["_fossils"]
assert got2["_fossils"]["last"] == {
    "why": "dropped rotted last table", "raw": "not-a-table"}
assert got2["last"] == {} and "login" not in got2
# the gate f1 combo: JUNK _fossils BESIDE rotted tables - the fix-up
# order is the whole lesson; a loader that crashes on its own safety
# net is worse than no net
with open(p, "w", encoding="utf-8") as fh:
    fh.write('{"_fossils": "junk", "last": "not-a-table",'
             ' "profiles": {"rot": {"displays": "not-a-list"}}}')
got3 = profiles.load(tmp)
assert isinstance(got3["_fossils"], dict), "the combo crashed the fold"
assert got3["_fossils"]["rot"]["raw"] == {"displays": "not-a-list"}
assert got3["_fossils"]["last"]["raw"] == "not-a-table"
assert got3["profiles"] == {}
print("fossils OK (rotted entries survive load+save inside _fossils;"
      " login/last drops ride the same door; picker reads profiles only)")

# 3c) WRITE-ON-APPLY (the fear-killer made permanent): a relaunch
# wearing a login costume - autostart stamp on an OLD session,
# when='autostart' - returns BEFORE the store is even opened. Not
# one save: the mtime proof from tonight, pinned forever.
import panelboss.cli as CLI
_saves = []
_real_save, _real_age = profiles.save, CLI._session_age_sec
profiles.save = lambda *a, **k: _saves.append(1)
CLI._session_age_sec = lambda: 300.0          # > LOGIN_FRESH_SEC 180
try:
    CLI._restore({"restore": {"when": "autostart"}}, True, None)
finally:
    profiles.save, CLI._session_age_sec = _real_save, _real_age
assert not _saves, _saves
print("write-on-apply OK (stale login stamp: the store is untouched)")

# 4) the gate: identity only. positions/modes may differ freely -
# they are what the profile APPLIES, not what it demands.
prof = {"displays": [{"id": "MONITOR\\AAA", "short": "AAA"},
                     {"id": "MONITOR\\BBB", "short": "BBB"}]}
assert profiles.desk_mismatch(prof, [{"id": "MONITOR\\BBB"},
                                     {"id": "MONITOR\\AAA"}]) == ""
s = profiles.desk_mismatch(prof, [{"id": "MONITOR\\CCC"}])
assert "AAA" in s and "BBB" in s and "CCC" in s, s
# THE GATE-SENTENCE SHORT-NAME LAW (the loud-voice wave): a panel the
# profile knows is ADDRESSED BY ITS SHORT in the sentence the owner
# reads; the raw \\.\-style id may speak only for strangers (the
# unprofiled extra has no short, so it rides its id).
assert "MONITOR\\AAA" not in s and "MONITOR\\BBB" not in s, s
print("gate OK (identity set; swapped panel named both ways; panels "
      "the profile knows addressed by short)")

# 4b) THE PICKER LANDS BY IDENTITY (Oct-24 dossier, the disappearing
# profile as a FROZEN INSTANT): Cappy's A/B/C demo against the app's
# own code. ONE row at a mode the desk has not landed yet: the strict
# fingerprint matcher answers None (a cold boot never wears the
# profile's settled fp), the identity matcher answers the NAME. Once
# the modes land, strict agrees - identity was never a looser truth,
# only an earlier one.
cold = [{"id": "MONITOR\\R1", "short": "R1", "x": 0, "y": 0,
         "w": 1024, "h": 768, "rate": 60, "primary": True}]
want = [dict(cold[0], w=3840, h=2160, rate=144)]
pdata = {"profiles": {"r": {"fp": profiles.target_fp(want),
                            "created": 0.0, "used": 0.0,
                            "match": "process", "hdr": "snap",
                            "displays": want, "wins": []}},
         "last": {}}
assert profiles.default_name(pdata, profiles.target_fp(cold)) is None
assert profiles.name_for_desk(pdata, cold) == "r"
assert profiles.default_name(pdata, profiles.target_fp(want)) == "r"
print("picker OK (identity lands where the frozen fingerprint is "
      "blind; the strict matcher still answers once modes arrive)")

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
    the apply must fall back to the belief path. layout_ok is
    tri-state (the loud-voice wave): True obeys, False kills every
    panel, a list of gdies kills exactly those - the partial desk
    the real engine produces daily."""

    def __init__(self, mons, fps, layout_ok=True, hdr=None):
        self.mons, self.fps = mons, list(fps)
        self.dead = (set() if layout_ok is True else
                     None if layout_ok is False else set(layout_ok))
        self.calls, self.entries = [], []
        self.pressed, self.placed, self.rescued = [], [], []
        self.hdr, self.sets = hdr or [], []
        self.launches = []
        self.unmin = []                  # Oct-24: restored seats
        self.extra_wins = []             # iconic rows the seat walk
        #                                # answers (present-law tests)
        self.commit_rc = 0             # the gate's finding 4 knob:
        #                    a fake whose FINAL commit died (-3 class)

    def monitors(self):
        return self.mons

    def fingerprint(self):
        self.calls.append("fp")
        return self.fps.pop(0) if len(self.fps) > 1 else self.fps[0]

    def apply_layout(self, entries):
        self.entries = entries
        order = [e["gdi"] for e in entries]
        self.calls.append(("layout", order))
        # THE REAL REFUSAL SHAPE (test-only-truth correction, Oct 14):
        # the old fake answered ["refused 87"] - a line no version of
        # the real engine can produce, so the sentence builder was
        # pinned against a fiction and its lines[-1:] truncation hid
        # behind it. The fake now speaks the engine's own dialect:
        # enable rows carrying the driver's rc, one commit row, and a
        # refusal line (short + RC_WHY's human word) per dead panel.
        lines, refused = [], []
        for e in entries:
            rc = -1 if (self.dead is None or e["gdi"] in self.dead) else 0
            lines.append("enable %s %dx%d@%d -> %d" % (
                e["gdi"], e.get("w") or 0, e.get("h") or 0,
                e.get("rate") or 0, rc))
            if rc not in (0, 1):
                refused.append((e.get("short") or e["gdi"],
                                DC.RC_WHY.get(rc, "the driver answered %d"
                                              % rc)))
        lines.append("commit -> %d" % self.commit_rc)
        if self.commit_rc not in (0, 1):
            # the engine's finding-4 line, mirrored faithfully (the
            # fake's whole law since the test-only-truth correction):
            # a dead commit is REFUSED IN WORDS, named 'commit'
            lines.append("refused commit: %s (desk left partial)"
                         % DC.RC_WHY.get(
                             self.commit_rc,
                             "the driver answered %d" % self.commit_rc))
        for who, why in refused:
            lines.append("refused %s: %s (desk left partial)" % (who, why))
        return self.commit_rc in (0, 1) and not refused, lines

    def press_keys(self, combo):
        self.pressed.append(combo)
        return ""

    def hdr_states(self):
        return [dict(r, mode=2 if r["state"] == "on" else 0,
                     precise=True) for r in self.hdr]

    def hdr_set(self, gdi, on):
        self.sets.append((gdi, on))
        self.calls.append(("hdr", gdi, on))   # ordering is a fact the
                                               # amendment pins: after
                                               # layout, never before
        for r in self.hdr:
            if r["gdi"] == gdi:
                r["state"] = "on" if on else "off"
        return ""

    def list_windows(self, include_minimized=False):
        # the Oct-24 feed law mirrored: iconic rows answer ONLY when
        # the caller asked (the seat walk does; capture never does).
        base = (self.base_wins if getattr(self, "base_wins", None)
                is not None else
                [{"proc": "opera.exe", "title": "A", "hwnd": 2,
                  "rect": [0, 0, 5, 5], "zoomed": False}])
        return [dict(w) for w in base] + [
            dict(w) for w in getattr(self, "extra_wins", [])
            if include_minimized or not w.get("iconic")]

    def unminimize(self, hwnd):
        self.unmin.append(hwnd)
        return "ok"

    def launch(self, exe):
        self.launches.append(exe)
        return ""

    def place(self, hwnd, rect, zoomed=False):
        self.placed.append((hwnd, rect, bool(zoomed)))
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
    assert f6.placed == [(2, (10, 10, 100, 100), False)], f6.placed
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

    # THE HDR REFUSAL ADDRESSED (the loud-voice wave): a color command
    # the driver answers with words must speak the panel's PROFILE
    # SHORT and quote the driver - the engine built the addressed shape
    # ("hdr %s: %s" by short at the trouble site) but until the wave no
    # scenario ever made the driver refuse, so the format was an
    # unverified promise. Now it is pinned.
    tmp6 = tempfile.mkdtemp()
    profiles.save({"hdr_key": "win+alt+b", "hdr_now": "unknown",
                   "last": {}, "profiles": {"p": prof6}}, tmp6)

    class MuteHDR(FakeWM):
        def hdr_set(self, gdi, on):         # refuses in words
            self.sets.append((gdi, on))
            return ("this monitor cannot do HDR"
                    if gdi == AAA["gdi"] else "")

    f6 = MuteHDR(DESK, [TARGET], True,
                 [{"gdi": AAA["gdi"], "supported": True,
                   "state": "off"}])
    profiles.wm = f6
    ok6, say6, _info6 = profiles.apply(profiles.load(tmp6), "p",
                                       dir=tmp6)
    assert "hdr AAA: this monitor cannot do HDR" in say6, say6
    assert "never confirmed" in say6, say6   # the refusal is not eaten
    assert f6.sets == [(AAA["gdi"], True)], f6.sets

    # 6a2) THE EXPLICIT PER-PANEL COLOR ASK (amendment 8): a display's
    # true/false outranks the profile-wide ask AND snap (an
    # instruction beats a memory); the wide ask keeps running over
    # the unclaimed panels; the command lands AFTER the layout, never
    # before (the HDR toggle re-enumerates paths); an all-compliant
    # desk is silence with an honest sentence, and a leave-alone
    # profile applies its explicit rows too
    prof6["hdr"] = "snap"
    prof6["displays"][0]["hdr_state"] = "on"      # snap wants AAA on...
    prof6["displays"][0]["hdr"] = False           # ...the row says off
    prof6["displays"][1]["hdr_state"] = "on"      # BBB: only snap
    rows = [{"gdi": AAA["gdi"], "supported": True, "state": "off"},
            {"gdi": BBB["gdi"], "supported": True, "state": "off"}]
    ok6, say6, f6, _, _ = scenario([TARGET], hdr=rows)
    assert ok6, say6
    li = [i for i, c in enumerate(f6.calls) if c[0] == "layout"]
    hi = [i for i, c in enumerate(f6.calls) if c[0] == "hdr"]
    assert li and hi and min(li) < min(hi), f6.calls   # order law
    assert f6.sets == [(BBB["gdi"], True)], \
        "explicit-off AAA is zero-call (already off), snap still " \
        "lights BBB: %s" % (f6.sets,)
    prof6["displays"][0]["hdr"] = True
    prof6["displays"][1]["hdr"] = True            # both explicit on
    prof6["displays"][0].pop("hdr_state")
    prof6["displays"][1].pop("hdr_state")
    ok6, say6, f6, _, _ = scenario(
        [TARGET], hdr=[{"gdi": AAA["gdi"], "supported": True,
                        "state": "off"},
                       {"gdi": BBB["gdi"], "supported": True,
                        "state": "off"}])         # fresh rows: the
                                                  # fake driver keeps
                                                  # the last scenario's
                                                  # memory, and a
                                                  # compliant BBB
                                                  # owes no command
    assert sorted(f6.sets) == sorted([(AAA["gdi"], True),
                                      (BBB["gdi"], True)]), f6.sets
    assert "AAA on (verified)" in say6 and "BBB on (verified)" \
        in say6, say6
    prof6["hdr"] = "leave alone"                  # explicit rows ride
    rows2 = [{"gdi": AAA["gdi"], "supported": True, "state": "on"},
             {"gdi": BBB["gdi"], "supported": True, "state": "on"}]
    ok6, say6, f6, _, _ = scenario([TARGET], hdr=rows2)
    assert f6.sets == [] and "already wear" in say6, say6
    prof6["displays"][0].pop("hdr")
    prof6["displays"][1].pop("hdr")
    prof6["hdr"] = "on"

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

    # the driver refuses EVERY panel: no verify, no windows - and the
    # sentence (loud-voice wave) names EVERY dead panel by its profile
    # short and speaks the driver's rc in human words, not the last
    # log line's number. No applied clause: nothing did apply.
    ok6, say6, f6, _, info6 = scenario([TARGET], ok=False)
    assert not ok6 and "layout refused" in say6 and not f6.placed
    assert "refused AAA" in say6 and "refused BBB" in say6, say6
    assert "the driver failed the switch" in say6, say6
    assert r"\\.\DISPLAY" not in say6, say6      # short, never the slot
    assert " - applied: " not in say6, say6
    assert info6.get("no_shows", []) == [], "refused apply chased windows"

    # THE PARTIAL DESK (the loud-voice wave, then the gate's finding
    # 1): AAA died, BBB took the mode - and BOTH halves of the
    # sentence speak PROFILE SHORTS. The old applied clause re-parsed
    # the enable rows and leaked the raw GDI slot
    # ("\\.\DISPLAY2 1920x1080@144") into a sentence whose refusal
    # half correctly shouted shorts: half-lawful. Applied is built
    # from the entries now - the no-slot pin below is the law's
    # teeth.
    ok6, say6, f6, _, info6 = scenario([TARGET], ok=[AAA["gdi"]])
    assert not ok6, say6
    assert "layout refused" in say6 and "refused AAA" in say6, say6
    assert "the driver failed the switch" in say6, say6
    assert " - applied: BBB" in say6, say6      # the SHORT applies
    assert r"\\.\DISPLAY" not in say6, say6     # no slot, half or whole
    assert not f6.placed, "a refused apply chased windows"

    # A DEAD COMMIT (the gate's finding 4): every row took its mode
    # and the final commit answer died (-3, the registry class) -
    # the numberless truth must ride the refuse-commit row through
    # the SAME refusal filter (free coverage), and the applied clause
    # must STAY SILENT: a dead commit applied NOTHING, whatever the
    # per-panel rows say. The old shape was a bare "commit -> -3":
    # a number without a word, untestable and unreadable.
    tmp6 = tempfile.mkdtemp()
    profiles.save({"hdr_key": "win+alt+b", "hdr_now": "unknown",
                   "last": {}, "profiles": {"p": prof6}}, tmp6)
    f6 = FakeWM(DESK, [TARGET], True)
    f6.commit_rc = -3
    profiles.wm = f6
    ok6, say6, _info6 = profiles.apply(profiles.load(tmp6), "p",
                                       dir=tmp6)
    assert not ok6, say6
    assert ("refused commit: the registry could not be written"
            in say6), say6
    assert " - applied: " not in say6, say6     # dead commit, zero claims
    assert r"\\.\DISPLAY" not in say6, say6
    assert not f6.placed, "a dead commit chased windows"

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
             seed_login=None, scope="full"):
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

        def w_windows(self, include_minimized=False):
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
                                          login=login, dir=tmp7,
                                          scope=scope)
        return ok7, say7, info7, w7

    # 6b2) THE OWNER'S ONE-CLICK PARTIAL (Oct 16): a scope="windows"
    # apply - the verb the profiles card's new "restore my windows"
    # button rides - SPAWNS the missing app and seats it exactly as the
    # full apply does, while never asking a driver anything. This is the
    # whole engine-side surface of that button: the shape already
    # existed, so the button adds none. (Its answer is the shared say
    # path's own "monitors untouched (windows only)" line, pinned here.)
    ok7, say7, info7, w7 = run7(wake_after=1, scope="windows")
    assert ok7 and w7.launches == [r"C:\x\opera.exe"], (say7, w7.launches)
    assert w7.placed == [(7, (10, 10, 100, 100), False)], w7.placed
    assert "monitors untouched" in say7, say7
    assert w7.entries == [], "windows-only asked the drivers"
    assert info7["no_shows"] == [], info7

    # wakes on the next poll: the exe ran once, the window was moved,
    # and the wait ended the moment it showed - not a second longer
    ok7, say7, info7, w7 = run7(wake_after=1)
    assert ok7 and w7.launches == [r"C:\x\opera.exe"], (say7,
                                                        w7.launches)
    assert w7.placed == [(7, (10, 10, 100, 100), False)], w7.placed
    assert info7["no_shows"] == [], info7
    assert w7.polls <= 3, "waited far past the window's arrival"

    # never wakes, MANUALLY (Oct-24 law): the launch is issued with
    # NO delay and NO patience - a restore the owner watches waits
    # for nothing, so the waited-through health-check line does not
    # exist ("would not start"/"within N s" are boot-path words);
    # the seat is a miss this walk saw, and it is LOUD once anyway.
    ok7, say7, info7, w7 = run7()
    assert ok7 and info7["no_shows"] == [
        {"proc": "opera.exe", "title": "A"}], info7
    assert w7.launches == [r"C:\x\opera.exe"], w7.launches
    assert "within" not in say7 and "would not start" not in say7, \
        say7                                    # no blame, no wait
    assert profiles.time.monotonic() == w7.launch_times[0], \
        "the manual path spent patience after the launch"

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
        def list_windows(self, include_minimized=False):
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
    assert w7.placed == [(8, (10, 10, 100, 100), False)], w7.placed

    # --- A MINIMIZED WINDOW IS PRESENT (owner ruling, Oct 24 launch
    # day): the seat walk answers iconic windows, RESTORES them, and
    # places them - zero launch issued (the open pin never reached
    # the launcher) and zero patience spent (a manual restore waits
    # nothing). A zoomed seat rides place()'s dance (the SW_RESTORE
    # then SW_SHOWMAXIMIZED sequence is pinned in layout_test 3e).
    prof8 = {"fp": TARGET, "match": "process + title",
             "hdr": "leave alone",
             "displays": [dict(AAA), dict(BBB)],
             "wins": [{"proc": "opera.exe", "title": "A",
                       "rect": [10, 10, 100, 100], "zoomed": True,
                       "monitor": "AAA", "exe": r"C:\x\opera.exe",
                       "match": "process + title", "open": True,
                       "wait": 10}]}
    tmp8 = tempfile.mkdtemp()
    profiles.save({"hdr_key": "win+alt+b", "hdr_now": "unknown",
                   "last": {}, "profiles": {"p": prof8}}, tmp8)
    f8 = FakeWM(DESK, [TARGET])
    f8.base_wins = []                      # the app shows NOTHING
    #                                       open: only the taskbar
    #                                       button answers the seat
    f8.extra_wins = [{"proc": "opera.exe", "title": "A", "hwnd": 9,
                      "rect": [9000, 9000, 100, 100],
                      "zoomed": False, "iconic": True}]
    profiles.wm = f8
    t8 = profiles.time.monotonic()
    ok8, say8, info8 = profiles.apply(profiles.load(tmp8), "p",
                                      dir=tmp8, scope="windows")
    assert ok8 and f8.unmin == [9], (say8, f8.unmin)
    assert f8.placed == [(9, (10, 10, 100, 100), True)], f8.placed
    assert f8.launches == [], "a minimized window was RE-LAUNCHED"
    assert profiles.time.monotonic() == t8, \
        "the manual walk spent patience on a window that was alive"
    assert info8["no_shows"] == [], info8
    assert "1 placed" in say8 and "would not start" not in say8, say8

    # patience is a BOOT grace, and boot HONORS the rail: 300 s
    # stored (the 5-minute end), the login grace on top, and the
    # fake clock waits every second of it before the miss is spoken.
    ok7, say7, info7, w7 = run7(lambda r: r.update(wait=300),
                                login=True)
    assert "within 360 s" in say7, say7      # 300 rail + 60 login
    assert w7.polls >= 360, "the boot grace skipped the rail"
    print("open pins OK (wake, per-pin wait, loud once then quiet, "
          "refused launch, launcher browse, no double-nag)")
    print("present law OK (minimized restored and seated, zero "
          "launches, manual waits nothing; boot honors the rail)")

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
        # The C6a refusal law made this fixture honest: the old
        # "return 0, say nothing" shape is EXACTLY a powered-off
        # monitor's answer (the module's own :44 docstring case),
        # and apply_layout now refuses to stage enable off it -
        # the audit's -2 illusion in action. A driver that CAN
        # answer: nonzero rc and a filled mode (probe-verified
        # shape against a live CDD device, Oct 13).
        import ctypes
        from panelboss.wm._winapi import DEVMODEW
        d = ctypes.cast(dm, ctypes.POINTER(DEVMODEW)).contents
        d.dmDeviceName = "FAKE"
        d.dmPelsWidth, d.dmPelsHeight = 1280, 720
        d.dmDisplayFrequency = 60
        return 1

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

# 9) THE create-now PIN (defect 1): a capture into an EMPTY store must
#    yield EXACTLY ONE loadable, default-filled profile card - the
#    capture is the bare skeleton the redesign's tri-state hdr guard
#    could have dropped on reload. Drives the real create->save->load
#    round-trip on a fake desk; the store is a scratch dir, never the
#    owner's profiles.json.
try:
    class _DeskWM:
        def monitors(self):
            return [dict(AAA)]
        def fingerprint(self):
            return "FP-AAA"
        def hdr_states(self):
            return []                      # silent {} -> hdr_state None
    profiles.wm = _DeskWM()                # one monitor (AAA), no windows
    tmp9 = tempfile.mkdtemp()
    empty = profiles.load(tmp9)
    assert empty["profiles"] == {}, "expected an empty store to start"
    profiles.create(empty, "desk1", dir=tmp9)
    back9 = profiles.load(tmp9)
    assert list(back9["profiles"]) == ["desk1"], back9["profiles"]
    card = back9["profiles"]["desk1"]
    # default-filled: the capture wrote the live panel, tri-state hdr
    # survived the reload guard (None = hands off, the only legal null)
    assert card["displays"] and card["displays"][0]["id"] == "MONITOR\\AAA", \
        card["displays"]
    assert card["displays"][0].get("hdr", None) in (True, False, None)
    assert card["hdr"] in ("snap", "on", "off", "leave alone", "toggle"), \
        card["hdr"]
    assert card["wins"] == []
    # a SECOND capture lands beside it, never over the first
    profiles.create(back9, "desk2", dir=tmp9)
    assert sorted(profiles.load(tmp9)["profiles"]) == ["desk1", "desk2"]
finally:
    profiles.wm = real_wm
print("create-now OK (empty store -> one loadable default-filled card)")
print("ALL PROFILES TESTS OK")
