"""theater_live: the permanent live-desk guard for the theater ring's
z-order law (cappy packet, Oct-16).

The bug class this exists to catch: the ring PAINTED, measured, and
INVISIBLE - the wrong-direction anchor of Oct-15 and the six-arg,
wrong-band SetWindowPos of Oct-16 both hid behind unit pins that fake
the paint seam. This script reads the REAL desk: it enumerates the
running app's overlay windows, finds the four theater pieces at the
EXACT rects _frame_pieces must produce, and asserts each is VISIBLE,
TOPMOST-BAND, ABOVE the browser window that covers the hole, and
BELOW the taskbar of its row (the desk's chrome never darkens).

Run WITH a video playing and the desk idle past [videodim].idle_sec:
  .venv\\Scripts\\python.exe scripts\\theater_live.py
Exit 0 = the law holds on this desk right now; exit 1 names the piece
that broke it and the desk's idle seconds, so LAWFUL absence (desk in
use, rail not reached) reads differently from the bug. A z-law
regression must fail green->red HERE, not owner->debugger.
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

U = ctypes.windll.user32
GWL_EXSTYLE, WS_EX_TOPMOST = -20, 0x8
TRAY = ("Shell_TrayWnd", "Shell_SecondaryTrayWnd")
ENUMPROT = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_long)


def app_pids():
    """The PanelBoss process tree: the venv redirector (command line
    carries the path or run.py) plus its base child (found by
    parentage). One PowerShell call, parsed here."""
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
          "ForEach-Object { \"$($_.ProcessId)|$($_.ParentProcessId)|"
          "$($_.CommandLine)\" }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True).stdout
    rows = []
    for ln in out.splitlines():
        p = ln.split("|", 2)
        try:
            rows.append((int(p[0]), int(p[1]), p[2] if len(p) > 2 else ""))
        except (ValueError, IndexError):
            continue
    ours = {pid for pid, _parent, cl in rows
            if "panelboss-reskin" in cl or "run.py" in cl}
    grew = True
    while grew:
        grew = False
        for pid, parent, _cl in rows:
            if parent in ours and pid not in ours:
                ours.add(pid)
                grew = True
    return ours


def enumerate_windows():
    """[(hwnd, class, (l,t,r,b), visible, topmost, pid)] - one walk."""
    found = []

    def cb(h, _l):
        pid = wt.DWORD()
        U.GetWindowThreadProcessId(h, ctypes.byref(pid))
        cls = ctypes.create_unicode_buffer(256)
        U.GetClassNameW(h, cls)
        r = wt.RECT()
        U.GetWindowRect(h, ctypes.byref(r))
        ex = U.GetWindowLongW(h, GWL_EXSTYLE)
        found.append((h, cls.value, (r.left, r.top, r.right, r.bottom),
                      bool(U.IsWindowVisible(h)), bool(ex & WS_EX_TOPMOST),
                      pid.value))
        return 1
    U.EnumWindows(ENUMPROT(cb), 0)
    return found


def folded_row():
    """The doorway row folded exactly like the eye does it (the app's
    own module does the work - no second implementation of the fold)."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    from panelboss import videoeye
    return videoeye._rect_px(videoeye._read(time.monotonic(), time.time()))


def expected_pieces(hole):
    """The exact piece set _frame_pieces WOULD produce (mirror of
    dimmer.py's clamped complement: per monitor the rect touches, the
    four edge bands, zero-area sides dropped). Exact matching, so no
    coincidental Tk window near the hole can impersonate a piece."""
    rx, ry, rw, rh = hole
    mons = []
    MONITORPROC = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(wt.RECT), ctypes.c_long)

    def cb(h, _dc, m_rect, _mp):
        mons.append((m_rect.left, m_rect.top, m_rect.right, m_rect.bottom))
        return 1
    U.EnumDisplayMonitors(0, 0, MONITORPROC(cb), 0)
    out = set()
    for mx, my, mr, mb in mons:
        ix0, iy0 = max(rx, mx), max(ry, my)
        ix1, iy1 = min(rx + rw, mr), min(ry + rh, mb)
        if ix0 >= ix1 or iy0 >= iy1:
            continue
        if iy0 > my:
            out.add((mx, my, mr, iy0))
        if iy1 < mb:
            out.add((mx, iy1, mr, mb))
        if ix0 > mx:
            out.add((mx, iy0, ix0, iy1))
        if ix1 < mr:
            out.add((ix1, iy0, mr, iy1))
    return out


