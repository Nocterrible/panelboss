"""Background dimming: the idle desk puts dark veils on the windows
you are not using.

The law, from the owner's Oct-15 rulings: when [dimmer] is on and at
least one monitor row opted in and input has been still past
idle_sec, EVERY visible top-level window on an opted monitor gets its
own click-through dark veil - except the DESKTOP ITSELF (the
Progman/WorkerW shell views carry the wallpaper; a uniform veil over
them veils the wall, which is the "darkening the whole screen"
reading, Oct 15 UAT), the foreground window (touched = instantly
un-veiled, next tick), zero-size, iconic, DWM-cloaked, this app's
OWN OVERLAYS (the skip is TOOLWINDOW-scoped since the same UAT: our
strips/veils/covers are overrideredirect toplevels and carry the bit,
the settings window does not and dims like any background window -
"doesn't work on panelboss settings window itself", owner), exes the
user put on [dimmer.apps], and every process the WASAPI sensor says
is AUDIBLE right now (a window that started making sound un-dims the
tick the sensor learns it; one that went quiet keeps its exemption
for SETTLE_SEC - the API drops a stopped session from the enumeration
at once, the settle lives HERE). Input returns and the whole set
fades out within ramp_sec in at most THREE alpha steps: a dimmer
that blinks off is a screensaver. The card's idle rail also reaches
ZERO (Oct-15 UAT, the ramp's floor law). The card's pause switch and
the bound hotkey pause the same way: a fade, not a blink, and the
field comes back the tick the pause lifts.
An [dimmer.always] row is a SUB-MODE of the opt-in, not a bypass:
that panel dims without waiting for idle_sec, but it bows to the
foreground (its center inside the panel's rect un-dims the panel -
if the focused app is ON it, you are using it) and to the audible
exemption; an unattributable focus dims the always rows and
confesses once per transition. The veil LEVEL defaults to 20% (the
Oct-15 OLED ruling: 45 was aggressive) and the RAMP rail reaches 0,
where the drop is immediate - the fade arithmetic guards that case
by name, not by luck.

Geometry is DWMWA_EXTENDED_FRAME_BOUNDS (13), not GetWindowRect:
measured today, the GDI rect lies by eight pixels around every
rounded window, and a veil cut to the GDI rect visibly overhangs the
corners. Cloak is attribute (14), pinned here from the SDK, same
eyes wm/_inspect uses.

The veil windows are ordinary Tk toplevels with WS_EX_TRANSPARENT |
WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW on the root ancestor, painted on
a private interpreter that obeys the birth-order law
(hider.wait_for_window() BEFORE its tk.Tk - the lesson that froze
this morning's blackout). Ordinary windows die with the process: a
crash unpaints by construction, and teardown is the orderly half.
The painter's pump wraps EVERY item: a paint for a destroyed hwnd
raises inside Tk, and an escaped raise left that veil alive, dark
and un-clickable over a dead app (Oct-15 UAT, the random darker
box). On a raise the window is dropped and destroyed, and the pump
keeps draining - the jog pump's lesson, matched. Layering is a Z-
PIN, not topmost (gate finding 1): every paint SetWindowPos's the
veil immediately above its OWN window - against the target's
GW_HWNDPREV neighbour (the next-ABOVE window; GW_HWNDNEXT walks the
order DOWN and was measured painting the veil under its owner,
nailing nothing), band-matched so a topmost owner still gets
a topmost veil. Topmost was the bug: every veil lived in the
topmost band above every non-topmost window, so overlapping
backgrounds STACKED their alphas (45, 69.75, 83.4 percent at one,
two, three veils) - the seam the containment ledger used to
suppress at birth. With the pin each veil sits in its owner's
stratum and stacking is arithmetic-impossible, so the ledger
(_covered/_ledged_birth/_reclaim) is retired whole. A refused pin
(UIPI-elevated target, vanished anchor) is a cosmetic one-tick
miss: skip, never straggle.

THE HOTKEY LAW (owner): unbound by DEFAULT - no stolen chord before
consent. The card captures a press and stores [mods, vk]; THIS module
decides the re-arm from the tick when the stored word changes, but
the VERB is a note on the display watcher's pump queue (the Oct-15
1408 law, measured: RegisterHotKey from a foreign thread is refused
with ERROR_INVALID_HOTKEY_WINDOW for a window it does not own, and a
wrong-thread unregister leaks the registration in the owning queue -
the registering thread must pump the queue the WM_HOTKEY posts to,
the broadcast lesson's twin). The note carries (op, mods, vk); the
pump applies it against its own window and the answer (ok, errno)
rides back on the note's event (the _ear_req idiom, ridden not
re-invented). A taken combo answers the card's say row with the
dated word and keeps the OLD binding; binding while headless answers
a word too, never a silent lie. Since the Oct-15 instrumentation the
say row is EVIDENCE, not a verdict: every attempt logs the stored
word, the registered mods, the vk and the pump hwnd in hex, and a
refusal that is not ERROR_HOTKEY_ALREADY_REGISTERED says its number,
not "taken" - the one word was swallowing 87s and 1400s into a lie
about a chord that was never actually taken. One press pauses, one
resumes (toggle, not hold).

SIZE LAW: the file runs ~900 (the Oct-15 video mode grew it ~100 -
the frame is the Veils qualification the docstring above the FSM
promised, and the mode shares the paint loop, the ramp, and the
drop table: splitting Veils now would fork the qualification by
half) and the seam is real, not cosmetic -
Veils (the FSM, ~180) and the stratum below it (census + pins,
painter, hotkey arm) are already three files wearing one name; when
the veil set needs card-side state, the stratum moves out as
_dimwin.py and the seam opens on its own. The pinning table is
atomic (the shared-windll lesson) and the test drives the FSM, the
painter pump (with a fake tkinter), AND the hotkey arm through
injected seams, so the whole module runs app-up and headless alike.
"""

import ctypes
import logging
import os
import queue
import threading
import time

log = logging.getLogger("dimmer")

SETTLE_SEC = 4.0        # the audible exemption outlives the session by
                        # this much: the enumeration answers only the
                        # ACTIVE set, and a song between two samples
                        # must not strobe the veil

