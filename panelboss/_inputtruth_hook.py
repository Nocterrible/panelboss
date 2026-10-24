"""The pump's ears: one thread, one window, RAWINPUT - no hook
chain anywhere (owner ruling, Oct 20, closing the mode debate).

WHY RAW, NOT THE HOOK CHAIN - the repo's own measured law
(display.py:16-23, production since the away-lift wave): a
WH_KEYBOARD_LL/WH_MOUSE_LL pair costs every input event on the desk
a ~31 ms dispatch quantum, a 32 Hz mouse for the WHOLE desktop while
the chain lives; the hook gates everyone's input. WM_INPUT is the
same intelligence without the round-trip: a POSTED message for our
window only, no callback ever runs on anyone else's input path. The
pump re-arms that law, it does not renegotiate it.

THE SHAPE mirrors the proven away-lift block in display.py verbatim
where it counts: the (1,2)/(1,6) usage pairs, RIDEV_INPUTSINK, the
two-call GetRawInputData with the short-buffer pad, and display's
OWN ctypes prototypes for the window calls (every slot c_void_p -
the x64 truncation class that AV'd this module's first, unpinned
draft). A thread of its own owns the window class, the
registrations and the un-take (RIDEV_REMOVE through the same entry
point: this OS exports no UnregisterRawInputDevices - display
measured); GetMessageW sleeps until a packet or the detach's WM_QUIT
and wakes on the raw events themselves.

Injected input produces NO device packets here: the Oct-20 probe
(on this desk, after the macropad replug closed the case) showed
ZERO packets across 3.3 s of hands-off quiet - the honest desk
is silent, and the stamper's lie was its own stuck firmware, now
reset - and every SYNTHESIZED packet (SendInput kb make/break + a
200 px mouse move) arrived with hDevice == 0 while real devices
carry their HID handle. The pump therefore filters injection by
the kernel's own marker (null hDevice) AND by the TERMSRV_SHADOW
flag (the RDP-injected twin): an injected mouse with real deltas
would else stamp the clock like a hand. What the injected flag on
the hook structs was for, these two gates do without the chain.

WHY ONE FILE AND 309 LINES: the prototype block below and the
thread loop are ONE read - the x64 slot law that AV'd this
module's first draft binds both halves, and the pure logic was
already split at design time (inputtruth.py). Severing them
would make every future edit re-learn the pairing the hard way:
the split costs more than it saves here, which is the law's own
exemption, spoken out loud.
"""
import ctypes
import ctypes.wintypes as wt
import threading
import time

U32 = ctypes.windll.user32
K32 = ctypes.windll.kernel32

WM_INPUT = 0x00FF                     # winuser.h, as in display.py
WM_QUIT = 0x0012
RIDEV_REMOVE = 0x00000001
RIDEV_INPUTSINK = 0x00000100          # deliver while unfocused
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
RIM_TYPEKEYBOARD = 1
HWND_MESSAGE = ctypes.c_void_p(-3)

# The listener is a passive SINK: registered without RIDEV_EXCLUDE
# (the default), it shares every device with the legacy WM_* messages
# and with any other raw listener (display's own away ears), and it
# consumes nothing: the loop never calls DefRawInputProc, so there is
# nothing to export and nothing is swallowed. (RIDEV_EXCLUDE would
# ALSO pull the legacy queue off for our window - the one behaviour
# change a sink must not make.)

# winuser.h flag words live in inputtruth.py (the pure source); the
# ears import them so the parse and the filter read one ruler.
from .inputtruth import (MOUSE_MOVE_ABSOLUTE, MOUSE_VIRTUAL_DESKTOP,
                         RI_KEY_BREAK, RI_KEY_E0, RI_KEY_E1,
                         RI_KEY_TERMSRV_SHADOW)

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long,      # LRESULT (display's
                             ctypes.c_void_p,   # shape, line 240: a
                             ctypes.c_uint,     # 32-bit return at a
                             ctypes.c_ulonglong, ctypes.c_longlong)
                             # callback slot is read as far as it is
                             # declared - the high bits are never
                             # touched, and this matches the
                             # production twin exactly)


class WNDCLASSEXW(ctypes.Structure):     # not in wintypes; the SDK
    _fields_ = [("cbSize", wt.UINT), ("style", wt.UINT),  # layout, x64
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", ctypes.c_void_p),
                ("hIcon", ctypes.c_void_p),
                ("hCursor", ctypes.c_void_p),
                ("hInstanceBackground", ctypes.c_void_p),
                ("lpszMenuName", ctypes.c_wchar_p),
                ("lpszClassName", ctypes.c_wchar_p),
                ("hIconSm", ctypes.c_void_p)]


# display.py's PROVEN prototypes (247-251), copied not reinvented:
# every parameter slot c_void_p - 64-bit-wide parameters at 32-bit
# DWORD slots are harmless on the x64 convention, the inverse
# (default c_int restypes) is the truncation class that AV'd this
# module's first draft. The class is passed BY NAME (display's call
# shape at 475), not the atom.
U32.RegisterClassExW.restype = wt.USHORT
U32.RegisterClassExW.argtypes = [ctypes.c_void_p]
U32.CreateWindowExW.restype = ctypes.c_void_p
U32.CreateWindowExW.argtypes = [ctypes.c_void_p,        # dwExStyle
                                ctypes.c_wchar_p,       # class name
                                ctypes.c_wchar_p        # title
                                ] + [ctypes.c_void_p] * 9
