"""Background dimming: the idle desk puts dark veils on the windows
you are not using.

The law, from the owner's Oct-15 rulings: when [dimmer] is on and at
least one monitor row opted in and input has been still past
idle_sec, EVERY visible top-level window on an opted monitor gets its
own click-through dark veil - except the foreground window (touched =
instantly un-veiled, next tick), zero-size, iconic, DWM-cloaked, this
app's own windows, exes the user put on [dimmer.apps], and every
process the WASAPI sensor says is AUDIBLE right now (a window that
started making sound un-dims the tick the sensor learns it; one that
went quiet keeps its exemption for SETTLE_SEC - the API drops a
stopped session from the enumeration at once, the settle lives
HERE). Input returns and the whole set fades out within ramp_sec in
at most THREE alpha steps: a dimmer that blinks off is a screensaver.

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

SIZE LAW: the file is 390 lines and the seam is real, not
cosmetic - Veils (the FSM, ~110) and the stratum below it
(census/pins ~130, painter ~80) are already two files wearing one
name; when the UI half lands and needs veil state on the card, the
stratum moves out as _dimwin.py and the seam opens on its own. The
pinning table is atomic (the shared-windll lesson) and the test
drives the FSM through its injected seams either way. The hotkey:
bound is a STORED WORD only - this wave registers no hotkey
anywhere (the card's button pauses; WM_HOTKEY plumbing is the
documented follow-up).
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
_u32.GetWindowRect.restype = ctypes.c_int
_u32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
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
        sounding = set(self._audio())
        for pid in sounding:
            self._exempt[pid] = now
        for pid in [p for p in self._exempt
                    if p not in sounding
                    and now - self._exempt[p] >= SETTLE_SEC]:
            del self._exempt[pid]
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
        ramp = max(3, min(60, int(d.get("ramp_sec", 8))))   # belt:
        #                                                normalize
        #                                                already
        #                                                clamped
        if self._idle() >= d.get("idle_sec", 120):
            for hwnd, rect in qualified.items():
                st = self._live.get(hwnd)
                if st is None:
                    self._live[hwnd] = {"rect": rect, "alpha": alpha,
                                        "die": None}
                    self._paint(hwnd, rect, alpha)
                elif st["die"] is not None or st["alpha"] != alpha:
                    st["die"], st["alpha"] = None, alpha   # back to
                    self._paint(hwnd, rect, alpha)         # full
                elif st["rect"] != rect:                   # it moved
                    st["rect"] = rect
                    self._paint(hwnd, rect, alpha)         # we followed
            for hwnd in [h for h in self._live if h not in qualified]:
                self._drop(hwnd)          # disqualified: the veil is
                                          # GONE this tick - foreground
                                          # and sound un-dim instantly,
                                          # the fade belongs to the
                                          # idle edge alone
            return
        for hwnd, st in list(self._live.items()):
            if st["die"] is None:
                st["die"] = now
            gone = now - st["die"]
            if gone >= ramp:
                self._drop(hwnd)
                continue
            b = min(2, int(gone * 3 / ramp))
            a = round(st["alpha"] * _FADE_LEVELS[b], 3)
            self._paint(hwnd, st["rect"], a)
            st["die"] = st["die"]         # the ramp clock is the
                                          # first fading tick's; it
                                          # never re-starts mid-ramp

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
    x, y = r.l, r.t
    cx, cy = (r.l + r.r) // 2, (r.t + r.b) // 2
    short = None
    for s, (mx, my, mw, mh) in by_short.items():
        if mx <= cx < mx + mw and my <= cy < my + mh:
            short = s
            break
    return {"hwnd": w, "pid": pid.value, "exe": _exe(pid.value),
            "monitor": short, "fg": w == fg,
            "cloaked": bool(cloak.value),
            "iconic": bool(_u32.IsIconic(w)),
            "rect": (x, y, r.r - r.l, r.b - r.t)}


_exe_cache = {}


def _exe(pid):
    """exe-basename-lower per pid, cached (a reused pid is a one-tick
    wrong-answer at worst, and the veil is transient anyway)."""
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
        _exe_cache[pid] = name
    return name


def _census():
    """Every visible top-level window as veil facts. The settings
    window answers through the same door as any other app - own-
    process skip covers our own veils, strips, and wash."""
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
    return rows


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
                act, hwnd, rect, alpha = _q.get_nowait()
            except queue.Empty:
                break
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
                w.attributes("-topmost", True)
                w.protocol("WM_DELETE_WINDOW", lambda: None)
            w.geometry("%dx%d+%d+%d" % (rect[2], rect[3],
                                        rect[0], rect[1]))
            w.attributes("-alpha", alpha)
            w.deiconify()
            w.lift()
            _clickthrough(w)
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


# ------------------------------------------------------------------ API

_veils = None


def tick(cfg, now):
    """The _boot hook (AFTER hider.tick). No boot call: the veils are
    lazy, the painter thread only exists the first time a veil is
    actually born - an armed-off [dimmer] costs one dict and a
    return."""
    global _veils
    if _veils is None:
        _veils = Veils(_census, _sounding, _idle_secs, _paint, _unveil)
    _veils.tick(cfg, now)


def teardown():
    global _veils
    if _veils is not None:
        _veils.teardown()
        _veils = None
