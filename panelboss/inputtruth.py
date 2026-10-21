"""The input-TRUTH pump: the app's own idle clock (Oct-20 wave).

Why this exists (the desk receipts, Temp\\opencode\\ Oct 20): the
owner's desk read NEVER idle on the stock clock for a full working
day. GetLastInputInfo aged ZERO (0.00-0.05 s) continuously while the
desk sat hands-off and the cursor pixel-frozen - through a
three-receipt hunt (unplug.log / direct.log / nohid.log / nohid2.log)
that first blamed the KVM box and landed, at the desk itself, on a
3-button macropad whose firmware was STUCK re-reporting the mouse
with zero travel; a physical replug reset it and the clock now ages
honestly. The stamper was transient; the CLASS is permanent (pads,
KVMs, jigglers, and whatever ships next), so the pump ships as
INSURANCE, not repair - opt-in (default ON, the owner's explicit
override of the default-off law: default-on plus fail-open means
the worst case equals the old behavior, which is what justified the
override), and its failure path IS the old behavior.

THE MECHANISM (owner ruling, Oct 20, closing the mode debate): RAW
INPUT ONLY - WH_*_LL hooks cost every input event on the desk a ~31
ms dispatch quantum (measured law, display.py:16-23), so the ear is
a RIDEV_INPUTSINK registration on a thread of its own (the module
_inputtruth_hook carries the ctypes and the proven display shape).
THE FILTER, pure and hook-free below:
  - a keydown counts (a MAKECODE with the BREAK bit clear; a release
    proves nothing a press did not already prove);
  - a pointer counts when it has TRAVELED >= DEAD_ZONE_PX since the
    last count - CUMULATIVE across reports (a high-resolution mouse
    legitimately streams sub-3 px deltas: per-report thresholds
    would never fire on it, and a slow drag would hide), so the
    zero-travel pad-chatter stream of the receipts is invisible by
    construction, and any real motion - however gentle - accumulates
    across and stamps;
  - absolute-position reports (touch panels) count by the anchor
    delta: the owner's finger moved the pointer, that is travel;
  - INJECTED input never counts as a hand: the kernel's marker is
    the documented NULL hDevice on the raw header (probe-confirmed
    Oct 20: every SendInput packet arrived hDevice-less) and the
    TERMSRV_SHADOW keyboard flag (RDP's twin). The ears drop both
    BEFORE the pump sees them - and this is what the exemption
    below is for.
  - BOOT = INFINITE idle, not "now": the pump has no truth until a
    report passes the filter; a fresh process does not claim the
    desk was just touched (the rails read past at boot, honestly,
    the way the app's first seconds have always read them);
  - fail-open: if the ear cannot install (a service session, a dead
    window station) or its thread dies, idle_seconds() answers the
    STOCK display.idle_seconds() and says ONE DATED WARNING LINE -
    deaf, not lying silently.

THE WAKE EXEMPTION (owner ruling, Oct 20, the off-phase only):
  'Injected input produces no device packets. So: if the stock clock
  (GetLastInputInfo) moved while the pump observed ZERO raw device
  packets in the same interval, whatever moved it was injection -
  count it as input. During real device traffic (any packets, even
  zero-travel pad lies), the pump's verdict alone governs.'
wake_idle_seconds() carries it; ONLY the screens-off wake consumes
it (state/_boot.py's off-phase call) - the away trigger and the
theater conjunct keep the pump's unexempted verdict, because a
remote hand must not count as a human AT the desk, only as a knock
on the door it already dimmed. Admitted corner, in the same
sentence: injection arriving amid pad-chatter does not wake - the
camera's presence eye and a click on the dark desk remain the
documented recovery (both predate the pump and neither leans on
this clock).

The core is a pure class: the suite feeds it synthetic packets with
its own fake clock (no ctypes, no hooks, no sleeps), and the real
ear earns only a smoke test - install, unstall, survive an idle
desk. See videoeye_test.py's pump section for the whole law in
executable shape.
"""
import logging
import threading
import time

