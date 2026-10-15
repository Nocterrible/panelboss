"""Which processes are AUDIBLE right now - raw-vtable WASAPI, no COM
library, no dependency beyond ole32. SLOTS ARE IDL ORDER, counted from
the SDK headers shipped on this box (the docs pages list methods
alphabetically and lie about vtable order - this file's reason for
existence as a pinned, commented constant set):

    IUnknown:                       QueryInterface 0, AddRef 1, Release 2
    IMMDeviceEnumerator:            GetDefaultAudioEndpoint 4
    IMMDevice:                      Activate 3
    IAudioClient:                   GetService 14         (Initialize=3,
                                     GetBufferSize=4, GetStreamLatency=5,
                                     GetCurrentPadding=6,
                                     IsFormatSupported=7, GetMixFormat=8,
                                     GetDevicePeriod=9, Start=10, Stop=11,
                                     Reset=12, SetEventHandle=13)
    IAudioSessionManager2:          GetSessionEnumerator 5 (base
                                     IAudioSessionManager owns 3/4)
    IAudioSessionEnumerator:        GetCount 3, GetSession 4 (there is
                                     no Next - the Oct-14 "Next 3" was
                                     the COM enum idiom imagined onto
                                     an index-based interface)
    IAudioSessionControl2:          GetState 3            (base control's
                                     first method)
                                     GetProcessId 14       (control owns
                                     3..11: GetSessionIdentifier 12,
                                     GetSessionInstanceIdentifier 13)

STATE ENUM (AudioSessionTypes.h): {0 Inactive, 1 Active, 2 Expired}.
MTA (COINIT_MULTITHREADED) required.

Oct-15 correction pass (the walk died at its first vtable call and the
except-handler's empty set hid every one of these; each fix verified
against the live device): the Oct-14 table put GetService at 4, Get-
Session-Enumerator at 4, GetProcessId at 16, and a "Next" at 3; the
IAudioClient IID's tail was transcribed B0A2-C6B7B8AA441B where the
SDK (and the endpoint's own activation table) say B178-C2F568A703B2 -
the device answers E_NOINTERFACE to the wrong tail through the ctypes
path AND through a .NET RCW, so the tail was the bug, not the device;
the IAudioSessionManager2 IID was 77AA1422-1635-4596-9FC0-
1D979573DA2A where the SDK says 77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F;
the state enum was recorded {0 Active, 1 Inactive} - inverted; and the
Activate(IAudioClient)->GetService(IAudioSessionManager2) hop was
dropped from the walk: this box's endpoints answer GetService(SessMgr2)
E_NOINTERFACE (measured: all three candidate IIDs and a direct QI too,
while slot 14's neighbors speak - Reset answers NOT_INITIALIZED), so
the walk takes the Microsoft volume-mixer sample's own route,
Activate(IAudioSessionManager2) straight off the device: S_OK on 91 of
91 render endpoints.

THE CALLING LAW (the actual deref bug, Oct-15): two plain pointer reads
and a constructor/call split. WINFUNCTYPE(...) returns a CONSTRUCTOR
taking exactly one argument - the function address; the real arguments
belong to the INSTANCE it returns, so the Oct-14 fn(cast(addr,
c_void_p), *args) raised TypeError 'takes exactly 1 argument (4 given)'
before any COM call - the arity of the CONSTRUCTOR, misread as
Release's signature. And POINTER(POINTER(c_void_p))[0][slot]'s double-
index answers a garbage int for a vtable (measured: the real slot-2
word 0x7ffd... vs 0x30EC834857415641), which is the off-by-one the
Oct-14 probe was chasing: the table index was never wrong, the ctypes
pointer-of-pointer read was. Read the vtable with two bare c_void_p
loads instead, and pass `this` explicitly as argtypes[0] - ctypes does
not thread the COM self-pointer for you.

Every failure path answers the EMPTY SET: 'cannot tell' is always safe
for the dimmer (nothing gets excused, everything still dims), and a
sound-exempt app that the OS momentarily refuses to enumerate is a
fair price for a module that never raises into a tick.
"""

import ctypes
from ctypes import POINTER, WINFUNCTYPE, byref, c_void_p
from ctypes.wintypes import DWORD, LONG, ULONG

HRESULT = LONG        # 3.10 wintypes predates both GUID and HRESULT
INT = ctypes.c_int    # GetCount/GetSession speak int, not DWORD


class GUID(ctypes.Structure):          # 3.10's wintypes has none
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, d1, d2, d3, tail):
        super().__init__()
        self.Data1, self.Data2, self.Data3 = d1, d2, d3
        self.Data4 = (ctypes.c_ubyte * 8)(*tail)

_ole = ctypes.WinDLL("ole32", use_last_error=True)
_ole.CoInitializeEx.restype = HRESULT
_ole.CoInitializeEx.argtypes = [c_void_p, DWORD]
_ole.CoCreateInstance.restype = HRESULT
_ole.CoCreateInstance.argtypes = [POINTER(GUID), c_void_p, DWORD,
                                  POINTER(GUID), POINTER(c_void_p)]

_CLSID_MMDEV = GUID(0xBCDE0395, 0xE52F, 0x467C,
                    (0x8E, 0x3D, 0xC4, 0x57, 0x92, 0x91, 0x69,
                     0x2E))      # BCDE0395-E52F-467C-8E3D-C4579291692E
                                 # (NAudio/cscore/ToggleSysFx agree;
                                 # the Oct-14 note's -B749 tail was
                                 # transcription, this is the value -
                                 # verified live, alarm audible)
