"""SCRATCH PROBE (sibling of sdc_off_probe.py, not in run_all) - the
DISCIPLINED RETRIAL of rung (b), the SetDisplayConfig path-set minus
the AOC. SIZE LAW: one experiment - a victim-checked retraction
ladder whose finally/restore discipline must read in one piece.

Two corrections ride this file:
  (i) the old probe's SDC constants were the topology BITS, not the
  verbs (SDC_APPLY=0x1, SDC_USE_SUPPLIED=0x2; winuser.h: 0x80 / 0x20.
  The old 0x1|0x2 = INTERNAL|CLONE with no verb - the illegal
  combination that answers 0x57 at entry, driver untouched);
  (ii) the shape that moves the RIGHT glass is PATH-MINUS (drop the
  target's paths from the supplied array), not zero-flags (keep the
  path, flags=0): zero-flags is accepted at every verb set tried
  but re-normalizes by the CCD's own taste and disconnected
  DELA283, the primary, twice. Measured; the dossier carries both.

OWNER STROBE LAW (mid-flight, 2026-10-14 evening - the desk had been
toggled ~30 times by six ladder runs): (1) EVERY shape VALIDATEs
first and a validate-refusal is the shape's whole evidence - no
apply ever follows a nonzero VALIDATE; (2) proven shapes are not
re-applied (as-is APPLY measured rc=0x0 four times, SANITY EXTEND
three - their validate twins run here instead, the glass stays
lit); (3) AT MOST ONE physical retraction cycle per session, on the
AOC - tonight's was spent in sdc2-off6.log/verify2 (PATH-MINUS save,
GHOST classification, clean restore); (4) persistence reads from
the reg.exe Connectivity delta (elevated - a medium token gets
Access-denied), not from another reboot; (5) after the one cycle,
flag-shape experiments are `check` mode: validate-only, zero
applies, desk-silent.

FLAG NOTES: SDC_ALLOW_PATH_ORDER_CHANGES (0x2000) answers 0x57 on
this 26220/NVIDIA stack paired with USE_SUPPLIED (measured under
both VALIDATE and APPLY) and with TOPOLOGY_SUPPLIED too - the
lineage combo is falsified as-is HERE; the working retraction verb
set is SDC_APPLY|SDC_USE_SUPPLIED|SDC_SAVE_TO_DATABASE|
SDC_ALLOW_CHANGES = 0x6A0 (sdc2-off6.log). SAVE_TO_DATABASE makes
the disconnect persist in the HKLM CCD store - the restore MUST
carry the same SAVE bit or the stored profile reboots the panel
dark (named footgun; this probe's restore carries it).

OWNER EVIDENCE (2026-10-14): Settings' Disconnect blacks the AOC
through the KVM - Windows stops driving the output, the panel falls
to standby on signal loss; "it doesn't care what's downstream of
the adapter". Windows refuses to disconnect the LAST active display
(single-screen desks are OS-guarded; the app inherits the tested
refuse->blackout path, no new code).

Safety: the app is RUNNING on the owner's desk (pid 168024). The
retraction restores in a finally; a desk that sat short gets 3
saved-array restores + a loud S.O.S. Identity law per the dossier:
joins are gdi slots + EDID model tokens, never friendly names; and
MID-WINDOW the GDI view can LIE (the KVM's emulated EDID ghosts a
detached slot as "AOC2790@DISPLAY3") - the CCD's own QDC(2) re-query
is the authoritative victim check, ccd_view() below.

    python scripts/sdc_off_probe2.py check   # validate table, 0 applies
    python scripts/sdc_off_probe2.py off     # one physical cycle only
"""
import ctypes
import os
import re
import subprocess
import sys
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panelboss import wm                                        # noqa: E402
from panelboss.wm import _hdr                                   # noqa: E402

