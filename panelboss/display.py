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
- the away-lift ears (a dimmed desk waking on real input): RAWINPUT
  registrations bound to the watcher's own window, ACTIVE ONLY while
  a spell lives - WM_INPUT is a posted message for us alone, so an
  unarmed machine pays nothing and an armed spell costs the parse,
  never the desktop's input chain (the WH_KEYBOARD_LL/WH_MOUSE_LL
  era of this feature measured a ~31 ms dispatch quantum on any
  pumping thread - a 32 Hz mouse for the whole desk; the matrix that
  killed it is documented at the raw block below)
- foreground fullscreen detection: exclusive-fullscreen apps swallow the
  broadcast, so the guard skips them
- the dimmer's hotkey door (request_hotkey): RegisterHotKey and
  UnregisterHotKey belong to the thread that owns the window and
  pumps its queue (measured Oct-15: a cross-thread register is
  refused with 1408, ERROR_INVALID_HOTKEY_WINDOW; a wrong-thread
  unregister leaks the registration), so the arm leaves a NOTE here
  and the pump loop applies it - the _ear_req idiom, not new
  machinery; (ok, errno) travels back on the note's event
- the away dim spell's corner jail: covered rects get the cursor
  parked (jail_cursor/unjail_cursor) - a SetCursorPos move generates
  no raw input, so the jail can never wake what it covers

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

u32.GetCursorPos.restype = ctypes.c_int            # pin law, Oct 15:
u32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]   # self-
u32.SetCursorPos.restype = ctypes.c_int                         # pinned,
u32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]       # no order luck
u32.RegisterHotKey.restype = ctypes.c_int          # the hotkey pair is
u32.RegisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int,  # applied on
                               ctypes.c_uint, ctypes.c_uint]   # the pump
u32.UnregisterHotKey.restype = ctypes.c_int                     # thread only
u32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
u32.PostMessageW.restype = ctypes.c_int             # the hotkey note's
u32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                             ctypes.c_void_p, ctypes.c_void_p] # wake
k32 = ctypes.windll.kernel32
wts = ctypes.windll.wtsapi32     # the session-event ear's door
                                 # (WTSRegisterSessionNotification);
                                 # its absence is a warning, never a
                                 # boot-killer - the camera path is
                                 # the load-bearing lift

WM_SYSCOMMAND = 0x112
SC_MONITORPOWER = 0xF170
HWND_BROADCAST = 0xFFFF        # every top-level window receives it
HWND_MESSAGE = -3              # (HWND)-3 per winuser.h; the 32-bit legacy
                               # 0xFFFFFFF0 is (HWND)-16 and fails to create
                               # on this 64-bit box (measured)
MONITOR_ON = 1
MONITOR_OFF = 2                # DPMS standby, same as the power plan

WM_POWER = 0x218
PBT_POWER = 4                  # lParam points to a POWERBROADCAST_HDR
WM_DISPLAYCHANGE = 0x7E        # the color/topology broadcast (amendment
                               # 8): sent when HDR flips, a mode lands
                               # or a monitor joins - by US or by
                               # anyone else's hand
WS_VISIBLE = 0x10000000        # the delivery shape for the above
WS_EX_TOOLWINDOW = 0x80        # (visible but nowhere to be seen)

WM_DISPLAYCHANGE = 0x007E      # topology moved: the brightness handles
                               # may be stale (see _bright.invalidate;
                               # honest limit: a message-only window
                               # never hears this broadcast, the
                               # refusal-self-heal is the real law)

WM_KEYDOWN = 0x0100            # the raw keyboard record carries it
WM_WTSSESSION_CHANGE = 0x02A2  # wParam is the session STATE change -
                               # the lock-aware lift's one honest
                               # knock: raw input is per-desktop, so
                               # the away-lift ears go deaf while
                               # Winlogon owns the desk; this message
                               # rides the window's thread queue from
                               # the session itself either way
WTS_SESSION_UNLOCK = 0x08      # wtsapi3.h (its sibling LOCK is 0x07;
                               # the names are the numbers' only
                               # source worth trusting at this FFI)
WTS_CONSOLE_CONNECT = 0x01     # the transport flips (wtsapi3.h): a
WTS_CONSOLE_DISCONNECT = 0x02  # session changing transport - or any
WTS_REMOTE_CONNECT = 0x03      # session coming and going - changes
WTS_REMOTE_DISCONNECT = 0x04   # the DESK: the RDP canvas appears and
                               # vanishes with the attach, so every
                               # flip re-mints the display set (the
                               # pump routes all four to
                               # _display_moved; lParam carries the
                               # sessionId, the old idiom read it
                               # from wParam - the id rode the wrong
                               # parameter)
NOTIFY_FOR_THIS_SESSION = 0    # the register flag: a tray app lives
                               # in the owner's session and needs no
                               # other one's news
