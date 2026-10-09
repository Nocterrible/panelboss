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
k32 = ctypes.windll.kernel32
dwm = ctypes.windll.dwmapi

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
LOST_EDGE = 30                 # the monitor_control rescue's floor:
                               # under this a window is not something
                               # a person could grab anyway

SWP_NOZORDER = 0x4
SWP_NOACTIVATE = 0x10
SWP_SHOWWINDOW = 0x40
SWP_NOOWNERZORDER = 0x10000        # measured here: dies with 1004
                                   # whatever the insert-after slot
                                   # holds - _move does not use it
SW_SHOWNORMAL = 1
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
    # c_void_p, NOT POINTER(RECT): windll.user32 is one cached
    # handle shared by the whole process, and a POINTER(RECT) here
    # also binds every OTHER caller - display.py's GetWindowRect
    # passes a wintypes.RECT, structurally identical but a different
    # class, and ctypes checks identity: _screens_off died with
    # "expected LP_RECT instance instead of pointer to RECT" on the
    # first real absence (measured), and the monitor stayed lit.
    "GetWindowRect": (ctypes.c_void_p, ctypes.c_void_p),
    "GetWindowTextW": (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int),
    "GetWindowTextLengthW": (ctypes.c_void_p, ctypes.c_wchar_p,
                             ctypes.c_int),
    "GetWindowThreadProcessId": (ctypes.c_void_p,
                                 ctypes.POINTER(wintypes.DWORD)),
}
for _name, _args in _TYPED.items():
    getattr(u32, str(_name)).argtypes = list(_args)
del _name, _args

k32.OpenProcess.restype = ctypes.c_void_p
k32.OpenProcess.argtypes = [wintypes.DWORD, ctypes.c_bool, wintypes.DWORD]
k32.QueryFullProcessImageNameW.restype = ctypes.c_bool
k32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p,
                                           wintypes.DWORD,
                                           ctypes.c_wchar_p,
                                           ctypes.POINTER(wintypes.DWORD)]
k32.CloseHandle.restype = ctypes.c_bool
k32.CloseHandle.argtypes = [ctypes.c_void_p]

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


def win_title(hwnd):
    n = u32.GetWindowTextLengthW(hwnd, None, 0)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(min(n, 200) + 1)
    u32.GetWindowTextW(hwnd, buf, len(buf))
    return buf.value


def _proc_info(hwnd):
    """(name, full exe path) - one OpenProcess, two answers. The
    name is the identity a profile matches on (hwnds die, pids are
    recycled, the name survives relaunches); the full path is what
    a pin can re-run when the app is not open any more."""
    try:
        pid = wintypes.DWORD()
        if not u32.GetWindowThreadProcessId(hwnd, byref(pid)):
            return "", ""
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False,
                            pid.value)
        if not h:
            return "", ""
        try:
            buf = ctypes.create_unicode_buffer(4096)
            n = wintypes.DWORD(len(buf))
            if not k32.QueryFullProcessImageNameW(h, 0, buf, byref(n)):
                return "", ""
            full = buf.value
            return full.split("\\")[-1].lower(), full
        finally:
            k32.CloseHandle(h)
    except Exception:
        return "", ""                      # a window dying mid-walk;
                                           # a profile entry with no
                                           # proc is simply unmatched


