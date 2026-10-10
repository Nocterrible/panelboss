"""vrr_ghost.py - can a small flip-model window steer the panel's blanking?

The owner's idea (Oct 10): present a tiny popup at a chosen pace and
let VRR stretch the panel's blanking to track it - zero mode
switches, zero flash, fractional rates (23.976) free. The claim
needs a witness. The witness is an observer: a SECOND swap chain
whose Present(vsync=1) calls block until the next blank - the gap
between their returns IS the panel's live blanking period.

    baseline reading: observer gaps ~ panel max hz  -> the ghost was
                      ignored (composited, or VRR does not follow it)
    tracked reading:  observer gaps ~ 1000/--hz     -> the blanking
                      followed the ghost's pace. the trick is real.

Evidence hierarchy per docs/vrr-findings.md: this driver's NVAPI VRR
bits are blind (all zero on a running-VRR panel), so nothing here
queries them - a claim needs an observable witness, and here that
is the timing of the presents themselves. The human witness is the
panel OSD (many show live Hz) or the G-SYNC indicator: watch it
while this runs.

Read-only: dxgi.dll display calls only, zero DRS writes, zero
ChangeDisplaySettings. The legacy dxgi hook surface is a fossil;
every call is printed raw, and a missing export is a finding, not a
crash. Usage: python scripts/vrr_ghost.py [--hz 24] [--seconds 4]
[--monitor 240|short-name]  (no arg = the primary)
"""

import argparse
import ctypes
import os
import statistics
import sys
import threading
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from awaywatch import wm                                          # noqa: E402

u32 = ctypes.windll.user32
dxgi = ctypes.windll.dxgi      # the legacy hook shim: exports resolve
                               # lazily, a missing one raises OSError

u32.DefWindowProcW.restype = ctypes.c_longlong
u32.DefWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                               ctypes.c_ulonglong, ctypes.c_longlong]

WM_CLOSE = 0x0010
WS_POPUP = 0x80000000
SW_SHOW = 5


class MSG(ctypes.Structure):
    _fields_ = (("hwnd", wintypes.HWND), ("message", ctypes.c_uint),
                ("w_param", wintypes.WPARAM), ("l_param", wintypes.LPARAM),
                ("time", ctypes.c_uint), ("pt_x", ctypes.c_long),
                ("pt_y", ctypes.c_long))


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND,
                             ctypes.c_uint, wintypes.WPARAM,
                             ctypes.c_longlong)
_PROCS = []                    # the wndprocs must outlive the windows


class WNDCLASSEX(ctypes.Structure):
    _fields_ = (("cbSize", ctypes.c_uint),
                ("style", ctypes.c_uint),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", ctypes.c_void_p),
                ("hIcon", ctypes.c_void_p),
                ("hCursor", ctypes.c_void_p),
                ("hbrBackground", ctypes.c_void_p),
                ("lpszMenuName", ctypes.c_wchar_p),
                ("lpszClassName", ctypes.c_wchar_p),
                ("hInstance2", ctypes.c_void_p))


_CLASS_DONE = []


def popup(x, y, w, h):
    def proc(hwnd, msg, w_param, l_param):
        return u32.DefWindowProcW(hwnd, msg, w_param, l_param)
    _PROCS.append(WNDPROC(proc))
    if not _CLASS_DONE:
        wc = WNDCLASSEX()
        wc.cbSize = ctypes.sizeof(WNDCLASSEX)
        wc.lpfnWndProc = _PROCS[-1]
        wc.hbrBackground = 2             # COLOR_WINDOW+1: erase black
        wc.lpszClassName = "vrrghost"
        if not u32.RegisterClassExW(ctypes.byref(wc)):
            raise SystemExit("RegisterClassExW failed (%d)"
                             % u32.GetLastError())
        _CLASS_DONE.append(1)
    hwnd = u32.CreateWindowExW(0, "vrrghost", 0, WS_POPUP, x, y, w, h,
                               0, 0, 0, 0)
    if not hwnd:
        raise SystemExit("CreateWindowExW failed (%d)"
                         % u32.GetLastError())
    return hwnd


def make_chain(hwnd, w, h):
    """every creation attempt is reported; the fossil surface wants
    (hwnd, swap_effect, width, height, format, flags, *device,
    *swap_chain) - flip effect first, the tearing-friendly one"""
    attempts = []
    for creator_name in ("D3D11CreateDeviceAndSwapChain",
                         "D3D10CreateDeviceAndSwapChain"):
        try:
            creator = getattr(dxgi, creator_name)
        except AttributeError:
            attempts.append((creator_name, None, "export missing"))
            continue
        for effect in (3, 1, 2, 0):
            dev, chain = ctypes.c_void_p(), ctypes.c_void_p()
            # NOTE: the 8-arg call shape below is the FOSSIL surface
            # (a hook-era convention, never a real export). the real
            # d3d11.dll D3D11CreateDeviceAndSwapChain is the 12-arg
            # adapter/driver/feature-levels/desc form - calling the
            # real one with these args would read 87 as a feature-
            # levels POINTER and AV. kept as a probe of the hook
            # surface only; a COM round 2 rewrites this whole path
            try:
                rc = creator(hwnd, effect, w, h, 87, 1,
                             ctypes.byref(dev), ctypes.byref(chain))
            except OSError as exc:
                attempts.append((creator_name, effect, "call: %s" % exc))
                break
            attempts.append((creator_name, effect,
                             "rc=0x%08X" % (rc & 0xFFFFFFFF)))
            if rc == 0 and chain.value:
                for a in attempts:
                    print("  attempt %s effect=%s %s" % a)
                return creator_name, effect, dev, chain
    for a in attempts:
        print("  attempt %s effect=%s %s" % a)
    return None, None, None, None


