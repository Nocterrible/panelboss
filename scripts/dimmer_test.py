"""The dimmer's law, pinned: the skip list, the settle hysteresis
across its 4.0 s boundary, the ramp that never blinks, and the
normalize rails. The suite drives the Veils FSM through its injected
seams - no Tk, no WASAPI, no census - so it runs app-up and headless
alike."""
import ctypes
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
      cloaked=False, iconic=False, fg=False, rect=(10, 10, 800, 600),
      cls="ApplicationAppWindow"):
    return {"hwnd": hwnd, "pid": pid, "exe": exe, "cls": cls,
            "monitor": monitor,
            "cloaked": cloaked, "iconic": iconic, "fg": fg,
            "rect": rect}


def cfg(on=True, monitors=None, apps=None, idle_sec=120, ramp_sec=8,
        always=None, **kw):
    # NO level default here (gate finding 2): the helper's old 45 was
    # the retired default wearing an honest face, and a regression of
    # the shipped 20 would have ridden under it. Every call names its
    # level; the bare-dict pin at SHIPPED-DEFAULT owns the one truth.
    level = kw.pop("level")
    assert not kw, "unknown cfg kwargs: %r" % (sorted(kw),)
    return {"dimmer": {"on": on,
                       "monitors": monitors if monitors is not None
                       else {"AOC2790": True},
                       "always": always or {},
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
dimmer.tick(cfg(level=30, on=False), 100)
assert dimmer._veils is not None and dimmer._q is None
ok("no boot: the veil painter does not exist until a veil is born")

W = World([w(1)])
W.tick(cfg(level=30, on=False), 100)
assert W.rec.painted == {} and W.rec.gone == []
ok("an unarmed dimmer paints nothing and promises nothing")

# opt-in is per-monitor, and un-arming every row tears the field down
W = World([w(1, monitor="AOC2790"), w(2, monitor="IOC912B")])
W.tick(cfg(level=30, monitors={"AOC2790": True, "IOC912B": False}), 100)
assert 1 in W.rec.painted and 2 not in W.rec.painted
ok("a false row dims nothing: the opt-in law, per panel")
W.tick(cfg(level=30, monitors={"AOC2790": False, "IOC912B": False}), 101)
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
W.tick(cfg(level=30, apps={"chrome.exe": True}), 100)
assert set(W.rec.painted) == {1}
assert W.rec.painted[1][1] == 0.3
ok("the skip list is law (fg, cloaked, iconic, own, excluded, zero, "
   "audible) and the veil's alpha IS the level")

# foreground change un-veils on the tick it is seen (the ~0.2 s law)
W = World([w(1), w(2)])
W.tick(cfg(level=30), 100)
assert set(W.rec.painted) == {1, 2}
W.wins = [w(1, fg=True), w(2)]
W.tick(cfg(level=30), 101)
assert 1 not in W.rec.painted and 1 in W.rec.gone
ok("the foreground change un-veils on the tick it is seen")

# the settle boundary, walked from both sides
W = World([w(9, pid=99)], audio=[99])
W.tick(cfg(level=30), 100)
assert 9 not in W.rec.painted
W.audio = set()
W.tick(cfg(level=30), 103.999)
assert 9 not in W.rec.painted
W.tick(cfg(level=30), 104.0)
assert 9 in W.rec.painted
ok("a silent app stays exempt until the 4.0 s settle, to the tick")

# and back to audible is instant, not another settle away
W.rec.gone.clear()
W.audio = {99}
W.tick(cfg(level=30), 104.5)
assert 9 not in W.rec.painted and 9 in W.rec.gone
ok("a window that starts making sound un-dims the tick we learn it")

# the ramp: hold, two more steps, bare by ramp_sec - never a blink
W = World([w(1), w(2)])
W.tick(cfg(level=30), 100)
W.idle = 0.0
W.tick(cfg(level=30), 100)
assert set(W.rec.painted) == {1, 2} and W.rec.painted[1][1] == 0.3
W.tick(cfg(level=30), 103)
assert W.rec.painted[1][1] == 0.2     # step one of three, at 30%%
W.tick(cfg(level=30), 106)
assert W.rec.painted[1][1] == 0.1     # step two, bare by ramp_sec
W.tick(cfg(level=30), 108)
assert W.rec.painted == {} and 1 in W.rec.gone and 2 in W.rec.gone
ok("the fade holds, steps twice more, and the desk is bare at ramp")

# a moved window drags its veil; a second stillness re-lights mid-fade
W = World([w(1)])
W.tick(cfg(level=30), 100)
W.wins = [w(1, rect=(50, 60, 640, 480))]
W.tick(cfg(level=30), 101)
assert W.rec.painted[1][0] == (50, 60, 640, 480)
ok("a moved window drags its veil along")
W.idle = 0.0
W.tick(cfg(level=30), 102)
W.idle = 999.0
W.tick(cfg(level=30), 103)
assert W.rec.painted[1][1] == 0.3
ok("a second stillness re-lights the fade mid-step")


# --- Oct-15 UAT bug 1: Progman and WorkerW pass the census, so the
# --- desktop itself gets veiled. The filter lives in the CENSUS
# --- stratum (a fact about the desk, not a config rule): a fake
# --- census carrying a Progman row and an ordinary app row must
# --- emit only the app row - the desktop can never reach paint.
_raw_desk = [w(1, cls="Progman", rect=(0, 0, 2560, 1440)),
             w(2, cls="WorkerW", rect=(0, 0, 2560, 1440)),
             w(3, cls="Chrome_WidgetWin_1")]
W = World(dimmer._veil_rows(_raw_desk))    # the REAL filter, named
W.tick(cfg(level=30), 100)
assert set(W.rec.painted) == {3}, "a desktop view reached paint"
ok("Progman and WorkerW never reach paint: the wallpaper is not a "
   "window you are not using")
assert dimmer.DESKTOP_VIEWS == {"Progman", "WorkerW"}
SRC_LINES = SRC.splitlines()
_i = SRC_LINES.index("def _census():")
assert any("_veil_rows" in l for l in SRC_LINES[_i:_i + 30]), \
    "the census returns its rows unfiltered - the set is dead weight"
assert "GetClassNameW.restype" in SRC and \
    "GetClassNameW.argtypes" in SRC   # the pin discipline, at the
    #                                   import block like every other
    #                                   verb (the GetCursorPos class)
ok("the filter is in the census stratum, not the FSM, and the class "
   "lookup is pinned")
_cold = dimmer._census()
assert all(f["cls"] not in dimmer.DESKTOP_VIEWS or f["fg"]
           for f in _cold), _cold
ok("the live census on this desk answers no un-fg'd Progman/WorkerW "
   "row (an fg desktop view rides the filter, the FSM's fg skip "
   "still refuses it paint)")


# --- the foreground fix (gate finding 2): a focus that is a CHILD
# --- (UWP CoreWindow, dropdown, devtools popup) must mark its TOP-
# --- LEVEL. This desk answers a REAL child to lean on: SHELLDLL_-
# --- DefView, the desktop's own view window, whose GA_ROOT is the
# --- Progman/WorkerW row. Fake the foreground as that child and the
# --- real census must flag the ROOT row (and only it): the old raw
# --- compare flagged nothing (the child is no row at all), which is
# --- how a foreground UWP app stayed qualified and the desktop focus
# --- dimmed the always rows blind. Through the REAL _census, and the
# --- flagged row drops the same tick in the WORLD drive below:
# --- desktop view with the fg flag rides _veil_rows (attribution!)
# --- but the FSM's fg skip refuses it a veil (wallpaper law intact).
_Progman = ctypes.windll.user32.FindWindowW("Progman", None)
assert _Progman, "this desk answers no Progman"
_DefView = ctypes.windll.user32.FindWindowExW(_Progman, 0, None, None)
assert _DefView, "this Progman answers no child to lean on"
_root = ctypes.windll.user32.GetAncestor(_DefView, dimmer.GA_ROOT)
_real_fg = dimmer._u32.GetForegroundWindow
dimmer._u32.GetForegroundWindow = lambda: _DefView
try:
    _fixed = dimmer._census()                    # the REAL door
finally:
    dimmer._u32.GetForegroundWindow = _real_fg
_fgged = [f for f in _fixed if f["fg"]]
assert len(_fgged) == 1 and _fgged[0]["hwnd"] == _root \
    and _fgged[0]["cls"] in dimmer.DESKTOP_VIEWS, \
    "the child focus did not resolve to the top-level that owns it: " \
    "%r vs %r" % (_fgged, _root)
assert all(not f["fg"] for f in _fixed
           if f["cls"] in dimmer.DESKTOP_VIEWS and f["hwnd"] != _root), \
    "the sibling desktop view rode the filter un-flagged"
W = World(_fixed)                                # every live desk row
W.tick(cfg(level=30, monitors={f["monitor"]: True
                               for f in _fixed if f["monitor"]}), 100)
assert _root not in W.rec.painted, \
    "the fg'd desktop view reached paint (wallpaper law broken)"
ok("a focus on a child marks its TOP-LEVEL through the real census "
   "(GA_ROOT at the door); the desktop row carries attribution yet "
   "never reaches paint - the same-tick drop rides the fg flag")

# --- Oct-15 UAT bug 2a: a paint for a destroyed hwnd raises inside
# --- Tk; the item must die alone, not take the pump - and its veil
# --- must leave the dict. Driven with a fake tkinter through the
# --- REAL painter thread. The z-pin (gate finding 1) rides the same
# --- drive: every birth goes through _zpin with a fake hwnd the real
# --- IsWindow refuses (dead anchor: skip, never raise) - the drive
# --- proves the pin costs the pump nothing on anchors it cannot read.
import time as _time_mod
import types as _types


class _Cap(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, rec):
        self.lines.append(rec.getMessage())


_cap = _Cap()
_dlg = logging.getLogger("dimmer")
_dlg.setLevel(logging.DEBUG)          # else the INFO confessions die
_dlg.addHandler(_cap)                 # at the default WARNING gate


class _DeadWin:
    # a veil whose real app died: geometry lands, alpha raises
    def __init__(self):
        self._pb_rect = None
        self.calls = []

    def geometry(self, s):
        self.calls.append("geom")
        raise RuntimeError("invalid command name \"dead.win\"")

    def deiconify(self):
        pass

    def update_idletasks(self):
        pass

    def winfo_id(self):
        return 0x4242

    def destroy(self):
        self.calls.append("destroy")

    def withdraw(self):
        self.calls.append("withdraw")

    def attributes(self, *a):
        pass

    def overrideredirect(self, *a):
        pass

    def configure(self, *a, **k):
        pass

    def protocol(self, *a):
        pass


class _LiveWin(_DeadWin):
    def geometry(self, s):
        self.calls.append("geom")


JOBS = []


class _Root:
    def withdraw(self):
        pass

    def after(self, ms, f=None):
        JOBS.append(f)              # the test fires the pump itself

    def mainloop(self):
        pass                        # the fake loop returns; the pump


#                                   # is driven by hand below
_dead, _live = _DeadWin(), _LiveWin()
_wl = iter([_live, _live, _live, _dead])   # births: veil1, veil2,
#                                          # veil3, veil9-dead - the
#                                          # ledger is gone, so EVERY
#                                          # qualified birth takes a
#                                          # widget (the 0x4242 fake
#                                          # winfo_id + real IsWindow
#                                          # refuse every z-pin: the
#                                          # dead-anchor path rides)
_tk = _types.SimpleNamespace(Toplevel=lambda *a, **k: _wl.__next__(),
                             Tk=lambda: _Root())
_saved_modules = dict(sys.modules)
from panelboss import hider as _hider
_saved_hider_wait = _hider.wait_for_window
_saved_click = dimmer._clickthrough
_saved_q = dimmer._q
_hider.wait_for_window = lambda *a: None
dimmer._clickthrough = lambda win: None
sys.modules["tkinter"] = _tk
try:
    dimmer._q = None
    dimmer._paint(1, (10, 10, 800, 600), 0.3)       # live veil
    dimmer._paint(2, (20, 20, 400, 300), 0.3)       # contained too:
    #                                               # it BIRTS now,
    #                                               # z-pinned below
    #                                               # its own target
    dimmer._paint(3, (1200, 10, 900, 700), 0.3)     # disjoint birth
    dimmer._paint(9, (5, 5, 2000, 1000), 0.3)       # the DEAD hwnd
    dimmer._paint(3, (0, 0, 700, 500), 0.3)         # grows: re-pins
    _deadline = _time_mod.time() + 10.0
    while not JOBS:
        assert _time_mod.time() < _deadline, "the fake painter died"
        _time_mod.sleep(0.02)
    JOBS.pop(0)()                    # one pump: drain everything
    assert dimmer._q.empty(), "the pump stopped draining on a raise"
finally:
    sys.modules.clear()
    sys.modules.update(_saved_modules)
    _hider.wait_for_window = _saved_hider_wait
    dimmer._clickthrough = _saved_click
    dimmer._q = _saved_q
assert "destroy" in _dead.calls, \
    "the dead veil was not dropped from the dict and destroyed"
assert _live._pb_rect == (0, 0, 700, 500)    # the grown veil, alive
assert any("one veil item failed" in l for l in _cap.lines), \
    "the dead-veil drop was silent"
_dlg.removeHandler(_cap)
ok("one dead hwnd kills ONE veil (dropped from the dict, destroyed, "
   "LOGGED) and the pump survives to drain the rest")

# --- the z-pin (gate finding 1's fix), through fakes. Pin 1: a DEAD
# --- anchor is a silent skip - no band write, no position call, no
# --- raise. Pin 2: a live anchor pins OUR root (never the owner's
# --- handle - that would yank the user's window forward) under the
# --- target's next-up neighbour, with the full flag word 0x213 =
# --- NOSIZE|NOMOVE|NOACTIVATE|NOOWNERZORDER, band-matched: an
# --- ordinary anchor gets an ordinary veil, a topmost one a topmost
# --- veil, and an anchor at the band's head (GetWindow answers none)
# --- pins at HWND_TOP (None).
class _ZWin:
    def __init__(self):
        self.attrs = []

    def update_idletasks(self):
        pass

    def winfo_id(self):
        return 0x4242

    def attributes(self, *a):
        self.attrs.append(a)


_iw, _gw, _swp = dimmer._iswindow, dimmer._getwindow, dimmer._setwindowpos
_gwlw = dimmer._u32.GetWindowLongW
try:
    dimmer._iswindow = lambda h: 0
    _z = _ZWin()
    dimmer._zpin(_z, 0x1234)
    assert _z.attrs == [], "a dead anchor still got a band write"

    def _live_iw(h):
        return 1

    def _above(h, g):
        return 0x1337 if g == dimmer.GW_HWNDNEXT else None

    _pins = []

    def _swp_rec(h, a, x, y, cx, cy, f):
        _pins.append((h, a, f))
        return 1

    dimmer._iswindow = _live_iw
    dimmer._getwindow = _above
    dimmer._setwindowpos = _swp_rec
    _z = _ZWin()
    dimmer._zpin(_z, 0x1234)                    # ordinary anchor
    assert _z.attrs == [("-topmost", False)], _z.attrs
    assert _pins == [(0x4242, 0x1337, 0x213)], _pins
    _z = _ZWin()
    dimmer._getwindow = lambda h, g: None       # anchor at the top
    dimmer._zpin(_z, 0x1234)
    assert _pins[-1] == (0x4242, None, 0x213), _pins[-1]

    def _topmost_ex(h, i):                      # topmost owner
        return 0x8 if i == dimmer.GWL_EXSTYLE else 0

    dimmer._u32.GetWindowLongW = _topmost_ex
    dimmer._getwindow = _above
    _z = _ZWin()
    dimmer._zpin(_z, 0x1234)
    assert _z.attrs == [("-topmost", True)], _z.attrs   # band matched
    assert _pins[-1] == (0x4242, 0x1337, 0x213), _pins[-1]
finally:
    dimmer._iswindow = _iw
    dimmer._getwindow = _gw
    dimmer._setwindowpos = _swp
    dimmer._u32.GetWindowLongW = _gwlw
ok("the z-pin: a dead anchor skips silent; a live one pins OUR root "
   "under the next-up neighbour with flags 0x213, band-matched both "
   "ways, HWND_TOP at the band's head")


# --- RULING 3 (Oct-15): the per-monitor always sub-mode. An opted
# --- row that also says always dims WITHOUT the idle clock - but the
# --- foreground window's panel is exempt (the owner: "if the focused
# --- app or mouse isn't on that monitor"), the audible exemption
# --- rides, and the pause clears everything. dimming is a SET.
_AOC = {"AOC2790": True, "IOC912B": True}
_c = cfg(level=30, monitors=_AOC, always={"IOC912B": True})
W = World([w(9, fg=True, monitor="AOC2790"),      # focus on AOC
           w(1, monitor="AOC2790"),
           w(2, monitor="IOC912B")], idle=0.0)    # desk NOT idle
W.tick(_c, 100)
assert set(W.rec.painted) == {2}, \
    "always did not dim the un-focused panel while the desk is busy"
# the focus moves onto the always panel: that panel bows to the edge -
# its field FADES out soft (the pause law's shape), it does not blink
W.wins = [w(9, fg=True, monitor="IOC912B"), w(1, monitor="AOC2790"),
          w(2, monitor="IOC912B")]
W.tick(_c, 101)
assert W.rec.painted[2][1] == 0.3       # the edge holds, no blink
W.tick(_c, 109)                          # a whole ramp later: bare
assert W.rec.painted == {} and 2 in W.rec.gone
ok("an always panel dims without the idle wait and fades the tick "
   "the focus lands on it")
# a focus that answers NO panel (off every rect, or none): the always
# rows dim blind, confessed ONCE per transition - not per tick
_dlg.addHandler(_cap)
W.wins = [w(9, fg=True, monitor=None), w(1, monitor="AOC2790"),
          w(2, monitor="IOC912B")]
W.tick(_c, 110)
assert W.rec.painted[2][1] == 0.3       # re-lit: the blind word says why
before = len(_cap.lines)
W.tick(_c, 111)
W.tick(_c, 112)
assert len(_cap.lines) == before, "the blind-focus word repeats per tick"
assert any("no panel" in l for l in _cap.lines)
_dlg.removeHandler(_cap)
ok("an unattributable focus dims the always rows, and the blind word "
   "rides the transition")
# audible exemption rides the always path; the settle walks past it
# like anywhere else; the pause outranks the row and clears the field
W = World([w(2, monitor="IOC912B", pid=77)], audio=[77], idle=0.0)
W.tick(_c, 100)
assert 2 not in W.rec.painted
W.audio = set()
W.tick(_c, 104.01)                       # the settle is a settle here too
assert set(W.rec.painted) == {2}
ok("a window the sensor hears keeps its brightness on an always panel")
dimmer.set_paused(True)
W.tick(_c, 105)                          # the pause edge holds, soft
assert W.rec.painted[2][1] == 0.3
W.tick(_c, 113)                          # the whole ramp: bare
assert W.rec.painted == {} and 2 in W.rec.gone
dimmer.set_paused(False)
W.tick(_c, 114)
assert set(W.rec.painted) == {2}
ok("the pause outranks the always row and the field returns with it")
# an always that never opted in dims nothing (sub-mode, not a bypass)
W = World([w(2, monitor="IOC912B")], idle=0.0)
W.tick(cfg(level=30, monitors={"IOC912B": False}, always={"IOC912B": True}), 100)
assert W.rec.painted == {}
ok("always is a SUB-MODE of the opt-in: an un-armed row never dims")
# a dimming always panel does NOT freeze a returning panel's veil:
# input back with BOTH panels always - the focus lands on IOC, so
# IOC fades down its own ramp while AOC never blinks
_c2 = cfg(level=30, monitors=_AOC, always={"AOC2790": True, "IOC912B": True})
W = World([w(1, monitor="AOC2790"), w(2, monitor="IOC912B")],
          idle=999.0)
W.tick(_c2, 100)                         # idle: both panels full
assert set(W.rec.painted) == {1, 2}
W.idle = 0.0
W.wins = [w(9, fg=True, monitor="IOC912B"), w(1, monitor="AOC2790"),
          w(2, monitor="IOC912B")]
W.tick(_c2, 101)                         # IOC owns the focus now
assert W.rec.painted[2][1] == 0.3       # still full at the edge...
W.tick(_c2, 104)                         # ...three seconds down the ramp
assert W.rec.painted[2][1] == 0.2       # step one of three, at 30%%
assert W.rec.painted[1][1] == 0.3       # AOC never blinked
W.tick(_c2, 110)
assert 2 in W.rec.gone and W.rec.painted[1][1] == 0.3
ok("the panel that stopped dimming fades on its own edge while an "
   "always panel keeps duty")

# --- RULING 4: ramp_sec reaches ZERO and the drop is immediate. The
# --- fade arithmetic guards the /ramp by name; the drop lands THIS
# --- tick. (The clamp rails are pinned in the normalize block above,
# --- the card's range in the UI pin below - floor 0, ceiling 60.)
W = World([w(1), w(2)])
W.tick(cfg(level=30, ramp_sec=0), 100)
assert set(W.rec.painted) == {1, 2}
W.idle = 0.0
W.tick(cfg(level=30, ramp_sec=0), 100)
assert W.rec.painted == {} and 1 in W.rec.gone and 2 in W.rec.gone
ok("ramp 0 is the instant drop - no division, no step, this tick")
# and a mid-fade re-stillness at ramp 0 re-lights like any other ramp
W = World([w(1)])
W.tick(cfg(level=30, ramp_sec=0), 100)
W.idle = 0.0
W.tick(cfg(level=30, ramp_sec=0), 101)
W.idle = 999.0
W.tick(cfg(level=30, ramp_sec=0), 102)
assert W.rec.painted[1][1] == 0.3
ok("stillness at ramp 0 re-lights the field like any other ramp")

# --- RULING 5: the level DEFAULT is 20 (OLED). The rails are pinned
# --- untouched in the normalize block; here the bare dict (no level
# --- key at all) must paint 0.2, and an explicit level still rules.
_nolvl = cfg(level=30)
del _nolvl["dimmer"]["level"]
W = World([w(1)])
W.tick(_nolvl, 100)
assert W.rec.painted[1][1] == 0.2
W.tick(cfg(level=30), 101)
assert W.rec.painted[1][1] == 0.3
ok("the bare-config veil sits at 20 percent; an explicit level rules")

# the card must SHOW both rulings: the ramp slider's floor is the
# shared constant (it reaches 0 with the rail), the level default
# rides the same constant - a card restating its own numbers is the
# lie these pins refuse
_UISRC = open("panelboss/ui/window/_oled.py", encoding="utf-8").read()
_UIR = _UISRC[_UISRC.index('row = self._row(box, "fade within"'):]
_UIR = _UIR[:_UIR.index('"veil level"')]
assert "from_=DIMMER_RAMP_FLOOR" in _UIR and \
    "DIMMER_LEVEL_DEFAULT" in _UISRC and \
    config.DIMMER_LEVEL_DEFAULT == 20 and config.DIMMER_RAMP_FLOOR == 0
assert '"always"' in _UISRC and "_oled_dim_always_changed" in _UISRC
ok("the card draws its rails from the constants and carries the "
   "always sub-mode per row")


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
                                 "always": {"AOC2790": True,
                                            "GONE": False,
                                            "IOC912B": "maybe"},
                                 "apps": {"chrome.exe": True,
                                          "JUNK": 7},
                                 "bound": ["ctrl", 5]})
    assert n["on"] is False and n["idle_sec"] == 3600 and \
        n["ramp_sec"] == 2 and n["level"] == 90 and \
        n["monitors"] == {"AOC2790": True, "GONE": True} and \
        n["always"] == {"AOC2790": True, "GONE": False} and \
        n["apps"] == {"chrome.exe": True} and n["bound"] is None
    # the Oct-15 ramp ruling: the FLOOR moved to zero (a stored 2 is
    # now legal verbatim - nothing clamps it up), an explicit 0
    # survives, and the CEILING still rules
    assert config.normalize_dimmer({"ramp_sec": 2})["ramp_sec"] == 2
    assert config.normalize_dimmer({"ramp_sec": 0})["ramp_sec"] == 0
    assert config.normalize_dimmer({"ramp_sec": 99})["ramp_sec"] == 60
    # and the level default dropped to 20 as a DEFAULT: an explicit
    # 45 is still a legal 45 (the rails 10..90 stand unmoved)
    assert config.normalize_dimmer({"level": 45})["level"] == 45
    # the UI's ACTUAL write shape round-trips (the gate's F1: the
    # old str-check folded the card's own pair to None at load):
    assert config.normalize_dimmer({"bound": [2, 123]})["bound"] == \
        [2, 123]
    assert config.normalize_dimmer({"bound": ["6", "117"]})["bound"] \
        == [6, 117]                     # the hand-edited belt
    assert config.normalize_dimmer({"bound": [2]})["bound"] is None
    words = "\n".join(rec.lines)
    for needle in ("dimmer on", "is not a bool; the row is dropped",
                   "dimmer bound", "kept for when it returns",
                   "dimmer always"):
        assert needle in words, needle
    for needle in ("idle", "ramp", "level"):      # the rails clamp
        assert needle not in words                # in silence, hider
    d = config.normalize_dimmer({})               # law
    assert d["on"] is False and d["monitors"] == {} and \
        d["always"] == {} and d["apps"] == {} and \
        d["idle_sec"] == 120 and d["ramp_sec"] == 8 and \
        d["level"] == 20 and d["bound"] is None
    ok("bad words warn and fold; the rails clamp; absent is dark; "
       "the always table normalizes under the monitors' own law")
