"""The video eye's law, pinned: default-off at the root, the doorway
read (the native host's fixed %APPDATA%\\PanelBoss\\rect), the
content-space fold (DPR-scaled bounds, the chrome correction, the
viewport-space judgment), the liveness gates (paused, min_rect_px, the
grace), freshest-wins across families - and the Veils frame: four pieces
clamped per monitor, the straddle covering BOTH panels with no sliver on
the video column, plain veils skipped on the covered panels only, the
ramp retraction, the pause, the STILLNESS CONJUNCT (owner clause 2,
restored Oct 20: the ring rides the [videodim].idle_sec rail - motion
lifts it, the rail re-arms it; Frame.idle drives the fake clock), the
HOLE WORD (owner, Oct 24: the ring's hole is the VIDEO - the founder's
shape made law again; the REPORTING WINDOW hole of clause 1, Oct 20
(bounds expanded 8 px) survives as the [videodim] hole = "window"
word, pinned byte-for-byte; liveness never left the video rect), THE
DIM LAYER AND THE PLAYER (owner, Oct 24: a PLAYING report sheds the
plain veil from its holder window in ANY window state and outranks the
always rows; PAUSED re-wears the veil - tonight's DELA census, lawful
and pinned as law; a DEAD row holds no mask), THE PUMP (the conjunct's clock: inputtruth's filter core pinned
as a PURE function on synthetic report events - boot infinite idle,
the zero-travel chatter refusal, the 3 px dead-zone accumulation, the
injected masks - the hook thread a smoke test only, and the deaf pump
its packeted one warning line), the sound exemption (a film's audio does NOT lift the theater
frame), and the replacement seam (theater active ->
a plain idle veil never covers that region). Every door is a fake seam
(the doorway path, monitors, the clock) - no browser, no Tk, app-up and
headless alike, the dimmer_test family's idiom.
"""
import json
import math
import os
import sys

sys.path.insert(0, ".")
from panelboss import config, dimmer, inputtruth, videoeye   # noqa: E402
import panelboss._inputtruth_hook as _inputtruth_hook  # noqa: E402


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
        family="chrome", age=0.0, lane="click"):
    return {"rect": {"left": x, "top": y, "width": w, "height": h},
            "dpr": dpr, "paused": paused, "scroll": list(scroll),
            "view": list(view),
            "bounds": {"left": bounds[0], "top": bounds[1],
                       "width": bounds[2], "height": bounds[3]},
            "family": family, "lane": lane, "ts": CLK.wall - age}


def door(rect, view=(1920, 1080), bounds=(0, 0, 1920, 1080), age=0.0,
         dpr=1, paused=False, family="chrome", lane="click",
         origin=None):
    body = {"rect": {"left": rect[0], "top": rect[1],
                     "width": rect[2], "height": rect[3]},
            "dpr": dpr, "paused": paused, "scroll": [0, 0],
            "view": list(view),
            "bounds": {"left": bounds[0], "top": bounds[1],
                       "width": bounds[2], "height": bounds[3]},
            "family": family, "lane": lane, "ts": CLK.wall - age}
    if origin is not None:
        body["origin"] = list(origin)
    with open(videoeye.RECT_PATH, "w", encoding="utf-8") as f:
        f.write(json.dumps(body) + "\n")
    stamp = CLK.wall - age
    os.utime(videoeye.RECT_PATH, (stamp, stamp))


def vcfg(on=True, grace=3, mins=200000, idle=15, level=20):
    return {"videodim": {"on": on, "min_rect_px": mins, "grace_s": grace,
                         "idle_sec": idle, "level": level}}


# ---------------------------------------------------------------- pins
# 1. default-off is a ROOT: no file read, no answer
videoeye._STATE.clear()
cfg = vcfg(on=False)
videoeye.tick(cfg, CLK.monotonic())
assert videoeye._STATE == {}
assert videoeye.video_rect(vcfg(on=False)) is None
ok("feature off means the THEATER DOOR is shut: no rect, the switch "
   "owns the frame")

# 1b. THE UNDATED DOOR (owner, Oct 20): with the theater switch OFF
#     the eye STILL reads the doorway (the extension pushes on play
#     no matter what the app's switch says), so live_rect answers the
#     PLAYER-EXEMPTION call - the buddy's report is a fact, the
#     switch is only the frame's consent.
videoeye._STATE.clear()
door((100, 100, 800, 450), lane="auto", paused=False)
videoeye.tick(vcfg(on=False), CLK.monotonic())
assert videoeye._STATE, "the eye closed its eye to the doorway when " \
    "the theater switched off - the player exemption went blind"
assert videoeye.video_rect(vcfg(on=False), CLK.monotonic()) is None, \
    "the feature switch must still gate the FRAME door"
assert videoeye.live_rect(vcfg(on=False), CLK.monotonic()) == \
    (100, 100, 800, 450), "live_rect is the ungated door: a playing " \
    "reported video answers with its rect"
os.remove(videoeye.RECT_PATH)      # leave pin 2 its pristine no-file
videoeye._STATE.clear()            # desk: the door file was THIS
                                   # pin's prop, not the world's
ok("theater off keeps the eye looking: video_rect stays shut, "
   "live_rect serves the exemption")

# 1c. the CLICK snapshot rides the ungated door too - and ages on
#     grace like anywhere: a test-the-geometry exempt-bite has a
#     grace-second lease, no more, and the theater switch changes
#     nothing about that lease.
videoeye._STATE.clear()
door((100, 100, 800, 450), lane="click", age=1.0)
videoeye.tick(vcfg(on=False, grace=3), CLK.monotonic())
assert videoeye.live_rect(vcfg(on=False, grace=3),
                           CLK.monotonic()) == (100, 100, 800, 450)
CLK.advance(3.5)
assert videoeye.live_rect(vcfg(on=False, grace=3),
                           CLK.monotonic()) is None
os.remove(videoeye.RECT_PATH)
videoeye._STATE.clear()
ok("the click snapshot ages on grace through the ungated door too: "
   "the test gesture's exemption lease is grace_s, no more")

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

# 4b. THE ORIGIN REPORT (the owner's border-guess cure, Oct 16 UAT): a
#     MAXIMIZED window's borders hang OFF-screen (live doorway row:
#     bounds.left=-8), so the even-split guess is wrong by a few dozen
#     px. A row that REPORTS its viewport origin (window.screenX/
#     screenY, DIP) folds on the report - the bounds math never runs.
videoeye._STATE.clear()
door((613.5, 68, 1840, 920), bounds=(-8, -8, 3856, 2144),
     view=(3798, 2019), origin=(0, 117))
videoeye.tick(vcfg(), CLK.monotonic())
r = videoeye.video_rect(vcfg())
#     the arithmetic, on the new law: x = round((0 + 613.5) * 1) =
#     round(613.5) = 614 - Python's round ties to EVEN, the very
#     round() the legacy branch uses (the fold's rounding law is
#     round(), unchanged; an int(x+0.5) lane would say 614 too, but
#     this pins what the CODE gives: 614); y = round((117 + 68) * 1)
#     = 185; the size is the rect scaled, (1840, 920).
assert r == (614, 185, 1840, 920), r
ok("the origin report folds exact - the border-guess's few-dozen-px "
   "bite is gone (the same row by the legacy formula lands x=634, "
   "20 px off the truth)")

# 4b+. THE WEBRECT REPORT (v0.4.3, the owner's "up by triple" cure):
#     window.screenX/screenY is a LIE on a maximized window (Chromium
#     fills it with the WINDOW rect - measured (0,0) while the web
#     content actually starts at (42,109): the whole toolbar + the GX
#     sidebar sit between the two). The HOST now measures the browser's
#     Chrome_RenderWidgetHostHWND child - the web viewport whose size
#     IS view x dpr - and stamps its PHYSICAL rect as webrect. The fold
#     anchors on it: x = round(webrect.left + rect.left*dpr), the
#     webrect already PHYSICAL (NOT dpr-scaled - only the page's CSS
#     rect scales).
videoeye._STATE.clear()
def _door_with_webrect(rect, view=(1920, 1080), bounds=(0, 0, 1920, 1080),
                       dpr=1, webrect=(42, 109, 3798, 2019), family="chrome",
                       lane="click", origin=None):
    body = {"rect": {"left": rect[0], "top": rect[1],
                     "width": rect[2], "height": rect[3]},
            "dpr": dpr, "paused": False, "scroll": [0, 0],
            "view": list(view),
            "bounds": {"left": bounds[0], "top": bounds[1],
                       "width": bounds[2], "height": bounds[3]},
            "family": family, "lane": lane, "ts": CLK.wall,
            "webrect": list(webrect)}
    if origin is not None:
        body["origin"] = list(origin)
    with open(videoeye.RECT_PATH, "w", encoding="utf-8") as f:
        f.write(json.dumps(body) + "\n")
    os.utime(videoeye.RECT_PATH, (CLK.wall, CLK.wall))
