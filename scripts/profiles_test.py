"""Offline checks for the profile engine: pairing, the HDR belief,
the store (quarantine included), the mismatch gate, and the whole
apply flow against a FAKE wm - the two-pass order, the verify loop,
the best-effort road. The real desk is never touched: no real
apply_layout ever runs here."""
import os
import sys
import tempfile
import types

sys.path.insert(0, r"F:\Projects\ICU-PresenceDetector")

from awaywatch import profiles

# 1) pairing: the three modes on the renamed-browser-tab scenario.
# 'process + title' misses the rename (that is the honest cost);
# 'process' catches it (exact-title pass first, so A keeps its own
# seat and B adopts the renamed tab); open windows that answer no
# pin are never paired.
saved = [{"proc": "opera.exe", "title": "A", "rect": [0, 0, 8, 8]},
         {"proc": "opera.exe", "title": "B", "rect": [9, 9, 8, 8]},
         {"proc": "code.exe", "title": "x", "rect": [5, 5, 8, 8]}]
live = [{"proc": "opera.exe", "title": "renamed!", "hwnd": 1},
        {"proc": "opera.exe", "title": "A", "hwnd": 2},
        {"proc": "code.exe", "title": "x", "hwnd": 3},
        {"proc": "calc.exe", "title": "free", "hwnd": 4}]
pp = profiles.pair(saved, live, "process + title")
p_p = profiles.pair(saved, live, "process")
p_t = profiles.pair(saved, live, "title")
got = lambda ps: sorted((s["title"], l["hwnd"]) for s, l in ps)
assert got(pp) == [("A", 2), ("x", 3)], got(pp)
assert got(p_p) == [("A", 2), ("B", 1), ("x", 3)], got(p_p)
assert got(p_t) == [("A", 2), ("x", 3)], got(p_t)
assert all(l["hwnd"] != 4 for _, l in pp + p_p + p_t), \
    "the unpinned calc window got shoved"
print("pairing OK (3 modes, rename caught only by 'process')")

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
    fp list it is handed, one string per poll."""

    def __init__(self, mons, fps, layout_ok=True):
        self.mons, self.fps = mons, list(fps)
        self.layout_ok = layout_ok
        self.calls, self.entries = [], []
        self.pressed, self.placed, self.rescued = [], [], []

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

    def scenario(fps, mons=DESK, best=False, ok=True):
        tmp6 = tempfile.mkdtemp()
        profiles.save({"hdr_key": "win+alt+b", "hdr_now": "unknown",
                       "last": {}, "profiles": {"p": prof6}}, tmp6)
        data = profiles.load(tmp6)
        f = FakeWM(mons, fps, ok)
        profiles.wm = f
        ok_, say = profiles.apply(data, "p", best_effort=best,
                                  dir=tmp6)
        return ok_, say, f, profiles.load(tmp6)

    # matched desk: layout asked, HDR belief unknown->press->"on"
    # persisted, window placed, rescue ran, last-used recorded
    ok6, say6, f6, disk = scenario([TARGET])
    assert ok6, say6
    assert ("layout", [AAA["gdi"], BBB["gdi"]]) in f6.calls or \
        ("layout", [BBB["gdi"], AAA["gdi"]]) in f6.calls, f6.calls
    assert f6.pressed == ["win+alt+b"], f6.pressed
    assert f6.placed == [(2, (10, 10, 100, 100))], f6.placed
    assert f6.rescued, "auto-rescue skipped"
    assert disk["hdr_now"] == "on", "belief not persisted"
    assert disk["last"].get(TARGET) == "p"
    # 2 s of quiet were actually demanded before believing
    assert f6.calls.count("fp") >= 2, f6.calls

    # different desk, no mercy: refused, nothing touched
    ok6, say6, f6, _ = scenario(["other fp"],
                                mons=[dict(AAA)], best=False)
    assert not ok6 and "different desk" in say6 and f6.entries == []

    # same but try-anyway: the missing panel asked of nothing, the
    # present one kept, windows placed on the shrunken desk
    ok6, say6, f6, _ = scenario(["other fp"], mons=[dict(AAA)],
                                best=True)
    assert ok6 and "never matched" in say6, say6
    assert [e["gdi"] for e in f6.entries] == [AAA["gdi"]], \
        f6.entries
    assert f6.placed, "best effort must still place windows"

    # the driver refuses: no verify, no windows, honest sentence
    ok6, say6, f6, _ = scenario([TARGET], ok=False)
    assert not ok6 and "layout refused" in say6 and not f6.placed
finally:
    profiles.wm, profiles.time = real_wm, real_time
print("apply flow OK (gate, mercy, belief, verify, rescue, refusal)")

# 7) the two-pass order inside wm.apply_layout itself, with the
# config API faked: enables first, new primary LAST with
# CDS_SET_PRIMARY, disables after, one commit at the end.
from awaywatch import wm


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
