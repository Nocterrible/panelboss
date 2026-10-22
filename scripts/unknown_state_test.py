"""The boot-in-the-dark scenarios, no cameras or displays:
1) fresh input with unknown screens -> harmless power-on, becomes
   active (this was the stuck case: restart while monitors were dark)
2) idle + unknown + somebody visible -> power-on anyway
3) idle + unknown + nobody -> absent countdown ends in a normal off
4) external dark (0.0 broadcast) while counting -> adopted off, camera
   wakes on presence - driven through the CURRENT vote seam (Oct 12):
   a patched cam_mod.Camera, the real _poll, background opens joined
   between ticks (the blackvote/asyncopen house fixture pattern),
   because an unregistered eye never earns round credit
5) our own OFF echo (0.0 while already off) -> no re-adoption churn
6) the blinded-eye fallback (owner law, the burned-OLED night, Oct 22):
   presence unknown == absent - a no-verdict streak of 300 s with the
   desk's input equally silent engages away the deadline path's way,
   off the pump seam's honest clock (a-e pins, the stock clock faked
   lying)
SIZE LAW note: one scaffold (shared fakes + one _drive); splitting the
pins would clone the seam fakes five times.
"""
import logging
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

from panelboss import camera as cam_mod
from panelboss import config, display
from panelboss.state import PresenceMonitor

_real_camera = cam_mod.Camera


class _FakeCam:
    """An eye that sees somebody: a bright frame (asyncopen's GRAY=128
    proves 128 clears BLACK_CEIL) and NO driver sleep - the doctrine
    below needs votes now; the open's asynchrony is what drain_vote
    joins."""

    def __init__(self, index=0, warmup=4, width=1280, height=720, **kw):
        self.index = index

    def warm_up(self, frames=None):
        return 1

    def read(self, timeout=3, screen=None):
        return np.full((8, 8, 3), 128, np.uint8)

    def release(self):
        pass

    def is_open(self):
        return True


class _Somebody:
    def detect(self, frame):
        return [[0, 0, 8, 8]], np.array([0.9])


def drain_vote(m):
    """Join the background opens the VOTE path spawned (blackvote's
    seam): tick 1 spawns and abstains, tick 2 votes."""
    for op in (getattr(m, "_single_opener", None),
               getattr(getattr(m, "camera", None), "_opener", None)):
        if op is None:
            continue
        while True:
            with op.lock:
                th = [j.thread for j in list(op.inflight.values())
                      if j is not None and j.thread.is_alive()]
            if not th:
                break
            th[0].join(10)


def scratch_cfg(camera_toml):
    d = tempfile.mkdtemp(prefix="panelboss_unknown_")
    with open(os.path.join(d, "config.toml"), "w", encoding="utf8") as fh:
        fh.write("[camera]\nenabled = true\n" + camera_toml)
    cfg = config.get_config(dir=d, verbose=False)
    cfg["power"]["skip_camera_when_blocked"] = False   # never consult
    cfg["power"]["assistant_task"] = False             # the real
    cfg["power"]["restore_windows"] = False            # powercfg / wm
    return cfg

cfg = config.get_config(verbose=False)
# state.flushes the WHOLE cfg on some paths - redirect every write to
# scratch, or these tests flip the live assistant flag off again
# (measured: they did, minutes before "the setting does not persist")
_scratch = os.path.join(os.environ.get("TEMP", "."), "panelboss_test_config.toml")
try:
    os.remove(_scratch)     # consume fresh, never stale (Oct 12 audit:
except OSError:             # shared scratch residue is a false-red
    pass                    # class)
config.write_config = (
    lambda c, path=None, _w=config.write_config: _w(c, _scratch))
