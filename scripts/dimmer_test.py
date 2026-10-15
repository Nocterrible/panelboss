"""The dimmer's law, pinned: the skip list, the settle hysteresis
across its 4.0 s boundary, the ramp that never blinks, and the
normalize rails. The suite drives the Veils FSM through its injected
seams - no Tk, no WASAPI, no census - so it runs app-up and headless
alike."""
import logging
import os
import sys

sys.path.insert(0, ".")
from panelboss import config, dimmer   # noqa: E402

OK = []


def ok(name):
    OK.append(name)
    print("ok -", name)


# the settle constant is the wave's own law: 4.0 seconds, no drift
assert dimmer.SETTLE_SEC == 4.0
ok("the audible exemption outlives the session by exactly 4.0 s")

SRC = open("panelboss/dimmer.py", encoding="utf-8").read()
assert "RegisterHotKey" in SRC   # the arm lives here now - the pin
#                                 below is that the DEFAULT registers
#                                 nothing, not that no plumbing does


class Rec:
    def __init__(self):
        self.painted = {}
        self.gone = []

    def paint(self, hwnd, rect, alpha):
        self.painted[hwnd] = (rect, alpha)

    def unveil(self, hwnd):
        self.painted.pop(hwnd, None)
        self.gone.append(hwnd)


def w(hwnd, pid=1, exe="notepad.exe", monitor="AOC2790",
      cloaked=False, iconic=False, fg=False, rect=(10, 10, 800, 600)):
    return {"hwnd": hwnd, "pid": pid, "exe": exe, "monitor": monitor,
            "cloaked": cloaked, "iconic": iconic, "fg": fg,
            "rect": rect}


def cfg(on=True, monitors=None, apps=None, idle_sec=120, ramp_sec=8,
        level=45):
    return {"dimmer": {"on": on,
                       "monitors": monitors if monitors is not None
                       else {"AOC2790": True},
                       "apps": apps or {}, "idle_sec": idle_sec,
                       "ramp_sec": ramp_sec, "level": level,
                       "bound": None}}


class World:
    """One FSM with fake eyes: the window list, the audio set, and
    the idle clock are all mine to move between ticks."""

    def __init__(self, wins, audio=(), idle=999.0):
        self.wins, self.audio, self.idle = list(wins), set(audio), idle
        self.rec = Rec()
        self.v = dimmer.Veils(lambda: self.wins, lambda: set(self.audio),
                              lambda: self.idle, self.rec.paint,
                              self.rec.unveil)

    def tick(self, c, now):
        self.v.tick(c, now)


# default-off law, plus the lazy painter the no-boot promise means
dimmer._veils = None
dimmer.tick(cfg(on=False), 100)
assert dimmer._veils is not None and dimmer._q is None
ok("no boot: the veil painter does not exist until a veil is born")

W = World([w(1)])
W.tick(cfg(on=False), 100)
assert W.rec.painted == {} and W.rec.gone == []
ok("an unarmed dimmer paints nothing and promises nothing")

# opt-in is per-monitor, and un-arming every row tears the field down
W = World([w(1, monitor="AOC2790"), w(2, monitor="IOC912B")])
W.tick(cfg(monitors={"AOC2790": True, "IOC912B": False}), 100)
assert 1 in W.rec.painted and 2 not in W.rec.painted
ok("a false row dims nothing: the opt-in law, per panel")
W.tick(cfg(monitors={"AOC2790": False, "IOC912B": False}), 101)
assert W.rec.painted == {} and 1 in W.rec.gone
ok("un-arming every row takes the whole field down with it")

# the skip list: seven doors and exactly one window gets a veil
W = World([w(1),
           w(2, fg=True),
           w(3, cloaked=True),
           w(4, iconic=True),
           w(5, pid=os.getpid()),
           w(6, exe="chrome.exe"),
           w(7, rect=(0, 0, 0, 400)),
           w(8, pid=555)], audio=[555])
W.tick(cfg(apps={"chrome.exe": True}), 100)
assert set(W.rec.painted) == {1}
assert W.rec.painted[1][1] == 0.45
ok("the skip list is law (fg, cloaked, iconic, own, excluded, zero, "
   "audible) and the veil's alpha IS the level")

# foreground change un-veils on the tick it is seen (the ~0.2 s law)
W = World([w(1), w(2)])
W.tick(cfg(), 100)
assert set(W.rec.painted) == {1, 2}
W.wins = [w(1, fg=True), w(2)]
W.tick(cfg(), 101)
assert 1 not in W.rec.painted and 1 in W.rec.gone
ok("the foreground change un-veils on the tick it is seen")

# the settle boundary, walked from both sides
W = World([w(9, pid=99)], audio=[99])
W.tick(cfg(), 100)
assert 9 not in W.rec.painted
W.audio = set()
W.tick(cfg(), 103.999)
assert 9 not in W.rec.painted
W.tick(cfg(), 104.0)
assert 9 in W.rec.painted
ok("a silent app stays exempt until the 4.0 s settle, to the tick")

