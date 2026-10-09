"""Window-restore (wm) + its wiring into the state machine.

The move logic is pinned with fakes (no real window is dragged); the
read-only OS calls (fingerprint/snapshot) are exercised live because
they must not raise or hang. The whole point of the wake side - that
a restore is attempted on EVERY return to a lit desk, including the
mouse-jiggle the display watcher reports - is pinned at the three
trigger sites, and that a restore abandons the instant a newer
snapshot (or no snapshot) exists."""
import os
import sys

sys.path.insert(0, r"F:\Projects\ICU-PresenceDetector")
from awaywatch import config, state, wm
from awaywatch.state import PresenceMonitor


# 1) wanted(): the pure decision, one disqualifier flipped at a time.
def fact(**over):
    w = dict(visible=True, owned=False, iconic=False, cloaked=False,
             tool=False, ghost=False, furniture=False,
             rect=(0, 0, 800, 600))
    w.update(over)
    return w


assert wm.wanted(fact()), "a plain window must be movable"
for key in ("owned", "iconic", "cloaked", "tool", "ghost", "furniture"):
    assert not wm.wanted(fact(**{key: True})), key + " must be left alone"
assert not wm.wanted(fact(visible=False)), "not visible = not ours"
assert not wm.wanted(fact(rect=None)), "no rect = no move"
assert not wm.wanted(fact(rect=(0, 0, 0, 0))), "zero-area is a ghost"
print("wanted OK (six disqualifiers + invisible + empty rect)")

# 2) read-only OS calls, live: must not raise, fingerprint is stable.
fp = wm.fingerprint()
assert isinstance(fp, str) and fp.count("@") >= 1, fp
assert fp == wm.fingerprint(), "fingerprint wobbles between calls"
snap = wm.snapshot()
assert set(snap) == {"fp", "ts", "wins"}
assert all(wm.wanted(w) for w in snap["wins"]), "snapshot kept junk"
print("live reads OK (fingerprint %d monitor(s), snapshot %d window(s))"
      % (fp.count("|") + 1, len(snap["wins"])))


# 3) apply(): counting, at the seam, no real geometry involved.
_real_rect, _real_move = wm.true_rect, wm._move
try:
    wm.true_rect = lambda h: {1: (0, 0, 10, 10),      # already right
                              2: (5, 5, 10, 10),      # needs a move
                              3: None}[h]             # gone in the dark
    wm._move = lambda w: "ok"
    fake = {"wins": [{"hwnd": 1, "rect": (0, 0, 10, 10)},
                     {"hwnd": 2, "rect": (0, 0, 10, 10)},
                     {"hwnd": 3, "rect": (0, 0, 10, 10)}]}
    assert wm.apply(fake) == (1, 1, 1, 0)             # moved/kept/gone/skip
    wm._move = lambda w: "gone"
    assert wm.apply({"wins": [{"hwnd": 2, "rect": (0, 0, 10, 10)}]}
                    ) == (0, 0, 1, 0)
    wm._move = lambda w: "fail"
    assert wm.apply({"wins": [{"hwnd": 2, "rect": (0, 0, 10, 10)}]}
                    ) == (0, 0, 0, 1)
finally:
    wm.true_rect, wm._move = _real_rect, _real_move
print("apply OK (kept / moved / gone / failed counted honestly)")


# 4) wait_settled: quiet-and-matching, cancelled, timed-out.
class FakeTime:
    def __init__(self):
        self.t = 0.0

    def sleep(self, s):
        self.t += s

    def monotonic(self):
        return self.t


_real_time, _real_fp = wm.time, wm.fingerprint
try:
    wm.time = FakeTime()
    wm.fingerprint = lambda: "DESK-A"                 # settles immediately
    assert wm.wait_settled(budget=30, stable=2) == "DESK-A"

    wm.time = FakeTime()
    calls = {"n": 0}

    def never_quiet():                                # topology churns
        calls["n"] += 1
        return "X%d" % calls["n"]

    wm.fingerprint = never_quiet
    assert wm.wait_settled(budget=3, stable=2) != "DESK-A", "never settled"

    wm.time = FakeTime()
    wm.fingerprint = lambda: "DESK-A"
    assert wm.wait_settled(budget=30, stable=2,
                           cancel=lambda: True) is None, "should cancel"
finally:
    wm.time, wm.fingerprint = _real_time, _real_fp
print("wait_settled OK (settles / churns past budget / cancels)")