DWMWA_EXTENDED_FRAME_BOUNDS = 13
DWMWA_CLOAKED = 14
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x20
WS_EX_TOOLWINDOW = 0x80
WS_EX_NOACTIVATE = 0x08000000
GA_ROOT = 2
GW_HWNDNEXT = 2
WS_EX_TOPMOST = 0x8
# The next-ABOVE anchor is GW_HWNDPREV (3), not the packet's
# GW_HWNDNEXT (2): the docs' "next in the Z order" walks TOP toward
# BOTTOM (EnumWindows' own top-down order is the same convention),
# and the GetPixel probe of Oct-15 measured the NEXT-shaped pin
# painting the veil UNDER its target (no dim at all on a gray base).
GW_HWNDPREV = 3
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_FADE_LEVELS = (1.0, 2.0 / 3.0, 1.0 / 3.0)   # THREE steps, then gone
_SWP_ZPIN = 0x213   # NOSIZE | NOMOVE | NOACTIVATE | NOOWNERZORDER: a
                   # z-move that moves nothing, touches nothing else
# Warn-once for the pin's swallow (Oct-16, cappy): the TypeError that
# hid a dead theater cure for a whole wave died SILENT inside _zpin's
# except - a refused band law is cosmetic, but it must confess ONCE.
# ONE FLAG PER BRANCH (gate finding 1): a benign plain-anchor dead-
# window race must never re-silence the theater branch's confession.
_PIN_WARNED = [False]
_PIN_WARNED_PLAIN = [False]
# The taskbar exclusion for theater pieces: primary + per-monitor tray
# classes; the pieces anchor UNDER the tray occupying their own
# monitor row so the desk's chrome is never darkened (cappy packet).
_TRAY_CLASSES = ("Shell_TrayWnd", "Shell_SecondaryTrayWnd")
_TRAY_CACHE = {"until": 0.0, "rows": []}   # rows: [(hwnd, left, right)]

_u32 = ctypes.WinDLL("user32", use_last_error=True)   # the pin law is
_u32.SetWindowLongW.restype = ctypes.c_long            # self-pinned
_u32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int,        # from
                                ctypes.c_long]                         # birth
_u32.GetWindowLongW.restype = ctypes.c_long
_u32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
_u32.GetAncestor.restype = ctypes.c_void_p
_u32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
_u32.IsWindowVisible.restype = ctypes.c_int
_u32.IsWindowVisible.argtypes = [ctypes.c_void_p]
_u32.IsIconic.restype = ctypes.c_int
_u32.IsIconic.argtypes = [ctypes.c_void_p]
_u32.GetWindowThreadProcessId.restype = ctypes.c_uint
_u32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p,
                                          ctypes.POINTER(ctypes.c_uint)]
_u32.GetForegroundWindow.restype = ctypes.c_void_p
_u32.GetForegroundWindow.argtypes = []
_u32.EnumWindows.restype = ctypes.c_int
_u32.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_long]
# the veil-qualification lookup: restype/argtypes land at the import
# block like every other user32 verb here - an unpinned lookup is the
# class of bug that froze this morning's blackout (GetCursorPos),
# we do not repeat it
_u32.GetClassNameW.restype = ctypes.c_int
_u32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
_u32.GetWindowRect.restype = ctypes.c_int
_u32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_u32.IsWindow.restype = ctypes.c_int        # the z-pin's guard: a dead
_u32.IsWindow.argtypes = [ctypes.c_void_p]  # anchor skips, it never raises
_u32.GetWindow.restype = ctypes.c_void_p
_u32.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
_u32.SetWindowPos.restype = ctypes.c_int
_u32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_uint]
# (the hotkey pair is NOT pinned here: since the Oct-15 1408 law the
# verbs belong to the display pump thread - display.py's own block
# pins them; this module leaves notes, see _request_hotkey)
_dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
_dwm.DwmGetWindowAttribute.restype = ctypes.c_long
_dwm.DwmGetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                       ctypes.c_void_p, ctypes.c_uint]
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenProcess.restype = ctypes.c_void_p
_k32.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_uint]
_k32.QueryFullProcessImageNameW.restype = ctypes.c_int
_k32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                            ctypes.c_wchar_p,
                                            ctypes.POINTER(ctypes.c_uint)]
_k32.CloseHandle.restype = ctypes.c_int
_k32.CloseHandle.argtypes = [ctypes.c_void_p]
_WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p,
                                  ctypes.c_long)

HOTKEY_ID = 0x5042                      # 'PB' - the app's only slot
MOD_NOREPEAT = 0x4000                   # autorepeat is not a press
ERROR_HOTKEY_ALREADY_REGISTERED = 1409  # the ONLY errno allowed to
                                        # say "taken" (Oct-15 UAT:
                                        # every refusal wore that one
                                        # word - the rest now wear
                                        # their number)

# the desktop's own shell views (Oct-15 UAT: the census kept them, so
# the dimmer veiled the WALLPAPER and the desk read as "the whole
# screen went dark"). This is a FACT about the desktop, not a config
# rule, so it filters in the census stratum - never in the Veils FSM,
# whose job is qualification by config.
DESKTOP_VIEWS = frozenset(("Progman", "WorkerW"))

# the patchable aliases the fakes lean on (the suite owns the desk
# here; the pins above stay the real verbs). The hotkey pair is a
# NOTE on the display pump since the Oct-15 1408 lesson (a
# cross-thread RegisterHotKey is refused for a foreign window, and a
# cross-thread unregister leaks the registration in the owning
# queue): the note carries (op, mods, vk) and the pump answers
# (ok, errno) - the alias IS the door the fakes stand in.
def _request_hotkey(op, mods=0, vk=0):
    from . import display
    return display.request_hotkey(op, mods, vk)
_iswindow = _u32.IsWindow
_getwindow = _u32.GetWindow
_setwindowpos = _u32.SetWindowPos


class _RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                ("r", ctypes.c_long), ("b", ctypes.c_long)]


