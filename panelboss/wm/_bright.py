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

THE REFUSAL LAW, TWO HONEST HALVES (corrected mid-day 2026-10-14; the
owner's UAT proved the AOC dims through this door while the morning's
scratch probes NAK'd it repeatedly - the same fingers, one-shot, zero
retries, a second process fighting the app for handles on one flaky
I2C bus; the PROBE LAW in AUDIT-PUNCHLIST.md owns the correction):

* REFUSAL is the SEND: SetMonitorBrightness/SetVCPFeature FALSE after
  the full retry budget (0.3 s between tries; every failure class
  rides the budget - a spent budget is the only honest no), or the
  door never opening at all (NO_DOOR, the gray class). A refusal is a
  fact about THIS app's attempts, timestamped, not the firmware's soul.
* An accepted write whose readback never answers - or answers unmoved,
  or answers a courtesy - is UNVERIFIED-TRUST, never refusal. This
  desk has the reply-deaf class (the AOC's brightness; the IOC's
  power-read answering "on" through a fully-ACKed D6-off window is
  the accepts-and-lies class measured live at the power door,
  scripts/sdc_off_probe.py - whether the window was dark is the
  owner's pending eye-half, and the law holds either way: the app
  cannot resolve it, so it must not pretend to). The caller's status
  word says "(unverified)"; the preview is the human judge.
Panels DIVERGE here, re-measured today across these very three:
DISPLAY2 answers every brightness read; DISPLAY1 replies are selective
at best (KVM partial pass-through per the dossier); the old law
("readback unmoved = refused") lived by lying about live panels, and
its blackout-every-doubt fallback retires to the refusal half.
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
REFUSAL = ("the monitor will not take the write (DDC/CI send failed "
           "after the retry budget)")
NO_DOOR = "no DDC/CI door (physical handles never opened)"
# THE VCP DOOR (the off sub-mode rides it): 0xD6 per the owner's sheet.
# The 2026-10-14 probes (scripts/sdc_off_probe.py, the control panel)
# measured the door's manners: SetVCPFeature TRUE means the bus
# transaction ACKed - nothing more. The control panel ACKed D6=4
# (0x04) 4/5 with one transient 0xC0262582, and its own power read
# answered "on" (val=1) THROUGH the dark window: accepts-and-lies is
# real for power, on a directly attached panel, so the KVM never
# needed to explain it. The reply-honest class gets its retrial
# through this app's door, with retries (the morning verdict's zero-
# retry budget is the PROBE LAW's named contamination).
VCP_TRIES = 3               # the budget; a refusal after it is a fact
                            # about THIS app's attempts, timestamped
VCP_RETRY_SEC = 0.3         # the flaky I2C's measured demand
VCP_POWER = 0xD6
VCP_POWER_ON = 0x01         # 0x66 is the MCCS standard - this desk's
VCP_POWER_OFF = 0x04        # panels NAK it unsupported (measured);
                            # vendor-D6 is the power code that exists
SETTLE_SEC = 5.0            # THE SETTLE WINDOW (captain's door verdict,
                            # Oct 19): after any invalidate or import the
                            # WRITES stay silent this long - the desk
                            # moved, a write may take one more try; the
                            # READS ride ungated (measured clean all
                            # morning, incl. the deaf AOC leg)
_ARR_SLACK = 2              # the ghost-re-attach head (TOCTOU, verified
                            # Oct 19): count + 2 structs, so a monitor
                            # re-attaching between the count and the
                            # fetch overruns into slack, not the heap
BELT_STAGGER_SEC = 1.5      # the boot belt's spacing between row asks:
                            # a refused 'off' row is NEVER re-asked
                            # inside its own spell; any future re-ask
                            # rides vcp (settle-gated) and must re-stamp
                            # the rec['tried'] dated law
MAX_PATH = 260
SETTLE = ("the door is settling after a desk change - the write may "
          "take one more try")


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
dx.SetVCPFeature.argtypes = [ctypes.c_void_p, ctypes.c_ubyte,
                             wintypes.DWORD]
dx.SetVCPFeature.restype = ctypes.c_long                            # BOOL
dx.GetVCPFeatureAndVCPFeatureReply.argtypes = [
    ctypes.c_void_p, ctypes.c_ubyte, ctypes.POINTER(ctypes.c_ubyte),
    ctypes.c_void_p, ctypes.c_void_p]
