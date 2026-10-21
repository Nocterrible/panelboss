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
asyncopen doctrine). ENUMERATE_DOOR_BUDGET_SEC (wave D: the probe's
own arithmetic, 2*27+5 - pinned as a spec here) shrinks to 0.5 s and
the whole enumeration must still land all rows, in order, inside
budget + margin of wall time, with the wedged index and every later
index reading dead and the pre-wedge index honest - and the on_row
beats answering once per resolved row. The hello IR bridge (the
19:33 fingerprint's TRUE home, the call one past the wave-C fence)
gets the same join at IR_BUDGET_SEC: stalled -> [] UNCACHEd + the
ONE warning the dialog's empty-board ear is built to repeat.
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

_saved_cv2 = cam_mod.cv2
_saved_budget = cam_mod.ENUMERATE_DOOR_BUDGET_SEC
_saved_ir = cam_mod.IR_BUDGET_SEC
cam_mod.cv2 = fake_cv2
cam_mod._bad_doors.clear()        # no tombstone interference offline

# the derivation itself is a spec (wave D): the enumerate budget is
# the PROBE's arithmetic (2 x the measured warm-open window + the
# named margin), not the duty's, and a copy-paste of the old 125
# would silently re-widen the veil prison this wave exists to kill.
check(abs(cam_mod.ENUMERATE_DOOR_BUDGET_SEC - (2 * 27.0 + 5.0)) < 1e-9,
      "the shipped enumerate budget is the debugger's derivation, "
      "2*27+5: %r" % cam_mod.ENUMERATE_DOOR_BUDGET_SEC)
cam_mod.ENUMERATE_DOOR_BUDGET_SEC = 0.5   # read at CALL time (the
                                          # camcore (c) doctrine:
                                          # patchable means live)
cam_mod.IR_BUDGET_SEC = 0.5
try:
    beats = []
    t0 = time.monotonic()
    rows = cam_mod.enumerate_cameras(0, 3, on_row=beats.append)
    took = time.monotonic() - t0
    check(took < 3.0,
          "the wedged door did NOT eat the board: enumerate returned "
          "in %.2f s (budget 0.5, margin 2.5)" % took)
    check(rows == [(0, True, 640.0), (1, False, 0.0), (2, False, 0.0)],
          "per-index honesty survives the wedge: index 0 answered "
          "true, index 1 (the zombie) AND every later index take the "
          "dead shape for this pass: %r" % (rows,))
    check(beats == rows,
          "on_row beats once per RESOLVED index, dead-tail included "
          "(the veil walks with the sweep): %r" % (beats,))
    check(any("outlived" in m and str(BLOCKED) in m for m in Grab.msgs),
          "the stall confessed in the log (warning, with the index)")
    # and the shape is STABLE: a fresh pass (the cache/rescan logic
    # aside) must answer again, not stay hung: same fake, the wedged
    # index is one Event-wait deeper but the budget again outruns it
    Grab.msgs.clear()
    t0 = time.monotonic()
    rows2 = cam_mod.enumerate_cameras(0, 3)
    took2 = time.monotonic() - t0
    check(rows2 == rows and took2 < 3.0,
          "the watchdog is not a one-shot: the next sweep answers the "
          "same honest rows in %.2f s" % took2)
    # ---- the ROOT FIX (wave D): the hello IR bridge gets the SAME
    # join. find_groups is MF enumeration - poisonable per process
    # (the 19:33 fingerprint's true home: one call past enumerate's
    # fence drowned the wave-C board twice on the dot) - so a find_
    # groups that blocks forever must answer [] inside the budget,
    # UNCACHEd: a stall is this round's truth, not the process's.
    import types as _types
    _ir_saved_mod = sys.modules.get("whircam")
    _ir_saved_cache = cam_mod._ir_names_cache
    hang = threading.Event()

    class _G:
        name = "IR One"

    fake_ir = _types.ModuleType("whircam")
    fake_ir.find_groups = lambda: (hang.wait(30.0), [])[1]
    sys.modules["whircam"] = fake_ir
    cam_mod._ir_names_cache = None
    Grab.msgs.clear()
    t0 = time.monotonic()
    names = cam_mod.hello_ir_names()
    took_ir = time.monotonic() - t0
    check(names == [] and took_ir < 3.0,
          "the stalled IR bridge answers [] inside its budget (%.2f s)"
          % took_ir)
    check(cam_mod._ir_names_cache is None,
          "the stall is NOT cached - the silent-ignorance sequel to "
          "the hang would be a permanent blind IR feature")
    check(any("outlived" in m and "hello IR bridge" in m
              for m in Grab.msgs),
          "the IR stall confessed the ONE warning (the dialog's ear "
          "repeats exactly this class of line)")
    # and an unstuck bridge answers normally through the same join
    fake_ir.find_groups = lambda: [_G()]
    cam_mod._ir_names_cache = None
    check(cam_mod.hello_ir_names() == ["IR One"],
          "the next call re-asks and a living bridge answers")
    sys.modules["whircam"] = _ir_saved_mod
    cam_mod._ir_names_cache = _ir_saved_cache
finally:
    cam_mod.cv2 = _saved_cv2
    cam_mod.ENUMERATE_DOOR_BUDGET_SEC = _saved_budget
    cam_mod.IR_BUDGET_SEC = _saved_ir
    cam_mod._bad_doors.clear()

# ---- the watcher's ears registration (gate-caught, pre-existing): the
# owner's desk died on it TWICE today ('display watcher died at
# startup' 08:25 and 11:18, ctypes.ArgumentError 'expected
# LP_RAWINPUTDEVICE instance instead of RAWINPUTDEVICE_Array_2'): the
# argtypes of the shared user32 function are a cross-module property,
# _inputtruth_hook re-binds them to ITS struct class when the pump
# installs, and display's raw array then raises through the pump
# thread. The pin runs the live order: the hook imported FIRST (its
# class binding in effect), then the watcher's own arm/disarm - the
# call must SURVIVE (the disease raised right here before the fix)
# and the 'died at startup' line must not speak. Real API call on the
# desktop's own HWND (INPUTSINK needs one); restored by the release
# arm the same test drives.
import ctypes
# THE LIVE ORDER IS THE TEST: display binds its class at boot import,
# the pump installs (rebinds to the hook's class) AFTER - so display
# first, the hook second. (A swapped pair lets display's import-time
# binding run last and the survival check passes UNFIXED - the teeth
# check below caught exactly that in its first draft.)
from panelboss import display as disp
from panelboss import _inputtruth_hook            # noqa: E402,F401

_disp_log = logging.getLogger("display")


class _Grab2(logging.Handler):
    msgs = []

    def emit(self, record):
        _Grab2.msgs.append(record.getMessage())


_g2 = _Grab2()
_disp_log.addHandler(_g2)
_active_saved = list(disp._ACTIVE)
_reg_saved = disp.u32.RegisterRawInputDevices.argtypes
# the pin's teeth: without the hook's binding ACTUALLY in effect on
# the shared function, the survival check would pass unfixed (a
# display-class binding lets display's own array through by
# construction). The hook module binds its OWN struct class at import
# (module line 157); assert that is what the call must survive.
# (Amended after the gate round: this check was first written against
# _inputtruth_hook.ctypes.POINTER, which the module never re-exports
# - an attribute accident, not an assertion; it now compares the
# documented rule directly, class identity across modules.)
check(_reg_saved is not None and len(_reg_saved) == 3
      and getattr(_reg_saved[0], "_type_", None)
      is _inputtruth_hook.RAWINPUTDEVICE,
      "the hook's OWN struct-class binding is in effect before the "
      "call (import order verified, not assumed): %r" % (_reg_saved,))
try:
    w = disp.Display(verbose=False)               # __init__ only, no run()
    # a real message-only sink ON THIS THREAD (the _run shape):
    # INPUTSINK's registration needs a window the calling thread
    # owns; GetDesktopWindow was judged 87 for exactly that reason,
    # and a registration that SUCCEEDS is the stronger pin
    _proc = disp.WNDPROTYPE(disp._def_window)     # keep the callback alive
    _wc = disp.WNDCLASSEX()
    _wc.cbSize = ctypes.sizeof(_wc)
    _wc.lpfnWndProc = _proc
    _wc.lpszClassName = "EnumwatchEarSink"
    disp.u32.RegisterClassExW(ctypes.byref(_wc))  # 1407 (already) is fine
    _hwnd = disp.u32.CreateWindowExW(0, "EnumwatchEarSink", None, 0,
                                     0, 0, 0, 0, disp.HWND_MESSAGE,
                                     None, ctypes.c_void_p(0), None)
    w._hwnd = _hwnd
    armed = None
    try:
        w._register_ears()                        # the line that killed the
        armed = w._hooked                         # pump thread at 08:25
    except ctypes.ArgumentError as e:
        armed = "ArgumentError: %s" % e
    check(armed is True,
          "the watcher's registration survives the hook's binding and "
          "the OS ACCEPTS it (pre-fix it raised ctypes.ArgumentError "
          "before the OS saw the call): %r" % (armed,))
    w._release_ears()
    check(w._hooked is False,
          "the disarm arm rides the same neutral call (no raise)")
    check(not any("died at startup" in m or "without a stop" in m
                  for m in _Grab2.msgs),
          "the death line stayed silent under the fake's order: %r"
          % _Grab2.msgs[-3:])
    # and the neutralization is the shipped shape: the call clears the
    # cross-module class binding (the ONLY order-safe arm the gate's
    # two candidates leaves - byref was measured to bounce off the
    # class check too, message changed, disease the same)
    check(disp.u32.RegisterRawInputDevices.argtypes is None,
          "the call did not neutralize the shared binding at call time")
finally:
    disp._ACTIVE[:] = _active_saved
    disp.u32.RegisterRawInputDevices.argtypes = _reg_saved
    _disp_log.removeHandler(_g2)

print("enumwatch-test: %d failure(s)" % len(fails))
sys.exit(1 if fails else 0)
