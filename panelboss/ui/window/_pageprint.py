"""Page stills for the tab switch: the incoming page's own pixels.

WHY (owner ruling, Oct 25 - "the UI redraws from bottom right to top
left are still prevalent whenever switching tabs"). Measured with a
52 fps camera (2,677 frames, a 32x24 paint map): a switch does NOT paint
the page in one frame - the raised page's ~300 child windows paint one
reveal frame at a time, 1.3-2.9 s of wall clock here, newest widget
first. Forcing the paint (the RDW_* forms) measured 5x Tk's own pass and
made it worse, so the cure makes the paint land on VISIBLE-IDENTICAL
pixels instead: the incoming page is imaged and that image rides the
flat backdrop the switch already raises.

THE ONE CAMERA IS THE GLASS. `screen_bitmap` takes the screen at the
page's rect in 15 ms, which is truthful at exactly one moment - the page
is on the glass, settled, and being LEFT - so that is when the cache is
built, and `rect_is_ours` refuses the grab when the point is not ours.

The offscreen camera was TRIED AND FALSIFIED: PrintWindow renders a
Tk/CTk page INCOMPLETELY - its 2,677-frame film shows whole card rows
arriving as unpainted white blocks (child canvases that never answer
WM_PRINTCLIENT), so a "still" from that path is a visible artifact, not a
cover. It is not kept as a fallback: no still means the flat backdrop and
the old progressive paint, which is exactly the pre-fix behaviour.
"""
from __future__ import annotations

import logging

from ._gdiraw import (GA_ROOT, OK, POINT, SRCCOPY, blit_to_image, gdi32,
                      user32)

log = logging.getLogger("ui")


def screen_bitmap(x, y, w, h):
    """The glass at a screen rect: the composited truth, children and
    all, in ~15 ms. Only correct while that rect IS visible - the caller
    owns that guard (see rect_is_ours)."""
    if not OK or w < 8 or h < 8:
        return None
    return blit_to_image(w, h, lambda mdc, sdc: gdi32.BitBlt(
        mdc, 0, 0, w, h, sdc, int(x), int(y), SRCCOPY))


def rect_is_ours(widget):
    """WHOSE PIXELS ARE AT THAT POINT? The screen camera's guard, asked
    directly instead of guessed from focus: WindowFromPoint returns the
    topmost window at a screen point, so if that window's root ancestor
    is not ours, the glass at this rect belongs to somebody else and
    photographing it would cache a picture of their window. (The
    alternative, GetForegroundWindow, was measured WRONG for this job:
    a process that does not hold focus cannot be foreground even while
    its window is visibly on top of the desktop, which is how every
    probe in this repo runs.) Unknown answers False: no still beats a
    lie."""
    if not OK:
        return False
    try:
        root = user32.GetAncestor(widget.winfo_id(), GA_ROOT)
        pt = POINT(widget.winfo_rootx() + widget.winfo_width() // 2,
                    widget.winfo_rooty() + widget.winfo_height() // 2)
        hit = user32.WindowFromPoint(pt)
        return bool(hit) and user32.GetAncestor(hit, GA_ROOT) == root
    except Exception:
        return False