k32 = ctypes.WinDLL("kernel32")
u32 = _hdr.u32
QDC_ALL = 0x00000001
QDC_ACTIVE = 0x00000002     # _hdr.QDC_ONLY_ACTIVE_PATHS, the app's green
SDC_TOPO_EXTEND = 0x00000004
SDC_TOPO_SUPPLIED = 0x00000010
SDC_USE_SUPPLIED = 0x00000020
SDC_VALIDATE = 0x00000040
SDC_APPLY = 0x00000080      # NOT 0x1 - that bit is TOPOLOGY_INTERNAL
SDC_SAVE = 0x00000200
SDC_ALLOW_CHANGES = 0x00000400
SDC_ALLOW_PATH_ORDER = 0x00002000
SUPP_APPLY = SDC_APPLY | SDC_USE_SUPPLIED
SUPP_VAL = SDC_VALIDATE | SDC_USE_SUPPLIED
assert ctypes.sizeof(_hdr.DC_PATH) == 72 and \
    ctypes.sizeof(_hdr.DC_MODE) == 64, "DisplayConfig layout drift"
u32.SetDisplayConfig.argtypes = [wintypes.UINT, ctypes.POINTER(_hdr.DC_PATH),
                                 wintypes.UINT, ctypes.POINTER(_hdr.DC_MODE),
                                 wintypes.UINT]
u32.SetDisplayConfig.restype = ctypes.c_long
REG_KEY = (r"HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
           r"\Connectivity")
VAL_RE = re.compile(r"^(\S+)\s+REG_BINARY\s+([0-9A-Fa-f]{16})")
AOC = "AOC2790"


def sdc(paths, modes, flags, tag):
    """One SetDisplayConfig call, logged rc/gle; None = the
    NULL-array family-verb shape. Returns (rc, gle)."""
    k32.SetLastError(0)
    rc = u32.SetDisplayConfig(0 if paths is None else len(paths), paths,
                              0 if modes is None else len(modes), modes,
                              flags)
    print("%-22s rc=0x%X gle=%d" % (tag, rc & 0xFFFFFFFF,
                                    ctypes.get_last_error()), flush=True)
    return rc, ctypes.get_last_error()


def desk(tag):
    rows = [(m.get("short"), m.get("gdi")) for m in wm.monitors()]
    print("desk[%s]: %d rows %s" % (tag, len(rows), rows), flush=True)
    return rows


def conn_rows(tag):
    """{subkey: {value: first-16-hex}} - the Connectivity store,
    values not blobs; None = unreadable (the confession is logged,
    elevation owed: a medium-integrity token is Administrators-
    Deny-Only and the key's ACL is Administrators-read)."""
    try:
        r = subprocess.run(["reg", "query", REG_KEY, "/s"],
                           capture_output=True, text=True, timeout=10)
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode:
            print("conn[%s]: reg query rc=%d: %s - store diff "
                  "UNVERIFIED at medium integrity (elevation owed)"
                  % (tag, r.returncode,
                     out.strip().splitlines()[0]
                     if out.strip() else "(no output)"), flush=True)
            return None
    except Exception as exc:
        print("conn[%s]: reg query failed: %r" % (tag, exc), flush=True)
        return None
    rows, sub = {}, ""
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("HKEY"):
            sub = s[len(REG_KEY):].strip("\\")
            continue
        m = VAL_RE.match(s)
        if m:
            rows.setdefault(sub, {})[m.group(1)] = m.group(2)
    print("conn[%s]: %d subkey(s), %d value(s)"
          % (tag, len(rows), sum(len(v) for v in rows.values())),
          flush=True)
    return rows


def conn_diff(a, b):
    if a is None or b is None:
        print("conn[diff]: skipped (a snapshot unreadable)", flush=True)
        return
    changed = 0
    for k in sorted(set(a) | set(b)):
        for v in sorted(set(a.get(k, {})) | set(b.get(k, {}))):
            x, y = a.get(k, {}).get(v, "-"), b.get(k, {}).get(v, "-")
            if x != y:
                changed += 1
                print("conn[diff]: %s\\%s %s -> %s" % (k, v, x, y),
                      flush=True)
    print("conn[diff]: %d value(s) changed" % changed, flush=True)


