"""W2C probe: the four audit MEDs' regression nets, offline (no
window, no powercfg, no disk). Run from repo root:
python scripts/w2c_probe.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------- (a) --
# merge_seen exact-first matching: python.exe must NOT eat pythonw.exe's
# override (the old bidirectional substring folded it into the EARLIER
# row - first match won).
from panelboss.ui import overrides as OV  # noqa: E402

res = {"requests": [
    {"caller": "process", "object": "C:\\py\\python.exe",
     "request": "DISPLAY", "text": "python.exe", "overridden": False},
    {"caller": "process", "object": "C:\\py\\pythonw.exe",
     "request": "DISPLAY", "text": "pythonw.exe", "overridden": False}],
    "override_entries": [
        {"cat": "process", "name": "pythonw.exe", "types": ["SYSTEM"]}]}
seen = OV.merge_seen({}, res)
w = seen[("process", "pythonw.exe")]
p = seen[("process", "python.exe")]
assert w["overridden"] == {"SYSTEM"} and p["overridden"] == set(), seen
assert len(seen) == 2, seen
print("ok - override lands on the exact row (python.exe vs pythonw.exe)")

# ambiguous substring ("python" names BOTH rows): warn + skip - the
# override keeps its own row, the two request rows stay clean
res2 = {"requests": res["requests"], "override_entries": [
    {"cat": "process", "name": "python", "types": ["DISPLAY"]}]}
seen2 = OV.merge_seen({}, res2)
assert len(seen2) == 3, seen2                     # a third row of its own
assert seen2[("process", "python")]["overridden"] == {"DISPLAY"}
assert seen2[("process", "python.exe")]["overridden"] == set()
assert seen2[("process", "pythonw.exe")]["overridden"] == set()
print("ok - ambiguous substring warns and skips the fold (never guesses)")

# ---------------------------------------------------------------- (b) --
# plan ownership: switch MARKS the store, handback CLEARS it, and the
# boot reconcile flips a stale claim back (fake exec, no powercfg).
import panelboss.gaming as gaming           # noqa: E402
import panelboss.gaming_watch as gw         # noqa: E402
import panelboss.power_plan as ppl          # noqa: E402

real = (ppl.plans, ppl.active, ppl.set_plan, ppl._run)
FAST = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"          # the real ones,
BAL = "381b4222-f694-41f0-9685-ff5bb260df2e"           # measured /list
cur, PPS = [BAL], []
ppl.plans = lambda: [{"guid": FAST, "name": "Höchstleistung"},
                     {"guid": BAL, "name": "Ausgewuchtet"}]
ppl.active = lambda: cur[0]


def _sp(g):
    PPS.append(g)
    cur[0] = g
    return True


ppl.set_plan = _sp
GCFG = {"power_plan": "high performance"}              # English config
gw._apply_power_plan({}, GCFG, True, {})               # switch
assert PPS == [FAST] and cur[0] == FAST, PPS           # localized names,
                                                       # GUID layer picked
assert gaming.plan_owned(GCFG) and GCFG["power_plan_prev"] == BAL, GCFG
gw._apply_power_plan({"power_plan": {"saved": BAL, "active": FAST}},
                     GCFG, False, {})                  # clean handback
assert not gaming.plan_owned(GCFG), GCFG
print("ok - switch marks the store, handback clears it")

# the crash class: marker set, side memory gone (cur already FAST)
GCFG2 = {"power_plan": "high performance"}
gaming.mark_plan_owned(GCFG2, BAL)
cur[0] = FAST
gw._boot_reconcile({"gaming": GCFG2})
assert PPS[-1] == BAL and not gaming.plan_owned(GCFG2), (PPS, GCFG2)
print("ok - boot with marker + current=perf flips back and clears")

# moved by someone else: current is NOT our perf plan -> clear, no swap
gaming.mark_plan_owned(GCFG2, BAL)
cur[0] = "d" * 8 + "-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
n = len(PPS)
gw._boot_reconcile({"gaming": GCFG2})
assert not gaming.plan_owned(GCFG2) and len(PPS) == n, (PPS, GCFG2)
print("ok - boot with a moved plan just voids the claim (no swap)")
ppl.plans, ppl.active, ppl.set_plan, ppl._run = real

# ---------------------------------------------------------------- (c) --
# localized powercfg output parses the SAME GUID the English one does
# (shape copied from power_plan_test.py's SAMPLE), and the display
# gate answers on a header that carries its GUID instead of the words.
EN = ("Power Scheme " + FAST + " (High performance)\n"
      "    Alternative name: High performance\n")
DE = ("Energieschema " + FAST + " (Höchstleistung)\n"
      "    Alternativer Name: Höchstleistung\n")
got = []
for text in (EN, DE):
    ppl._run = lambda args, _t=text: _t if args == ["/list"] else ""
    found = ppl.plans()
    assert len(found) == 1 and found[0]["guid"].lower() == FAST, found
    got.append(found[0]["guid"].lower())
assert got[0] == got[1]
print("ok - German /list parses the same scheme GUID as English")

from panelboss import power as pw  # noqa: E402

DE_GATE = ("ANZEIGE [7516b95f-f776-4464-8c53-06167f40cc99]:\n"
           "[PROCESS] \\Device\\HarddiskVolume8\\player.exe\n"
           "Video Wake Lock\n")
parsed = pw._parse(DE_GATE)
assert any("player.exe" in x for x in parsed["display"]), parsed
EN_GATE = "DISPLAY:\n[PROCESS] player.exe\nVideo Wake Lock\n"
assert any("player.exe" in x for x in pw._parse(EN_GATE)["display"])
assert not pw._is_display_section("SLEEP")            # the rest stays put
print("ok - the display gate answers to the subgroup GUID, words intact")

print("W2C PROBE OK")