MOUSE_WAKE_PX = 20             # the debounce law: cursor jitter must
                               # not wake a dimmed desk; movement
                               # counts only past this (displacement
                               # from the first delta after the arm -
                               # RAW's relative motion made this law
                               # honest in a way absolute coords
                               # never were)

# THE EARS, RAW (36e3214 follow-up, measured): the WH_*_LL shape was
# first, and the matrix killed it - an LL callback dispatches on its
# owning thread through a sent-message round-trip that measured
# QUANTIZED at ~31 ms per event on any pumping thread (injected or
# hardware, foreground or not), i.e. a 32 Hz stutter for the WHOLE
# desktop for as long as the spell lives, because the hook chain
# gates everyone's input. RAWINPUT is the same intelligence without
# the round-trip: WM_INPUT is a POSTED message for OUR window only,
# it rides the loop's normal wake (QS_RAWINPUT below), no callback
# ever runs on anyone else's input path, and the mouse's RELATIVE
# deltas implement the >20 px jitter law exactly as written.
WM_INPUT = 0x00FF
RIDEV_REMOVE = 0x00000001
RIDEV_INPUTSINK = 0x00000100   # deliver while our window is unfocused
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
RIM_TYPEKEYBOARD = 1
QS_RAWINPUT = 0x0100


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.UINT), ("dwSize", wintypes.UINT),
                ("hDevice", ctypes.c_void_p),
                ("wParam", ctypes.c_ulonglong)]


class RAWMOUSE(ctypes.Structure):
    class _U(ctypes.Union):
        class _S(ctypes.Structure):
            _fields_ = [("ulButtons", wintypes.USHORT),
                        ("buttonFlags", wintypes.USHORT),
                        ("buttonData", wintypes.ULONG)]
        _fields_ = [("buttons", _S),
                    ("rawButtons", wintypes.USHORT),
                    ("rawButtonData", wintypes.ULONG)]
    _fields_ = [("flags", wintypes.USHORT), ("_pad", wintypes.USHORT),
                ("u", _U),
                ("lastX", wintypes.LONG), ("lastY", wintypes.LONG)]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [("makeCode", wintypes.USHORT), ("flags", wintypes.USHORT),
                ("reserved", wintypes.USHORT), ("vkey", wintypes.USHORT),
                ("message", wintypes.UINT), ("extraInfo", wintypes.UINT)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER),
                ("mouse", RAWMOUSE), ("keyboard", RAWKEYBOARD)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT),
                ("usUsage", wintypes.USHORT),
                ("flags", wintypes.UINT), ("hwndTarget", ctypes.c_void_p)]


class RAWINPUTDEVICELIST(ctypes.Structure):     # only for the unregister
    _fields_ = [("hDevice", ctypes.c_void_p), ("type", wintypes.UINT)]

# pump cadence, the two faces of the SAME loop: while ANY ear is on
# duty the wait floor is 20 ms (input itself wakes the wait early -
# QS_RAWINPUT below - so the floor only bounds _stop/_ear_req
# service); deaf, the old 100 ms. The cadence lesson that produced
# these numbers lives at the RAWINPUT block: a SLEEPING thread
# dispatches no hook callbacks at all (fast-poll measured 33/s for
# the whole armed phase), and even input-aware waiting could not
# beat the hook round-trip - the raw shape made the floor irrelevant
# to latency and this block is what's left of the chase.
ARMED_PAUSE_SEC = 0.020
IDLE_PAUSE_SEC = 0.1
QS_ALLEVENTS = 0x0400          # key, mouse, posted, timer, paint, sent
MWMO_INPUTAVAILABLE = 0x0004   # and wake NOW on input already queued

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x1       # keep the box awake while we poll the camera
ES_DISPLAY_REQUIRED = 0x2      # resets the display idle timer (wake fallback)

INPUT_KEYBOARD = 1             # SendInput inject: the only weapon that
KEYUP = 0x0002                 # measurably lights these panels (see wake)
VK_CONTROL = 0x11              # a lone modifier presses no buttons

DEVICE_NOTIFICATION = 1
SERVICE_NOTIFICATION = 2

SMTO_ABORTIFHUNG = 0x0002     # was mis-named SMTO_NORMAL since first
                              # write (Oct-16 audit): SMTO_NORMAL is
                              # 0x0000; the VALUE here is the abort
                              # flag, and it is the RIGHT one for a
                              # broadcast power command. Value kept,
                              # name corrected.
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

# partial argtypes would reject the 4-arg call, so the full pin lands now;
# the hwnd slot is c_void_p so the 64-bit sink handle never truncates
u32.RegisterPowerSettingNotification.restype = ctypes.c_void_p
u32.RegisterPowerSettingNotification.argtypes = [ctypes.c_void_p,
                                                 ctypes.c_void_p,
                                                 ctypes.c_uint,
                                                 ctypes.c_uint]