finally:
    config._live_shorts = config._live_shorts_saved

# --- the pause switch is a SOFT stop: it fades like activity does and
# --- comes back the tick the pause lifts - no blink, no re-arming walk
W = World([w(1)])
W.tick(cfg(level=30), 100)                      # veil at full, unpaused
assert W.rec.painted[1][1] == 0.3
dimmer.set_paused(True)
assert dimmer.paused() is True
W.tick(cfg(level=30), 101)                      # paused: the fade clock starts
assert W.rec.painted[1][1] == 0.3      # hold, not blink
W.tick(cfg(level=30), 109)                      # the whole ramp: bare, not killed
assert W.rec.painted == {} and 1 in W.rec.gone
dimmer.set_paused(False)
W.tick(cfg(level=30), 110)
assert W.rec.painted[1][1] == 0.3      # back at full, the next tick
ok("the pause switch fades the field within ramp and lifts it back")

# --- one press pauses, one resumes (the toggle, not the hold)
dimmer.set_paused(False)
dimmer._veils = None
dimmer.hotkey_press()
dimmer.tick(cfg(level=30, on=False), 100)
assert dimmer.paused() is True
dimmer.hotkey_press()
dimmer.tick(cfg(level=30, on=False), 101)
assert dimmer.paused() is False
ok("a WM_HOTKEY press toggles: one pauses, one resumes")

