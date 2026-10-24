"""Window introspection: one hwnd in, a dict of facts out, and
the pure `wanted` decision of what we dare to move. Formerly wm.py
lines 231-346."""

import ctypes
from ctypes import wintypes

from ._winapi import (DWMWA_CLOAKED, FURNITURE_PREFIX, GA_ROOT,
                      GWL_EXSTYLE, GWL_STYLE,
                      PROCESS_QUERY_LIMITED_INFORMATION, RECT,
                      SMTO_ABORTIFHUNG, SMTO_TIMEOUT_MS, WM_GETTEXT,
                      WS_CHILD, WS_EX_TOOLWINDOW, WS_EX_TRANSPARENT,
                      WNDENUMPROC, byref, dwm, k32, sizeof, u32)


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
    """Title, with a deadline. A FOREIGN window answers GetWindowText
    from the manager's cached copy and cannot block (Raymond Chen's
    rule, and the reason this is surgical: only own-process windows
    ever send). OUR windows - the hider strips ride the hider-paint
    thread - answer with a SENT message, and a send to a thread that
    is not pumping waits forever (the capture freeze, measured
    Oct-16). Own-process windows therefore ride SendMessageTimeout:
    1.5 s, then an honest empty title."""
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(hwnd, byref(pid))
    if pid.value != k32.GetCurrentProcessId():
        n = u32.GetWindowTextLengthW(hwnd)     # cached read, cannot block
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(min(n, 200) + 1)
        u32.GetWindowTextW(hwnd, buf, len(buf))
        return buf.value
    buf = ctypes.create_unicode_buffer(201)
    if u32.SendMessageTimeoutW(hwnd, WM_GETTEXT, 200, byref(buf),
                               SMTO_ABORTIFHUNG, SMTO_TIMEOUT_MS, None):
        return buf.value
    return ""                                  # deaf thread: honest empty


def _proc_info(hwnd):
    """(name, full exe path, owner pid) - one OpenProcess, three
    answers, zero extra syscalls beyond the window's own pid read.
    The name is the identity a profile matches on (hwnds die, pids
    are recycled, the name survives relaunches); the full path is
    what a pin can re-run when the app is not open any more; the
    pid is the thread-through of the GetWindowThreadProcessId the
    path already needs (dossier C: the rescue skips OUR rows with
    it, no second syscall). A window dying mid-walk answers pid 0/
    None: never our own pid, so the rescue treats it as foreign -
    the conservative arm (a dead window's move is a harmless
    no-op)."""
    try:
        pid = wintypes.DWORD()
        if not u32.GetWindowThreadProcessId(hwnd, byref(pid)):
            return "", "", 0
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False,
                            pid.value)
        if not h:
            return "", "", pid.value
        try:
            buf = ctypes.create_unicode_buffer(4096)
            n = wintypes.DWORD(len(buf))
            if not k32.QueryFullProcessImageNameW(h, 0, buf, byref(n)):
                return "", "", pid.value
            full = buf.value
            return full.split("\\")[-1].lower(), full, pid.value
        finally:
            k32.CloseHandle(h)
    except Exception:
        return "", "", None              # a window dying mid-walk;
                                         # a profile entry with no
                                         # proc is simply unmatched


def proc_name(hwnd):
    name, _, _ = _proc_info(hwnd)
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
    proc, exe, pid = _proc_info(hwnd)
    return {
        "hwnd": hwnd,
        "rect": true_rect(hwnd),
        "title": win_title(hwnd),
        "proc": proc,
        "exe": exe,
        "pid": pid,                       # owner pid (dossier C):
                                          # the rescue skips its own
                                          # rows with it
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
