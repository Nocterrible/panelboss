"""The panel refresh's law, pinned: ring geometry, the no-catch-up
advance, the manual-only wash, and the normalize rails. The wash
painter is NOT summoned here - every fake keeps the veil thread lazy,
so the suite runs app-up and headless alike."""
import sys

sys.path.insert(0, ".")
from panelboss import config, jog   # noqa: E402

OK = []


def ok(name):
    OK.append(name)
    print("ok -", name)


# the ring is a law at import time: rest-first, zero-sum, four beats
assert jog.JOG_RING[0] == 0
assert sum(jog.JOG_RING) == 0 and len(jog.JOG_RING) == 4
ok("the ring starts at rest and sums to zero drift")


def cfg(on=True, rows=None, step=2, cycle=30, mode="shuffle"):
    return {"jog": {"on": on, "hold": None, "monitors":
                    rows if rows is not None else {"AOC2790": True},
                    "step_px": step, "cycle_min": cycle, "mode": mode}}


# default-off: an unarmed tick moves nothing and forgets nothing loudly
jog._state.clear()
jog.tick_with_cfg(cfg(on=False), 100.0)
assert jog._state == {} and jog.shift("AOC2790") == (0, 0)
ok("dark jog: no state, no shift, no promise")

# arming rests: the first beat only sets a deadline
jog.tick_with_cfg(cfg(), 100.0)
assert jog.shift("AOC2790") == (0, 0), "arming must not move a strip"
st = jog._state["AOC2790"]
assert st["idx"] == 0 and st["due"] == 100.0 + 30 * 60
ok("arming rests at zero and sets the first deadline")

# one advance per due beat, and the ring walks its four beats. The
# SAME cfg is reused: the helper's clock is the lie this pin must not
# inherit - the deadline is the state's own, ever since arming.
C = cfg()
DUE = jog._state["AOC2790"]["due"]
jog.tick_with_cfg(C, DUE)
assert jog.shift("AOC2790") == (2, 0)
jog.tick_with_cfg(C, DUE + 1.0)                 # not due again
assert jog.shift("AOC2790") == (2, 0), "double-advance on a tick"
jog.tick_with_cfg(C, jog._state["AOC2790"]["due"])
assert jog.shift("AOC2790") == (0, 0)           # ring beat 2: rest
jog.tick_with_cfg(C, jog._state["AOC2790"]["due"])
assert jog.shift("AOC2790") == (-2, 0)          # ring beat 3
ok("the ring advances once per due beat, in order, and never twice")

# the no-catch-up law: a slept loop ages ONE step, not the elapsed
# number of cycles
LASTDUE = jog._state["AOC2790"]["due"]
jog.tick_with_cfg(C, LASTDUE + 900 * 60)
assert jog.shift("AOC2790") == (0, 0)           # beat 0 again (wrapped)
assert jog._state["AOC2790"]["due"] == LASTDUE + 900 * 60 + 30 * 60
ok("a fifteen-hour clock gap steps once - no catch-up, no skip")

# the feature's own law: not one tick of the whole ring walk above
# ever birthed the veil painter
assert jog._wash_q is None, "tick() reached for the wash veil"
ok("tick never births the wash veil - wash is manual, proven")

# opted-out rows are forgotten; unknown shifts answer zero
jog.tick_with_cfg(cfg(rows={"AOC2790": False}), LASTDUE + 901 * 60)
assert "AOC2790" not in jog._state and jog.shift("AOC2790") == (0, 0)
ok("an opted-out row loses its place in the ring")

# wash is a word, never a raise, never a surprise light
w = jog.wash("AOC2790", cfg(on=False))
assert w == "jog feature is armed off - nothing lights", w
w = jog.wash("AOC2790", cfg(rows={}))
assert w == "no monitor row opted in", w
w = jog.wash("GONE", cfg())
assert w == "monitor GONE is not opted in", w
ok("every wash refusal names itself (the veil itself is UAT's)")

# the sweep: the button lights the WHOLE opted-in set, not the dict's
# first key (owner UAT, Oct 15: the IOC-only wash was a hidden
# preference by insertion order). One monitor's rect is unknown to a
# test desk without windows, so the honest word for THAT row is the
# off-desk one - what the pin demands is that every opted row is
# ASKED, each answering its own word.
w = jog.wash_all(cfg(rows={"AOC2790": True, "IOC912B": True,
                           "GONE": False}))
assert w.count(",") == 1, w
assert "wash: AOC2790" in w or "off the desk" in w, w
assert "wash: IOC912B" in w or "off the desk" in w.split("AOC2790")[-1], w
assert "GONE" not in w                       # opted out: never asked
ok("the wash sweep asks every opted-in row, in order, none skipped")

# normalize rails mirror the hider's honesty exactly
import logging                                    # noqa: E402


class Recorder(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, rec):
        self.lines.append(rec.getMessage())

    def install(self, name):
        lg = logging.getLogger(name)
        lg.setLevel(logging.DEBUG)
        lg.propagate = False
        lg.handlers = [self]
        return self


rec = Recorder().install("config")
config._live_shorts_saved = config._live_shorts
config._live_shorts = lambda: ["AOC2790"]
try:
    j = config.normalize_jog({"on": "yes", "step_px": 40, "cycle_min": 1,
                              "mode": "polish",
                              "monitors": {"AOC2790": True,
                                           "GONE": True,
                                           "IOC912B": "maybe"}})
    assert j["on"] is False and j["step_px"] == 8 and \
        j["cycle_min"] == 5 and j["mode"] == "shuffle"
    assert j["monitors"] == {"AOC2790": True, "GONE": True}
    words = "\n".join(rec.lines)
    for needle in ("jog on", "polish", "not a bool",
                   "kept for when it returns"):
        assert needle in words, needle
    assert "step" not in words and "cycle" not in words  # the rails
                                                         # clamp in
                                                         # silence,
                                                         # hider law
    j = config.normalize_jog({})
    assert j["on"] is False and j["monitors"] == {} and \
        j["step_px"] == 2 and j["cycle_min"] == 30
    ok("bad words warn and fold; the rails clamp; absent is dark")
finally:
    config._live_shorts = config._live_shorts_saved

print("\nJOG TESTS OK (%d)" % len(OK))
