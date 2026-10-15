"""The faux taskbar strip: burn-in insurance that asks nothing's permission.

Windows' own auto-hide machinery is unusable from here, and the repo
already knows it the hard way (docs/taskbar-findings.md, measured +
bisected): the SHAppBarMessage export ACCESS-VIOLATES from this process
family, and the ABM_SETSTATE write answered success-but-no-effect via
the direct-SendMessage transport (owner's 26220 desk, twice, clean).
The chosen answer is therefore the one with no shared state at all:
paint our own black strip over each opted-in bar. The strip is an ordinary window - it cannot
strand a taskbar on a crash, cannot fight a foreign hider app over
registry state, and takes effect the instant it is switched on (the
registry route would have needed an Explorer restart to be believed).
One honest weakness, owned: the strip covers the bar without
informing apps that queried the work area - fullscreens may slip
behind it. The OLED card's TIP confesses exactly this.

Anatomy: Strips is the pure FSM (testable with injected eyes and
paint); hider_win.py carries the Win32/Tk stratum - bar rects via
GetWindowRect, the autohide truth via taskbar.flag_note(), the
painter on a private Tk interpreter. No SHAppBarMessage anywhere:
this process family access-violates on it (measured, documented), and
the strip needs nothing else from it. Tick rides the state
loop (_boot hook, ~0.2 s): pause must deafen the camera, never the
shell's own ears, so this lives outside the preview branch.

SIZE LAW (one file on purpose): the stratum and the FSM
interlock through one constructor seam (eyes/paint/caret are the
class's whole world) and the whole file is one law's body - splitting
would double the read cost of understanding it and buy nothing the
test fake cannot already reach. If a second feature grows in here,
it moves out first.
"""

import ctypes
import logging
import queue
import threading
import time

log = logging.getLogger("hider")

EDGE_NAMES = {0: "left", 1: "top", 2: "right", 3: "bottom"}
CONFLICT = ("Windows auto-hide is also on - this strip may double-hide")

_u32 = ctypes.WinDLL("user32", use_last_error=True)   # the stratum's
                                                       # only dynamic
                                                       # dependency


class _RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                ("r", ctypes.c_long), ("b", ctypes.c_long)]


class _GTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("flags", ctypes.c_uint),
                ("hwndActive", ctypes.c_void_p),
                ("hwndFocus", ctypes.c_void_p),
                ("hwndCaret", ctypes.c_void_p),
                ("rcCaret", _RECT), ("dwThreadID", ctypes.c_uint),
                ("hwndMenuOwner", ctypes.c_void_p)]


_u32.FindWindowW.restype = ctypes.c_void_p
_u32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
_u32.FindWindowExW.restype = ctypes.c_void_p
_u32.FindWindowExW.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                               ctypes.c_wchar_p, ctypes.c_wchar_p]
_u32.GetWindowRect.restype = ctypes.c_int
_u32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_RECT)]
_u32.GetCursorPos.restype = ctypes.c_int
_u32.GetCursorPos.argtypes = [ctypes.POINTER(_RECT)]   # POINT fits RECT
_u32.GetForegroundWindow.restype = ctypes.c_void_p
_u32.GetForegroundWindow.argtypes = []
_u32.GetWindowThreadProcessId.restype = ctypes.c_uint
_u32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p,
                                          ctypes.POINTER(ctypes.c_uint)]
_u32.GetGUIThreadInfo.restype = ctypes.c_int
_u32.GetGUIThreadInfo.argtypes = [ctypes.c_uint, ctypes.POINTER(_GTINFO)]
_u32.ClientToScreen.restype = ctypes.c_int
_u32.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.POINTER(_RECT)]


def _bars():
    """Every taskbar as {short, hwnd, rect(x,y,w,h)}: the primary bar
    plus each secondary (per-monitor) bar. The short is the row label
    the card and the config share - matched by rect containment through
    wm.monitors(), never by friendly name (the KVM ghost learned that
    lesson in blood). A bar the ABM read refuses for is skipped: the
    strip for it is simply never painted."""
    from . import wm
    hwnds = []
    first = _u32.FindWindowW("Shell_TrayWnd", None)
    if first:
        hwnds.append(first)
    nxt, last = None, None
    while True:
        nxt = _u32.FindWindowExW(None, last, "Shell_SecondaryTrayWnd",
                                 None)
        if not nxt:
            break
        hwnds.append(nxt)
        last = nxt
    found = []
    for hwnd in hwnds:
        r = _RECT()                        # GetWindowRect is the whole
        if _u32.GetWindowRect(hwnd, ctypes.byref(r)):   # story: no shell
            found.append((r.l, r.t, r.r - r.l, r.b - r.t))        # API call

    rows = wm.monitors()
    out = []
    for rect in found:
        x, y, w, h = rect
        cx, cy = x + w // 2, y + h // 2
        for r in rows:
            if (r["x"] <= cx < r["x"] + r["w"]
                    and r["y"] <= cy < r["y"] + r["h"]):
                out.append((r["short"], rect))
                break
    return out