def proc_name(hwnd):
    name, _ = _proc_info(hwnd)
    return name


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
    proc, exe = _proc_info(hwnd)
    return {
        "hwnd": hwnd,
        "rect": true_rect(hwnd),
        "title": win_title(hwnd),
        "proc": proc,
        "exe": exe,
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


def _short_id(monitor_id):
    """"MONITOR\\AOC2790\\{...}\\0009" -> "AOC2790": the model token is
    the only part of the EDID path a human can read."""
    parts = str(monitor_id).split("\\")
    if len(parts) >= 2 and parts[0].upper() == "MONITOR":
        return parts[1]
    return str(monitor_id)[:24]


def monitors():
    """Every attached monitor as {id, short, gdi, x, y, w, h, rate,
    bits, primary}. The identity is the MONITOR DeviceID (EDID-derived
    serial/model), not the \\.\DISPLAYn slot - slots get reshuffled
    by reconnect storms, the panel's own ID does not."""
    out = []
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
        out.append({"id": monitor_id, "short": _short_id(monitor_id),
                    "gdi": d.DeviceName,
                    "x": dm.display.dmPosition.x,
                    "y": dm.display.dmPosition.y,
                    "w": int(dm.dmPelsWidth), "h": int(dm.dmPelsHeight),
                    "rate": int(dm.dmDisplayFrequency),
                    "bits": int(dm.dmBitsPerPel),
                    "primary": bool(d.StateFlags
                                    & DISPLAY_DEVICE_PRIMARY_DEVICE)})
    return out


def monitor_for(rect):
    """The monitor owning a rect's centre - for labelling profile
    rows, nothing leans on the answer."""
    if not rect:
        return None
    cx, cy = rect[0] + rect[2] // 2, rect[1] + rect[3] // 2
    for m in monitors():
        if m["x"] <= cx < m["x"] + m["w"] and m["y"] <= cy < m["y"] + m["h"]:
            return m
    return None


def fingerprint():
    """Topology as one string: every monitor's hardware ID, place
    and size. Reconnecting the same monitor reproduces it exactly;
    swapping or unplugging one for good changes it - and then the
    saved rects belong to a desk that no longer exists."""
    return "|".join(sorted(
        "%s@%d,%d %dx%d%s" % (m["id"], m["x"], m["y"], m["w"], m["h"],
                              "P" if m["primary"] else "")
        for m in monitors()))


def list_windows():
    """Every window the app dares to move (wanted's rules), with the
    identity fields a profile needs."""
    return [w for w in _toplevel_facts() if wanted(w)]


def place(hwnd, rect, zoomed=False):
    """Public wrapper for the move logic, so profiles do not import
    the private path."""
    return _move({"hwnd": hwnd, "rect": tuple(rect),
                  "zoomed": bool(zoomed)})


# A PRIVATE shell32 handle: windll.shell32 is the one power.py already
# calls ShellExecuteW("runas") through, and argtypes bound there would
# bind there too (the user32 trap, learned the hard way). WinDLL() hands
# out a fresh copy whose prototype belongs to us alone.
_shell32 = ctypes.WinDLL("shell32")
_shell32.ShellExecuteW.restype = ctypes.c_int
_shell32.ShellExecuteW.argtypes = [wintypes.HWND, ctypes.c_wchar_p,
                                   ctypes.c_wchar_p, ctypes.c_wchar_p,
                                   ctypes.c_wchar_p, ctypes.c_int]


def launch(exe_path):
    """The naive re-open a pin with 'open it' makes: shell-execute
    the exe exactly as double-clicking it in Explorer would (so .lnk
    and app paths behave as they do for a human). Honest about its
    limits: store apps and stub-launchers start NOTHING under this
    name - the caller waits for a window and must not wait forever.
    Returns "" or the reason it could not even try."""
    if not exe_path:
        return "no exe path was saved for this pin"
    ret = _shell32.ShellExecuteW(None, "open", exe_path, None, None,
                                 SW_SHOWNORMAL)
    if ret <= 32:
        return "the shell refused to start %s (error %d)" % (
            exe_path.split("\\")[-1], ret)
    return ""


# --------------------------------------------------- desktop application --
# The procedures below are stolen from the monitor_control project
# (both halves of it), with its measured lessons baked in: the driver
# is the truth about sizes (the display-config API reported widths
# that disagreed with the desktop - measured), the current DEVMODE
# must be the base of any change (one copied from the mode list has
# an empty dmDeviceName and every request then comes back -2), a
# CDS_TEST ask costs nothing and saves a blink, Windows reports
# success BEFORE the modes settle (so everything is read back), and
# it refuses with 87 to drop the display that owns the desktop in
# the same call that hands the desktop over.
ENUM_REGISTRY_SETTINGS = -2
CDS_UPDATEREGISTRY = 0x01
CDS_TEST = 0x02
CDS_SET_PRIMARY = 0x10
CDS_NORESET = 0x10000000
DM_POSITION = 0x20
DM_PELSWIDTH = 0x80000
DM_PELSHEIGHT = 0x40000
DM_DISPLAYFREQUENCY = 0x400000
DISP_CHANGE_SUCCESSFUL = 0
DISP_CHANGE_RESTART = 1

u32.ChangeDisplaySettingsExW.argtypes = [
    ctypes.c_wchar_p, ctypes.POINTER(DEVMODEW), ctypes.c_void_p,
    wintypes.DWORD, ctypes.c_void_p]
u32.ChangeDisplaySettingsExW.restype = ctypes.c_long


def current_mode(gdi):
    """The DEVMODE to base a change on. A turned-off monitor has no
    current mode, and one copied fresh from the mode list carries an
    empty dmDeviceName (every non-trivial request then answers -2,
    the "monitor unplugged itself" illusion) - so: current first,
    registry second, both with the name the driver recognises."""
    dm = DEVMODEW()
    dm.dmSize = sizeof(dm)
    if u32.EnumDisplaySettingsW(gdi, ENUM_CURRENT_SETTINGS, byref(dm)) \
            and dm.dmPelsWidth:
        return dm
    if u32.EnumDisplaySettingsW(gdi, ENUM_REGISTRY_SETTINGS, byref(dm)):
        return dm
    return None


def offered_modes(gdi, limit=400):
    """The modes the driver offers, spelled "WxH@Hz", driver order,
    deduplicated - the profile UI shows this list next to each
    monitor so a user cannot ask for a mode the panel will not
    take."""
    out = []
    for i in range(limit):
        dm = DEVMODEW()
        dm.dmSize = sizeof(dm)
        if not u32.EnumDisplaySettingsW(gdi, i, byref(dm)):
            break
        if not dm.dmPelsWidth:
            continue
        name = "%dx%d@%d" % (dm.dmPelsWidth, dm.dmPelsHeight,
                             dm.dmDisplayFrequency)
        if name not in out:
            out.append(name)
    return out


def set_mode(gdi, w, h, rate):
    """Size (and rate when asked) on one monitor, the Modes.Set
    procedure: current DEVMODE as the base, the mode must be on the
    driver's list (an unlisted one answers -2 like a dead cable),
    CDS_TEST before touching the screen, believe the driver over the
    return code."""
    dm = current_mode(gdi)
    if dm is None:
        return "the driver will not say what %s is set to" % gdi
    if int(dm.dmPelsWidth) == w and int(dm.dmPelsHeight) == h and \
            (rate <= 0 or int(dm.dmDisplayFrequency) == rate):
        return "already %dx%d@%d" % (w, h, dm.dmDisplayFrequency)
    want = "%dx%d@%d" % (w, h, rate)
    if rate > 0 and want not in offered_modes(gdi):
        return "%s is not among the modes this monitor offers" % want
    dm.dmPelsWidth = w
    dm.dmPelsHeight = h
    dm.dmFields |= DM_PELSWIDTH | DM_PELSHEIGHT
    if rate > 0:
        dm.dmDisplayFrequency = rate
        dm.dmFields |= DM_DISPLAYFREQUENCY
    if u32.ChangeDisplaySettingsExW(gdi, byref(dm), None, CDS_TEST,
                                    None) != DISP_CHANGE_SUCCESSFUL:
        return "%s is on the list but the driver will not switch" % want
    rc = u32.ChangeDisplaySettingsExW(gdi, byref(dm), None, 0, None)
    if rc == DISP_CHANGE_RESTART:          # the keep-settings dialog
        u32.ChangeDisplaySettingsExW(None, None, None, 0, None)
    time.sleep(0.9)                        # the mode lands async
    return "asked %s (driver answer %d)" % (want, rc)


def apply_layout(entries):
    """Turn the profile's display plan on the desk: enable pass
    first (new primary LAST so it can steal 0,0 cleanly, CDS_SET_
    PRIMARY), then the disable pass (0x0 at 0,0), then one commit;
    everything CDS_UPDATEREGISTRY | CDS_NORESET. entries:
    [{gdi, on, primary, x, y, w, h, rate}] - devices already in the
    wanted state are skipped, so a profile applied onto its own desk
    never blinks (the switcher's rule: a change nobody asked for is
    still a change)."""
    lines = []
    wanted = [e for e in entries if e.get("on", True)]
    disabled = [e for e in entries if not e.get("on", True)]
    if not wanted:
        return False, ["no monitor would stay on - refusing"]
    primary = next((e["gdi"] for e in wanted if e.get("primary")),
                   wanted[0]["gdi"])

    def already(dev, want_on):
        now = {m["gdi"]: m for m in monitors()}
        cur = now.get(dev)
        if want_on:
            if cur is None:
                return False
            e = next(x for x in entries if x["gdi"] == dev)
            px = 0 if dev == primary else int(e["x"])
            py = 0 if dev == primary else int(e["y"])
            return (cur["w"] == int(e["w"]) and cur["h"] == int(e["h"])
                    and cur["x"] == px and cur["y"] == py
                    and (dev != primary or cur["primary"]))
        return cur is None                 # already off

    pend = [e for e in wanted if not already(e["gdi"], True)]
    order = [e for e in pend if e["gdi"] != primary] + \
            [e for e in pend if e["gdi"] == primary]
    for e in order:
        dm = current_mode(e["gdi"])
        base = dm if dm is not None else DEVMODEW()
        base.dmSize = sizeof(base)
        base.dmDriverExtra = 0
        base.dmPelsWidth = int(e["w"])
        base.dmPelsHeight = int(e["h"])
        if e.get("rate"):
            base.dmDisplayFrequency = int(e["rate"])
        base.display.dmPosition.x = (0 if e["gdi"] == primary
                                     else int(e["x"]))
        base.display.dmPosition.y = (0 if e["gdi"] == primary
                                     else int(e["y"]))
        base.dmFields = DM_POSITION | DM_PELSWIDTH | DM_PELSHEIGHT
        if e.get("rate"):
            base.dmFields |= DM_DISPLAYFREQUENCY
        flags = CDS_UPDATEREGISTRY | CDS_NORESET
        if e["gdi"] == primary:
            flags |= CDS_SET_PRIMARY
        rc = u32.ChangeDisplaySettingsExW(e["gdi"], byref(base), None,
                                          flags, None)
        lines.append("enable %s %dx%d@%d -> %d" % (
            e["gdi"], e["w"], e["h"], e.get("rate") or 0, rc))
    for e in disabled:
        if already(e["gdi"], False):
            continue
        dm = DEVMODEW()
        dm.dmSize = sizeof(dm)
        dm.dmFields = DM_POSITION | DM_PELSWIDTH | DM_PELSHEIGHT
        dm.dmPelsWidth = 0
        dm.dmPelsHeight = 0
        rc = u32.ChangeDisplaySettingsExW(e["gdi"], byref(dm), None,
                                          CDS_UPDATEREGISTRY
                                          | CDS_NORESET, None)
        lines.append("disable %s -> %d" % (e["gdi"], rc))
    rc = u32.ChangeDisplaySettingsExW(None, None, None, 0, None)
    lines.append("commit -> %d" % rc)
    return rc in (DISP_CHANGE_SUCCESSFUL, DISP_CHANGE_RESTART), lines


# ------------------------------------------------------------- HDR ------
# The C# project's honest conclusion: there is no API it could reach
# that reads HDR back, only the Win+Alt+B hotkey (which has moved
# between Windows versions, hence the configurable key), so the app
# only ever SENDS the key and keeps its own belief about the state.
# Same deal here: press when the belief disagrees with the profile,
# flip the belief, never claim to know.
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1
VK = {"win": 0x5B, "windows": 0x5B, "alt": 0x12, "ctrl": 0x11,
      "control": 0x11, "shift": 0x10}


class KEYBDINPUT(ctypes.Structure):
    """The x64 INPUT for a keyboard event: 40 bytes exactly (their
    C# pins it with Size=40) - a smaller struct is not INPUT-shaped
    and SendInput refuses it in silence."""
    _fields_ = [("type", wintypes.UINT), ("pad", wintypes.UINT),
                ("vk", wintypes.USHORT), ("scan", wintypes.USHORT),
                ("flags", wintypes.UINT), ("time", wintypes.UINT),
                ("extra", ctypes.c_ulonglong),
                ("tail", ctypes.c_ulonglong)]


assert ctypes.sizeof(KEYBDINPUT) == 40, "INPUT drift, SendInput is blind"


def press_keys(combination):
    """Press a combination ("win+alt+b"): every key down, then up in
    reverse, one SendInput batch. Returns the trouble string (empty
    = the batch was accepted - whether HDR followed is, again,
    unknowable from here)."""
    keys = []
    for part in combination.lower().replace("-", "+").split("+"):
        part = part.strip()
        if not part:
            continue
        if part in VK:
            keys.append(VK[part])
        elif len(part) == 1 and part.isalnum():
            keys.append(ord(part.upper()))
        elif part.startswith("f") and len(part) <= 3 \
                and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            keys.append(0x70 + int(part[1:]) - 1)
    if not keys:
        return "'%s' is not a key combination like win+alt+b" \
            % combination
    batch = (KEYBDINPUT * (len(keys) * 2))()
    for i, vk in enumerate(keys):
        batch[i] = KEYBDINPUT(INPUT_KEYBOARD, 0, vk, 0, 0, 0, 0)
        batch[len(keys) * 2 - 1 - i] = KEYBDINPUT(
            INPUT_KEYBOARD, 0, vk, 0, KEYEVENTF_KEYUP, 0, 0)
    u32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p,
                              ctypes.c_int]
    n = u32.SendInput(len(batch), batch, sizeof(KEYBDINPUT))
    if n != len(batch):
        return "windows took %d of %d key events" % (n, len(batch))
    return ""


