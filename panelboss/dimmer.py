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
own windows, exes the user put on [dimmer.apps], and every
process the WASAPI sensor says is AUDIBLE right now (a window that
started making sound un-dims the tick the sensor learns it; one that
went quiet keeps its exemption for SETTLE_SEC - the API drops a
stopped session from the enumeration at once, the settle lives
HERE). Input returns and the whole set fades out within ramp_sec in
at most THREE alpha steps: a dimmer that blinks off is a screensaver.
The card's pause switch and the bound hotkey pause the same way: a
fade, not a blink, and the field comes back the tick the pause lifts.

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
keeps draining - the jog pump's lesson, matched. And the pump is
where the SET is composed before it is painted: a birth whose rect
is fully CONTAINED in a live veil's rect is refused (two stacked
alphas paint a darker seam than either; the covering veil already
darkens that field). The inverse containment is deliberately left
to the next move - see _covered.

THE HOTKEY LAW (owner): unbound by DEFAULT - no stolen chord before
consent. The card captures a press and stores [mods, vk]; THIS module
does the actual RegisterHotKey, against the DISPLAY watcher's pump
window (the registering thread must pump the queue the WM_HOTKEY
posts to - the broadcast lesson's twin), and re-arms from the tick
when the stored word changes. A taken combo answers the card's say
row with the dated word and keeps the OLD binding; binding while
headless answers a word too, never a silent lie. One press pauses,
one resumes (toggle, not hold).

SIZE LAW: the file runs ~470 and the seam is real, not cosmetic -
Veils (the FSM, ~120) and the stratum below it (census + pins,
painter, hotkey arm) are already three files wearing one name; when
the veil set needs card-side state, the stratum moves out as
_dimwin.py and the seam opens on its own. The pinning table is
atomic (the shared-windll lesson) and the test drives the FSM AND
the hotkey arm through injected seams, so the whole module runs
app-up and headless alike.
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
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_FADE_LEVELS = (1.0, 2.0 / 3.0, 1.0 / 3.0)   # THREE steps, then gone

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
_u32.RegisterHotKey.restype = ctypes.c_int
_u32.RegisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                ctypes.c_uint, ctypes.c_uint]
_u32.UnregisterHotKey.restype = ctypes.c_int
_u32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_uint]
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

# the desktop's own shell views (Oct-15 UAT: the census kept them, so
# the dimmer veiled the WALLPAPER and the desk read as "the whole
# screen went dark"). This is a FACT about the desktop, not a config
# rule, so it filters in the census stratum - never in the Veils FSM,
# whose job is qualification by config.
DESKTOP_VIEWS = frozenset(("Progman", "WorkerW"))

# the patchable aliases the fakes lean on (the suite owns the desk
# here; the pins above stay the real verbs)
_register = _u32.RegisterHotKey
_unregister = _u32.UnregisterHotKey


class _RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                ("r", ctypes.c_long), ("b", ctypes.c_long)]


