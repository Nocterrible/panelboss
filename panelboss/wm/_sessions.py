"""The session-transport side: is THIS session remote (an RDP / remote
desktop canvas)? The away engine and the off-legs stand down for a
desk that answers remote - a fake canvas must never be asked to power
itself (the DDC door LIES for a virtual row: reachable=True, nphys=1,
measured from inside the session).

Belt religion, same as the rest of wm: restype/argtypes pinned at
import, every refusal returns None, never raises - a session query the
OS declines degrades to "unknown", not an exception through the off
transition. The measured trap (the one that fooled a past
investigation): WTSQuerySessionInformationW's BOOL answer lives in
the OUTPUT BUFFER, not the return value - the return only says the
call worked; the buffer read is what matched `query session`.
"""

import ctypes
from ctypes import wintypes

# wtsapi32's own handle: ctypes caches the windll entry, so this is
# the SAME object display.py pins the WTSRegister pair on (no
# prototype fights - the two parts pin disjoint functions).
wts = ctypes.windll.wtsapi32

WTS_CURRENT_SESSION = 0xFFFFFFFF
WTSIsRemoteSession = 29            # WTS_INFO_CLASS ordinal, wtsapi32.h
WTSConnectState = 1                # the belt helper's class (wtsapi32.h)
WTS_LISTENER_ID = 0x10000          # 65536: the listener id to skip

# NOTE, measured: WTSGetActiveConsoleSessionId lives on kernel32 (k32),
# NOT wtsapi32 - if a future consumer asks for the console id, it goes
# to k32 (panelboss/wm/_winapi.py owns that handle).


class WTS_SESSION_INFOW(ctypes.Structure):   # for WTSEnumerateSessionsW
    _fields_ = [("SessionId", wintypes.DWORD),
                ("pWinStationName", wintypes.LPWSTR),
                ("State", wintypes.DWORD)]


# the pins (belt): the buffer slot is c_void_p on both, the class and
# the session slots are DWORD - the 64-bit buffer survives the way in
wts.WTSQuerySessionInformationW.argtypes = [ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
wts.WTSQuerySessionInformationW.restype = wintypes.BOOL
wts.WTSFreeMemory.argtypes = [ctypes.c_void_p]
wts.WTSFreeMemory.restype = None
wts.WTSEnumerateSessionsW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
        ctypes.c_uint,
        ctypes.POINTER(ctypes.POINTER(WTS_SESSION_INFOW)),
        ctypes.POINTER(wintypes.DWORD)]
wts.WTSEnumerateSessionsW.restype = wintypes.BOOL


def _query_current_session(cls):
    """One WTSQuerySessionInformationW for the CURRENT session.
    Returns the raw bytes the call wrote, or None when refused - the
    caller reads its own answer off the buffer (the BOOL-class trap),
    never off the return value."""
    buf = ctypes.c_void_p()
    cb = wintypes.DWORD()
    try:
        ok = wts.WTSQuerySessionInformationW(None, WTS_CURRENT_SESSION,
                                             cls, ctypes.byref(buf),
                                             ctypes.byref(cb))
    except Exception:
        return None
    if not ok or not buf.value:
        return None
    try:
        return bytes(ctypes.string_at(buf.value, int(cb.value or 1)))
    except Exception:
        return None


def session_is_remote():
    """Is the current session remote? True / False / None (the query
    refused - treat as unknown, never raise)."""
    data = _query_current_session(WTSIsRemoteSession)
    if data is None:
        return None
    try:
        return bool(int.from_bytes(data[:4], "little"))
    except Exception:
        return None


def _is_remote_by_id(sid):
    """Per-id twin of session_is_remote for the enumeration pass."""
    buf = ctypes.c_void_p()
    cb = wintypes.DWORD()
    try:
        ok = wts.WTSQuerySessionInformationW(None, sid, WTSIsRemoteSession,
                                             ctypes.byref(buf),
                                             ctypes.byref(cb))
    except Exception:
        return None
    if not ok or not buf.value:
        return None
    try:
        return bool(int.from_bytes(
            bytes(ctypes.string_at(buf.value, int(cb.value or 1)))[:4],
            "little"))
    except Exception:
        return None


def remote_session_ids():
    """The set of every ACTIVE session id that is a remote session.
    The listener id (65536) is skipped; a refused per-id query is
    EXCLUDED (unknown is not remote). The array is WTSFreeMemory'd
    on every path. An enumeration refusal answers an empty set."""
    out = set()
    arr = ctypes.POINTER(WTS_SESSION_INFOW)()
    count = wintypes.DWORD()
    try:
        if not wts.WTSEnumerateSessionsW(None, 0, 1, ctypes.byref(arr),
                                         ctypes.byref(count)):
            return out
        for i in range(int(count.value)):
            sid = arr[i].SessionId
            if sid == WTS_LISTENER_ID:
                continue
            if _is_remote_by_id(sid) is True:
                out.add(sid)
    except Exception:
        pass                       # belt: a dead query, not a dead desk
    finally:
        try:
            wts.WTSFreeMemory(arr)
        except Exception:
            pass
    return out


def session_connected():
    """Belt helper, same query family: does the current session
    answer a connect-state query at all? Any answer is fine - the
    point is that the door is open, not which state it names.
    Refusal answers None, never raises."""
    return _query_current_session(WTSConnectState) is not None
