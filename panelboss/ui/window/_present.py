"""Win32 paint primitives for the settings window: keep overlapping
Tk windows from bleeding into each other, and force a synchronous
present when a region must be painted in one pass.

WHY this file exists (the owner's screenshot, Oct 16: "tabbing causes
both sets of objects to coexist briefly... text over text"). Tk on
Windows makes every widget a real child window. Two overlapping Tk
windows (the tab pages are siblings) do NOT clip each other by default,
so the page underneath kept painting its labels over the raised page -
the coexistence the owner photographed. `raise`, `update`,
`update_idletasks`, unmapping and a forced repaint were all measured
and none of them removed it: the bleed is a window STYLE property, not
a paint-ordering one.

`clip_siblings` sets WS_CLIPSIBLINGS on every window in a subtree. With
it, a child that paints clips every overlapping SIBLING out of its own
update region, so the raised page always wins and the page underneath
can never show through.

`present` is the other half: force a widget's whole subtree to repaint
NOW, in this call, so a swap completes inside the callback instead of
trickling out over several frames. RedrawWindow with
INVALIDATE|ERASE|UPDATENOW|ALLCHILDREN is the one call that does it.

Both are quiet on failure (a dying widget, a non-Windows host): a miss
is a miss, never a raise into a click handler.
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger("ui")

_RDW_INVALIDATE = 0x0001
_RDW_ERASE = 0x0004
_RDW_ALLCHILDREN = 0x0080
_RDW_UPDATENOW = 0x0100
_FLAGS = (_RDW_INVALIDATE | _RDW_ERASE | _RDW_ALLCHILDREN | _RDW_UPDATENOW)

_WS_CLIPSIBLINGS = 0x04000000
_GWL_STYLE = -16


def present(widget):
    """Repaint `widget` and every descendant NOW, in one pass."""
    try:
        hwnd = widget.winfo_id()
    except Exception:
        return                              # gone mid-teardown
    if sys.platform == "win32":
        try:
            import ctypes
            if ctypes.windll.user32.RedrawWindow(hwnd, None, None, _FLAGS):
                return
        except Exception:
            log.debug("present: RedrawWindow failed", exc_info=True)
    try:
        widget.update_idletasks()           # honest fallback, weaker
    except Exception:
        pass


def clip_siblings(widget):
    """Set WS_CLIPSIBLINGS on `widget` and every descendant, so an
    overlapping Tk sibling can never paint over the raised one. One walk
    per build; idempotent (setting a set bit again is a no-op)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        gdi = ctypes.windll.user32
    except Exception:
        return

    def walk(w):
        try:
            hwnd = w.winfo_id()
            style = gdi.GetWindowLongW(hwnd, _GWL_STYLE)
            if not style & _WS_CLIPSIBLINGS:
                gdi.SetWindowLongW(hwnd, _GWL_STYLE,
                                   style | _WS_CLIPSIBLINGS)
        except Exception:
            pass                            # gone mid-teardown: a miss
        for c in w.winfo_children():
            walk(c)

    walk(widget)
