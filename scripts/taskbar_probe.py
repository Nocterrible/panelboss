"""read-only taskbar probe: what explorer's bar surface looks like
from OUTSIDE, right now. Finds the primary + secondary tray windows,
asks the AppBar API what autohide flag each carries, maps them onto
our monitors, sniffs the shell process for the known taskbar
tinkerers (ExplorerPatcher / Windhawk / StartAllBack / 7+ Tweaker)
that would intercept the same surfaces, and locates the cursor for
the future hover loop. NOTHING is written: no SETSTATE, no
PostMessage, no SetForegroundWindow - this only proves the machinery
docs/taskbar-findings.md leans on is reachable on this machine.

Run: python scripts/taskbar_probe.py   (from repo root)
"""
import ctypes
import sys
from ctypes import wintypes as W

sys.path.insert(0, ".")
from awaywatch import wm  # noqa: E402  monitors(); shares u32/k32

u32, k32 = wm.u32, wm.k32
ABM_GETSTATE = 0x00000004
ABS_ONTOP, ABS_AUTOHIDE = 0x01, 0x02
TH32_SNAPMODULE = 0x00000010
INVALID = ctypes.cast(ctypes.c_void_p(-1), ctypes.c_void_p).value
MARKERS = ("ep_", "windhawk", "startallback", "7t-tweaker")


class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("hWnd", W.HWND),
                ("l", W.LONG), ("t", W.LONG), ("r", W.LONG),
                ("b", W.LONG), ("uCallback", W.UINT),
                ("dwState", W.DWORD)]


class MODULEENTRY32W(ctypes.Structure if False else
                     ctypes.Structure):    # copy of wm's proven
    _fields_ = [("dwSize", W.DWORD),      # layout (wm builds its
                ("resumed", W.DWORD),     # own inside has_xinput)
                ("count", W.DWORD),
                ("mod", ctypes.c_void_p),
                ("szModule", W.WCHAR * 256),
                ("exe", W.WCHAR * 260)]


# one-time wiring; windll.user32 is a shared cached singleton, so
# argtypes are set once, in call order, right here.
u32.FindWindowW.restype = W.HWND
u32.FindWindowW.argtypes = [W.LPCWSTR, W.LPCWSTR]
u32.GetWindowRect.restype = W.BOOL
u32.GetWindowRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
u32.IsWindowVisible.restype = W.BOOL
u32.IsWindowVisible.argtypes = [W.HWND]
u32.GetWindowThreadProcessId.restype = W.UINT
u32.GetWindowThreadProcessId.argtypes = [W.HWND,
                                         ctypes.POINTER(W.DWORD)]
u32.GetCursorPos.restype = W.BOOL
u32.GetCursorPos.argtypes = [ctypes.POINTER(W.POINT)]
ENUMCB = ctypes.CFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
u32.EnumWindows.restype = W.BOOL
u32.EnumWindows.argtypes = [ENUMCB, W.LPARAM]
sh32 = ctypes.windll.shell32
sh32.SHAppBarMessage.restype = W.UINT
sh32.SHAppBarMessage.argtypes = [ctypes.POINTER(APPBARDATA),
                                 W.UINT]
k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
k32.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
k32.Module32FirstW.restype = W.BOOL
k32.Module32FirstW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
k32.Module32NextW.restype = W.BOOL
k32.Module32NextW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
k32.CloseHandle.restype = W.BOOL
k32.CloseHandle.argtypes = [ctypes.c_void_p]


def find_bars():
    """Every Shell_TrayWnd / Shell_SecondaryTrayWnd in z-order."""
    found = []

    def cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(64)
        if u32.GetClassNameW(hwnd, buf, 64) and \
                buf.value in ("Shell_TrayWnd",
                              "Shell_SecondaryTrayWnd"):
            found.append(hwnd)
        return True

    keep = ENUMCB(cb)
    u32.EnumWindows(keep, 0)
    return found


