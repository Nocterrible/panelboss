"""Win32 display power control.

- turns monitors off/on with the same SC_MONITORPOWER broadcast the power
  plan uses, so standby is the identical DPMS state the built-in display
  timeout puts the monitors into
- runs a hidden window + GUID_MONITOR_ON power sink on its own thread so
  power framework transitions (a plan timeout turning the screens off
  before our absence logic fires) are noticed

  Measured on this machine: raw SC_MONITORPOWER broadcasts do NOT produce
  a GUID_MONITOR_ON notification; the event only fires for power framework
  transitions. Display state is therefore tracked from our own commands,
  input activity and the camera, and broadcasts are a bonus signal.
- GetLastInputInfo drives the idle gate (never poll the camera while the
  user is typing)
- foreground fullscreen detection: exclusive-fullscreen apps swallow the
  broadcast, so the guard skips them

All ctypes, no third-party bindings. Verified recipe: window class atom,
hidden window and sink all live on the pumping thread, every handle is a
c_void_p so 64-bit values never truncate, and SendMessageTimeout always
carries a real timeout (0 means forever and some app on the system never
pumps its queue).
"""

from __future__ import annotations

import ctypes
import logging
import queue
import struct
import threading
import time
from ctypes import wintypes
from ctypes import WINFUNCTYPE

log = logging.getLogger("display")

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32

WM_SYSCOMMAND = 0x112
SC_MONITORPOWER = 0xF170
HWND_BROADCAST = 0xFFFF        # every top-level window receives it
HWND_MESSAGE = 0xFFFFFFFF      # message-only windows always receive it too
MONITOR_ON = 1
MONITOR_OFF = 2                # DPMS standby, same as the power plan

WM_POWER = 0x218
PBT_POWER = 4                  # lParam points to a POWERBROADCAST_HDR

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x1       # keep the box awake while we poll the camera
ES_DISPLAY_REQUIRED = 0x2      # resets the display idle timer (wake fallback)

INPUT_KEYBOARD = 1             # SendInput inject: the only weapon that
KEYUP = 0x0002                 # measurably lights these panels (see wake)
VK_CONTROL = 0x11              # a lone modifier presses no buttons

DEVICE_NOTIFICATION = 1
SERVICE_NOTIFICATION = 2

SMTO_NORMAL = 0x0002
SMTO_TIMEOUT_MS = 1500

SM_XVIRTUALSCREEN = 76
SM_CYVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

# GUID_MONITOR_ON: {3C57862E-89AB-4A23-9B76-3E77C16516AC}
GUID_MONITOR_ON = struct.pack("<IHH8s", 0x3C57862E, 0x89AB, 0x4A23,
                               bytes.fromhex("9B763E77C16516AC"))

CLASS_NAME = "MonitorPowerSink"

# LRESULT window proc (HWND, UINT msg, WPARAM, LPARAM)
WNDPROTYPE = WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_uint,
                         ctypes.c_ulonglong, ctypes.c_longlong)

u32.DefWindowProcW.restype = ctypes.c_long
u32.DefWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                ctypes.c_ulonglong, ctypes.c_longlong]

u32.CreateWindowExW.restype = ctypes.c_void_p
u32.CreateWindowExW.argtypes = [ctypes.c_void_p,      # hInstance (0, loader ignores)
                                    ctypes.c_wchar_p,          # class name
                                    ctypes.c_wchar_p              # window title
                                    ] + [ctypes.c_void_p] * 9


class _GUID(ctypes.Structure):
    _fields_ = [("b", ctypes.c_char * 16)]


class LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("dwTime", wintypes.DWORD)]


class WNDCLASSEX(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),      # always the first field
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROTYPE),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", ctypes.c_void_p),
                ("hIcon", ctypes.c_void_p),
                ("hCursor", ctypes.c_void_p),
                ("hbrBackground", ctypes.c_void_p),
                ("lpszMenuName", ctypes.c_wchar_p),
                ("lpszClassName", ctypes.c_wchar_p),
                ("hIconSm", ctypes.c_void_p)]


def _def_window(h, m, w, l):
    return int(u32.DefWindowProcW(h, m, w, l) or 0)


