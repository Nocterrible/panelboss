"""videoeye probe: which Windows capture backend ships the "dim around the
playing video" motion eye.

Owner spec: sample a browser window's CONTENT <=5x/s, diff consecutive
frames, bounding box of the changed region = the video rect. Three
backends, each gets one 30 s window at <=2 fps (a black Toplevel covers
half the target for the middle 10 s - the occlusion test):

  A  DXGI desktop duplication, monitor hosting the target, via
     windows_capture.DxgiDuplicationSession (package route, not raw
     ctypes - the wheel ships a session + to_numpy already)
  B  PrintWindow(PW_RENDERFULLCONTENT=2) on the target HWND, manual
     ctypes (PIL ImageGrab.grab(hwnd) is not PrintWindow, so no PIL)
  C  Windows.Graphics.Capture per-window via windows_capture's
     WindowsCapture (event-driven; frames arrive in a callback)

Also printed as they happen: HDR state of the host monitor (wm.hdr_states,
one call), the one-shot WASAPI audio gate (sounding pids cross-named via
panelboss.dimmer._exe), and per-backend cost/occlusion/CPU stats.
No git, no files written, own windows closed on exit.

SIZE LAW note: ~300 lines in one file on purpose - a throwaway measurement
rig whose three backends share one motion-bbox core and one window helper;
splitting into a core + three backend modules would cost 3x the import
seams for a script read once and archived.
"""
import ctypes
import os
import statistics
import sys
import time
import traceback
from collections import deque
from ctypes import wintypes as W

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), ".."))
import numpy as np  # noqa: E402

U32 = ctypes.windll.user32
GDI = ctypes.windll.gdi32
PW_RENDERFULLCONTENT = 2
BROWSER_EXES = ("chrome.exe", "msedge.exe")   # spec's primary set
WIN_SEC = 30.0     # sampling window per backend
COVER_SEC = 10.0   # occlusion cover duration (middle third)
PERIOD = 0.5       # 2 fps = <= 5 fps cap, cheap for the eye's real duty
DS = 4            # downsample stride for the motion diff
THRESH = 24       # gray-level diff = "changed pixel"
_TKROOT = None


def say(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


def gray_ds(arr):
    """(h,w,4) BGR(A) frame -> (h//DS,w//DS) uint8 grayscale.
    Channels are BGRA so B,G,R = 0,1,2 either way."""
    d = arr[::DS, ::DS]
    return ((d[..., 0].astype(np.uint16) + d[..., 1] + d[..., 2]) // 3
            ).astype(np.uint8)


def bbox_of(changed):
    """bool 2-D mask -> (area, (x0,y0,x1,y1) in ds px) or (0, None)."""
    n = int(changed.sum())
    if not n:
        return 0, None
    ys, xs = np.nonzero(changed)
    return n, (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))


def diff_bbox(g, prev, wbox):
    sub = g[wbox[1]:wbox[3], wbox[0]:wbox[2]]
    pv = prev[wbox[1]:wbox[3], wbox[0]:wbox[2]]
    if sub.shape != pv.shape:
        return 0, None
    area, bb = bbox_of(np.abs(sub.astype(np.int16) - pv.astype(np.int16))
                       > THRESH)
    if bb:
        bb = (bb[0] + wbox[0], bb[1] + wbox[1], bb[2] + wbox[0],
              bb[3] + wbox[1])
    return area, bb