class Veils:
    """Pure FSM (the Strips shape): windows() -> window facts
    (hwnd, pid, exe, cls, monitor, rect, cloaked, iconic, fg, tool),
    audio() -> the ACTIVE-pid set (silent empty on every sensor
    failure - never raises), idle() -> input-still seconds,
    paint(hwnd, rect, alpha) / unveil(hwnd). A census hiccup holds
    every veil at its last position: no tick, not a dead loop.
    Qualification is PER MONITOR since the Oct-15 always ruling:
    "dimming" is a set of active panel shorts, not one boolean -
    but the census-stays-shut law survives: it opens only when at
    least one panel is active.

    VIDEO MODE (Oct-15, the dim-around-the-playing-video ruling):
    the two optional seams, video(cfg, now) -> a LIVE physical rect
    or None (videoeye.video_rect is the shipped eye; the suite
    injects a fake) and monitors() -> panel rows. When the eye is
    live the veil set gains FOUR dark pieces (top/bottom/left/
    right) around the rect, clamped PER MONITOR, keyed by synthetic
    negative hwnds; the plain per-window veils are SKIPPED on the
    covered panels - the frame already darkens everything outside
    the hole there, and a window veil under the frame would stack
    its alpha (the stratum's own no-stacking law). The foreground
    gets NO exclusion on those panels: the browser's own chrome
    dims too - the hole is the rect, not the window. The frame's
    alpha is its OWN [videodim] level (the theater rail, default
    20 - NOT the idle dimmer's shared level; the Oct-16 replacement
    wave) and the fade/ramp rules apply unchanged; a gone rect
    rides the RAMP, not a blink. ADMITTED EDGE (the gate, Oct 16):
    'covered' is derived from EXISTING pieces - a video rect that
    COVERS ITS WHOLE PANEL draws no pieces (a panel-covering rect
    is none), so that panel is not covered and a plain veil can
    dim the movie itself once the panel qualifies. Geometry not
    changed for it (the case is a fullscreen player, which dims
    itself into blackness anyway); admitted here so the next
    reviewer reads the law, not a mystery."""

    def __init__(self, windows, audio, idle, paint, unveil,
                 video=None, monitors=None):
        self._windows, self._audio, self._idle = windows, audio, idle
        self._paint, self._unveil = paint, unveil
        self._video, self._mons = video, monitors or _monitors
        self._frames = {}      # (panel short, side) -> synthetic key
        self._live = {}        # hwnd -> {"rect", "alpha", "die":
        #                           None|t, "mon": panel short,
        #                           "frame": bool (video pieces)}
        self._exempt = {}      # pid -> last tick the sensor heard it
        self._fg_unattr = False  # the always rows' blind-focus
        #                        # confession rides TRANSITIONS

    def tick(self, cfg, now):
        d = cfg.get("dimmer") or {}
        vrect = self._live_rect(cfg, now)
        frame = self._frame_pieces(vrect)
        covered = {short for _, short in frame.values()}
        rows = d.get("monitors") or {}
        opted = {s for s, v in rows.items() if v}
        if (not d.get("on") or not opted) and not covered:
            # the [videodim] section is its OWN consent: a live
            # frame survives an off [dimmer] (it borrows the level
            # and the ramp rules, not the switch); with no frame
            # the old master gate stands untouched
            self.teardown()
            return
        # the predicate first: fading needs no fresh facts; birth does
        # - a fading tick leaves the census and the WASAPI walk in
        # their pockets. Per-monitor since the Oct-15 "always" ruling:
        # an always row dims WITHOUT the idle clock, for as long as
        # the foreground window is not sitting on it (the owner's own
        # words: "if the focused app or mouse isn't on that monitor",
        # attributed by the fg window's CENTER inside the monitor
        # rect). The foreground and audible exemptions still apply
        # INSIDE an always panel - only the idle wait is skipped -
        # and the pause clears the whole field, always rows included.
        idle_ok = (not _PAUSED
                   and self._idle() >= d.get("idle_sec", 120))
        always = {s for s, v in (d.get("always") or {}).items()
                  if v and s in opted}
        if idle_ok:
            self._fg_unattr = False
            dimming = set(opted)
        elif _PAUSED:
            dimming = set()
        else:
            dimming = set(always)      # tentative: the fg attribution
            #                          # below can only SUBTRACT from
            #                          # an armed always set
        if covered:
            # VIDEO MODE (the class docstring): the panels the frame
            # covers qualify on the rect ALONE - the always ruling's
            # shape without the idle wait, because a live video IS
            # the activity this mode was built around. The fg
            # attribution below may subtract a covered panel for the
            # PLAIN veils; the frame re-adds it (no fg exclusion in
            # video mode - the browser's chrome dims with the rest).
            dimming |= covered
        if not d.get("on"):
            dimming = covered           # the off [dimmer] seeds
            #                           # NOTHING plain: the frame
            #                           # is the whole veil set
        if dimming:
            sounding = set(self._audio())
            for pid in sounding:
                self._exempt[pid] = now
            stale = [p for p in self._exempt
                     if p not in sounding
                     and now - self._exempt[p] >= SETTLE_SEC]
        else:
            stale = [p for p, t in self._exempt.items()
                     if now - t >= SETTLE_SEC]
        for pid in stale:
            del self._exempt[pid]
        if not dimming:
            self._fade(d, now, cfg.get("videodim"))
            return
        try:
            wins = self._windows()
        except Exception:
            log.warning("dimmer: the census failed this tick; the "
                        "veils hold position")
            return
        if not idle_ok:
            fg = [w for w in wins if w["fg"]]
            fg_short = fg[0]["monitor"] if fg else None
            if fg_short is None:
                # the focus answers no panel at all (no foreground,
                # or a center off every rect): the always rows own
                # it, confessed ONCE per transition, not per tick
                if not self._fg_unattr:
                    self._fg_unattr = True
                    log.info("dimmer: the foreground window sits on "
                             "no panel; the always rows dim blind "
                             "until it answers")
            else:
                self._fg_unattr = False
                dimming.discard(fg_short)
            if covered:
                dimming |= covered   # the frame owes the focus no
                #                    # passage: video mode dims the
                #                    # foreground window's chrome too
            if not dimming:
                # the focus landed on the last always panel and the
                # desk is not idle: the field fades out soft
                self._fade(d, now, cfg.get("videodim"))
                return
        apps = d.get("apps") or {}
        qualified = {}
        for w in wins:
            if w["fg"] or w["cloaked"] or w["iconic"]:
                continue
            x, y, cw, ch = w["rect"]
            if cw <= 0 or ch <= 0:
                continue
            # SELF-VEIL LAW (owner UAT, Oct 15): the own-process skip
            # protects OUR OVERLAYS, not our process - the taskbar
            # strips, the jog/wash covers, the veils and the tip are
            # overrideredirect/click-through Tk toplevels and answer
            # the census WITH the toolwindow bit; the SETTINGS window
            # is the CTk root, no such bit, and dims like any
            # background window. (The hider's strips stay immune by
            # exactly this test - toolwindows - measured, not named.)
            if w["pid"] == os.getpid() and w.get("tool"):
                continue
            if apps.get(w["exe"]) is True:
                continue
            if w["monitor"] in covered:
                continue     # VIDEO MODE (the class docstring): the
            #                 # frame owns this panel and a window
            #                 # veil under it would STACK its alpha
            #                 # (the stratum's own no-stacking law).
            #                 # REPLACEMENT SEAM (owner, Oct 16): while
            #                 # the theater frame lives, its panel is a
            #                 # COVERED panel for the plain-veil law -
            #                 # a second idle veil must NOT pop over the
            #                 # movie while the rest of the desk dims.
            #                 # This JOINS (never parallels) the
            #                 # per-window audio exemption below: a
            #                 # SOUNDING movie browser is already exempt
            #                 # by pid, but a SILENT mid-scene stretch
            #                 # ages the browser out of _exempt after
            #                 # SETTLE_SEC - this panel/region skip is
            #                 # the sound-independent backstop that
            #                 # holds during exactly that settle edge.
            if w["monitor"] not in dimming:
                continue
            if w["pid"] in self._exempt:
                continue        # SOUND-EXEMPTION SEAM for the PLAIN
            #                   # veils: a sounding pid keeps ITS OWN
            #                   # window bright (per-window, not
            #                   # desk-wide), with a SETTLE_SEC hold
            #                   # after it goes quiet. The theater frame
            #                   # NEVER consults _exempt - its lift is
            #                   # the pointer/keyboard idle gate in
            #                   # _live_rect (GetLastInputInfo), so a
            #                   # film's audio cannot kill the veil.
            qualified[w["hwnd"]] = ((x, y, cw, ch), w["monitor"])
        for key, piece in frame.items():
            qualified[key] = piece      # the frame rides the SAME
            #                           # paint loop: birth, follow
            #                           # (the rect moves, the pieces
            #                           # re-clip), shared level alpha
        alpha = d.get("level", 20) / 100.0
        # The theater pieces draw at THEIR OWN darkness (the owner's
        # Oct-16 "veil level" rail), NOT the idle dimmer's level: a
        # movie frame may be darker or lighter than the plain veils.
        # Same clamp family as the dimmer's level (10..90).
        valpha = int((cfg.get("videodim") or {}).get("level", 20)) \
            / 100.0
        for hwnd, (rect, short) in qualified.items():
            st = self._live.get(hwnd)
            a = valpha if hwnd in frame else alpha
            if st is None:
                self._live[hwnd] = {"rect": rect, "alpha": a,
                                    "die": None, "mon": short,
                                    "frame": hwnd in frame}
                self._paint(hwnd, rect, a)
            elif st["die"] is not None or st["alpha"] != a:
                st["die"], st["alpha"] = None, a   # back to full
                st["mon"] = short
                self._paint(hwnd, rect, a)
            elif st["rect"] != rect:                   # it moved
                st["rect"] = rect
                st["mon"] = short                      # its own panel
                self._paint(hwnd, rect, a)             # we followed
            elif st.get("frame"):
                # THEATER RE-PIN (Oct-16 UAT cure): an unchanged frame
                # piece still rides the paint queue EVERY tick - a
                # plain veil survives re-activations pinned to its own
                # window, but a frame piece owns nothing, and the first
                # click on the browser buries it (the UAT bite: the
                # ring was painted, measured, and invisible). One
                # SetWindowPos per piece per beat is the honest cost
                # of the replacement law.
                self._paint(hwnd, rect, a)
        ramp = max(0, min(60, int(d.get("ramp_sec", 8))))   # belt:
        #                                                normalize
        #                                                already
        #                                                clamps
        for hwnd, st in list(self._live.items()):
            if hwnd in qualified:
                continue
            if st.get("frame"):
                # THE FADE-OFF OPTION (owner, Oct 16: "I don't like
                # the fade, so I won't use it - but having the option
                # is the right move"): [videodim] fade is a strict
                # bool, DEFAULT OFF - input returns, the frame
                # vanishes THIS TICK like every other drop. fade=true
                # opts the theater into the ramp family (one-tick
                # hold, retract over ramp_sec, no blink).
                if (cfg.get("videodim") or {}).get("fade") is True:
                    self._fade_one(now, hwnd, st, ramp)
                else:
                    self._drop(hwnd)
                # (the old ramp-only law - "a vanished rect is a
                # stopped video, the RAMP pulls the frame back, its
                # first step the one-tick hold" - survives ONLY as
                # the fade=true branch above)
            elif st["mon"] in dimming:
                self._drop(hwnd)        # disqualified ON A DIMMING
                                        # PANEL: the veil is GONE
                                        # this tick - foreground and
                                        # sound un-dim instantly, the
                                        # fade belongs to the idle
                                        # edge alone
            else:
                # the panel itself stopped dimming (input returned
                # while an always panel keeps the field, an opt-out):
                # that edge is an idle edge FOR THIS PANEL - fade it
                # down, don't blink it off, and don't freeze it dark
                # just because another panel is still working
                self._fade_one(now, hwnd, st, ramp)

    def _live_rect(self, cfg, now):
        """The eye's door, fail-open by construction: no seam, a
        paused desk, a raising eye - all read as "no rect". The
        liveness law itself (not paused, big enough, fresh within
        grace) is the eye's: videoeye.video_rect applies the
        [videodim] rails, so this FSM re-checks nothing.

        THE AUTOMATIC CONJUNCTION (owner, Oct 16): the theater veil
        frames the video only when it is PLAYING AND the desk has been
        input-still for [videodim].idle_sec - the dimmer's own idle
        spell, one knob, same clock (self._idle()). Sound is EXEMPT:
        a film's audio must not lift the theater veils, so the lift
        gate is the POINTER/KEYBOARD idle clock (GetLastInputInfo) and
        NOTHING else - the frame pieces are painted directly into
        `qualified` (the tick's frame loop), bypassing the `_exempt`
        sound ledger that lifts the PLAIN per-window veils. The dimmer
        pause still outranks the frame (it is the whole-field law).
        """
        if self._video is None or _PAUSED or not (
                (cfg.get("videodim") or {}).get("on")):
            return None                  # pause outranks the frame too
            #                            # (the whole-field law, the
            #                            # always rows' own shape)
        idle_s = float((cfg.get("videodim") or {}).get(
            "idle_sec", 15))         # 15 = VIDEODIM_IDLE_DEFAULT (the
                                     #   constant's twin here; this
                                     #   module imports config lazily)
        try:
            if self._idle() < idle_s:
                return None          # the desk is being USED: no frame
        except Exception:
            return None              # a dead idle clock is a dead frame
        try:
            return self._video(cfg, now)
        except Exception:
            log.warning("dimmer: the video eye raised; no frame "
                        "this tick (fail-open)")
            return None

    def _frame_pieces(self, vrect):
        """The four dark pieces (top/bottom/left/right) around the
        live rect, CLAMPED PER MONITOR: a straddle cuts one piece
        set per panel and every piece stays inside its panel's
        bounds - the video column across the seam stays bright, so
        no dark sliver ever lands on video px (the judgment call
        this geometry ships with, named in the delivery). Zero-size
        pieces (the rect touching an edge) drop; the full ring is
        FOUR, an edge kiss is three, a panel-covering rect is none.
        Keys are synthetic NEGATIVE ints: the painter takes
        (hwnd, rect, alpha) and keys nothing off hwnd realism - and
        the negative key IS the law the pump obeys (Oct-16 buried-ring
        cure): _zpin's synthetic-anchor branch pins the piece to the
        top of the ORDINARY band on every paint, and the tick re-queues
        unchanged pieces every beat, so no activation buries the ring."""
        out = {}
        if vrect is None:
            return out
        rx, ry, rw, rh = vrect
        if rw <= 0 or rh <= 0:
            return out
        try:
            mons = self._mons()
        except Exception:
            return out                  # no desk, no frame: fail-open
        for m in mons:
            mx, my, mw, mh = m["x"], m["y"], m["w"], m["h"]
            ix0, iy0 = max(rx, mx), max(ry, my)
            ix1, iy1 = min(rx + rw, mx + mw), min(ry + rh, my + mh)
            if ix0 >= ix1 or iy0 >= iy1:
                continue                # the rect is off this panel
            s = m["short"]
            if iy0 > my:
                out[self._fkey(s, "t")] = ((mx, my, mw, iy0 - my), s)
            if iy1 < my + mh:
                out[self._fkey(s, "b")] = ((mx, iy1, mw,
                                            my + mh - iy1), s)
            if ix0 > mx:
                out[self._fkey(s, "l")] = ((mx, iy0, ix0 - mx,
                                            iy1 - iy0), s)
            if ix1 < mx + mw:
                out[self._fkey(s, "r")] = ((ix1, iy0,
                                            mx + mw - ix1,
                                            iy1 - iy0), s)
        return out

    def _fkey(self, short, side):
        key = self._frames.get((short, side))
        if key is None:
            key = self._frames[(short, side)] = -(len(self._frames) + 1)
        return key

    def _fade(self, d, now, videodim=None):
        """The whole field goes soft: every live veil takes one step
        down the ramp. THE FADE OPTION applies HERE too (owner, Oct 16
        - the first cut patched only the qualified-shrink path and the
        field-gone path ramped the frame anyway, caught by the suite
        pin): a frame piece under [videodim] fade=False is dropped
        this tick, like every other drop. The dimmer's own ramp is
        untouched; a None videodim (a caller without the section)
        means the dimmer's own veils only, and no frame exists to
        disagree about."""
        ramp = max(0, min(60, int(d.get("ramp_sec", 8))))
        vfade = (videodim or {}).get("fade") is True
        for hwnd, st in list(self._live.items()):
            if st.get("frame") and not vfade:
                self._drop(hwnd)
            else:
                self._fade_one(now, hwnd, st, ramp)

    def _fade_one(self, now, hwnd, st, ramp):
        """One veil, one step. ramp 0 is the Oct-15 ruling (the rail
        must reach zero and mean it) and the explicit guard is what
        the division below owes it: the drop lands THIS tick,
        immediate - never a ZeroDivisionError wearing the fade's
        clothes."""
        if st["die"] is None:
            st["die"] = now
        gone = now - st["die"]
        if ramp == 0 or gone >= ramp:
            self._drop(hwnd)
            return
        b = min(2, int(gone * 3 / ramp))
        self._paint(hwnd, st["rect"],
                    round(st["alpha"] * _FADE_LEVELS[b], 3))

    def _drop(self, hwnd):
        self._unveil(hwnd)
        self._live.pop(hwnd, None)

    def teardown(self):
        for hwnd in list(self._live):
            self._drop(hwnd)
        self._exempt.clear()