def capture(flags, tag):
    """GBS -> Query, counts from the OS's own answers (never guesses)."""
    n_p, n_m = wintypes.UINT(), wintypes.UINT()
    k32.SetLastError(0)
    rc = u32.GetDisplayConfigBufferSizes(flags, ctypes.byref(n_p),
                                         ctypes.byref(n_m))
    print("%s GBS rc=0x%X counts=%d/%d"
          % (tag, rc & 0xFFFFFFFF, n_p.value, n_m.value), flush=True)
    if rc:
        return None
    paths = (_hdr.DC_PATH * n_p.value)()
    modes = (_hdr.DC_MODE * n_m.value)()
    k32.SetLastError(0)
    rc = u32.QueryDisplayConfig(flags, ctypes.byref(n_p), paths,
                                ctypes.byref(n_m), modes, None)
    print("%s Query rc=0x%X got=%d/%d"
          % (tag, rc & 0xFFFFFFFF, n_p.value, n_m.value), flush=True)
    return None if rc or not n_p.value else (n_p.value, n_m.value,
                                             paths, modes)


def name_of(psrc, ptgt):
    """(source gdi name, target path) - the dossier's identity joins,
    both via DisplayConfigGetDeviceInfo."""
    sn = _hdr.DC_SOURCE_NAME()
    sn.header.type, sn.header.size = _hdr.DCI_GET_SOURCE_NAME, \
        ctypes.sizeof(sn)
    sn.header.adapter, sn.header.id = psrc.adapter, psrc.id
    u32.DisplayConfigGetDeviceInfo(ctypes.byref(sn.header))
    tn = _hdr.DC_TARGET_NAME()
    tn.header.type, tn.header.size = _hdr.DCI_GET_TARGET_NAME, \
        ctypes.sizeof(tn)
    tn.header.adapter, tn.header.id = ptgt.adapter, ptgt.id
    u32.DisplayConfigGetDeviceInfo(ctypes.byref(tn.header))
    return sn.name, tn.path


def arr(buf, count, kind):
    cls = _hdr.DC_PATH if kind == "p" else _hdr.DC_MODE
    n = count if kind == "p" else len(buf) // 64
    return (cls * n).from_buffer_copy(buf)


def ccd_view(tag):
    """The AUTHORITATIVE view: active paths straight from the CCD
    (target model token + gdi source), not the GDI slot names - on
    this NVIDIA+KVM desk EnumDisplayDevices can ghost a panel behind
    the switch's emulated EDID."""
    act = capture(QDC_ACTIVE, "ccd-" + tag)
    if act is None:
        return None
    n, m, paths, modes = act
    out = []
    for i in range(n):
        src, tp = name_of(paths[i].src, paths[i].tgt)
        tok = tp.split("#")[1].upper() if "#" in tp else "?"
        out.append((tok, str(src).upper()))
    print("ccd[%s]: active targets %r" % (tag, out), flush=True)
    return out


def validate_twin(flags):
    return (flags & ~SDC_APPLY) | SDC_VALIDATE


