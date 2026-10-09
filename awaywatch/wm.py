"""Window and topology memory: the fix for monitors that fully
disconnect when they sleep.

Some panels unplug themselves from Windows on standby. Everything on
them survives in limbo, and when the display returns Windows re-lays
the desk - windows land on the wrong screen, resized, maximized
somewhere they never lived. The app owns the off edge (it fires the
broadcast while the truth is still intact) and hears about the on
edge from every source (its own wake, the camera, a jiggle through
the display watcher, the power button after a sleep), so it can
remember and hand back:

  off    snapshot every top-level window's pixel rect plus a
         fingerprint of the monitor set (hardware IDs + places)
  wake   wait for the topology to SETTLE (the reconnect storm relays
         windows while it runs; applying mid-storm just hands the
         re-layout more material), and only when the fingerprint is
         the one that was saved - the same monitors, same places.
         Then move everything back.

Honest limits, all fail-open: a different fingerprint (a monitor
swapped, unplugged for good) means the saved rects belong to a desk
that no longer exists - nothing is moved. Minimized windows are left
alone (they were not seen; Windows re-places them on the user's own
restore). Owned popups follow their owner's story. Cloaked windows
live on another virtual desktop and must not be dragged across.
Windows that went away in the dark are skipped, and Windows's own
correct placement is respected (same rect = no move).

The monitor side speaks EnumDisplayDevices/EnumDisplaySettings -
the path proven on this machine by the neighboring monitor_control
project. GetMonitorInfoW is deliberately untouched: it fails here
(error 87) for every struct shape tried, and the DEVMODE route also
carries the EDID identity of the physical panel, which the
\\.\DISPLAYn slot names do not.
"""

import ctypes
import logging
import threading
import time
from ctypes import wintypes

log = logging.getLogger("wm")

u32 = ctypes.windll.user32
dwm = ctypes.windll.dwmapi

SWP_NOZORDER = 0x4
SWP_NOACTIVATE = 0x10
SWP_SHOWWINDOW = 0x40
SWP_NOOWNERZORDER = 0x10000        # measured here: dies with 1004
                                   # whatever the insert-after slot
                                   # holds - _move does not use it
SW_SHOWMAXIMIZED = 3
SW_RESTORE = 9

WS_CHILD = 0x40000000
WS_EX_TOOLWINDOW = 0x80
WS_EX_TRANSPARENT = 0x20
GWL_STYLE = -16
GWL_EXSTYLE = -20
GA_ROOT = 2
DWMWA_CLOAKED = 14

ENUM_CURRENT_SETTINGS = -1
DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x1
DISPLAY_DEVICE_PRIMARY_DEVICE = 0x4
DISPLAY_DEVICE_MIRRORING_DRIVER = 0x8

# the shell's furniture: always on screen, never a window somebody
# arranged (and WorkerW really appears once per wallpaper layer)
FURNITURE_PREFIX = ("Progman", "WorkerW", "Shell_TrayWnd",
                    "Shell_SecondaryTrayWnd")


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class POINTL(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _PrinterFields(ctypes.Structure):
    _fields_ = [("dmOrientation", wintypes.SHORT),
                ("dmPaperSize", wintypes.SHORT),
                ("dmPaperLength", wintypes.SHORT),
                ("dmPaperWidth", wintypes.SHORT),
                ("dmScale", wintypes.SHORT),
                ("dmCopies", wintypes.SHORT),
                ("dmDefaultSource", wintypes.SHORT),
                ("dmPrintQuality", wintypes.SHORT)]


class _DisplayFields(ctypes.Structure):
    _fields_ = [("dmPosition", POINTL),
                ("dmDisplayOrientation", wintypes.DWORD),
                ("dmDisplayFixedOutput", wintypes.DWORD)]


class _DevmodeUnion(ctypes.Union):
    _fields_ = [("printer", _PrinterFields), ("display", _DisplayFields)]


class DEVMODEW(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("dmDeviceName", wintypes.WCHAR * 32),
                ("dmSpecVersion", wintypes.WORD),
                ("dmDriverVersion", wintypes.WORD),
                ("dmSize", wintypes.WORD),
                ("dmDriverExtra", wintypes.WORD),
                ("dmFields", wintypes.DWORD),
                ("u", _DevmodeUnion),
                ("dmColor", wintypes.SHORT),
                ("dmDuplex", wintypes.SHORT),
                ("dmYResolution", wintypes.SHORT),
                ("dmTTOption", wintypes.SHORT),
                ("dmCollate", wintypes.SHORT),
                ("dmFormName", wintypes.WCHAR * 32),
                ("dmLogPixels", wintypes.WORD),
                ("dmBitsPerPel", wintypes.DWORD),
                ("dmPelsWidth", wintypes.DWORD),
                ("dmPelsHeight", wintypes.DWORD),
                ("dmDisplayFlags", wintypes.DWORD),
                ("dmDisplayFrequency", wintypes.DWORD),
                ("dmICMMethod", wintypes.DWORD),
                ("dmICMIntent", wintypes.DWORD),
                ("dmMediaType", wintypes.DWORD),
                ("dmDitherType", wintypes.DWORD),
                ("dmReserved1", wintypes.DWORD),
                ("dmReserved2", wintypes.DWORD),
                ("dmPanningWidth", wintypes.DWORD),
                ("dmPanningHeight", wintypes.DWORD)]


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD),
                ("DeviceName", wintypes.WCHAR * 32),
                ("DeviceString", wintypes.WCHAR * 128),
                ("StateFlags", wintypes.DWORD),
                ("DeviceID", wintypes.WCHAR * 128),
                ("DeviceKey", wintypes.WCHAR * 128)]