# ------------------------------------------------- HDR, actually read --
# The research result, measured HERE (October 2026): Windows reports
# per-monitor HDR through the DisplayConfig device-info API. Type 15,
# GET_ADVANCED_COLOR_INFO_2 (build 26100+), carries the truth field:
# activeColorMode SDR=0 / WCG=1 / HDR=2, plus a value bitmask whose
# bit 4 says whether the panel can do HDR at all. The old type 9 is
# NOT HDR - it is "advanced color", HDR and wide-gamut merged; on
# this desk it answers supported+enabled for a monitor that has no
# HDR whatsoever. So: ask 15 first; a refusal (50) means an old OS
# and only then the hotkey-with-belief below is the honest path.
# The join rules, from the same measured source: the adapter/id the
# header must carry come from the TARGET's MODE entry (the source
# side is the GPU's), and the monitor is named by the DISPLAY#<model>#
# segment of the target device path - never by the friendly name
# (which is a marketing string: this desk's IOC912B calls itself
# "GA27W1Q"). Sizes are asserted at import exactly like every other
# struct here: a wrong size is not an error, it is a silent overwrite.
class LUID(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.LONG)]


class DC_RATIONAL(ctypes.Structure):
    _fields_ = [("num", wintypes.UINT), ("den", wintypes.UINT)]


