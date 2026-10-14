"""Monitor brightness over DDC/CI - the HMONITOR-scoped dxva2 route.

PROBE LAW (measured on this desk, 2026-10-14, three struct-death rounds
to earn these lines - the education goes verbatim):

* PHYSICAL_MONITOR's real layout is {HMONITOR hMonitor; WCHAR
  szPhysicalMonitor[4 + MAX_PATH]} - there is NO LUID field. A
  MONITORINFOEXW-or-LUID guess inside the struct makes
  GetPhysicalMonitorsFromHMONITOR return FALSE (0) and the array read
  back as zero-filled garbage: the classic silent-ignorance trap that
  first pronounced this box's DDC/CI dead. It is not dead; it is
  exacting.
* EVERY function here returns BOOL: 0 = FALSE = failure/refusal,
  nonzero = TRUE. Reading the return as an HRESULT ("0 = S_OK")
  inverts the entire truth - a refusal reads as success and the
  garbage reads as support. No support-flag comes back from
  GetMonitorBrightness; capability lives in GetMonitorCapabilities
  alone (exported, unused here: the set/read refusal is the
  capability answer that matters).
* The system-wide GetPhysicalMonitors / GetNumberOfPhysicalMonitors /
  GetMonitorCurrentBrightness are NOT exported by this OS's
  dxva2.dll (GetProcAddress census, 2026-10-14). HMONITOR-scoped
  only: GetNumberOfPhysicalMonitorsFromHMONITOR -> count, then
  GetPhysicalMonitorsFromHMONITOR.
* WMI WmiMonitorBrightness: Not supported here (0x8004100c),
  WmiMonitorBasicModeFeatures: no rows. GetMonitorBrightness is the
  ONLY read path on this box; the packet's WMI read-fallback is dead
  lore, kept nowhere.
* The gdi -> HMONITOR map rides EnumDisplayMonitors + GetMonitorInfoW
  WITH a correct cbSize (the wm docstring's "error 87, never use it"
  was a struct-size bug, not an API truth - corrected there).

THE REFUSAL LAW: refused = SetMonitorBrightness FALSE  UNION  the
+0.5 s confirmation read failing  UNION  the readback unchanged when
the write should have moved it. Panels DIVERGE here, measured on
these very three: DISPLAY2 round-tripped 80 -> 90 -> 80 with the
readback following every write; DISPLAY3 answered Set(85) TRUE and
stayed 75 - it accepts brightness writes and never obeys them. A TRUE
return from such a panel is a courtesy, not a fact; only the readback
is. So a set that does not move the panel is a refusal, never silent:
the caller degrades that row to blackout and says so.
"""

import ctypes
import logging
import threading
import time
from ctypes import wintypes

log = logging.getLogger("wm.bright")

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32
dx = ctypes.windll.dxva2

CONFIRM_SLEEP_SEC = 0.5     # the measured settle: slow DDC/CI panels
                            # answer the readback late, not never
REFUSAL = "the monitor refuses brightness (DDC/CI)"

MAX_PATH = 260


class _MIEX(ctypes.Structure):        # the cbSize-exact twin (probe law)
    _fields_ = [("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", ctypes.c_wchar * 32)]


class PHYSICAL_MONITOR(ctypes.Structure):
    _fields_ = [("hMonitor", ctypes.c_void_p),
                ("szPhysicalMonitor", ctypes.c_wchar * (4 + MAX_PATH))]


u32.EnumDisplayMonitors.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_void_p, wintypes.LPARAM]
u32.EnumDisplayMonitors.restype = wintypes.BOOL
u32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MIEX)]
u32.GetMonitorInfoW.restype = wintypes.BOOL
dx.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
dx.GetNumberOfPhysicalMonitorsFromHMONITOR.restype = ctypes.c_long  # BOOL
dx.GetPhysicalMonitorsFromHMONITOR.argtypes = [
    ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(PHYSICAL_MONITOR)]
dx.GetPhysicalMonitorsFromHMONITOR.restype = ctypes.c_long          # BOOL
dx.GetMonitorBrightness.argtypes = [ctypes.c_void_p,
                                    ctypes.POINTER(wintypes.UINT),
                                    ctypes.POINTER(wintypes.UINT),
                                    ctypes.POINTER(wintypes.UINT)]
