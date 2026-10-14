"""Per-monitor black overlay: the painted lie of a sleeping panel.

One borderless topmost black Toplevel per monitor - on an OLED a full
black pixel is a pixel at rest, so the fake-off reads as off while the
panel never cold-boots its ODM (the 16-38 s re-enumeration class this
whole feature exists to dodge). Geometry arrives in the rows
wm.monitors() already resolves - nothing here re-derives a rect.

Thread law: the state machine owns its own thread and Tk owns thread
zero, so the overlay runs its OWN Tk interpreter on a private daemon
thread; the public calls only ever enqueue onto a thread-safe queue,
and the interpreter's after(50, pump) loop performs the widget work
(the app's standing answer to cross-thread Tk - same shape as the
power assistant's truth queue).

Destroy law: a release withdraws FIRST and destroys on the pump's
later tick - never inside the click callback that is still on the
widget's own stack (the withdraw+schedule idiom the tips learned in
ui/helpbtn.py). Opaque by contract: alpha 1.0 - anything peeking
through a fake-off OLED unmasks the fake. A click is swallowed AND
lifts: the callback the caller passed runs first (the UI's cancel-
now token), then the watcher queue is told ("away_lift", "overlay").

Draw-over safety is the UI's side of the deal (ui/window/_away.py):
a preview overlay transient-raises its dialog - across Tk
interpreters transient() does not exist, so topmost+raise is the
cross-app law that keeps the settings window clickable above a
blackout preview.
"""

import logging
import queue
import threading
import time

log = logging.getLogger("wm.overlay")

_BG = "#000000"          # the whole product, in one hex
_PUMP_MS = 50            # the interpreter's own tick; no busy wait
_DESTROY_MS = 150        # a release waits this long: off the callback

_root = None
_windows = {}            # gdi (lower case) -> widget
_q = queue.Queue()
_thread = None


def _start_root():
    """The private interpreter, once per process: a withdrawn root and
    a pump that outlives every window it made."""
    global _root, _thread
    if _root is not None:
        return
    import tkinter as tk

    def run():
        global _root
        root = tk.Tk()
        root.withdraw()            # the root is scaffolding, never a UI
        root.title("panelboss-away")
        _root = root
        root.option_add("*tearOff", False)
        root.after(_PUMP_MS, _pump)   # the heartbeat starts on the Tk
        root.mainloop()               # thread, from here on forever

    _thread = threading.Thread(target=run, daemon=True,
                               name="away-overlay")
    _thread.start()
    for _ in range(100):           # a second at most; a dead Tk says so
        if _root is not None:
            break
        time.sleep(0.01)


def _show(gdi, rect, on_click):
    import tkinter as tk
    x, y, w, h = rect
    win = _windows.get(gdi)
    if win is not None:
        try:                       # idempotent: re-place, re-lift, restyle
            win.geometry("%dx%d+%d+%d" % (w, h, x, y))
            win.configure(bg=_BG)
            win.attributes("-alpha", 1.0)
            win.deiconify()
            win.attributes("-topmost", True)
            win.lift()
            return
        except tk.TclError:
            _windows.pop(gdi, None)
    win = tk.Toplevel(_root)
    win.overrideredirect(True)     # borderless: fake-off has no chrome
    win.geometry("%dx%d+%d+%d" % (w, h, x, y))
    win.configure(bg=_BG)
    win.attributes("-alpha", 1.0)  # opaque, the law above
    win.attributes("-topmost", True)
    win.lift()
    win.protocol("WM_DELETE_WINDOW", lambda: None)   # the tray X
    win.bind("<Button-1>", lambda e: _click(gdi, on_click))
    _windows[gdi] = win


def _click(gdi, on_click):
    """A click swallows AND wakes: the caller's token first (a preview
    cancels now), then the engine's own lift path."""
    try:
        if on_click is not None:
            on_click()
    except Exception:
        log.debug("overlay click token failed", exc_info=True)
    from .. import display         # late: display owns the queue
    if display.watcher is not None:
        display.watcher.queue.put(("away_lift", "overlay",
                                   time.monotonic()))


def _hide(gdi):
    win = _windows.pop(gdi, None)
    if win is None:
        return
    try:
        win.attributes("-topmost", False)
        win.withdraw()             # destroy law: off screen first...
        _root.after(_DESTROY_MS, win.destroy)   # ...off the stack after
    except Exception:
        log.debug("overlay destroy skipped", exc_info=True)


def _pump():
    while True:
        try:
            try:
                item = _q.get_nowait()
            except queue.Empty:
                break
            action, args = item
            if action == "show":
                _show(*args)
            elif action == "hide":
                _hide(args[0])
        except Exception:
            log.debug("overlay pump item failed", exc_info=True)
    if _root is not None:
        _root.after(_PUMP_MS, _pump)


def show(gdi, rect, on_click=None):
    """Cover one monitor. Idempotent (see _show). rect = (x, y, w, h)
    from wm.monitors() - device pixels, the app is DPI-unaware."""
    _start_root()
    _q.put(("show", (str(gdi).lower(), rect, on_click)))


def hide(gdi):
    """Release one cover. Idempotent - a missing cover is a released
    cover."""
    _q.put(("hide", (str(gdi).lower(),)))


def hide_all():
    for gdi in list(_windows):
        hide(gdi)


def shown(gdi=None):
    """The honest state word for the suites and the row status: the
    cover list (or whether one specific monitor wears it)."""
    if gdi is None:
        return sorted(_windows)
    return str(gdi).lower() in _windows
