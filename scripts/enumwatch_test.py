"""The enumeration's join watchdog (owner UAT, wave C): the third
virgin launch re-hung the setup screen at the byte-for-byte 18:33
fingerprint - assign-gather opens camera 1 through the fallback door,
one log line, then NOTHING - because enumerate_cameras ran
_open_door + cap.get + release UNBOUNDED while holding the device-
tree lock: the deadline covered only the ACQUISITION, never the
working verb. The engine got the wave-A join: the door cycle runs in
a joined thread, the stalled index answers the dead shape (opened=
False - the very row the hung-holder branch already produced), and
the sweep stops there rather than probing beside the zombie (two
threads opening at once is the measured driver death this lock
exists to prevent).

Offline, fake cv2 only - no real doors, no LED on the owner's desk.
Fake shape: VideoCapture blocks FOREVER (bounded 30 s for test
hygiene) on the poisoned index; every other index opens DSHOW-first
and serves a bright frame (GRAY 128 clears BLACK_CEIL, the
asyncopen doctrine). DOOR_BUDGET_SEC shrinks to 0.5 s and the whole
enumeration must still land all rows, in order, inside budget +
margin of wall time, with the wedged index and every later index
reading dead and the pre-wedge index honest.
"""
import logging
import os
import sys
import threading
import time
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from panelboss import camera as cam_mod

fails = []


def check(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


class Grab(logging.Handler):
    msgs = []

    def emit(self, record):
        Grab.msgs.append(record.getMessage())


logging.getLogger("camera").addHandler(Grab())

BLOCKED = 1                       # the DroidCam-class index whose MF
                                  # door never comes back


class FakeVideoCapture:
    def __init__(self, index, *args):
        if index == BLOCKED:
            # the wedge: the interprocess mutex inside the plugin,
            # held past every sane deadline. Bounded at 30 s purely
            # for test hygiene (a daemon zombie must not outlive a
            # CI box); every join in here is far shorter.
            threading.Event().wait(30.0)
        self.index = index
        self.released = 0

    def isOpened(self):
        return True

    def set(self, *args):
        pass

    def get(self, prop):
        return 640.0

    def read(self):
        return True, np.full((8, 8, 3), 128, np.uint8)

    def release(self):
        self.released += 1


class FakeVideoWriter:
    @staticmethod
    def fourcc(*c):
        return 0


fake_cv2 = types.ModuleType("cv2")
fake_cv2.VideoCapture = FakeVideoCapture
fake_cv2.VideoWriter = FakeVideoWriter
fake_cv2.CAP_DSHOW = 200
fake_cv2.CAP_PROP_FRAME_WIDTH = 3
fake_cv2.CAP_PROP_FRAME_HEIGHT = 4
fake_cv2.CAP_PROP_FOURCC = 6

_saved_cv2, _saved_budget = cam_mod.cv2, cam_mod.DOOR_BUDGET_SEC
cam_mod.cv2 = fake_cv2
cam_mod.DOOR_BUDGET_SEC = 0.5     # read at CALL time (the camcore (c)
                                  # doctrine: patchable means live)
cam_mod._bad_doors.clear()        # no tombstone interference offline
try:
    t0 = time.monotonic()
    rows = cam_mod.enumerate_cameras(0, 3)
    took = time.monotonic() - t0
    check(took < 3.0,
          "the wedged door did NOT eat the board: enumerate returned "
          "in %.2f s (budget 0.5, margin 2.5)" % took)
    check(rows == [(0, True, 640.0), (1, False, 0.0), (2, False, 0.0)],
          "per-index honesty survives the wedge: index 0 answered "
          "true, index 1 (the zombie) AND every later index take the "
          "dead shape for this pass: %r" % (rows,))
    check(any("outlived" in m and str(BLOCKED) in m for m in Grab.msgs),
          "the stall confessed in the log (warning, with the index)")
    # and the shape is STABLE: a fresh pass (the cache/resec logic
    # aside) must answer again, not stay hung: same fake, the wedged
    # index is one Event-wait deeper but the budget again outruns it
    Grab.msgs.clear()
    t0 = time.monotonic()
    rows2 = cam_mod.enumerate_cameras(0, 3)
    took2 = time.monotonic() - t0
    check(rows2 == rows and took2 < 3.0,
          "the watchdog is not a one-shot: the next sweep answers the "
          "same honest rows in %.2f s" % took2)
finally:
    cam_mod.cv2 = _saved_cv2
    cam_mod.DOOR_BUDGET_SEC = _saved_budget
    cam_mod._bad_doors.clear()

print("enumwatch-test: %d failure(s)" % len(fails))
sys.exit(1 if fails else 0)