# no-arg call, so a restype pin only: the default c_int restype would
# truncate a 64-bit HWND before the caller sees it
u32.GetForegroundWindow.restype = ctypes.c_void_p
# the twin of the Register pin above (gate LOW): the 64-bit sink handle
# must survive the way IN (default c_int truncates it to a corpse), and
# an unregister raising must not skip the DestroyWindow sharing its
# cleanup try-block
u32.UnregisterPowerSettingNotification.argtypes = [ctypes.c_void_p]
u32.UnregisterPowerSettingNotification.restype = ctypes.c_long   # BOOL

# the session-unlock ear's pair (lock-on-away wave): the hwnd slot is
# c_void_p on both, so the 64-bit window handle survives the way IN
# exactly like the power-sink pin above demanded
wts.WTSRegisterSessionNotification.argtypes = [ctypes.c_void_p,
                                               wintypes.DWORD]
wts.WTSRegisterSessionNotification.restype = wintypes.BOOL
# the W capital in UnRegister is the OS's own typo (probed at import:
# WTSUnregisterSessionNotification does not exist on wtsapi32; ctypes
# raises, and the suite is what caught it here)
wts.WTSUnRegisterSessionNotification.argtypes = [ctypes.c_void_p]
wts.WTSUnRegisterSessionNotification.restype = wintypes.BOOL


class _GUID(ctypes.Structure):
    _fields_ = [("b", ctypes.c_char * 16)]


WM_HOTKEY = 0x0312               # the dimmer's pause press: registered
                                 # by the PUMP THREAD against THIS
                                 # window (the 1408 lesson - see the
                                 # note block at _service_hotkey),
                                 # and WM_HOTKEY is a POSTED message -
                                 # it rides the queue (the broadcast
                                 # lesson's twin: sent goes to the
                                 # proc, posted goes to the loop below)
WM_APP = 0x8000                  # private message range; +1 is the
                                 # dimmer's hotkey note landing. The
                                 # post is a WAKE ONLY - the pump
                                 # applies whatever note it finds, no
                                 # payload travels on the message


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


_ACTIVE = []                   # the live Display, one per process: a
                               # broadcast is SENT straight to the
                               # window proc (it never rides the
                               # queue), and a module-level proc has
                               # no self - the queue is reached
                               # through this one-slot list


# (the WH_*_LL era of this file is documented above and in the awaymode
# lifecycle pin - the KBDLLHOOKSTRUCT/MSLLHOOKSTRUCT twins and the
# SetWindowsHookExW argtype block were deleted with the callbacks, not
# left to fossil: dead FFI is a lie about what the module calls)

u32.MsgWaitForMultipleObjectsEx.argtypes = [
    wintypes.UINT, ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
    wintypes.UINT, wintypes.UINT]
u32.MsgWaitForMultipleObjectsEx.restype = wintypes.DWORD
u32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE),
                                        wintypes.UINT, wintypes.UINT]
u32.RegisterRawInputDevices.restype = wintypes.BOOL
u32.GetRawInputData.argtypes = [ctypes.c_void_p, wintypes.UINT,
                                ctypes.c_void_p,
                                ctypes.POINTER(wintypes.UINT),
                                wintypes.UINT]
u32.GetRawInputData.restype = wintypes.UINT


def _def_window(h, m, w, l):
    if m == WM_DISPLAYCHANGE and _ACTIVE:
        # amendment 8's ear: WM_DISPLAYCHANGE (HDR flip, mode change,
        # a monitor joining) is delivered by SEND, so the pump loop's
        # PeekMessage never sees it - measured Oct 13, twice: an
        # invisible top-level got nothing at all (the broadcast
        # enumerator skips hidden windows), and a visible one caught
        # the message in the PROC, not the queue. WS_VISIBLE +
        # WS_EX_TOOLWINDOW at -32000 is the shape: on screen
        # nowhere, in Alt+Tab never.
        try:
            _ACTIVE[0]._display_moved()      # the away wave's second
            #                                duty rides the SAME branch
            #                                (the merge law): post the
            #                                event AND invalidate the
            #                                brightness handles - the
            #                                topology moving makes the
            #                                HMONITOR-scoped DDC/CI
            #                                cache suspect, and the
            #                                hdrwatch arm reads the
            #                                queue event
        except Exception:
            pass               # a dying watcher loses an event, not
                               # the process; state fail-opens anyway
    return int(u32.DefWindowProcW(h, m, w, l) or 0)


