"""Taskbar hover/autohide - the core pokes.

The goal (docs/taskbar-findings.md): the bar shows while hovered and
vanishes near-instantly, sane on a multi-monitor desk, WITHOUT injecting
a DLL into explorer. Everything here is measured on this desk (24H2/26H2,
Win11) and the measurements are the law:

* ``shell32.SHAppBarMessage`` access-violates for external callers on
  this build (every struct size, zero and real hwnd alike). It is NEVER
  called from here - neither to read state nor to set the flag.
* The autohide flag's truth is the ``HKCU\\...\\StuckRects3`` "Settings"
  blob, byte 8 (2 = shown, 3 = autohide). Read-only, via winreg module
  functions (the open handle has no methods).
* Show/hide is forced with ``PostMessage(trayWnd, WM_TIMER, 3|2)`` -
  id 3 = unhide, id 2 = hide. Plain posts can be swallowed by a
  fullscreen foreground app, so a show is retried every ``retry_ms``
  while the cursor sits at the bar's edge. ``SendMessageTimeout`` to the
  private toggle (WM_USER+0x1CA) is NOT proven from outside and is not
  depended on.
* A "stuck open" taskbar is a focus gate (PermitAutoHide): one
  ``SetForegroundWindow(Progman)`` nudges it; that is the whole unlock,
  one post, no loops.

Honest limits, all fail-open: posting is not obeying (a swallowed post
returns True and does nothing); module enumeration is psapi-ONLY because
toolhelp's snapshot answers ZERO modules in this process family; the
module emulates the native show/hide of a bar that is ALREADY autohiding
(it cannot turn autohide on - the write path is dead) and it hands off
entirely when a tinkerer's mod owns the bar.
"""

from __future__ import annotations

import ctypes
import logging
import time
import winreg
from ctypes import wintypes

from . import wm

log = logging.getLogger("taskbar")

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32

# ------------------------------------------------------------------ consts --
WM_TIMER = 0x111
TIMER_UNHIDE = 3                 # the tray's SetTimer id for "unhide"
TIMER_HIDE = 2                   # ... and for "hide"

LIST_MODULES_ALL = 0x03
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

# module-name substrings (lowercased) that mark a tinkerer's taskbar mod -
# the ones that intercept the same surfaces we poke. "ep_" is the
# StartAllBack-era token; the rest per the findings doc.
COHABITANT_TOKENS = ("ep_", "windhawk", "startallback", "7t", "tweaker")

EDGE_TOL = 4                     # px: how close a bar's edge must be to the
                                 # monitor edge to count as "docked there"
EDGE_PAD = 6                     # px of slack on the hover trigger strip

# the autohide flag's home, byte 8 of the StuckRects3 "Settings" blob
_STUCK_KEY = (r"Software\Microsoft\Windows\CurrentVersion"
              r"\Explorer\StuckRects3")
_STUCK_SHOWN = 2
_STUCK_AUTOHIDE = 3