dx.GetVCPFeatureAndVCPFeatureReply.restype = ctypes.c_long          # BOOL
dx.DestroyPhysicalMonitors.argtypes = [wintypes.UINT,
                                       ctypes.POINTER(PHYSICAL_MONITOR)]
dx.DestroyPhysicalMonitors.restype = ctypes.c_long                  # BOOL

_lock = threading.Lock()
_cache = {}           # gdi (lower case) -> (hmon, count, array)
_retired = []         # RETIRE-NOT-FREE (Oct 19): the (count, array)
                      # pairs the event thread FORGETS, never frees -
                      # they ride this list until process exit (the
                      # kernel reclaims), so a write thread mid-retry
                      # sleep can never meet a freed trampoline page
_settle_until = 0.0   # monotonic deadline: writes refuse until then
_settle_until = time.monotonic() + SETTLE_SEC   # THE IMPORT SEED: the
                                                # boot belt runs past
                                                # import+6 s, so the
                                                # seed never gates it


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
    # THE TOCTOU LAW (verified Oct 19): a KVM ghost may re-attach
    # between the count and the fetch; the array carries _ARR_SLACK
    # past the count, so its overrun lands in slack, not the heap -
    # and the API is told the ORIGINAL count, never the padded size
    arr = (PHYSICAL_MONITOR * (count.value + _ARR_SLACK))()
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


def _send(write, tries):
    """The retry door that EVERY DDC/CI write rides (the bus demanded
    it - measured): 0.3 s between tries, the full budget spent on any
    failure class, and the verdict reports the LAST answer. A refusal
    out of here is a fact about this loop's attempts, not the
    firmware's soul: the morning's one-shot scratch NAKs were the
    probing itself (PROBE LAW, AUDIT-PUNCHLIST, 2026-10-14).
    (ok, tries_used, last_error)."""
    err = 0
    for n in range(1, max(1, tries) + 1):
        k32.SetLastError(0)
        if write():
            return True, n, 0
        err = k32.GetLastError() & 0xFFFFFFFF
        if n < tries:
            time.sleep(VCP_RETRY_SEC)
    return False, tries, err


def set(gdi, pct):
    """One brightness write under the two honest halves (module
    header). Returns (trouble, verified): trouble "" = the write was
    SENT - verified True when the +0.5 s readback confirms the move,
    verified False in UNVERIFIED-TRUST (readback deaf or courtesy,
    the class this desk demonstrably has - never a refusal);
    REFUSAL = the send failed after the full budget; NO_DOOR = the
    handles never opened (the gray class). The caller owes the
    refusal half a degradation and a confession, and the unverified
    half an honest status word."""
    if time.monotonic() < _settle_until:   # the SETTLE WINDOW: the bus
        return REFUSAL, False              # is not touched during settle
    px = _phys(gdi)
    if px is None:
        return NO_DOOR, False
    h = px[2][0].hMonitor
    before = _read(px)
    if before is not None:
        want = max(before[1], min(before[2], int(pct)))
    else:
        want = max(0, min(100, int(pct)))   # no range to clamp by;
        # the write still rides - a read-refused door is not a
        # write-refused door (that lie is retired with the old law)
    sent, _n, err = _send(lambda: dx.SetMonitorBrightness(h, want),
                          VCP_TRIES)
    if not sent:
        invalidate(gdi)                    # stale-handle class: rebuild
        log.info("bright: %s %d%% send refused (error 0x%X, %d tries)",
                 gdi, want, err, _n)
        return REFUSAL, False
    if before is not None and want == before[0]:
        return "", True                    # already there: nothing owed
    time.sleep(CONFIRM_SLEEP_SEC)
    after = _read(px)
    verified = after is not None and after[0] == want
    if not verified:
        log.info("bright: %s ACKed %d%%, readback says %s - unverified "
                 "trust, not refusal (PROBE LAW)", gdi, want,
                 "nothing" if after is None else "%d%%" % after[0])
    return "", verified


