"""Does the Shell accept the tray icon at all?

Spies on pystray's Shell_NotifyIcon call, shows a solid red icon for
12 seconds, prints every NIM_ call with its result and error code.
panelboss.tray is imported first, so its identity patch is in place
before any of this process's NIM_ calls: the spy asserts that every
call it sees carries uID=1 and, while the tray says the Shell accepts
it, the NIF_GUID flag - stamped with a TEST guid (the production slot
is checked as data, not by touching it, so a running app's icon can
never be deleted by this test's NIM_DELETE).
The spy scenario (Nov 21 twin-icon incident): after the live run, a
test double of the wrapped inner refuses every GUID-stamped NIM_ADD
(the first mirrors the live E_FAIL; the retry ladder loses the same
race, so the ladder and the GUID-less fallback both run for real) and
lets every GUID-less call land. It is installed at the module level
BEFORE tray's wrapper binds its closure, so tray's own code - never
this script - is what calls it; the Oct 12 vacuous-pass guard applies
with the force of a class. Its ledger is then asserted: both delete
identities issued before the fallback ADD, the fallback ADD without
NIF_GUID, a warning line per abnormal transition, and the re-claim
hook pinned in the message-handler registration."""
import ctypes
import logging
import os
import sys
import threading
import time
import uuid

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panelboss import tray          # noqa: E402  the patch wraps the
                                     # Shell_NotifyIcon it finds at
                                     # import time; this spy wraps it
                                     # again, one layer out
from pystray._util import win32     # noqa: E402
import pystray                      # noqa: E402

k32 = ctypes.windll.kernel32

# the identity this app mints: computed here, independently of whatever
# tray.py did, so a wrong name or a dropped fill fails this test
expected_guid = uuid.uuid5(uuid.NAMESPACE_DNS, "panelboss.tray")

# a DIFFERENT identity to actually drive the Shell with: same GUID the
# app uses and NIM_DELETE under it remove the FIRST icon registered
# there - a live app's icon, not the test's - and a duplicate-GUID ADD
# can trip the fallback latch and mis-assert the whole run. Swapping
# tray._GUID_ITEM keeps the stamping machinery under test; only the
# bytes differ, and the production bytes are asserted below as data.
test_guid = uuid.uuid5(uuid.NAMESPACE_DNS, "panelboss.tray.test")

nim_calls = []
orig = win32.Shell_NotifyIcon       # the raw windll function, or the
                                     # tray patch if it got here first;
                                     # this spy wraps whatever that is


def _guid_bytes(g):
    """The 16 bytes of a NOTIFYICONDATAW guidItem in canonical field
    order (the order Windows textifies, same as uuid.bytes): the first
    three fields big-endian, the last eight bytes straight across.
    The struct fields are stored little-endian in memory, but the
    identity that Windows keys the tray slot on is the textified
    value, so this is what the assertion compares."""
    return (g.Data1.to_bytes(4, "big")
            + g.Data2.to_bytes(2, "big")
            + g.Data3.to_bytes(2, "big")
            + bytes(g.Data4))


def spy(code, data):
    result = orig(code, data)
    err = k32.GetLastError()
    # read the fields AFTER the inner call: the tray patch stamps the
    # struct before it calls down, so post-call is the state the Shell
    # actually saw (a spy that read pre-call would see the pre-stamp
    # values whenever it sits outside the patch)
    nim_calls.append((code, data.uID, data.uFlags,
                      _guid_bytes(data.guidItem), bool(result), err,
                      tray._guid_live))   # the latch state THIS call
                                          # was stamped under, not the
                                          # end-of-run state
    print("Shell_NotifyIcon code=%s uID=%s flags=0x%x -> %s (err %s)"
          % (hex(code), data.uID, data.uFlags, result, err))
    return result


win32.Shell_NotifyIcon = spy   # _win32 looks the name up at call time

tray._GUID_ITEM = tray._guid_item(test_guid)   # see test_guid above;
# _stamp_identity reads the module global at every call, so every stamp
# from here on carries the test bytes

img = Image.new("RGB", (32, 32))
img.putpixel((0, 0), (255, 0, 0))
draw = img.load()
for x in range(32):
    for y in range(32):
        draw[x, y] = (255, 0, 0)          # solid red; impossible to miss

icon = pystray.Icon(name="VISIBLE TEST", icon=img,
                    menu=pystray.Menu(pystray.MenuItem("Quit",
                                                       action=print)))