def bar_state(hwnd=None):
    """(None, note). MEASURED HERE: shell32.SHAppBarMessage
    access-violates for EXTERNAL callers on this build (every struct
    size, zero and real hwnd alike - bisected in child processes),
    so the flag truth comes from the StuckRects3 blobs the Settings
    toggle itself writes (READ-ONLY; byte 8's autohide bit is the
    community-proven spot, the other bits encode edge/lock and are
    version-noisy). MMStuckRects3 is the multi-monitor layout."""
    import winreg
    out = []
    for key in ("StuckRects3", "MMStuckRects3"):
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               "Software\\Microsoft\\Windows\\"
                               "CurrentVersion\\Explorer\\" + key)
            blob = winreg.QueryValueEx(k, "Settings")[0]
            out.append("%s byte8=%s" % (key, hex(blob[8]))
                       if blob and len(blob) > 8 else
                       "%s: short blob" % key)
        except OSError as exc:
            out.append("%s unreadable: %s" % (key, exc.strerror))
    return None, "; ".join(out)


def owner(hwnd):
    pid = W.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def shell_modules(pid):
    """Module names of pid via the toolhelp walk that wm.has_xinput
    proved works here: flags SNAPMODULE|SNAPMODULE32, First called
    exactly once (it resets the OS-side walk), dwSize re-set before
    every Next, sentinel checked."""
    snap = k32.CreateToolhelp32Snapshot(TH32_SNAPMODULE | 0x00000100,
                                        pid)
    if snap in (None, getattr(wm, "_INVALID_HANDLE_VALUE",
                              ctypes.cast(ctypes.c_void_p(-1),
                                          ctypes.c_void_p).value)):
        return []
    names = []
    try:
        me = MODULEENTRY32W()
        me.dwSize = ctypes.sizeof(me)
        if not k32.Module32FirstW(snap, ctypes.byref(me)):
            return []
        while True:
            names.append((me.szModule or "").lower())
            me.dwSize = ctypes.sizeof(me)   # required before each Next
            if not k32.Module32NextW(snap, ctypes.byref(me)):
                break
    except Exception:
        pass                          # a snapshot can refuse; the
    finally:                          # probe survives it
        k32.CloseHandle(snap)
    return names


def main():
    mons = wm.monitors()
    print("monitors: " + ", ".join(
        "%s@%d (%d,%d %dx%d)" % (m["short"], m["rate"], m["x"],
                                 m["y"], m["w"], m["h"]) for m in mons))
    bars = find_bars()
    print("tray windows found: %d" % len(bars))
    _, flag = bar_state(bars[0] if bars else None)
    print("autohide flag truth (global, Settings' own store): "
          + flag)
    for h in bars:
        rect = W.RECT()
        u32.GetWindowRect(h, ctypes.byref(rect))
        hit = next((m for m in mons
                    if (rect.left + rect.right) / 2 >= m["x"] and
                    (rect.left + rect.right) / 2 < m["x"] + m["w"] and
                    abs(rect.bottom - (m["y"] + m["h"])) <= 4), None)
        print("  hwnd %s pid %d rect=(%d,%d,%d,%d) visible=%s -> %s"
              % (h, owner(h), rect.left, rect.top, rect.right,
                 rect.bottom, bool(u32.IsWindowVisible(h)),
                 "|monitor " + hit["short"] if hit else "|unmapped"))
    if bars:
        mods = shell_modules(owner(bars[0]))
        tinkerers = sorted({n for n in mods
                            for mk in MARKERS if mk in n})
        print("shell modules: %d, taskbar tinkerers loaded: %s"
              % (len(mods), ", ".join(tinkerers) or "none"))
    pt = W.POINT()
    u32.GetCursorPos(ctypes.byref(pt))
    print("cursor at (%d,%d) - the hover loop's only sensor"
          % (pt.x, pt.y))
    print("taskbar surface reachable from ctypes: %s"
          % ("YES" if bars else "NO"))
    return 0 if bars else 1


if __name__ == "__main__":
    sys.exit(main())