# ---------------------------------------------------------------- stratum

def _fact(w, fg, by_short):
    pid = ctypes.c_uint()
    _u32.GetWindowThreadProcessId(w, ctypes.byref(pid))
    r = _RECT()
    if _dwm.DwmGetWindowAttribute(w, DWMWA_EXTENDED_FRAME_BOUNDS,
                                  ctypes.byref(r), ctypes.sizeof(r)):
        r = _RECT()                      # no DWM answer: the GDI lie
        if not _u32.GetWindowRect(w, ctypes.byref(r)):
            return None                  # is the honest fallback
    cloak = ctypes.c_uint()
    _dwm.DwmGetWindowAttribute(w, DWMWA_CLOAKED, ctypes.byref(cloak),
                               ctypes.sizeof(cloak))
    cx, cy = (r.l + r.r) // 2, (r.t + r.b) // 2
    short = None
    for s, (mx, my, mw, mh) in by_short.items():
        if mx <= cx < mx + mw and my <= cy < my + mh:
            short = s
            break
    buf = ctypes.create_unicode_buffer(256)
    _u32.GetClassNameW(w, buf)           # a refusal leaves "": no
    ex = _u32.GetWindowLongW(w, GWL_EXSTYLE)   # shell view is unnamed
    return {"hwnd": w, "pid": pid.value,
            "exe": _exe(pid.value), "cls": buf.value,
            # the overlay badge, measured on this desk (Oct-15 UAT):
            # every window WE paint is an overrideredirect (or an
            # explicit click-through) Tk toplevel, and Windows Tk
            # gives THOSE WS_EX_TOOLWINDOW; the settings window is
            # the CTk root - same class, NO toolwindow bit.
            "tool": bool(ex & WS_EX_TOOLWINDOW),
            "monitor": short, "fg": w == fg,
            "cloaked": bool(cloak.value),
            "iconic": bool(_u32.IsIconic(w)),
            "rect": (r.l, r.t, r.r - r.l, r.b - r.t)}


