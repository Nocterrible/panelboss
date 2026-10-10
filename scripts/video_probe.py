"""video signal probe: which PDH GPU Engine kinds real video decode
lights up on THIS driver/browser stack, per process.

The gaming engine deliberately ignores every non-render engine kind;
the video-rate feature needs the OPPOSITE filter, so the question
comes back: where does hardware decode actually land on 2026 drivers
- videodecode? videoprocessing? something else? No engine may trust a
counter this probe has not seen move with real video.

Same laws as gpu.py (whose plumbing this rides): fresh PDH query per
call (engine instances are born with the process), one collect pair
(~1.2 s gap), per-instance reads only (the wildcard array read heap-
corrupts this build), cap 400 instances, fail open to {}.

Run it IDLE first, then again while a video plays - only the delta
proves the signal.
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes as W

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), ".."))

from awaywatch import gaming_watch, gpu, wm  # noqa: E402

CAP = 400
# kinds whose whole existence is video: if the game engine ignores
# them and they still light up on Netflix, they are the video signal
VIDEO_KINDS = ("VIDEODECODE", "VIDEOENCODE", "VIDEOPROCESSING", "JPEG")


def proc_names():
    """pid -> exe name via the toolhelp PROCESS snapshot (flag 0x2).
    Module snapshots are dead in this process family; the process
    snapshot is measured fine."""
    k32 = ctypes.WinDLL("kernel32")

    class PE(ctypes.Structure):
        _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD),
                    ("th32ProcessID", W.DWORD),
                    ("th32DefaultHeapID", ctypes.POINTER(W.BYTE)),
                    ("th32ModuleID", W.DWORD), ("cntThreads", W.DWORD),
                    ("th32ParentProcessID", W.DWORD),
                    ("PriClassBase", W.LONG), ("dwFlags", W.DWORD),
                    ("szExeFile", 260 * ctypes.c_char)]
    k32.CreateToolhelp32Snapshot.restype = W.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
    k32.Process32FirstW.argtypes = [W.HANDLE, ctypes.POINTER(PE)]
    k32.Process32NextW.argtypes = [W.HANDLE, ctypes.POINTER(PE)]
    out = {}
    h = k32.CreateToolhelp32Snapshot(0x2, 0)
    if not h:
        return out
    pe = PE()
    pe.dwSize = ctypes.sizeof(pe)
    if k32.Process32FirstW(h, ctypes.byref(pe)):
        while True:
            out[pe.th32ProcessID] = pe.szExeFile.decode("mbcs",
                                                        "replace")
            if not k32.Process32NextW(h, ctypes.byref(pe)):
                break
    k32.CloseHandle(h)
    return out


def sample(render_only=False):
    """{(pid, kind): busy_percent} across ALL engine kinds (or just
    the rendering ones, for the cap experiment), fresh query per
    call; {} on any failure."""
    q = None
    try:
        rc, names = gpu._enum()
        if rc or not names:
            print("enumerate rc=%x names=%d" % (rc, len(names)))
            return {}
        by_kind = {}
        for n in names:
            m = gpu._INST_RE.match(n)
            if not m:
                continue
            kind = m.group(2).upper()
            if render_only and not gpu._is_render(kind):
                continue
            by_kind.setdefault((int(m.group(1)), kind), n)
        pairs = sorted(by_kind.items())[:CAP]
        qh = W.HANDLE()
        rc = gpu.pdh.PdhOpenQueryW(None, 0, ctypes.byref(qh))
        if rc:
            print("open rc=%x" % rc)
            return {}
        q = qh
        handles = []
        adds_failed = 0
        first_add_rc = 0
        for (pid, kind), n in pairs:
            h = W.HANDLE()
            rc = gpu.pdh.PdhAddCounterW(
                q, "\\GPU Engine(%s)\\Utilization Percentage" % n,
                0, ctypes.byref(h))
            if rc:
                adds_failed += 1
                first_add_rc = first_add_rc or rc
                continue             # a dead pid's instance can
            handles.append((pid, kind, h))   # refuse late; the
        if adds_failed:              # probe keeps the rest
            print("add: %d/%d refused, first rc=%x"
                  % (adds_failed, len(pairs), first_add_rc))
        if not handles:
            return {}
        rc = gpu.pdh.PdhCollectQueryData(q)
        if rc:
            print("collect1 rc=%x" % rc)
            return {}
        time.sleep(gpu.COLLECT_GAP_SEC)
        rc = gpu.pdh.PdhCollectQueryData(q)
        if rc:
            print("collect2 rc=%x" % rc)
            return {}
        # PDH format<->struct PAIRING, the actual documented law:
        #   PDH_FMT_DOUBLE (0x800)              -> PDH_DOUBLE_DATA
        #       {CStatus,Pad,Timestamp(8),Value}   = _FMTV16 here
        #   PDH_FMT_DOUBLE|PDH_FMT_NO_TIME     -> PDH_FORMAT_DATA
        #       {CStatus,Pad,Value}                = _FMTV here
        # gpu.py mixed them (0x800 into the 16-byte struct = the
        # function writes a timestamp over our Value and past the
        # struct). Get-Counter reads 1636 instances fine right now,
        # so the OS side is healthy and the pairing experiment below
        # decides the winner.
        totals = {}
        rcs = {}
        PAIRS = ((gpu.PDH_FMT_DOUBLE | 0x2000, gpu._FMTV),
                 (gpu.PDH_FMT_DOUBLE, gpu._FMTV16))
        fn = gpu.pdh.PdhGetFormattedCounterValue
        old_pin = fn.argtypes
        try:
            fn.argtypes = [W.HANDLE, W.DWORD, W.LPVOID, W.LPVOID]
            for fmt, struct in PAIRS:
                ok = 0
                nz = 0
                bad_rc = 0
                vals = []
                for pid, kind, h in handles:
                    f = struct()
                    vtype = W.DWORD()
                    rc = fn(h, fmt, ctypes.byref(vtype),
                            ctypes.byref(f))
                    if rc:
                        bad_rc = bad_rc or rc
                        continue
                    ok += 1
                    vals.append((pid, kind, f.Value))
                    if f.Value:
                        nz += 1
                print("pair fmt=%x struct=%s: %d/%d clean, %d "
                      "nonzero%s" % (fmt, struct.__name__, ok,
                                      len(handles), nz,
                                      "" if ok else
                                      " (first rc=%x)" % bad_rc))
                if ok and not totals:
                    for pid, kind, v in vals:
                        totals[(pid, kind)] = \
                            totals.get((pid, kind), 0.0) + v
                    winner = (fmt, struct.__name__)
            if ok:
                print("winner: fmt=%x struct=%s" % winner)
        finally:
            fn.argtypes = old_pin
        if rcs:
            print("read rc histogram: " + ", ".join(
                "%x x%d" % (k, v) for k, v in rcs.items()))
        return totals
    except Exception:
        return {}
    finally:
        if q is not None:
            try:
                gpu.pdh.PdhCloseQuery(q)
            except Exception:
                pass


def main():
    if gpu.pdh is None:
        print("pdh.dll unavailable")
        return 1
    fg = wm.foreground()
    mons = wm.monitors()
    print("foreground: %s on %s covers=%s"
          % ((fg or {}).get("proc"), (fg or {}).get("monitor"),
             gaming_watch.covers(fg, mons) if fg else False))
    for m in mons:
        print("monitor %s @%s" % (m["short"], m["rate"]))
    t0 = time.perf_counter()
    totals = sample()
    print("sample done (%.1f s), %d cells"
          % (time.perf_counter() - t0, len(totals)))
    names = proc_names()
    rows = sorted(((v, pid, kind) for (pid, kind), v in totals.items()
                   if round(v, 2) != 0.0), reverse=True)
    if not rows:
        print("NOTHING busy - run this while a video plays to see "
              "where hardware decode lands")
    for v, pid, kind in rows[:40]:
        tag = ("VIDEO" if kind in VIDEO_KINDS else
               "render" if gpu._is_render(kind) else "other")
        print("  pid %-7d %-14s %-15s %6.2f%%  %-6s %s"
              % (pid, names.get(pid, "?")[:14], kind, v, tag,
                 "<= FOREGROUND" if fg and pid == fg.get("pid")
                 else ""))
    video_busy = {(pid, kind) for v, pid, kind in rows
                  if kind in VIDEO_KINDS}
    print("verdict: video-family activity:",
          "YES - " + ", ".join(sorted({k for _, k in video_busy}))
          if video_busy else "none in this sample")
    return 0


if __name__ == "__main__":
    sys.exit(main())