if ctypes.sizeof(DEVMODEW) != 220:
    raise ImportError("DEVMODEW drift: %d bytes, Windows says 220 - "
                      "EnumDisplaySettings would fail with 87"
                      % ctypes.sizeof(DEVMODEW))

u32.EnumDisplayDevicesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.POINTER(DISPLAY_DEVICEW),
                                   wintypes.DWORD]
u32.EnumDisplayDevicesW.restype = wintypes.BOOL
u32.EnumDisplaySettingsW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                     ctypes.POINTER(DEVMODEW)]
u32.EnumDisplaySettingsW.restype = wintypes.BOOL

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p,
                                 ctypes.c_longlong)

# handle-sized args and returns must be typed or ctypes truncates
# them to int32 on x64: a real handle can ride above 2**31, and a
# truncated GetAncestor answer silently outlaws every window.
_TYPED = {
    "EnumWindows": (ctypes.c_void_p, ctypes.c_longlong),
    "GetClassNameW": (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int),
    "GetWindowLongW": (ctypes.c_void_p, ctypes.c_int),
    "GetAncestor": (ctypes.c_void_p, ctypes.c_uint),
    "IsWindow": (ctypes.c_void_p,),
    "IsWindowVisible": (ctypes.c_void_p,),
    "IsIconic": (ctypes.c_void_p,),
    "IsZoomed": (ctypes.c_void_p,),
    "ShowWindow": (ctypes.c_void_p, ctypes.c_int),
    "SetWindowPos": (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                     ctypes.c_int, ctypes.c_int, ctypes.c_int,
                     ctypes.c_uint),
    "GetWindowRect": (ctypes.c_void_p, ctypes.POINTER(RECT)),
}
for _name, _args in _TYPED.items():
    getattr(u32, str(_name)).argtypes = list(_args)
del _name, _args

u32.GetAncestor.restype = ctypes.c_void_p
u32.GetWindowLongW.restype = ctypes.c_long
u32.SetWindowPos.restype = ctypes.c_bool
u32.GetClassNameW.restype = ctypes.c_int
dwm.DwmGetWindowAttribute.restype = ctypes.c_long   # the answer lives
                                                    # in the out-param
dwm.DwmGetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                      ctypes.c_void_p, ctypes.c_uint]

byref = ctypes.byref
sizeof = ctypes.sizeof


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _cloaked(hwnd):
    try:
        v = wintypes.DWORD()
        dwm.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, byref(v),
                                  sizeof(v))
        return bool(v.value)
    except Exception:
        return False                       # dwmapi is the compositor;
                                           # no answer = not cloaked


def true_rect(hwnd):
    """(x, y, w, h) in the desktop's pixel coordinates. pythonw runs
    DPI-aware, so GetWindowRect answers in real pixels - the trap
    this rests is the virtualized rect a dpi-blind caller reads,
    which would send every restored window to a scaled ghost of its
    old place."""
    r = RECT()
    if not u32.GetWindowRect(hwnd, byref(r)):
        return None
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)


def wanted(w):
    """Pure decision, one place, testable: what we dare to move.
    Everything else is left exactly as it is."""
    return (w["visible"] and not w["owned"] and not w["iconic"]
            and not w["cloaked"] and not w["tool"] and not w["ghost"]
            and not w["furniture"] and w["rect"] is not None
            and w["rect"][2] > 0 and w["rect"][3] > 0)