_exe_cache = {}


def _exe(pid):
    """exe-basename-lower per pid, cached FOR THE REST OF THE PROCESS:
    a recycled pid keeps answering with the dead app's name until the
    overflow clear below forgets everyone at once. The veil is
    transient anyway, and a wrong name only ever fails an exclusion
    OPEN (a dimmed window that should have been spared, for one
    clear's lifetime at worst)."""
    name = _exe_cache.get(pid)
    if name is None:
        name = ""
        h = _k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
        if h:
            try:
                buf = ctypes.create_unicode_buffer(1024)
                n = ctypes.c_uint(1024)
                if _k32.QueryFullProcessImageNameW(h, 0, buf,
                                                   ctypes.byref(n)):
                    name = buf.value.rsplit("\\", 1)[-1].lower()
            finally:
                _k32.CloseHandle(h)
        if len(_exe_cache) >= 1024:
            _exe_cache.clear()     # the bound: a thousand pids deep,
            #                     every stale name goes at once -
            #                     cheaper than eviction bookkeeping
            #                     and honest by noon
        _exe_cache[pid] = name
    return name


def _veil_rows(rows):
    """The census stratum's filter (Oct-15 UAT): rows whose class is
    one of DESKTOP_VIEWS are NEVER emitted - the wallpaper is not a
    window you are not using, and veiling it made the field read as
    "the whole screen dimmed" (the overlap of that veil with an
    app's own veil was the extra darkness). A FACT about the desk,
    not a config rule, so it lives here and not in the Veils FSM -
    and named, so the suite can drive the fake census through the
    real door. The settings window answers through the same door as
    any other app AND gets the veil (owner UAT, Oct 15): the
    own-process skip is TOOLWINDOW-scoped, covering our own veils,
    strips, and wash - never the settings window. The exception the
    gate's fg fix adds: a desktop row
    THAT HOLDS THE FOREGROUND FLAG rides through - dropping it
    before the flag is consulted threw away the focus attribution
    (a WorkerW/Progman focus became "the foreground sits on no
    panel", dimming the always rows blind), and the FSM's own fg
    skip still refuses it a veil, so the wallpaper law stands: the
    row passes the door precisely when it can never reach paint."""
    return [f for f in rows
            if f["cls"] not in DESKTOP_VIEWS or f["fg"]]