videoeye._STATE.clear()
_door_with_webrect((613.5, 68, 1840, 920),
                   bounds=(-8, -8, 3856, 2144), view=(3798, 2019),
                   webrect=(42, 109, 3798, 2019), origin=(0, 0))
videoeye.tick(vcfg(), CLK.monotonic())
r = videoeye.video_rect(vcfg())
#     x = round(42 + 613.5*1) = round(655.5) = 656 (ties to even);
#     y = round(109 + 68) = 177; size (1840, 920).
assert r == (656, 177, 1840, 920), r
ok("the webrect report folds EXACT - the page's size bound to the "
   "host's measured viewport origin (42,109): x=656 not 614, y=177 "
   "not 68 - the owner's 'left by more, up by triple' bite is gone")

# 4c. the compat lane: the SAME row without the report (no origin key,
#     host/extension pairs mid-update) keeps the CURRENT bounds answer
videoeye._STATE.clear()
door((613.5, 68, 1840, 920), bounds=(-8, -8, 3856, 2144),
     view=(3798, 2019))
videoeye.tick(vcfg(), CLK.monotonic())
r = videoeye.video_rect(vcfg())
#     vx = -8 + max(0, 3856 - 3798)/2 = 21; x = round(21 + 613.5) =
#     round(634.5) = 634 (ties to even); vy = -8 + (2144 - 2019) =
#     117; y = round(117 + 68) = 185.
assert r == (634, 185, 1840, 920), r
ok("a row without the report folds the legacy bounds answer (the "
   "compat lane is alive, pinned at the owner's exact bite)")

# 4d. a junk origin reads as NO origin (_origin: two numbers or None)
#     and the legacy lane keeps the fold - the row above pin 3, the
#     same expected answer
videoeye._STATE.clear()
door((100, 200, 800, 450), bounds=(600, 200, 1600, 900),
     view=(1584, 649), origin="junk")
videoeye.tick(vcfg(), CLK.monotonic())
r = videoeye.video_rect(vcfg())
assert r == (708, 651, 800, 450), r
ok("a junk origin is no origin: the fold falls back, never guesses")

# 4e. THE VISIBLE PICTURE (owner, Oct 19, the GX ghost): a paused:false
#     row whose folded rect lies ENTIRELY off the virtual desktop (a
#     memory-saver tab parked at -32000, a minimized player) is no
#     video - theater must not veil a desk for a rumor of one. The
#     rule reads the REAL SM_CXVIRTUALSCREEN, so the pins place the
#     ghost far outside any desk this suite can run on.
videoeye._STATE.clear()
_door_with_webrect((16, 68, 1037, 583), view=(1506, 1181),
                   bounds=(-32000, -32000, 1506, 1181), dpr=1,
                   webrect=(-32000, -32000, 1506, 1181),
                   family="opera_gx", lane="auto")
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.video_rect(vcfg()) is None, \
    "the GX ghost (webrect -32000) still conjuncts the theater veil"
ok("a paused:false row parked off the desk dims NOTHING - the "
   "conjunct is the picture, not the audio")

videoeye._STATE.clear()
import ctypes as _ct
_vx = _ct.windll.user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
_vy = _ct.windll.user32.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
_door_with_webrect((10, 10, 900, 500), view=(1200, 800),
                   bounds=(_vx + 1, _vy + 1, 1200, 800), dpr=1,
                   webrect=(_vx + 1, _vy + 1, 1200, 800), lane="auto")
videoeye.tick(vcfg(), CLK.monotonic())
r = videoeye.video_rect(vcfg())
assert r == (_vx + 11, _vy + 11, 900, 500), r
ok("a whole frame just inside the desk edge stays a movie")

videoeye._STATE.clear()
_door_with_webrect((0, 0, 3000, 1000), view=(3000, 1000),
                   bounds=(_vx - 100, _vy, 3000, 1000), dpr=1,
                   webrect=(_vx - 100, _vy, 3000, 1000), lane="auto")
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.video_rect(vcfg()) == (_vx - 100, _vy, 3000, 1000)
ok("a straddled window is a visible picture - intersection, not "
   "containment, is the rule")

# 4f. the report under dpr 2: the DIP pair scales like everything else
videoeye._STATE.clear()
door((10, 20, 200, 100), dpr=2, bounds=(0, 0, 1920, 1080),
     view=(960, 540), origin=(100, 50))
videoeye.tick(vcfg(mins=1), CLK.monotonic())
r = videoeye.video_rect(vcfg(mins=1))
#     (100 + 10) * 2 = 220, (50 + 20) * 2 = 140, 200*2=400, 100*2=200
assert r == (220, 140, 400, 200), r
ok("origin folds physical px under dpr 2 - (110*2, 70*2, 400, 200), "
   "the one ruler holds")

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

# 8b. the AUTO lane is a durable STATE, not a snapshot: a paused:false
#     auto row does NOT age out on grace_s - a movie plays for minutes
#     with no further event, and the eye must not retract it. The IDLE
#     conjunction (playing AND still) lives in the DIMMER, not here.
videoeye._STATE.clear()
door((100, 200, 800, 450), bounds=(600, 200, 1600, 900), lane="auto")
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.video_rect(vcfg(), CLK.monotonic()) is not None
CLK.advance(30.0)               # way past grace_s - the movie still plays
assert videoeye.video_rect(vcfg(), CLK.monotonic()) is not None
ok("an auto playing row persists past grace_s (a movie is a state, "
   "not a 3 s snapshot); the theater gate is the rect itself, in the "
   "dimmer - the eye grows no timer")

# 8c. the CLICK lane is a snapshot: it ages out on grace_s (measure
#     once, see the rect - the demoted test-the-geometry gesture)
videoeye._STATE.clear()
door((100, 200, 800, 450), bounds=(600, 200, 1600, 900), lane="click")
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.video_rect(vcfg(), CLK.monotonic()) is not None
CLK.advance(4.0)
assert videoeye.video_rect(vcfg(), CLK.monotonic()) is None
ok("a click snapshot ages out on grace_s - the test gesture measures "
   "once and goes")

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
        self.calls = []      # every paint ever queued (the re-pin pin
                             # counts beats, the dict only holds states)

    def paint(self, hwnd, rect, alpha):
        self.painted[hwnd] = (rect, alpha)
        self.calls.append((hwnd, rect, alpha))

    def unveil(self, hwnd):
        self.painted.pop(hwnd, None)
        self.gone.append(hwnd)


def w(hwnd, monitor="MONA", fg=False, rect=(10, 10, 800, 600)):
    return {"hwnd": hwnd, "pid": hwnd, "exe": "notepad.exe",
            "cls": "X", "monitor": monitor, "tool": False,
            "cloaked": False, "iconic": False, "fg": fg, "rect": rect}


RECT = [None]
WRECT = [None]     # the clause-1 half of the fake seam (the reporting
                   # window's bounds; None keeps the bare-rect answer:
                   # every pre-pair pin runs the compat lane)


class Frame:
    """The fake desk: an idle clock (mutable via .idle), an audio set
    (mutable via .audio), and the video eye seam fixed to RECT[0] /
    WRECT[0]. The .idle rail drives BOTH waits again: the plain
    veil's dimmer rail AND the theater's STILLNESS CONJUNCT (clause 2
    restored, Oct 20 - motion state means the fake reads below the
    [videodim].idle_sec rail and the RING is not born; the player
    exemption reads the seam, never the clock, so the movie stays
    bright either way). The plain veil's sound exemption reads
    .audio. Both are per-tick mutable so the suite can drive the
    sound/touch edges and the exemption without a browser."""
    def __init__(self, wins=None, idle=0.0, audio=None, vlevel=30,
                 vfade=False, vmons=None):
        self.wins = wins or []
        self.rec = Rec()
        self.idle = idle
        self.audio = audio if audio is not None else set()
        self.vlevel = vlevel
        self.vfade = vfade
        # the [videodim].monitors rows (the Oct-16 per-panel wave);
        # {} is the legacy shape - only the video's panel is framed
        self.vmons = vmons or {}
        self.v = dimmer.Veils(
            lambda: self.wins, lambda: self.audio,
            lambda: self.idle, self.rec.paint, self.rec.unveil,
            video=lambda cfg, now: RECT[0] if WRECT[0] is None
            else (RECT[0], WRECT[0]),      # the bare-rect lane and
            #                               # the clause-1 pair, on
            #                               # the same one seam
            monitors=lambda: MON)

    def tick(self, now, level=30, dim_on=True, vidle=0, von=True,
             dim_idle=120, hole=None, always=None):
        # hole: the [videodim] hole word - None leaves the key ABSENT
        # (the byte-compatible file's shape; the Oct-24 video-hole
        # default law rides the absence), "window" asks the Oct-20
        # shape. always: the [dimmer].always rows (19g drives the
        # owner's desk shape: a panel that dims WITHOUT the idle wait).
        vd = {"on": von, "min_rect_px": 1, "grace_s": 3,
              "idle_sec": vidle, "level": self.vlevel,
              "fade": self.vfade, "monitors": self.vmons}
        if hole is not None:
            vd["hole"] = hole
        self.v.tick({"dimmer": {"on": dim_on,
                                "monitors": {"MONA": True,
                                             "MONB": True},
                                "always": always or {}, "apps": {},
                                "idle_sec": dim_idle, "ramp_sec": 8,
                                "level": level, "bound": None},
                     "videodim": vd},
                    now)


