"""The video eye's law, pinned: default-off at the root, the port's
brand decide, the content-space fold (DPR-scaled bounds, the chrome
correction, the viewport-space judgment), the liveness gates (paused,
min_rect_px, the grace), the freshest-of-two-sources precedence -
and the Veils frame: four pieces clamped per monitor, the straddle
covering BOTH panels with no sliver on the video column, plain veils
skipped on the covered panels only, the ramp retraction, the pause.
Every door is a fake seam (the _cdp transport, window_bounds,
monitors, the clock) - no browser, no Tk, app-up and headless alike,
the dimmer_test family's idiom."""
import json
import logging
import os
import sys

sys.path.insert(0, ".")
from panelboss import config, dimmer, videoeye          # noqa: E402

OK = []
NOWHERE = os.path.join(os.environ.get("TEMP", "."), "pb-no-bridge-file")
if os.path.exists(NOWHERE):
    os.remove(NOWHERE)
videoeye.BRIDGES = (NOWHERE,)            # one door, the test's own


def ok(name):
    OK.append(name)
    print("ok -", name)


# ---------------------------------------------------------------- fakes
class Clock:
    def __init__(self):
        self.mono = 1000.0
        self.wall = 9000.0

    def advance(self, s):
        self.mono += s
        self.wall += s

    def monotonic(self):
        return self.mono

    def time(self):
        return self.wall


class FakeSock:
    """The scripted page attach: talk answers from the script and
    COUNTS every call (the truth-call cache pin reads the count)."""

    def __init__(self, cdp):
        self.cdp = cdp
        self.closed = False

    def talk(self, method, params=None, timeout=4.0):
        if self.closed:
            raise videoeye._cdp.CdpError("talk on a closed socket")
        self.cdp.talks.append(method)
        if method == "Runtime.evaluate":
            return {"result": {"value": json.dumps(self.cdp.row)
                               if self.cdp.row is not None else "null"}}
        if method == "Browser.getWindowForTarget":
            return {"windowId": 7}
        if method == "Browser.getWindowBounds":
            # the CDP shape, MEASURED live today (Oct 15) off the
            # 9333 box: bounds{left,top,width,height} in DIP px
            l, t, w, h = self.cdp.bounds
            return {"windowId": 7, "bounds": {"left": l, "top": t,
                                             "width": w, "height": h}}
        raise videoeye._cdp.CdpError("unscripted " + method)

    def close(self):
        self.closed = True


class FakeCdp:
    CdpError = Exception

    def __init__(self, row=None, bounds=None, brand="Chrome/155",
                 port=9333, targets=None):
        self.port = port
        self.targets = targets if targets is not None else []
        self.row = row
        self.bounds = bounds
        self.brand = brand
        self.talks = []
        self.finds = 0

    def find_port(self, dirs, timeout=2.0):
        self.finds += 1
        return self.port

    def read_json(self, url, timeout=2.0):
        if url.endswith("/json/version"):
            return {"Browser": self.brand}
        return self.targets

    def Socket(self, url, timeout=4.0):
        return FakeSock(self)


def row(x=100, y=200, w=800, h=450, dpr=1, paused=False,
        scroll=(0, 0), view=(1584, 649)):
    return {"rect": {"left": x, "top": y, "width": w, "height": h},
            "dpr": dpr, "paused": paused, "scroll": list(scroll),
            "view": list(view)}


def target(url="https://www.youtube.com/watch?v=x"):
    return [{"type": "page", "url": url, "id": "T1",
             "webSocketDebuggerUrl": "ws://127.0.0.1:1/devtools/page/T1"}]


CLK = Clock()
videoeye.time = CLK
CDP = None


def live(r=None, bounds=(600, 200, 1600, 900), port=9333,
         targets=None, brand="Chrome/155", cfg=None, t=None):
    """One feature-on beat on a fresh state: install the script,
    tick once, hand back the config the pin reads after."""
    global CDP
    CDP = FakeCdp(row=r, bounds=bounds, brand=brand, port=port,
                  targets=targets if targets is not None else target())
    videoeye._cdp = CDP
    videoeye._STATE.clear()
    cfg = cfg or vcfg()
    videoeye.tick(cfg, CLK.monotonic() if t is None else t)
    return cfg


def vcfg(on=True, grace=3, mins=200000):
    return {"videodim": {"on": on, "sites": list(videoeye.SITES),
                         "min_rect_px": mins, "grace_s": grace}}