class Display(threading.Thread):
    """Hidden window + power sink; owns its thread from cradle to grave.

    Registers the window class, creates the window and the
    RegisterPowerSettingNotification on the SAME thread that pumps the
    message queue (verified: notifications are only delivered to the
    queue of the thread that created the window). Queues ("monitor",
    1.0 | 0.0, ts) events for the state machine; `state` stays current
    so callers can always ask whether the screens are lit.
    """

    def __init__(self, verbose=True):
        super().__init__(daemon=True, name="display-watcher")
        self.verbose = verbose
        self.queue = queue.Queue()
        self.state = 1.0                  # assume on until told otherwise
        self.last_event = 0.0             # monotonic; time of the last
                                          # broadcast we noticed
        self._stop = False
        self._proc = WNDPROTYPE(_def_window)   # keep the callback alive
        self._hwnd = None
        self._handle = None

    def run(self):
        msg = wintypes.MSG()
        u32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 0)  # create the queue
        wc = WNDCLASSEX()
        wc.cbSize = ctypes.sizeof(wc)               # the docs say this is
                                                    # always required
        wc.lpfnWndProc = self._proc
        wc.lpszClassName = CLASS_NAME
        wc.hIcon = u32.LoadIconW(0, 32512)
        wc.hCursor = u32.LoadCursorW(0, 32512)
        atom = u32.RegisterClassExW(ctypes.byref(wc))
        if not atom and k32.GetLastError() != 1407:   # already registered
            log.error("RegisterClassExW failed (%s); no state tracking",
                      k32.GetLastError())
            return
        for parent in (ctypes.c_void_p(-3),             # HWND_MESSAGE:
                                                  # message-only windows
                                                  # are created with -3, the
                                                  # 32-bit value truncates
                      ctypes.c_void_p(0)):            # top level fallback
            self._hwnd = u32.CreateWindowExW(ctypes.c_void_p(0), CLASS_NAME,
                                             None, 0, 0, 0, 64, 64, parent,
                                             None, ctypes.c_void_p(0), None)
            if self._hwnd:
                break
        if not self._hwnd:
            log.error("no window (%s); no state tracking",
                      k32.GetLastError())
            return
        self._handle = u32.RegisterPowerSettingNotification(
            self._hwnd, ctypes.byref(_GUID(b=GUID_MONITOR_ON)), 0,
            DEVICE_NOTIFICATION | SERVICE_NOTIFICATION)
        if not self._handle:
            log.warning("power sink refused (%s); state tracking is a bonus",
                        k32.GetLastError())
        while not self._stop:
            while u32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
                if msg.message == WM_POWER and msg.wParam == PBT_POWER:
                    self._record(msg.lParam)
                u32.DefWindowProcW(msg.hWnd, msg.message, msg.wParam,
                                   msg.lParam)
            time.sleep(0.1)
        u32.UnregisterPowerSettingNotification(self._handle)
        u32.DestroyWindow(self._hwnd)

    def _record(self, lparam):
        """POWERBROADCAST_HDR is Version(4) Guid(16) Length(4) Data[]."""
        header = bytes((ctypes.c_char * 28).from_address(lparam))
        if header[4:20] != GUID_MONITOR_ON:
            return
        flag = struct.unpack("<I", header[24:28])[0]
        self.state = float(flag)
        self.last_event = time.monotonic()
        self.queue.put(("monitor", float(flag), self.last_event))

    def stop(self):
        self._stop = True


watcher = None


def watch(verbose=True):
    """Start the display watcher thread once."""
    global watcher
    if watcher is None:
        watcher = Display(verbose=verbose)
        watcher.start()
    return watcher


def get_display_state():
    """'is the display on' right now (best effort; see module notes)."""
    return bool(watcher.state) if watcher else True


def wait_for(on=True, timeout=1.0):
    """Drain queued events until the display comes up/goes dark.

    Raw SC_MONITORPOWER broadcasts may not emit the notification at all,
    so callers should treat a False return as 'unknown', not 'failed'.
    """
    if watcher is None:
        return False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            event, value, ts = watcher.queue.get(timeout=0.1)
        except queue.Empty:
            continue
        if value == (1.0 if on else 0.0):
            return True
    return False


class MOUSEINPUT(ctypes.Structure):
    # present for the SIZE only: SendInput rejects any cbSize that is
    # not the real INPUT union size, and the mouse case is the widest
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouse_data", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ctypes.c_void_p)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("vk", wintypes.WORD), ("scan", wintypes.WORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("extra", ctypes.c_void_p)]