def present_of(creator_name):
    """there is NO legacy present shim to name-derive: the returned
    pointer is a COM IDXGISwapChain and Present is vtable slot 5 on
    it - vrr_ghost kept the fossil name-lookup design only as long
    as it could, and this is where it ends"""
    raise SystemExit("%s handed back a COM IDXGISwapChain; no "
                     "D3D11/D3D10SwapChainPresent export exists on "
                     "this box (checked dxgi, d3d11, d3d10, d3d9). "
                     "a COM rewrite needs vtable slot 5 (Present) - "
                     "findings above stand" % creator_name)


def pump():
    msg = MSG()
    while u32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
        u32.TranslateMessage(ctypes.byref(msg))
        u32.DispatchMessageW(ctypes.byref(msg))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hz", type=float, default=24.0)
    ap.add_argument("--seconds", type=float, default=4.0)
    ap.add_argument("--monitor", default="", help="wm short id fragment")
    ap.add_argument("--size", default="36x24")
    args = ap.parse_args()
    size = tuple(int(v) for v in args.size.lower().split("x"))

    mons = wm.monitors()
    for m in mons:
        print("monitor %s at %d,%d %dx%d@%d%s"
              % (m["short"], m["x"], m["y"], m["w"], m["h"], m["rate"],
                 " PRIMARY" if m["primary"] else ""))
    pick = ([m for m in mons if args.monitor and args.monitor in m["short"]]
            or [m for m in mons if m["primary"]] or mons)[0]
    print("ghost goes on %s (%s): watch its OSD now, or the g-sync "
          "indicator" % (pick["short"], pick["rate"]))

    w, h = size
    ghost_win = popup(pick["x"] + 4, pick["y"] + 4, w, h)
    u32.ShowWindow(ghost_win, SW_SHOW)
    obs_win = popup(pick["x"] + 8 + w, pick["y"] + 4, 12, 96)
    u32.ShowWindow(obs_win, SW_SHOW)

    cname, effect, gdev, gchain = make_chain(ghost_win, w, h)
    if not gchain:
        raise SystemExit("no swap chain on this build - findings above")
    present = present_of(cname)
    print("ghost chain: %s effect=%d" % (cname, effect))
    print("warm-up present rc=0x%08X"
          % (present(gchain, 0, 0) & 0xFFFFFFFF))

    ocname, _oe, odev, ochain = make_chain(obs_win, 12, 96)
    observer = present_of(ocname) if ochain else None
    if not observer:
        print("no observer chain: ghost-only run, trust the OSD")

    stop = threading.Event()
    lost_pace = [0]

    def pacer():
        interval = 1.0 / args.hz
        next_t = time.perf_counter()
        deadline = next_t + args.seconds
        while not stop.is_set() and time.perf_counter() < deadline:
            rc = present(gchain, 0, 0)
            if rc != 0:
                print("ghost present stopped the pacer rc=0x%08X"
                      % (rc & 0xFFFFFFFF))
                break
            now = time.perf_counter()
            if now - next_t > interval:
                lost_pace[0] += 1
            next_t += interval
            if next_t > now:
                time.sleep(next_t - now)
        stop.set()

    th = threading.Thread(target=pacer, daemon=True)
    th.start()
    gaps = []
    if observer:
        deadline = time.perf_counter() + args.seconds + 0.5
        while time.perf_counter() < deadline and not stop.is_set():
            t0 = time.perf_counter()
            rc = observer(ochain, 1, 0)      # vsync: blocks to blank
            if rc != 0:
                print("observer present rc=0x%08X - ghost only"
                      % (rc & 0xFFFFFFFF))
                break
            gaps.append(time.perf_counter() - t0)
            pump()
    stop.set()
    th.join(2)

    max_ms = 1000.0 / max(1, pick["rate"])
    want_ms = 1000.0 / args.hz
    if gaps:
        med = statistics.median(gaps) * 1e3
        d_want = abs(med - want_ms)
        d_max = abs(med - max_ms)
        print("observer: %d vsync presents, median gap %.3f ms "
              "(ghost pace %.2f ms off by %.2f, panel max %.2f ms "
              "off by %.2f)"
              % (len(gaps), med, want_ms, d_want, max_ms, d_max))
        if abs(want_ms - max_ms) < max(1.0, 0.25 * max_ms):
            print("verdict: INCONCLUSIVE - --hz is within a quarter "
                  "period of the panel max; no reading can separate "
                  "ghost from baseline here")
        elif d_want < d_max:
            print("verdict: TRACKED (lead only, not verdict: the "
                  "observer's own vsync chain may itself pin the "
                  "cadence, and DWM composing at exactly the ghost "
                  "rate would fake this match - confirm by changing "
                  "--hz and watching med move with it)")
        else:
            print("verdict: NOT TRACKED - the blanking stays nearer "
                  "the panel max; whatever paced it, it was not the "
                  "ghost's 1/--hz (composited cadences like 60 land "
                  "here too - nearer max than want)")
    print("ghost lost pace %d times (sleep granularity is not the "
          "subject here)" % lost_pace[0])
    u32.PostMessageW(ghost_win, WM_CLOSE, 0, 0)
    u32.PostMessageW(obs_win, WM_CLOSE, 0, 0)
    pump()


if __name__ == "__main__":
    main()