# --- the hotkey arm, driven through fakes: the stored word registers
# --- ONCE against the live pump window; a taken combo keeps the old
# --- and leaves the dated word; headless answers a word and retries;
# --- the default (bound None) registers NOTHING. The Oct-15
# --- instrumentation rides the same drive: every attempt logs the
# --- truth line, and only errno 1409 may wear the word "taken".
# --- SINCE THE 1408 FIX the arm LEAVES NOTES, it does not knock: the
# --- fake stands in for display.request_hotkey and the asserts name
# --- the pump-thread law - mods/vk/MOD_NOREPEAT must reach the pump
# --- verbatim, and the restore of an old binding rides the SAME road.
_dlg.addHandler(_cap)
reg, unreg = [], []


class _Door:
    """The fake note door: records every (op, mods, vk) the arm
    leaves, refuses the pairs armed in REFUSE with their errno."""
    REFUSE = {}

    def __call__(self, op, mods=0, vk=0):
        (reg if op == "register" else unreg).append((op, mods, vk))
        err = self.REFUSE.get((mods, vk), 0)
        return (err == 0, err)


dimmer._pump_hwnd = lambda: 0x99
dimmer._request_hotkey = _Door()
dimmer._sync_hotkey([0x0002, 123])              # ctrl+F12 as stored
assert reg == [("register", 0x0002 | dimmer.MOD_NOREPEAT, 123)] and \
    dimmer.bound_live()