# and back to audible is instant, not another settle away
W.rec.gone.clear()
W.audio = {99}
W.tick(cfg(), 104.5)
assert 9 not in W.rec.painted and 9 in W.rec.gone
ok("a window that starts making sound un-dims the tick we learn it")

# the ramp: hold, two more steps, bare by ramp_sec - never a blink
W = World([w(1), w(2)])
W.tick(cfg(), 100)
W.idle = 0.0
W.tick(cfg(), 100)
assert set(W.rec.painted) == {1, 2} and W.rec.painted[1][1] == 0.45
W.tick(cfg(), 103)
assert W.rec.painted[1][1] == 0.3
W.tick(cfg(), 106)
assert W.rec.painted[1][1] == 0.15
W.tick(cfg(), 108)
assert W.rec.painted == {} and 1 in W.rec.gone and 2 in W.rec.gone
ok("the fade holds, steps twice more, and the desk is bare at ramp")

# a moved window drags its veil; a second stillness re-lights mid-fade
W = World([w(1)])
W.tick(cfg(), 100)
W.wins = [w(1, rect=(50, 60, 640, 480))]
W.tick(cfg(), 101)
assert W.rec.painted[1][0] == (50, 60, 640, 480)
ok("a moved window drags its veil along")
W.idle = 0.0
W.tick(cfg(), 102)
W.idle = 999.0
W.tick(cfg(), 103)
assert W.rec.painted[1][1] == 0.45
ok("a second stillness re-lights the fade mid-step")


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
    n = config.normalize_dimmer({"on": "yes", "idle_sec": 9999,
                                 "ramp_sec": 2, "level": 200,
                                 "monitors": {"AOC2790": True,
                                              "GONE": True,
                                              "IOC912B": "maybe"},
                                 "apps": {"chrome.exe": True,
                                          "JUNK": 7},
                                 "bound": ["ctrl", 5]})
    assert n["on"] is False and n["idle_sec"] == 3600 and \
        n["ramp_sec"] == 3 and n["level"] == 90 and \
        n["monitors"] == {"AOC2790": True, "GONE": True} and \
        n["apps"] == {"chrome.exe": True} and n["bound"] is None
    # the UI's ACTUAL write shape round-trips (the gate's F1: the
    # old str-check folded the card's own pair to None at load):
    assert config.normalize_dimmer({"bound": [2, 123]})["bound"] == \
        [2, 123]
    assert config.normalize_dimmer({"bound": ["6", "117"]})["bound"] \
        == [6, 117]                     # the hand-edited belt
    assert config.normalize_dimmer({"bound": [2]})["bound"] is None
    words = "\n".join(rec.lines)
    for needle in ("dimmer on", "is not a bool; the row is dropped",
                   "dimmer bound", "kept for when it returns"):
        assert needle in words, needle
    for needle in ("idle", "ramp", "level"):      # the rails clamp
        assert needle not in words                # in silence, hider
    d = config.normalize_dimmer({})               # law
    assert d["on"] is False and d["monitors"] == {} and d["apps"] == \
        {} and d["idle_sec"] == 120 and d["ramp_sec"] == 8 and \
        d["level"] == 45 and d["bound"] is None
    ok("bad words warn and fold; the rails clamp; absent is dark")
finally:
    config._live_shorts = config._live_shorts_saved

# --- the pause switch is a SOFT stop: it fades like activity does and
# --- comes back the tick the pause lifts - no blink, no re-arming walk
W = World([w(1)])
W.tick(cfg(), 100)                      # veil at full, unpaused
assert W.rec.painted[1][1] == 0.45
dimmer.set_paused(True)
assert dimmer.paused() is True
W.tick(cfg(), 101)                      # paused: the fade clock starts
assert W.rec.painted[1][1] == 0.45      # hold, not blink
W.tick(cfg(), 109)                      # the whole ramp: bare, not killed
assert W.rec.painted == {} and 1 in W.rec.gone
dimmer.set_paused(False)
W.tick(cfg(), 110)
assert W.rec.painted[1][1] == 0.45      # back at full, the next tick
ok("the pause switch fades the field within ramp and lifts it back")

# --- one press pauses, one resumes (the toggle, not the hold)
dimmer.set_paused(False)
dimmer._veils = None
dimmer.hotkey_press()
dimmer.tick(cfg(on=False), 100)
assert dimmer.paused() is True
dimmer.hotkey_press()
dimmer.tick(cfg(on=False), 101)
assert dimmer.paused() is False
ok("a WM_HOTKEY press toggles: one pauses, one resumes")

# --- the hotkey arm, driven through fakes: the stored word registers
# --- ONCE against the live pump window; a taken combo keeps the old
# --- and leaves the dated word; headless answers a word and retries;
# --- the default (bound None) registers NOTHING
reg, unreg = [], []
dimmer._pump_hwnd = lambda: 0x99
dimmer._register = lambda h, i, m, v: (reg.append((m, v)) is None)
dimmer._unregister = lambda h, i: (unreg.append(i) is None)
dimmer._sync_hotkey([0x0002, 123])              # ctrl+F12 as stored
assert reg == [(0x0002 | dimmer.MOD_NOREPEAT, 123)] and \
    dimmer.bound_live()