class DC_HEADER(ctypes.Structure):
    _fields_ = [("type", wintypes.UINT), ("size", wintypes.UINT),
                ("adapter", LUID), ("id", wintypes.UINT)]


class DC_SOURCE_NAME(ctypes.Structure):
    _fields_ = [("header", DC_HEADER), ("name", wintypes.WCHAR * 32)]


class DC_TARGET_NAME(ctypes.Structure):
    _fields_ = [("header", DC_HEADER), ("flags", wintypes.UINT),
                ("tech", wintypes.UINT),
                ("edid_man", wintypes.USHORT),
                ("edid_prod", wintypes.USHORT),
                ("connector", wintypes.UINT),
                ("friendly", wintypes.WCHAR * 64),
                ("path", wintypes.WCHAR * 128)]


class DC_COLOR_INFO(ctypes.Structure):          # type 9 payload
    _fields_ = [("header", DC_HEADER), ("value", wintypes.UINT),
                ("encoding", wintypes.UINT), ("bits", wintypes.UINT)]


class DC_COLOR_INFO_2(ctypes.Structure):        # type 15, 24H2+
    _fields_ = [("header", DC_HEADER), ("value", wintypes.UINT),
                ("encoding", wintypes.UINT), ("bits", wintypes.UINT),
                ("mode", wintypes.UINT)]        # 0 SDR / 1 WCG / 2 HDR