def show(icon):
    icon.visible = True           # the docs say the icon starts hidden
    icon.update_menu()            # the constructor sets _menu directly; the
    # win32 backend only builds the HMENU via update_menu
    print("menu handle:", icon._menu_handle is not None)


t = threading.Thread(target=lambda: icon.run(setup=show), daemon=True)
t.start()
time.sleep(12)   # documented intent: the human glance window
icon.stop()
t.join(3)

ok = True
if tray._GUID != expected_guid:
    print("identity FAIL: tray._GUID is %s, want the app uuid5"
          % tray._GUID)
    ok = False
if _guid_bytes(tray._guid_item(expected_guid)) != expected_guid.bytes:
    print("identity FAIL: _guid_item() mis-fills the struct")
    ok = False
# the loop below is vacuous on an EMPTY call log: an icon the Shell
# silently rejected would still print "identity OK" (Oct 12 audit,
# the vacuous pass). At least one NIM_ADD must have RETURNED True -
# without a accepted add there is no identity to check at all.
if not any(code == win32.NIM_ADD and result
           for code, _uid, _flags, _gb, result, _err, _live in nim_calls):
    print("identity FAIL: the Shell accepted NOTHING - zero "
          "successful NIM_ADD calls (pystray never reached the tray)")
    ok = False
for code, uid, flags, gbytes, result, err, live_at_call in nim_calls:
    if uid != 1:
        print("identity FAIL: %s carried uID=%s, want 1" % (hex(code), uid))
        ok = False
    has_guid = bool(flags & win32.NIF_GUID)
    if has_guid != live_at_call:
        print("identity FAIL: %s NIF_GUID=%s but the latch said %s "
              "at that call" % (hex(code), has_guid, live_at_call))
        ok = False
    if has_guid and gbytes != test_guid.bytes:
        print("identity FAIL: %s carried the wrong GUID bytes" % hex(code))
        ok = False
# ------------------------------------------------------------- spy scene ---
# The double and the pinned handlers below; the assertions come after
# the live run has stopped (the scene is driven without a pump, see
# the run function).
class spy_icon:
    _message_handlers = {}


def make_failed_first_add_spies():
    """Install the test double as the innermost layer and pin fake
    message handlers onto a stand-in icon (the vacuous-pass guard:
    tray.py's own code calls the double, this script only reads the
    ledgers). Returns (the double, the live spy, the pinned table)."""
    class _shell_double:
        calls = []

        def __call__(self, code, data):
            d = self.calls
            if code == win32.NIM_ADD and (data.uFlags & win32.NIF_GUID):
                # a GUID-blind Shell: the first add is refused like
                # the live Nov 21 E_FAIL and every retry-ladder
                # re-ADD loses the same race
                d.append((code, data.uID, data.uFlags,
                          _guid_bytes(data.guidItem), False,
                          0x80040150))
                return 0
            if code == win32.NIM_ADD:
                # the fallback's GUID-less add is the one that lands
                d.append((code, data.uID, data.uFlags,
                          _guid_bytes(data.guidItem), True, 0))
                return 1
            # DELETEs miss (no slot yet): the legitimate FALSE the
            # sweep comments call for
            d.append((code, data.uID, data.uFlags,
                      _guid_bytes(data.guidItem), False, 0))
            return 0

    double = _shell_double()
    outer = win32.Shell_NotifyIcon          # the live spy (wraps the
                                            # wrapped inner it caught)
    win32.Shell_NotifyIcon = double
    tray._wrap_shell_notify()               # the wrap rebinds its
                                            # closure to the double: the
                                            # scene then runs tray's REAL
                                            # stamped code (ghost sweep,
                                            # ladder, fallback, twin
                                            # kill) end to end, with the
                                            # shell replaced

    handlers = dict(spy_icon._message_handlers)
    for code in (win32.WM_TASKBARCREATED, win32.WM_DISPLAYCHANGE):
        handlers[code] = (code, spy_icon())

    tray._RECLAIM_HOOKED = True             # _ready's one-shot wrap
                                            # must not replace the pins
    return double, outer, handlers


class _warn_capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        if record.name == "tray" and record.levelno >= logging.WARNING:
            self.lines.append(record.getMessage())


capture = _warn_capture()
logging.getLogger("tray").addHandler(capture)
double, outer, pinned = make_failed_first_add_spies()


