"""The faux taskbar strip's law, pinned. Pure-FSM discipline: the
Win32 stratum is never summoned - eyes, cursor, caret, paint, unpaint
and the clock all arrive as fakes, so every behavior below runs the
same code the state loop calls on the owner's desk."""
import logging
import sys

sys.path.insert(0, ".")
from panelboss import config, hider  # noqa: E402
from panelboss.hider import Strips  # noqa: E402

OK = []


def ok(name):
    OK.append(name)
    print("ok -", name)


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


def bars(*pairs):
    return lambda: [list(p) for p in pairs]


B1 = ["AOC2790", (0, 2128, 3840, 32)]
B2 = ["IOC912B", (3840, 2128, 2560, 32)]


def cfg(on=True, hold=3, reveal="hovered", rows=None):
    return {"hider": {"on": on, "hold_sec": hold, "reveal": reveal,
                      "monitors": rows if rows is not None else
                      {"AOC2790": True, "IOC912B": True}}}


class Desk:
    """One Strips with counting paint/unpaint and a hand-driven cursor,
    caret and clock."""

    def __init__(self, eye=bars(B1, B2), cursor=(100, 100), caret=False):
        self.painted, self.bared, self.now = [], [], 100.0
        self.cursor, self.caret = cursor, caret
        self.s = Strips(eye, self.paint, self.unpaint, self.cursor_,
                        self.clock, lambda: self.caret)

    def paint(self, short, rect):
        self.painted.append(short)

    def unpaint(self, short, rect):
        self.bared.append(short)

    def cursor_(self):
        return self.cursor

    def clock(self):
        return self.now

    def move(self, xy):
        self.cursor = xy

    def to(self, dt):
        self.now += dt


# 1 the law of the quiet desk: master-off paints nothing, ever
d = Desk()
d.s.tick(cfg(on=False))
assert d.painted == [] and d.bared == []
d.s.tick({"hider": {}})
assert d.painted == []
ok("default-off law: an unarmed hider never touches a bar")

# 2 opt-in arms coverage; an off row never owns a strip
d = Desk()
d.s.tick(cfg(rows={"AOC2790": True, "IOC912B": False}))
assert d.painted == ["AOC2790"] and d.bared == []
ok("armed rows cover, opted-out rows stay as Windows left them")

# 3 the hover withdraw: cursor into the zone bares exactly that bar
d.move((10, 2130))
d.painted.clear(), d.bared.clear()
d.s.tick(cfg())
assert d.bared == ["AOC2790"]
d.painted.clear(), d.bared.clear()
d.s.tick(cfg())
assert d.bared == [] and d.painted == ["IOC912B"]   # repaint, no re-bare
ok("hovered bar bares once; the other merely keeps its strip refreshed")

# 4 the return timer, exact on the rails
d.move((100, 100))
d.painted.clear(), d.bared.clear()
d.to(2.0)
d.s.tick(cfg())                                     # out_since starts HERE
assert "AOC2790" not in d.painted
d.painted.clear()
d.to(1.0)
d.s.tick(cfg())                                     # 1.0 < 3: not yet
assert "AOC2790" not in d.painted
d.painted.clear()
d.to(2.0)
d.s.tick(cfg())                                     # 3.0 on the nose
assert "AOC2790" in d.painted
ok("hold_sec is honored exactly - early tick no, at the rail yes")

# 5 the caret holds every return, and the clock restarts when it dies
d = Desk(caret=True)
d.s.tick(cfg())
d.move((10, 2130))
d.s.tick(cfg())
assert d.bared == ["AOC2790"]
d.move((100, 100))
d.to(99.0)
d.painted.clear(), d.bared.clear()
d.s.tick(cfg())                                    # caret lives: no return
assert d.painted == ["IOC912B"]                    # only the untouched
d.caret = False                                    # repaint may happen
d.s.tick(cfg())                                    # fresh timer starts
d.to(2.9)
d.painted.clear()                                  # clear AFTER the tick
d.s.tick(cfg())                                    # 2.9: held; the bare
assert d.painted == ["IOC912B"]                    # twin may repaint
d.to(0.2)                                          # a forgiven one
d.s.tick(cfg())
assert "AOC2790" in d.painted                       # 3.1: the strip comes
ok("a live caret anywhere in any bar holds the return; gone, "            # home
   "the seconds start again from zero")

# 6 reveal scopes: 'all' bares every armed bar on one hover
d = Desk()
d.s.tick(cfg())
d.move((3900, 2130))
d.painted.clear(), d.bared.clear()
d.s.tick(cfg(reveal="all"))
assert sorted(d.bared) == ["AOC2790", "IOC912B"]
ok("reveal 'all': one bar hovered, every bar bared")

# 7 a word the app has never heard never selects a leg (belt)
d = Desk()
d.s.tick(cfg())
d.move((10, 2130))
d.s.tick(cfg(reveal="everybar"))                    # unknown -> hovered
assert d.bared == ["AOC2790"]
ok("unknown reveal word behaves hovered - the word-seam belt")

# 8 opting out mid-spell retires the strip
rec = Recorder().install("hider")
d = Desk()
d.s.tick(cfg())
d.s.tick(cfg(rows={"AOC2790": False, "IOC912B": False}))
assert d.bared == ["AOC2790", "IOC912B"]
d.s.tick(cfg(rows={"AOC2790": True, "IOC912B": True}))
assert d.painted.count("AOC2790") == 2      # one re-arm each, exact
assert d.painted.count("IOC912B") == 2
ok("an opted-out row's strip retires; opting back in re-arms")

# 9 teardown clears every strip and every grudge
d = Desk()
d.s.tick(cfg())
d.s.teardown()
assert d.bared == ["AOC2790", "IOC912B"]
d.s.tick(cfg())
assert d.painted.count("AOC2790") == 2      # re-armed from the teardown
assert d.painted.count("IOC912B") == 2
ok("teardown bares all; the next tick re-arms cleanly")

# 10 normalize_hider's honesty laws
rec2 = Recorder().install("config")
config._live_shorts_saved = config._live_shorts
config._live_shorts = lambda: ["AOC2790"]
try:
    h = config.normalize_hider({"on": "yes", "hold_sec": "x",
                                "reveal": "everywhere",
                                "monitors": {"AOC2790": True,
                                             "GONE": True,
                                             "IOC912B": "maybe"}})
    assert h["on"] is False and h["hold_sec"] == 3 and \
        h["reveal"] == "hovered" and h["monitors"] == {"AOC2790": True,
                                                       "GONE": True}
    words = "\n".join(rec2.lines)
    for needle in ("hider on", "hider reveal", "not a bool",
                   "names no panel"):
        assert needle in words, needle
    h = config.normalize_hider({})
    assert h == {"on": False, "hold_sec": 3, "reveal": "hovered",
                 "monitors": {}}
    h = config.normalize_hider({"hold_sec": 999})
    assert h["hold_sec"] == config.HOLD_SEC_CEIL
    ok("bad words warn and fold; the rails clamp; absent is dark")
finally:
    config._live_shorts = config._live_shorts_saved

# 11 the conflict line is a fixed sentence, not an improvisation
assert hider.CONFLICT in ("Windows auto-hide is also on - this strip "
                          "may double-hide")
ok("the double-hide confession says the one honest sentence")

print("\nHIDER TESTS OK (%d)" % len(OK))
