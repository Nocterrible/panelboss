"""W3C absorb probe (architect-inline after the W3C2 lane died twice at
zero writes): the shared-u32 pin coexistence the second gate demanded,
and the plan-picker truth table the Ultimate fix settled."""
import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# (a) cross-module u32 coexistence AFTER the taskbar pin pass: import
# order taskbar-first (the gate's failure order), then call through
# BOTH other modules' seams - display's fullscreen guard (GetWindowRect
# + GetForegroundWindow) and wm's window census (its own EnumWindows
# callback through the same shared singleton).
from panelboss import taskbar  # noqa: isort:skip  (the point of the order)
from panelboss import display, wm

assert display.foreground_is_fullscreen() in (True, False)
wins = wm._toplevel_facts()           # _inspect's census: its own
assert isinstance(wins, list), wins   # EnumWindows callback on the
                                      # same shared singleton
assert taskbar.bars() is not None     # taskbar's own EnumWindows path
print("[PASS] a: shared-u32 canon survives taskbar-first import "
      "(display guard, wm census, taskbar bars all answer)")

# (b) picker truth table (the second-gate MED: "performance" could
# only ever mean High Performance; the box's strongest plan was
# invisible to it).
from panelboss import power_plan as pp

ULT = "145a4ce4-b6f7-4c45-bd2b-80d0f847696d"
HP = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
BAL = "381b4222-f694-41f0-9685-ff5bb260df2e"
plans = [{"guid": ULT, "name": "Ultimate Performance"},
         {"guid": HP, "name": "High performance"},
         {"guid": BAL, "name": "Balanced"}]
cases = [
    (("performance", plans), ULT),                 # strongest wins
    (("performance", plans[1:]), HP),              # next, by name
    (("high", plans), HP),                         # no substring theft
    (("", plans), ""),                             # unchanged conservative
    (("zzz", plans), ""),
    (("performance", [{"guid": ULT, "name": "X"}]),  # locale-proof GUID arm
     ULT),
]
for (args, box), want in cases:
    got = pp.pick(box, args)
    assert got == want, (args, got, want)
print("[PASS] b: picker table - strongest-first, absent-scheme falls "
      "through, empty/unknown stay '', localized guids resolve")

# (c) the localized display-gate fixture: a header carrying the real
# subgroup GUID (measured via powercfg /query, not invented) must
# bucket to display even when the label word is foreign.
from panelboss import power

out = power._parse("ANZEIGE :7516b95f-f776-4464-8c53-06167f40cc99:\r\n"
                   "\t\tEine Anwendung m\u00f6chte den Bildschirm\r\n"
                   "System:\r\n\t\tEtwas anderes\r\n")
assert any("Bildschirm" in d for d in out["display"]), out
assert len(out["other"]) == 1, out
print("[PASS] c: localized header WITH its GUID buckets as display "
      "(the locale-independent invariant, live-measured GUID)")

# (d) the production marker chain (third-gate ledger 7: every probe so
# far drove _reconcile_plan with an in-memory cfg that has no _path -
# proving the write->disk->reload->reconcile round trip was skipped):
# temp state dir, marker written through the REAL writer, reloaded,
# reconciled, the cleared state persisted again and re-read.
import os
import tempfile

tmp = tempfile.mkdtemp(prefix="pb_w3cd_")
from panelboss import config, gaming, gaming_watch

cfg = config.get_config(tmp)                       # fresh store in tmp
gsec = cfg.setdefault("gaming", {})
gsec["power_plan_owned"] = True
gsec["power_plan_prev"] = "381b4222-f694-41f0-9685-ff5bb260df2e"
# write_config's single-arg form means CONFIG_DIR, NOT cfg["_path"]
# (the reason _persist_plan_state guards on _path at all) - the probe
# passes the tmp path explicitly or it litters the owner's real store
config.write_config(cfg, tmp)
back = config.get_config(tmp)
assert gaming.plan_owned(back["gaming"]) and \
    gaming.plan_prev(back["gaming"]) == \
    "381b4222-f694-41f0-9685-ff5bb260df2e", back["gaming"]
said = gaming_watch._reconcile_plan(
    back["gaming"],
    active=lambda: "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    pick=lambda s: "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    set_plan=lambda g: g == "381b4222-f694-41f0-9685-ff5bb260df2e")
assert "handed back" in said, said
gaming_watch._persist_plan_state(back)             # full cfg: has _path
again = config.get_config(tmp)
assert not gaming.plan_owned(again["gaming"]), again["gaming"]
print("[PASS] d: marker round-trips the REAL writer and the reconcile "
      "clear reaches the disk - the crash-claim chain is proven, not "
      "asserted against fakes only")

print("w3c absorb probe OK")