class DC_SET_STATE(ctypes.Structure):           # types 10 and 16
    _fields_ = [("header", DC_HEADER), ("value", wintypes.UINT)]


class DC_PATH_SOURCE(ctypes.Structure):
    _fields_ = [("adapter", LUID), ("id", wintypes.UINT),
                ("modeIdx", wintypes.UINT), ("status", wintypes.UINT)]


class DC_PATH_TARGET(ctypes.Structure):
    _fields_ = [("adapter", LUID), ("id", wintypes.UINT),
                ("modeIdx", wintypes.UINT), ("tech", wintypes.UINT),
                ("rotation", wintypes.UINT), ("scaling", wintypes.UINT),
                ("rate", DC_RATIONAL), ("order", wintypes.UINT),
                ("avail", wintypes.INT), ("status", wintypes.UINT)]


class DC_PATH(ctypes.Structure):
    _fields_ = [("src", DC_PATH_SOURCE), ("tgt", DC_PATH_TARGET),
                ("flags", wintypes.UINT)]


class DC_MODE(ctypes.Structure):
    _fields_ = [("kind", wintypes.UINT), ("id", wintypes.UINT),
                ("adapter", LUID), ("tail", ctypes.c_char * 48)]


for _n, _s, _want in (("DC_HEADER", DC_HEADER, 20), ("DC_MODE", DC_MODE, 64),
                      ("DC_PATH", DC_PATH, 72), ("DC_COLOR_INFO",
                                                 DC_COLOR_INFO, 32),
                      ("DC_COLOR_INFO_2", DC_COLOR_INFO_2, 36),
                      ("DC_SET_STATE", DC_SET_STATE, 24),
                      ("DC_SOURCE_NAME", DC_SOURCE_NAME, 84),
                      ("DC_TARGET_NAME", DC_TARGET_NAME, 420)):
    assert ctypes.sizeof(_s) == _want, "DisplayConfig layout drift: %s" % _n

