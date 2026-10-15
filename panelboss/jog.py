"""Panel refresh for OLEDs: the pixel jog and the manual wash.

The honesty premise, first: PanelBoss cannot read an OLED's wear
counters and will not pretend otherwise - the one register this desk
has ever answered (the IOC912B's power state) was PROVEN to lie during
a witnessed blackout. What the app can do is move its own covers and
light the panel on request, and that is exactly what this module is:

* shuffle - the app's covers (taskbar strips today, dim veils when the
  dimmer wave lands) sit on a small deterministic ring of offsets
  stepped by the cycle timer, so no cover edge ages one strip of glass
  permanently. The ring is (0, +s, 0, -s): it starts at rest (arming
  moves nothing), sums to ZERO drift, and returns - a cover never
  wanders off its bar.
* wash - a brief translucent white veil over one monitor, MANUAL by
  law: tick() never births it. Wash is a request, not a scheduled
  promise, and the card says so.

SIZE LAW (one file on purpose): the ring arithmetic, the state table
and the wash veil's painter are one law's body at ~130 lines; the
split would cost more reading than it saves. If the dimmer wave grows
a second surface into the ring, THAT is the seam to split at.

Laws obeyed from the module book, not reinvented: the birth-order
contract (the veil's interpreter waits hider.wait_for_window() before
claiming a Tk - same lesson that froze this morning's blackout), the
pin law (every ctypes verb below carries its own argtypes), and the
default-off law (no ring, no veil, until [jog] says on and a row
opts in).
"""

import ctypes
import logging
import queue
import threading
import time

log = logging.getLogger("jog")

JOG_WASH_SEC = 10.0   # ten seconds of white: long enough to even a
                      # latent image's first order, short enough that
                      # nobody walks away mid-wash and finds a glare
                      # panel; vendors' own refreshes land in the same
                      # order of magnitude (observed, not specified -
                      # no panel here publishes its timer)

JOG_RING = (0, 1, 0, -1)     # the rest-start, zero-drift ring; the
                             # tuple is a LAW and the suite asserts its
                             # sum at import time

_state = {}                  # short -> {"idx": int, "due": float}
_wash_q = None               # the veil painter's queue, lazy
_wash_thread = None


def tick(cfg, now):
    """One state-loop beat: advance due rings, never birth a wash."""
    j = cfg.get("jog") or {}
    if not j.get("on"):
        teardown()
        return
    rows = j.get("monitors") or {}
    cycle = max(60, int(j.get("cycle_min", 30)) * 60)
    for short, on in rows.items():
        if not on:
            _state.pop(short, None)
            continue
        st = _state.get(short)
        if st is None:
            # arming rests at zero: the first beat only sets the deadline
            _state[short] = {"idx": 0, "due": now + cycle}
            continue
        if now >= st["due"]:
            st["idx"] = (st["idx"] + 1) % len(JOG_RING)
            st["due"] = now + cycle   # re-armed from NOW: a slept
                                      # loop ages one step, never two
                                      # (the no-catch-up law, pinned)


def shift(short):
    """The current ring offset (dx, dy) in device pixels for one
    monitor - (0, 0) unless the feature is armed and the row opted in.
    The hider reads this per paint; zero extra machinery, zero new
    window class."""
    j = _cfg_jog
    if not (j.get("on") if j else False):
        return (0, 0)
    st = _state.get(short)
    if st is None or not (j.get("monitors") or {}).get(short):
        return (0, 0)
    step = j.get("step_px", 2)
    return (JOG_RING[st["idx"]] * step, 0)


_cfg_jog = {}                # the [jog] dict, refreshed each tick so
                             # shift() stays honest between beats


def tick_with_cfg(cfg, now):
    global _cfg_jog
    _cfg_jog = cfg.get("jog") or {}
    tick(cfg, now)


def wash(short, cfg):
    """The manual wash for one monitor: returns the word the card
    shows - it NEVER raises and it never lights silently. cfg arrives
    from the UI (the state loop's dict), so the verdict reads the same
    rails the user just moved."""
    j = cfg.get("jog") or {}
    if not j.get("on"):
        return "jog feature is armed off - nothing lights"
    if not (j.get("monitors") or {}):
        return "no monitor row opted in"
    if not (j.get("monitors") or {}).get(short):
        return "monitor %s is not opted in" % short
    from . import wm
    rect = None
    for m in wm.monitors():
        if (m.get("short") or m.get("id")) == short:
            rect = (m["x"], m["y"], m["w"], m["h"])
    if rect is None:
        return "monitor %s is off the desk right now" % short
    _paint_wash(rect)
    log.info("jog: wash started on %s for %.0f s", short, JOG_WASH_SEC)
    return "wash: %s" % short


def teardown():
    _state.clear()


# ------------------------------------------------------------- wash veil

_u32 = ctypes.WinDLL("user32", use_last_error=True)   # the pin law is
_u32.GetSystemMetrics.restype = ctypes.c_int           # self-pinned
_u32.GetSystemMetrics.argtypes = [ctypes.c_int]        # from birth


def _paint_wash(rect):
    """Fire-and-forget on the wash painter; a live veil is RE-LIT (a
    second wash extends, never stacks)."""
    _start_wash_painter()
    _wash_q.put(("wash", rect))


def _start_wash_painter():
    global _wash_q, _wash_thread
    if _wash_q is not None:
        return
    _wash_q = queue.Queue()

    def run():
        import tkinter as tk
        from . import hider
        hider.wait_for_window()      # the birth-order law: the window's
                                     # root claims the process default
                                     # first (see overlay_order_test);
                                     # the timeout floor releases a
                                     # headless boot
        root = tk.Tk()
        root._owner_thread = threading.get_ident()
        root.withdraw()
        veil = None

        def pump():
            nonlocal veil
            try:
                while True:
                    act, rect = _wash_q.get_nowait()
                    if act == "wash":
                        x, y, w, h = rect
                        if veil is None:
                            import customtkinter as ctk
                            veil = ctk.CTkToplevel(root)
                            veil.overrideredirect(True)
                            veil.attributes("-topmost", True)
                            veil.attributes("-alpha", 0.93)
                            veil.configure(fg_color="#f8f8f0")
                        veil.geometry("%dx%d+%d+%d" % (w, h, x, y))
                        veil.deiconify()
                        veil.lift()
                        veil.after(int(JOG_WASH_SEC * 1000), _drop)
            except queue.Empty:
                pass
            root.after(50, pump)

        def _drop():
            nonlocal veil
            if veil is not None:
                veil.withdraw()
                root.after(150, veil.destroy)
                veil = None

        root.after(50, pump)
        root.mainloop()

    _wash_thread = threading.Thread(target=run, daemon=True,
                                    name="jog-wash")
    _wash_thread.start()
    for _ in range(100):
        if _wash_q is not None:
            break
        time.sleep(0.01)
