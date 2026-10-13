"""Camera-core probe for the W2B deltas (the audit's MED cluster).

(a) W3A: release is lock-free ownership. Camera.release() no longer
    queues behind the open's deadlined lock; the null-first swap hands
    the cap to exactly one caller, so two threads hammering release()
    50 rounds each on ONE fake-cap camera drive the driver's let-go
    exactly ONCE, however many times it is called, with no
    AttributeError (the gate 2b two-waiter shape).
(b) DELTA 2: a BaseException (cv2's C++ raise paths can surface one)
    in the opener's factory reaps the worker's inflight row - the eye
    is never left "opening" forever - records it exactly as the
    dead-open footprint (failed), and STILL re-raises so the daemon
    dies honestly. A plain Exception keeps the old swallow.
(c) DELTA 1: _open_lock still has a deadline (OPEN_LOCK_TIMEOUT). A
    holder wedging the lock past it makes the open ABSTAIN: the
    not-opened handle (is_open() False - the module's dead-corpse
    shape _open_door already documents), the confession logged, and
    the CALLER never waits out the holder. The constant is
    monkeypatched to 0.2 s so the probe is fast; the deadline logic
    reads it at call time, which is exactly what the patch proves.
    (The _cams adoption nulls the store row on the same principle;
    multi_cam/asyncopen already drive that seam.)
"""
import logging
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panelboss import camera as cam_mod

logging.basicConfig(level=logging.INFO,
                    format="probe| %(levelname)s %(name)s: %(message)s")


class Grab(logging.Handler):
    msgs = []

    def emit(self, record):
        Grab.msgs.append(record.getMessage())


for _name in ("camera", "state"):
    logging.getLogger(_name).addHandler(Grab())


def saw(sub):
    return any(sub in m for m in Grab.msgs)


class FakeCap:
    """The corpse-shape stand-in: opens, reports a tiny frame size,
    counts its releases (the driver's slow let-go would live here)."""

    def __init__(self):
        self.releases = 0

    def isOpened(self):
        return True

    def get(self, _prop):
        return 8.0

    def release(self):
        self.releases += 1


def probe_abstain():
    cap = FakeCap()
    saved_door = cam_mod._open_door
    cam_mod._open_door = lambda *a, **k: (cap, "dshow")
    held = threading.Event()
    release = threading.Event()

    def holder():                      # a wedged driver open: it owns
        with cam_mod._open_lock:       # the tree and will not answer
            held.set()
            release.wait(5.0)

    th = threading.Thread(target=holder, daemon=True, name="wedged")
    th.start()
    assert held.wait(2.0), "the holder never took the lock"
    saved = cam_mod.OPEN_LOCK_TIMEOUT
    cam_mod.OPEN_LOCK_TIMEOUT = 0.2    # read at CALL time by _open_timed
    try:
        t0 = time.monotonic()
        cam = cam_mod.open_camera({"index": 0})
        took = time.monotonic() - t0
        assert took < 1.0, ("open waited out the holder (%.2f s), not "
                            "its deadline" % took)
        assert cam is not None and not cam.is_open(), \
            "the abstain shape must be the not-opened handle"
        assert saw("camera open locked past"), "the abstain did not confess"
        assert cap.releases == 0, "the door never ran while the lock stayed"
    finally:
        cam_mod.OPEN_LOCK_TIMEOUT = saved
        release.set()
        th.join(3.0)
        cam_mod._open_door = saved_door


def probe_reap():
    seen = {}
    saved_hook = threading.excepthook

    def hook(args):
        seen["exc"] = args.exc_value

    def boom(index):                   # a C++ raise surrogate: a death
        raise KeyboardInterrupt("cv2 raise path")   # below except-Exception

    def dies(index):                   # the old, ordinary dead open
        raise ValueError("driver said no")

    threading.excepthook = hook
    try:
        op = cam_mod.AsyncOpener(boom)
        assert op.open_async(0) is None
        deadline = time.monotonic() + 2.0
        while op.inflight and time.monotonic() < deadline:
            time.sleep(0.02)
        assert 0 not in op.inflight, \
            "BaseException stranded the row: the eye stays opening forever"
        assert 0 in op.failed, "the reap must take the dead-open footprint"
        assert op.held.get(0) is None, "no phantom handle behind the row"
        assert not op.inflight_live(), "a reaped row cannot pin the lease"
        assert isinstance(seen.get("exc"), KeyboardInterrupt), \
            "the re-raise died with the worker: the daemon's death must " \
            "stay visible, not be swallowed by the reap"
        # the plain-Exception path keeps the OLD shape: reap, failed,
        # and NO re-raise (the factory logged its own abstain already)
        seen.clear()
        op2 = cam_mod.AsyncOpener(dies)
        assert op2.open_async(1) is None
        deadline = time.monotonic() + 2.0
        while op2.inflight and time.monotonic() < deadline:
            time.sleep(0.02)
        assert 1 not in op2.inflight and 1 in op2.failed, \
            "the ordinary dead open changed shape"
        assert "exc" not in seen, "plain Exception must not re-raise"
    finally:
        threading.excepthook = saved_hook


def probe_one_release():
    """(a) W3A: the lock-free ownership swap. Two threads hammer ONE
    Camera's release() 50 rounds each (gate 2b's two-waiter shape,
    stress-timed): the null-first swap elects exactly one winner, so
    the fake cap counts ONE release ever, and a loser on a nulled cap
    must not AttributeError."""
    shared = FakeCap()
    saved_door = cam_mod._open_door
    cam_mod._open_door = lambda *a, **k: (shared, "dshow")
    try:
        cam = cam_mod.Camera(index=0)
        assert cam.is_open(), "the fake door must read open"
        errors = []

        def hammer():
            try:
                for _ in range(50):
                    cam.release()
            except BaseException as exc:      # the old None.release()
                errors.append(exc)            # race lands here

        threads = [threading.Thread(target=hammer, daemon=True,
                                    name="hammer%d" % i)
                   for i in (1, 2)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(10.0)
        assert not any(th.is_alive() for th in threads), \
            "a hammer never finished"
        assert not errors, "release raised across the swap: %r" % errors[0]
        assert shared.releases == 1, \
            ("double release: the cap left the shop %d times"
             % shared.releases)
        assert cam.cap is None, "null by construction"
        assert not cam.is_open(), "a released Camera is a dead Camera"
    finally:
        cam_mod._open_door = saved_door


probe_one_release()
print("probe| (a) two threads, one release, no AttributeError: OK")
probe_reap()
print("probe| (b) BaseException reaps the opening row: OK")
probe_abstain()
print("probe| (c) locked-past-deadline abstains: OK")
print("camcore probe: 3/3 OK")
