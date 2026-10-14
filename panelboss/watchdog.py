"""The join watchdog, engine-side (wave D: split OUT of camera.py the
moment the bounding laws grew past the +40-line growth rule the wave-C
gate named - a fix that only bounds verbs may not itself bloat the
bounded). The shape one wave after another keeps needing: run a verb
whose answer the DRIVER owns (cv2 opens, MF releases, WinRT group
enumeration) in a daemon thread, join with a deadline, and read a
timeout as the dead verdict - the engine's between-frames deadline
loops cannot help when the blocking call never returns AT ALL.

THE CALLER OF join_open MUST HOLD _open_lock across the call when
the op is a device-tree touch: the RLock is thread-owned, a child
re-acquiring would deadlock against the join that waits for it, and
the holder's shield is what serializes the driver while the child
works (the one exception is the hello IR bridge, whose enumeration
the CALLER now wraps in its own _open_timed - same shield, same
shape). A stalled child is ABANDONED: it keeps whatever handle
wedged it and dies with the process - you cannot pull a foot off a
train, but the BOARD can be pulled out of the station. A late
answering driver touch goes through the lock-honest paths the
caller's module provides (_release_cap defers; the next holder
drains), so the abandon never smuggles an unlocked touch back in.

The budgets are the caller-domain's own published worsts, named at
the call sites; the three door-class numbers ride here because
camera.py and the setup dialog must arm with the SAME arithmetic
(a deadline two files disagree about is a rumor twice).
"""

import logging
import threading

log = logging.getLogger("camera")   # the engine's voice: the stall
                                    # confession must land where the
                                    # door lines already live (and
                                    # where the setup dialog's
                                    # empty-board ear listens)

# a slow driver OPEN is not a reason for the whole subsystem to wedge
# (the camera module's doctrine, inherited): every budget below is a
# DOUBLE of a published measured worst plus a named margin, and all
# are read at CALL time by their users - the suites shrink them to
# watch the watchdog fire, which is exactly what the patch proves.
DOOR_BUDGET_SEC = 30.0 + 90.0 + 5.0     # the wave-C duty-class door
                             # cycle: the engine's lock deadline (30,
                             # camera.py's published acquisition
                             # worst) + the duty ceiling (90,
                             # OPEN_GRACE_SEC - a legitimate warm
                             # open measured at 38) + the named
                             # margin. find_camera and the deferred
                             # release keep it (wave D: "duty keeps
                             # the 125"); the enumeration probe got
                             # its own, smaller budget below.
ENUMERATE_DOOR_BUDGET_SEC = 2 * 27.0 + 5.0
                             # the debugger's derivation (wave D):
                             # the enumeration's auto-door probe is
                             # open+get ONLY (no warm, no delivery
                             # wait), and NVIDIA's measured warm-open
                             # window tops out at 27 s - two full
                             # windows + margin ~= 60; the 90 s
                             # grace is the DUTY ceiling and the 30 s
                             # lock term is not the join's to carry
                             # (it bounds WAITING, not WORKING - the
                             # _open_timed above the join already
                             # paid the waiting in its own shape).
IR_BUDGET_SEC = 20.0         # the hello IR bridge's find_groups: a
                             # ~1 s call that is poisonable PER
                             # PROCESS on this vcam-heavy desk (the
                             # 19:33 fingerprint's true home); the
                             # stall answer is [] and NOT cached -
                             # see camera.hello_ir_names


def join_open(op, budget, what):
    """Run op() under a timed join; return its verdict, or None for
    STALLED (the thread outlived the budget and was abandoned) or
    for a raised op (the raise is confessed, never bare-passed - an
    op's death is the door's verdict of no, the same dead shape).
    THE CALLER MUST HOLD _open_lock when the op touches the device
    tree (docstring top)."""
    box = []

    def run():
        try:
            box.append(op())
        except Exception:
            log.exception("door op for %s raised - the door's own no",
                          what)
            box.append(None)

    t = threading.Thread(target=run, daemon=True,
                         name="door-join-%s" % (what,))
    t.start()
    t.join(budget)
    if box:
        return box[0]
    log.warning("door op for %s outlived its %.0f s join budget - "
                "reported dead, the zombie keeps the handle",
                what, budget)
    return None
