"""The video eye's law, pinned: default-off at the root, the doorway
read (the native host's fixed %APPDATA%\\PanelBoss\\rect), the
content-space fold (DPR-scaled bounds, the chrome correction, the
viewport-space judgment), the liveness gates (paused, min_rect_px, the
grace), freshest-wins across families - and the Veils frame: four pieces
clamped per monitor, the straddle covering BOTH panels with no sliver on
the video column, plain veils skipped on the covered panels only, the
ramp retraction, the pause. Every door is a fake seam (the doorway path,
monitors, the clock) - no browser, no Tk, app-up and headless alike,
the dimmer_test family's idiom.
"""
import json
import os
import sys

sys.path.insert(0, ".")
from panelboss import config, dimmer, videoeye          # noqa: E402

OK = []
_TMP = os.path.join(os.environ.get("TEMP", "."), "pb-videoeye-test-door")
os.makedirs(_TMP, exist_ok=True)
_DOOR = os.path.join(_TMP, "rect")
if os.path.exists(_DOOR):
    os.remove(_DOOR)
videoeye.RECT_PATH = _DOOR          # one door, the test's own - the
# real %APPDATA%\\PanelBoss\\rect never touches the suite, and the
# desk's live click cannot decide whether the suite passes.


def ok(name):
    OK.append(name)
    print("ok -", name)


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


CLK = Clock()
videoeye.time = CLK


def row(x=100, y=200, w=800, h=450, dpr=1, paused=False,
        scroll=(0, 0), view=(1584, 649), bounds=(600, 200, 1600, 900),
        family="chrome", age=0.0):
    return {"rect": {"left": x, "top": y, "width": w, "height": h},
            "dpr": dpr, "paused": paused, "scroll": list(scroll),
            "view": list(view),
            "bounds": {"left": bounds[0], "top": bounds[1],
                       "width": bounds[2], "height": bounds[3]},
            "family": family, "ts": CLK.wall - age}


def door(rect, view=(1920, 1080), bounds=(0, 0, 1920, 1080), age=0.0,
         dpr=1, paused=False, family="chrome"):
    body = {"rect": {"left": rect[0], "top": rect[1],
                     "width": rect[2], "height": rect[3]},
            "dpr": dpr, "paused": paused, "scroll": [0, 0],
            "view": list(view),
            "bounds": {"left": bounds[0], "top": bounds[1],
                       "width": bounds[2], "height": bounds[3]},
            "family": family, "ts": CLK.wall - age}
    with open(videoeye.RECT_PATH, "w", encoding="utf-8") as f:
        f.write(json.dumps(body) + "\n")
    stamp = CLK.wall - age
    os.utime(videoeye.RECT_PATH, (stamp, stamp))


def vcfg(on=True, grace=3, mins=200000):
    return {"videodim": {"on": on, "min_rect_px": mins, "grace_s": grace}}


# ---------------------------------------------------------------- pins
# 1. default-off is a ROOT: no file read, no answer
videoeye._STATE.clear()
cfg = vcfg(on=False)
videoeye.tick(cfg, CLK.monotonic())
assert videoeye._STATE == {}
assert videoeye.video_rect(vcfg(on=False)) is None
ok("feature off means NOTHING happens: no file read, no state, no rect")

# 2. no doorway file -> None (fail-open)
videoeye._STATE.clear()
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.video_rect(vcfg()) is None
ok("no doorway file reads as no rect, confessed nowhere loud")

# 3. the doorway click folds through the door: own bounds, dpr scale,
#    the outer-minus-inner chrome correction
videoeye._STATE.clear()
door((100, 200, 800, 450), bounds=(600, 200, 1600, 900),
     view=(1584, 649))
videoeye.tick(vcfg(), CLK.monotonic())
r = videoeye.video_rect(vcfg())
assert r == (708, 651, 800, 450), r
#    the fold is the port era's own, unchanged (the module's promise:
#    only the input plumbing moved). bounds DPR-scaled = (600,200,1600,
#    900); inner*1 = (1584,649); chrome top = 900-649 = 251, half-lateral
#    = (1600-1584)/2 = 8; vx = 600+8+100 = 708, vy = 200+251+200 = 651.
ok("the click folds: DPR-scaled bounds, chrome correction, viewport"
   " rect -> physical px (fold unchanged at %r)" % (r,))

# 4. dpr 2 doubles the world and the fold still lands physical px
videoeye._STATE.clear()
door((100, 200, 400, 225), dpr=2, bounds=(600, 200, 800, 450),
     view=(792, 325))
videoeye.tick(vcfg(), CLK.monotonic())
r = videoeye.video_rect(vcfg())
assert r and r[2] == 800 and r[3] == 450, r
ok("dpr is the ONE ruler: the fold is physical px, stable under dpr 2")

# 5. the scroll pair rides the row and does NOT shift the rect
#    (getBoundingClientRect is viewport-space)
videoeye._STATE.clear()
door((100, 200, 800, 450), bounds=(600, 200, 1600, 900),
     view=(1584, 649))
r1 = videoeye.video_rect(vcfg())
ok("scroll rides the row for the future DRM lane and never shifts the "
   "veil (the viewport-space law, pinned not silent)")

# 6. paused is NOT live (the veil is for PLAYING video)
videoeye._STATE.clear()
door((100, 200, 800, 450), bounds=(600, 200, 1600, 900),
     paused=True)
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.video_rect(vcfg()) is None
ok("a paused video is no rect: the feature dims playback, not posters")