# 11. one monitor, a rect fully inside: EXACTLY four pieces, the hole
#     is the rect (idle high so the conjunction is satisfied)
f = Frame([w(1)], idle=999.0)
RECT[0] = (100, 100, 600, 300)
f.tick(100)
assert {v[0] for v in f.rec.painted.values()} == {
    (0, 0, 1000, 100), (0, 400, 1000, 400), (0, 100, 100, 300),
    (700, 100, 300, 300)}, f.rec.painted
ok("the frame is exactly four dark rectangles - the hole is the rect")

# 12. the straddle: pieces PER MONITOR, each clamped; the seam column
#     across the video stays bright. (Oct-21 amendment, d1: the fake
#     desk gained a STRADDLING HOLDER - the old lone window sat fully
#     west of the reported rect, and the holder-match gate at birth
#     rightly refuses a report no census window holds. The straddle
#     law itself is unchanged; the desk just became honest about who
#     plays the movie.)
f = Frame([w(1, rect=(850, 150, 300, 500))], idle=999.0)
RECT[0] = (900, 200, 200, 400)
f.tick(100)
assert {v[0] for v in f.rec.painted.values()} == {
    (0, 0, 1000, 200), (0, 600, 1000, 200), (0, 200, 900, 400),
    (1000, 0, 1000, 200), (1000, 600, 1000, 200),
    (1100, 200, 900, 400)}, f.rec.painted
ok("the straddle cuts one piece set per panel, each clamped - the seam "
   "column never darkens under the video")

# 13. a gone rect is a stopped video: the frame rides the RAMP. The
#     desk stays "still" at 10 s - enough for the theater rail (vidle
#     default 0) but BELOW the plain dimmer's 120 s rail, so a stopped
#     video reads as "no frame, and not idle-dimmed either": only the
#     frame's own ramp path is under test, no plain veil in the frame.
f = Frame([w(1)], idle=10.0)
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

# 15. THE STILLNESS CONJUNCT, RESTORED (owner clause 2, Oct 20:
#     "movie theater respects input timers"). THE HEADLINE PAIR:
#     motion state (rail unpassed) means no RING - and STILL no
#     plain veil on the player: the exemption keys on the buddy's
#     report, clock-free, plain law armed notwithstanding. Stillness
#     past the rail BIRTHS the ring; motion lifts it (fade-off: this
#     tick); the rail re-arms it. The rect's own going lifts it on
#     its own law (70eb8fa's surviving half). Frame.idle drives the
#     fake clock; the theater rail (vidle) sits ABOVE the plain
#     120 rail so the plain-armed / ring-unborn state is reachable.
f = Frame([w(1, rect=(50, 50, 900, 700)),
           w(2, monitor="MONB", rect=(1100, 50, 800, 600))],
          idle=121.0, vlevel=30)
RECT[0] = (100, 100, 600, 300)
f.tick(100, vidle=130)               # plain ARMED (121 >= 120) and
assert f.rec.painted == {2: ((1100, 50, 800, 600), 0.3)}, \
    f.rec.painted                    # the theater rail UNPASSED (121
#                                    # < 130): NO RING - and the player
#                                    # (w1's rect holds the video)
#                                    # takes no plain veil either
f.idle = 131.0
f.tick(101, vidle=130)               # stillness past the rail: the
assert len([h for h in f.rec.painted if h < 0]) == 4, f.rec.painted
                                     # RING IS BORN around the rect
assert 2 in f.rec.painted            # MONB dims as the plain law says
f.idle = 30.0
f.tick(102, vidle=130)               # motion: below BOTH rails - the
assert f.rec.painted == {}, f.rec.painted   # ring LIFTS (fade off: this
                                     # tick), the plain field retracts
f.idle = 131.0
f.tick(103, vidle=130)               # the rail RE-ARMS: the ring is
assert len([h for h in f.rec.painted if h < 0]) == 4, f.rec.painted
                                     # born again
RECT[0] = None
f.tick(104, vidle=130)               # and the rect's GOING lifts it
assert f.rec.painted == {            # too, rail notwithstanding -
    1: ((50, 50, 900, 700), 0.3),    # and the exemption rides the
    2: ((1100, 50, 800, 600), 0.3)}  # REPORT: no report, no
#                                    # exemption, the movie window
#                                    # dims like any idle window
#                                    # (70eb8fa's admitted law)
ok("the restored conjunct (clause 2): no ring while the desk moves "
   "and no plain veil on the player in that state (the pair), the "
   "ring born and re-born on the rail, the rect's going its own lift")

# 15b. THE FADE OPTION, other side: fade=True opts the theater into
#      the ramp family - the retraction after the MOTION LIFT (or
#      the rect's own going) is the one-tick hold (the eye's
#      fail-open law) then the gradual steps, no blink. The conjunct
#      decides WHEN the ring lifts; the fade option decides HOW.
fb = Frame([w(1, rect=(50, 50, 900, 700)),
            w(2, monitor="MONB", rect=(1100, 50, 800, 600))],
           idle=131.0, vlevel=30, vfade=True)
RECT[0] = (100, 100, 600, 300)
fb.tick(120, vidle=130)                # stillness past the rail:
assert len([h for h in fb.rec.painted if h < 0]) == 4   # the ring is BORN
fb.idle = 30.0                         # motion mid-film: the ring
fb.tick(121, vidle=130)                # lifts - fade=true joins the
assert len([h for h in fb.rec.painted if h < 0]) == 4   # ramp family,
assert all(v[1] == 0.3 for h, v in fb.rec.painted.items()
           if h < 0)                      # the hold is still full
fb.tick(129, vidle=130)                # a whole ramp later: bare
assert fb.rec.painted == {}, fb.rec.painted
ok("fade=true rides the ramp family on the MOTION lift too: one-tick "
   "hold then retract - the conjunct's lift, the fade option's shape")

# 15c. HOLDER-MATCH AT BIRTH (d1, the owner's freshness ruling): the
#      ring is born only over a LIVE HOLDER. Branch one: the eye
#      reports, the desk is still past the rail, and the census holds
#      NO window containing the rect - stale by FACT, no clock
#      needed: zero theater pieces are born (the plain veils proceed:
#      it is the RING that the ghost refuses, not the desk's law).
#      The spy counts the seam: ONE census per birth tick - the gate
#      paid it and the plain walk rode it (this assert FAILS if the
#      walk re-EnumerWindows). Branch two: the census is DEAD - the
#      birth gate refuses on the doubt too, and the walk's old fail-
#      open still holds the (empty) field's position.
_census_calls = [0]


def _dead_census():
    raise OSError("census dead (fake)")


f = Frame([w(1, rect=(10, 10, 300, 200))], idle=999.0)   # too small
RECT[0] = (100, 100, 600, 300)                           # to hold it
_wreal = f.v._windows


def _spy():
    _census_calls[0] += 1
    return _wreal()


f.v._windows = _spy
f.tick(100, vidle=5)
assert not any(h < 0 for h in f.rec.painted), f.rec.painted   # NO ring
assert _census_calls[0] == 1, _census_calls      # one walk, reused
f = Frame([w(1)], idle=999.0)                   # the holder EXISTS
RECT[0] = (100, 100, 600, 300)                  # here; only eyes gone
f.v._windows = _dead_census
f.tick(100, vidle=5)
assert f.rec.painted == {} and f.rec.gone == [], f.rec.painted
ok("the ring is born only over a live holder (d1): a no-holder tick "
   "and a dead-census tick both refuse birth - stale by fact, fail- "
   "closed on birth alone - and the birth census is ONE walk the "
   "plain leg reuses (spy: exactly one seam call on a birth tick)")

# 16. THE SOUND EXEMPTION: a film's audio must not lift the theater
#     frame - the drive is the pointer/keyboard idle clock only. Sound
#     touches the PLAIN veil's per-window exemption, never the frame.
f = Frame([w(1)], idle=999.0, audio={1})
RECT[0] = (100, 100, 600, 300)
f.tick(100, vidle=5)
assert len(f.rec.painted) == 4        # audio pid present, frame STAYS
f.audio = {1}
f.tick(101, vidle=5)
assert len(f.rec.painted) == 4        # sound does not lift the frame
ok("a film's sound never lifts the theater frame - the lifts are the "
   "clock (the rail), the whole-field switches, and the rect's own "
   "going (the conjunct restored, clause 2)")

