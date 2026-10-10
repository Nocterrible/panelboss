"""Probe for panelboss.gpu: exercise usage() twice (each call builds a
fresh PDH query), print per-call timing (total wall time and setup
overhead = wall minus the collect-gap sleep), the top rendering-GPU
pids, the usability verdict, and a force-fail test (patched
PdhOpenQueryW -> usage() must return {}).
psutil is used for process names if importable; otherwise a stdlib
toolhelp snapshot (no new deps).
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes as W

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))

from panelboss import gpu
from panelboss.gpu import pdh

try:
    import psutil
    def _name(pid):
        try:
            return psutil.Process(pid).name()
        except Exception:
            return "?"
except ImportError:
    class _PE(ctypes.Structure):
        _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD),
                    ("th32ProcessID", W.DWORD),
                    ("th32DefaultHeapID", ctypes.POINTER(W.BYTE)),
                    ("th32ModuleID", W.DWORD), ("cntThreads", W.DWORD),
                    ("th32ParentProcessID", W.DWORD), ("PriClassBase", W.LONG),
                    ("dwFlags", W.DWORD),
                    ("szExeFile", 260 * ctypes.c_char)]
    _k32 = ctypes.WinDLL("kernel32")
    _k32.CreateToolhelp32Snapshot.restype = W.HANDLE
    _k32.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
    _k32.Process32FirstW.argtypes = [W.HANDLE, ctypes.POINTER(_PE)]
    _k32.Process32NextW.argtypes = [W.HANDLE, ctypes.POINTER(_PE)]
    _SNAP = {}
    h = _k32.CreateToolhelp32Snapshot(0x2, 0)
    _pe = _PE()
    _pe.dwSize = ctypes.sizeof(_PE)
    if h and _k32.Process32FirstW(h, ctypes.byref(_pe)):
        while True:
            _SNAP[_pe.th32ProcessID] = _pe.szExeFile.decode("mbcs", "replace")
            if not _k32.Process32NextW(h, ctypes.byref(_pe)):
                break
    def _name(pid):
        return _SNAP.get(pid, "?")

def main():
    if pdh is None:
        print("pdh.dll unavailable")
        return
    rc, insts = gpu._enum()
    t0 = time.perf_counter()
    u1 = gpu.usage()
    wall1 = time.perf_counter() - t0
    t0 = time.perf_counter()
    u2 = gpu.usage()
    wall2 = time.perf_counter() - t0
    print("enum rc=%x instances=%d" % (rc & 0xFFFFFFFF, len(insts)))
    print("call1 pids=%d wall=%.3fs setup=%.3fs" %
          (len(u1), wall1, wall1 - gpu.COLLECT_GAP_SEC))
    print("call2 pids=%d wall=%.3fs setup=%.3fs" %
          (len(u2), wall2, wall2 - gpu.COLLECT_GAP_SEC))
    rows = sorted(u2.items(), key=lambda kv: kv[1], reverse=True)[:12]
    print("top rendering-GPU processes (pid  name  percent):")
    for pid, p in rows:
        print("%8d  %-22s  %7.1f" % (pid, _name(pid)[:22], p))
    print("GPU counters usable: " + ("YES" if insts else "NO"))
    # Force-fail: with a fresh build per call, a failing PdhOpenQueryW
    # makes usage() return {}; after restore, a fresh build works again.
    orig = pdh.PdhOpenQueryW
    pdh.PdhOpenQueryW = lambda *a: 1
    try:
        bad = gpu.usage()
        assert bad == {}, "force-fail: expected {}, got %r" % (bad,)
    finally:
        pdh.PdhOpenQueryW = orig
    assert isinstance(gpu.usage(), dict), "recovery must return a dict"
    print("force-fail test: OK")

if __name__ == "__main__":
    main()