def _census():
    """Every visible top-level window as veil facts, minus the
    desktop's own shell views (_veil_rows). The foreground is
    resolved to its root ancestor (gate finding 2): a focus that is
    a CHILD or owned popup (a UWP CoreWindow child, a dropdown, a
    devtools popup) must mark its TOP-LEVEL as foreground, or the
    whole app stays qualified and the focused window keeps a veil
    the owner is actively typing into."""
    from . import wm
    fg = _u32.GetAncestor(_u32.GetForegroundWindow(), GA_ROOT) \
        or _u32.GetForegroundWindow()
    by_short = {m["short"]: (m["x"], m["y"], m["w"], m["h"])
                for m in wm.monitors()}
    rows = []

    def cb(hwnd, _l):
        try:
            if _u32.IsWindowVisible(hwnd):
                f = _fact(hwnd, fg, by_short)
                if f:
                    rows.append(f)
        except Exception:
            pass                         # a window mid-destruction:
        return 1                         # not a fact, not a failure

    p = _WNDENUMPROC(cb)
    _u32.EnumWindows(p, 0)
    return _veil_rows(rows)


# ---------------------------------------------------------------- painter

_q = None


def _painter():
    global _q
    if _q is None:
        _q = queue.Queue()
        threading.Thread(target=_run_painter, daemon=True,
                         name="dimmer-veil").start()
        for _ in range(100):
            if getattr(_q, "root", None) is not None:
                break
            time.sleep(0.01)
    return _q


def _clickthrough(win):
    try:
        win.update_idletasks()
        h = _u32.GetAncestor(win.winfo_id(), GA_ROOT) or win.winfo_id()
        ex = _u32.GetWindowLongW(h, GWL_EXSTYLE)
        _u32.SetWindowLongW(h, GWL_EXSTYLE,
                            ex | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
                            | WS_EX_TOOLWINDOW)
    except Exception:                    # the veil still dims; only
        pass                             # click-through degrades


def _tray_above(rect):
    """The taskbar window covering the piece's monitor ROW, or None.
    Enumerates the two tray classes at most every 5 s (the desk's
    chrome rarely restacks; a re-pin beat must not pay a full
    enumeration every 0.2 s). ROW matching is horizontal: a tray is
    this piece's chrome when its x-span overlaps the piece's - the
    monitors of a desk have disjoint x-spans, the taskbars sit at the
    bottom of each row where the pieces' union reaches anyway."""
    now = time.monotonic()
    if now >= _TRAY_CACHE["until"]:
        rows = []

        @_WNDENUMPROC
        def cb(hwnd, _l):
            if _u32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(256)
                _u32.GetClassNameW(hwnd, buf)
                if buf.value in _TRAY_CLASSES:
                    r = _RECT()
                    if _u32.GetWindowRect(hwnd, ctypes.byref(r)):
                        rows.append((hwnd, r.l, r.r))
            return 1
        _u32.EnumWindows(cb, 0)
        _TRAY_CACHE.update(until=now + 5.0, rows=rows)
    x0, _, w, _ = rect
    for hwnd, left, right in _TRAY_CACHE["rows"]:
        if min(right, x0 + w) - max(left, x0) > 0:
            return hwnd
    return None


