"""The wake side: snapshot while lit, the move logic, the settle
wait, and the threaded restore. Formerly wm.py lines 954-1065, plus
`place` (lines 427-431, verbatim) - it is the public wrapper for
_move and lives beside it."""

import logging
import threading
import time

from ._inspect import _toplevel_facts, true_rect, wanted
from ._monitors import fingerprint, monitors
from ._rescue import lost
from ._winapi import (SWP_NOACTIVATE, SWP_NOZORDER, SWP_SHOWWINDOW,
                      SW_SHOWMAXIMIZED, SW_RESTORE, u32)

log = logging.getLogger("wm")


def place(hwnd, rect, zoomed=False):
    """Public wrapper for the move logic, so profiles do not import
    the private path."""
    return _move({"hwnd": hwnd, "rect": tuple(rect),
                  "zoomed": bool(zoomed)})


def unminimize(hwnd):
    """SW_RESTORE on a window the pin walk found LIVE but minimized
    (owner ruling, Oct 24 launch day: a minimized window is PRESENT
    - its seat is earned by restore-then-place, never by launching
    the exe again and blaming the launcher when the single-instance
    app answers nothing). The walk calls THIS before place(): the
    sequence (up, then positioned) is the same claim layout_test
    pins for _move; a zoomed seat rides place()'s dance from here
    with the window already upright. Returns ok/gone."""
    if not u32.IsWindow(hwnd):
        return "gone"                     # died under the walk
    u32.ShowWindow(hwnd, SW_RESTORE)
    return "ok"


def snapshot():
    """The desk as it truly is, while the screens are still on."""
    wins = [w for w in _toplevel_facts() if wanted(w)]
    snap = {"fp": fingerprint(), "ts": time.time(), "wins": wins}
    log.info("layout saved: %d windows, %d monitor%s",
             len(wins), snap["fp"].count("|") + 1 if snap["fp"] else 0,
             "" if snap["fp"].count("|") == 0 else "s")
    return snap


def _move(w):
    """Back to the saved rect - and back to the CAPTURED STATE:
    position AND minimization (owner ruling, Oct 23: restore means
    RESTORED). A maximized window cannot simply be moved (it fills
    its monitor by definition): restore to floating, move onto its
    OWN old monitor, maximize again - the result is maximized exactly
    where it lived, which is the whole point. THE MINIMIZE BIT IS
    THE CONTRACT, decided by the capture ALONE - no 'likely ours'
    heuristics about who minimized: the dark spell's own minimizing
    and a user's click mid-dark both leave the window
    currently-minimized-but-captured-open, and the contract answers
    both with the same word (up, then placed); a window captured
    minimized is the USER's state - honored, left exactly so. An OLD
    capture without the field (the bit is younger than some files on
    disk) restores POSITION ONLY and never guesses a show state: a
    window sitting minimized under a pre-bit record is left minimized
    (the SetWindowPos SHOWWINDOW flag would de-iconify it - a guess
    in code clothing), and one that is already visible is placed."""
    if not u32.IsWindow(w["hwnd"]) or not u32.IsWindowVisible(w["hwnd"]):
        return "gone"
    if u32.IsIconic(w["hwnd"]):
        _cap = w.get("iconic")
        if _cap is True:
            return "skip"                    # captured minimized: the
            #                                user's own state, honored
        if _cap is not False:
            # _cap None: a pre-bit record (the profiles/tray path
            # hands none) may not GUESS the show state, and the
            # SetWindowPos below would de-iconify it with its
            # SWP_SHOWWINDOW flag: the skip is the exact pre-0.3.6
            # answer. (_cap True returned above; live captures
            # screen iconic windows out via wanted() - the bit is
            # the belt for hand-made and future records.)
            return "skip"
        # captured OPEN: the un-minimize is PART of the restore,
        # not a second feature - the sequence (up, then place) is
        # pinned in layout_test; the zoomed dance below rides the
        # same SW_RESTORE a second time, harmless by law.
        u32.ShowWindow(w["hwnd"], SW_RESTORE)
    x, y, cx, cy = w["rect"]
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
    """Put back what the sleep cycle actually displaced. v2 (RDP
    incident): the old rule was "position differs from the snapshot,
    move it back" - which rolled back every window the user (or a
    third-party app re-persisting its own stale memory) had moved
    between snapshot and wake, canonizing the snatch forever. A
    window grabbly-on-screen at wake is wherever its owner wants it;
    we relocate only windows no monitor covers now, which is exactly
    what a scrambled wake stack produces. Same rect = Windows put it
    back itself, and arguing with that is how loops are born."""
    moved = kept = gone = skipped = 0
    mons = monitors()
    for w in snap["wins"]:
        cur = true_rect(w["hwnd"])
        if cur is None:
            gone += 1
            continue
        if cur == w["rect"]:
            kept += 1
            continue
        if mons and not lost(cur, mons):
            skipped += 1                   # moved since the snapshot,
            continue                       # still reachable: leave it
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
