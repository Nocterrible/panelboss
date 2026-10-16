"""The Win32 ABI floor: the user32/kernel32/dwmapi handles,
the shared argtype pins, the display/window structs, the message
constants. The ctypes pins run at package import, exactly where the
old wm.py ran them; every sibling part takes these names from here.

Formerly wm.py lines 38-228 (stdlib imports folded into this header).
The part stays whole past a bare subject split because the structs
and the pinning table are one atomic lesson: the shared-windll
diplomacy of the comments below."""

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
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
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


class WINDOWPLACEMENT(ctypes.Structure):
    """Where a window AGREES to come back: rcNormalPosition survives
    minimize, so a stale one (remembered from another desk) is the
    ghost the rescue v2 repairs without ever un-minimizing. SIX
    members, 44 bytes - the gate's live dword dump proved showCmd
    sits at offset 8, and that a length=40 Get does NOT fail:
    Windows truncates the write to whatever length you declare, so
    a short struct mis-decodes SILENTLY (see tripwire below)."""
    _fields_ = [("length", wintypes.UINT), ("flags", wintypes.DWORD),
                ("showCmd", wintypes.UINT),
                ("ptMinPosition", wintypes.POINT),
                ("ptMaxPosition", wintypes.POINT),
                ("rcNormalPosition", RECT)]


if ctypes.sizeof(DEVMODEW) != 220:
    raise ImportError("DEVMODEW drift: %d bytes, Windows says 220 - "
                      "EnumDisplaySettings would fail with 87"
                      % ctypes.sizeof(DEVMODEW))

if ctypes.sizeof(WINDOWPLACEMENT) != 44:
    raise ImportError("WINDOWPLACEMENT drift: %d bytes, Windows says "
                      "44 - and GetWindowPlacement would truncate "
                      "silently, decoding garbage (measured Oct 11)"
                      % ctypes.sizeof(WINDOWPLACEMENT))

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
    # ONE arg: the real signature is GetWindowTextLengthW(HWND).
    # This dict pins the SHARED user32 singleton - a fat pin here
    # would break every other module that calls it honestly.
    "GetWindowTextLengthW": (ctypes.c_void_p,),
    "GetWindowThreadProcessId": (ctypes.c_void_p,
                                 ctypes.POINTER(wintypes.DWORD)),
    # c_void_p for the struct arg again (the shared-windll lesson):
    # byref(WINDOWPLACEMENT) satisfies it, and no sibling module
    # calls these two by these names, so no pin can step on it.
    "GetWindowPlacement": (ctypes.c_void_p, ctypes.c_void_p),
    "SetWindowPlacement": (ctypes.c_void_p, ctypes.c_void_p),
    # The timeout route for title reads (win_title, _inspect): GetWindow-
    # Text on an OWN-process window SENDS, and a send to a thread that
    # is not pumping waits forever - measured Oct-16 (py-spy, two frozen
    # threads): the capture walk died on the hider-paint thread. The
    # lparam and out-param slots are c_void_p (the shared-windll lesson
    # above): byref(buffer)/None satisfy them, and display.py's turn_off
    # passes byref(c_ulong()) in the same slot, no stepping-on.
    "SendMessageTimeoutW": (ctypes.c_void_p, ctypes.c_uint,
                            ctypes.c_ulonglong, ctypes.c_void_p,
                            ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p),
}
for _name, _args in _TYPED.items():
    getattr(u32, str(_name)).argtypes = list(_args)
del _name, _args
u32.SendMessageTimeoutW.restype = ctypes.c_long   # 0 = refused or timed out

WM_GETTEXT = 0x000D
SMTO_ABORTIFHUNG = 0x0002     # SMTO_NORMAL is 0x0000; the constant in
SMTO_TIMEOUT_MS = 1500        # display.py mis-named for years (measured
                              # Oct-16) - the VALUE is this flag.

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
u32.GetWindowPlacement.restype = wintypes.BOOL
u32.SetWindowPlacement.restype = wintypes.BOOL
u32.GetClassNameW.restype = ctypes.c_int
dwm.DwmGetWindowAttribute.restype = ctypes.c_long   # the answer lives
                                                    # in the out-param
dwm.DwmGetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                      ctypes.c_void_p, ctypes.c_uint]

byref = ctypes.byref
sizeof = ctypes.sizeof