log = logging.getLogger("inputtruth")

DEAD_ZONE_PX = 3          # cumulative travel that counts (winuser.h
#                          # deltas are physical px)
WAKE_WINDOW_SEC = 1.0     # the off-phase wake's window (the same
#                          # 1.0 the _phase off-phase reads; the
#                          # twin is pinned in the wake docstring)
# winuser.h flag words the filter reads (the ears import these; one
# source of truth for the constants, pure of ctypes)
RI_KEY_BREAK = 0x01       # the release twin of a make code
RI_KEY_E0 = 0x02          # the extended-key report bits: the MAKE
RI_KEY_E1 = 0x04          # logic reads the make code, not these
RI_KEY_TERMSRV_SHADOW = 0x10   # RDP-injected: not a local hand
MOUSE_MOVE_ABSOLUTE = 0x01  # position reports (touch): anchor-delta
MOUSE_VIRTUAL_DESKTOP = 0x02   # display's own gate: not px of THIS desk


class Pump:
    """The pure filter core: the ears feed it, the suite feeds it,
    and time always arrives as `now` (the test's fake clock drives
    the whole semantics). Thread-safety: a few floats and one
    anchor under the GIL - a torn read is a millisecond of clock,
    not a wrong verdict."""

    def __init__(self):
        self.last = None            # monotonic of the last COUNTED input
        self.last_packet = None     # monotonic of the last DEVICE packet
        #                              (any packet, even zero-travel -
        #                              the exemption's traffic witness)
        self._acc = 0.0             # traveled px since the last stamp
        self._ax = self._ay = None  # the absolute-report anchor

    def key(self, makecode, flags, now):
        """A RAWKEYBOARD device packet: True when it stamps the
        clock. BREAK-flagged is a release; a zero makecode is the
        unicode/LED no-op twin of one; the TERMSRV_SHADOW bits are
        the ears' drop, rechecked here for the direct-feed suite."""
        self.last_packet = now   # every packet is traffic (the doc)
        if flags & RI_KEY_TERMSRV_SHADOW:
            return False
        if makecode and not (flags & RI_KEY_BREAK):
            self.last = now
            return True
        return False

    def mouse(self, dx, dy, mflags, now):
        """A RAWMOUSE device packet: True when it stamps the clock.
        Relative reports ACCUMULATE |dx|+|dy| (high-res mice stream
        honest sub-threshold deltas; the receipts' pad chatter
        streams exact zeros and never crosses); absolute reports
        move an anchor and count their jump (a touch panel's finger
        is travel, but VIRTUAL_DESKTOP coordinates are not px of
        this desk - display's own gate, mirrored). VIRTUAL_DESKTOP
        reports are still DEVICE traffic (the hardware spoke, the
        wake exemption's witness hears it) - traffic is the stream,
        a refusal is a verdict."""
        self.last_packet = now
        if mflags & MOUSE_VIRTUAL_DESKTOP:
            return False
        if mflags & MOUSE_MOVE_ABSOLUTE:
            moved = (abs(dx - self._ax) + abs(dy - self._ay)
                     if self._ax is not None else 0)
            self._ax, self._ay = dx, dy
        else:
            moved = abs(dx) + abs(dy)
        self._acc += moved
        if self._acc >= DEAD_ZONE_PX:
            self._acc = 0.0          # re-arm at the current point
            self.last = now
            return True
        return False

    def traffic_since(self, t):
        """Any DEVICE packet at or after t (the zero-delta lies
        count here: it is the pump's own stream the exemption
        watches, and the pad's class of lie is traffic too)."""
        return self.last_packet is not None and self.last_packet >= t

    def idle_seconds(self, now):
        """Seconds since the last counted input; inf at boot (never
        input) - the packeted infinite-idle start, not 'now'."""
        if self.last is None:
            return float("inf")
        return max(now - self.last, 0.0)