def bridge_file(rect, view=(1920, 1080), bounds=(0, 0, 1920, 1080),
                age=0.0, dpr=1, paused=False, family="chrome"):
    body = {"rect": {"left": rect[0], "top": rect[1],
                     "width": rect[2], "height": rect[3]},
            "dpr": dpr, "paused": paused, "scroll": [0, 0],
            "view": list(view),
            "bounds": {"left": bounds[0], "top": bounds[1],
                       "width": bounds[2], "height": bounds[3]},
            "family": family, "ts": CLK.wall - age}
    with open(videoeye.BRIDGES[0], "w", encoding="utf-8") as f:
        f.write(json.dumps(body) + "\n")
    stamp = CLK.wall - age
    os.utime(videoeye.BRIDGES[0], (stamp, stamp))
    return videoeye.BRIDGES[0]


# ---------------------------------------------------------------- pins
# 1. default-off is a ROOT: no sockets, no bridge read, no answer
live(r=row(), port=None, cfg=vcfg(on=False))
assert CDP.finds == 0 and videoeye.video_rect(vcfg(on=False)) is None
ok("feature off means NOTHING happens: zero port probes, zero file "
   "reads, no rect")

# 2. a dark port -> None, and the say names the failure
live(r=row(), port=None)
assert videoeye.video_rect(vcfg()) is None
f = videoeye._STATE["chrome"]
assert f.say == "no debug port answers" and f.miss == 1
ok("no port answering reads as no rect, confessed in the say")

# 3. brand decide: a Chrome port is NOT an opera_gx door
live(r=row(), brand="Chrome/155")
assert videoeye._STATE["opera_gx"].say.startswith("the port belongs")
assert videoeye._STATE["chrome"].port == 9333
ok("the /json/version brand word decides whose port it is - a chrome "
   "port cannot anchor an opera family")

# 4. page found + video playing -> the fold is EXACT: outer px from
#    the DPR-scaled CDP bounds, the viewport inset is outer minus
#    inner*dpr (chrome 251 down top, border 8 half-lateral), the
#    rect in viewport space
cfg = live(r=row(), bounds=(600, 200, 1600, 900))
r = videoeye.video_rect(cfg)
assert r == (708, 651, 800, 450), r     # vx=600+16/2+100, vy=200+251+200
ok("the fold is law: content rect at the viewport origin the "
   "outer-minus-inner correction paints, DPR-scaled")

# 5. dpr 2 doubles the world and the two rulers still agree
live(r=row(dpr=2, view=(792, 325)), bounds=(600, 200, 800, 450))
r = videoeye.video_rect(vcfg())
assert r == (1408, 1050, 1600, 900), r  # px outer (1200,400,1600,900):
#                                        # vx=1200+8+200, vy=400+250+400
ok("dpr is the ONE ruler: the scaled bounds and the scaled content "
   "rect agree in physical px")

# 6. the scroll pair rides the row and does NOT shift the rect:
#    getBoundingClientRect is viewport-space (the judgment this
#    delivery names - a scrolled page moves the video IN the page,
#    and the rect answers the move without the scroll term)
live(r=row(scroll=(0, 500)), bounds=(600, 200, 1600, 900))
assert videoeye.video_rect(vcfg()) == (708, 651, 800, 450)
ok("scroll rides the row for the future DRM lane and never shifts "
   "the veil (the viewport-space law, pinned not silent)")

# 7. paused is NOT live (the veil is for PLAYING video)
live(r=row(paused=True), bounds=(600, 200, 1600, 900))
assert videoeye.video_rect(vcfg()) is None
ok("a paused video is no rect: the feature dims playback, not posters")

# 8. min_rect_px rejects the ad-banner "video" - and it is a rail,
#    not a verdict: a lower rail admits the same row
live(r=row(w=320, h=180), bounds=(600, 200, 1600, 900))
assert videoeye.video_rect(vcfg()) is None          # 57600 < 200000
assert videoeye.video_rect(vcfg(mins=10000)) == (708, 651, 320, 180)
ok("min_rect_px is the ad-banner line of defense, and it is a rail, "
   "not a verdict")

# 9. the grace: the row lives for grace_s past the last good probe
#    and dies after (the browser vanished, the ramp retracts - the
#    dimmer-side ramp ride is pin 16)
cfg = live(r=row(), bounds=(600, 200, 1600, 900))
t0 = CLK.monotonic()
CLK.advance(2.0)
assert videoeye.video_rect(cfg, CLK.monotonic()) == (708, 651, 800, 450)
CLK.advance(1.5)
assert videoeye.video_rect(cfg, CLK.monotonic()) is None
ok("a vanished eye holds the rect for grace_s and lets it go after - "
   "to the tick")

