"""The rescue: windows no screen covers come back to the primary.
Formerly wm.py lines 903-951."""

import logging

from ._inspect import _toplevel_facts
from ._monitors import monitors
from ._winapi import (LOST_EDGE, SWP_NOACTIVATE, SWP_SHOWWINDOW,
                      SW_RESTORE, u32)

log = logging.getLogger("wm")


# ----------------------------------------------------------- rescue -----
def lost(rect, mons):
    """Pure decision (testable): a rectangle no monitor intersects
    belongs to a window nobody can reach. Stolen from
    monitor_control's WindowRescue, disqualifiers and all."""
    x, y, cx, cy = rect
    for m in mons:
        if (x < m["x"] + m["w"] and x + cx > m["x"]
                and y < m["y"] + m["h"] and y + cy > m["y"]):
            return False
    return True


def rescue_lost():
    """Every visible, not-minimized, grabbable window that no screen
    covers comes back to the middle of the primary monitor (the C#
    original returns it to the nearest one; the ask here was
    explicitly "center of the primary"). Cloaked (other virtual
    desktop) windows are the port's one addition: their coordinates
    are honest, they just live on another desktop - dragging them
    across is not a rescue."""
    mons = monitors()
    if not mons:
        return []
    prim = next((m for m in mons if m["primary"]), mons[0])
    brought = []
    for w in _toplevel_facts():
        if not w["visible"] or w["iconic"] or w["cloaked"] \
                or w["furniture"]:
            continue
        r = w["rect"]
        if not r or r[2] < LOST_EDGE or r[3] < LOST_EDGE:
            continue
        if not lost(r, mons):
            continue
        x, y, cx, cy = r
        cx = min(cx, prim["w"])
        cy = min(cy, prim["h"])
        nx = prim["x"] + max(0, (prim["w"] - cx) // 2)
        ny = prim["y"] + max(0, (prim["h"] - cy) // 2)
        if w["zoomed"]:
            u32.ShowWindow(w["hwnd"], SW_RESTORE)
        if u32.SetWindowPos(w["hwnd"], None, nx, ny, cx, cy,
                            SWP_NOACTIVATE | SWP_SHOWWINDOW):
            brought.append((w["title"] or w["proc"] or
                            "(untitled)").strip()[:48])
    log.info("rescue: %s", ("brought back " + ", ".join(brought))[:200]
             if brought else "nothing was off screen")
    return brought