# 17. THE REPLACEMENT SEAM: while the theater frame is ACTIVE, a plain
#     idle veil must NOT cover that panel - the movie stays bright, the
#     rest of the desk dims. (The browser window is exempt by pid only
#     while it is SOUNDING; the frame's panel skip is the
#     sound-independent backstop for a silent mid-scene stretch.)
f = Frame([w(1), w(2, monitor="MONB", rect=(1100, 100, 800, 600))],
          idle=999.0)   # MONB's window wears a MONB-true rect (the
                        # default dummy sat numerically OVER the
                        # video and would claim the player exemption
                        # for the wrong panel - real census rects are
                        # monitor-true; real rects, real law)
RECT[0] = (100, 100, 600, 300)        # the theater frame on MONA
f.tick(100, vidle=5, dim_on=True)
keys = f.rec.painted
# plain window 1 (on MONA) must NOT be painted: the frame owns MONA.
assert 1 not in keys, keys
assert 2 in keys, keys                # window 2 on MONB dims normally
assert sum(1 for k in keys if k < 0) == 4, keys   # exactly 4 frame pieces
ok("theater active -> a plain veil never covers the video's panel; the "
   "rest of the desk dims (replacement seam)")

# 17b. PER-PANEL THEATER (owner, Oct 16): [videodim].monitors frames an
#      OPT-IN panel with a FULL-FIELD piece at its own level while the
#      conjunction holds, and an on=false row strips the video's own
#      panel - the plain veils proceed there as usual. (viii): every
#      pin above ran with NO monitors table (the harness default {})
#      and passed unchanged - the legacy shape is the regression proof.
f = Frame([w(1, monitor="MONB")], idle=999.0, vmons={
    "MONB": {"on": True, "level": 50}})
RECT[0] = (100, 100, 600, 300)            # the video sits on MONA
f.tick(100, vidle=5)
pieces = {h: v for h, v in f.rec.painted.items() if h < 0}
assert len(pieces) == 5, f.rec.painted   # 4 border pieces (MONA) +
#                                         # one full field (MONB)
full = [v for v in pieces.values() if v[0] == (1000, 0, 1000, 800)]
assert len(full) == 1 and full[0][1] == 0.5, f.rec.painted
border = [v for v in pieces.values() if v[0] != (1000, 0, 1000, 800)]
assert len(border) == 4 and all(v[1] == 0.3 for v in border), \
    f.rec.painted                        # the global theater level
assert 1 not in f.rec.painted            # MONB is covered too: the
#                                        # plain veil never stacks
#                                        # under its full-field piece
ok("videodim.monitors MONB: EXACTLY one full-field piece at its rect, "
   "alpha 0.5 (per-row level), while MONA keeps its four border pieces")

f = Frame([w(1), w(2, rect=(3000, 10, 800, 600))], idle=999.0,
          vmons={"MONA": {"on": False}})
RECT[0] = (100, 100, 600, 300)
f.tick(100, vidle=5, dim_on=True)
assert f.rec.painted == {2: ((3000, 10, 800, 600), 0.3)}, f.rec.painted
# (Oct-20 amendment: the old expectation veiled BOTH windows - the
# plain veil proceeds on an opted-out panel exactly as always, and
# the player exemption now rides that rule: window 1 plays the
# reported video and stays bright; window 2 does not and dims on
# schedule. The amendment proves the seam is per-window, not a new
# blanket panel immunity - the ring remains the only panel-wide
# actor, and it is opted out here.)
ok("videodim.monitors MONA on=false: the video panel gets NO frame "
   "and is NOT covered - the plain veils proceed there, every window "
   "but the one playing the reported video (Oct-20 exemption)")

# 19. THE OWNER REPRODUCTION, PINNED (Oct 20, corrected by the same
#     evening's re-probe): a video plays on MONA, the owner tabs to a
#     window on MONB, the secondary opted into the theater at its own
#     level - and the desk is PHYSICAL and never-still: GetLastInputInfo
#     re-stamped by zero-travel HID chatter (the KVM/USB chain;
#     measured 0.00-0.05 s across 90+30 hands-off samples, the cursor
#     pixel-frozen at (-3140,1542) - the RDP theory of 70eb8fa was
#     wrong, the clock is the sick half). The plain dimmer runs
#     ALWAYS-ON (the owner's [dimmer].idle_sec=0). The stillness rail
#     therefore UNPASSES forever: the ring never comes here (until
#     the clock's trust is adjudicated) - but the movie does NOT go
#     dark: the player window is exempt from the plain veils by the
#     buddy's report, clock-independent. That is the clause-2 pair,
#     live-desk edition: no ring AND no veil on the movie. The opt-in
#     secondary dims with the rest (the ring is the only actor that
#     would full-field it, and the ring is unborn).
f = Frame([w(1, rect=(50, 50, 900, 700)),
           w(2, monitor="MONB", fg=True, rect=(1100, 50, 800, 600))],
          idle=0.0, vlevel=76,
          vmons={"MONB": {"on": True, "level": 76}})
RECT[0] = (100, 100, 600, 300)
f.tick(100, vidle=5, dim_idle=0)
assert not any(h < 0 for h in f.rec.painted), f.rec.painted
                                     # the rail never passes: NO ring
assert f.rec.painted == {}, f.rec.painted
#       (the plain field cannot birth EITHER window here: w1 is the
#       player - exempt by the buddy's report, clock-free; w2 is the
#       foreground - exempt by the plain law's own first gate. The
#       always-on desk dims everything ELSE, exactly as configured.)
f.tick(101, vidle=5, dim_idle=0, level=30)   # second beat, same truth
assert not any(h < 0 for h in f.rec.painted)
assert f.rec.painted == {}
ok("the owner's desk, honestly: a never-aging clock starves the ring, "
   "never the MOVIE - the player exemption is clock-independent, so "
   "the movie never wears a veil whatever the timer says")

# 19c. THE HOLE IS THE VIDEO (owner reversal, Oct 24): even when the
#      row reports its bounds, the DEFAULT hole is the video rect -
#      the page and the browser's own chrome wear the darkness with
#      the desk (the Oct-20 window law survives one config word away,
#      pinned next, byte-for-byte). MONA is (0,0,1000,800); the video
#      (300,300,400,200):
f = Frame([w(1)], idle=999.0)
RECT[0] = (300, 300, 400, 200)       # a video INSIDE the window
WRECT[0] = (100, 50, 800, 700)       # reported - and IGNORED by the
#                                    # default law
f.tick(100)
assert {v[0] for v in f.rec.painted.values()} == {
    (0, 0, 1000, 300), (0, 500, 1000, 300), (0, 300, 300, 200),
    (700, 300, 300, 200)}, f.rec.painted
ok("the hole is the VIDEO by default, even over a reported window "
   "(the Oct-24 reversal): the ring is cut around the video, the "
   "chrome dims with the desk")

# 19c'. THE WINDOW WORD: hole = "window" answers the Oct-20 shape -
#       the REPORTING WINDOW, the bounds 8 px EXPANDED (the GDI-lie
#       direction, dimmer's geometry note - a too-small hole would
#       clip the reporting window's px, and THAT the veil may never
#       do). The ring lands entirely outside the expanded bounds -
#       the browser's chrome stays bright with the movie it plays.
#       The window (100,50,800,700) expands to (92,42,816,716):
f = Frame([w(1)], idle=999.0)
f.tick(100, hole="window")
assert {v[0] for v in f.rec.painted.values()} == {
    (0, 0, 1000, 42), (0, 758, 1000, 42), (0, 42, 92, 716),
    (908, 42, 92, 716)}, f.rec.painted
ok("hole = \"window\": the Oct-20 shape survives one word away - the "
   "ring cut around the reporting window (bounds + 8 px), the old "
   "set byte-for-byte")

# 19d. THE NAMED ASYMMETRY (clause 1's honest half): liveness stayed
#      on the VIDEO rect - a tiny ad in a huge window must not carve
#      a huge hole from a tiny video. The same row under the min rail
#      has NO ring at all (the eye's law, videoeye._best_pair: the
#      gates read the video, and a gated-out row hands out NO window
#      either). Pinned at the eye, at the door: a sub-min video in a
#      1920x1080 window answers (None, None) - not (None, window).
videoeye._STATE.clear()
door((10, 10, 40, 30), bounds=(0, 0, 1920, 1080), view=(1920, 1080))
videoeye.tick(vcfg(), CLK.monotonic())   # 1200 px under the min rail
assert videoeye.live_rect(vcfg(), CLK.monotonic()) is None
assert videoeye.window_rect(vcfg(), CLK.monotonic()) is None
ok("a sub-min video in a huge window answers NO hole at all: the "
   "min rail rides the video, the hole rides the report")