def _zpin(win, target_hwnd):
    """The layering law (gate finding 1): the veil sits IMMEDIATELY
    ABOVE ITS OWN WINDOW, band-matched - never in the topmost band,
    where stacked veils over overlapping apps add alphas into a
    seam darker than either. The pin reads the target's next-ABOVE
    neighbour (GW_HWNDPREV - the packet said GW_HWNDNEXT and the
    GetPixel probe of Oct-15 refused it: the z-order walk goes top
    toward bottom, so NEXT pinned the veil UNDER its owner, painting
    nothing; PREV anchors above), then SetWindowPos's OUR veil's
    root ancestor under it: the first argument is ours, never the
    owner's, which is what keeps the call from yanking the user's
    window forward - the trap this whole fix must not fall into.
    Band-match first (a topmost owner still gets a topmost veil, an
    ordinary one an ordinary veil), and a dead anchor is a SKIP, not
    a raise: a refused pin (UIPI-elevated target, a window that
    vanished this tick) costs one cosmetic beat and the next paint
    follows the window anyway."""
    try:
        if target_hwnd is not None and int(target_hwnd) <= 0:
            # SYNTHETIC ANCHOR (theater pieces) - THE BAND LAW, as
            # measured on the owner's desk (Oct-16 cappy): a background
            # process CANNOT restack into the top of the ORDINARY band
            # over the foreground window - HWND_TOP answers success and
            # the piece stays under the browser forever (foreground
            # lock; AttachThreadInput does not lift it). The TOPMOST
            # band is the only band a background raiser wins, and the
            # taskbar exclusion rides inside it: anchor under the tray
            # of this piece's own monitor row (slide one slot down via
            # GW_HWNDPREV), so the desk's chrome never darkens. The
            # tick re-pins frame pieces every beat (Veils.tick), and
            # EVERY SetWindowPos here carries SEVEN args - the six-arg
            # call of the first cure died as a ctypes TypeError in the
            # swallow below and cost a full wave (warn-once, per
            # branch: one benign plain-anchor race must never re-
            # silence the theater's own confession - gate finding 1).
            try:
                win.update_idletasks()
                h = (_u32.GetAncestor(win.winfo_id(), GA_ROOT)
                     or win.winfo_id())
                if not _setwindowpos(h, -1, 0, 0, 0, 0, _SWP_ZPIN):
                    raise OSError("SetWindowPos(HWND_TOPMOST) refused")
                tray = _tray_above(getattr(win, "_pb_rect", None)
                                   or (0, 0, 0, 0))
                if tray is not None:
                    above = _getwindow(tray, GW_HWNDPREV)
                    if above:
                        _setwindowpos(h, above, 0, 0, 0, 0, _SWP_ZPIN)
            except Exception:
                if not _PIN_WARNED[0]:
                    _PIN_WARNED[0] = True
                    log.warning("dimmer: the THEATER piece pin raised "
                                "or was refused; the ring may sit under "
                                "the browser (videoeye_test pin 25, "
                                "scripts/theater_live.py name the law)")
            # no tray (locked workstation, odd shell): the piece stays
            # at top of the topmost band - confessed, one-line degrade.
            return
        if not _iswindow(target_hwnd):
            return                       # dead anchor: skip, never straggle
        ex = _u32.GetWindowLongW(target_hwnd, GWL_EXSTYLE)
        win.attributes("-topmost", bool(ex & WS_EX_TOPMOST))
        win.update_idletasks()
        h = _u32.GetAncestor(win.winfo_id(), GA_ROOT) or win.winfo_id()
        above = _getwindow(target_hwnd, GW_HWNDPREV)
        _setwindowpos(h, above, 0, 0, 0, 0, _SWP_ZPIN)
    except Exception:                    # the veil still dims; only
        if not _PIN_WARNED_PLAIN[0]:     # the layering degrades - the
            _PIN_WARNED_PLAIN[0] = True  # plain branch's OWN once.
            log.warning("dimmer: the plain veil pin raised; the "
                        "layering degrades (once per process)")


def _run_painter():
    import tkinter as tk
    from . import hider
    hider.wait_for_window()              # the birth-order law
    root = tk.Tk()
    root._owner_thread = threading.get_ident()
    root.withdraw()
    _q.root = root
    veils = {}

    def pump():
        while True:
            try:
                item = _q.get_nowait()
            except queue.Empty:
                break
            hwnd = None
            try:
                act, hwnd, rect, alpha = item
                if act == "gone":
                    w = veils.pop(hwnd, None)
                    if w is not None:
                        w.withdraw()
                        w.after(150, w.destroy)
                    continue
                w = veils.get(hwnd)
                if w is None:
                    w = veils[hwnd] = tk.Toplevel(root)
                    w.overrideredirect(True)
                    w.configure(bg="#000000")
                    w.protocol("WM_DELETE_WINDOW", lambda: None)
                w._pb_rect = rect
                w.geometry("%dx%d+%d+%d" % (rect[2], rect[3],
                                            rect[0], rect[1]))
                w.attributes("-alpha", alpha)
                w.deiconify()
                _zpin(w, hwnd)           # the layering law: ours sits
                #                      under the target's next-up, in
                #                      the target's band - never the
                #                      topmost band (gate finding 1)
                _clickthrough(w)
            except Exception:
                # the dead-hwnd law (Oct-15 UAT, the stale dark box):
                # a paint against a destroyed window raises inside
                # Tk, and an escaped raise left that veil in the
                # dict - un-click-through, un-lifted, outliving the
                # app it covered. One bad item never takes the pump:
                # drop the window, destroy it, keep draining (the
                # jog pump's shape, learned twenty minutes older).
                log.exception("dimmer: one veil item failed; the "
                              "pump survives")
                w = veils.pop(hwnd, None)
                if w is not None:
                    try:
                        w.destroy()
                    except Exception:
                        pass
        root.after(50, pump)

    root.after(50, pump)
    root.mainloop()


def _paint(hwnd, rect, alpha):
    _painter().put(("veil", hwnd, rect, alpha))


def _unveil(hwnd):
    _painter().put(("gone", hwnd, None, 0.0))


def _sounding():
    from . import _wasapi
    return _wasapi.sounding_pids()


def _video_rect(cfg, now):
    """The eye's door into the FSM (the seam the tests replace):
    lazy import - videoeye owns the sockets, this module only ever
    asks the question. Liveness and the [videodim] rails are the
    eye's law, pinned in videoeye.video_rect's own docstring."""
    from . import videoeye
    return videoeye.video_rect(cfg, now)


def _monitors():
    """The panel rows the frame clamps against (the seam the tests
    replace): wm.monitors answers {short, x, y, w, h} in the same
    physical px the veils paint in."""
    from . import wm
    return wm.monitors()


def _idle_secs():
    from . import display
    return display.idle_seconds()


# ------------------------------------------------------------- hotkey arm

def _pump_hwnd():
    """The display watcher's own window: WM_HOTKEY posts to the queue
    of the thread that REGISTERED, and that thread is the pump."""
    from . import display
    return display.hotkey_window()