# pin the assistant OFF for these scenarios: the live config now
# honestly says true, and then every _on_phase would consult the REAL
# task store - state would correctly wait for whatever apps hold the
# real display right now, and the asserts would be testing the desk,
# not the code
cfg["power"]["assistant_task"] = False
# and the away mode (off wave, Oct 14): the live config carries
# [away] mode = "dim" since the owner's UAT, and scenario 3 asserts
# the STOCK off path - without this pin the dim engine correctly eats
# the turn_off and the assert tests the owner's card setting, not the
# code (same doctrine as the two pins below: never the desk)
cfg["away"]["mode"] = "off"
# same doctrine, second door (unknown_state red, Oct 13 07:21): with
# skip_camera_when_blocked true, _on_phase consults the REAL powercfg
# /requests - on a morning desk someone's display blocker answers, the
# absence round correctly defers, and the off-assert fails on the
# DESK, not the code. The scratch_cfg above already pins this off;
# the shared cfg here must too, or the suite tests whatever apps
# happen to be holding the display at run time.
cfg["power"]["skip_camera_when_blocked"] = False
# and the same for the leave-on budget: scenario 3's intent is the
# PURE absence deadline (absent_since + absent_confirm_sec = 160), but
# the recovery dict rides the live cfg (leave_on_grace_sec 180 today)
# and _on_phase's re_off arm hands out credit at the first tick - the
# loop tops out at 159 and off then depends on WHICH TICK the credit
# lands, i.e. on the owner's recovery setting, not on the code. Pin
# the budget to zero: the deadline is the law under test, nothing else.
cfg["recovery"]["wake_policy"] = "off"
cfg["recovery"]["leave_on_grace_sec"] = 0
# and the tier the ghost-law pins judge against: the same live-file
# hazard wake_burst names (the owner's slider reaches 0.95 - a strict
# scenario must not red because the desk is tuned strict, and an
# assist scenario must not pass because it is tuned loose)
cfg["inference"]["confidence"] = 0.45
sent = []
display.wake = lambda *a, **k: sent.append("wake")
display.turn_off = lambda *a, **k: sent.append("off")
display.set_hold = lambda *a, **k: None
display.foreground_is_fullscreen = lambda: False
from panelboss import wm as _wm                      # the away engine's
_wm.session_is_remote = lambda: False   # transport ear: these are the
#                                       LOCAL-desk laws, and the box
#                                       running them may BE a remote
#                                       session (the Oct-15 exemption
#                                       would otherwise stand the
#                                       broadcast down on its merits)

m = PresenceMonitor(cfg, detector=None)
m._release_camera = lambda: None
m._hold_camera = lambda: None
m._drain_tray = lambda: None
m._grab = lambda: None

# 1) typing after a boot that could not know the screen state
assert m.state == "unknown", m.state
m._poll = lambda: (True, 0.9)
m._on_phase(100.0, idle=0.2)
assert m.state == "active" and sent == ["wake"], (m.state, sent)
print("boot-into-typing OK: power-on sent, state active")

# 2) idle at a dark-but-unproven desk, camera sees a person
sent.clear()
m2 = PresenceMonitor(cfg, detector=None)
m2._release_camera = lambda: None
m2._drain_tray = lambda: None
m2._poll = lambda: (True, 0.9)
m2._on_phase(100.0, idle=90.0)              # unknown -> counting -> poll
assert m2.state == "active" and sent == ["wake"], (m2.state, sent)
print("boot-dark-person OK: power-on sent on the first present frame")

# 3) idle + nobody: the unknown resolves through the normal off path
sent.clear()
m3 = PresenceMonitor(cfg, detector=None)
m3._release_camera = lambda: None
m3._hold_camera = lambda: None
m3._drain_tray = lambda: None
m3._poll = lambda: (False, 0.1)
m3._on_phase(100.0, idle=90.0)
for t in range(101, 166):    # past the 100+absent_confirm_sec deadline -
    m3._on_phase(float(t), idle=90.0)   # the old 160 bound ended at 159,
                                        # exactly one tick short of the
                                        # deadline the store computes, so
                                        # the suite only passed when some
                                        # credit path happened to expire
                                        # early: testing the arithmetic,
                                        # not by luck (Oct 13 red)
assert m3.state == "off" and sent[-1] == "off", (m3.state, sent)
print("boot-dark-nobody OK: absence ends in a normal off (%s)" % sent)

# 4) external dark while counting -> adopted; presence wakes. The
# vote rides the real seam: fbfe9d1 made the open async and f8c7bd8
# made _off_phase consume votes through _round_tally, where a present
# vote from an eye that never registered itself (_note_vote's
# _vote_index) earns no round credit - the old instance-level
# `m4._poll = lambda: (True, 0.9)` bypassed that registration (and the
# round doctrine says an unregistered vote must not count), so the
# fake, not the wake, was stale.
cam_mod.Camera = _FakeCam
m4 = PresenceMonitor(scratch_cfg('index = 1\nmode_on = "boot_per_poll"\n'
                                 'mode_off = "boot_per_poll"\n'),
                     _Somebody())              # the REAL _poll votes here