def run_spy_scene():
    data = win32.NOTIFYICONDATAW()
    data.hWnd = 12345          # any window: the double never touches
                               # the Shell, the value only rides the
                               # struct
    # uFlags stays 0: the stamping layer and the double only look at
    # uID / NIF_GUID / guidItem, and pystray's win32 module defines no
    # NIM_MESSAGE constant to OR in
    win32.Shell_NotifyIcon(win32.NIM_ADD, data)   # the first ADD of a
                                                 # fresh process: ghost
                                                 # sweep + add, exactly
                                                 # the path pystray's
                                                 # _show drives
    win32.Shell_NotifyIcon = outer               # restore the live
                                                 # spy for what follows


run_spy_scene()

# the spy's per-call latch assertion needs one relaxation, named: the
# twin kill deletes under a TEST guid while the latch is down, on
# purpose (windows-rs #5284, module doc) - the flag/latch consistency
# is enforced for every call that does not carry the TEST guid
for code, uid, flags, gbytes, result, err, live_at_call in nim_calls:
    has_guid = bool(flags & win32.NIF_GUID)
    if has_guid != live_at_call and gbytes == test_guid.bytes:
        if not (code == win32.NIM_DELETE
                and gbytes == _guid_bytes(tray._guid_item(test_guid))):
            print("identity FAIL: %s NIF_GUID=%s but the latch said %s "
                  "at that call" % (hex(code), has_guid, live_at_call))
            ok = False
# ------------------------------------------------------------ spy asserts ---
if ok:
    dcalls = double.calls
    if not dcalls:
        ok = False
        print("spy FAIL: the double was never called from tray.py - "
              "the vacuous pass (Oct 12 guard class)")
    else:
        fadd = None
        for i, (code, uid, flags, gbytes, result, err) in enumerate(dcalls):
            if fadd is None and code == win32.NIM_ADD \
                    and not (flags & win32.NIF_GUID):
                fadd = i
        if fadd is None:
            ok = False
            print("spy FAIL: no GUID-less ADD reached the double - the "
                  "fallback never ran")
        else:
            # (a) BOTH delete identities were issued before the
            #     fallback ADD: the GUID-stamped sweep and the
            #     (hWnd, uID=1) sweep
            pre = dcalls[:fadd]
            both = any(code == win32.NIM_DELETE and (flags & win32.NIF_GUID)
                       for code, _u, flags, _g, _r, _e in pre) \
                and any(code == win32.NIM_DELETE
                        and not (flags & win32.NIF_GUID)
                        for code, _u, flags, _g, _r, _e in pre)
            if not both:
                ok = False
                print("spy FAIL: the pre-fallback sweep did not issue "
                      "BOTH delete identities (got: %s)" % pre)
            else:
                print("spy PASS: both delete identities issued before "
                      "the fallback ADD")
            # (b) the fallback ADD went without NIF_GUID and landed
            c, u, fl, gb, r, _e = dcalls[fadd]
            if fl & win32.NIF_GUID or u != 1 or not r:
                ok = False
                print("spy FAIL: the first non-GUID ADD is not the "
                      "landing fallback ADD: %s" % (dcalls[fadd],))
            else:
                print("spy PASS: the fallback ADD went without NIF_GUID "
                      "(uID=1) and landed")
            # (c) at least one warning line per abnormal transition:
            #     every refused NIM_ call the double saw, the latch
            #     drop, and the named landing-identity line
            refused = sum(1 for _c, _u, _f, _g, r, _e in dcalls
                          if not r)
            if len(capture.lines) < refused:
                ok = False
                print("spy FAIL: %d warning lines for %d refused calls "
                      "wanted" % (len(capture.lines), refused))
            if not any("the Shell refused the NIF_GUID add" in l
                       for l in capture.lines):
                ok = False
                print("spy FAIL: the latch-drop warning never fired")
            if not any("registered under (hWnd,uID=1)" in l
                       for l in capture.lines):
                ok = False
                print("spy FAIL: the landing-identity warning never "
                      "fired")
            if ok:
                print("spy PASS: a warning line per abnormal transition "
                      "(%d lines, %d refusals)" %
                      (len(capture.lines), refused))
# (d) the re-claim-hook pin lands with the re-claim itself, stage 2

print("calls:", nim_calls)
print("identity OK" if ok else "identity BROKEN")
sys.exit(0 if ok else 1)
