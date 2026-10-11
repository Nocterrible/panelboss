"""The wake side: snapshot while lit, the move logic, the settle
wait, and the threaded restore. Formerly wm.py lines 954-1065, plus
`place` (lines 427-431, verbatim) - it is the public wrapper for
_move and lives beside it."""

import logging
import threading
import time

from ._inspect import _toplevel_facts, true_rect, wanted
from ._monitors import fingerprint
from ._winapi import (SWP_NOACTIVATE, SWP_NOZORDER, SWP_SHOWWINDOW,
                      SW_SHOWMAXIMIZED, SW_RESTORE, u32)

log = logging.getLogger("wm")


def place(hwnd, rect, zoomed=False):
    """Public wrapper for the move logic, so profiles do not import
    the private path."""
    return _move({"hwnd": hwnd, "rect": tuple(rect),
                  "zoomed": bool(zoomed)})


def snapshot():
    """The desk as it truly is, while the screens are still on."""
    wins = [w for w in _toplevel_facts() if wanted(w)]
    snap = {"fp": fingerprint(), "ts": time.time(), "wins": wins}
    log.info("layout saved: %d windows, %d monitor%s",
             len(wins), snap["fp"].count("|") + 1 if snap["fp"] else 0,
             "" if snap["fp"].count("|") == 0 else "s")
    return snap


def _move(w):
    """Back to the saved rect. A maximized window cannot simply be
    moved (it fills its monitor by definition): restore to floating,
    move onto its OWN old monitor, maximize again - the result is
    maximized exactly where it lived, which is the whole point."""
    if not u32.IsWindow(w["hwnd"]) or not u32.IsWindowVisible(w["hwnd"]):
        return "gone"
    if u32.IsIconic(w["hwnd"]):
        return "skip"                        # minimized in the dark by
    x, y, cx, cy = w["rect"]                 # somebody/something: leave
    if w["zoomed"]:
        u32.ShowWindow(w["hwnd"], SW_RESTORE)
    # (NOZORDER | NOACTIVATE | SHOWWINDOW) - NOOWNERZORDER measured
    # to die with 1004 whatever the insert-after slot holds; with
    # NOZORDER set, hwndInsertAfter itself is ignored, so None rides.
    if not u32.SetWindowPos(w["hwnd"], None, x, y, cx, cy,
                             SWP_NOZORDER | SWP_NOACTIVATE
                             | SWP_SHOWWINDOW):
        return "fail"                      # died under us
    if w["zoomed"]:
        u32.ShowWindow(w["hwnd"], SW_SHOWMAXIMIZED)
    return "ok"


def apply(snap):
    """Move everything back. Same rect already = Windows put it back
    itself, and arguing with that is how loops are born."""
    moved = kept = gone = skipped = 0
    for w in snap["wins"]:
        cur = true_rect(w["hwnd"])
        if cur is None:
            gone += 1
            continue
        if cur == w["rect"]:
            kept += 1
            continue
        result = _move(w)
        if result == "ok":
            moved += 1
        elif result == "gone":
            gone += 1
        else:
            skipped += 1
    log.info("layout restored: %d moved, %d already right, %d gone, "
             "%d left alone", moved, kept, gone, skipped)
    return moved, kept, gone, skipped


SETTLE_SEC = 4.0             # the fingerprint must sit unchanged this
WAIT_BUDGET_SEC = 60.0       # long before the desk is rebuilt


def wait_settled(budget=WAIT_BUDGET_SEC, stable=SETTLE_SEC,
                 cancel=None):
    """Poll the topology until it is quiet for `stable` seconds;
    returns the final fingerprint (the caller compares it against
    the saved one). Never applies mid-storm. `cancel` aborts early
    (a newer snapshot superseded this one)."""
    deadline = time.monotonic() + budget
    last, quiet_since = None, None
    while True:
        time.sleep(1.0)
        fp = fingerprint()
        now = time.monotonic()
        if cancel is not None and cancel():
            return None
        if fp != last:
            last, quiet_since = fp, None
        elif quiet_since is None:
            quiet_since = now
        elif now - quiet_since >= stable:
            return fp
        if now > deadline:
            return fp                        # caller checks identity


def restore(snap, cancel=None):
    """Wait for the desk to come back exactly as saved, then move
    everything. Synchronous; restore_async wraps it in the helper
    thread the state machine needs."""
    try:
        fp = wait_settled(cancel=cancel)
        if fp is None:
            log.info("layout restore superseded by a newer snapshot")
            return "superseded"
        if fp != snap["fp"]:
            log.info("topology changed in the dark (%s) - saved "
                     "positions belong to another desk; not moving",
                     fp or "no display?")
            return "topology"
        apply(snap)
        return "applied"
    except Exception:
        log.exception("layout restore crashed; the desk is on its own")
        return "crashed"


def restore_async(snap, cancel=None):
    """Helper thread: the wait is seconds-long and the monitor loop
    must keep polling the camera through it."""
    threading.Thread(target=restore, args=(snap, cancel),
                     daemon=True, name="wm-restore").start()