# 5) restore(): the three exits, with the wait and the move mocked.
_real_wait, _real_apply = wm.wait_settled, wm.apply
try:
    wm.wait_settled = lambda **k: None
    assert wm.restore({"fp": "A"}) == "superseded"
    wm.wait_settled = lambda **k: "B"
    assert wm.restore({"fp": "A"}) == "topology"
    wm.wait_settled = lambda **k: "A"
    moved = []
    wm.apply = lambda s: moved.append(s)
    assert wm.restore({"fp": "A", "wins": []}) == "applied" and moved
finally:
    wm.wait_settled, wm.apply = _real_wait, _real_apply
print("restore OK (superseded / other desk / applied)")

# 6) the state wiring: snapshot on off, restore on every wake.
cfg = config.get_config(verbose=False)
_scratch = os.path.join(os.environ.get("TEMP", "."), "icu_test_config.toml")
config.write_config = (
    lambda c, path=None, _w=config.write_config: _w(c, _scratch))
# virgin defaults (a live file can hold anything - the window suite
# pins the switch against THAT, so the promise itself is pinned here)
_fresh = os.path.join(os.environ.get("TEMP", "."), "icu_fresh_cfg")
os.makedirs(_fresh, exist_ok=True)
_virgin = config.get_config(dir=_fresh, verbose=False)
assert _virgin["power"]["restore_windows"] is True, "the tip's promise"
assert _virgin["ui"]["start_minimized"] is False, "boot opens the window"
cfg["power"]["restore_windows"] = True
cfg["power"]["assistant_task"] = False

snap_log, restore_log = [], []
_real_snap = wm.snapshot


def fake_snap():
    s = {"fp": "DESK", "ts": 0, "wins": [{"hwnd": 1, "rect": (0, 0, 5, 5),
                                          "zoomed": False}]}
    snap_log.append(s)
    return s


wm.snapshot = fake_snap
wm.restore_async = lambda snap, cancel=None: restore_log.append(
    (snap, cancel))

display_stubs = {"wake": 0, "off": 0}
state.display.wake = lambda *a, **k: display_stubs.__setitem__(
    "wake", display_stubs["wake"] + 1)
state.display.turn_off = lambda *a, **k: display_stubs.__setitem__(
    "off", display_stubs["off"] + 1)

m = PresenceMonitor(cfg, detector=None)

# off remembers the layout while the screens are still lit
m._remember_layout()
assert m.layout is not None and len(snap_log) == 1
gen_after_off = m.layout_gen

# restore hands the snapshot over and pops it (one restore per dark)
m._restore_layout()
assert len(restore_log) == 1 and restore_log[0][0] is snap_log[0]
assert m.layout is None, "snapshot consumed"
m._restore_layout()
assert len(restore_log) == 1, "no second restore without a new snapshot"

# the cancel predicate a newer off arms
_, cancel = restore_log[0]
assert cancel() is False, "fresh restore is still valid"
m._remember_layout()                        # a fresh dark spell
assert cancel() is True, "superseded by the newer snapshot"

# every return to a lit desk fires a restore, whoever lit it
fired = []
m._restore_layout = lambda: fired.append(1)
m.layout = {"fp": "X", "ts": 0, "wins": [{}]}
m._wake(1.0, 0.9)
m.layout = {"fp": "X", "ts": 0, "wins": [{}]}
m._force_on(2.0, "test boot")
m.layout = {"fp": "X", "ts": 0, "wins": [{}]}
m.state = "off"
m._notice_screens(3.0, 1.0)                 # the jiggle the user means
assert len(fired) == 3, fired

print("wiring OK (snapshot on off, restore on wake/force-on/jiggle, "
      "consumed once, superseded on new off)")

wm.snapshot = _real_snap

# the shared-handle diplomacy: wm pins user32 argtypes at import on
# the process-wide windll cache, so display.py's GetWindowRect -
# a DIFFERENT class (wintypes.RECT), identical layout - must still
# be accepted there. Measured: POINTER(wm.RECT) poisoned the shared
# handle and killed every _screens_off tick (LP_RECT vs pointer to
# RECT) until the rect argument became a plain void pointer
from awaywatch import display as disp
assert isinstance(disp.foreground_is_fullscreen(), bool)
assert isinstance(wm.list_windows(), list)
print("shared user32 handle OK (display and wm both get window rects)")

print("ALL LAYOUT TESTS OK")