m4._release_camera = lambda: None
m4._hold_camera = lambda: None
m4._drain_tray = lambda: None
m4._notice_screens(200.0, 0.0)
assert m4.state == "off", m4.state
m4.next_poll = 200.0                        # pretend the off-cadence
                                             # deadline came due already
sent.clear()
t = 210.0
for _ in range(4 * m4.cfg["inference"]["min_hits"] + 4):
    m4._off_phase(t, idle=30.0)             # opening eye: abstain
    drain_vote(m4)                          # the background open lands
    if m4.state != "off":
        break                               # the adopted desk woke
    t += 1.0
assert m4.state == "counting" and sent == ["wake"], (m4.state, sent)
cam_mod.Camera = _real_camera
print("external-dark adopted OK: camera woke it for a person")

# 5) our own off echo does not re-adopt or double-hold
m5 = PresenceMonitor(cfg, detector=None)
m5._release_camera = lambda: None
m5._hold_camera = lambda: None
m5.state = "off"
hold_calls = []
m5._hold_camera = lambda: hold_calls.append(1)
m5._notice_screens(300.0, 0.0)
assert m5.state == "off" and hold_calls == []
print("off-echo ignored OK")

# 6) THE BLINDED-EYE FALLBACK (owner law, the burned-OLED night, Oct 22):
# presence unknown == absent. Three minutes of no verdict AND the desk's
# own input equally silent votes the desk away through the deadline
# path's own _screens_off - the same code path, so the re_off and
# fullscreen gates land the same class of state as a confirmed
# absence. INPUT TRUTH is the dimmer's gated _idle_secs seam, NOT the
# gate's stock get_idle_time: a lying-desk gadget poisons the stock
# clock (the macropad class that forced the Oct-20 pump), and this
# incident family is the blind eye MEETING a poisonable clock, so the
# fallback asks the honest clock; the pump's own fail-open keeps an
# opt-out user on the stock reading. The pins fake the seam
# explicitly; the harness's fakes keep the desk out of every assert.
import panelboss.dimmer as _dim
import panelboss.inputtruth as _it
from panelboss.state._phase import BLINDED_AWAY_SEC

recs6 = []


class Grab6(logging.Handler):
    def emit(self, record):
        recs6.append(record.getMessage())


logging.basicConfig(level=logging.INFO)
logging.getLogger("state").addHandler(Grab6())
assert BLINDED_AWAY_SEC == 300, BLINDED_AWAY_SEC

_real_pump_clock, _real_stock = _it.idle_seconds, display.idle_seconds


def _blind_mon():
    mb = PresenceMonitor(cfg, detector=None)
    mb._release_camera = lambda: None
    mb._hold_camera = lambda: None
    mb._drain_tray = lambda: None
    return mb


def _drive(mb, verdict, t0=100, t1=410, idle=90.0):
    """verdict(t) -> (present, score); the harness ticks once a second,
    the machine re-polls on its own on_poll cadence."""
    for t in range(t0, t1 + 1):
        mb._poll = lambda t=t: verdict(t)
        mb._on_phase(float(t), idle=idle)
        if mb.state == "off":
            break
    return mb