QDC_ONLY_ACTIVE_PATHS = 0x2
DCI_GET_SOURCE_NAME = 1
DCI_GET_TARGET_NAME = 2
DCI_GET_ADVANCED_COLOR_INFO = 9
DCI_SET_ADVANCED_COLOR_STATE = 10
DCI_GET_ADVANCED_COLOR_INFO_2 = 15
DCI_SET_HDR_STATE = 16
ERROR_NOT_SUPPORTED = 50
u32.GetDisplayConfigBufferSizes.argtypes = [
    wintypes.UINT, ctypes.POINTER(wintypes.UINT),
    ctypes.POINTER(wintypes.UINT)]
u32.GetDisplayConfigBufferSizes.restype = ctypes.c_long
u32.QueryDisplayConfig.argtypes = [
    wintypes.UINT, ctypes.POINTER(wintypes.UINT),
    ctypes.POINTER(DC_PATH), ctypes.POINTER(wintypes.UINT),
    ctypes.POINTER(DC_MODE), ctypes.c_void_p]
u32.QueryDisplayConfig.restype = ctypes.c_long
u32.DisplayConfigGetDeviceInfo.argtypes = [ctypes.POINTER(DC_HEADER)]
u32.DisplayConfigGetDeviceInfo.restype = ctypes.c_long
u32.DisplayConfigSetDeviceInfo.argtypes = [ctypes.POINTER(DC_HEADER)]
u32.DisplayConfigSetDeviceInfo.restype = ctypes.c_long


def _dc_targets():
    """Every active display path as rows {gdi, model, adapter, id} -
    adapter/id the TARGET-side mode coordinates, the only ones the
    advanced-color calls accept."""
    n_path, n_mode = wintypes.UINT(0), wintypes.UINT(0)
    if u32.GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS,
                                       ctypes.byref(n_path),
                                       ctypes.byref(n_mode)) != 0:
        return []
    paths = (DC_PATH * n_path.value)()
    modes = (DC_MODE * n_mode.value)()
    if u32.QueryDisplayConfig(QDC_ONLY_ACTIVE_PATHS,
                              ctypes.byref(n_path), paths,
                              ctypes.byref(n_mode), modes,
                              None) != 0:
        return []
    out = []
    for p in paths:
        if p.tgt.modeIdx == 0xFFFFFFFF or p.tgt.modeIdx >= n_mode.value:
            continue
        src = DC_SOURCE_NAME()
        src.header.type, src.header.size = DCI_GET_SOURCE_NAME, \
            ctypes.sizeof(src)
        src.header.adapter, src.header.id = p.src.adapter, p.src.id
        if u32.DisplayConfigGetDeviceInfo(ctypes.byref(src.header)):
            continue
        tgt = DC_TARGET_NAME()
        tgt.header.type, tgt.header.size = DCI_GET_TARGET_NAME, \
            ctypes.sizeof(tgt)
        tgt.header.adapter, tgt.header.id = p.tgt.adapter, p.tgt.id
        u32.DisplayConfigGetDeviceInfo(ctypes.byref(tgt.header))
        model = tgt.path.split("#")[1] if "#" in tgt.path else ""
        m = modes[p.tgt.modeIdx]
        out.append({"gdi": src.name, "model": model,
                    "adapter": m.adapter, "id": m.id})
    return out