def lum_check(gray, bb, wbox):
    """luminance inside the moving bbox vs the window's static chrome:
    the Chromium-GPU black-rectangle check (PrintWindow failure mode)."""
    if not bb or bb[2] - bb[0] < 2 or bb[3] - bb[1] < 2:
        return None
    m = np.zeros(gray.shape, bool)
    m[bb[1]:bb[3] + 1, bb[0]:bb[2] + 1] = True
    inside = gray[m]
    h, w = gray.shape
    chrome = gray[wbox[1] + h // 4:wbox[3] - h // 4,
                  wbox[0] + w // 4:wbox[2] - w // 4]
    if inside.size < 16 or chrome.size == 0:
        return None
    return float(inside.std()), float(inside.mean()), float(chrome.std())


# ---- target window / monitor ------------------------------------------
def top_windows():
    U32.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
    out = []

    @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(h, _lp):
        if U32.IsWindowVisible(h):
            pid = W.DWORD()
            U32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            r = W.RECT()
            U32.GetWindowRect(h, ctypes.byref(r))
            buf = ctypes.create_unicode_buffer(256)
            U32.GetWindowTextW(h, buf, 255)
            out.append(dict(hwnd=int(h), pid=pid.value,
                            title=buf.value, rect=(r.left, r.top,
                                                  r.right, r.bottom)))
        return True
    U32.EnumWindows(cb, 0)
    return out


def _browse(exes):
    from panelboss import dimmer
    return [w for w in top_windows()
            if dimmer._exe(w["pid"]) in exes and w["title"]]


def pick_target():
    cands = _browse(set(BROWSER_EXES))
    if not cands:
        say("no chrome/edge window; opening youtube.com, waiting 8 s")
        import webbrowser
        webbrowser.open("https://www.youtube.com")
        time.sleep(8)
        cands = _browse(set(BROWSER_EXES))
    if not cands:
        # spec's set is empty on this desk (only WebView2 embeds) - the
        # fallback browser is the default (Opera): the eye measures
        # MOTION, the brand is not part of the question
        cands = _browse({"opera.exe"})
        cands.sort(key=lambda w: "youtube" in w["title"].lower(),
                   reverse=True)
        say("fallback: no chrome/edge, using",
            cands[0]["title"][:60] if cands else "NONE")
    if not cands:
        raise SystemExit("no browser target available")
    cands.sort(key=lambda w: (w["rect"][2] - w["rect"][0]) *
               (w["rect"][3] - w["rect"][1]), reverse=True)
    t = cands[0]
    if t["rect"][0] <= -32000:    # parked/minimized: restore so the
        U32.ShowWindow(t["hwnd"], 1)    # probe sees it (spec-allowed
        time.sleep(2)                   # browser focus)
        r = W.RECT()
        U32.GetWindowRect(t["hwnd"], ctypes.byref(r))
        t["rect"] = (r.left, r.top, r.right, r.bottom)
        say("restored minimized window:", t["title"][:60])
    say("TARGET", t["pid"], t["title"][:80], "rect", t["rect"],
        "candidates", len(cands))
    return t


def host_monitor(t):
    """host monitor via the codebase's proven route (wm.monitors /
    monitor_for - GetMonitorInfoW misbehaves on this box, rc=FALSE for
    every arg shape tried). Returns (host_row, dev). Our process is not
    DPI-aware, so GetWindowRect px and dmPosition px share one space.
    Note: our rect is (l,t,R,B); wm wants (x,y,w,h)."""
    from panelboss import wm
    mons = wm.monitors()
    l, tt, rr, bb = t["rect"]
    wx, wy = l, tt
    wrect = (wx, wy, rr - l, bb - tt)
    cx, cy = l + (rr - l) // 2, tt + (bb - tt) // 2
    host = wm.monitor_for(wrect)
    if host is None:
        # centre-based fallback
        host = next((m for m in mons
                     if m["x"] <= cx < m["x"] + m["w"]
                     and m["y"] <= cy < m["y"] + m["h"]), None)
    if host is None:
        host = mons[0]
    say("HOST", host["gdi"], host["short"],
        "px", (host["x"], host["y"], host["w"], host["h"]),
        "primary" if host["primary"] else "secondary",
        "of", len(mons), "monitors")
    return host, host["gdi"]


# ---- stats -------------------------------------------------------------
class Stats:
    def __init__(self, name):
        self.name = name
        self.acq, self.bbox = [], []
        self.to = self.err = 0
        self.covers = []      # (t_sec, area_px_ds)
        self.lums = []        # (std, mean, chrome_std)
        self.outside_small = 0
        self.t0 = time.time()
        self.cpu0 = sum(os.times()[:2])

    def cpu_line(self, tag=""):
        dt = time.time() - self.t0
        cpu = sum(os.times()[:2]) - self.cpu0
        cores = os.cpu_count() or 1
        say(self.name, "CPU", f"{cpu:.2f}s user+sys over {dt:.1f}s = "
            f"{100 * cpu / (cores * dt):.1f}% of {cores} cores", tag)


def summary(name, st, frame_wh, occl, note=""):
    if not st.acq:
        say(name, "SUMMARY no samples", note)
        return
    acq, bx = st.acq, st.bbox
    pre = [a for t, a in st.covers if t < 10]
    cov = [a for t, a in st.covers if 10 <= t < 20]
    post = [a for t, a in st.covers if t >= 20]
    med = lambda xs: statistics.median(xs) if xs else 0
    say(name, "SUMMARY", "samples", len(acq),
        f"fps={len(acq) / WIN_SEC:.2f}", "frame", frame_wh,
        f"acquire ms mean={statistics.mean(acq):.2f} "
        f"p95={np.percentile(acq, 95):.2f}",
        f"bbox ms mean={statistics.mean(bx):.2f} "
        f"p95={np.percentile(bx, 95):.2f}",
        f"timeouts={st.to} errors={st.err}",
        f"outside_small_motion_samples={st.outside_small}",
        "occlusion", occl,
        f"pre/cov/post median bbox px (ds): "
        f"{med(pre):.0f}/{med(cov):.0f}/{med(post):.0f}", note)
    if st.lums:
        worst = min(st.lums, key=lambda x: x[0])
        say(name, "LUMINANCE bbox(std/mean) vs chrome(std):",
            f"min-bbox-std={worst[0]:.1f} bbox-mean={worst[1]:.1f} "
            f"chrome-std={worst[2]:.1f} over {len(st.lums)} checks")
    st.cpu_line()


def cover_toggle(t, phase):
    """'up': black Toplevel over the LEFT HALF of the target (half the
    target area, over the video region of a typical browser layout).
    overrideredirect = no taskbar entry, minimal focus stealing. Returns
    the window (caller keeps it alive, destroys on 'down')."""
    global _TKROOT
    import tkinter as tk
    if _TKROOT is None:
        _TKROOT = tk.Tk()
        _TKROOT.withdraw()
    w = (t["rect"][2] - t["rect"][0]) // 2
    h = t["rect"][3] - t["rect"][1]
    win = tk.Toplevel(_TKROOT)
    win.overrideredirect(True)
    win.config(bg="black")
    win.geometry(f"{w}x{h}+{t['rect'][0]}+{t['rect'][1]}")
    win.update()
    say("COVER up over left half", (w, h))
    return win


def run_cover_phase(st, cov, ref, up_after=10):
    """drive the cover schedule; returns the (possibly new) cover win.
    ref = time base (st.t0)."""
    now = time.time() - ref
    if cov is None and now >= up_after:
        try:
            cov = cover_toggle(COVER_T, "up")
        except Exception:
            say("COVER failed, occlusion test SKIPPED:",
                traceback.format_exc().strip().splitlines()[-1])
            cov = "FAILED"
    if cov is not None and cov != "FAILED" and now >= up_after + COVER_SEC:
        cov.destroy()
        say("COVER down")
        cov = None
    return cov


COVER_T = None    # filled in main (the target dict for the cover)


def occl_verdict(st):
    pre = [a for t, a in st.covers if t < 10]
    cov = [a for t, a in st.covers if 10 <= t < 20]
    post = [a for t, a in st.covers if t >= 20]
    m = lambda xs: statistics.median(xs) if xs else 0
    p, c, q = m(pre), m(cov), m(post)
    if p < 50:
        return "NO-MOTION-BASELINE (target may not be playing)"
    keep = "KEPT" if c >= 0.3 * p else "DEGRADED"
    rec = "IMMEDIATE" if q >= 0.3 * p else "SLOW/NOT-IN-WINDOW"
    return f"{keep} motion through cover (pre/med={p:.0f} cov={c:.0f} " \
           f"post={q:.0f}); recovery {rec}"


# ---- backend A: DXGI desktop duplication (package session) -------------
def window_box_ds(t, host, shape):
    """target window rect in downsampled frame coords (backend A).
    Frame px == monitor px (DD outputs native res); GetWindowRect px
    and the host row's dmPosition px share one space (non-DPI-aware
    process)."""
    r, m = t["rect"], host
    x0 = max(0, int((r[0] - m["x"]) / DS))
    y0 = max(0, int((r[1] - m["y"]) / DS))
    x1 = min(shape[1] // DS, int((r[2] - m["x"]) / DS))
    y1 = min(shape[0] // DS, int((r[3] - m["y"]) / DS))
    return (x0, y0, x1, y1)


def outside_motion(g, prev, wbox):
    """cursor-ride heuristic (backend A): small motion OUTSIDE the window
    rect = desktop cursor (or a toast) in the duplicated output."""
    H, Wd = g.shape
    mask = np.zeros_like(g, bool)
    if wbox[1] > 0:
        mask[:wbox[1], :] = True
    if wbox[3] < H:
        mask[wbox[3]:, :] = True
    if wbox[0] > 0:
        mask[:, :wbox[0]] = True
    if wbox[2] < Wd:
        mask[:, wbox[2]:] = True
    ch = np.abs(g.astype(np.int16) - prev.astype(np.int16)) > THRESH
    n = int((ch & mask).sum())
    return 4 < n < 0.002 * H * Wd


def run_a(t, host):
    import windows_capture as wc
    from panelboss import wm
    st = Stats("A")
    prev, frame_wh = None, None
    nmons = len(wm.monitors())
    say("A", "start DxgiDuplicationSession - picking capture_index by "
        "content (all monitors are %dx%d, size can't disambiguate) "
        "of %d" % (host["w"], host["h"], nmons))

    def pick_index():
        """Scan candidate monitors; the one with the most motion inside
        the target's window region over 2 frames is the host. Content
        match, not slot order - the native index ordering is unknown."""
        best, best_area, best_sess = None, -1, None
        for alt in range(nmons):
            try:
                s2 = wc.DxgiDuplicationSession(alt)
                f1 = s2.acquire_frame(1000)
            except Exception:
                continue
            if f1 is None:
                continue
            time.sleep(0.25)
            try:
                f2 = s2.acquire_frame(1000)
            except Exception:
                f2 = None
            if f2 is None:
                continue
            a1, a2 = f1.to_numpy(), f2.to_numpy()
            if a1.shape != a2.shape:
                continue
            g1, g2 = gray_ds(a1), gray_ds(a2)
            wbox = window_box_ds(t, host, a1.shape)
            area, _ = diff_bbox(g2, g1, wbox)
            if area > best_area:
                best_area, best, best_sess = area, alt, s2
        if best is None:
            say("A", "no monitor showed window-region motion; default 0")
            best, best_sess = 0, wc.DxgiDuplicationSession(0)
        say("A", "capture_index", best, "window-region motion",
            best_area, "ds px^2")
        return best_sess, best
    sess, idx = pick_index()
    end = time.time() + WIN_SEC
    cov = None
    try:
        while time.time() < end:
            loop_start = time.time()
            cov = run_cover_phase(st, cov, st.t0)
            try:
                f = sess.acquire_frame(timeout_ms=1000)
            except RuntimeError:
                st.to += 1
                try:
                    sess.recreate()          # ACCESS_LOST class: respawn
                except Exception:
                    pass
                f = None
            if f is None:
                time.sleep(0.1)
                continue
            t0 = time.perf_counter()
            a = f.to_numpy()
            t1 = time.perf_counter()
            if frame_wh is None:
                frame_wh = (a.shape[1], a.shape[0])
                say("A", "frame", frame_wh, "color", f.color_format,
                    "host_px", (host["w"], host["h"]),
                    "HOST-SIZE-MISMATCH"
                    if (host["w"], host["h"]) != frame_wh else "host-match")
            g = gray_ds(a)
            wbox = window_box_ds(t, host, a.shape)
            st.acq.append((t1 - t0) * 1e3)
            t0b = time.perf_counter()
            if prev is not None:
                area, bb = diff_bbox(g, prev, wbox)
                st.bbox.append((time.perf_counter() - t0b) * 1e3)
                st.covers.append((time.time() - st.t0, area))
                if len(st.lums) % 10 == 0:
                    v = lum_check(g, bb, wbox)
                    if v:
                        st.lums.append(v)
                if outside_motion(g, prev, wbox):
                    st.outside_small += 1
            prev = g
            time.sleep(max(0.0, PERIOD - (time.time() - loop_start)))
    finally:
        if cov is not None and cov != "FAILED":
            try:
                cov.destroy()
            except Exception:
                pass
    summary("A", st, frame_wh, occl_verdict(st),
            "route: windows_capture.DxgiDuplicationSession idx=%d" % idx
            + "; cursor: DDA composites the desktop cursor into the frame")


# ---- backend B: PrintWindow(PW_RENDERFULLCONTENT) -----------------------
class BmpInfo(ctypes.Structure):
    _fields_ = [("biSize", W.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", W.WORD),
                ("biBitCount", W.WORD), ("biCompression", W.DWORD),
                ("biSizeImage", W.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", W.DWORD),
                ("biClrImportant", W.DWORD)]


def pw_grab(hwnd):
    """PrintWindow into a top-down 32bpp DIB -> (h,w,4) BGRA, or None."""
    r = W.RECT()
    U32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return None
    sdc = U32.GetDC(None)
    mdc = GDI.CreateCompatibleDC(sdc)
    bmp = GDI.CreateCompatibleBitmap(sdc, w, h)
    GDI.SelectObject(mdc, bmp)
    ok = U32.PrintWindow(hwnd, mdc, PW_RENDERFULLCONTENT)
    bmi = BmpInfo()
    bmi.biSize = ctypes.sizeof(bmi)
    bmi.biWidth, bmi.biHeight = w, -h
    bmi.biPlanes, bmi.biBitCount, bmi.biCompression = 1, 32, 0
    buf = (ctypes.c_ubyte * (w * h * 4))()
    got = GDI.GetDIBits(mdc, bmp, 0, h, buf, bmi, 0)
    GDI.DeleteObject(bmp)
    GDI.DeleteDC(mdc)
    U32.ReleaseDC(None, sdc)
    if not ok or got != h:
        return None
    return np.frombuffer(buf, np.uint8).reshape(h, w, 4)


def run_b(t):
    st = Stats("B")
    say("B", "start PrintWindow(PW_RENDERFULLCONTENT) on hwnd", t["hwnd"])
    prev, frame_wh = None, None
    end = time.time() + WIN_SEC
    cov = None
    try:
        while time.time() < end:
            loop_start = time.time()
            cov = run_cover_phase(st, cov, st.t0)
            t0 = time.perf_counter()
            a = pw_grab(t["hwnd"])
            t1 = time.perf_counter()
            if a is None:
                st.err += 1
                time.sleep(0.2)
                continue
            g = gray_ds(a)
            if frame_wh is None:
                frame_wh = (a.shape[1], a.shape[0])
                say("B", "frame", frame_wh)
            wbox = (0, 0, g.shape[1], g.shape[0])
            st.acq.append((t1 - t0) * 1e3)
            t0b = time.perf_counter()
            if prev is not None:
                area, bb = diff_bbox(g, prev, wbox)
                st.bbox.append((time.perf_counter() - t0b) * 1e3)
                st.covers.append((time.time() - st.t0, area))
                if len(st.lums) % 10 == 0:
                    v = lum_check(g, bb, wbox)
                    if v:
                        st.lums.append(v)
                if g.std() < 2:
                    st.err += 1      # whole frame black = PW gave nothing
            prev = g
            time.sleep(max(0.0, PERIOD - (time.time() - loop_start)))
    finally:
        if cov is not None and cov != "FAILED":
            try:
                cov.destroy()
            except Exception:
                pass
    summary("B", st, frame_wh, occl_verdict(st),
            "route: manual ctypes PrintWindow; cursor: PrintWindow never "
            "captures the desktop cursor")


# ---- backend C: Windows.Graphics.Capture per-window ----------------------
def run_c(t):
    import windows_capture as wc
    st = Stats("C")
    frames, closed = deque(), []

    def on_frame_arrived(f, _ctrl):
        t0 = time.perf_counter()
        g = gray_ds(f.frame_buffer)
        frames.append((g, (time.perf_counter() - t0) * 1e3))

    def on_closed():
        closed.append(time.time())

    cap = wc.WindowsCapture(window_hwnd=t["hwnd"], cursor_capture=True)
    cap.event(on_frame_arrived)
    cap.event(on_closed)
    ctrl = cap.start_free_threaded()
    say("C", "start WindowsCapture(window_hwnd=%d, cursor=True)"
        % t["hwnd"])
    prev, frame_wh, dropped, last_take = None, None, 0, st.t0
    end = st.t0 + WIN_SEC
    cov = None
    try:
        while time.time() < end:
            loop_start = time.time()
            cov = run_cover_phase(st, cov, st.t0)
            if len(frames) > 1:
                dropped += len(frames) - 1
            if not frames:
                st.to += 1
                time.sleep(0.05)
                continue
            if time.time() - last_take < PERIOD:
                time.sleep(PERIOD - (time.time() - last_take))
            g, acq = frames.popleft()
            last_take = time.time()
            if frame_wh is None:
                frame_wh = (g.shape[1] * DS, g.shape[0] * DS)
                say("C", "frame (approx, ds x %d)" % DS, frame_wh)
            st.acq.append(acq)
            t0b = time.perf_counter()
            if prev is not None:
                area, bb = diff_bbox(g, prev,
                                     (0, 0, g.shape[1], g.shape[0]))
                st.bbox.append((time.perf_counter() - t0b) * 1e3)
                st.covers.append((time.time() - st.t0, area))
                if len(st.lums) % 10 == 0:
                    v = lum_check(g, bb, (0, 0, g.shape[1], g.shape[0]))
                    if v:
                        st.lums.append(v)
            prev = g
            time.sleep(PERIOD)
    finally:
        try:
            ctrl.stop()
            ctrl.wait()
        except Exception:
            pass
        if cov is not None and cov != "FAILED":
            try:
                cov.destroy()
            except Exception:
                pass
    summary("C", st, frame_wh, occl_verdict(st),
            "route: windows_capture.WindowsCapture (WGC per-window); "
            "dropped_unprocessed=%d closed_events=%d; cursor: "
            "cursor_capture=True" % (dropped, len(closed)))


# ---- audio gate (one-shot) ----------------------------------------------
def audio_gate(target):
    from panelboss import _wasapi, dimmer
    pids = _wasapi.sounding_pids()
    say("AUDIO sounding_pids:", sorted(pids) or "(none)")
    for pid in sorted(pids):
        say("AUDIO", "pid", pid, "exe", repr(dimmer._exe(pid)))
    say("AUDIO target UI pid:", target["pid"],
        "exe", repr(dimmer._exe(target["pid"])))


def main():
    T0 = time.time()
    say("VIDEOEYE PROBE", sys.version.split()[0], "numpy", np.__version__)
    global COVER_T
    COVER_T = pick_target()
    host, dev = host_monitor(COVER_T)
    from panelboss import wm
    rows = wm.hdr_states()
    say("HDR", [(r["gdi"], r["model"], r["state"], r["precise"])
                for r in rows if r["gdi"] == dev]
        or f"host {dev} not in hdr_states() rows")
    audio_gate(COVER_T)
    for name, fn in (("A", lambda: run_a(COVER_T, host)),
                     ("B", lambda: run_b(COVER_T)),
                     ("C", lambda: run_c(COVER_T))):
        try:
            fn()
        except Exception:
            say(name, "RAISED, continuing:",
                traceback.format_exc().strip().splitlines()[-2:])
    say("TOTAL runtime %.1f s" % (time.time() - T0))
    say("PROBE DONE")


if __name__ == "__main__":
    main()