dimmer._sync_hotkey([0x0002, 123])              # unchanged: no re-knock
assert len(reg) == 1
ok("the stored word registers once against the live pump window")
dimmer._register = lambda h, i, m, v: (                    # the desk
    reg.append((m, v)) is None and                         # says TAKEN
    (m, v) != (0x0001 | dimmer.MOD_NOREPEAT, 65))          # to ONE
dimmer._sync_hotkey([0x0001, 65])
note = dimmer.bind_note()
assert (0x0001 | dimmer.MOD_NOREPEAT, 65) in reg              # knocked
assert reg[-1] == (0x0002 | dimmer.MOD_NOREPEAT, 123)         # restored
assert "taken" in note and note[:2].isdigit()          # and it is dated
assert dimmer.bound_live()                             # OLD one stands
ok("a taken combo answers with the dated word and keeps the old")
dimmer._sync_hotkey(None)                    # esc: clean unbind
assert unreg and not dimmer.bound_live() and dimmer.bind_note() == ""
before = len(reg)
dimmer._pump_hwnd = lambda: None             # headless now
dimmer._sync_hotkey([0x0008, 80])
assert len(reg) == before and "pump" in dimmer.bind_note()
dimmer._pump_hwnd = lambda: 0x99             # the pump came back
dimmer._sync_hotkey([0x0008, 80])
assert reg[-1] == (0x0008 | dimmer.MOD_NOREPEAT, 80)
ok("binding while headless answers a word and retries, never a lie")

# --- the DEFAULT, one more time from a cold arm: bound None registers
# --- NOTHING (the owner's consent law, not a grep)
dimmer._hk = dimmer._hk_tried = None
dimmer._hk_note = ""
reg.clear()
dimmer._sync_hotkey(None)
assert reg == [] and not dimmer.bound_live()
ok("unbound by default means UNBOUND: the arm registers nothing")

# --- the capture rule (gate F4), driven with fake events: a bare key
# --- gets the word and keeps the OLD binding; a chord becomes the
# --- pair, Tk masks translated to the RegisterHotKey flags
pair, word = dimmer.capture_word(0x0000, 65)             # bare 'A'
assert pair is None and word == ("a letter is not a chord - bind a "
                                 "combo, esc clears")
assert dimmer.capture_word(0x4 | 0x8, 123) == ([0x3, 123], None)
assert dimmer.capture_word(0x1, 32) == ([0x4, 32], None)   # shift
assert dimmer.capture_word(0x40, 80) == ([0x8, 80], None)  # win
ok("a bare key is refused (a letter is typed, not stolen); a chord "
   "is translated")

# and the walk-away cancel is wired at the arming seam (FocusOut
# bound when the flag stands, both unbound in the disarm - the UI's
# shape, pinned from the source the card actually ships)
UI = open("panelboss/ui/window/_oled.py", encoding="utf-8").read()
arm = UI[UI.index("def _oled_dim_bind"):
         UI.index("def _oled_dim_disarm")]
assert 'self.bind("<FocusOut>", self._oled_dim_focus_out)' in arm
dis = UI[UI.index("def _oled_dim_disarm"):
         UI.index("def _oled_dim_capture")]
assert 'self.unbind_all("<KeyPress>")' in dis and \
    'self.unbind("<FocusOut>")' in dis
cap = UI[UI.index("def _oled_dim_capture"):
         UI.index("def _dim_words")]
assert "self._oled_dim_disarm()" in cap and \
    "dimmer.capture_word" in cap
ok("FocusOut cancels a pending capture; every completion disarms")

print("\nDIMMER TESTS OK (%d)" % len(OK))


# the ordering truth (gate F4): a modifier's OWN keydown carries
# state=0 - the capture must KEEP WAITING through Control/Shift/Alt/
# Super keydowns, only the chord's letter (state already lit) decides
class _Ev:
    def __init__(self, keysym, state, keycode):
        self.keysym, self.state, self.keycode = keysym, state, keycode

class _Say:
    def __init__(self): self.text = ""
    def configure(self, text=None): self.text = text

class _Self:
    pass

s = _Self()
s._dim_pending = True
s.cfg = {"dimmer": {"bound": [2, 123]}}          # old binding stands
s.oled_say3 = _Say()
import panelboss.ui.window._oled as O
ev_ctrl = _Ev("Control_L", 0, 162)               # the FIRST keydown
O._OledMixin._oled_dim_capture(s, ev_ctrl)
assert s._dim_pending is not False or getattr(s, "_dim_pending", False), \
    "Control_L keydown disarmed the capture - chords unbindable"
assert s.cfg["dimmer"]["bound"] == [2, 123]      # old binding intact
ok("a modifier keydown keeps the capture waiting (chords "
   "bindable in the natural order)")