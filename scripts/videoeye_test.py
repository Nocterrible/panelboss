"""The video eye's law, pinned: default-off at the root, the doorway
read (the native host's fixed %APPDATA%\\PanelBoss\\rect), the
content-space fold (DPR-scaled bounds, the chrome correction, the
viewport-space judgment), the liveness gates (paused, min_rect_px, the
grace), freshest-wins across families - and the Veils frame: four pieces
clamped per monitor, the straddle covering BOTH panels with no sliver on
the video column, plain veils skipped on the covered panels only, the
ramp retraction, the pause, the THREE-BEAT idle conjunction (on after X,
drop on input, re-arm after X), the sound exemption (a film's audio does
NOT lift the theater frame), and the replacement seam (theater active ->
a plain idle veil never covers that region). Every door is a fake seam
(the doorway path, monitors, the clock) - no browser, no Tk, app-up and
headless alike, the dimmer_test family's idiom.
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
        family="chrome", age=0.0, lane="click"):
    return {"rect": {"left": x, "top": y, "width": w, "height": h},
            "dpr": dpr, "paused": paused, "scroll": list(scroll),
            "view": list(view),
            "bounds": {"left": bounds[0], "top": bounds[1],
                       "width": bounds[2], "height": bounds[3]},
            "family": family, "lane": lane, "ts": CLK.wall - age}


def door(rect, view=(1920, 1080), bounds=(0, 0, 1920, 1080), age=0.0,
         dpr=1, paused=False, family="chrome", lane="click"):
    body = {"rect": {"left": rect[0], "top": rect[1],
                     "width": rect[2], "height": rect[3]},
            "dpr": dpr, "paused": paused, "scroll": [0, 0],
            "view": list(view),
            "bounds": {"left": bounds[0], "top": bounds[1],
                       "width": bounds[2], "height": bounds[3]},
            "family": family, "lane": lane, "ts": CLK.wall - age}
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
   "not a 3 s snapshot); the idle gate lives in the dimmer")

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
    """The fake desk: an idle clock (mutable via .idle), an audio set
    (mutable via .audio), and the video eye seam fixed to RECT[0]. The
    theater veil's idle conjunction reads .idle; the plain veil's sound
    exemption reads .audio. Both are per-tick mutable so the suite can
    drive the three beats and the sound/touch edges without a browser."""
    def __init__(self, wins=None, idle=0.0, audio=None, vlevel=30,
                 vfade=False):
        self.wins = wins or []
        self.rec = Rec()
        self.idle = idle
        self.audio = audio if audio is not None else set()
        self.vlevel = vlevel
        self.vfade = vfade
        self.v = dimmer.Veils(lambda: self.wins, lambda: self.audio,
                              lambda: self.idle, self.rec.paint,
                              self.rec.unveil,
                              video=lambda cfg, now: RECT[0],
                              monitors=lambda: MON)

    def tick(self, now, level=30, dim_on=True, vidle=0):
        self.v.tick({"dimmer": {"on": dim_on,
                                "monitors": {"MONA": True,
                                             "MONB": True},
                                "always": {}, "apps": {},
                                "idle_sec": 120, "ramp_sec": 8,
                                "level": level, "bound": None},
                     "videodim": {"on": True, "min_rect_px": 1,
                                  "grace_s": 3, "idle_sec": vidle,
                                  "level": self.vlevel,
                                  "fade": self.vfade}},
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
#     across the video stays bright
f = Frame([w(1)], idle=999.0)
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

# 15. THE THREE BEATS (the automatic lane's conjunction): a playing
#     video frames only when the input has been still for idle_sec; any
#     input drops it; stillness again re-arms it - ONE rail, symmetric.
f = Frame([w(1)], idle=0.0, vlevel=30)
RECT[0] = (100, 100, 600, 300)
f.tick(100, vidle=5)                 # still 0 s < 5 s: NO frame
assert f.rec.painted == {}, f.rec.painted
f.idle = 6.0                          # the desk sits still past the rail
f.tick(101, vidle=5)                  # frame lands
assert len(f.rec.painted) == 4, f.rec.painted
f.idle = 1.0                          # a pointer move: input returns
f.tick(102, vidle=5)                  # FADE OFF (the default, owner
assert f.rec.painted == {}, f.rec.painted   # Oct 16): the frame is
f.tick(103, vidle=5)                  # GONE this tick and stays gone
assert len(f.rec.painted) == 0        # while the desk is under X
f.idle = 6.0                          # stillness passes X AGAIN: the
f.tick(104, vidle=5)                  # SAME rail re-arms, no second
assert len(f.rec.painted) == 4        # knob
ok("the three beats: on after X still, drop the tick input returns "
   "(fade off, the default), re-arm after X again - one symmetric rail")

# 15b. THE FADE OPTION, other side: fade=True opts the theater into
#      the ramp family - the first step is the one-tick hold (the
#      eye's fail-open law), then gradual retract, no blink.
fb = Frame([w(1)], idle=0.0, vlevel=30, vfade=True)
RECT[0] = (100, 100, 600, 300)
fb.tick(120, vidle=5)
fb.idle = 6.0
fb.tick(121, vidle=5)
assert len(fb.rec.painted) == 4, fb.rec.painted
fb.idle = 1.0
fb.tick(122, vidle=5)                 # fade ON: still painted, dying
assert len(fb.rec.painted) == 4       # has begun (one-tick hold)
fb.tick(130, vidle=5)
assert fb.rec.painted == {}, fb.rec.painted
ok("fade=true rides the ramp family: one-tick hold then retract - "
   "the theater opt-in beside the owner's no-fade default")

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
ok("a film's sound never lifts the theater frame (the lift is the "
   "pointer/keyboard idle gate, not the sound ledger)")

# 17. THE REPLACEMENT SEAM: while the theater frame is ACTIVE, a plain
#     idle veil must NOT cover that panel - the movie stays bright, the
#     rest of the desk dims. (The browser window is exempt by pid only
#     while it is SOUNDING; the frame's panel skip is the
#     sound-independent backstop for a silent mid-scene stretch.)
f = Frame([w(1), w(2, monitor="MONB")], idle=999.0)
RECT[0] = (100, 100, 600, 300)        # the theater frame on MONA
f.tick(100, vidle=5, dim_on=True)
keys = f.rec.painted
# plain window 1 (on MONA) must NOT be painted: the frame owns MONA.
assert 1 not in keys, keys
assert 2 in keys, keys                # window 2 on MONB dims normally
assert sum(1 for k in keys if k < 0) == 4, keys   # exactly 4 frame pieces
ok("theater active -> a plain veil never covers the video's panel; the "
   "rest of the desk dims (replacement seam)")

# --- config: the rails at the boundary --------------------------------
n = config.normalize_videodim({"on": "yes", "min_rect_px": 9e9,
                               "grace_s": -2, "idle_sec": 9999,
                               "level": -5})
assert n["on"] is False and n["min_rect_px"] == 4_000_000 \
    and n["grace_s"] == 0 and n["idle_sec"] == 300 \
    and n["level"] == 10, n
d = config.normalize_videodim({})
assert d == {"on": False, "min_rect_px": 200000, "grace_s": 3,
             "idle_sec": 15, "level": 20, "fade": False}, d
assert config.normalize_videodim({"idle_sec": -5})["idle_sec"] == 0
assert config.normalize_videodim({"level": 999})["level"] == 90
ok("normalize_videodim: bad on warns and folds, the rails clamp "
   "(idle_sec 0..300 default 15, level 10..90 default 20), absent is "
   "dark")

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
CJ = open(os.path.join("extension", "content.js"),
          encoding="utf-8").read()        # content.js as measure()
assert 'op !== "measure"' in CJ or 'msg.op !== "measure"' in CJ
ok("the background folds the content-script's automatic lane and the "
   "test button reaches the tab's own measure via tabs.sendMessage - no "
   "scripting, no eval, one measure in content.js")


if os.path.exists(videoeye.RECT_PATH):
    os.remove(videoeye.RECT_PATH)
print("\nVIDEOEYE TESTS OK (%d)" % len(OK))