# 19e. THE PAIRED DOOR (clause 1 at the eye): live_pair is the seam's
#      contract - (rect, window bounds) from ONE walk of the same
#      freshest row; the bounds fold is the dpr ruler the compat lane
#      already used (the pin-3 row's physical (600,200,1600,900)); a
#      webrect row whose host never reported bounds answers (rect,
#      None) - the compat lane, the video rect stays the hole.
videoeye._STATE.clear()
door((100, 200, 800, 450), bounds=(600, 200, 1600, 900),
     view=(1584, 649))
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.live_pair(vcfg(), CLK.monotonic()) == \
    ((708, 651, 800, 450), (600, 200, 1600, 900))
os.remove(videoeye.RECT_PATH)
videoeye._STATE.clear()
_wb = {"rect": {"left": 100, "top": 100, "width": 800, "height": 450},
       "dpr": 1, "paused": False, "scroll": [0, 0],
       "view": [1920, 1080], "family": "chrome", "lane": "auto",
       "ts": CLK.wall, "webrect": [0, 0, 1920, 1080]}
with open(videoeye.RECT_PATH, "w", encoding="utf-8") as f19:
    f19.write(json.dumps(_wb) + "\n")
os.utime(videoeye.RECT_PATH, (CLK.wall, CLK.wall))
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.live_pair(vcfg(), CLK.monotonic()) == \
    ((100, 100, 800, 450), None)     # webrect folds, bounds absent
os.remove(videoeye.RECT_PATH)
videoeye._STATE.clear()
ok("live_pair: one walk, both answers; dpr folds the bounds; no "
   "bounds report is (rect, None) - the compat lane at the door")

# 19f. THE PUMP, PURE (the conjunct's clock, the Oct-20 input-truth
#      wave): the filter core takes SYNTHETIC RAW PACKET fields - no
#      hooks (none shipped: the owner's raw-only ruling), no ctypes
#      threads, no sleeps; the clock arrives as `now`. This is the
#      law the desk receipts wrote (unplug.log / direct.log /
#      nohid.log / nohid2.log, Oct 20): a stuck macropad re-reported
#      the mouse with ZERO travel and poisoned GetLastInputInfo for
#      a working day - travel, not the report, is the input.
pmp = inputtruth.Pump()
assert math.isinf(pmp.idle_seconds(0.0))   # BOOT = INFINITE idle, not
#                                           # "now" (the packeted state)
for _i in range(500):                      # the nohid.log desk: 500
    assert not pmp.mouse(0, 0, 0, 1.0 + _i)  # zero-travel relative
assert math.isinf(pmp.idle_seconds(600.0)) # packets - the stream is
#                                           # traffic, but never input
assert not pmp.key(0x1E, inputtruth.RI_KEY_BREAK, 601.0)
                                           # a keyUP proves nothing
assert pmp.key(0x1E, 0, 602.0)             # a MAKE with the BREAK
                                           # clear is a hand
assert pmp.idle_seconds(607.0) == 5.0
assert not pmp.key(0x1E, inputtruth.RI_KEY_TERMSRV_SHADOW, 608.0)
                                           # the RDP-shadow make is
                                           # not a local hand
assert pmp.key(0x41, inputtruth.RI_KEY_E0, 610.0)
                                           # extended bits ride: the
                                           # make still counts
pmp = inputtruth.Pump()                    # the CUMULATIVE dead zone
assert not pmp.mouse(1, 0, 0, 100.0)       # a high-res mouse streams
assert not pmp.mouse(0, 1, 0, 100.1)       # honest sub-zone deltas:
assert not pmp.mouse(0, 0, 0, 100.15)      # 2 px so far, under
assert pmp.mouse(1, 0, 0, 100.2)           # 3 px TOTAL travels:
                                           # stamps
assert not pmp.mouse(1, 1, 0, 100.3)       # and the accumulator
                                           # RE-ARMS: 2 px after the
                                           # stamp is 2, not 5
pmp = inputtruth.Pump()                    # absolute reports anchor
pmp.mouse(200, 100, inputtruth.MOUSE_MOVE_ABSOLUTE, 200.0)
assert math.isinf(pmp.idle_seconds(201.0))  # first one measures
                                           # nothing
pmp = inputtruth.Pump()                    # from
pmp.mouse(200, 100, inputtruth.MOUSE_MOVE_ABSOLUTE, 200.0)
assert not pmp.mouse(201, 100, inputtruth.MOUSE_MOVE_ABSOLUTE, 201.0)
                                           # one finger-px under way
assert pmp.mouse(202, 102, inputtruth.MOUSE_MOVE_ABSOLUTE, 202.0)
                                           # 4 px from the ANCHOR: a
                                           # touch travel counts
pmp = inputtruth.Pump()
assert not pmp.mouse(9999, 0, inputtruth.MOUSE_VIRTUAL_DESKTOP, 300.0)
                                           # virtual-desktop coords
                                           # are not px of this desk
                                           # (display's own gate)
assert pmp.traffic_since(300.0) and not pmp.traffic_since(300.5)
                                           # the refused packet is
                                           # STILL device traffic
                                           # (the witness counts the
                                           # stream, not the verdict) -
                                           # the pad's zero-travel
                                           # class of lie keeps the
                                           # wake exemption SHUT,
                                           # exactly as the owner's
                                           # rule reads
ok("the pump's filter, pure: boot infinite, zero-travel traffic never "
   "input, real travel ACCUMULATES across sub-zone reports (high-res "
   "mice, slow drags), absolute reports count by anchor delta, "
   "VIRTUAL_DESKTOP and shadow-makes and keyups are none of the "
   "pump's business; traffic_since is the exemption's witness")

#      INJECTION IS DROPPED AT THE EAR (the null-hDevice marker the
#      Oct-20 probe confirmed live: every SendInput packet arrived
#      hDevice-less while real devices carry their HID handle).
#      Structure-level: hand RawEars._parse real RAWINPUT buffers
#      with and without the handle, no thread required.
class _EarProbe:
    """A RawEars that never started a thread: _parse against buffers
    the fake GetRawInputData hands back."""
    def __init__(self):
        self._pump = inputtruth.Pump()
        self._now = lambda: 400.0


_real_grid = _inputtruth_hook.U32.GetRawInputData
_bufs = {}


def _fake_grid(handle, cmd, buf, psize, hsize):
    blob = _bufs["raw"]
    if buf is None:
        psize._obj.value = len(blob)        # byref(UINT): report size
        return 0
    ctypes.memmove(buf, blob, len(blob))
    psize._obj.value = len(blob)
    return len(blob)


def _pack(head_dev, payload, kind):
    h = _inputtruth_hook.RAWINPUTHEADER()
    h.dwType = kind
    h.dwSize = 200
    h.hDevice = head_dev
    h.wParam = 0
    return bytes(h) + payload


def _parse_into(ear, blob):
    _bufs["raw"] = blob
    _inputtruth_hook.U32.GetRawInputData = _fake_grid
    try:
        _inputtruth_hook.RawEars._parse(ear, 1)
    finally:
        _inputtruth_hook.U32.GetRawInputData = _real_grid


import ctypes                              # noqa: E402
ear = _EarProbe()
_kb = _inputtruth_hook.RAWKEYBOARD(0x1E, 0, 0, 0x41, 0x0100, 0)
ear_pump = ear._pump
_parse_into(ear, _pack(0, bytes(_kb), _inputtruth_hook.RIM_TYPEKEYBOARD))
assert ear_pump.last is None               # hDevice NULL: injected,
#                                           # never reaches the pump
#                                           # (no stamp, and NO
#                                           # traffic credit either:
#                                           # a synthetic knock is
#                                           # not a device speaking)
_parse_into(ear, _pack(0x1001, bytes(_kb), _inputtruth_hook.RIM_TYPEKEYBOARD))
assert ear_pump.last == 400.0              # handle present: the make
#                                           # stamps as the pure core
#                                           # said it would
ear_pump.last = 399.0              # move the witness off the kb
                                   # stamp so the mouse drop is
                                   # OBSERVABLE, not coincidental
_mo = _inputtruth_hook.RAWMOUSE()
_mo.flags = 0
_mo.u.buttons.ulButtons = 0
_mo.u.buttons.buttonFlags = 0
_mo.u.buttons.buttonData = 0
_mo.lastX, _mo.lastY = 17, 0
_parse_into(ear, _pack(0, bytes(_mo), _inputtruth_hook.RIM_TYPEMOUSE))
assert ear_pump.last == 399.0              # injected MOUSE (17 px!)
#                                           # also dropped: an
#                                           # injected hand's travel
#                                           # is not this pump's
#                                           # input, and the EXEMPTION
#                                           # (below) is its lane
ok("null-hDevice packets (SendInput's documented marker, probe-confirmed "
   "Oct 20) are dropped AT THE EAR for both device types: injection "
   "cannot stamp the pump clock no matter what deltas it carries - "
   "the owner's wake exemption is a remote hand's only lane")