def _cursor():
    p = _RECT()
    if not _u32.GetCursorPos(ctypes.byref(p)):
        return None
    return p.l, p.t


def _autohide_on():
    """The conflict line's eye, per the law this repo wrote for itself
    (taskbar.py): the autohide flag's truth is the StuckRects3 byte -
    2 shown, 3 autohide - read through the registry, no shell API, no
    poke. None (unreadable) counts as no conflict: the line is a
    courtesy, not a gate."""
    from . import taskbar
    return taskbar.flag_note().startswith("autohide")


class Strips:
    """Pure FSM. eyes() -> list of [short, rect]; paint/unpaint take
    (short, rect); now() is the monotonic clock - tests inject a ladder.
    Reveal law (owner): cursor inside a bar's rect withdraws it ('all'
    withdraws every opted-in strip together); a strip returns only
    after the cursor has stayed out of EVERY bar rect for hold_sec,
    and a live caret anywhere in any bar rect holds every return
    (typing in search is using the bars). Fail-closed by default: no
    eyes, no painting."""

    def __init__(self, eyes, paint, unpaint, cursor, now, caret=None,
                 confess=None):
        self._eyes, self._paint, self._unpaint = eyes, paint, unpaint
        self._cursor, self._now = cursor, now
        self._caret = caret or (lambda: False)
        self._confess = confess or (lambda: False)
        self._st = {}                       # short -> {withdrawn, out_since}
        self._confessed = False

    def tick(self, cfg):
        h = (cfg.get("hider") or {})
        bars = dict(self._eyes()) if h.get("on") else {}
        if not bars:
            self.teardown()
            return
        reveal = h.get("reveal", "hovered")
        if reveal not in ("hovered", "all"):
            reveal = "hovered"              # normalize_hider pre-folds;
                                            # the belt stays anyway
        hold = h.get("hold_sec", 3)
        rows = h.get("monitors") or {}
        now = self._now()
        pt = self._cursor()
        hover = set()
        if pt is not None:
            for short, (x, y, w, hh) in bars.items():
                if x <= pt[0] < x + w and y <= pt[1] < y + hh:
                    hover.add(short)
        for short, rect in bars.items():
            if not rows.get(short, False):  # the opt-in law: an off row
                self._retire(short)         # never owns a strip
                continue
            st = self._st.setdefault(short, {"withdrawn": False,
                                             "out_since": None})
            if short in hover or (reveal == "all" and hover):
                if not st["withdrawn"]:
                    self._unpaint(short, rect)   # bar bared for use
                    st["withdrawn"] = True
                st["out_since"] = None
                continue
            if not st["withdrawn"]:
                self._paint(short, rect)    # armed: the strip wears the
                continue                    # bar (idempotent repaint)
            if self._caret():
                st["out_since"] = None      # typing holds every return
                continue
            if st["out_since"] is None:
                st["out_since"] = now
            elif now - st["out_since"] >= hold:
                self._paint(short, rect)    # the covered return
                st["withdrawn"], st["out_since"] = False, None
        if not self._confessed and self._confess():
            self._confessed = True
            log.info(CONFLICT)              # once per arm, no war

    def _retire(self, short):
        """A row that opted out: strip gone, bar as Windows left it.
        A row that never armed anything has nothing to retire."""
        if self._st.pop(short, None) is None:
            return
        rect = dict(self._eyes()).get(short)
        if rect:
            self._unpaint(short, rect)

    def teardown(self):
        """Every strip gone. The crash-safety story in one pass: an
        app death unpaints by construction - ordinary windows die with
        their process - so this is the ORDERLY half of the same truth."""
        for short in list(self._st):
            self._retire(short)
        self._st.clear()
        self._confessed = False


# ------------------------------------------------------------------ adapter

_strips = None


