# Isolation probe: which exact call fails, with the FULL instance names.
#  (a) the module's own video_busy() as-is (its old pin)
#  (b) a fresh query using PdhAddCounterW (ANSI/localized) instead of
#      PdhAddEnglishCounterW, same instance names
#  (c) PdhAddEnglishCounterW with the full (untruncated) names
import ctypes
import os
import sys
import time
from ctypes import wintypes as W

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OBJ = "GPU Engine"
pdh = ctypes.WinDLL("pdh.dll")
pdh.PdhEnumObjectItemsW.argtypes = [W.LPCWSTR, W.LPCWSTR, W.LPCWSTR,
                                    W.LPWSTR, ctypes.POINTER(W.DWORD),
                                    W.LPWSTR, ctypes.POINTER(W.DWORD),
                                    W.DWORD, W.DWORD]


def instances(limit=12):
    csz, isz = W.DWORD(0), W.DWORD(0)
    pdh.PdhEnumObjectItemsW(None, None, OBJ, None, ctypes.byref(csz),
                            None, ctypes.byref(isz), 0, 0)
    cb = ctypes.create_unicode_buffer(max(csz.value, 2))
    ib = ctypes.create_unicode_buffer(max(isz.value, 2))
    if pdh.PdhEnumObjectItemsW(None, None, OBJ, cb, ctypes.byref(csz),
                               ib, ctypes.byref(isz), 0, 0):
        return []
    names = [t for t in bytes(ib).decode("utf-16", "ignore").split("\0")
             if t]
    names.sort()
    return names[:limit]


# the module's own reader, as-is
from panelboss.wm import _videostats as vs
print("=== (a) module's own video_busy() (old pin) ===")
print("  video_busy() ->", vs.video_busy())


class FMTV(ctypes.Structure):
    _fields_ = [("CStatus", W.DWORD), ("Pad", W.DWORD),
                ("Value", ctypes.c_double)]


def read_total(handles, fmt=0x00000800):
    total = 0.0
    ok = 0
    bad = 0
    for h in handles:
        f = FMTV()
        vt = W.DWORD()
        rc = pdh.PdhGetFormattedCounterValue(h, fmt, ctypes.byref(vt),
                                             ctypes.byref(f))
        if rc:
            bad = bad or rc
            continue
        ok += 1
        total += f.Value
    return total, ok, bad


for kind, names in (("ANSI PdhAddCounterW", instances(12)),
                    ("EN PdhAddEnglishCounterW", instances(12))):
    print("=== (%s) on %d FULL instances ===" % (kind, len(names)))
    hq = W.HANDLE()
    rc_open = pdh.PdhOpenQueryW(None, 0, ctypes.byref(hq))
    print("  open rc=0x%08x" % (rc_open & 0xFFFFFFFF))
    handles = []
    rcs = {}
    for n in names:
        h = W.HANDLE()
        if kind.startswith("ANSI"):
            rc = pdh.PdhAddCounterW(hq, "\\GPU Engine(%s)\\Utilization "
                                      "Percentage" % n, 0, ctypes.byref(h))
        else:
            rc = pdh.PdhAddEnglishCounterW(hq, "\\GPU Engine(%s)\\Utilization "
                                              "Percentage" % n, 0,
                                           ctypes.byref(h))
        rcs[rc & 0xFFFFFFFF] = rcs.get(rc & 0xFFFFFFFF, 0) + 1
        if not rc:
            handles.append((n, h))
        print("  add rc=0x%08x %s" % (rc & 0xFFFFFFFF, n))
    print("  add rc histogram: %s" % {("0x%08x" % k): v
                                      for k, v in sorted(rcs.items())})
    if not handles:
        pdh.PdhCloseQuery(hq)
        continue
    rc1 = pdh.PdhCollectQueryData(hq)
    time.sleep(1.2)
    rc2 = pdh.PdhCollectQueryData(hq)
    print("  collect rc1=0x%08x rc2=0x%08x handles=%d"
          % (rc1 & 0xFFFFFFFF, rc2 & 0xFFFFFFFF, len(handles)))
    hs = [h for _, h in handles]
    total, ok, bad = read_total(hs)
    print("  read FMTV: ok=%d/%d total=%.3f%s"
          % (ok, len(hs), total,
             "" if ok else " first_rc=0x%08x" % (bad & 0xFFFFFFFF)))
    pdh.PdhCloseQuery(hq)
print("PROBE DONE")
