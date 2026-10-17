"""webrect: measure a browser window's web viewport in PHYSICAL desktop px.

The page can measure the video's SIZE (getBoundingClientRect) but NOT its
SCREEN POSITION - the browser chrome (the GX sidebar's ~42 px, the
toolbar+tabs' ~109 px) sits between the window's outer rect and the web
content, and the page's window.screenX/screenY reports the WINDOW rect
(measured (0,0) on a maximized window whose content actually starts at
(42,109)). The ONE OS-side truth is the browser's
Chrome_RenderWidgetHostHWND child: its rectangle IS the web viewport, and
its size equals the page's innerWidth x innerHeight scaled by dpr. This
module - the OS-adjacent half of the native host, stdlib+ctypes only -
measures that child rect on every veil push and returns it as
[left, top, width, height] in physical px, so the app's fold can bind the
page's exact size to the exact screen position.

SIZE LAW (~120): ONE seam - find the family's browser window, read its
render-widget child rect, validate against the page's own view size.
Pure logic, no file writes, no transport; panelboss_host.py owns those.
"""
import ctypes
import os
from ctypes import wintypes

# FAMILY -> the browser's process image name (we filter EnumWindows
# candidates to the family's own exe so a chat/Electron window that also
# happens to be a Chrome_WidgetWin_1 cannot impersonate).
_FAMILY_EXE = {"opera_gx": "opera.exe", "edge": "msedge.exe",
               "chrome": "chrome.exe"}

_u32 = None
_k32 = None


def _handles():
    global _u32, _k32
    if _u32 is None:
        _u32 = ctypes.windll.user32
        _k32 = ctypes.windll.kernel32
        # be per-monitor-DPI-aware so GetWindowRect and EnumChildWindows
        # return true PHYSICAL px, the same space the app paints its
        # overlay windows in (EnumDisplaySettings is physical). A scaled
        # desk must not shift the ring by the scale factor's inverse.
        try:
            # PER_MONITOR_AWARE_V2 == -4
            _u32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            pass                # pre-1703 Windows: the desk is 100%


def _exe_of(pid):
    """The process image name (lowercased basename) for a pid, or "" -
    the family filter's only job. OpenProcess+QueryFullProcessImageName
    (the frozen-exe-safe route, no WMIC)."""
    _handles()
    h = _k32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if not _k32.QueryFullProcessImageNameW(h, 0, buf,
                                               ctypes.byref(size)):
            return ""
        return os.path.basename(buf.value).lower()
    finally:
        _k32.CloseHandle(h)


def _render_widget(hwnd):
    """The LARGEST Chrome_RenderWidgetHostHWND descendant of a top
    window, as its physical rect (left, top, right, bottom), or None.
    This child IS the web viewport: its size is the page's innerWidth x
    innerHeight * dpr, its top-left the viewport's screen origin."""
    _handles()
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _lp):
        cls = ctypes.create_unicode_buffer(256)
        _u32.GetClassNameW(h, cls, 255)
        if cls.value == "Chrome_RenderWidgetHostHWND":
            r = wintypes.RECT()
            if _u32.GetWindowRect(h, ctypes.byref(r)):
                found.append((r.left, r.top, r.right, r.bottom))
        return 1
    _u32.EnumChildWindows(hwnd, cb, 0)
    best, best_area = None, -1
    for r in found:
        a = (r[2] - r[0]) * (r[3] - r[1])
        if a > best_area:
            best_area, best = a, r
    return best


def webrect(payload):
    """The browser viewport's physical rect [left, top, w, h], or None.
    Selector: enumerate visible top windows whose pid's exe is the
    family's, take each one's render-widget child, and pick the window
    whose render-widget SIZE matches the page's reported view size
    (view x dpr, within tolerance) - ties broken by proximity of the
    window's outer rect to the extension's own bounds report. Any
    trouble answers None (never raises): the app's fold falls back to
    the origin/bounds lanes it already has."""
    fam = payload.get("family")
    want_exe = _FAMILY_EXE.get(fam, "chrome.exe")
    dpr = float(payload.get("dpr") or 1.0)
    view = payload.get("view")
    if not (isinstance(view, (list, tuple)) and len(view) >= 2):
        return None
    try:
        want_w = float(view[0]) * dpr
        want_h = float(view[1]) * dpr
    except (TypeError, ValueError):
        return None
    bounds = payload.get("bounds") or {}
    try:
        bx = float(bounds.get("left", 0)) * dpr
        by = float(bounds.get("top", 0)) * dpr
    except (TypeError, ValueError):
        bx = by = None
    _handles()
    cands = []

    @ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)
    def top_cb(h, _lp):
        if not _u32.IsWindowVisible(h):
            return 1
        pid = wintypes.DWORD()
        _u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value and _exe_of(pid.value) != want_exe:
            return 1
        rw = _render_widget(h)
        if rw is None:
            return 1
        w = rw[2] - rw[0]
        hh = rw[3] - rw[1]
        if w <= 0 or hh <= 0:
            return 1
        if abs(w - want_w) + abs(hh - want_h) > 4:
            return 1
        ow = wintypes.RECT()
        _u32.GetWindowRect(h, ctypes.byref(ow))
        pos_err = (abs(ow.left - bx) + abs(ow.top - by)) \
            if bx is not None else 0.0
        cands.append((abs(w - want_w) + abs(hh - want_h), pos_err, rw))
        return 1
    _u32.EnumWindows(top_cb, 0)
    if not cands:
        return None
    cands.sort()
    rw = cands[0][2]
    return [int(rw[0]), int(rw[1]), int(rw[2] - rw[0]), int(rw[3] - rw[1])]