assert any("stored [0x2, 0x7b] registered as mods=0x4002 vk=0x7b "
           "on hwnd=0x99" in l for l in _cap.lines), _cap.lines
dimmer._sync_hotkey([0x0002, 123])              # unchanged: no re-knock
assert len(reg) == 1
ok("the stored word registers once against the live pump (the note "
   "carries mods|NOREPEAT and the vk VERBATIM), and the success says so in hex")


class _Taken(_Door):
    # 1409 on the one chord the desk holds; the restore-knock of the
    # old binding must find a clean 0 ON THE PUMP, same as the first.
    REFUSE = {(0x0001 | dimmer.MOD_NOREPEAT, 65): 1409}


dimmer._request_hotkey = _Taken()
dimmer._sync_hotkey([0x0001, 65])
note = dimmer.bind_note()
assert reg[-2] == ("register", 0x0001 | dimmer.MOD_NOREPEAT, 65)  # knocked
assert unreg == [("unregister", 0, 0)]                            # old released
assert reg[-1] == ("register", 0x0002 | dimmer.MOD_NOREPEAT, 123)  # restored
assert "taken" in note and note[:2].isdigit()          # and it is dated
assert dimmer.bound_live()                             # OLD one stands
assert any("errno=1409 (ERROR_HOTKEY_ALREADY_REGISTERED)" in l
           for l in _cap.lines)