dx.GetMonitorBrightness.restype = ctypes.c_long                     # BOOL
dx.SetMonitorBrightness.argtypes = [ctypes.c_void_p, wintypes.UINT]
dx.SetMonitorBrightness.restype = ctypes.c_long                     # BOOL
dx.DestroyPhysicalMonitors.argtypes = [wintypes.UINT,
                                       ctypes.POINTER(PHYSICAL_MONITOR)]
dx.DestroyPhysicalMonitors.restype = ctypes.c_long                  # BOOL

_lock = threading.Lock()
_cache = {}           # gdi (lower case) -> (hmon, count, array)


def _hmon_for(gdi):
    """The logical display's HMONITOR, matched on the exact device
    name the monitor enum already hands us (\\.\DISPLAYn)."""
    want = str(gdi).lower()
    found = []

    def cb(hmon, _dc, _rc, _l):
        mi = _MIEX()
        mi.cbSize = ctypes.sizeof(_MIEX)      # the probe law, applied
        if u32.GetMonitorInfoW(hmon, ctypes.byref(mi)) \
                and str(mi.szDevice).lower() == want:
            found.append(hmon)
        return True

    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p,
                               ctypes.c_void_p,
                               ctypes.POINTER(wintypes.RECT),
                               wintypes.LPARAM)
    keep = proto(cb)
    u32.EnumDisplayMonitors(None, None, keep, 0)
    return found[0] if found else None


def _phys(gdi):
    """The cached physical handles behind one gdi, enumerated once.
    None = the enumerate fail (a refusal under the law)."""
    key = str(gdi).lower()
    with _lock:
        if key in _cache:
            return _cache[key]
    hmon = _hmon_for(gdi)
    if hmon is None:
        return None
    count = wintypes.DWORD(0)
    if not dx.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon,
                                                      ctypes.byref(count)) \
            or count.value == 0:
        return None
    arr = (PHYSICAL_MONITOR * count.value)()
    if not dx.GetPhysicalMonitorsFromHMONITOR(hmon, count.value, arr):
        return None
    # the array must outlive this call: the handles reference its
    # description buffer, so the cache owns it until invalidate()
    with _lock:
        _cache[key] = (hmon, count.value, arr)
    return (hmon, count.value, arr)


def _read(px):
    lo, cur, hi = (wintypes.UINT(), wintypes.UINT(), wintypes.UINT())
    if not dx.GetMonitorBrightness(px[2][0].hMonitor, ctypes.byref(lo),
                                   ctypes.byref(cur), ctypes.byref(hi)):
        return None
    return (int(cur.value), int(lo.value), int(hi.value))


def get(gdi):
    """Best-effort current brightness percent (None = refused class).
    The honest-restore ledger asks with this BEFORE any set."""
    px = _phys(gdi)
    if px is None:
        return None
    seen = _read(px)
    return seen[0] if seen else None


def set(gdi, pct):
    """One brightness write under the refusal law. '' = the panel
    MOVED (readback-confirmed); REFUSAL = enumerate fail, Set FALSE,
    or the +0.5 s readback unmoved - never silent, the caller owes
    that row a blackout degradation and a confession."""
    px = _phys(gdi)
    if px is None:
        return REFUSAL
    before = _read(px)
    if before is None:
        return REFUSAL
    want = max(before[1], min(before[2], int(pct)))
    if not dx.SetMonitorBrightness(px[2][0].hMonitor, want):
        invalidate(gdi)
        return REFUSAL
    if want == before[0]:                 # already there: no movement
        return ""                         # owed, nothing to confirm
    time.sleep(CONFIRM_SLEEP_SEC)
    after = _read(px)
    if after is None or (after[0] != want and after[0] == before[0]):
        invalidate(gdi)                   # stale-handle class: rebuild
        log.info("bright: %s accepted %d%% and stayed %d%% - a courtesy "
                 "answer, not a fact", gdi, want, before[0])
        return REFUSAL
    return ""


def restore(gdi, pct):
    """The lift write: back to the ledger's pct (get refused at the
    leaving moment? hand back max, the packet's honest default). No
    refusal return - the handback rides once and the truth is already
    in the engage-side ledger."""
    px = _phys(gdi)
    if px is None:
        return
    dx.SetMonitorBrightness(px[2][0].hMonitor, int(pct))


def invalidate(gdi=None):
    """Topology moved (WM_DISPLAYCHANGE) or a refusal proved the
    handles stale: drop the cache (this one, not every caller's)."""
    with _lock:
        keys = [gdi.lower()] if gdi else list(_cache)
        for key in keys:
            px = _cache.pop(key, None)
            if px:
                dx.DestroyPhysicalMonitors(px[1], px[2])