def restore(gdi, pct):
    """The lift write: back to the ledger's pct (get refused at the
    leaving moment? hand back max, the packet's honest default). The
    same retry door as set() - the hand-back deserves the budget too.
    No refusal comes back: the truth is already in the engage-side
    ledger, and a hand-back that cannot land is the panel's answer."""
    if time.monotonic() < _settle_until:   # the SETTLE WINDOW: the bus
        log.info("bright: hand-back of %s%% to %s waits out the "                 # is not touched during settle;
                 "settle", pct, gdi)                                             # the shape it already returns
        return
    px = _phys(gdi)
    if px is None:
        return
    sent, _n, err = _send(
        lambda: dx.SetMonitorBrightness(px[2][0].hMonitor, int(pct)),
        VCP_TRIES)
    if not sent:
        log.info("bright: hand-back of %s%% to %s refused after the "
                 "budget (error 0x%X); the panel keeps its own answer",
                 pct, gdi, err)


def vcp(gdi, code, value, tries=VCP_TRIES):
    """One VCP write through the brightness door's CACHED HANDLES -
    one handle table, one bus, one law. (sent, why): TRUE from
    SetVCPFeature is the transaction's ACK, not a promise the panel
    obeyed (the control panel's power read answered "on" through a
    fully-ACKed D6-off window, scripts/sdc_off_probe.py - the
    readback half is what vcp_read asks); sent False is REFUSAL with
    its error and try-count, or NO_DOOR at a panel never reached.
    A refusal is timestamped by the caller as what it is: this app's
    spent budget, not the firmware's soul."""
    if time.monotonic() < _settle_until:   # the SETTLE WINDOW: the bus
        return False, SETTLE               # is not touched during settle
    px = _phys(gdi)
    if px is None:
        return False, NO_DOOR
    h = px[2][0].hMonitor
    sent, _n, err = _send(lambda: dx.SetVCPFeature(h, code, int(value)),
                          tries)
    if not sent:
        invalidate(gdi)          # a dead handle and a NAK look alike
        log.info("vcp: %s 0x%02X=%d refused after %d tries (last error "
                 "0x%X)", gdi, code, value, tries, err)
        return False, "%s (error 0x%X after %d tries)" % (REFUSAL, err,
                                                          tries)
    return True, ""


def vcp_read(gdi, code):
    """(answered, value): the honest readback of one VCP code. A NO
    here is UNVERIFIED territory, never a write-verdict (reply-deaf
    is a demonstrated class, PROBE LAW). All three out-pointers real:
    NULL pVCPFeature answers 0x57 from this OS (measured this session)
    - the morning's "D6 read is deaf" was that argument bug, not the
    panel. type/current/max per the probes' proven shape."""
    px = _phys(gdi)
    if px is None:
        return False, None
    mtype = ctypes.c_ubyte()
    val = wintypes.DWORD()
    mx = wintypes.DWORD()
    if not dx.GetVCPFeatureAndVCPFeatureReply(px[2][0].hMonitor, code,
                                              ctypes.byref(mtype),
                                              ctypes.byref(val),
                                              ctypes.byref(mx)):
        return False, None
    return True, int(val.value)


def reachable(gdi):
    """The gray law, one line and no folklore: gray ONLY panels this
    app never reached - physical handles that never opened. A panel
    answering any door proved its bus; the capability state machine
    (UNKNOWN selectable -> TRIED-IN-APP -> trusted / refused-after-N,
    timestamped) lives in the row's STATUS WORD, not in a pre-sentence
    (owner correction, PROBE LAW, 2026-10-14)."""
    return _phys(gdi) is not None


def invalidate(gdi=None):
    """Topology moved (WM_DISPLAYCHANGE) or a refusal proved the
    handles stale: drop the cache (this one, not every caller's).
    THE RETIRE-NOT-FREE law (captain's door verdict, Oct 19): dropping
    means FORGETTING, never freeing - the event thread must not free
    what a write thread may still hold (a retry-sleep of 0.3 s holds
    the pair; the freed trampoline page is the C000041D class). The
    popped pair rides _retired until process exit: the kernel
    reclaims it, and the driver's later calls answer clean refusals,
    not faults. Any invalidate also re-arms the SETTLE WINDOW - the
    desk just moved, so the writes stay silent for SETTLE_SEC."""
    global _settle_until
    with _lock:
        keys = [gdi.lower()] if gdi else list(_cache)
        for key in keys:
            px = _cache.pop(key, None)
            if px:
                _retired.append((px[1], px[2]))
        _settle_until = time.monotonic() + SETTLE_SEC
