"""Wake frames: the opt-in diagnostic for a wake nobody asked for.

WHY (first field bug, Oct 26): a false-positive wake was only ever
seen as a score in the log - a blanket on a chair read as a person,
the counters said the desk woke forty-one times, and none of them
could say WHAT the eye saw. The counters were theater; the picture
is the evidence, and this module keeps it long enough to look.

THE PROMISE: the log of who-woke-it (time, camera, confidence) is
always kept, in memory only; frames are kept only while the switch
is on; nothing is ever written to disk; all of it dies on restart.
"""

import logging
import threading
import time
from collections import deque

import cv2

log = logging.getLogger("state")

RING_MAX = 5          # five rows is the whole history
JPEG_QUALITY = 82     # good enough to name a blanket as a blanket

_lock = threading.Lock()
_ring = deque(maxlen=RING_MAX)
_pending = None       # the newest present verdict: text always, the
                      # picture only under the switch (one slot, the
                      # freshest verdict wins)
_enabled = False      # [camera] wake_snap: set at load, flipped by the UI


def set_enabled(on):
    """The switch, wired from the config at load and by the UI on apply."""
    global _enabled
    _enabled = bool(on)


def remember(frame_bgr, score, cam_label):
    """Replace the pending slot at the verdict's own moment. Never
    raises: an encode that dies is a diagnostic about a diagnostic
    (the one swallow that stays debug), and the text row still stands
    without the picture."""
    global _pending
    jpg = None
    if _enabled:
        try:
            ok, buf = cv2.imencode(".jpg", frame_bgr,
                                   [int(cv2.IMWRITE_JPEG_QUALITY),
                                    JPEG_QUALITY])
            if ok:
                jpg = buf.tobytes()
        except Exception as exc:
            log.debug("wakesnap: the encode died (%s); text row only", exc)
    with _lock:
        _pending = {"ts": time.time(), "score": float(score),
                    "cam": str(cam_label), "jpg": jpg}


def wake(score=None):
    """The ring's only writer, called at every wake, whatever the
    switch says. A truthy score means a camera verdict drove it and
    the row rides the pending slot - the frame's own moment, label,
    and (under the switch) picture. A falsy score is the input branch
    (the typing arm's None, the away-lift and unlock events' 0.0): no
    camera claim drove this wake, so a pending slot - fresh or stale
    - says nothing about why the desk woke, gets dropped, and the row
    names the input. Truthy score with no pending slot writes a bare
    camera row. Rows may carry jpg=None: the wake predates the switch."""
    global _pending
    with _lock:
        item, _pending = _pending, None
        if item is None or not score:
            item = {"ts": time.time(),
                    "score": None if not score else float(score),
                    "cam": "input" if not score else "camera",
                    "jpg": None}
        _ring.append(item)


def frames():
    """The ring, newest first. An entry may carry jpg=None (the text-
    only classes wake() names): viewers caption those without art."""
    with _lock:
        return list(reversed(_ring))