def idle_seconds():
    li = wt.LASTINPUTINFO()
    li.cb = ctypes.sizeof(li)
    U.GetLastInputInfo(ctypes.byref(li))
    return (wt.GetTickCount() - li.dwTime) / 1000.0


def main():
    wins = enumerate_windows()
    order = [w[0] for w in wins if w[3]]          # EnumWindows: top-down
    pids = app_pids()
    if not pids:
        print("FAIL: no running PanelBoss (launch it first)")
        return 1
    hole = folded_row()
    if hole is None:
        print("FAIL: no usable doorway row - play a video on the site "
              "list and idle past the theater rail")
        return 1
    door = os.path.join(os.environ["APPDATA"], "PanelBoss", "rect")
    age = time.time() - os.path.getmtime(door)
    if age > 600:
        print("FAIL: the doorway row is %.0f s old - a stale rect "
              "validates the wrong geometry; play something fresh" % age)
        return 1
    x, y, w, h = hole
    exp = expected_pieces(hole)
    # The BROWSER: the visible Chromium-class window covering the
    # hole's center (all three site families share the class). The
    # foreground window was the first cut's proxy and made a console-
    # run guard falsely red (gate finding 3); if no browser is found,
    # fall back to the foreground and SAY so.
    browser = None
    for hwnd, cls, rect, vis, _t, _p in wins:
        cx, cy = x + w // 2, y + h // 2
        if vis and cls == "Chrome_WidgetWin_1" and \
                rect[0] <= cx <= rect[2] and rect[1] <= cy <= rect[3]:
            browser = hwnd
            break
    ref = browser or U.GetForegroundWindow()
    ref_pos = order.index(ref) if ref in order else 0
    trays = [hwnd for hwnd, cls, rect, vis, _t, _p in wins
             if cls in TRAY and vis]
    tray_spans = {hwnd: (rect[0], rect[2]) for hwnd, cls, rect, vis,
                  _t, _p in wins if hwnd in trays}
    found = [(hwnd, rect, top) for hwnd, cls, rect, vis, top, pid in wins
             if pid in pids and cls == "TkTopLevel" and vis
             and rect in exp]
    if not found:
        print("FAIL: no pieces at the expected rects %s - the ring is "
              "not painted. Desk input-idle %.1f s: under "
              "[videodim].idle_sec that absence is LAWFUL - hands off "
              "and re-run; past the rail it is the bug (the pause? "
              "the rail?)" % (sorted(exp)[:4], idle_seconds()))
        return 1
    missing = exp - {rect for _h, rect, _t in found}
    if missing:
        print("FAIL: %d of %d expected pieces absent (%s) - a partial "
              "ring is the old bite with one tooth missing"
              % (len(missing), len(exp), sorted(missing)))
        return 1
    bad = 0
    for hwnd, rect, top in found:
        pos = order.index(hwnd)
        row_trays = [order[t] for t in trays
                     if t in order and min(tray_spans[t][1], x + w)
                     - max(tray_spans[t][0], x) > 0]
        under_tray = (not row_trays) or all(pos > p for p in row_trays)
        if not top or pos > ref_pos or not under_tray:
            bad += 1
            print("FAIL: piece %s rect=%s z=%d vs browser z=%d (%s) "
                  "topmost=%s under_tray=%s"
                  % (hex(hwnd), rect, pos, ref_pos,
                     "hole-center window" if browser else
                     "FOREGROUND - no browser found under the hole",
                     top, under_tray))
    print(("OK: %d pieces: visible, topmost band, above the browser, "
           "below the taskbar" % len(found)) if not bad else
          ("BROKEN: %d of %d pieces fail the law" % (bad, len(found))))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