class POINTL(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


byref = ctypes.byref

# ---- user32 bindings (only the ones this module owns; every other is
# already pinned in wm.py and the types match, so there is no conflict) ----
u32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
u32.FindWindowW.restype = ctypes.c_void_p
u32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
u32.SetForegroundWindow.restype = ctypes.c_void_p
u32.PostMessageW.argtypes = [ctypes.c_void_p, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM]
u32.PostMessageW.restype = wintypes.BOOL
u32.GetCursorPos.argtypes = [ctypes.POINTER(POINTL)]
u32.GetCursorPos.restype = wintypes.BOOL


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _visible(hwnd):
    """IsWindowVisible, fail-open: an error answers False (the bar may be
    dead; there is nothing to show or hide on a dead handle)."""
    try:
        return bool(u32.IsWindowVisible(hwnd))
    except Exception:
        return False


def _rect(hwnd):
    """(left, top, right, bottom) in desktop pixels, or None. The
    pythonw build is DPI-aware, so these are real pixels (the same
    contract wm.true_rect rests on)."""
    try:
        r = wm.RECT()
        if not u32.GetWindowRect(hwnd, byref(r)):
            return None
        return (r.left, r.top, r.right, r.bottom)
    except Exception:
        return None


def _cursor():
    """(x, y) of the pointer in desktop pixels, or None on any failure."""
    try:
        pt = POINTL()
        if not u32.GetCursorPos(byref(pt)):
            return None
        return (pt.x, pt.y)
    except Exception:
        return None


def _tray_hwnds():
    """Every tray window on the desk: the primary Shell_TrayWnd (found
    straight up) plus each Shell_SecondaryTrayWnd (one per extra
    monitor, found by a top-level walk). The classes differ, so there is
    no overlap between the two. Any window mid-destruction is simply not
    collected (the callback swallows its own errors)."""
    out = []
    try:
        prim = u32.FindWindowW("Shell_TrayWnd", None)
        if prim:
            out.append(prim)
    except Exception:
        pass

    found = []

    def cb(hwnd, _l):
        try:
            if _class_name(hwnd) == "Shell_SecondaryTrayWnd":
                found.append(hwnd)
        except Exception:
            pass
        return 1

    try:
        proc = wm.WNDENUMPROC(cb)   # the reference keeps the callback alive
        u32.EnumWindows(proc, 0)
        out.extend(found)
    except Exception:
        pass
    return out


def _monitor_for_bar(rect, mons):
    """The monitor a bar's rect is docked to. The findings-doc rule -
    BOTH of:

    * the rect's center-x sits inside the monitor's horizontal span, and
    * the rect hugs the monitor's TOP or BOTTOM edge within EDGE_TOL px.

    Not either/or: every panel shares one y/h on this desk, so center-x
    alone (or edge proximity alone) would pick the wrong bar on a
    multi-monitor desk. That exact bug bit the probe."""
    if not rect or not mons:
        return None
    l, t, r, b = rect
    if r <= l or b <= t:
        return None
    cx = (l + r) // 2
    for m in mons:
        if not (m["x"] <= cx < m["x"] + m["w"]):
            continue
        top, bottom = m["y"], m["y"] + m["h"]
        if abs(b - bottom) <= EDGE_TOL or abs(t - top) <= EDGE_TOL:
            return m
    return None


def bars():
    """Every tray window mapped to the monitor its bar is docked to:

        {"hwnd": int, "short": str, "rect": (l, t, r, b), "visible": bool}

    ``short`` is the monitor's short id, or "" when the bar could not be
    mapped (no monitor matched the rect - the honest answer, not a guess).
    An empty list when the desk has no tray window at all. Read-only: it
    never pokes a bar (the user's taskbar must not flicker under a test).
    """
    out = []
    try:
        mons = wm.monitors()
    except Exception:
        mons = []
    for hwnd in _tray_hwnds():
        try:
            r = _rect(hwnd)
            if r is None:
                continue
            m = _monitor_for_bar(r, mons)
            out.append({"hwnd": int(hwnd),
                        "short": m["short"] if m else "",
                        "rect": r,
                        "visible": _visible(hwnd)})
        except Exception:
            continue   # a window dying mid-walk is not ours to chase
    return out


def _stuck_byte8():
    """The autohide flag's byte, straight from the registry blob: the
    StuckRects3 "Settings" value, byte 8. 2 = shown, 3 = autohide.
    ``None`` when it could not be read (key gone, value missing, blob
    too short) - the caller treats that as "could not be told"."""
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STUCK_KEY)
        try:
            blob, _type = winreg.QueryValueEx(k, "Settings")
        finally:
            winreg.CloseKey(k)
        if blob is not None and len(blob) > 8:
            return blob[8]
        return None
    except Exception:
        return None


def flag_note():
    """The autohide flag in human words. One of the state words always
    appears so the caller can parse it:

    * "shown"     - the bar is pinned visible (byte 8 == 2)
    * "autohide"  - the bar autohides (byte 8 == 3)
    * "unreadable"- the blob could not be read, with the reason

    The word is the STATE, not a suggestion: this module reads only."""
    b = _stuck_byte8()
    if b == _STUCK_SHOWN:
        return "shown (StuckRects3 byte8 = 2: the bar is pinned visible)"
    if b == _STUCK_AUTOHIDE:
        return "autohide (StuckRects3 byte8 = 3: the bar autohides)"
    if b is None:
        return ("unreadable (StuckRects3 'Settings' missing or too short "
                "to hold byte 8)")
    return "unreadable (StuckRects3 byte8 = %d is not a known state)" % b


def poke_show(hwnd):
    """Post WM_TIMER id 3 (unhide) to a tray window.

    HONEST: this returns the PostMessage result - whether the message
    was POSTED, not whether the bar obeyed. A post returns True and is
    then swallowed (a fullscreen foreground app eats it); that is why
    the watcher retries every ``retry_ms``. A dead/foreign hwnd simply
    makes the post fail (returns False), it does not raise."""
    try:
        return bool(u32.PostMessageW(hwnd, WM_TIMER, TIMER_UNHIDE, 0))
    except Exception:
        return False