U32.GetMessageW.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                            wt.UINT, wt.UINT]
U32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, ctypes.c_ulonglong,
                                   ctypes.c_longlong]
K32.GetModuleHandleW.restype = ctypes.c_void_p   # the truncated-
#                                                 # HINSTANCE AV, the
#                                                 # probe's first lesson
K32.GetLastError.restype = wt.UINT
U32.DestroyWindow.argtypes = [ctypes.c_void_p]
U32.DispatchMessageW.argtypes = [ctypes.c_void_p]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wt.UINT), ("dwSize", wt.UINT),
                ("hDevice", ctypes.c_void_p),
                ("wParam", ctypes.c_ulonglong)]


class RAWMOUSE(ctypes.Structure):
    class _U(ctypes.Union):
        class _S(ctypes.Structure):
            _fields_ = [("ulButtons", wt.USHORT),
                        ("buttonFlags", wt.USHORT),
                        ("buttonData", wt.ULONG)]
        _fields_ = [("buttons", _S),
                    ("rawButtons", wt.USHORT),
                    ("rawButtonData", wt.ULONG)]
    # flags(2) + pad(2) + the 8-byte union blob (the real 4-byte
    # union beside its 4-byte ulRawButtons - display's offset-proven
    # shape) puts lastX/lastY at 12/16, the winuser.h offsets
    _fields_ = [("flags", wt.USHORT), ("_pad", wt.USHORT), ("u", _U),
                ("lastX", wt.LONG), ("lastY", wt.LONG)]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [("makeCode", wt.USHORT), ("flags", wt.USHORT),
                ("reserved", wt.USHORT), ("vkey", wt.USHORT),
                ("message", wt.UINT), ("extraInfo", wt.UINT)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wt.USHORT), ("usUsage", wt.USHORT),
                ("flags", wt.UINT), ("hwndTarget", ctypes.c_void_p)]


U32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE),
                                        wt.UINT, wt.UINT]
U32.RegisterRawInputDevices.restype = wt.BOOL
U32.GetRawInputData.argtypes = [ctypes.c_void_p, wt.UINT, ctypes.c_void_p,
                                ctypes.POINTER(wt.UINT), wt.UINT]
U32.GetRawInputData.restype = wt.UINT