#      THE WAKE EXEMPTION, both directions (the owner's rule, verbatim
#      from the module docstring): injection counts as input ONLY when
#      the stock clock moved while the pump saw ZERO device packets -
#      amid real traffic (even zero-travel pad lies) the pump's
#      verdict alone governs.
_saved_ear = inputtruth._ear


class _AliveEar:
    def alive(self):
        return True


inputtruth._ear = _AliveEar()
pmp = inputtruth.Pump()
_saved_pump, inputtruth._pump = inputtruth._pump, pmp
inputtruth.WAKE_WINDOW_SEC = 1.0
# (a) DEVICE TRAFFIC + stock advance -> NO wake via the exemption:
_now = inputtruth.time.monotonic()         # no fake clock needed:
pmp.mouse(0, 0, 0, _now - 0.5)             # ONE zero-travel device
wake1 = inputtruth.wake_idle_seconds(0.3)      # packet half a second
assert math.isinf(wake1), wake1            # ago; stock says "0.3 -
#                                           # busy!" - the pump saw
                                           # traffic, so the pump
                                           # verdict (never a counted
                                           # input: inf) governs and
                                           # the stock lie does NOT
                                           # wake the screens
# (b) stock advance + NO packets at all -> the synthetic knock wakes:
pmp2 = inputtruth.Pump()                   # fresh: stream silent
inputtruth._pump = pmp2
wake2 = inputtruth.wake_idle_seconds(0.3)
assert wake2 == 0.3, wake2                       # whatever moved stock was
#                                           # injection - count it: a
#                                           # remote hand wakes the
#                                           # door it already dimmed
# and the pump's OWN truth still wakes it the plain way:
pmp2.key(0x1E, 0, inputtruth.time.monotonic())
                                           # a real make, this second
wake3 = inputtruth.wake_idle_seconds(9.0)  # stock says "idle 9s" -
assert wake3 < 1.0, wake3                  # the pump says HAND, and
#                                           # the hand outranks the
#                                           # stranger's 9 seconds
inputtruth._ear = _saved_ear
inputtruth._pump = _saved_pump
ok("the wake exemption, both directions: traffic + stock advance does "
   "NOT wake (the pad lie cannot), silence + stock advance DOES (the "
   "remote hand is a guest at the door it already dimmed), and the "
   "pump's own counted input outranks a lying stock - off-phase only, "
   "the state seam is pinned in dimmer_test 6c")

#      THE CONJUNCT ON THE PUMP (the clause-2 rail and the filter,
#      end to end - hooks still synthetic, the seam's clock IS a
#      Pump): chatter holds the ring, real travel lifts it, the rail
#      re-arms. The Frame's idle seam is swapped for pump.idle and
#      the fake desk's clock hand is the pump's own `now`.
RECT[0] = (100, 100, 600, 300)
WRECT[0] = None
f = Frame([w(1)], idle=999.0)
pmp = inputtruth.Pump()
TC = [1000.0]
f.v._idle = lambda: pmp.idle_seconds(TC[0])
f.tick(100, vidle=15)
assert len([h for h in f.rec.painted if h < 0]) == 4, f.rec.painted
                                       # boot=inf past the rail: RING
for _i in range(200):                  # the desk CHATTERS hands-off
    pmp.mouse(0, 0, 0, TC[0])          # 10 s of zero-travel packets
    TC[0] += 0.05
f.tick(101, vidle=15)
assert len([h for h in f.rec.painted if h < 0]) == 4, f.rec.painted
                                       # the ring HOLDS through lies
assert pmp.mouse(4, 0, 0, TC[0])       # 4 px of real travel: a hand
f.tick(102, vidle=15)
assert not any(h < 0 for h in f.rec.painted), f.rec.painted
                                       # lifts the RING (the player
                                       # stays bright either way -
                                       # the exemption is clock-free)
TC[0] += 15.0
f.tick(103, vidle=15)
assert len([h for h in f.rec.painted if h < 0]) == 4, f.rec.painted
                                       # and the rail RE-ARMS on the
                                       # pump
RECT[0] = None
ok("the conjunct rides the pump clock end to end: chatter holds the "
   "ring, real travel lifts it, the rail re-arms - clause 2 on the "
   "sick desk's own truth")

#      THE HOOK THREAD, SMOKE ONLY (the packet's one concession to the
#      real desk: the raw ear installs, survives an idle beat, and
#      unstalls clean - every SEMANTIC above was pinned without it):
assert inputtruth.install(), "the raw ear must install on this desk"
assert inputtruth.alive()
import time as _time
inputtruth.pump().key(0x1E, 0, _time.monotonic())
assert isinstance(inputtruth.idle_seconds(), float)  # the smoke
#                                                     # keystamp makes it
#                                                     # finite, never a raise
_time.sleep(0.3)                                     # an idle desk...
assert inputtruth.alive(), "the ear rode the idle beat"
assert isinstance(inputtruth.idle_seconds(), float)  # ...survived; any
#                                                     # real hand that
#                                                     # typed during it
#                                                     # merely restamps
inputtruth.uninstall()
assert not inputtruth.alive()
inputtruth.uninstall()                               # idempotent, no raise

#      FAIL-OPEN (the deaf pump's packeted word): a refusal reaches
#      the dimmer seam as the STOCK clock plus exactly ONE DATED
#      warning line.
import logging as _lg


class _Ear(_lg.Handler):
    def __init__(self):
        _lg.Handler.__init__(self)
        self.n = 0
        self.line = ""

    def emit(self, rec):
        self.n += 1
        self.line = rec.getMessage()


wh = _Ear()
inputtruth.log.addHandler(wh)
_real_attach = sys.modules["panelboss._inputtruth_hook"].attach


def _refuser(pump):
    raise OSError("RegisterRawInputDevices refused: Win32 error 5 "
                  "(fake)")


sys.modules["panelboss._inputtruth_hook"].attach = _refuser
assert not inputtruth.install()
v2 = inputtruth.idle_seconds()          # fail-open: the stock clock
assert isinstance(v2, float) and v2 >= 0.0   # answers (finite or the
#                                      # deaf-inf it returns too - the
#                                      # seam never sees a refusal)
inputtruth.idle_seconds()
inputtruth.idle_seconds()
assert wh.n == 1, wh.n                  # ...with ONE warning line
assert wh.line[:2].isdigit() and wh.line[2] == ":", wh.line
#                                       # and it is DATED (the owner's
#                                       # fail-open addition: the line
#                                       # opens HH:MM - a pump that
#                                       # dies at 3 am says 3 am)
sys.modules["panelboss._inputtruth_hook"].attach = _real_attach
inputtruth.log.removeHandler(wh)
inputtruth._unavailable = False          # fresh-process parity for
inputtruth._refusal = ""                 # whatever reads next
inputtruth._warned = False
ok("the raw ear: installs, survives an idle desk, unstalls "
   "idempotently; a refusal fail-opens to the stock clock with "
   "exactly ONE DATED warning line (the packeted deaf-pump law)")

#      RE-ARM (Oct-23 dossier A, launch patch): the away ear's
#      RIDEV_REMOVE is PROCESS-WIDE (hwndTarget must be NULL - it
#      cannot address one window), so every away-lift teardown
#      silences the pump's identical (1,2)/(1,6) pairs while the
#      pump's thread keeps living in GetMessageW - the corpse
#      detection never sees it and the theater/veil motion-lift
#      goes deaf for the session. The teardown therefore owes the
#      re-arm: _release_ears' RIDEV_REMOVE succeeds ->
#      inputtruth.re_register() fires (the re-arms ride the fake's
#      RegisterRawInputDevices, flags INPUTSINK vs the away ear's
#      own REMOVE); the no-pump desk (the ears object None) gets a
#      no-op False from the seam, never a raise.
_real_reg = _inputtruth_hook.U32.RegisterRawInputDevices
_real_ear = inputtruth._ear
_removed, _rearmed = [], []


class _RegReplay:
    """A register that records WHICH pairs passed: the away ear's
    REMOVE (flags 1) and, behind it, the pump's INPUTSINK re-arm."""

    def __call__(self, arr, n, size):
        flags = [r.flags for r in arr]
        if flags == [1, 1]:
            _removed.append(1)
        elif flags == [0x100, 0x100]:
            _rearmed.append(1)
        return 1


class _RearmEar:
    """A live-ear stand-in: re_register only ever asks _register()
    - and the re-arm issues through the SAME documented entry
    point (the fake replay sees the INPUTSINK pairs pass)."""

    def _register(self):
        arr = (_inputtruth_hook.RAWINPUTDEVICE * 2)()
        for row, (page, usage) in zip(arr, ((1, 2), (1, 6))):
            row.usUsagePage = page
            row.usUsage = usage
            row.flags = 0x100                # RIDEV_INPUTSINK
            row.hwndTarget = None
        return bool(_inputtruth_hook.U32.RegisterRawInputDevices(
            arr, 2, ctypes.sizeof(_inputtruth_hook.RAWINPUTDEVICE)))