def try_rung(label, paths_buf, n_paths, flags, base):
    """VALIDATE gate -> APPLY -> 6 s victim watch -> restore (same
    flags, SAVE included). Returns ('HIT', t) AOC gone from the CCD
    view AND the desk rows, ('GHOST', t) gone from the CCD view but
    EnumDisplayDevices still shows its row (the KVM's emulated EDID
    ghosting - code-dark, eyes judge lit/dark), ('WRONG-VICTIM', t)
    rows dropped with the AOC still live in the CCD view,
    ('NO-DROP', None), ('VALIDATE-REFUSED', rc) - no apply, no
    glass - or ('REFUSED', rc) after an applied-but-refused shape."""
    rcv, _ = sdc(arr(paths_buf, n_paths, "p"), arr(MODES_B, 0, "m"),
                 validate_twin(flags), label + " VALIDATE")
    if rcv:
        print("%s: VALIDATE rc=0x%X - apply SKIPPED (owner strobe "
              "law: no glass on a refused shape)" % (label,
                                                     rcv & 0xFFFFFFFF),
              flush=True)
        return "VALIDATE-REFUSED", None, rcv
    rc, _ = sdc(arr(paths_buf, n_paths, "p"), arr(MODES_B, 0, "m"),
                flags, label + " APPLY")
    if rc:
        return "REFUSED", None, rc
    print("WATCH THE AOC - 6 seconds", flush=True)
    time.sleep(2)
    t0 = time.monotonic()
    hit, wrong, ghost, sampled = None, None, None, False
    rows = desk("mid +0.0s")
    try:
        while time.monotonic() - t0 < 6.0:
            time.sleep(0.5)
            el = time.monotonic() - t0
            rows = desk("mid %+.1fs" % el)
            if el >= 1.4 and not sampled:
                sampled = True
                view = ccd_view("mid %s" % label)
                if view is not None:
                    live = any(tok == AOC for tok, _ in view)
                    shown = AOC in {s for s, _ in rows}
                    if not live and shown:
                        ghost = el
                    elif not live:
                        hit = el
                    elif len(rows) < base:
                        wrong = el
    finally:
        sdc(arr(SAVED_P, N_P, "p"), arr(MODES_B, 0, "m"), flags,
            "RESTORE (same SAVE)")
    t1 = time.monotonic()
    while time.monotonic() - t1 < 20.0:
        time.sleep(0.5)
        if len(wm.monitors()) >= base:
            desk("after")
            break
    else:
        for k in range(3):                 # the desk sat short
            print("S.O.S.: %r short of %d rows, restore try %d"
                  % (label, base, k + 1), flush=True)
            sdc(arr(SAVED_P, N_P, "p"), arr(MODES_B, 0, "m"),
                SUPP_APPLY | SDC_SAVE | SDC_ALLOW_CHANGES,
                "RESTORE retry%d" % (k + 1))
            time.sleep(2.0)
            if len(wm.monitors()) >= base:
                break
        else:
            print("S.O.S. LOUD: desk still short after 3 tries - "
                  "Settings -> Detect or the physical button "
                  "(undefeated).", flush=True)
    t = hit if hit is not None else (ghost if ghost is not None
                                     else wrong)
    kind = ("HIT" if hit is not None else
            "GHOST" if ghost is not None else
            "WRONG-VICTIM" if wrong is not None else "NO-DROP")
    return kind, (t - t0 if t is not None else None), 0


