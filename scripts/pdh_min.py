"""minimal PDH GPU-Engine experiments, one per process invocation:

  python pdh_min.py <variant>

  scale3_pair     3 counters, collect pair 1.2 s (control shape)
  scale3_slow     3 counters, 3 collects over 3 s (late provider)
  scale400_slow   400 counters, 3 collects over 3 s
  scale400_pair   400 counters, 1.2 s pair (what gpu.py does today)

Reads every handle with BOTH format<->struct pairings and prints a
matrix. Answers the only two questions left: is 400 counters per
query the poison, or is data never arriving?"""
import ctypes
import os
import sys
from ctypes import wintypes as W

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
from panelboss import gpu  # noqa: E402

VARIANTS = {
    "scale3_pair": (3, (0.0, 1.2)),
    "scale3_slow": (3, (0.0, 1.5, 1.5)),
    "scale400_slow": (400, (0.0, 1.5, 1.5)),
    "scale400_pair": (400, (0.0, 1.2)),
}

fn = None


def read_all(handles):
    """Try both pairings; print a matrix line per pairing."""
    pins = [(gpu.PDH_FMT_DOUBLE | 0x2000, gpu._FMTV),
            (gpu.PDH_FMT_DOUBLE, gpu._FMTV16)]
    for fmt, struct in pins:
        ok = 0
        nz = 0
        first_rc = 0
        for h in handles:
            f = struct()
            vt = W.DWORD()
            rc = gpu.pdh.PdhGetFormattedCounterValue(
                h, fmt, ctypes.byref(vt), ctypes.byref(f))
            if rc:
                first_rc = first_rc or rc
                continue
            ok += 1
            nz += 1 if f.Value else 0
        print("  fmt=%x %s: ok=%d/%d nonzero=%d%s"
              % (fmt, struct.__name__, ok, len(handles), nz,
                 "" if ok else " first_rc=%x" % first_rc))


def run(variant):
    n, schedule = VARIANTS[variant]
    global fn
    fn = gpu.pdh.PdhGetFormattedCounterValue
    fn.argtypes = [W.HANDLE, W.DWORD, W.LPVOID, W.LPVOID]
    rc, names = gpu._enum()
    insts = [nme for nme in names if gpu._INST_RE.match(nme)][:n]
    print("%s: %d instances" % (variant, len(insts)))
    q = W.HANDLE()
    if gpu.pdh.PdhOpenQueryW(None, 0, ctypes.byref(q)):
        print("open failed")
        return
    hs = []
    for inst in insts:
        h = W.HANDLE()
        if gpu.pdh.PdhAddCounterW(
                q, "\\GPU Engine(%s)\\Utilization Percentage" % inst,
                0, ctypes.byref(h)):
            print("add failed")
            gpu.pdh.PdhCloseQuery(q)
            return
        hs.append(h)
    import time
    for gap in schedule:
        time.sleep(gap)
        rc = gpu.pdh.PdhCollectQueryData(q)
        print("  collect rc=%x" % rc)
    read_all(hs)
    gpu.pdh.PdhCloseQuery(q)


if __name__ == "__main__":
    run(sys.argv[1])
