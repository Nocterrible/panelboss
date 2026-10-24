"""The rescue: windows no screen covers come back to the primary.
Formerly wm.py lines 903-951. v2 (RDP incident, Oct 11): a sliver
inside the canvas counts as lost, and minimized windows get their
stale restore spot repaired without ever being un-minimized."""

import ctypes
import logging

from ._inspect import _toplevel_facts
from ._monitors import monitors
from ._winapi import (LOST_EDGE, SWP_NOACTIVATE, SWP_SHOWWINDOW,
                      SW_RESTORE, WINDOWPLACEMENT, byref, k32, sizeof,
                      u32)

log = logging.getLogger("wm")

GRAB_EDGE = 64                 # horizontal pixels enough for a human
                               # to click-drag a title bar; the RDP
                               # incident's chat window rode at 7 -
                               # technically visible, practically
                               # unreachable


# ----------------------------------------------------------- rescue -----
def lost(rect, mons):
    """Pure decision (testable): a rectangle no monitor shows a
    grabbable piece of belongs to a window nobody can reach. Stolen
    from monitor_control's WindowRescue, disqualifiers and all; v2
    raised the bar from "no intersection" to "less than a title-bar
    grab of intersection" (measured: a 7px sliver shrugged off
    rescue for three sleep cycles while its owner chased it)."""
    x, y, cx, cy = rect
    for m in mons:
        ix = min(x + cx, m["x"] + m["w"]) - max(x, m["x"])
        iy = min(y + cy, m["y"] + m["h"]) - max(y, m["y"])
        if ix >= GRAB_EDGE and iy >= LOST_EDGE:
            return False
    return True


def _repair_minimized(w, mons, prim):
    """A minimized window's visible rect is the sentinel
    (-32000, -32000); what matters is where it AGREES to land when
    restored (GetWindowPlacement's rcNormalPosition). A desk swap
    makes that memory stale - the taskbar click then restores into
    the void. Rewrite the placement, not the window: showCmd rides
    along, so it stays minimized and the NEXT restore lands on the
    canvas."""
    wp = WINDOWPLACEMENT()
    wp.length = sizeof(wp)
    if not u32.GetWindowPlacement(w["hwnd"], byref(wp)):
        log.debug("rescue: placement unreadable for %s", w.get("title")
                  or w.get("proc") or "?")
        return False
    l, t = wp.rcNormalPosition.left, wp.rcNormalPosition.top
    cx = wp.rcNormalPosition.right - l
    cy = wp.rcNormalPosition.bottom - t
    if cx < LOST_EDGE or cy < LOST_EDGE:
        return False                       # nothing to grab anyway
    if not lost((l, t, cx, cy), mons):
        return False
    cx, cy = min(cx, prim["w"]), min(cy, prim["h"])
    nl = prim["x"] + max(0, (prim["w"] - cx) // 2)
    nt = prim["y"] + max(0, (prim["h"] - cy) // 2)
    wp.rcNormalPosition.left, wp.rcNormalPosition.top = nl, nt
    wp.rcNormalPosition.right, wp.rcNormalPosition.bottom = \
        nl + cx, nt + cy
    return bool(u32.SetWindowPlacement(w["hwnd"], byref(wp)))


def rescue_lost():
    """Every visible, grabbable window no screen covers comes back to
    the middle of the primary monitor (the C# original returns it to
    the nearest one; the ask here was explicitly "center of the
    primary"). Cloaked (other virtual desktop) windows are the port's
    one addition: their coordinates are honest, they just live on
    another desktop - dragging them across is not a rescue. Minimized
    windows are no longer skipped outright (v2): their sentinel rect
    is meaningless, so they are judged by placement instead - see
    _repair_minimized."""
    mons = monitors()
    if not mons:
        return []
    prim = next((m for m in mons if m["primary"]), mons[0])
    brought, repaired, denied = [], [], []
    for w in _toplevel_facts():
        if not w["visible"] or w["cloaked"] or w["furniture"]:
            continue
        if w.get("pid") == k32.GetCurrentProcessId():
            # the rescue never touches our own windows - every one
            # is parked where we put it (Oct-13 broadcast law; the
            # white-box rescue is the confession). Own minimized
            # placement-repair is lawfully forfeit with the skip.
            continue
        name = (w["title"] or w["proc"] or "(untitled)").strip()[:48]
        if w["iconic"]:
            if _repair_minimized(w, mons, prim):
                repaired.append(name)
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
            brought.append(name)
        elif ctypes.GetLastError() == 5:        # ERROR_ACCESS_DENIED:
            # an elevated window above our integrity (UIPI) - the
            # rescue is not blind, it is out-ranked. Say which, and
            # say why: a silent miss reads as a broken tool, which
            # is exactly what the owner experienced with an
            # elevated Task Manager at 22:27.
            denied.append("(denied: elevated) " + name)
    msg = []
    if brought:
        msg.append("brought back " + ", ".join(brought))
    if repaired:
        msg.append("re-stored the off-desk spot of " + ", ".join(repaired))
    if denied:
        msg.append("out-ranked by " + ", ".join(denied))
    log.info("rescue: %s", "; ".join(msg)[:300] if msg
             else "nothing was off screen")
    return (brought + ["(min) " + n for n in repaired]
            + denied)