def main():
    global SAVED_P, N_P, N_M, MODES_B
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("off", "check"):
        print(__doc__)
        return
    base = len(desk("before"))
    if base < 2:
        print("desk has %d rows - the LAST active display cannot be "
              "disconnected (OS guard); rung needs >=2" % base)
        return
    act = capture(QDC_ACTIVE, "cap-active")
    capture(QDC_ALL, "cap-all")     # the read shape's evidence line
    if act is None:
        print("RUNG UNPROVEN: the read leg died (was clean Oct 14 "
              "pm - desk or driver moved since)")
        return
    N_P, N_M, paths, modes = act
    SAVED_P, MODES_B = bytes(bytearray(paths)), bytes(bytearray(modes))
    row = next((m for m in wm.monitors() if m.get("short") == AOC), None)
    if row is None:
        print("AOC row not on the desk (KVM moved?) - retraction "
              "skipped")
        return
    aoc_gdi = str(row.get("gdi", "")).upper()
    tgt_id = None
    for i in range(N_P):
        src, tp = name_of(paths[i].src, paths[i].tgt)
        print("path[%d] src=%r tgt=%r flags=0x%X%s"
              % (i, src, tp, paths[i].flags,
                 "  <== AOC" if str(src).upper() == aoc_gdi else ""))
        if str(src).upper() == aoc_gdi and tgt_id is None:
            tgt_id = (paths[i].tgt.adapter.low, paths[i].tgt.adapter.high,
                      paths[i].tgt.id)
    if tgt_id is None:
        print("AOC source %r carries no path - retraction skipped"
              % aoc_gdi)
        return

    def path_set(retract):
        """full saved paths; 'flags' zeroes the AOC paths' flags,
        'minus' drops them (the SO 57136638 technique)."""
        buf = bytearray(SAVED_P)
        sz = 72
        idxs = [i for i in range(N_P)
                if (paths[i].tgt.adapter.low, paths[i].tgt.adapter.high,
                    paths[i].tgt.id) == tgt_id]
        if retract == "flags":
            for i in idxs:
                if paths[i].flags:
                    buf[i * sz + sz - 4:i * sz + sz] = b"\0\0\0\0"
            return bytes(buf), N_P
        keep = [i for i in range(N_P) if i not in idxs]
        return b"".join(buf[i * sz:(i + 1) * sz] for i in keep), len(keep)

    minus, n_minus = path_set("minus")
    zeroed, _n = path_set("flags")
    shapes = (
        ("PATH-MINUS save", minus, n_minus,
         SUPP_APPLY | SDC_SAVE | SDC_ALLOW_CHANGES),
        ("PATH-MINUS supp", minus, n_minus,
         SDC_APPLY | SDC_TOPO_SUPPLIED | SDC_ALLOW_CHANGES
         | SDC_ALLOW_PATH_ORDER | SDC_SAVE),
        ("ZERO-FLAGS save", zeroed, N_P, SUPP_APPLY | SDC_SAVE
         | SDC_ALLOW_CHANGES))

    # the as-is gate: its APPLY measured rc=0x0 four times tonight -
    # the VALIDATE twin is the credibility check from here on, and
    # it costs no glass (owner strobe law).
    rc1, _ = sdc(paths, modes, SUPP_VAL, "AS-IS VALIDATE")
    if mode == "check":
        for label, buf, n, fl in shapes:
            sdc(arr(buf, n, "p"), arr(MODES_B, 0, "m"),
                validate_twin(fl), label + " VALIDATE")
        sdc(None, None, SDC_VALIDATE | SDC_TOPO_EXTEND,
            "SANITY EXTEND VALIDATE")
        print("check: table above is validate-only evidence; ZERO "
              "applies, glass untouched", flush=True)
        desk("final")          # the invariant: before == final rows
        return

    conn0 = conn_rows("before")
    results, applied = [], False
    if rc1 == 0:
        for label, buf, n, fl in shapes:      # ONE physical cycle
            kind, t, rc = try_rung(label, buf, n, fl, base)
            results.append((label, kind, t, rc))
            if kind != "VALIDATE-REFUSED":
                applied = True
                break                        # the cycle is spent
    else:
        print("as-is VALIDATE refused - marshal suspect stands; no "
              "apply, no glass")
    conn1 = conn_rows("after")
    conn_diff(conn0, conn1)
    if applied:
        post = ccd_view("restored")
        full = post is not None and sum(1 for tok, _ in post
                                        if tok == AOC) == 1
    else:
        full = None
    sdc(None, None, SDC_VALIDATE | SDC_TOPO_EXTEND,
        "SANITY EXTEND VALIDATE")     # APPLY measured 0x0 three times
    final = desk("final")
    hits = [r for r in results if r[1] in ("HIT", "GHOST")]
    verdict = ("MARSHAL-BUG" if rc1 else
               "RESURRECTED (%s)" % ("KVM-ghost at the GDI view, the "
                                     "CCD row itself went dark"
                                     if hits[0][1] == "GHOST"
                                     else "desk and CCD agree")
               if hits else
               "DEAD-ON-MERIT - no rung took the AOC out of the CCD "
               "view: %r" % ([(r[0], r[1], r[3]) for r in results],))
    print("VERDICT: %s - as-is VALIDATE rc=0x%X, rungs %r, "
          "post-restore all-3-active=%s, final desk %d rows; AOC "
          "dark? the owner's eyes are the court (SAVE_TO_DATABASE "
          "persisted through the restore - elevated reg diff owed)"
          % (verdict, rc1, [(r[0], r[1]) for r in results], full,
             len(final)), flush=True)


main()