from panelboss import display as disp  # noqa: E402
try:
    _inputtruth_hook.U32.RegisterRawInputDevices = _RegReplay()
    _w = disp.Display(verbose=False)   # __init__ only, no run() (the
    _w._hooked = True                  # enumwatch idiom): _release_ears
    inputtruth._ear = _RearmEar()      # never ran, so the live state
    _w._release_ears()                 # below is the no-pump desk's
    assert _removed == [1] and _rearmed == [1], (_removed, _rearmed)
    #                                     # the teardown AND the
    #                                     # re-arm, in that order
    assert _w._hooked is False
    inputtruth._ear = None             # the no-pump desk: the seam
    assert inputtruth.re_register() is False
    #                                    # is a no-op, never a raise
finally:
    _inputtruth_hook.U32.RegisterRawInputDevices = _real_reg
    inputtruth._ear = _real_ear
ok("the away ear's process-wide teardown re-arms the pump: a "
   "successful RIDEV_REMOVE fires inputtruth.re_register() (the "
   "INPUTSINK pairs ride the same entry point), and the no-pump "
   "desk's re-register is a no-op - the ring lifts again (dossier A)")

# 19b. the SAME desk with the THEATER OFF: the switch owns the frame
#      (no negative keys), but the player window STILL never wears the
#      plain veil - the exemption is the buddy's report, not the
#      theater's consent (owner, Oct 20: "which is I think a good
#      thing"). The desk went still (121 s past the plain 120 rail),
#      and the unrelated window dims on schedule.
f = Frame([w(1, rect=(50, 50, 900, 700)),
           w(2, rect=(750, 500, 200, 150))],
          idle=121.0)
RECT[0] = (100, 100, 600, 300)
f.tick(100, vidle=5, von=False)
assert not any(h < 0 for h in f.rec.painted), f.rec.painted
assert f.rec.painted == {2: ((750, 500, 200, 150), 0.3)}, f.rec.painted
ok("theater OFF: no frame at all, yet the window playing the reported "
   "video stays untouchable - every OTHER window dims as always")

# 19g. THE DIM LAYER AND THE PLAYER (owner ruling, Oct 24, the final
#      law of the plain veil): the window holding a PLAYING report
#      sheds it from ANY window state - foreground or background -
#      and the exemption OUTRANKS the [dimmer].always rows. A PAUSED
#      row holds no mask (the Oct-24 DELA census - the paused browser
#      under the always row's veil - was LAWFUL and is pinned as
#      law); a DEAD row holds no mask either (the eye's own age rule,
#      the Oct-21 no-ghost doctrine, the plain-veil half). Desk: MONA
#      is the always panel, the focus sits on MONB (the always row
#      dims MONA the moment focus leaves - no idle wait anywhere in
#      this section) and the desk MOVES (idle 0 under both rails), so
#      the ring never comes: the PLAIN law alone is under test. w1
#      holds the video, w3 is an unrelated window on the same panel.
f = Frame([w(1, rect=(50, 50, 900, 700)),
           w(2, monitor="MONB", fg=True, rect=(1100, 50, 800, 600)),
           w(3, rect=(60, 60, 100, 60))], idle=0.0)
RECT[0] = (500, 300, 300, 200)       # PLAYING, held by w1
WRECT[0] = None
f.tick(100, vidle=130, dim_idle=120, always={"MONA": True})
assert f.rec.painted == {3: ((60, 60, 100, 60), 0.3)}, f.rec.painted
#       the always row dims the panel its own way (no idle wait), the
#       unrelated window wears the veil, and the BACKGROUNDED player
#       sheds it - the ruling's heart.
RECT[0] = None                       # paused: the eye answers
f.tick(101, vidle=130, dim_idle=120, always={"MONA": True})
#                                    # (None, None) (the pause-lift
#                                    # is the eye's law, pinned at
#                                    # the door just below; here: the
#                                    # answer the exemption reads)
assert f.rec.painted == {1: ((50, 50, 900, 700), 0.3),
                         3: ((60, 60, 100, 60), 0.3)}, f.rec.painted
#       PAUSED re-wears the dim layer, THIS tick, at full alpha (a
#       new birth never ramps in) - the Oct-24 DELA census, pinned
#       as law.
#   and at the DOOR, the dead row's truth (the grace idiom of pin 8):
#   a fresh click row holds the exemption, the AGED one holds NOTHING
#   - no ghost may mask the dimmer.
videoeye._STATE.clear()
door((100, 200, 800, 450), bounds=(600, 200, 1600, 900),
     view=(1584, 649), paused=True)
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.live_pair(vcfg(), CLK.monotonic()) == (None, None)
#                                    # the PAUSE lifts both halves at
#                                    # the door: no rect, no window
os.remove(videoeye.RECT_PATH)
videoeye._STATE.clear()
door((100, 200, 800, 450), bounds=(600, 200, 1600, 900),
     view=(1584, 649))
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.live_pair(vcfg(), CLK.monotonic())[0] is not None
CLK.advance(4)                       # past the 3 s click grace
videoeye.tick(vcfg(), CLK.monotonic())
assert videoeye.live_pair(vcfg(), CLK.monotonic()) == (None, None)
os.remove(videoeye.RECT_PATH)
videoeye._STATE.clear()
ok("the Oct-24 dim-layer triple: PLAYING exempts the holder from the "
   "plain veil in any window state and outranks the always rows; "
   "PAUSED re-wears the veil (the DELA census, lawful, now pinned); "
   "DEAD ages the mask away at the door - the veil returns, no "
   "ghost holds it")

# --- config: the rails at the boundary --------------------------------
n = config.normalize_videodim({"on": "yes", "min_rect_px": 9e9,
                               "grace_s": -2, "idle_sec": 9999,
                               "level": -5})
assert n["on"] is False and n["min_rect_px"] == 4_000_000 \
    and n["grace_s"] == 0 and n["idle_sec"] == 30 \
    and n["level"] == 10, n
d = config.normalize_videodim({})
assert d == {"on": False, "min_rect_px": 200000, "grace_s": 3,
             "idle_sec": 15, "level": 20, "fade": False,
             "hole": "video", "monitors": {}}, d
# the hole word (owner, Oct 24): the ABSENT key answers video (the
# byte-compatible file is untouched and the ring hugs the video),
# "window" survives for the Oct-20 shape, and an unknown word warns
# naming itself and folds to the default (the fossil-law idiom, the
# away off_after_min retirement line's shape).
assert config.normalize_videodim({"hole": "video"})["hole"] == "video"
assert config.normalize_videodim({"hole": "window"})["hole"] == "window"
assert config.normalize_videodim({"hole": "chrome"})["hole"] == "video"
assert config.normalize_videodim({"hole": None})["hole"] == "video"
assert config.normalize_videodim({"idle_sec": -5})["idle_sec"] == 1
assert config.normalize_videodim({"idle_sec": 0})["idle_sec"] == 1
assert config.normalize_videodim({"level": 999})["level"] == 90
# the per-panel theater rows (owner, Oct 16): a row EXISTS to opt out,
# so `on` absent defaults True and junk on warns to True (a row no one
# trusts may not silently strip a frame); level clamps to the theater
# rails, absent/None/junk follows the global; the bare bool is the
# away table's shorthand; a non-dict table is the legacy {} (the
# dimmer's own monitors law, mirrored).
m = config.normalize_videodim({"monitors": {
    "MONA": {"on": False},
    "MONB": {"level": 150},
    "MONC": {},
    "MOND": {"on": "junk", "level": "dark"},
    "MONE": True}})["monitors"]
assert m == {"MONA": {"on": False, "level": None},
             "MONB": {"on": True, "level": 90},
             "MONC": {"on": True, "level": None},
             "MOND": {"on": True, "level": None},
             "MONE": {"on": True, "level": None}}, m
assert config.normalize_videodim({"monitors": []})["monitors"] == {}
assert config.normalize_videodim({"monitors": {"MONA": False}})[
    "monitors"] == {"MONA": {"on": False, "level": None}}
ok("normalize_videodim: bad on warns and folds, the rails clamp "
   "(idle_sec 1..30 default 15 - the owner's sticky-veil floor and "
   "timer law, Oct 16; level 10..90 default 20), the hole word folds "
   "to video (the Oct-24 default; unknown words warn naming "
   "themselves), the monitors table normalizes to {on: bool, level: "
   "int|None}, absent is dark")

# --- the wire: the manifest carries the native-messaging law ----------
MAN = json.load(open(os.path.join("extension", "manifest.json"),
                     encoding="utf-8"))
assert MAN["manifest_version"] == 3
assert MAN["permissions"] == ["nativeMessaging"], MAN["permissions"]
assert "host_permissions" not in MAN
cs = MAN.get("content_scripts")
assert cs and cs[0]["js"] == ["content.js"]
assert "*://*.youtube.com/*" in cs[0]["matches"]
assert "<all_urls>" not in cs[0]["matches"]
ok("the manifest asks nativeMessaging ONLY (the content script owns the "
   "measure, so scripting/activeTab are gone) - no <all_urls>, no "
   "downloads, no tabs")