def hdr_states():
    """One row per attached monitor: {gdi, model, supported, state,
    precise}. state is "on"/"off" (and "supported" says whether the
    panel could do it); on a pre-24H2 OS precise is False and state
    is "unknown" - the old API answers about HDR-or-wide-gamut
    merged, which is not a fact worth believing (measured: it says
    enabled on this desk's HDR-less third monitor)."""
    out = []
    for t in _dc_targets():
        a = DC_COLOR_INFO_2()
        a.header.type, a.header.size = DCI_GET_ADVANCED_COLOR_INFO_2, \
            ctypes.sizeof(a)
        a.header.adapter, a.header.id = t["adapter"], t["id"]
        if u32.DisplayConfigGetDeviceInfo(ctypes.byref(a.header)) == 0:
            out.append({"gdi": t["gdi"], "model": t["model"],
                        "supported": bool(a.value & 0x10),
                        "state": "on" if a.mode == 2 else
                        ("off" if a.mode in (0, 1) else "unknown"),
                        "mode": a.mode, "precise": True})
            continue
        b = DC_COLOR_INFO()
        b.header.type, b.header.size = DCI_GET_ADVANCED_COLOR_INFO, \
            ctypes.sizeof(b)
        b.header.adapter, b.header.id = t["adapter"], t["id"]
        rc = u32.DisplayConfigGetDeviceInfo(ctypes.byref(b.header))
        out.append({"gdi": t["gdi"], "model": t["model"],
                    "supported": bool(b.value & 1) if rc == 0 else False,
                    "state": "unknown", "mode": None,
                    "precise": False})
    return out


def hdr_set(gdi, on):
    """Command HDR on one monitor (type 16, build 24H2+): a real
    SET, not the hotkey's toggle-in-the-dark. Returns the trouble
    string ('' = accepted - believe the read-back afterwards, as
    always). Changing HDR re-enumerates the display paths, so this
    re-walks the topology every call and never trusts a cached id."""
    for t in _dc_targets():
        if t["gdi"] != gdi:
            continue
        s = DC_SET_STATE()
        s.header.type, s.header.size = DCI_SET_HDR_STATE, ctypes.sizeof(s)
        s.header.adapter, s.header.id = t["adapter"], t["id"]
        s.value = 1 if on else 0
        rc = u32.DisplayConfigSetDeviceInfo(ctypes.byref(s.header))
        if rc == 0:
            return ""
        return ("the monitor refuses the change (error %d)" % rc
                if rc != ERROR_NOT_SUPPORTED
                else "this monitor cannot do HDR")
    return "no active display path for %s any more" % gdi


# ----------------------------------------------------------- rescue -----
def lost(rect, mons):
    """Pure decision (testable): a rectangle no monitor intersects
    belongs to a window nobody can reach. Stolen from
    monitor_control's WindowRescue, disqualifiers and all."""
    x, y, cx, cy = rect
    for m in mons:
        if (x < m["x"] + m["w"] and x + cx > m["x"]
                and y < m["y"] + m["h"] and y + cy > m["y"]):
            return False
    return True


def rescue_lost():
    """Every visible, not-minimized, grabbable window that no screen
    covers comes back to the middle of the primary monitor (the C#
    original returns it to the nearest one; the ask here was
    explicitly "center of the primary"). Cloaked (other virtual
    desktop) windows are the port's one addition: their coordinates
    are honest, they just live on another desktop - dragging them
    across is not a rescue."""
    mons = monitors()
    if not mons:
        return []
    prim = next((m for m in mons if m["primary"]), mons[0])
    brought = []
    for w in _toplevel_facts():
        if not w["visible"] or w["iconic"] or w["cloaked"] \
                or w["furniture"]:
            continue
        r = w["rect"]
        if not r or r[2] < LOST_EDGE or r[3] < LOST_EDGE:
            continue
        if not lost(r, mons):
            continue
        x, y, cx, cy = r
        cx = min(cx, prim["w"])
        cy = min(cy, prim["h"])
        nx = prim["x"] + max(0, (prim["w"] - cx) // 2)
        ny = prim["y"] + max(0, (prim["h"] - cy) // 2)
        if w["zoomed"]:
            u32.ShowWindow(w["hwnd"], SW_RESTORE)
        if u32.SetWindowPos(w["hwnd"], None, nx, ny, cx, cy,
                            SWP_NOACTIVATE | SWP_SHOWWINDOW):
            brought.append((w["title"] or w["proc"] or
                            "(untitled)").strip()[:48])
    log.info("rescue: %s", ("brought back " + ", ".join(brought))[:200]
             if brought else "nothing was off screen")
    return brought


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
