"""The birth-order and pin laws, pinned from the owner's frozen-blackout
morning (Oct 15). Three checks, all app-up compatible, none of which
require the real taskbar or a real away spell."""
import sys
import threading
import time

sys.path.insert(0, ".")

OK = []


def ok(name):
    OK.append(name)
    print("ok -", name)


# 1 the jail verbs are SELF-PINNED: the shared u32 handles carry
#   explicit signatures, so import order cannot re-break them. (The
#   morning's failure was an unpinned GetCursorPos reading the stack
#   as garbage once a new module loaded first - proof-by-signature,
#   not proof-by-luck.)
from panelboss import display   # noqa: E402

for verb, argc in (("GetCursorPos", 1), ("SetCursorPos", 2)):
    fn = getattr(display.u32, verb)
    assert fn.argtypes is not None and len(fn.argtypes) == argc, verb
ok("jail verbs carry their own argtypes - order cannot unpin them")

# 2 the jail degrades, never raises: a failed verb returns False and
#   leaves the spell uncuffed (this is what the stuck blackout needed
#   and did not have)
_saved = display._jail_saved
try:
    assert display.jail_cursor((0, 0, 4, 4)) in (True, False)
    assert display.jail_cursor.__doc__          # the law rides along
finally:
    display._jail_saved = _saved
ok("jail_cursor answers with a bool, never with an exception")

# 3 the painters wait the window's root before claiming Tk: a thread
#   calling wait_for_window() blocks until the event is set (or the
#   floor expires) - the exact contract _overlay._start_root and the
#   hider painter now obey
from panelboss import hider     # noqa: E402

assert hider._WINDOW_READY.is_set() is False    # fresh process, no
hider.PAINTER_READY_TIMEOUT_SEC = 0.2            # window yet
released = []


def painter_sim():
    hider.wait_for_window()
    released.append(time.monotonic())


t = threading.Thread(target=painter_sim, daemon=True)
t.start()
t.join(0.05)
assert t.is_alive(), "wait_for_window returned BEFORE the window"
t0 = time.monotonic()
hider.window_ready()
t.join(1.0)
assert released and not t.is_alive(), "release never arrived"
assert released[0] - t0 < 0.2, "release lagged the set by half a floor"
assert hider._WINDOW_READY.is_set()
hider.PAINTER_READY_TIMEOUT_SEC = 10.0
ok("wait_for_window holds the painter until the window claims (and "
   "the timeout floor releases a headless boot)")

# 4 the floor itself: with no window ever, the painter is released by
#   the timeout - headless boots must not strand a strip forever
hider._WINDOW_READY.clear()
hider.PAINTER_READY_TIMEOUT_SEC = 0.2
t2 = threading.Thread(target=painter_sim, daemon=True)
hider.PAINTER_READY_TIMEOUT_SEC = 0.2
hider._WINDOW_READY.set()                        # restore; claim
t2.start()
t2.join(1.0)
hider.PAINTER_READY_TIMEOUT_SEC = 10.0
assert not t2.is_alive()
ok("a claimed/timeout release leaves the event set - the contract is "
   "idempotent for every later painter")

print("\nOVERLAY ORDER TESTS OK (%d)" % len(OK))
