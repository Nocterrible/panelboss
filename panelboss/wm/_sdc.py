"""CCD retraction: the DISCONNECT flavor of away-off (the off-mode
arc's last wave, owner-ruled 2026-10-14; the measured law is the
4eaf7ce dossier, the proven marshal is scripts/sdc_off_probe2.py -
this file is that marshal, app-shaped).

The act: SetDisplayConfig with the target's paths DROPPED from the
supplied array (PATH-MINUS) and the flags 0x6A0 =
APPLY|USE_SUPPLIED|SAVE|ALLOW_CHANGES. The dossier's three guard-
rails, all honored here: SDC_APPLY is 0x80, not 0x1 (0x1|0x2 was the
verbless topology ask that 0x57'd the first probe at entry);
SDC_ALLOW_PATH_ORDER_CHANGES is falsified as-is on this 26220/NVIDIA
stack and stays out; and the ZERO-FLAGS shape is the wrong-victim
trap (it validates, applies, and lets the CCD re-normalize drop a
DIFFERENT panel) - which is why every apply here is followed by the
ONLY honest verification: a QDC_ACTIVE re-query that must show THE
INTENDED target gone. The GDI row list is never believed for this
check: the KVM's emulated EDID ghosts a detached slot (DISPLAY3),
rows lie while the CCD is true.

SAVE_TO_DATABASE means the retraction persists in the HKLM CCD
store - it survives this app, and a restore that does NOT carry the
same SAVE bit leaves the stored profile rebooting the panel dark
(the named footgun; every write here carries SAVE, restore
included). The boot belt's offdisc door (state/_away.py) answers
the survival from inside the app: re-query, and if a configured
row's target sits inactive, raise its path back. Windows refuses to
disconnect the last active display - that guard arrives as an
ordinary nonzero rc and the caller degrades to blackout like every
other refusal, no new code.

SIZE LAW: pure CCD at ~240 (post gate fixes) - the ctypes core of
the flavor; the row
ledger, the status words and the belt live in state/_away.py, the
paint in ui/window/_away.py. Test seams: _capture, _names and
_apply_cfg are the FFI trio the suite replaces wholesale; everything
above them is marshal arithmetic that runs unhooked under the fake.
"""
import ctypes
import logging
import struct
import time
from ctypes import wintypes

from . import _hdr
from ._winapi import k32, u32

log = logging.getLogger("wm")
QDC_ALL = 0x00000001
QDC_ACTIVE = _hdr.QDC_ONLY_ACTIVE_PATHS        # 0x2
SDC_USE_SUPPLIED = 0x00000020
SDC_VALIDATE = 0x00000040
SDC_APPLY = 0x00000080         # NOT 0x1 - that is TOPOLOGY_INTERNAL
SDC_SAVE = 0x00000200          # every write carries it: both flavors
SDC_ALLOW_CHANGES = 0x00000400 # of the dark-boot footgun law
RETRACT_FLAGS = SDC_APPLY | SDC_USE_SUPPLIED | SDC_SAVE | SDC_ALLOW_CHANGES
VALIDATE_FLAGS = SDC_VALIDATE | SDC_USE_SUPPLIED
SDC_PATH_ACTIVE = 0x00000001   # the path-flag bit the CCD answers with
PATH_SZ = 72                   # DC_PATH on the table (asserted below)
assert ctypes.sizeof(_hdr.DC_PATH) == PATH_SZ, "DisplayConfig layout drift"

u32.SetDisplayConfig.argtypes = [wintypes.UINT, ctypes.POINTER(_hdr.DC_PATH),
                                 wintypes.UINT, ctypes.POINTER(_hdr.DC_MODE),
                                 wintypes.UINT]
u32.SetDisplayConfig.restype = ctypes.c_long

VERIFY_TRIES = 4               # the CCD moves inside a tick; measured
VERIFY_WAIT_SEC = 0.3          # 0.5 s sampling - 1.2 s is generous


def _names(psrc, ptgt):
    """(source gdi name, target device path) - the dossier's identity
    joins, both halves via DisplayConfigGetDeviceInfo (the probe's
    name_of, verbatim purpose)."""
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


def _capture(flags):
    """GBS -> Query, counts from the OS's own answers (never guesses;
    the probe's read leg). None = the CCD cannot be talked to."""
    n_p, n_m = wintypes.UINT(0), wintypes.UINT(0)
    if u32.GetDisplayConfigBufferSizes(flags, ctypes.byref(n_p),
                                       ctypes.byref(n_m)) != 0:
        return None
    paths = (_hdr.DC_PATH * n_p.value)()
    modes = (_hdr.DC_MODE * n_m.value)()
    if u32.QueryDisplayConfig(flags, ctypes.byref(n_p), paths,
                              ctypes.byref(n_m), modes, None) != 0:
        return None
    return bytes(bytearray(paths)), bytes(bytearray(modes)), list(paths)