# 10. the bridge click with ZERO sockets: the file row folds through
#     the same door (the manual trigger's whole promise)
live(r=None, port=None)
bridge_file((0, 0, 600, 400))
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.video_rect(vcfg()) == (0, 0, 600, 400)
ok("the bridge click folds through the SAME door: the row carries "
   "its own bounds, the eye scales once")

# 11. freshest of the two wins BOTH ways, and the tie goes to the
#     file (a click IS intent): newer-port, newer-file, tie
if os.path.exists(videoeye.BRIDGES[0]):
    os.remove(videoeye.BRIDGES[0])                 # pin 10's click rests
live(r=row(), bounds=(600, 200, 1600, 900))
bridge_file((0, 0, 600, 400), age=9.0)              # click was a while back
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.video_rect(vcfg()) == (708, 651, 800, 450)
os.utime(videoeye.BRIDGES[0], (CLK.wall, CLK.wall))     # fresh click
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.video_rect(vcfg()) == (0, 0, 600, 400)
os.utime(videoeye.BRIDGES[0], (CLK.wall - 0.0, CLK.wall - 0.0))  # exact tie
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.video_rect(vcfg()) == (0, 0, 600, 400)
ok("freshest wins both directions and ties go to the click")

# 12. the truth-call cache: Browser.getWindowBounds answers once per
#     BOUNDS_REFRESH window, the evaluate rides every probe
live(r=row(), bounds=(600, 200, 1600, 900))
n_b = CDP.talks.count("Browser.getWindowBounds")
CLK.advance(0.6)
videoeye.tick(vcfg(), CLK.monotonic())
assert CDP.talks.count("Browser.getWindowBounds") == n_b      # cached
assert CDP.talks.count("Runtime.evaluate") == 2               # not
ok("the bounds call caches (one per refresh window), the evaluate "
   "rides every beat")

# --- the Veils frame (the dimmer side; fake seam, fake desk) ------
MON = [{"short": "MONA", "x": 0, "y": 0, "w": 1000, "h": 800},
       {"short": "MONB", "x": 1000, "y": 0, "w": 1000, "h": 800}]


class Rec:
    def __init__(self):
        self.painted = {}
        self.gone = []

    def paint(self, hwnd, rect, alpha):
        self.painted[hwnd] = (rect, alpha)

    def unveil(self, hwnd):
        self.painted.pop(hwnd, None)
        self.gone.append(hwnd)


def w(hwnd, monitor="MONA", fg=False, rect=(10, 10, 800, 600)):
    return {"hwnd": hwnd, "pid": hwnd, "exe": "notepad.exe",
            "cls": "X", "monitor": monitor, "tool": False,
            "cloaked": False, "iconic": False, "fg": fg, "rect": rect}


RECT = [None]


class Frame:
    def __init__(self, wins=None, idle=0.0):
        self.wins = wins or []
        self.rec = Rec()
        self.idle = idle
        self.v = dimmer.Veils(lambda: self.wins, lambda: set(),
                              lambda: self.idle, self.rec.paint,
                              self.rec.unveil,
                              video=lambda cfg, now: RECT[0],
                              monitors=lambda: MON)

    def tick(self, now, level=30, dim_on=True):
        self.v.tick({"dimmer": {"on": dim_on,
                                "monitors": {"MONA": True,
                                             "MONB": True},
                                "always": {}, "apps": {},
                                "idle_sec": 120, "ramp_sec": 8,
                                "level": level, "bound": None},
                     "videodim": {"on": True, "sites": [],
                                  "min_rect_px": 1, "grace_s": 3}},
                    now)


# 13. one monitor, a rect fully inside: EXACTLY four pieces, exact
#     geometry, alpha = the shared [dimmer] level, keys negative
f = Frame([w(1)])
RECT[0] = (100, 100, 600, 300)
f.tick(100)
assert {v[0] for v in f.rec.painted.values()} == {
    (0, 0, 1000, 100), (0, 400, 1000, 400), (0, 100, 100, 300),
    (700, 100, 300, 300)}, f.rec.painted
assert all(v[1] == 0.3 for v in f.rec.painted.values())
assert all(h < 0 for h in f.rec.painted)      # synthetic negative keys
ok("the frame is exactly four dark rectangles - top/bottom/left/"
   "right, the hole is the rect")