class INPUT_UNION(ctypes.Union):
    _anonymous_ = ("mouse", "kbd")
    _fields_ = [("mouse", MOUSEINPUT), ("kbd", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", INPUT_UNION)]


def _ctrl_tap():
    """An injected lone modifier: re-trains a stubborn DP link like any
    input does, presses no buttons, and nudges the idle timer we gate
    on - on this box the ONLY input the display stack answers."""
    try:
        down = INPUT(type=INPUT_KEYBOARD)
        down.u.kbd.vk = VK_CONTROL
        up = INPUT(type=INPUT_KEYBOARD)
        up.u.kbd.vk = VK_CONTROL
        up.u.kbd.flags = KEYUP
        n = u32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
        n += u32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
        if n < 2:
            log.debug("ctrl tap dropped by the input stack (%s)",
                      ctypes.GetLastError())
    except Exception:
        log.debug("ctrl tap failed", exc_info=True)


def turn_off():
    """DPMS standby: the same state the power plan timeout uses.
    The W suffix is not decoration: user32.dll exports
    SendMessageTimeoutA/W, never the bare macro name, and ctypes
    raises AttributeError for names a C header only #defines."""
    log.debug("sending SC_MONITORPOWER(2) ...")
    user32 = u32
    user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SYSCOMMAND,
                               SC_MONITORPOWER, MONITOR_OFF, SMTO_NORMAL,
                               SMTO_TIMEOUT_MS,
                               ctypes.byref(ctypes.c_ulong()))
    if watcher:
        watcher.state = 0.0


def wake(timeout=2.0):
    """Restore the display, input FIRST.

    Measured on this box, the ON broadcast alone is effectless (NVIDIA
    + DP drops the link and the driver ignores the legacy request), and
    every "supported" one-shot turned out dead here: powrprof.dll
    exports NO CallNtPowerRequest at all (AttributeError, probed), the
    powercfg CLI has no video-on keyword in its request table (probed),
    and kernel32's PowerCreateRequest takes a REASON_CONTEXT with no
    video-on type to ask for. Injected input is the only measured
    weapon - real mouse movement always lights these panels, and
    SendInput rides the same stack - so: CTRL tap, then exactly one
    broadcast round (harmless, and honored on other machines), the
    ES_DISPLAY_REQUIRED pulse for the idle timer, tap again in case
    the round swallowed the first. The old 3-round loop burned 17.7 s
    in a blackout because wait_for's notification never arrives here
    (README quirk) - every round ran even after the panels lit.
    """
    _ctrl_tap()
    u32.SendMessageTimeoutW(HWND_BROADCAST, WM_SYSCOMMAND,
                             SC_MONITORPOWER, MONITOR_ON, SMTO_NORMAL,
                             SMTO_TIMEOUT_MS,
                             ctypes.byref(ctypes.c_ulong()))
    k32.SetThreadExecutionState(ES_CONTINUOUS | ES_DISPLAY_REQUIRED)
    time.sleep(0.2)
    k32.SetThreadExecutionState(ES_CONTINUOUS)
    _ctrl_tap()
    if watcher:
        watcher.state = 1.0
    return True


def set_hold(display=False, system=False):
    """Windows' own idle timers, suppressed exactly as the policy
    asks: DISPLAY resets/holds off the screen timeout, SYSTEM the
    sleep timeout (ES_DISPLAY alone still lets the box sleep under
    a lit screen). Requests are per-thread and die with the process,
    so a crash hands the machine back to the power plan - fail open
    by construction. Every caller lives on the monitor loop thread;
    one owner keeps the policy honest."""
    flags = ES_CONTINUOUS
    if display:
        flags |= ES_DISPLAY_REQUIRED
    if system:
        flags |= ES_SYSTEM_REQUIRED
    k32.SetThreadExecutionState(flags)


def get_idle_time():
    """Seconds since the last keyboard or mouse input."""
    info = LastInputInfo()
    info.cbSize = ctypes.sizeof(info)
    if not u32.GetLastInputInfo(ctypes.byref(info)):
        return float("inf")
    if info.dwTime == 0xFFFFFFFF:              # no input recorded yet
        return float("inf")
    return max(k32.GetTickCount() - info.dwTime, 0) / 1000.0


def foreground_is_fullscreen():
    """True when the foreground window covers the whole virtual desktop:
    exclusive-fullscreen apps swallow SC_MONITORPOWER broadcasts, so the
    guard refuses to send them while a game owns the display. Borderless
    windows do receive the message, so only the rect comparison matters.
    """
    hwnd = u32.GetForegroundWindow()
    if not hwnd:
        return False
    rect = wintypes.RECT()
    if not u32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    x = u32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y = u32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    width = u32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    height = u32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return (rect.left, rect.top, rect.right - rect.left,
            rect.bottom - rect.top) == (x, y, width, height)

