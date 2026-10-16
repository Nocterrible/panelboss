# One-shot PDH shape probe: old pin vs the spec's repaired wide route.
# Prints: instance count, open rc, per-add rc histogram, collect rc,
# read matrix (fmt x struct) with nonzero count.
import ctypes
import os
import sys
import time
from ctypes import wintypes as W

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OBJ = "GPU Engine"


def instances(limit=8):
    csz, isz = W.DWORD(0), W.DWORD(0)
    pdh = ctypes.WinDLL("pdh.dll")
    pdh.PdhEnumObjectItemsW.argtypes = [W.LPCWSTR, W.LPCWSTR, W.LPCWSTR,
                                        W.LPWSTR, ctypes.POINTER(W.DWORD),
                                        W.LPWSTR, ctypes.POINTER(W.DWORD),
                                        W.DWORD, W.DWORD]
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
    return names[:limit], len(names)


def run(shape, limit=8):
    names, total = instances(limit)
    pdh = ctypes.WinDLL("pdh.dll")
    q, rc_open = None, 0
    handles = []
    if shape == "old":
        # the module's Oct-13 pin, verbatim
        pdh.PdhOpenQueryW.argtypes = [W.LPCWSTR, W.DWORD,
                                      ctypes.POINTER(W.HANDLE)]
        pdh.PdhAddEnglishCounterW.argtypes = [W.HANDLE, W.LPCWSTR, W.DWORD,
                                              ctypes.POINTER(W.HANDLE)]
        pdh.PdhCollectQueryData.argtypes = [W.HANDLE]
        pdh.PdhGetFormattedCounterValue.restype = W.DWORD
        pdh.PdhGetFormattedCounterValue.argtypes = [
            W.HANDLE, W.DWORD, ctypes.POINTER(W.DWORD), W.LPVOID]
        pdh.PdhCloseQuery.argtypes = [W.HANDLE]
        hq = W.HANDLE()
        rc_open = pdh.PdhOpenQueryW(None, 0, ctypes.byref(hq))
        q = hq
        for n in names:
            h = W.HANDLE()
            rc = pdh.PdhAddEnglishCounterW(q, "\\GPU Engine(%s)\\Utilization "
                                            "Percentage" % n, 0,
                                           ctypes.byref(h))
            print("  old add rc=0x%08x path=%s" % (rc & 0xFFFFFFFF,
                                                   n[:40]))
            if not rc:
                handles.append(h)
    else:
        # the spec's repaired shape: wide args, c_long handles, c_long rcs
        pdh.PdhOpenQueryW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong,
                                      ctypes.POINTER(ctypes.c_long)]
        pdh.PdhOpenQueryW.restype = ctypes.c_long
        pdh.PdhAddEnglishCounterW.argtypes = [ctypes.c_void_p,
                                              ctypes.c_wchar_p,
                                              ctypes.c_void_p,
                                              ctypes.POINTER(ctypes.c_long)]
        pdh.PdhAddEnglishCounterW.restype = ctypes.c_long
        pdh.PdhCollectQueryData.argtypes = [ctypes.c_long]
        pdh.PdhCollectQueryData.restype = ctypes.c_long
        pdh.PdhGetFormattedCounterValue.restype = ctypes.c_long
        pdh.PdhGetFormattedCounterValue.argtypes = [
            ctypes.c_long, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
            ctypes.c_void_p]
        pdh.PdhCloseQuery.argtypes = [ctypes.c_long]
        pdh.PdhCloseQuery.restype = ctypes.c_long
        hq = ctypes.c_long()
        rc_open = pdh.PdhOpenQueryW(None, ctypes.c_ulong(0),
                                    ctypes.byref(hq))
        q = hq
        print("  new: total instances enumerated %d, using %d"
              % (total, len(names)))
        rcs = {}
        for n in names:
            h = ctypes.c_long()
            rc = pdh.PdhAddEnglishCounterW(hq.value, "\\GPU Engine(%s)\\Utilization "
                                            "Percentage" % n, None,
                                           ctypes.byref(h))
            rcs[rc & 0xFFFFFFFF] = rcs.get(rc & 0xFFFFFFFF, 0) + 1
            if not rc:
                handles.append(h)
        print("  new add rc histogram: %s" % {
            ("0x%08x" % k): v for k, v in sorted(rcs.items())})
    if not q:
        print("  open rc=0x%08x" % (rc_open & 0xFFFFFFFF))
        return
    rc1 = pdh.PdhCollectQueryData(q)
    time.sleep(1.2)
    rc2 = pdh.PdhCollectQueryData(q)
    print("  collect rc1=0x%08x rc2=0x%08x handles=%d"
          % (rc1 & 0xFFFFFFFF, rc2 & 0xFFFFFFFF, len(handles)))

    class FMTV(ctypes.Structure):
        _fields_ = [("CStatus", W.DWORD), ("Pad", W.DWORD),
                    ("Value", ctypes.c_double)]

    class FMTV16(ctypes.Structure):
        _fields_ = [("CStatus", W.DWORD), ("Pad", W.DWORD),
                    ("Timestamp", ctypes.c_ulonglong),
                    ("Value", ctypes.c_double)]

    for fmt, struct in ((0x00000800, FMTV), (0x00000800 | 0x2000, FMTV16),
                        (0x00000800, FMTV16), (0x00000800 | 0x2000, FMTV)):
        ok = nz = 0
        bad = 0
        vals = []
        for h in handles:
            f = struct()
            vt = W.DWORD()
            rc = pdh.PdhGetFormattedCounterValue(h, fmt, ctypes.byref(vt),
                                                 ctypes.byref(f))
            if rc:
                bad = bad or rc
                continue
            ok += 1
            vals.append(f.Value)
            nz += 1 if f.Value else 0
        print("  read fmt=0x%08x %s: ok=%d/%d nonzero=%d%s max=%.3f"
              % (fmt, struct.__name__, ok, len(handles), nz,
                 "" if ok else " first_rc=0x%08x" % (bad & 0xFFFFFFFF),
                 max(vals) if vals else 0.0))
    pdh.PdhCloseQuery(q)


if __name__ == "__main__":
    print("=== OLD pin (module's Oct-13 shape) ===")
    run("old")
    print("=== NEW pin (spec's repaired wide route) ===")
    run("new")
    print("PROBE DONE")