ok("a taken combo answers with the dated word and keeps the old - "
   "the release AND the restore both ran on the pump door")


class _DifferentDoor(_Door):
    REFUSE = {(0x0004 | dimmer.MOD_NOREPEAT, 0x2d): 87}


dimmer._request_hotkey = _DifferentDoor()
dimmer._sync_hotkey([0x0004, 0x2d])                  # win+'-'
note = dimmer.bind_note()
assert "taken" not in note and "87" in note, note
assert any("mods=0x4004 vk=0x2d" in l and "hwnd=0x99" in l
           and "errno=87" in l for l in _cap.lines), _cap.lines
ok("a NON-collision refusal says its number, never 'taken' - the "
   "Oct-15 false-claim fix, and the truth line carries the hex")
dimmer._request_hotkey = _Door()
dimmer._sync_hotkey(None)                    # esc: clean unbind
assert len(unreg) == 3 and not dimmer.bound_live() and \
    dimmer.bind_note() == ""                 # esc, taken-release,
#                                              # different-door release
before = len(reg)
dimmer._pump_hwnd = lambda: None             # headless now
dimmer._sync_hotkey([0x0008, 80])
assert len(reg) == before and len(unreg) == 3 and \
    "pump" in dimmer.bind_note()
dimmer._pump_hwnd = lambda: 0x99             # the pump came back
dimmer._sync_hotkey([0x0008, 80])
assert reg[-1] == ("register", 0x0008 | dimmer.MOD_NOREPEAT, 80)
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
assert "raw state=" in cap               # the Oct-15 truth line: the
ok("FocusOut cancels a pending capture; every completion disarms "   # raw
   "and logs the raw Tk state it stored")                            # state


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


# --- 6b: THE WIRE. The pump branch and the id must agree, or a press
# --- is silent and total; a rename on either side used to be free.
# --- Pin the message id, the wParam belt, and the call-in together
# --- from the source the app actually runs (the fake-seam drive above
# --- has never touched the real branch - this does).
DISP = open("panelboss/display.py", encoding="utf-8").read()
assert "WM_HOTKEY = 0x0312" in DISP                  # the message id
assert dimmer.HOTKEY_ID == 0x5042                    # the app's slot
_branch = DISP[DISP.index("if msg.message == WM_HOTKEY:"):]
_branch = _branch[:_branch.index("elif msg.message")]
assert "msg.wParam == dimmer.HOTKEY_ID" in _branch and \
    "dimmer.hotkey_press()" in _branch, \
    "the pump's WM_HOTKEY branch no longer walks the id belt to the "\
    "press call-in"
assert "hotkey_window" in DISP                       # the registrar's
#                                                     # door (the hwnd
#                                                     # that owns the
#                                                     # registration)
_dlg.removeHandler(_cap)
ok("the WM_HOTKEY wire is pinned end to end: 0x0312, the 0x5042 "
   "belt, straight to hotkey_press")
print("\nDIMMER TESTS OK (%d)" % len(OK))