class RawEars:
    """The live pair (generic mouse + keyboard - the away-lift block's
    own usage pairs). attach() raises OSError (with the Win32 word)
    when the desk refuses the class, the window, or the registration;
    alive() reads the thread."""

    _CLS = "PanelBossPumpEar"

    def __init__(self, pump):
        self._pump = pump
        self._now = time.monotonic
        self._hwnd = None
        self._fail = [""]
        self._alive = False
        self._ready = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True,
                                   name="inputtruth")
        self._tid = None
        self._t.start()
        if not self._ready.wait(2.0):
            raise OSError("the raw pump thread never reported")
        if self._fail[0]:
            raise OSError(self._fail[0])
        self._alive = True

    def _parse(self, handle):
        """One WM_INPUT, display's proven two-call dance; a refusal
        or a short buffer drops the packet (a lost report ages the
        clock a little - the loop never stops here)."""
        if not handle:
            return
        size = wt.UINT(0)
        if U32.GetRawInputData(handle, RID_INPUT, None,
                               ctypes.byref(size),
                               ctypes.sizeof(RAWINPUTHEADER)) != 0 \
                or not size.value:
            return
        buf = (ctypes.c_char * size.value)()
        if U32.GetRawInputData(handle, RID_INPUT, buf, ctypes.byref(size),
                               ctypes.sizeof(RAWINPUTHEADER)) != size.value:
            return
        raw = bytes(buf) + b"\0" * 64          # short buffers read clean
        head = RAWINPUTHEADER.from_buffer_copy(raw)
        base = ctypes.sizeof(RAWINPUTHEADER)
        # winuser.h documents it and the Oct-20 probe confirmed it on
        # this desk: a packet injected via SendInput/journal carries
        # NULL hDevice. Device traffic is handles-only - the wake
        # exemption's "any packet" counts THESE, and a remote hand's
        # mouse never stamps the pump (its keystrokes reach the
        # screens through the exemption, honest for the OFF-PHASE
        # wake only, exactly as the owner's rule reads).
        if not head.hDevice:
            return
        if head.dwType == RIM_TYPEKEYBOARD:
            kb = RAWKEYBOARD.from_buffer_copy(raw, base)
            if not (kb.flags & RI_KEY_TERMSRV_SHADOW):
                self._pump.key(kb.makeCode, kb.flags, self._now())
        elif head.dwType == RIM_TYPEMOUSE:
            mo = RAWMOUSE.from_buffer_copy(raw, base)
            self._pump.mouse(mo.lastX, mo.lastY, mo.flags, self._now())
        # else: a joystick hopper speaks - the pump is for hands

    def _register(self):
        """The (1,2)/(1,6) INPUTSINK pairs on this thread's
        message-only hwnd. Idempotent: re-issuing the same pairs to
        the same hwnd is the documented re-arm - display's away-ear
        RIDEV_REMOVE is process-wide (it addresses the pair, not one
        window) and silences these same pairs while its own thread
        keeps pumping. The call shape stays argtypes-neutral (the
        Oct-21 cross-module disease): display clears the shared
        binding at its own calls, and a plain array converts under
        both its cleared handle and this module's own binding."""
        arr = (RAWINPUTDEVICE * 2)()
        for row, (page, usage) in zip(arr, ((1, 2), (1, 6))):
            row.usUsagePage = page
            row.usUsage = usage
            row.flags = RIDEV_INPUTSINK
            row.hwndTarget = self._hwnd
        if U32.RegisterRawInputDevices(arr, 2,
                                       ctypes.sizeof(RAWINPUTDEVICE)):
            return True
        self._fail[0] = ("RegisterRawInputDevices refused: Win32 "
                         "error %d" % K32.GetLastError())
        U32.DestroyWindow(self._hwnd)
        self._hwnd = None
        return False

    def _run(self):
        msg = wt.MSG()
        self._tid = K32.GetCurrentThreadId()
        U32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 0)   # create the
        #                                                 # queue first
        #                                                 # (display's
        #                                                 # order-of-
        #                                                 # operations)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        # the class proc is the OS's OWN DefWindowProcW, addressed
        # directly (display's Python proc filters its broadcast
        # stream; the ear has one message that matters and it eats
        # that inline). A NULL-proc class is refused by CreateWindow,
        # and a from_address'd proc is a READ of the function's first
        # bytes as a pointer - the AV that taught both, the Oct-20
        # probe: cast a c_void_p of the address is the honest idiom.
        wc.lpfnWndProc = ctypes.cast(
            ctypes.c_void_p(
                ctypes.cast(U32.DefWindowProcW,
                            ctypes.c_void_p).value),
            WNDPROC)
        wc.lpszClassName = self._CLS
        if not U32.RegisterClassExW(ctypes.byref(wc)):
            if K32.GetLastError() != 1407:      # already registered:
                self._fail[0] = ("RegisterClassExW refused: Win32 "
                                 "error %d" % K32.GetLastError())
                self._ready.set()
                return
        self._hwnd = U32.CreateWindowExW(0, self._CLS, None, 0,
                                         0, 0, 0, 0,
                                         HWND_MESSAGE, None,
                                         ctypes.c_void_p(0), None)
        if not self._hwnd:
            self._fail[0] = ("CreateWindowExW(HWND_MESSAGE) refused: "
                             "Win32 error %d" % K32.GetLastError())
            self._ready.set()
            return
        if not self._register():
            self._ready.set()
            return
        self._ready.set()
        # GetMessageW sleeps until a packet or the detach's WM_QUIT:
        # WM_INPUT is POSTED for this window, so raw traffic itself
        # wakes the wait (display's MsgWait floor bounds ITS periodic
        # duties - the ear owns none, and a sleeping pump is the
        # power-cheapest shape this desk will ever see)
        while U32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_INPUT:
                self._parse(msg.lParam)
            elif msg.message == WM_QUIT:
                break
            else:
                U32.DispatchMessageW(ctypes.byref(msg))
        arr = (RAWINPUTDEVICE * 2)()
        for row, (page, usage) in zip(arr, ((1, 2), (1, 6))):
            row.usUsagePage = page
            row.usUsage = usage
            row.flags = RIDEV_REMOVE
            row.hwndTarget = 0
        U32.RegisterRawInputDevices(arr, 2, ctypes.sizeof(RAWINPUTDEVICE))
        # the un-take through the same entry point (display measured
        # the missing export); a refusal at teardown is the OS letting
        # go with the window anyway
        if self._hwnd:
            U32.DestroyWindow(self._hwnd)
            self._hwnd = None
        self._alive = False

    def alive(self):
        return self._alive and self._t.is_alive()

    def detach(self):
        if self._tid:
            U32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
        self._t.join(2.0)
        self._alive = False


def attach(pump):
    """The seam inputtruth.install() calls: live raw ears or an
    OSError carrying the desk's refusal."""
    return RawEars(pump)


def re_register():
    """The re-arm the away ear owes us: its RIDEV_REMOVE is
    process-wide (hwndTarget must be NULL - it cannot address one
    window), so it silences our identical (1,2)/(1,6) pairs while the
    pump's thread keeps living in GetMessageW and the corpse-detection
    never sees it. Re-issuing RIDEV_INPUTSINK to the same hwnd is the
    documented re-arm (the argtypes-neutral call shape above). No pump
    up (the ears object None / not built) - no-op, False."""
    from . import inputtruth
    ear = inputtruth._ear
    if ear is None:
        return False
    return bool(ear._register())