def poke_hide(hwnd):
    """Post WM_TIMER id 2 (hide) to a tray window. Same honest contract
    as :func:`poke_show`: posted != obeyed; a swallowed post returns True
    and does nothing. Returns False for a dead/foreign hwnd, never raises."""
    try:
        return bool(u32.PostMessageW(hwnd, WM_TIMER, TIMER_HIDE, 0))
    except Exception:
        return False


def unlock_focus():
    """Nudge the "stuck open" focus gate once: find Progman (the desktop
    window) and SetForegroundWindow it. The docs name the gate
    (PermitAutoHide refuses while the taskbar/flyout owns the
    foreground); one nudge is the whole unlock - one post, no loops.
    Returns whether the SetForegroundWindow call answered True; a missing
    Progman answers False. Never raises."""
    try:
        hwnd = u32.FindWindowW("Progman", None)
        if not hwnd:
            return False
        return bool(u32.SetForegroundWindow(hwnd))
    except Exception:
        return False


def cohabitants():
    """Module names loaded into the shell (the process that owns
    Shell_TrayWnd - explorer.exe) that look like a tinkerer's taskbar mod:
    one whose lowercased name contains any token in COHABITANT_TOKENS.
    ``[]`` on a clean desk.

    Read-only and psapi-ONLY: toolhelp's module snapshot answers ZERO
    modules for every pid in this process family (measured), so the psapi
    route (EnumProcessModulesEx + GetModuleBaseNameW, LIST_MODULES_ALL)
    is the only one that sees the shell's modules - the same walk
    wm.has_xinput proved here. Any error (no tray window, dead pid,
    refused handle) answers ``[]``.

    NOTE: this queries explorer's module table; on a normal shell that is
    fast, but psapi enumerations of a protected process can block, so it
    is called once at watcher start, never in a tight loop."""
    try:
        hwnd = u32.FindWindowW("Shell_TrayWnd", None)
        if not hwnd:
            return []
        pid = wintypes.DWORD()
        if not u32.GetWindowThreadProcessId(hwnd, byref(pid)):
            return []
        h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION,
                            False, pid.value)
        if not h:
            return []
        try:
            ps = ctypes.WinDLL("psapi.dll")
            ps.EnumProcessModulesEx.restype = ctypes.c_bool
            ps.EnumProcessModulesEx.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                wintypes.DWORD]
            need = wintypes.DWORD()
            ps.EnumProcessModulesEx(h, None, 0, byref(need), LIST_MODULES_ALL)
            cnt = max(1, need.value // ctypes.sizeof(ctypes.c_void_p))
            arr = (ctypes.c_void_p * cnt)()
            got = wintypes.DWORD()
            if not ps.EnumProcessModulesEx(h, arr, ctypes.sizeof(arr),
                                           byref(got), LIST_MODULES_ALL):
                return []
            name = ctypes.create_unicode_buffer(260)
            ps.GetModuleBaseNameW.restype = wintypes.UINT
            ps.GetModuleBaseNameW.argtypes = [ctypes.c_void_p,
                                              ctypes.c_void_p,
                                              wintypes.LPWSTR, wintypes.UINT]
            out = []
            for i in range(got.value // ctypes.sizeof(ctypes.c_void_p)):
                if ps.GetModuleBaseNameW(h, arr[i], name, 260):
                    low = name.value.lower()
                    for tok in COHABITANT_TOKENS:
                        if tok in low and name.value not in out:
                            out.append(name.value)
                            break
            return out
        finally:
            k32.CloseHandle(h)
    except Exception:
        return []


# ------------------------------------------------------------ the watcher --
def _at_bar_edge(cx, cy, rect, mon):
    """Is the cursor at this bar's monitor edge - the strip where an
    autohidden bar lives and a person reaches for it?

    The cursor must be over the bar's OWN monitor (every panel shares one
    y/h, so the edge check alone would trigger the wrong bar on a
    multi-monitor desk) and within the bar's vertical trigger band: the
    bar's own rect, stretched to the monitor edge it is docked to, with
    EDGE_PAD px of slack on both sides. A bar that is up reports a full
    thickness (a wide strip); a bar that is hidden reports ~zero
    thickness, so only the few px right at the edge count - which is
    exactly the native "hover the edge to reveal it" gesture."""
    if mon is None or rect is None:
        return False
    m = mon
    if not (m["x"] <= cx < m["x"] + m["w"]
            and m["y"] <= cy < m["y"] + m["h"]):
        return False                    # not over this monitor at all
    l, t, r, b = rect
    if not (l - EDGE_PAD <= cx <= r + EDGE_PAD):
        return False                    # horizontally off the bar's span
    bottom = m["y"] + m["h"]
    # the bar docks to whichever monitor edge its rect is nearest
    edge = bottom if abs(b - bottom) <= abs(t - m["y"]) else m["y"]
    thickness = max(b - t, 1)
    if edge == bottom:                  # bottom-docked: strip just above
        lo, hi = edge - thickness - EDGE_PAD, edge + EDGE_PAD
    else:                               # top-docked: strip just below
        lo, hi = edge - EDGE_PAD, edge + thickness + EDGE_PAD
    return lo <= cy <= hi


def _step_one(bar, mons, cx, cy, now, retry_sec, per):
    """Advance one bar's show/hide state by a single 20 ms tick.

    * cursor at the edge and the bar is down -> poke_show, retrying every
      ``retry_ms`` until it is up (a swallowed post is retried, an up bar
      stops being poked because ``visible`` is then True);
    * cursor LEFT the edge (a True->False hop) and the bar is up ->
      poke_hide exactly once.

    Per-bar memory (last edge-state, last show-post time) is kept in the
    caller's ``per`` dict so the "once" hide and the retry cadence survive
    across ticks. A per-bar error is swallowed (one bar dying is not the
    loop's)."""
    hwnd = bar["hwnd"]
    mon = _monitor_for_bar(bar["rect"], mons)
    at_edge = _at_bar_edge(cx, cy, bar["rect"], mon)
    visible = _visible(hwnd)
    st = per.get(hwnd)
    if st is None:
        st = {"prev_edge": False, "since": 0.0}
        per[hwnd] = st
    if at_edge:
        if not visible and \
                (st["since"] <= 0.0 or now - st["since"] >= retry_sec):
            if poke_show(hwnd):
                st["since"] = now      # the retry anchor (a swallowed post
                                       # is retried on the next cadence slot)
        # else: up and being hovered, or mid-cadence (a post just went out)
        # - do nothing
    else:
        if st["prev_edge"] and visible and poke_hide(hwnd):
            st["since"] = 0.0        # hide fired; reset the retry anchor
    st["prev_edge"] = at_edge


def hover_watch(cfg, stop):
    """The daemon loop the cli runs in its own thread. Fail-open
    end-to-end: every Win32 failure ends only that attempt, never the
    loop, and the loop exits within 100 ms of ``stop`` being set.

    It first checks for a tinkerer's mod (cohabitants); if one owns the
    bar it logs and hands off (sleeps until stop). Then it checks the
    autohide flag; the module emulates the native show/hide only when the
    bar is ALREADY autohiding (byte 8 == 3) - it cannot turn autohide on,
    so with the flag off it idles. Otherwise it polls the cursor at 20 ms
    and drives each bar's show/hide per :func:`_step_one`."""
    try:
        co = cohabitants()
    except Exception:
        co = []
    if co:
        log.info("taskbar: hands off to %s", ", ".join(co))
        stop.wait()
        return
    if _stuck_byte8() != _STUCK_AUTOHIDE:
        log.info("taskbar: autohide is off (StuckRects3 byte8 != 3); "
                 "nothing to emulate; idling")
        stop.wait()
        return
    try:
        retry_sec = float((cfg.get("taskbar") or {})
                          .get("retry_ms", 150)) / 1000.0
    except Exception:
        retry_sec = 0.15
    cache = {"mons": None, "mons_at": 0.0}
    per = {}
    log.info("taskbar: hover watch armed (retry %d ms)",
             int(retry_sec * 1000))
    while not stop.is_set():
        try:
            cx, cy = _cursor()
            if cx is not None:
                now = time.monotonic()
                if cache["mons"] is None or \
                        now - cache["mons_at"] > 2.0:
                    cache["mons"] = wm.monitors()
                    cache["mons_at"] = now
                mons = cache["mons"]
                for bar in bars():
                    try:
                        _step_one(bar, mons, cx, cy, now, retry_sec, per)
                    except Exception:
                        continue
        except Exception:
            log.debug("taskbar: tick died (fail-open)", exc_info=True)
        stop.wait(0.02)