# 7. min_rect_px rejects the ad-banner "video" - and it is a rail,
#    not a verdict
videoeye._STATE.clear()
door((0, 0, 320, 180), bounds=(0, 0, 1920, 1080))
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.video_rect(vcfg()) is None
assert videoeye.video_rect(vcfg(mins=10000)) is not None
ok("min_rect_px is the ad-banner line of defense, and it is a rail, "
   "not a verdict")

# 8. the grace: the row lives for grace_s past the click's stamp and
#    dies after (the extension vanished, the ramp retracts)
videoeye._STATE.clear()
door((100, 200, 800, 450), bounds=(600, 200, 1600, 900))
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.video_rect(vcfg()) is not None
CLK.advance(2.0)
assert videoeye.video_rect(vcfg(), CLK.monotonic()) is not None
CLK.advance(1.5)
assert videoeye.video_rect(vcfg(), CLK.monotonic()) is None
ok("a stale doorway holds the rect for grace_s and lets it go after")

# 9. freshest across families wins: the newest family's row is the one
#    the dimmer frames (the extension swings a family on its UA tell)
videoeye._STATE.clear()
door((0, 0, 600, 400), family="chrome", age=9.0)
videoeye.tick(vcfg(), CLK.monotonic())
door((0, 0, 500, 500), family="opera_gx", age=1.0)
videoeye.tick(vcfg(), CLK.monotonic())
r = videoeye.video_rect(vcfg())
assert r is not None and r[2] == 500 and r[3] == 500, r
ok("freshest family wins across the desk: the newest click frames")

# 10. an unknown family word folds as chrome (never a crash, never a
#     lost rect)
videoeye._STATE.clear()
door((0, 0, 640, 360), family="safari", bounds=(0, 0, 1280, 720),
     view=(1280, 720))
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.video_rect(vcfg(mins=1)) is not None
ok("a foreign family word reads as chrome - the click still frames")

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
                     "videodim": {"on": True, "min_rect_px": 1,
                                  "grace_s": 3}},
                    now)


# 11. one monitor, a rect fully inside: EXACTLY four pieces, the hole
#     is the rect
f = Frame([w(1)])
RECT[0] = (100, 100, 600, 300)
f.tick(100)
assert {v[0] for v in f.rec.painted.values()} == {
    (0, 0, 1000, 100), (0, 400, 1000, 400), (0, 100, 100, 300),
    (700, 100, 300, 300)}, f.rec.painted
ok("the frame is exactly four dark rectangles - the hole is the rect")

# 12. the straddle: pieces PER MONITOR, each clamped; the seam column
#     across the video stays bright
f = Frame([w(1)])
RECT[0] = (900, 200, 200, 400)
f.tick(100)
assert {v[0] for v in f.rec.painted.values()} == {
    (0, 0, 1000, 200), (0, 600, 1000, 200), (0, 200, 900, 400),
    (1000, 0, 1000, 200), (1000, 600, 1000, 200),
    (1100, 200, 900, 400)}, f.rec.painted
ok("the straddle cuts one piece set per panel, each clamped - the seam "
   "column never darkens under the video")

# 13. a gone rect is a stopped video: the frame rides the RAMP
f = Frame([w(1)])
RECT[0] = (100, 100, 600, 300)
f.tick(100)
assert len(f.rec.painted) == 4
RECT[0] = None
f.tick(101)
assert all(v[1] == 0.3 for v in f.rec.painted.values())
f.tick(109)
assert f.rec.painted == {} and len(f.rec.gone) == 4
ok("the veil unfurls down the ramp (hold, steps, bare) - the ramp path "
   "ran")

# 14. the plain mode is UNTOUCHED by the new code paths
f = Frame([w(1), w(2, monitor="MONB")], idle=999.0)
RECT[0] = None
f.tick(100)
assert set(f.rec.painted) == {1, 2}
ok("no live rect means no negative keys: the plain dimmer behaves as "
   "before")

# --- config: the rails at the boundary --------------------------------
n = config.normalize_videodim({"on": "yes", "min_rect_px": 9e9,
                               "grace_s": -2})
assert n["on"] is False and n["min_rect_px"] == 4_000_000 \
    and n["grace_s"] == 0
d = config.normalize_videodim({})
assert d == {"on": False, "min_rect_px": 200000, "grace_s": 3}
ok("normalize_videodim: bad on warns and folds, the rails clamp, "
   "absent is dark")

# --- the wire: the manifest carries the native-messaging law ----------
MAN = json.load(open(os.path.join("extension", "manifest.json"),
                     encoding="utf-8"))
assert MAN["manifest_version"] == 3
assert set(MAN["permissions"]) == {"scripting", "activeTab",
                                   "nativeMessaging"}
assert "host_permissions" not in MAN
ok("the manifest says what the native-messaging host uses: scripting + "
   "activeTab + nativeMessaging, no <all_urls>, no downloads, no tabs")
BG = open(os.path.join("extension", "background.js"),
          encoding="utf-8").read()
assert "function measureVideo()" in BG
assert "eval(" not in BG and "eval(" not in BG
assert "chrome.runtime.connectNative" in BG
ok("the measure is a static bundled function (no eval call) handed to "
   "the native host over connectNative")

if os.path.exists(videoeye.RECT_PATH):
    os.remove(videoeye.RECT_PATH)
print("\nVIDEOEYE TESTS OK (%d)" % len(OK))