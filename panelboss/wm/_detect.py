"""Detection probes: the foreground fact dict and the xinput module
probe - the self-contained appended block, psapi pins and all.
Formerly wm.py lines 1068-1189."""

import ctypes
from ctypes import wintypes

from ._inspect import _cloaked, _proc_info, true_rect, win_title
from ._monitors import monitor_for
from ._winapi import (PROCESS_QUERY_INFORMATION, PROCESS_VM_READ,
                      byref, k32, u32)


# ---------------------------------------------------------------------
# Detection probes - a self-contained appended block (removing it
# leaves no stale argtypes behind: the psapi snapshot bindings pin
# locally, nothing else in the package uses those entry points).
#
# HONEST WARNING: has_xinput() queries the target's module table
# (psapi EnumProcessModulesEx + GetModuleBaseNameW). Querying an
# anti-cheat-protected process can BLOCK for up to seconds (the
# kernel waits on the target's module table). Callers MUST invoke it
# only on a foreground-pid CHANGE, never in a tight loop or per
# camera frame. The spec's primary path (GetModuleHandleExW with an
# hProcess) does not exist - the API is current-process only - so
# this warning applies to EVERY call.
#
# WHY PSAPI AND NOT TOOLHELP: the spec's toolhelp route
# (CreateToolhelp32Snapshot + Module32FirstW/NextW) was measured
# broken on this machine - its module snapshot of a live child that
# had just loaded xinput1_3.dll returned only 7 of the ~30+ modules
# and xinput never appeared in them. The psapi self-test returned
# the full list (33 modules). psapi is the route proven to see xinput.
# ---------------------------------------------------------------------

u32.GetForegroundWindow.restype = wintypes.HWND


def foreground():
    """The foreground window as one fact dict, or None:

        {"hwnd": int, "pid": int, "proc": "game.exe", "exe": str,
         "title": str, "rect": [x, y, w, h], "monitor": "short-id"}

    Fail-open: any missing piece -> None; a partial dict is never a
    useful answer, so the whole thing falls over. "exe", "title" and
    "monitor" may be "" on the way out.
    """
    try:
        hwnd = u32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        if not u32.GetWindowThreadProcessId(hwnd, byref(pid)):
            return None
        if _cloaked(hwnd):
            return None             # a UWP suspension lie: the hwnd is
                                    # alive but nothing is visible
        proc, exe = _proc_info(hwnd)
        if not proc:
            return None
        title = win_title(hwnd)
        rect = true_rect(hwnd)
        if rect is None:
            return None
        m = monitor_for(rect)
        return {"hwnd": int(hwnd), "pid": int(pid.value),
                "proc": proc, "exe": exe, "title": title,
                "rect": list(rect),
                "monitor": m["short"] if m else ""}
    except Exception:
        return None                 # the window died between calls


def has_xinput(pid):
    """True if the process at `pid` has any xinput module loaded
    (xinput1_1..1_4.dll, xinput9*.dll - substring "xinput", case-
    insensitive). NO caching: the answer is only valid as of now;
    callers cache.

    Module table via psapi (EnumProcessModulesEx + GetModuleBaseNameW),
    which MEASURED works from this process family where the toolhelp
    route answers ZERO modules for every pid (bisected in child
    processes: self/xinput-child/explorer all 0 via toolhelp, 21/32/
    397 via psapi) - a toolhelp walk here is a guaranteed miss, not a
    slower path. ANY error - refused handle, dead pid, protected
    process - returns False.

    HONEST WARNING: querying an anti-cheat-protected process can
    block for seconds (the kernel waits on the target's module
    table). Call only on a foreground-pid CHANGE, never in a tight
    loop.
    """
    try:
        # Local pinning: self-contained block (shared windll cache).
        k32.OpenProcess.restype = ctypes.c_void_p
        k32.OpenProcess.argtypes = [wintypes.DWORD, ctypes.c_bool,
                                    wintypes.DWORD]
        h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION,
                            False, int(pid))
        if not h:
            return False
        try:
            ps = ctypes.WinDLL("psapi.dll")
            ps.EnumProcessModulesEx.restype = ctypes.c_bool
            ps.EnumProcessModulesEx.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                wintypes.DWORD]
            need = wintypes.DWORD()
            ps.EnumProcessModulesEx(h, None, 0, ctypes.byref(need),
                                    0x03)                   # ALL
            cnt = max(1, need.value //
                      ctypes.sizeof(ctypes.c_void_p))
            arr = (ctypes.c_void_p * cnt)()
            got = wintypes.DWORD()
            if not ps.EnumProcessModulesEx(h, arr,
                                           ctypes.sizeof(arr),
                                           ctypes.byref(got), 0x03):
                return False
            name = ctypes.create_unicode_buffer(260)
            ps.GetModuleBaseNameW.restype = wintypes.UINT
            ps.GetModuleBaseNameW.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, wintypes.LPWSTR,
                wintypes.UINT]
            for i in range(got.value //
                           ctypes.sizeof(ctypes.c_void_p)):
                if ps.GetModuleBaseNameW(h, arr[i], name, 260) and \
                        "xinput" in name.value.lower():
                    return True
            return False
        finally:
            k32.CloseHandle(h)
    except Exception:
        return False                # fail-open: unknown = no xinput