class Veils:
    """Pure FSM (the Strips shape): windows() -> window facts
    (hwnd, pid, exe, monitor, rect, cloaked, iconic, fg), audio() ->
    the ACTIVE-pid set (silent empty on every sensor failure - never
    raises), idle() -> input-still seconds, paint(hwnd, rect, alpha)
    / unveil(hwnd). A census hiccup holds every veil at its last
    position: no tick, not a dead loop."""

    def __init__(self, windows, audio, idle, paint, unveil):
        self._windows, self._audio, self._idle = windows, audio, idle
        self._paint, self._unveil = paint, unveil
        self._live = {}        # hwnd -> {"rect", "alpha", "die": None|t}
        self._exempt = {}      # pid -> last tick the sensor heard it

    def tick(self, cfg, now):
        d = cfg.get("dimmer") or {}
        rows = d.get("monitors") or {}
        opted = {s for s, v in rows.items() if v}
        if not d.get("on") or not opted:
            self.teardown()
            return
        # the predicate first: fading needs no fresh facts; birth does
        # - a fading tick leaves the census and the WASAPI walk in
        # their pockets
        dimming = (not _PAUSED
                   and self._idle() >= d.get("idle_sec", 120))
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
            ramp = max(3, min(60, int(d.get("ramp_sec", 8))))   # belt:
            #                                                normalize
            #                                                already
            #                                                clamped
            for hwnd, st in list(self._live.items()):
                if st["die"] is None:
                    st["die"] = now
                gone = now - st["die"]
                if gone >= ramp:
                    self._drop(hwnd)
                    continue
                b = min(2, int(gone * 3 / ramp))
                self._paint(hwnd, st["rect"],
                            round(st["alpha"] * _FADE_LEVELS[b], 3))
            return
        try:
            wins = self._windows()
        except Exception:
            log.warning("dimmer: the census failed this tick; the "
                        "veils hold position")
            return
        apps = d.get("apps") or {}
        qualified = {}
        for w in wins:
            if w["fg"] or w["cloaked"] or w["iconic"]:
                continue
            x, y, cw, ch = w["rect"]
            if cw <= 0 or ch <= 0:
                continue
            if w["pid"] == os.getpid():
                continue
            if apps.get(w["exe"]) is True:
                continue
            if w["monitor"] not in opted:
                continue
            if w["pid"] in self._exempt:
                continue
            qualified[w["hwnd"]] = (x, y, cw, ch)
        alpha = d.get("level", 45) / 100.0
        for hwnd, rect in qualified.items():
            st = self._live.get(hwnd)
            if st is None:
                self._live[hwnd] = {"rect": rect, "alpha": alpha,
                                    "die": None}
                self._paint(hwnd, rect, alpha)
            elif st["die"] is not None or st["alpha"] != alpha:
                st["die"], st["alpha"] = None, alpha   # back to full
                self._paint(hwnd, rect, alpha)
            elif st["rect"] != rect:                   # it moved
                st["rect"] = rect
                self._paint(hwnd, rect, alpha)         # we followed
        for hwnd in [h for h in self._live if h not in qualified]:
            self._drop(hwnd)            # disqualified: the veil is
                                        # GONE this tick - foreground
                                        # and sound un-dim instantly,
                                        # the fade belongs to the idle
                                        # edge alone

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
    return {"hwnd": w, "pid": pid.value,   # shell view is unnamed
            "exe": _exe(pid.value), "cls": buf.value,
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
    any other app; own-process skip covers our own veils, strips,
    and wash."""
    return [f for f in rows if f["cls"] not in DESKTOP_VIEWS]


def _census():
    """Every visible top-level window as veil facts, minus the
    desktop's own shell views (_veil_rows)."""
    from . import wm
    fg = _u32.GetForegroundWindow()
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


def _covered(veils, hwnd, rect):
    """The pump's composite, consulted ONLY at a birth (Oct-15 UAT,
    the random-darker-box): True when some live veil's rect FULLY
    CONTAINS this new one. Two stacked Tk windows each at the level
    darken the intersection past either - the seam reads as a stale
    veil. The covering veil already darkens that whole field, so the
    contained window gets no window of its own; when the covering
    app loses its veil, the contained window's next paint request
    births it normally. The INVERSE (a live veil sitting inside a
    bigger newcomer) is deliberately left: the discrepancy dies the
    tick the underlying window moves, and a general rectangle-
    subtraction painter is a rewrite the owner has not asked for."""
    for h, w in veils.items():
        if h == hwnd:
            continue
        lr = getattr(w, "_pb_rect", None)
        if lr is None:
            continue                     # a veil from before the law
        if (lr[0] <= rect[0] and lr[1] <= rect[1]
                and rect[0] + rect[2] <= lr[0] + lr[2]
                and rect[1] + rect[3] <= lr[1] + lr[3]):
            return True
    return False


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
                    if _covered(veils, hwnd, rect):
                        continue         # the covering veil owns it
                    w = veils[hwnd] = tk.Toplevel(root)
                    w.overrideredirect(True)
                    w.configure(bg="#000000")
                    w.attributes("-topmost", True)
                    w.protocol("WM_DELETE_WINDOW", lambda: None)
                w._pb_rect = rect
                w.geometry("%dx%d+%d+%d" % (rect[2], rect[3],
                                            rect[0], rect[1]))
                w.attributes("-alpha", alpha)
                w.deiconify()
                w.lift()
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
    the card with the word in the meantime."""
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
            _unregister(hwnd, HOTKEY_ID)
        _hk = None
    if not want:
        _hk_tried, _hk_note = None, ""
        return
    if _register(hwnd, HOTKEY_ID, want[0] | MOD_NOREPEAT, want[1]):
        _hk, _hk_tried, _hk_note = want, want, ""
        return
    back = (" (clear and rebind to retry once the other app lets "
            "go)")                       # the advice belongs on the
    if old and _register(hwnd, HOTKEY_ID, old[0] | MOD_NOREPEAT,   # bare
                         old[1]):                                   # word
        _hk = old                                                   # too:
        back = "; the old binding stands" + back                    # first
    _hk_tried = want                                                # binds
    _hk_note = _dated("that combo is taken on this desk" + back)    # hit


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
        _veils = Veils(_census, _sounding, _idle_secs, _paint, _unveil)
    _sync_hotkey((cfg.get("dimmer") or {}).get("bound"))
    _veils.tick(cfg, now)


def teardown():
    global _veils, _hk, _hk_tried, _hk_note
    if _hk is not None:
        hwnd = _pump_hwnd()
        if hwnd:
            _unregister(hwnd, HOTKEY_ID)
        _hk, _hk_tried, _hk_note = None, None, ""
    if _veils is not None:
        _veils.teardown()
        _veils = None
