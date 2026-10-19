"""THE DDC/CI DOOR (captain's verdict ses_eab74fb30ffesL9esYLWpt8ZcG,
Oct 19): the cross-thread handle free that killed the app - invalidate()
freed what a write thread held mid-retry-sleep (C000041D, the ctypes
trampoline page). The door now FORGETS, never frees, stays silent for
SETTLE_SEC after any desk change, and sizes its array past the
ghost-re-attach TOCTOU. Fake dx/u32/k32 (the seams are module attrs);
time is faked too - the gate reads _bright.time.monotonic, and no real
second ever passes in this suite.
Run from repo root:
.venv\\Scripts\\python.exe scripts\\bright_door_test.py
SIZE LAW note (190-odd lines, under the ~300 gate): the fake kernel,
the fake clock and the three pins are ONE world - splitting the file
would clone the world, not sell a seam.
"""
import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panelboss.wm import _bright            # noqa: E402
from panelboss.wm._bright import _MIEX      # noqa: E402
from ctypes import wintypes                # noqa: E402

GDI = r"\\.\DISPLAY1"     # the caller's gdi is the slot name
                            # (DISPLAY_DEVICEW.DeviceName), per
                            # _monitors.py:71 - _bright lowercases


class FakeTime:
    """The clock seam: the door's SETTLE gate reads
    _bright.time.monotonic; advancing NOW is the whole test lever."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, sec):
        self.sleeps.append(sec)


class Fake:
    """The fake-kernel seam: _bright reads dx/u32/k32 as ATTRIBUTES
    (dx.SetVCPFeature, u32.EnumDisplayMonitors), so the fakes are
    namespaces, not dicts."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def fake_world():
    """The fake kernel: every door answer recorded, NO door ever freed."""
    rec = {"destroy": 0, "setvcp": [], "counts": [], "arrays": [],
           "ghost": 1, "last_count": None}

    def setvcp(h, code, value):
        rec["setvcp"].append((h, code, value))
        return 1

    def no_of_phys(h, count):
        rec["counts"].append(count)
        # count arrives byref()-ed (a CArgObject): cast to write
        p = ctypes.cast(count, ctypes.POINTER(wintypes.DWORD))
        p.contents.value = 1
        rec["last_count"] = 1
        return 1

    def phys(h, n, arr):
        rec["arrays"].append(arr)
        arr[0].hMonitor = ctypes.c_void_p(0x1)
        if rec["ghost"]:                        # the ghost re-attach:
            rec["ghost"] -= 1                   # one MORE struct than
            arr[n].hMonitor = ctypes.c_void_p(0x2)   # the count promised
        return 1

    def destroy(n, arr):                        # the FATAL call: it must
        rec["destroy"] += 1                     # never happen again
        return 1

    def enum(_mon, _dc, cb, _l):
        for i in (1, 2, 3):            # the fake desk: three legs
            cb(0xA00 + i, None, None, 0)
        return 1

    def info(h, mi):
        # mi is a byref() CArgObject: cast back to the struct to write
        ctypes.cast(mi, ctypes.POINTER(_MIEX)).contents.szDevice = \
            "\\\\.\\DISPLAY%d" % (h - 0xA00)
        return 1

    t = FakeTime()
    saved = [(_bright, "dx", _bright.dx), (_bright, "u32", _bright.u32),
             (_bright, "k32", _bright.k32), (_bright, "time", _bright.time),
             (_bright, "_retired", list(_bright._retired)),
             (_bright, "_settle_until", _bright._settle_until)]
    _bright.dx = Fake(GetNumberOfPhysicalMonitorsFromHMONITOR=no_of_phys,
                      GetPhysicalMonitorsFromHMONITOR=phys,
                      SetVCPFeature=setvcp,
                      DestroyPhysicalMonitors=destroy)
    _bright.u32 = Fake(EnumDisplayMonitors=enum,
                       GetMonitorInfoW=info)
    _bright.k32 = Fake(SetLastError=lambda e: 0, GetLastError=lambda: 0)
    _bright.time = t
    return rec, t, saved


def restore(saved):
    for obj, name, old in saved:
        setattr(obj, name, old)


def fresh(rec, t):
    """One clean world per pin: the desk cache and the retire list
    start empty, the clock at zero."""
    _bright._cache.clear()
    _bright._retired[:] = []
    t.now = 0.0
    t.sleeps = []


def test_settle_window():
    rec, t, saved = fake_world()
    try:
        t.now = 10.0                      # the import seed (0..5) is long
        _bright.invalidate()              # over; the invalidate re-arms
        assert _bright._settle_until == 15.0, _bright._settle_until
        sent, why = _bright.vcp(GDI, _bright.VCP_POWER, 4)
        assert (sent, why) == (False, _bright.SETTLE), (sent, why)
        assert rec["setvcp"] == [], "the bus is NOT touched in settle"
        t.now = 16.0                      # past the window: the normal
        sent, why = _bright.vcp(GDI, _bright.VCP_POWER, 4)      # _send
        assert sent is True and why == "", (sent, why)          # budget
        assert len(rec["setvcp"]) == 1 and t.sleeps == [], rec["setvcp"]
        print("ok - settle window: a clean settling refusal, zero bus "
              "traffic, the write lands once the desk stops moving")
    finally:
        restore(saved)


def test_retire_not_free():
    rec, t, saved = fake_world()
    fresh(rec, t)
    try:
        t.now = 10.0
        for gdi in (r"\\.\DISPLAY1", r"\\.\DISPLAY2",
                    r"\\.\DISPLAY3"):
            assert _bright.reachable(gdi)          # the desk's three legs
        _bright.invalidate(GDI)
        assert GDI.lower() not in _bright._cache \
            and len(_bright._cache) == 2, \
            "the gdi arg drops JUST that row, never the desk"
        _bright.invalidate(r"\\.\DISPLAY2")
        _bright.invalidate()
        assert len(_bright._retired) == 3, len(_bright._retired)
        assert all(len(e) == 2 and isinstance(e[0], int)
                   for e in _bright._retired), _bright._retired
        assert rec["destroy"] == 0, "RETIRED, never destroyed"
        print("ok - retire-not-free: three invalidates ride _retired "
              "(arg pops that row, None pops all), DestroyPhysicalMonitors "
              "never called")
    finally:
        restore(saved)


def test_arr_slack():
    rec, t, saved = fake_world()
    fresh(rec, t)
    try:
        t.now = 10.0
        px = _bright._phys(GDI)
        assert px is not None, "the door must open on the fakes"
        arr = px[2]
        assert arr._length_ == rec["last_count"] \
            + _bright._ARR_SLACK, "the array carries the slack"
        assert rec["ghost"] == 0, "the ghost wrote into the fetch"
        assert arr[1].hMonitor == 0x2, \
            "the overrun landed in slack, not the heap"
        print("ok - arr slack: a count+1 ghost re-attach writes the extra "
              "slot clean (count+2 allocated, the original count sent)")
    finally:
        restore(saved)


def main():
    test_settle_window()
    test_retire_not_free()
    test_arr_slack()
    print("BRIGHT DOOR TESTS OK")


if __name__ == "__main__":
    main()