# 14. the straddle: pieces PER MONITOR, each clamped; the video
#     column across the seam stays bright (no sliver on video px -
#     the geometry judgment this delivery names)
f = Frame([w(1)])
RECT[0] = (900, 200, 200, 400)                # crosses MONA|MONB at 1000
f.tick(100)
assert {v[0] for v in f.rec.painted.values()} == {
    (0, 0, 1000, 200), (0, 600, 1000, 200), (0, 200, 900, 400),
    (1000, 0, 1000, 200), (1000, 600, 1000, 200),
    (1100, 200, 900, 400)}, f.rec.painted
ok("the straddle cuts one piece set per panel, each clamped - the "
   "seam column never darkens under the video")

# 15. the covered panels take NO plain veils (they would stack under
#     the frame); an uncovered panel dims by the old rules; idle so
#     the plain mode is live everywhere else
f = Frame([w(1, monitor="MONA"), w(3, monitor="MONB")], idle=999.0)
RECT[0] = (0, 0, 1000, 700)                   # MONA: one bottom piece
f.tick(100)
assert 1 not in f.rec.painted and 3 in f.rec.painted   # plain rules live
neg = [h for h in f.rec.painted if h < 0]
assert len(neg) == 1 and f.rec.painted[neg[0]][0] == (0, 700, 1000, 100)
ok("videodim live skips the plain veils on the covered panel only - "   # the hole
   "the other panels keep the old law")

# 16. a gone rect is a stopped video: the frame rides the RAMP (the
#     fade's first step is the one-tick hold), never a blink
f = Frame([w(1)])
RECT[0] = (100, 100, 600, 300)
f.tick(100)
assert len(f.rec.painted) == 4
RECT[0] = None
f.tick(101)
assert all(v[1] == 0.3 for v in f.rec.painted.values())  # the hold
f.tick(104)
assert all(v[1] == 0.2 for v in f.rec.painted.values())  # step one
f.tick(109)
assert f.rec.painted == {} and len(f.rec.gone) == 4
ok("the veil unfurls down the ramp (hold, steps, bare) - the ramp "
   "path ran")

# 17. the plain mode is UNTOUCHED by the new code paths: no rect,
#     no frames, the old field paints as the 42 pins promise
f = Frame([w(1), w(2, monitor="MONB")], idle=999.0)
RECT[0] = None
f.tick(100)
assert set(f.rec.painted) == {1, 2}
ok("no live rect means no negative keys: the plain dimmer behaves "
   "exactly as before")

# 18. the pause outranks the frame too (the whole-field law), and
#     the frame returns the tick the pause lifts
dimmer.set_paused(True)
f = Frame([w(1)])
RECT[0] = (100, 100, 600, 300)
f.tick(100)
assert f.rec.painted == {}
dimmer.set_paused(False)
f.tick(101)
assert len(f.rec.painted) == 4
ok("the pause clears the frame and the field returns the tick it lifts")

# --- config: the rails at the boundary --------------------------------
rec_lines = []


class _Cap(logging.Handler):
    def emit(self, record):
        rec_lines.append(record.getMessage())


_cap = _Cap()
logging.getLogger("config").addHandler(_cap)
n = config.normalize_videodim({"on": "yes", "sites": ["ok.com", 7],
                               "min_rect_px": 9e9, "grace_s": -2})
assert n["on"] is False and n["sites"] == ["ok.com"] \
    and n["min_rect_px"] == 4_000_000 and n["grace_s"] == 0
d = config.normalize_videodim({})
assert d["on"] is False and len(d["sites"]) == 6 \
    and d["min_rect_px"] == 200000 and d["grace_s"] == 3
assert any("is not a bool" in l for l in rec_lines)
assert any("only strings" in l for l in rec_lines)
logging.getLogger("config").removeHandler(_cap)
ok("normalize_videodim: bad on warns and folds, the rails clamp, the "
   "junk sites warn, absent is dark")

# --- the wire: the extension ships the SAME string and the manifest
#     carries its stated word ------------------------------------------
BG = open(os.path.join("extension", "background.js"),
          encoding="utf-8").read()
assert 'const RECT_JS = "%s";' % videoeye.RECT_JS in BG
MAN = json.load(open(os.path.join("extension", "manifest.json"),
                     encoding="utf-8"))
assert MAN["manifest_version"] == 3
assert set(MAN["permissions"]) == {"debugger", "nativeMessaging",
                                   "tabs", "downloads"}
assert MAN["host_permissions"] == ["<all_urls>"]
ok("the extension carries the eye's OWN string verbatim, and the "
   "manifest says what the code uses (downloads for the v1 writer)")

if os.path.exists(videoeye.BRIDGES[0]):
    os.remove(videoeye.BRIDGES[0])
print("\nVIDEOEYE TESTS OK (%d)" % len(OK))