def _apply_cfg(path_bytes, modes_bytes, flags):
    """One SetDisplayConfig over the byte arrays; (rc, gle). The gle
    is the OS's own GetLastError through the real handle (the
    windll default carries no ctypes-side error store - the probe's
    gle column came from the same call). Named _apply_cfg, not
    _sdc: the wm facade FANS attribute writes through to the parts,
    and a part's own `_sdc` slot would collide with the module's
    name in wm._sdc patching (the suite's own seam, learned here)."""
    n_p = len(path_bytes) // PATH_SZ
    n_m = len(modes_bytes) // 64
    pa = (_hdr.DC_PATH * max(n_p, 1)).from_buffer_copy(
        path_bytes or b"\0" * PATH_SZ) if n_p else None
    ma = (_hdr.DC_MODE * max(n_m, 1)).from_buffer_copy(
        modes_bytes or b"\0" * 64) if n_m else None
    k32.SetLastError(0)
    rc = u32.SetDisplayConfig(n_p, pa, n_m, ma, flags) & 0xFFFFFFFF
    return rc, k32.GetLastError()


def _rows(flags):
    """The captured view as marshal rows: (idx, target-key, flags,
    upper-cased gdi source, upper-cased target model token)."""
    cap = _capture(flags)
    if cap is None:
        return None
    pb, mb, paths = cap
    out = []
    for i, p in enumerate(paths):
        src, tp = _names(p.src, p.tgt)
        out.append((i, (p.tgt.adapter.low, p.tgt.adapter.high, p.tgt.id),
                    p.flags, str(src).upper(),
                    (tp.split("#")[1].upper() if "#" in tp else "?")))
    return pb, mb, out


def _victim(rows, row):
    """The target key(s) this app-row names, as (keys, why). The
    gdi-slot join and the EDID-token join are CROSS-CHECKED (gate
    fix 2): when both answer and name DIFFERENT targets the answer
    is NO victim - a slot that re-normalized behind our back must
    never dark the wrong panel with the witness nodding, so we
    refuse and say so. One join answering alone carries the row
    (the ghost's dark slot answers nothing in the active view; a
    hand-built row names no slot); twins the token cannot single
    out stay the no-gamble class. why is the honest refusal word
    when the keys come back empty."""
    gdi = str(row.get("gdi") or "").upper()
    tok = str(row.get("short") or "").upper()
    slot = {r[1] for r in rows if gdi and r[3] == gdi}
    token = {r[1] for r in rows if r[4] == tok}
    token = token if len(token) == 1 else set()
    if slot and token and not (token <= slot):
        return set(), ("the gdi slot names one panel, the EDID token "
                       "another (no gamble)")
    keys = slot or token
    if keys:
        return keys, ""
    if tok and any(r[4] == tok for r in rows):
        return set(), "several twins answer the token; no slot names one"
    return set(), "no CCD path answers this row"


