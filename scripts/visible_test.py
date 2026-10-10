"""Does the Shell accept the tray icon at all?

Spies on pystray's Shell_NotifyIcon call, shows a solid red icon for
12 seconds, prints every NIM_ call with its result and error code.
awaywatch.tray is imported first, so its identity patch is in place
before any of this process's NIM_ calls: the spy asserts that every
call it sees carries uID=1 and, while the tray says the Shell accepts
it, the NIF_GUID flag - stamped with a TEST guid (the production slot
is checked as data, not by touching it, so a running app's icon can
never be deleted by this test's NIM_DELETE)."""
import ctypes
import os
import sys
import threading
import time
import uuid

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from awaywatch import tray          # noqa: E402  the patch wraps the
                                     # Shell_NotifyIcon it finds at
                                     # import time; this spy wraps it
                                     # again, one layer out
from pystray._util import win32     # noqa: E402
import pystray                      # noqa: E402

k32 = ctypes.windll.kernel32

# the identity this app mints: computed here, independently of whatever
# tray.py did, so a wrong name or a dropped fill fails this test
expected_guid = uuid.uuid5(uuid.NAMESPACE_DNS, "icu-presence-detector.tray")

# a DIFFERENT identity to actually drive the Shell with: same GUID the
# app uses and NIM_DELETE under it remove the FIRST icon registered
# there - a live app's icon, not the test's - and a duplicate-GUID ADD
# can trip the fallback latch and mis-assert the whole run. Swapping
# tray._GUID_ITEM keeps the stamping machinery under test; only the
# bytes differ, and the production bytes are asserted below as data.
test_guid = uuid.uuid5(uuid.NAMESPACE_DNS, "icu-presence-detector.tray.test")

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
time.sleep(12)
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
print("calls:", nim_calls)
print("identity OK" if ok else "identity BROKEN")
sys.exit(0 if ok else 1)
