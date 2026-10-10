"""power_plan offline checks + READ-ONLY live calls (list/active
only; never /setactive from a test). Run from repo root:
python scripts/power_plan_test.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from awaywatch import power_plan as pp  # noqa: E402

real_run = pp._run
GUIDS = "8c5e7fda-e8bf-11e5-9023-aa40e0c00000"
SAMPLE = ("Power Scheme " + GUIDS + " (High performance)\n"
          "    Alternative name: High performance\n")
pp._run = lambda args: SAMPLE if args == ["/list"] else ""  # parse: parens
found = pp.plans()
assert len(found) == 1 and found[0]["name"] == "High performance"
print("ok - parenthesized name parsed")

LOCALIZED = ("La combinación de energia esta en modo Equilibrado\n"
             "scheme " + GUIDS + "\n")
pp._run = lambda args: LOCALIZED if args == ["/list"] else ""
found = pp.plans()
assert len(found) == 1
assert found[0]["name"].startswith("La combinaci")   # line above
print("ok - localized layout: name taken from the guid's line above")

pp._run = lambda args: ""
assert pp.plans() == [] and pp.active() is None
assert pp.set_plan("") is False and pp.set_plan(GUIDS) is False
print("ok - silent powercfg fails open everywhere")

W = [{"guid": GUIDS, "name": "High performance"},
     {"guid": "a" * 8 + "-abcd-dabc-abcd-abcdefabcdef",
      "name": "Balanced"}]
assert pp.pick(W, "high") == GUIDS
assert pp.pick(W, GUIDS.upper()) == GUIDS.upper()   # bare guid wins
assert pp.pick(W, "balanced") == W[1]["guid"]
assert pp.pick(W, "no such plan") == ""
assert pp.pick(W, "") == ""
print("ok - pick(): fragment, bare guid, miss, empty")

pp._run = real_run                    # the live desk deserves the
                                      # real powercfg
live = pp.plans()
act = pp.active()
assert act and any(p["guid"].lower() == act.lower() for p in live)
print("ok - live desk: %d plan(s), active=%s listed among them"
      % (len(live), act))
print("  live plans:", ", ".join(p["name"] or "?" for p in live))
print("POWER PLAN TESTS OK")
