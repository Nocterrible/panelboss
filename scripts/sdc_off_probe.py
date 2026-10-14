"""SCRATCH PROBE (not a suite; not in run_all) - the AOC off-ladder
experiments under the KVM amendment (owner redirect, 2026-10-14,
target-corrected same day): the CONTROL panel is the directly-attached
IOC912B (\\.\DISPLAY2) - the very panel whose brightness door
round-tripped exactly this morning (cur=80, set 90 TRUE, read 90,
restore TRUE, final 80), so a demonstrated two-way channel is being
asked for power directly. The AOC (U2790B, \\.\DISPLAY1) sits behind
the KVM: it gets the same leg only after the control runs clean, so
divergent outcomes convict the switch, not the wire. The AW2725Q row
is OUT OF THIS PROBE today - its EDID stamp (DEL) and friendly name
disagree and only the owner's word pins identities (dossier line);
the IOC's friendly (GA27W1Q) is the marketing-string artifact the
profiles code already distrusts, so every join here is the gdi
SOURCE PATH, never a name.

Legs (each its own invocation - the owner's eyes report between them):

    python scripts/sdc_off_probe.py vcp DISPLAY2   # leg 1/3: D6 direct,
        # 5 OFF writes at 400 ms (ddcutil's lag forgiveness), D6
        # read-backs at +1.5/+2.5 s, 3 ON writes, brightness re-read.
    python scripts/sdc_off_probe.py sdc DISPLAY2   # leg 2: SetDisplayConfig
        # path-set minus the target's paths, SDC_APPLY|SDC_USE_SUPPLIED
        # and NO ALLOW_CHANGES (that flag lets Windows re-add the path),
        # hold ~6 s, restore from saved arrays, desk before/mid/after.

Every leg prints WATCH THE <panel> and pauses 2 s before it moves.
CODE evidence is what this prints; EYE evidence is the owner's.

The DisplayConfig ride is the APP's own: _hdr.py's size-asserted
structs (DC_PATH=72, DC_MODE=64) and its QDC value. CORRECTION,
mine, recorded by the probe law (AUDIT-PUNCHLIST): the first pass
passed QDC flag 0x1 and called the resulting 0x57 "the 24H2
regression" - false. 0x1 is not a valid flag; the app ships
ONLY_ACTIVE = 0x2 and runs this API green in-process. Set-side
manners remain unproven until leg 2 runs. gle is only meaningful
after SetLastError(0), which every probe call now does.
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panelboss import wm                                        # noqa: E402
from panelboss.wm import _bright, _hdr                          # noqa: E402

u32 = _hdr.u32                        # the app's user32, query argtypes set
k32 = ctypes.WinDLL("kernel32")
QDC_ALL = 0                           # no flag = the all-pairs view
QDC_ACTIVE = _hdr.QDC_ONLY_ACTIVE_PATHS   # 0x2, the app's proven value
SDC_APPLY = 0x00000001
SDC_USE_SUPPLIED = 0x00000002
u32.SetDisplayConfig.argtypes = [wintypes.UINT, ctypes.POINTER(_hdr.DC_PATH),
                                 wintypes.UINT, ctypes.POINTER(_hdr.DC_MODE),
                                 wintypes.UINT]
u32.SetDisplayConfig.restype = ctypes.c_long


def gle0():
    k32.SetLastError(0)


def desk(tag):
    rows = [(m.get("short"), m.get("gdi")) for m in wm.monitors()]
    print("desk[%s]: %d rows %s" % (tag, len(rows), rows))
    return len(rows)


def row_for(gdi_part):
    """The desk row whose gdi slot ends with DISPLAYn - the ONLY
    identity join this probe trusts (names lie, per the dossier)."""
    for m in wm.monitors():
        if gdi_part in str(m.get("gdi", "")).upper():
            return m
    return None


def src_of(psrc):
    sn = _hdr.DC_SOURCE_NAME()
    sn.header.type, sn.header.size = _hdr.DCI_GET_SOURCE_NAME, \
        ctypes.sizeof(sn)
    sn.header.adapter, sn.header.id = psrc.adapter, psrc.id
    if u32.DisplayConfigGetDeviceInfo(ctypes.byref(sn.header)):
        return "?"
    return sn.name


def watch(label, seconds):
    print("WATCH THE %s - leg starts in 2 s, effect window %d s"
          % (label, seconds), flush=True)
    time.sleep(2)


# ---------------------------------------------------------- legs 1 and 3: VCP
def vcp_leg(gdi_part, label):
    row = row_for(gdi_part)
    if row is None:
        print("no desk row for %r - desk moved; leg skipped" % gdi_part)
        return
    gdi = row["gdi"]
    print("target row: %r gdi=%r (label: %s)"
          % (row.get("short"), gdi, label))
    px = _bright._phys(gdi)
    if px is None:
        print("VCP LEG: _phys None - no physical handle for this gdi; "
              "never-reached class (gray, per the correction)")
        return
    hp = px[2][0].hMonitor
    dx = ctypes.WinDLL("dxva2", use_last_error=True)
    dx.GetMonitorBrightness.argtypes = [ctypes.c_void_p] + [
        ctypes.POINTER(wintypes.UINT)] * 3
    dx.GetMonitorBrightness.restype = wintypes.BOOL
    dx.SetVCPFeature.argtypes = [ctypes.c_void_p, ctypes.c_ubyte,
                                 wintypes.DWORD]
    dx.SetVCPFeature.restype = wintypes.BOOL
    dx.GetVCPFeatureAndVCPFeatureReply.argtypes = [
        ctypes.c_void_p, ctypes.c_ubyte, ctypes.POINTER(ctypes.c_ubyte),
        ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    dx.GetVCPFeatureAndVCPFeatureReply.restype = wintypes.BOOL

    def b_read(tag):
        gle0()
        lo, cur, hi = (wintypes.UINT(), wintypes.UINT(), wintypes.UINT())
        ok = dx.GetMonitorBrightness(hp, ctypes.byref(lo), ctypes.byref(cur),
                                     ctypes.byref(hi))
        print("%s: rc=%s gle=%d cur=%s lo=%s hi=%s"
              % (tag, bool(ok), ctypes.get_last_error(),
                 cur.value if ok else "-", lo.value if ok else "-",
                 hi.value if ok else "-"))
        return bool(ok), cur.value if ok else None

    def d6_read(tag, code=0xD6):
        gle0()
        typ = ctypes.c_ubyte()
        val = wintypes.DWORD()
        got = wintypes.DWORD()
        # ALL THREE out-pointers real: pVCPFeature=NULL gets a
        # 0x57 from this OS (measured, same probe session) - another
        # one-shot-probe artifact in the morning's "reply-deaf" lore.
        r = dx.GetVCPFeatureAndVCPFeatureReply(hp, code, ctypes.byref(typ),
                                               ctypes.byref(val),
                                               ctypes.byref(got))
        print("  VCP 0x%02X read (%s): rc=%s gle=0x%X type=%d val=%s max=%s"
              % (code, tag, bool(r), ctypes.get_last_error() & 0xFFFFFFFF,
                 typ.value, val.value if r else "-", got.value if r else "-"))

    def burst(code, value, n, tag):
        oks = []
        for i in range(n):
            gle0()
            r = dx.SetVCPFeature(hp, code, value)
            oks.append(bool(r))
            print("%s write %d/%d at +%.2fs: rc=%s gle=0x%X"
                  % (tag, i + 1, n, time.monotonic() - t0, bool(r),
                     ctypes.get_last_error() & 0xFFFFFFFF))
            time.sleep(0.4)                     # ddcutil's lag forgiveness
        return oks

    b_read("brightness read BEFORE")
    d6_read("before")
    d6_read("before", 0x66)
    watch(label, 6)
    t0 = time.monotonic()
    oks = burst(0xD6, 0x04, 5, "OFF(D6)")       # the dispatched code first
    time.sleep(1.1)                             # read-back lands at +1.5 s
    d6_read("after-off +1.5s")
    time.sleep(1.0)
    d6_read("after-off +2.5s")                  # a lagging reply gets a witness
    ons = burst(0xD6, 0x01, 3, "ON(D6)")
    time.sleep(1.1)
    d6_read("after-on +1.5s")
    print("--- the standard code gets its retrial in this same window ---")
    d6_read("pre-66", 0x66)
    oks66 = burst(0x66, 0x04, 5, "OFF(66)")     # MCCS power control
    time.sleep(1.5)
    d6_read("after-off66 +1.5s", 0x66)
    time.sleep(1.0)
    d6_read("after-off66 +2.5s", 0x66)
    ons66 = burst(0x66, 0x01, 3, "ON(66)")
    time.sleep(1.5)
    d6_read("after-on66", 0x66)
    b_read("brightness read AFTER")
    print("VERDICT(half): D6 OFF %d/5 ON %d/3 | 66 OFF %d/5 ON %d/3 - "
          "read lines carry the reply story; EYES decide the rest"
          % (sum(oks), sum(ons), sum(oks66), sum(ons66)))


# ------------------------------------------------------------- leg 2: SDC
def capture():
    """The documented dance on the APP's flag values and size-checked
    structs: GBS -> allocate -> Query. ALL_PAIRS (0) first, ONLY_ACTIVE
    (0x2) as fallback; every rc recorded so this build's manners stay
    EVIDENCE."""
    attempts = []
    for flags in (QDC_ALL, QDC_ACTIVE):
        n_p, n_m = wintypes.UINT(), wintypes.UINT()
        rc = u32.GetDisplayConfigBufferSizes(flags, ctypes.byref(n_p),
                                             ctypes.byref(n_m))
        attempts.append("GBS flags=%d -> 0x%X counts=%d/%d"
                        % (flags, rc & 0xFFFFFFFF, n_p.value, n_m.value))
        if rc or not n_p.value:
            continue
        paths = (_hdr.DC_PATH * n_p.value)()
        modes = (_hdr.DC_MODE * n_m.value)()
        rc = u32.QueryDisplayConfig(flags, ctypes.byref(n_p), paths,
                                    ctypes.byref(n_m), modes, None)
        attempts.append("Query flags=%d -> 0x%X got=%d/%d"
                        % (flags, rc & 0xFFFFFFFF, n_p.value, n_m.value))
        if rc or not n_p.value:
            continue
        return attempts, (flags, n_p.value, n_m.value,
                          bytes(bytearray(paths)), bytes(bytearray(modes)))
    return attempts, None


def sdc_leg(gdi_part, label):
    before = desk("before")
    attempts, data = capture()
    for a in attempts:
        print("  capture: " + a)
    if data is None:
        print("SDC LEG: no query shape worked - RUNG UNPROVEN (read step)")
        return
    flags, n_paths, n_modes, paths_b, modes_b = data
    src = (_hdr.DC_PATH * n_paths).from_buffer_copy(paths_b)
    want = None
    print("paths %d modes %d (join = gdi source path, per the dossier)"
          % (n_paths, n_modes))
    for i in range(n_paths):
        p = src[i]
        sname = str(src_of(p.src))
        hit = gdi_part in sname.upper()
        print("  path[%d] src=%r flags=0x%X%s"
              % (i, sname, p.flags, "  <== TARGET" if hit else ""))
        if hit and want is None:
            want = (p.tgt.adapter.low, p.tgt.adapter.high, p.tgt.id)
    if want is None:
        print("SDC LEG: no path carries the %r source - RUNG UNPROVEN "
              "for this panel" % gdi_part)
        return
    retracted = bytearray(paths_b)
    sz = ctypes.sizeof(_hdr.DC_PATH)
    zeroed = 0
    for i in range(n_paths):
        p = src[i]
        if ((p.tgt.adapter.low, p.tgt.adapter.high,
             p.tgt.id) == want and p.flags):
            retracted[i * sz + sz - 4:i * sz + sz] = b"\0\0\0\0"
            zeroed += 1
    print("retracting %d path(s) -> target %r" % (zeroed, want))
    watch(label, 6)
    t0 = time.monotonic()
    gle0()
    pth = (_hdr.DC_PATH * n_paths).from_buffer_copy(bytes(retracted))
    mod = (_hdr.DC_MODE * n_modes).from_buffer_copy(modes_b)
    rc = u32.SetDisplayConfig(n_paths, pth, n_modes, mod,
                              SDC_APPLY | SDC_USE_SUPPLIED)
    print("APPLY rc=0x%X gle=%d at +%.2fs"
          % (rc & 0xFFFFFFFF, ctypes.get_last_error(),
             time.monotonic() - t0))
    t_drop = None
    if rc == 0:
        while time.monotonic() - t0 < 6.0:
            time.sleep(0.5)
            if t_drop is None and desk("during") < before:
                t_drop = time.monotonic() - t0
    time.sleep(1.0)
    gle0()
    pth2 = (_hdr.DC_PATH * n_paths).from_buffer_copy(paths_b)
    rc2 = u32.SetDisplayConfig(n_paths, pth2, n_modes, mod,
                               SDC_APPLY | SDC_USE_SUPPLIED)
    t1 = time.monotonic()
    print("RESTORE rc=0x%X gle=%d at +%.2fs"
          % (rc2 & 0xFFFFFFFF, ctypes.get_last_error(), t1 - t0))
    t_back = None
    while time.monotonic() - t1 < 20.0:
        time.sleep(0.5)
        if desk("after") >= before:
            t_back = time.monotonic() - t1
            break
    print("VERDICT: drop=%s reappear=%s"
          % (("%.2fs" % t_drop) if t_drop else "NOT OBSERVED",
             ("%.2fs" % t_back) if t_back else "NOT within 20 s"))
    if rc2:
        print("S.O.S.: restore FAILED - panel may sit dark; Settings -> "
              "Detect or the physical button (undefeated).")


def main():
    args = sys.argv[1:]
    if len(args) < 2 or args[0] not in ("vcp", "sdc"):
        print(__doc__)
        return
    gdi = args[1].upper().replace("\\\\", "").replace("\\", "")
    part = "DISPLAY" + "".join(c for c in gdi if c.isdigit())
    label = {"DISPLAY2": "IOC912B (direct-attached control)",
             "DISPLAY1": "AOC2790 (KVM leg - provisional by law)"}.get(
        part, part)
    if args[0] == "vcp":
        vcp_leg(part, label)
    else:
        sdc_leg(part, label)


main()