LAW_LINE = "the blinded eye votes absent"
try:
    # (a) 300 s of no verdict + input-idle >= 300 -> engaged, and the
    # stock clock is faked LYING (5 s): only the pump seam's honest
    # reading could have fired - that IS the pin's point
    sent.clear()
    recs6.clear()
    _it.idle_seconds = lambda: 310.0        # the honest ear
    display.idle_seconds = lambda: 5.0      # the lying-desk stock clock
    _dim._PUMP_ON = True                    # the owner's default
    ma = _drive(_blind_mon(), lambda t: (None, None), 100, 410)
    assert ma.state == "off" and sent[-1] == "off", (ma.state, sent)
    assert any(LAW_LINE in r for r in recs6), recs6
    print("blinded eye (a) OK: 300 s of no verdict + honest idle >= 300 "
          "engaged off the pump seam; the lying stock clock (5 s) lost")

    # (b) 300 s of no verdict but input IN THE window -> NOT engaged
    # (the conjunct is real)
    sent.clear()
    recs6.clear()
    _it.idle_seconds = lambda: 45.0
    _dim._PUMP_ON = True
    mb = _drive(_blind_mon(), lambda t: (None, None), 100, 430)
    assert mb.state != "off" and not any(LAW_LINE in r for r in recs6), \
        (mb.state, recs6)
    print("blinded eye (b) OK: 330 s of no verdict with input in the "
          "window did not engage")

    # (c) a decisive present mid-streak resets it: 350 s of None in
    # total with one True at t=250 -> no engage (the streak restarts
    # at 250 and would need 550)
    sent.clear()
    recs6.clear()
    _it.idle_seconds = lambda: 310.0
    _dim._PUMP_ON = True
    mc = _drive(_blind_mon(),
                lambda t: (True, 0.9) if t == 250 else (None, None),
                100, 450)
    assert mc.state != "off" and not any(LAW_LINE in r for r in recs6), \
        (mc.state, recs6)
    print("blinded eye (c) OK: a decisive present at t=250 reset the "
          "streak - no engage in 350 s of mostly-None")

    # (d) a decisive absent runs the classic confirmed-absence clock,
    # FASTER than the 300 s fallback - the fallback never supersedes
    # evidence (off by t~160 here, absent_confirm_sec 60 in this cfg)
    sent.clear()
    recs6.clear()
    _it.idle_seconds = lambda: 310.0
    _dim._PUMP_ON = True
    md = _drive(_blind_mon(), lambda t: (False, 0.1), 100, 410)
    assert md.state == "off" and sent[-1] == "off", (md.state, sent)
    assert not any(LAW_LINE in r for r in recs6), recs6
    print("blinded eye (d) OK: a decisive absent ran the "
          "confirmed-absence clock (off at t=160, far faster than the "
          "fallback) and the fallback never touched it")

    # (e) opt-out honest: input_pump OFF - the seam falls to the stock
    # reading and the fallback engages off it (the owner's clock choice
    # is the pump's; the law's clock is the owner's, either way)
    sent.clear()
    recs6.clear()
    _it.idle_seconds = lambda: 5.0          # the ear, unused now
    display.idle_seconds = lambda: 310.0    # the stock reading the seam
                                            # now rides
    _dim._PUMP_ON = False
    me = _drive(_blind_mon(), lambda t: (None, None), 100, 410)
    assert me.state == "off" and sent[-1] == "off", (me.state, sent)
    assert any(LAW_LINE in r for r in recs6), recs6
    print("blinded eye (e) OK: pump OFF - the seam fell to the stock "
          "reading and the fallback engaged off it")
finally:
    _it.idle_seconds, display.idle_seconds = _real_pump_clock, _real_stock
    _dim._PUMP_ON = None

# 7) THE GHOST AT THE UNKNOWN BOOT (LAW 1, the ghost-law build): a
# sub-floor True on a desk whose screens the app cannot prove are lit
# does NOT get the power-on. The force-on branch is decisive work too,
# and the 00:47 autopsy's person@0.30-on-an-empty-scene is exactly the
# shadow that must not light a panel; the absence countdown starts
# anyway (the scenario-3 shape), the strict presence keeps force-
# owning (scenario 2 above is that pin), and the blinded streak is
# untouched either way (a verdict is a verdict - the two clocks).
sent.clear()
m8 = PresenceMonitor(cfg, detector=None)
m8._release_camera = lambda: None
m8._hold_camera = lambda: None
m8._drain_tray = lambda: None
m8._poll = lambda: (True, 0.30)                   # the ghost
m8._on_phase(100.0, idle=90.0)                    # unknown -> counting
assert m8.state == "counting" and sent == [], (m8.state, sent)
assert m8.absent_since == 100.0, \
    "the ghost skipped the absence clock at the boot seam"
for t in range(101, 166):                         # the countdown runs
    m8._poll = lambda t=t: (True, 0.30)           # THROUGH the ghosts
    m8._on_phase(float(t), idle=90.0)
assert m8.state == "off" and sent[-1] == "off", (m8.state, sent)
print("boot-dark-ghost OK (assist presence never forces the screens "
      "on; the unproven desk counts away through the ghosts)")

print("ALL UNKNOWN-STATE TESTS OK")