_pump = Pump()
_ear = None               # the live RawEars, or None
_lock = threading.Lock()
_unavailable = False      # the install refused (or died): fail-open
_refusal = ""             # its word, told by the ONE fail-open line
_warned = False           # ONE warning line, ever


def pump():
    """The live core (the smoke test and the probes feed it)."""
    return _pump


def alive():
    return _ear is not None and _ear.alive()


def install():
    """Start the raw ear (idempotent, thread-safe). True = the ear
    is on. A refusal is remembered WITHOUT a voice here (the
    fail-open line tells it once, dated, at the first read); a
    later install may still retry (a dead pump is a state, not a
    verdict - the hotkey arm's no-pump retry, the same shape)."""
    global _ear, _unavailable, _refusal
    with _lock:
        if _ear is not None and _ear.alive():
            return True
        from . import _inputtruth_hook
        try:
            _ear = _inputtruth_hook.attach(_pump)
        except OSError as exc:          # the desk refused the ear
            _ear = None
            _unavailable = True
            _refusal = str(exc)
            return False
        _unavailable = False
        _refusal = ""
        return True


def uninstall():
    """Send the ear home (join its thread; the un-take happens on it)
    and drop it. Idempotent."""
    global _ear
    with _lock:
        if _ear is not None:
            _ear.detach()
            _ear = None


def _fail_open():
    """The deaf pump's ONE dated word, then the stock clock."""
    global _warned
    if not _warned:
        _warned = True
        log.warning("%s inputtruth: fail-open to the stock "
                    "GetLastInputInfo clock%s (one line; the pump "
                    "exists because THIS clock can be re-stamped by "
                    "device chatter - see the module docstring)",
                    time.strftime("%H:%M"),
                    " - the ear refused: " + _refusal if _refusal
                    else " - the ear died")
    from . import display
    return display.idle_seconds()


def idle_seconds():
    """THE pump clock (the dimmer's _idle_secs seam speaks it, and
    every [dimmer]/[videodim].idle_sec rail follows): seconds since
    real input; inf while no report has passed the filter since
    boot; the stock GetLastInputInfo (loudly once, dated) when the
    ear cannot or no longer does live."""
    global _ear
    if _ear is None and not _unavailable:
        install()                       # lazy: the first rail read
        #                                # births the ear (an armed-off
        #                                # [dimmer] never asks)
    if _ear is not None and not _ear.alive():
        with _lock:                     # a dead pump is a state, not
            if _ear is not None and not _ear.alive():
                _ear = None             # a verdict: drop the corpse
            #                           # and the lazy arm above
            #                           # re-births it next read
    if _ear is not None and _ear.alive():
        return _pump.idle_seconds(time.monotonic())
    return _fail_open()


def wake_idle_seconds(stock):
    """The OFF-PHASE wake clock, and the ONLY path carrying the
    injection exemption (the owner's rule, the docstring: if the
    stock clock moved while the pump saw no device packets at all,
    whatever moved it was a synthetic knock - count it, the screens
    must come back for a remote hand too. During device traffic -
    ANY packets, even the zero-travel lies of the pad class - the
    pump's verdict alone governs, so the same chatter that poisons
    the stock clock can never wake the screens here). `stock` is
    the caller's GetLastInputInfo read (no second syscall, and the
    suite can hand in a fake). Off or deaf returns `stock`
    unchanged: the old wake, exactly. Admitted corner: injection
    amid pad-chatter does not wake - the camera eye and a click are
    the recovery, documented and unchanged."""
    if not alive():
        return stock
    now = time.monotonic()
    p = _pump.idle_seconds(now)
    if p < WAKE_WINDOW_SEC:
        return p
    if _pump.traffic_since(now - WAKE_WINDOW_SEC):
        return p
    return min(p, stock)