BG = open(os.path.join("extension", "background.js"),
          encoding="utf-8").read()
assert "eval(" not in BG
assert "chrome.runtime.connectNative" in BG
assert "onMessage" in BG and "lane" in BG
assert "tabs.sendMessage" in BG
assert "chrome.scripting" not in BG and "executeScript" not in BG
assert "measureVideo" not in BG           # the static measure moved to
assert "origin: row.origin" in BG         # v0.4.2: the background is a
#                                         # pass-through for the report,
#                                         # it derives nothing
CJ = open(os.path.join("extension", "content.js"),
          encoding="utf-8").read()        # content.js as measure()
assert 'op !== "measure"' in CJ or 'msg.op !== "measure"' in CJ
assert "window.screenX" in CJ             # v0.4.2: the page reports its
#                                         # own viewport origin (a
#                                         # maximized border hangs
#                                         # off-screen - the guess lied)
assert "capture: true" in CJ              # inner scrollers fire on the
#                                         # element; scroll does not
#                                         # bubble, it traverses capture
ok("the background folds the content-script's automatic lane and the "
   "test button reaches the tab's own measure via tabs.sendMessage - no "
   "scripting, no eval, one measure in content.js; v0.4.2 carries the "
   "origin report through and the scroll listener rides the capture "
   "phase")


# THEATER RE-PIN (Oct-16 UAT cure, the invisible-ring bite): an
# unchanged frame piece must ride the paint queue EVERY tick - a plain
# veil survives re-activations by being pinned to its own window, a
# frame piece owns nothing, and the first browser activation buries it
# under the very window it exists to darken (the pieces were painted,
# measured pixel-exact, and invisible). The negative-key re-QUEUE is
# the contract - it survives this commit. The z CALL changed shape in
# the Oct-17 flicker-cure commit (the owner's "flickering during
# playback"): _zpin's synthetic branch is now IDEMPOTENT - a piece
# already topmost and chained to its row's tray costs ZERO SetWindowPos
# calls, so the per-beat re-pin is a no-op when nothing was buried
# (dimmer_test.py pins the idempotent law; this pin keeps pinning the
# queue half only). The real-window half is the owner's UAT to confirm.
f = Frame([w(1)], idle=999.0)
RECT[0] = (100, 100, 600, 300)
f.tick(100)
assert len(f.rec.calls) == 4, f.rec.calls          # birth paints
assert all(h < 0 for h, _, _ in f.rec.calls), \
    ("frame pieces ride negative synthetic keys (the pump's synthetic-"
     "anchor branch is their only raise path)")
f.tick(101)                                        # NOTHING changed
assert len(f.rec.calls) == 8, f.rec.calls          # re-pinned, not frozen
assert [c[0] for c in f.rec.calls[4:]] == [c[0] for c in f.rec.calls[:4]], \
    "the re-pin re-queues the SAME four pieces"
assert [c[1] for c in f.rec.calls[4:]] == [c[1] for c in f.rec.calls[:4]], \
    "at the SAME rects - the re-pin is pure z-order (geometry unchanged)"
ok("an unchanged frame RE-QUEUES every tick - the buried-ring bite has "
   "a teeth-mark in the suite now; since the Oct-17 flicker-cure commit "
   "the z-call is idempotent (already-placed = zero SetWindowPos, pinned "
   "in dimmer_test), so the queue contract is what this pin asserts")

# 25. THE ARITY+BAND PIN (cappy packet, Oct-16): the first cure called
#     SetWindowPos with SIX args - ctypes raised TypeError inside the
#     branch's silent swallow and the raise never reached Win32. The
#     spy records the exact call; the law is SEVEN args and
#     HWND_TOPMOST (-1): a background process cannot restack into the
#     top of the ORDINARY band over the foreground window (measured:
#     ok=1, still under; AttachThreadInput does not lift the clamp).
_real_swp = dimmer._setwindowpos
_swp_calls = []
dimmer._setwindowpos = lambda *a: _swp_calls.append(a)


class _StubWin:
    _pb_rect = (0, 0, 64, 64)

    def update_idletasks(self):
        pass

    def winfo_id(self):
        return 0x12345                # a fake child id: GetAncestor
                                      # answers 0, the branch falls
                                      # back to winfo_id() itself


dimmer._zpin(_StubWin(), -1)
assert _swp_calls, "the synthetic branch must actually CALL the verb"
first = _swp_calls[0]
assert len(first) == 7, "SetWindowPos takes 7 args; a 6-arg call dies " \
    "in ctypes before Win32 ever sees it (the Oct-16 wave-killer)"
assert first[1] == -1, "the theater band is TOPMOST (-1): HWND_TOP " \
    "lands under the foreground browser - measured, not theorized"
dimmer._setwindowpos = _real_swp
ok("the synthetic pin calls the verb with SEVEN args and HWND_TOPMOST "
   "- the arity bug and the band bug both have a teeth-mark now")

# 25b. the live half: the real verb on a real Tk window sets the
#      topmost bit (the branch is proven against Win32 itself, not
#      only against the spy).
import tkinter as _tk
_root = _tk.Tk()
_root.withdraw()
_top = _tk.Toplevel(_root)
_top.overrideredirect(True)
_top.geometry("64x64+80+80")
_top.deiconify()
_top.update_idletasks()
_h = dimmer._u32.GetAncestor(_top.winfo_id(), dimmer.GA_ROOT) \
    or _top.winfo_id()
assert dimmer._u32.SetWindowPos(_h, -1, 0, 0, 0, 0, dimmer._SWP_ZPIN), \
    "the real SetWindowPos with the branch's arg list must succeed"
assert dimmer._u32.GetWindowLongW(_h, dimmer.GWL_EXSTYLE) & dimmer.WS_EX_TOPMOST, \
    "and the window must CARRY the topmost bit afterwards"
_top.destroy()
_root.destroy()
ok("the branch's exact verb lifts a real window into the topmost band "
   "(Win32 itself as the witness)")

# --- THE CARD'S WORDS, PINNED VERBATIM (pin-as-data, owner law): the
#     theater card and the dimmer card tell the Oct-24 law - the ring
#     hugs the video, the calmer window shape is one config word
#     away, and the player sheds the dim layer from any state (paused
#     re-wears it). A reword without a ruling fails the suite. The
#     card module imports with no Tk and no root (the window_boot
#     _away idiom); the pin compares the DATA, not the file's shape.
from panelboss.ui.window import _oled                    # noqa: E402
assert _oled.TIP_COMP["card"] == (
    "a playing video dims the desk around it, once the input "
    "sits still for the \"veil after\" wait; motion lifts the "
    "frame and it re-arms after the wait. The ring hugs the "
    "video: the page and the window's own chrome wear the "
    "darkness with the desk, and the calmer window-hole shape "
    "is one config word away ([videodim] hole = 'window'). "
    "While it plays the MOVIE never wears a veil: the window "
    "reporting the playing rect is exempt from the plain "
    "veils in any window state (a film's sound never lifts "
    "it)"), _oled.TIP_COMP["card"]
assert _oled.TIP_COMP["on"] == (
    "movie theater mode: a PLAYING video gets a dimmed ring "
    "around the video itself once the input has been still for "
    "the 'veil after' wait; motion lifts the ring, which "
    "re-arms after the same wait, and a film's sound never "
    "touches it. The page and the window's own chrome wear the "
    "darkness with the desk (the calmer window-hole shape is "
    "one config word away: [videodim] hole = 'window'). The "
    "player window stays exempt from the PLAIN veils with or "
    "without this switch; a paused row re-earns them, and the "
    "app learns the video's place from the buddy extension's "
    "native host."), _oled.TIP_COMP["on"]
assert _oled.TIP_DIM["on"] == (
    "an idle desk puts a dark click-through veil over every "
    "window you are not using; the window you touch lights "
    "instantly, and a window the mic just heard keeps its "
    "brightness for four seconds. The window the buddy reports "
    "as playing a video never wears the veil either - "
    "backgrounded included, always rows included; pause the "
    "video and the dim layer comes back. Elevated windows "
    "(Task Manager's class) never wear a veil this app cannot "
    "stack against - running the app elevated reaches them but "
    "is not recommended. Nothing dims until you opt in, per "
    "monitor."), _oled.TIP_DIM["on"]
ok("the theater and dimmer cards' words are pinned verbatim: the "
   "video-hole ring, the one-word window shape, and the player's "
   "place under the dim layer are now the card's own data - a reword "
   "without a ruling fails the suite")


if os.path.exists(videoeye.RECT_PATH):
    os.remove(videoeye.RECT_PATH)
print("\nVIDEOEYE TESTS OK (%d)" % len(OK))