# The call-time neutralizer for RegisterRawInputDevices (see
# Display._register_ears for the whole disease): a real windll
# function carries the cross-module class binding that must go; the
# suites' fakes carry none (and a bound METHOD cannot even hold the
# attribute - awaymode_test's AttributeError mid-sweep), so the
# clear is attempted and forgiven exactly where it cannot apply.
def _neutral_reg_bind(lib):
    try:
        lib.RegisterRawInputDevices.argtypes = None
    except AttributeError:
        pass


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
        self._lift_armed = False               # the away engine's flag
        self._lift_origin = None               # mouse travel accumulator
        self._ear_req = None                   # pending register/unregister
        self._hotkey_req = None                # the dimmer's pending
        #                                      # (op, mods, vk,
        #                                      # done_event, result) note
        #                                      # set AFTER __init__: the
        #                                      # pump reads it in
        #                                      # _pump_pause, and a field
        #                                      # born only at run() time
        #                                      # AttributeError'd the
        #                                      # away-suite's pre-run
        #                                      # pause probe (Oct 15)
        self._hooked = False                   # requests are APPLIED on
        #                                      the pump thread (the raw
        #                                      registrations bind to
        #                                      this thread's window),
        #                                      so the engine only ever
        #                                      leaves a note: None = no
        #                                      request, True/False = want
        self._hwnd = None
        self._handle = None
        self._wts_reg = False                  # the session-unlock ear's
        #                                      own life: refused or
        #                                      message-only means no
        #                                      word, and the camera
        #                                      path stands alone
        _ACTIVE[:] = [self]                    # the broadcast ear's route

    def run(self):
        try:
            self._run()
        except Exception:
            # a startup raise used to leave the global watcher set with a
            # dead thread: confess, then let the state machine's
            # watcher-is-None path (assume-on) own the failure
            log.exception("display watcher died at startup")
            raise
        finally:
            self._settle()

    def _settle(self):
        """Confess any unrequested exit and null the global watcher."""
        if self._handle and not self._stop:
            log.error("display watcher exiting without a stop request")
        if _ACTIVE[:1] == [self]:
            del _ACTIVE[0]                 # the ear goes deaf with the
                                           # window: no event to a corpse
        global watcher
        if watcher is self:
            watcher = None

    def _run(self):
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
        for parent, top_level in ((ctypes.c_void_p(0), True),   # the broadcast
                                  (ctypes.c_void_p(HWND_MESSAGE), False)):  # shape, see below
            # WS_VISIBLE + WS_EX_TOOLWINDOW at a position off every
            # screen: the shape that measurably RECEIVES
            # WM_DISPLAYCHANGE (a bare invisible top-level got
            # nothing, and a message-only window is not top-level at
            # all - both proven Oct 13 against real hdr_set round
            # trips). Toolwindow keeps it out of Alt+Tab; off-screen
            # keeps it out of every screenshot; the power sink
            # registers identically. HWND_MESSAGE remains the
            # fallback: a station that refuses top-levels still gets
            # the power half, just deaf to display broadcasts.
            self._hwnd = u32.CreateWindowExW(WS_EX_TOOLWINDOW, CLASS_NAME,
                                             None, WS_VISIBLE,
                                             -32000, -32000, 64, 64,
                                             parent,
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
        # the session-unlock ear (lock-on-away wave): the TOP-LEVEL
        # shape only - a message-only window hangs off no desktop, and
        # its WTS registration is the answering-nothing class (silent
        # ignorance pre-confessed instead). If this ear's delivery ever
        # proves a lie, the camera eye still lifts the spell through
        # the lock - the feature never leans on this knock alone.
        if top_level and wts.WTSRegisterSessionNotification(
                self._hwnd, NOTIFY_FOR_THIS_SESSION):
            self._wts_reg = True
        elif not top_level:
            log.info("watcher is message-only; the session-unlock ear "
                     "stays deaf, the camera carries the lift")
        else:
            log.warning("session-unlock ear refused (%s); the camera "
                        "carries the lift", k32.GetLastError())
        self._hooked = False
        self._ear_req = None
        self._hotkey_req = None              # the dimmer's pending
        #                                    # (op, mods, vk,
        #                                    # done_event, result) note
        while not self._stop:
            # Drain EVERY pending message per cycle (the inner while
            # is the whole answer: with the input-aware wait below,
            # bursts arrive between waits and get one dispatch).
            while u32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
                # WM_DISPLAYCHANGE is NOT handled here: a broadcast
                # is sent to the window proc (the _def_window ear)
                # and never rides this queue; only the REGISTERED
                # power notification lands as a queued message
                if msg.message == WM_HOTKEY:
                    # the dimmer's pause toggle: the key was registered
                    # against this window, so the post lands in this
                    # queue. One flag-set on the pump thread - the flip
                    # belongs on the state loop's own beat (the cross-Tk
                    # law says a foreign-thread checkbox write is the
                    # bug class). The belt: only OUR id wakes the
                    # dimmer - a foreign WM_HOTKEY falls through
                    # untouched. The Oct-15 wire truth (the "presses
                    # and nothing happens" hunt): the arrival itself is
                    # logged - if a press never prints this line, the
                    # message never reached this queue; if it prints
                    # with a foreign wParam, the id belt is honest.
                    try:
                        from . import dimmer
                        log.info("display: WM_HOTKEY wParam=%#x on "
                                 "hwnd=%#x (want %#x)", msg.wParam,
                                 self._hwnd or 0, dimmer.HOTKEY_ID)
                        if msg.wParam == dimmer.HOTKEY_ID:
                            dimmer.hotkey_press()
                    except Exception:
                        pass           # a dimmer that cannot hear is a
                                       # dimmer, not a dead pump
                elif msg.message == WM_POWER and msg.wParam == PBT_POWER:
                    if not msg.lParam:
                        # NULL is an ACCESS VIOLATION, not an exception:
                        # from_address(0) kills this thread natively,
                        # below any except (the lane's probe measured
                        # 0xC0000005; the try below only guards malformed
                        # NON-NULL payloads - audit HIGH's real fix is
                        # refusing the null before the read)
                        log.warning("WM_POWER payload pointer is null; "
                                    "message skipped")
                    else:
                        try:
                            self._record(msg.lParam)
                        except Exception:
                            # fail-open per message: the watcher's death is
                            # the bug, one bad lParam must not kill it
                            log.exception("power record failed (lParam=%r); "
                                           "message skipped", msg.lParam)
                elif msg.message == WM_DISPLAYCHANGE:
                    # belt, kept honest by the ear's comment: a send
                    # never rides this queue (measured Oct 13), so
                    # this branch fires only for stations that DO
                    # queue one - same method, same two duties
                    self._display_moved()
                elif msg.message == WM_INPUT:
                    # the raw lift ears: POSTED to our window only -
                    # no callback ever runs on anyone else's input
                    # path, which is the whole point of the shape
                    try:
                        self._raw_probe(msg.lParam)
                    except Exception:
                        log.debug("raw input probe skipped",
                                  exc_info=True)
                elif msg.message == WM_WTSSESSION_CHANGE:
                    # the lock-aware lift (lock-on-away): posted by
                    # the session itself, deaf-desk or not. wParam is
                    # the EVENT, lParam the sessionId (the widened
                    # call below carries both; the old idiom dropped
                    # the lParam and the lock/unlock read rode the
                    # wrong parameter's coattails)
                    self._session_change(msg.wParam, msg.lParam)
                u32.DefWindowProcW(msg.hWnd, msg.message, msg.wParam,
                                   msg.lParam)
            self._service_ears()               # the engine's arm notes
            #                                  are APPLIED here, on the
            #                                  pump thread - and the
            #                                  wait below wakes on the
            #                                  raw ears' events
            #                                  (QS_RAWINPUT) as well
            #                                  as the pause floor
            self._service_hotkey()             # the dimmer's hotkey note
            #                                  # too: the registration
            #                                  # belongs to this thread
            #                                  # (the 1408 law), the
            #                                  # WM_APP post was its wake
            u32.MsgWaitForMultipleObjectsEx(
                0, None, int(self._pump_pause() * 1000),
                QS_ALLEVENTS | QS_RAWINPUT, MWMO_INPUTAVAILABLE)
        self._release_ears()                   # the lift ears die with
        #                                      the thread, cradle to grave
        if self._hotkey_req is not None:       # a note posted as the
            #                                  # pump went out: a refusal
            #                                  # now, never a caller left
            #                                  # waiting on a dead queue
            _req, self._hotkey_req = self._hotkey_req, None
            _req[4] = (False, 0)
            _req[3].set()
        try:
            if self._wts_reg:
                wts.WTSUnRegisterSessionNotification(self._hwnd)
            u32.UnregisterPowerSettingNotification(self._handle)
            u32.DestroyWindow(self._hwnd)
        except Exception:
            log.exception("display watcher shutdown failed")

    def _record(self, lparam):
        """POWERBROADCAST_HDR is Version(4) Guid(16) Length(4) Data[]."""
        header = bytes((ctypes.c_char * 28).from_address(lparam))
        if header[4:20] != GUID_MONITOR_ON:
            return
        flag = struct.unpack("<I", header[24:28])[0]
        self.state = float(flag)
        self.last_event = time.monotonic()
        self.queue.put(("monitor", float(flag), self.last_event))

    def _session_change(self, wparam, lparam=0):
        """One WM_WTSSESSION_CHANGE: wParam the EVENT, lParam the
        sessionId (the default keeps every single-arg call site -
        incl. the suite's - working). The UNLOCK word lifts the spell
        through the locked desktop - the raw ears are per-desktop and
        deaf behind Winlogon, so this is the one knock the locked
        desk can still make (the camera eye makes another; the spell
        answers to neither the mouse nor the faith). LOCK is ignored:
        the spell is already dark, and re-darking a dark desk is
        noise. The transport flips (console/remote connect and
        disconnect) RE-DERIVE the desk: the display set re-mints
        wholesale when the RDP canvas appears or vanishes - the same
        re-derive idiom the display-change ear rides."""
        if wparam == WTS_SESSION_UNLOCK:
            self.queue.put(("session_unlock", 1.0, time.monotonic()))
        elif wparam in (WTS_CONSOLE_CONNECT, WTS_CONSOLE_DISCONNECT,
                        WTS_REMOTE_CONNECT, WTS_REMOTE_DISCONNECT):
            log.info("session %s: transport flip %#x, re-deriving the "
                     "desk", lparam or "?", wparam)
            self._display_moved()

    # -------------------------------------------------------- the lift ears --
    def _pump_pause(self):
        """The wait floor (36e3214 follow-up): 20 ms while ANY ear is
        on duty (registered, or a request in flight - the note's own
        wait is part of the spell's latency budget), the old 100 ms
        deaf. With RAWINPUT the wait also WAKES on the input itself
        (QS_RAWINPUT), so the floor only bounds _stop/_ear_req
        service (the hotkey note wakes on its WM_APP+1 post; the
        floor is its belt, not its route); a spell pays CPU nowhere
        near the stutter the LL
        round-trip charged. Deaf floor untouched: the mode-off idle
        profile 36e3214 measured (0.02-0.06 cores) is unchanged."""
        if (self._hooked or self._ear_req is not None
                or self._hotkey_req is not None):
            return ARMED_PAUSE_SEC
        return IDLE_PAUSE_SEC

    def _service_ears(self):
        """Apply the engine's pending arm note (called from the pump
        loop - the registration is bound to THIS thread's window).
        Idempotent both ways: an arm over live ears and a disarm
        over deaf ones cost nothing, so a steady spell never churns."""
        want = self._ear_req
        if want is None or bool(want) == self._hooked:
            self._ear_req = None
            return
        if want:
            self._register_ears()
        else:
            self._release_ears()
        self._ear_req = None

    def request_hotkey(self, op, mods=0, vk=0):
        """The dimmer's hotkey knock, NOTE-AND-WAIT (the _ear_req
        idiom's twin): the store and a WM_APP+1 post - the pump's
        wait already wakes on posted input - and the PUMP thread
        applies it against its own window (1408, measured Oct-15:
        RegisterHotKey from a foreign thread is refused for a foreign
        window; the un-knock crosses too, a wrong-thread unregister
        leaks the registration in the owning queue). Blocks on the
        note's event: a wedged pump answers (False, 0) after the
        wait's bound, never a silent hang - the monitor tick that
        carries the arm may not die on the desk's behalf."""
        done = threading.Event()
        note = [op, int(mods), int(vk), done, (False, 0)]
        self._hotkey_req = note
        u32.PostMessageW(self._hwnd, WM_APP + 1, 0, 0)
        done.wait(5.0)
        return note[4]

    def _service_hotkey(self):
        """Apply the pending hotkey note, on the pump loop (every
        verb here belongs to THIS thread's window). The belt is
        honest: only our id is touched, the refusal keeps its real
        number (k32.GetLastError is this module's errno route - the
        windll handle here does not carry ctypes' copy), and the
        caller's event is set whatever happens - a note never dies
        waiting."""
        note = self._hotkey_req
        if note is None:
            return
        self._hotkey_req = None
        op, mods, vk, done, _res = note
        ok, err = False, 0
        try:
            from . import dimmer
            if op == "register":
                ok = bool(u32.RegisterHotKey(self._hwnd, dimmer.HOTKEY_ID,
                                             mods, vk))
            elif op == "unregister":
                ok = bool(u32.UnregisterHotKey(self._hwnd, dimmer.HOTKEY_ID))
            if not ok:
                # the windll handle here carries no ctypes copy
                # (use_last_error is dimmer's shape, display's house
                # verb is the real k32.GetLastError, as every refusal
                # line in this module already reads): the pump thread
                # calls the API directly, the number is its own.
                err = k32.GetLastError()
        except Exception:                    # a dead hwnd mid-knock:
            err = k32.GetLastError()          # the refusal rides the
            #                                 # same (False, errno)
            #                                 # road back, no raise
        note[4] = (ok, err)
        done.set()

    _DEVICES = ((1, 2), (1, 6))      # generic-desktop pointer, keyboard

    def _device_array(self, remove=False):
        arr = (RAWINPUTDEVICE * len(self._DEVICES))()
        for row, (page, usage) in zip(arr, self._DEVICES):
            row.usUsagePage = page
            row.usUsage = usage
            row.flags = RIDEV_REMOVE if remove else RIDEV_INPUTSINK
            row.hwndTarget = 0 if remove else (self._hwnd or 0)
        return arr

    def _register_ears(self):
        """RAWINPUT, not the hook chain (the matrix killed the LL
        shape: its callback dispatch measured 31 ms-quantized on ANY
        pumping thread - the hook chain gates EVERY desktop's input
        through it, so a spell used to mean a 32 Hz mouse). These
        registrations deliver to our window only, and only while a
        spell is alive; a mode-off machine never registers anything -
        invisible by construction, same law as before.

        THE CALL-TIME NEUTRAL BINDING (the owner's desk, Oct 21,
        twice: 'display watcher died at startup', ctypes.ArgumentError
        'expected LP_RAWINPUTDEVICE instance instead of
        RAWINPUTDEVICE_Array_2', 08:25 and 11:18): argtypes on the
        shared windll function object are a CROSS-MODULE property -
        _inputtruth_hook (the inputtruth pump's ears) re-binds it to
        ITS OWN struct class when the pump installs, and a raw array
        of display's struct then raises through the pump thread and
        kills the watcher (argtypes measure the class IDENTITY, so
        two same-laid-out classes are two types here; byref does not
        pierce the class check either - measured in the pin's probe:
        the message only changes to 'pointer to RAWINPUTDEVICE'). The
        gate named two candidate shapes - byref or missing argtypes;
        only the missing one survives every module order: clear the
        binding at the call, and ctypes auto-converts the array with
        no class check (the classic shape the pre-argtypes era used).
        Leaving it cleared is safe for the hook's later calls too -
        its array converts under no binding exactly like ours. The
        neutralizer is a module function because a fake user32 whose
        registration is a plain METHOD has no attr slot for argtypes
        (awaymode_test proved it mid-sweep the hard way), and a fake
        with no binding is exactly as neutral as one that clears."""
        _neutral_reg_bind(u32)
        arr = self._device_array()
        self._hooked = bool(u32.RegisterRawInputDevices(
            arr, len(arr), ctypes.sizeof(RAWINPUTDEVICE)))
        if not self._hooked:
            log.warning("raw lift ears refused (%s); the dimmed desk "
                        "wakes on the idle gate alone (one tick slower)",
                        k32.GetLastError())

    def _release_ears(self):
        # RIDEV_REMOVE through the SAME entry point (this OS exports
        # no UnregisterRawInputDevices at all - measured): flags
        # RIDEV_REMOVE + null target is the documented un-take. Same
        # call-time neutral binding as _register_ears (the sibling of
        # the same cross-module disease: the pump died at register
        # long before this line ever ran to find out).
        _neutral_reg_bind(u32)
        arr = self._device_array(remove=True)
        if not u32.RegisterRawInputDevices(
                arr, len(arr), ctypes.sizeof(RAWINPUTDEVICE)):
            log.debug("raw lift ears unregister was declined (%s)",
                      k32.GetLastError())
        from . import inputtruth
        inputtruth.re_register()
        # our remove is process-wide; the sibling ear re-arms or the
        # desk goes deaf (Oct-23 dossier A)
        self._hooked = False

    def _raw_probe(self, handle):
        """One WM_INPUT: posted, ours, zero round-trips. The cheap
        shield FIRST (unarmed ears read nothing - one int compare
        per event while a steady spell idles), then the wake laws:
        any keydown, or mouse travel past MOUSE_WAKE_PX measured as
        displacement from the first post-arm delta (jitter orbits
        its anchor and must not wake; the RELATIVE deltas RAW gives
        are what made that law honest in the first place)."""
        if not self._lift_armed or not handle:
            return
        size = wintypes.UINT(0)
        if u32.GetRawInputData(handle, RID_INPUT, None,
                               ctypes.byref(size),
                               ctypes.sizeof(RAWINPUTHEADER)) != 0 \
                or not size.value:
            return
        buf = (ctypes.c_char * size.value)()
        if u32.GetRawInputData(handle, RID_INPUT, buf, ctypes.byref(size),
                               ctypes.sizeof(RAWINPUTHEADER)) != size.value:
            return
        raw = bytes(buf) + b"\0" * 64          # short buffers read clean
        head = RAWINPUTHEADER.from_buffer_copy(raw)
        base = ctypes.sizeof(RAWINPUTHEADER)
        if head.dwType == RIM_TYPEKEYBOARD:
            kb = RAWKEYBOARD.from_buffer_copy(raw, base)
            if kb.message == WM_KEYDOWN:
                self._lift_now("key")
        elif head.dwType == RIM_TYPEMOUSE:
            mo = RAWMOUSE.from_buffer_copy(raw, base)
            if mo.flags & 0x01:                # MOUSE_MOVE_ABSOLUTE (0x01;
                return                         # 0x02 is VIRTUAL_DESKTOP -
                                               # gate finding 2's one-liner)
            ox, oy = self._lift_origin or (0, 0)
            ox += mo.lastX
            oy += mo.lastY
            self._lift_origin = (ox, oy)       # jitter orbits the anchor
            if ox * ox + oy * oy > MOUSE_WAKE_PX ** 2:
                self._lift_now("mouse")

    def _lift_now(self, reason):
        """One lift per arm (a held key re-arms the raw stream by the
        second): the ears go quiet until the engine re-arms at the
        next dark, and the engine is the only re-armor."""
        self._lift_armed = False
        self._lift_origin = None
        self.queue.put(("away_lift", reason, time.monotonic()))

    def _display_moved(self):
        try:
            from . import wm
            wm._bright.invalidate()
        except Exception:
            log.debug("brightness cache nudge failed (self-heal rides)",
                      exc_info=True)
        self.queue.put(("displaychange", 0.0, time.monotonic()))

    def stop(self):
        self._stop = True


def arm_input_lift(armed):
    """The engine's one word to the lift ears: armed=True wants them
    ON, armed=False sends them home - the word is a NOTE the pump
    applies on its own thread within one pause (20 ms while a note
    is in flight; the raw registrations bind to the watcher's window,
    so the engine never touches user32 itself). A mode-off machine
    never gets the word, so nothing is registered at all and the
    input path is clean by CONSTRUCTION, not by a flag check.
    Arming resets the mouse travel accumulator; the flag decides
    whether registered ears speak at all (one lift per arm)."""
    if watcher is not None:
        watcher._lift_armed = bool(armed)
        watcher._lift_origin = None
        watcher._ear_req = bool(armed)


# the corner jail (away wave, owner request): the cursor parks at a
# covered rect's far corner while a dim spell covers it, and comes
# home with the spell. The move generates NO raw input (the ears read
# the RAW stream only - a SetCursorPos warp is invisible to it,
# verified against the raw block above), so the jail can never wake
# what it covers; the far corner is where the pointer stops being a
# witness on the dark panel.
_jail_saved = None


def park_cursor(x, y):
    """Move the pointer to ONE exact point - no save, no restore (the
    owner's law, Oct 17: 'noone remembers where there cursor was
    after leaving the room'). The warp never counts as input: a
    SetCursorPos move is invisible to the raw stream (verified for
    the jail below, same verb), so the park cannot wake what it
    covers. A refused move is a shrug - the pointer sits where the
    leaving hand left it, and the spell proceeds uncuffed."""
    try:
        u32.SetCursorPos(int(x), int(y))        # pinned at import,
        #                              the Oct-15 freeze law
        return True
    except Exception:
        return False


def jail_cursor(rect):
    """Park the cursor at the far corner of a covered rect, ONCE per
    spell (the first covered row claims it; later ones leave the
    saved point alone). False = the cursor could not be read; the
    spell proceeds uncuffed.

    PIN LAW, learned the hard way (owner's frozen morning blackout,
    Oct 15): this site used unpinned calls on the shared u32 handle -
    safe only while some other module happened to pin them first, and
    the import ORDER decided. An argumentless GetCursorPos read the
    stack as a bad POINT; the raise fired BETWEEN overlay-paint and
    the lift arms, so the black stuck and every retry re-raised. No
    unpin restorable defaults either - a failed verb returns False,
    it never escapes into the spell."""
    global _jail_saved
    if _jail_saved is not None:
        return True
    pt = wintypes.POINT()
    try:
        if not u32.GetCursorPos(ctypes.byref(pt)):
            return False
        _jail_saved = (pt.x, pt.y)
        x, y, w, h = rect
        u32.SetCursorPos(int(x + max(0, w - 1)), int(y + max(0, h - 1)))
    except Exception:
        log.warning("jail: cursor verb failed; the spell proceeds "
                    "uncuffed")
        _jail_saved = None
        return False
    log.debug("jail: cursor %s,%s -> %s,%s", pt.x, pt.y,
              x + max(0, w - 1), y + max(0, h - 1))
    return True


def unjail_cursor():
    """Hand the saved point back - no-op for a spell that never
    covered anything (the engine calls it on every lift)."""
    global _jail_saved
    if _jail_saved is None:
        return
    u32.SetCursorPos(_jail_saved[0], _jail_saved[1])
    log.debug("jail: cursor home to %s,%s", _jail_saved[0],
              _jail_saved[1])
    _jail_saved = None


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
                               SC_MONITORPOWER, MONITOR_OFF, SMTO_ABORTIFHUNG,
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
                             SC_MONITORPOWER, MONITOR_ON, SMTO_ABORTIFHUNG,
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


def idle_seconds():
    """The dimmer's input truth, public under the name the wave's
    packet speaks: GetLastInputInfo's seconds, inf when the source is
    deaf. One line over get_idle_time on purpose - the pin law is
    already paid there, and a feature must not re-wrap the same verb
    into a second lie."""
    return get_idle_time()


def hotkey_window():
    """The live pump's hwnd for dimmer's RegisterHotKey, or None: no
    watcher thread, no window, and the arm answers the card with the
    dated word instead of a silent lie. A message-only fallback
    window would NOT do here: hotkeys are per desktop, and the
    top-level shape is the one the watcher keeps."""
    return _ACTIVE[0]._hwnd if _ACTIVE else None


def request_hotkey(op, mods=0, vk=0):
    """The dimmer's hotkey door: (op, mods, vk) -> (ok, err). The
    registration is APPLIED on the pump thread against the pump's own
    window - the Oct-15 measuring: RegisterHotKey from a foreign
    thread answers ERROR_INVALID_HOTKEY_WINDOW (1408, same-thread
    (True, 123), cross-thread (False, 1408)), and an unregister from
    the wrong thread leaks the registration in the owning queue - so
    the note crosses, the verb does not (the _ear_req idiom, ridden
    not re-invented). No live watcher answers (False, 0) at once:
    the pump does not exist to hold a note."""
    w = _ACTIVE[0] if _ACTIVE else None
    if w is None or not w._hwnd:
        return False, 0
    return w.request_hotkey(op, mods, vk)


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