_hk = None        # the (mods, vk) currently registered; None = no key
_hk_tried = None  # the stored word the last settled attempt answered
_hk_note = ""     # the dated word the card's say row shows
_hot_flag = False  # set on the pump thread, flipped on the loop beat
_PAUSED = False


def _dated(word):
    return time.strftime("%H:%M ") + word


def _norm_bound(want):
    if isinstance(want, (list, tuple)) and len(want) == 2:
        try:
            return (int(want[0]), int(want[1]))
        except (TypeError, ValueError):
            return None
    return None


def _sync_hotkey(want):
    """The tick's hotkey bookkeeping: one attempt per CHANGED stored
    word (not one per tick). The old key is released before the new
    knock - a combo that turns out taken keeps the OLD binding and
    leaves the dated word for the card; a headless attempt is NOT
    marked tried, so the arm re-tries once a pump lives, answering
    the card with the word in the meantime. Since the Oct-15 1408
    lesson every verb is a NOTE on the display pump's queue (the
    _ear_req idiom): the registration belongs to the thread that
    owns the window and pumps the queue the WM_HOTKEY posts to, and
    the (ok, errno) rides back on the note's event - the restore of
    an old binding is a second note, so it stands on the same law."""
    global _hk, _hk_tried, _hk_note
    want = _norm_bound(want)
    if want == _hk_tried:
        return
    hwnd = _pump_hwnd()
    if want and hwnd is None:
        _hk_note = _dated("no message pump lives to hold the key "
                          "yet")
        return
    old = _hk
    if old is not None:
        if hwnd:
            _request_hotkey("unregister")
        _hk = None
    if not want:
        _hk_tried, _hk_note = None, ""
        return
    mods = want[0] | MOD_NOREPEAT        # the ONLY place NOREPEAT is
    ok, err = _request_hotkey("register", mods, want[1])          # added:
    #                                    the pump applies it, THIS tick
    #                                    reports the answer - the door
    #                                    that was the bug is now the
    #                                    law: no verb leaves this
    #                                    thread when a window owns it
    if ok:
        _hk, _hk_tried, _hk_note = want, want, ""
        log.info("dimmer: hotkey arm: stored [%#x, %#x] registered "
                 "as mods=%#x vk=%#x on hwnd=%#x - one press pauses",
                 want[0], want[1], mods, want[1], hwnd or 0)
        return
    log.warning("dimmer: hotkey arm: stored [%#x, %#x] refused on "
                "hwnd=%#x: mods=%#x vk=%#x errno=%d%s",
                want[0], want[1], hwnd or 0, mods, want[1], err,
                " (ERROR_HOTKEY_ALREADY_REGISTERED)"
                if err == ERROR_HOTKEY_ALREADY_REGISTERED
                else " - NOT a collision - a different door")
    back = (" (clear and rebind to retry once the other app lets "
            "go)")                       # the advice belongs on the
    if old and _request_hotkey("register",                        # bare
                               old[0] | MOD_NOREPEAT,             # word
                               old[1])[0]:                        # too:
        _hk = old                                                 # first
        back = "; the old binding stands" + back                  # binds
    _hk_tried = want                                              # hit
    if err == ERROR_HOTKEY_ALREADY_REGISTERED:
        _hk_note = _dated("that combo is taken on this desk" + back)  # hit
    else:
        # the Oct-15 fix for the false "taken": a refusal that is
        # not 1409 says its NUMBER (87 is a bad parameter, 1400 a
        # bad chord - none of them is another app holding the key)
        _hk_note = _dated("the desk refused that combo - windows "
                          "error %d, not a clash" % err)


# the Tk modifier mask -> the RegisterHotKey flag (event.state order):
_TK_MODS = ((0x4, 0x2), (0x8, 0x1), (0x1, 0x4), (0x40, 0x8))


def capture_word(state, keycode):
    """The card's capture rule, pure so the suite can drive it with
    fake events: returns (pair, None) when the press is a chord, and
    (None, the word) when it was a bare key. A letter is something
    the user TYPES - stealing it on a bare press would be the exact
    theft the owner's consent law forbids; the old binding stands."""
    mods = 0
    for tk_mask, win_mod in _TK_MODS:
        if state & tk_mask:
            mods |= win_mod
    if mods == 0:
        return None, ("a letter is not a chord - bind a combo, "
                      "esc clears")
    return [mods, int(keycode)], None


def hotkey_press():
    """The display pump's call-in (its WM_HOTKEY branch): a press is
    ONE flag, flipped on the state loop's next beat - flipping the
    card's checkbox from the pump thread would be the cross-Tk class
    again, and the pause law is a toggle either way."""
    global _hot_flag
    _hot_flag = True


def set_paused(v):
    """The card's pause switch: a runtime bool, NOT config - the
    pause lives as long as the process."""
    global _PAUSED
    _PAUSED = bool(v)


def paused():
    return _PAUSED


def bind_note():
    """The binding confession, dated at attempt time: '' when the arm
    has nothing to say."""
    return _hk_note


def bound_live():
    """True only while a hotkey is actually registered."""
    return _hk is not None


# ------------------------------------------------------------------ API

_veils = None


def tick(cfg, now):
    """The _boot hook (AFTER hider.tick). No boot call: the veils are
    lazy, the painter thread only exists the first time a veil is
    actually born - an armed-off [dimmer] costs one dict and a
    return. The hotkey press lands here as a flag: ONE press
    pauses, one resumes."""
    global _veils, _hot_flag
    if _hot_flag:
        _hot_flag = False
        set_paused(not _PAUSED)
    if _veils is None:
        _veils = Veils(_census, _sounding, _idle_secs, _paint, _unveil,
                       video=_video_rect)
    _sync_hotkey((cfg.get("dimmer") or {}).get("bound"))
    _veils.tick(cfg, now)


def teardown():
    global _veils, _hk, _hk_tried, _hk_note
    if _hk is not None:
        if _pump_hwnd():
            _request_hotkey("unregister")      # the un-knock crosses too
            #                                  # (the leak law - and by
            #                                  # teardown time the pump
            #                                  # may already be gone:
            #                                  # the door answers (False,
            #                                  # 0) and the registration
            #                                  # dies with the process)
        _hk, _hk_tried, _hk_note = None, None, ""
    if _veils is not None:
        _veils.teardown()
        _veils = None