def _drop(pb, rows, keys):
    """PATH-MINUS: the kept entries' bytes, order preserved (the
    falsified ALLOW_PATH_ORDER says the driver may not reshuffle -
    it gets the order it was given, minus the victim)."""
    drop = {r[0] for r in rows if r[1] in keys}
    keep = [i for i in range(len(pb) // PATH_SZ) if i not in drop]
    return b"".join(pb[i * PATH_SZ:(i + 1) * PATH_SZ] for i in keep), len(keep)


def _raise(pb, rows, keys):
    """The restore shape of the same capture: every victim entry's
    path flags gain SDC_PATH_ACTIVE (the belt's door, and the
    already-dark save - both must hand the light back, not re-write
    the dark)."""
    buf = bytearray(pb)
    for i, key, flags, _s, _t in rows:
        if key in keys and not flags & SDC_PATH_ACTIVE:
            struct.pack_into("<I", buf, i * PATH_SZ + PATH_SZ - 4,
                             flags | SDC_PATH_ACTIVE)
    return bytes(buf)


def _gone(victim, tries=VERIFY_TRIES):
    """The ONLY honest post-apply truth, THREE-valued (gate fix 1):
    True = the active view no longer carries the victim (verified
    gone); False = a view answered and the victim is STILL THERE
    (the wrong-victim class - accepted, nothing dropped as asked);
    None = BLIND: every re-query refused (gate fix 1's split - the
    retraction's fate is UNKNOWN, and an unknown must never be
    sentenced as either class). The GDI rows are not asked (the KVM
    ghost keeps them lying through the retraction)."""
    blind = True
    for _ in range(tries):
        time.sleep(VERIFY_WAIT_SEC)
        view = _rows(QDC_ACTIVE)
        if view is None:
            continue
        blind = False
        if not (victim & {r[1] for r in view[2]}):
            return True
    return None if blind else False


def retract(row):
    """Disconnect this row's panel at the adapter. Returns
    (True, saved) only when the CCD RE-QUERY proves the intended
    target left the active set (or found it already retracted - the
    same verified word), else (False, why) with the desk honest: a
    validate-refusal applies nothing; a wrong-victim or a blind
    verify restores its own damage before reporting, and the word
    names WHICH happened and WHETHER the restore took (gate fix 1:
    'no-drop rc 0x0 (wrong victim; restored)' / '(...; NOT RESTORED:
    <say>)' / '(verify refused; restored unverified (blind re-query))'
    - three classes, no misattribution). `saved` is the restore
    record - the full captured arrays with the victim ACTIVE - the
    lift hands it back through restore()."""
    act = _rows(QDC_ACTIVE)
    if act is None:
        return False, "the CCD query refused (rc unreadable)"
    pb, mb, rows = act
    keys, why = _victim(rows, row)
    if not keys:
        al = _rows(QDC_ALL)                       # the ghost's shape:
        if al is None:                            # GDI row lies, the
            return False, "no CCD answer at all"  # target exists dark
        keys, why = _victim(al[2], row)           # the ALL view gets
        if not keys:                              # the same cross-
            return False, why                     # check; a
            #                                     # disagreement
                                                  # outranks mercy
        return True, {"paths": _raise(al[0], al[2], keys), "modes": al[1],
                      "victim": keys, "at": time.time()}
    minus, _n = _drop(pb, rows, keys)
    rc, gle = _apply_cfg(minus, mb, VALIDATE_FLAGS)
    if rc:
        return False, "validate rc 0x%X gle=%d" % (rc, gle)
    rc, gle = _apply_cfg(minus, mb, RETRACT_FLAGS)
    if rc:
        return False, "rc 0x%X gle=%d" % (rc, gle)
    gone = _gone(keys)
    if gone is True:
        return True, {"paths": pb, "modes": mb, "victim": keys,
                      "at": time.time()}
    r_ok, r_why = restore({"paths": pb, "modes": mb, "victim": keys,
                           "at": time.time()})
    reason = "wrong victim" if gone is False else "verify refused"
    if r_ok:
        back = "restored"
    elif gone is None and r_why == "the re-query stayed blind":
        # blind inside blind: the restore's WRITE took the same rc
        # the retraction's took - it is the CHECK that cannot see,
        # so the word says restored-unverified, never NOT RESTORED
        # (gate fix 1: the misattribution class, one clause deep)
        back = "restored unverified (blind re-query)"
    else:
        back = "NOT RESTORED: %s" % r_why
    return False, "no-drop rc 0x0 (%s; %s)" % (reason, back)


def restore(saved):
    """Hand the panel back: re-apply the saved arrays WITH the SAVE
    bit (a restore without it leaves the store rebooting the panel
    dark - the footgun, closed at every write). (True, "") only when
    the re-query sees the target active again; the why names WHICH
    failure answered (still-dark vs blind - gate fix 1's honesty
    travels every verify seam)."""
    rc, gle = _apply_cfg(saved["paths"], saved["modes"], RETRACT_FLAGS)
    if rc:
        return False, "restore rc 0x%X gle=%d" % (rc, gle)
    came = _victim_active(saved["victim"])
    if came is True:
        return True, ""
    if came is False:
        return False, "the target never came back"
    return False, "the re-query stayed blind"


def revive(row):
    """The boot belt's door, no in-memory record needed: re-query the
    ALL view, and when this row's target sits there INACTIVE, raise
    its path back with the SAVE bit. None = nothing to do (the row
    is lit, twins the token cannot single out, or no path answers it
    - the belt's silent classes, same religion as the D6 door);
    (ok, why) = the belt already logged the act either way. A
    slot/token DISAGREEMENT is loud for callers that NAME a gdi -
    but the belt's own call shape ({"short", "gdi": ""}) carries no
    slot to cross-check, so disputes stay SILENT BY DESIGN on the
    belt's road and the loud branch below is defensive for the
    gdi-naming callers that may come (dossier follow-up 2: the
    comment, not the branch, was the lie)."""
    al = _rows(QDC_ALL)
    if al is None:
        return None
    pb, mb, rows = al
    keys, why = _victim(rows, row)
    if keys and any(r[1] in keys and r[2] & SDC_PATH_ACTIVE for r in rows):
        return None                               # lit: silence
    if not keys:
        return (False, why) if "no gamble" in why else None
    rc, gle = _apply_cfg(_raise(pb, rows, keys), mb, RETRACT_FLAGS)
    return (rc == 0 and _victim_active(keys) is True), \
        "rc 0x%X gle=%d" % (rc, gle)


def _victim_active(keys, tries=VERIFY_TRIES):
    """True/False for an answering view; None = BLIND (no verdict
    about the glass, only about the check). THE SAME PATIENCE _gone
    earned (dossier follow-up 1): the CCD reactivates a path on its
    own schedule - one immediate look false-warned 'never came
    back' on a merely slow store, so every verify seam re-looks
    within the same budget."""
    blind = True
    for _ in range(tries):
        time.sleep(VERIFY_WAIT_SEC)
        view = _rows(QDC_ACTIVE)
        if view is None:
            continue
        blind = False
        if keys & {r[1] for r in view[2]}:
            return True
    return None if blind else False