def _facts(hwnd):
    style = u32.GetWindowLongW(hwnd, GWL_STYLE)
    ex = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    cls = _class_name(hwnd)
    return {
        "hwnd": hwnd,
        "rect": true_rect(hwnd),
        "visible": bool(u32.IsWindowVisible(hwnd)),
        "owned": u32.GetAncestor(hwnd, GA_ROOT) != hwnd,
        "iconic": bool(u32.IsIconic(hwnd)),
        "zoomed": bool(u32.IsZoomed(hwnd)),
        "cloaked": _cloaked(hwnd),
        "tool": bool(ex & WS_EX_TOOLWINDOW),
        "ghost": bool(ex & WS_EX_TRANSPARENT),
        "furniture": cls.startswith(FURNITURE_PREFIX)
        or bool(style & WS_CHILD),
    }


def _toplevel_facts():
    out = []

    def cb(hwnd, _l):
        try:
            out.append(_facts(hwnd))
        except Exception:
            pass                           # a window mid-destruction:
        return 1                           # not ours to move

    proc = WNDENUMPROC(cb)                   # the reference keeps the
    u32.EnumWindows(proc, 0)                 # callback alive
    return out


def fingerprint():
    """Topology as one string: every attached monitor's hardware
    identity, place and size. The identity is the MONITOR DeviceID
    (EDID-derived serial/model), not the \\.\DISPLAYn slot - slots
    get reshuffled by reconnect storms, the panel's own ID does not.
    Reconnecting the same monitor reproduces the string exactly;
    swapping or unplugging one for good changes it, and then the
    saved rects belong to a desk that no longer exists."""
    parts = []
    i = 0
    while True:
        d = DISPLAY_DEVICEW()
        d.cb = sizeof(d)
        if not u32.EnumDisplayDevicesW(None, i, byref(d), 0):
            break
        i += 1
        if d.StateFlags & DISPLAY_DEVICE_MIRRORING_DRIVER:
            continue                       # the mirror of a real one
        if not d.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP:
            continue                       # not part of the desk
        monitor_id = d.DeviceID             # adapter identity as the
        sub = DISPLAY_DEVICEW()             # rest; the monitor under
        sub.cb = sizeof(sub)                # it knows better
        if u32.EnumDisplayDevicesW(d.DeviceName, 0, byref(sub), 0):
            monitor_id = sub.DeviceID or monitor_id
        dm = DEVMODEW()
        dm.dmSize = sizeof(dm)
        if not u32.EnumDisplaySettingsW(d.DeviceName,
                                        ENUM_CURRENT_SETTINGS,
                                        byref(dm)):
            continue                       # no current mode to place
        parts.append("%s@%d,%d %dx%d%s" % (   # it by; fail open
            monitor_id, dm.display.dmPosition.x,
            dm.display.dmPosition.y, dm.dmPelsWidth, dm.dmPelsHeight,
            "P" if d.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE
            else ""))
    return "|".join(sorted(parts))


def snapshot():
    """The desk as it truly is, while the screens are still on."""
    wins = [w for w in _toplevel_facts() if wanted(w)]
    snap = {"fp": fingerprint(), "ts": time.time(), "wins": wins}
    log.info("layout saved: %d windows, %d monitor%s",
             len(wins), snap["fp"].count("|") + 1 if snap["fp"] else 0,
             "" if snap["fp"].count("|") == 0 else "s")
    return snap


def _move(w):
    """Back to the saved rect. A maximized window cannot simply be
    moved (it fills its monitor by definition): restore to floating,
    move onto its OWN old monitor, maximize again - the result is
    maximized exactly where it lived, which is the whole point."""
    if not u32.IsWindow(w["hwnd"]) or not u32.IsWindowVisible(w["hwnd"]):
        return "gone"
    if u32.IsIconic(w["hwnd"]):
        return "skip"                        # minimized in the dark by
    x, y, cx, cy = w["rect"]                 # somebody/something: leave
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
    """Move everything back. Same rect already = Windows put it back
    itself, and arguing with that is how loops are born."""
    moved = kept = gone = skipped = 0
    for w in snap["wins"]:
        cur = true_rect(w["hwnd"])
        if cur is None:
            gone += 1
            continue
        if cur == w["rect"]:
            kept += 1
            continue
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