_IID_IMMDEV = GUID(0xA95664D2, 0x9614, 0x4F35,
                   (0xA7, 0x46, 0xDE, 0x8D, 0xB6, 0x36, 0x17, 0xE6))
_IID_AUDIOCLIENT = GUID(0x1CB9AD4C, 0xDBFA, 0x4C32,
                        (0xB1, 0x78, 0xC2, 0xF5, 0x68, 0xA7, 0x03,
                         0xB2))  # the SDK's tail; the Oct-14 note's
                                 # -B0A2-C6B7B8AA441B is what the
                                 # endpoint's E_NOINTERFACE was
                                 # confessing (Audioclient.h:246).
                                 # The walk no longer activates it -
                                 # pinned here so the table above is
                                 # checkable against the header.
_IID_SESSMGR2 = GUID(0x77AA99A0, 0x1BD6, 0x484F,
                     (0x8B, 0xC7, 0x2C, 0x65, 0x4C, 0x9A, 0x9B,
                      0x6F))     # audiopolicy.h:1155 - the Oct-14
                                 # 77AA1422 tail answers E_NOINTERFACE

_CLSCTX_ALL = 0x17
_S_OK = 0
_STATE_ACTIVE = 1   # AudioSessionTypes.h: Inactive=0, Active=1,
                    # Expired=2 - the Oct-14 note's {0 Active} inverted
                    # the first two

_PTR = 8            # pointer width on this box (x64 python)


def _rel(obj):
    # IUnknown::Release, slot 2. There is no "ctypes table header" and
    # never was: the Oct-14 slot+1 dodge was the double-index garbage
    # below wearing a hat.
    if obj.value:
        _call(obj, 2, (c_void_p,), ())


def _call(obj, slot, argtypes, args, res=HRESULT):
    # THE LAW, each clause measured Oct-15: (1) EXPLICIT argtypes -
    # byref() carries no from_param. (2) The deref is two bare
    # c_void_p loads: word 0 of the object is the vtable, word `slot`
    # of the table is the function. (3) argtypes[0] is the this slot
    # and is NOT repeated in args - _call threads `obj` itself, the
    # C macro's This argument; ctypes never adds it for you. (4) The
    # WINFUNCTYPE constructor takes ONLY the address; the arguments
    # go to the instance it returns.
    vtbl = c_void_p.from_address(obj.value).value
    return WINFUNCTYPE(res, *argtypes)(
        c_void_p.from_address(vtbl + _PTR * slot).value)(obj, *args)


def sounding_pids():
    """PIDs with an ACTIVE render session right now. The state check
    is the whole feature: a video that paused leaves the ACTIVE set,
    and the caller's settle window keeps it exempt for a few honest
    seconds."""
    try:
        _ole.CoInitializeEx(None, 0x0)      # re-init on an inited
                                            # thread is a documented
                                            # no-op
        en = c_void_p()
        if _ole.CoCreateInstance(byref(_CLSID_MMDEV), None,
                                _CLSCTX_ALL, byref(_IID_IMMDEV),
                                byref(en)) != _S_OK or not en.value:
            return set()
        dev = c_void_p()
        if _call(en, 4, (c_void_p, DWORD, DWORD, POINTER(c_void_p)),
                 (DWORD(0), DWORD(0), byref(dev))) != _S_OK \
                or not dev.value:
            _rel(en)
            return set()
        mgr = c_void_p()                    # the volume-mixer route:
        if _call(dev, 3,                    # Activate the manager off
                 (c_void_p, POINTER(GUID),   # the device directly -
                  DWORD, c_void_p,           # GetService(SessMgr2) is
                  POINTER(c_void_p)),        # E_NOINTERFACE on this
                 (byref(_IID_SESSMGR2),      # box (see docstring)
                  _CLSCTX_ALL, None,
                  byref(mgr))) != _S_OK or not mgr.value:
            _rel(dev)
            _rel(en)
            return set()
        se = c_void_p()                     # ...Manager2::GetSession-
        if _call(mgr, 5, (c_void_p, POINTER(c_void_p)),   # Enumerator
                 (byref(se),)) != _S_OK or not se.value:
            _rel(mgr)
            _rel(dev)
            _rel(en)
            return set()
        count = INT()
        pids = set()
        if _call(se, 3, (c_void_p, POINTER(INT)),        # GetCount
                 (byref(count),)) == _S_OK:
            for i in range(max(0, count.value)):    # GetSession is
                s = c_void_p()                      # index-based; no
                if _call(se, 4,                     # Next on this
                         (c_void_p, INT,            # enumerator
                          POINTER(c_void_p)),
                         (i, byref(s))) != _S_OK or not s.value:
                    continue
                state = DWORD()
                if _call(s, 3, (c_void_p, POINTER(DWORD)),
                         (byref(state),)) == _S_OK \
                        and state.value == _STATE_ACTIVE:
                    pid = DWORD()
                    rc = _call(s, 14, (c_void_p, POINTER(DWORD)),
                               (byref(pid),))
                    if rc in (_S_OK, 0x000000D):    # the docs' S_ for
                        pids.add(pid.value)         # a multi-process
                                                      # session
                _rel(s)
        _rel(se)
        _rel(mgr)
        _rel(dev)
        _rel(en)
        return pids
    except Exception:
        return set()