def _tk_painter():
    """The strip windows' private Tk interpreter - the _overlay module's
    proven shape shrunk to needs: opaque black, borderless, no-activate
    (the bar must not gain focus from a repaint); no click capture (the
    strip is furniture, not a button)."""
    import tkinter as tk
    q = queue.Queue()
    wins = {}

    def pump():
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                break
            act, short, rect = item
            if act == "paint":
                x, y, w, h = rect
                win = wins.get(short)
                if win is None:
                    win = wins[short] = tk.Toplevel(q.root)
                    win.overrideredirect(True)
                    win.configure(bg="#000000")
                    win.attributes("-topmost", True)
                    win.protocol("WM_DELETE_WINDOW", lambda: None)
                win.geometry("%dx%d+%d+%d" % (w, h, x, y))
                win.deiconify()
                win.lift()
            elif act == "unpaint":
                win = wins.pop(short, None)
                if win is not None:
                    win.withdraw()
                    win.after(150, win.destroy)
        q.root.after(50, pump)

    def run():
        # the birth-order law (owner UAT, Oct 15): tkinter's default
        # root is process-global and the FIRST Tk() claims it;
        # customtkinter binds every image to that default (its
        # ImageTk.PhotoImage passes no master). A painter born before
        # the settings window therefore stole the window's images -
        # the kofi cup raised "image pyimage1 doesn't exist" inside
        # SettingsWindow.__init__, every boot since the boot hooks.
        # The painter waits for the window's root instead; a headless
        # boot (no window will ever come) waits out the timeout and
        # claims the default for itself - nothing else builds images
        # on the main thread then.
        _WINDOW_READY.wait(PAINTER_READY_TIMEOUT_SEC)
        root = tk.Tk()
        root._owner_thread = threading.get_ident()  # the sweep's guard
        root.withdraw()                             # (see _shell.run)
        q.root = root
        root.after(50, pump)
        root.mainloop()

    threading.Thread(target=run, daemon=True, name="hider-paint").start()
    for _ in range(100):
        if getattr(q, "root", None) is not None:
            break
        time.sleep(0.01)

    def paint(short, rect):
        q.put(("paint", short, rect))

    def unpaint(short, rect):
        q.put(("unpaint", short, rect))
    return paint, unpaint


# Birth-order law, see _tk_painter: the painter's interpreter must
# not be the process's first Tk; window_ready() releases it.
_WINDOW_READY = threading.Event()
PAINTER_READY_TIMEOUT_SEC = 10.0


def window_ready():
    """The settings window calls this the moment its Tk is born: the
    default root is the window's now, so the painter's interpreter can
    no longer claim it (tkinter first-root-wins). A headless boot
    never calls this; the painter times out and claims."""
    _WINDOW_READY.set()


def boot():
    """One FSM per process, called from the boot path; the eyes are the
    Win32 stratum's bar census."""
    global _strips
    paint, unpaint = _tk_painter()
    _strips = Strips(_bars, paint, unpaint, _cursor, time.monotonic,
                     caret=_caret_in_bars, confess=_autohide_on)


def autohide():
    """The card's conflict eye: Windows auto-hide state, best-effort."""
    try:
        return _autohide_on()
    except Exception:
        return False


def tick(cfg):
    if _strips is not None:
        _strips.tick(cfg)


def teardown():
    if _strips is not None:
        _strips.teardown()


# The caret law needs GetGUIThreadInfo; the bar-rect matching reuses the
# The caret law needs GetGUIThreadInfo; both structs and every
# pin live up by the handles they belong to.


def _caret_in_bars():
    """Is a live caret sitting inside any bar's rect (search typing)?
    Any step refusing is a polite no - the hold is a courtesy, not a
    right."""
    try:
        fg = _u32.GetForegroundWindow()
        if not fg:
            return False
        pid = ctypes.c_uint(0)
        tid = _u32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
        gi = _GTINFO()
        gi.cbSize = ctypes.sizeof(_GTINFO)
        if not _u32.GetGUIThreadInfo(tid, ctypes.byref(gi)):
            return False
        if not gi.hwndCaret:
            return False
        pt = _RECT(gi.rcCaret.l, gi.rcCaret.t, 0, 0)
        if not _u32.ClientToScreen(gi.hwndCaret, ctypes.byref(pt)):
            return False
        for short, rect in _bars():
            x, y, w, h = rect
            if x <= pt.l < x + w and y <= pt.t < y + h:
                return True
    except Exception:
        log.debug("caret probe refused; the hold rests", exc_info=True)
    return False
