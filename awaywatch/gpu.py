"""Rendering-GPU utilization per process, read from PDH's per-instance
counters (`\\GPU Engine(*)\\Utilization Percentage`).

What it measures: per-engine GPU busy percentage, summed per process, for
the engines that actually render frames. The watcher uses it to spot 3D
games, where a game pins one of its rendering engines near 100% while a
video player or the desktop shell only touches the decode engines.

Render-kinds only, on purpose. The PDH "GPU Engine" object carries one
instance per (pid, physical GPU, engine). Only kinds that draw frames
count here: 3D, GRAPHICS (GRAPHICS_1..N all included), COMPUTE. Everything
else - videodecode, videoencode, videoprocessing, copy, vr, security,
jpeg, unknown - is excluded deliberately, so a process whose only busy
engine is a videodecoder (video player, capture card, a Teams call) can
never look like a game.

Mechanics, all measured on this build:
  * PdhEnumObjectItemsW("GPU Engine") returns ~1850 instance names like
    `pid_13572_luid_0x00000000_0x00019BB1_phys_0_eng_0_engtype_3D`.
  * The wildcard array read (PdhGetFormattedCounterArrayW) aborts the
    process with heap corruption on this build; it was tried and
    abandoned. This module does per-instance reads only.
  * usage() builds a FRESH PDH query on every call: enumerate instances,
    add counters, collect pair, read, then close the query in a finally
    before returning. Fresh-build-per-call is the law, not an
    optimization: PDH spawns a new "GPU Engine(pid_X...)" instance when
    a process starts rendering, so a query built once is blind to
    later-launched games - stale by design. A failed fresh build just
    returns {}; there is no module-level state to rebuild from.
  * usage() performs one collect pair - collect, sleep ~1.2 s, collect -
    because a PDH delta needs a gap. That is ~1.2 s of blocking time PER
    CALL BY DESIGN; callers must run this off the UI thread.
  * At most 400 rendering instances are tracked: sorted by pid, then
    instance name; the rest are dropped and logged once at debug.

Fail-open: any failure (no pdh.dll, no GPU object, access denied, an
ancient Windows) makes usage() return {} and never raise.
"""

import ctypes
import logging
import re
import time
from ctypes import wintypes as W

logger = logging.getLogger("gpu")

try:
    pdh = ctypes.WinDLL("pdh.dll")
except (OSError, AttributeError):
    pdh = None

PDH_FMT_DOUBLE = 0x00000800
CAP = 400
COLLECT_GAP_SEC = 1.2

# Two FMTV layouts exist across Windows versions; the plain one is the
# primary read and the timestamp-padded one is the hedge. Empirical
# result (2026-10-09, this machine, idle desktop): _FMTV read every
# instance with rc=0 across all collect pairs; the hedge fired (all
# values were 0.0) and _FMTV16 also read rc=0 with all zeros, so the
# variants are indistinguishable while the GPU is idle - the hedge can
# only matter once a value is nonzero. _FMTV is the winner of record.
class _FMTV(ctypes.Structure):
    _fields_ = [("CStatus", W.DWORD), ("Pad", W.DWORD),
                ("Value", ctypes.c_double)]


class _FMTV16(ctypes.Structure):
    _fields_ = [("CStatus", W.DWORD), ("Pad", W.DWORD),
                ("TS", ctypes.c_ulonglong),
                ("Value", ctypes.c_double)]


if pdh is not None:
    # LPCWSTR for every string param: plain str crosses the boundary as
    # ANSI on this path and produces cryptic 0xC0000BBC from PdhEnum.
    pdh.PdhEnumObjectItemsW.argtypes = [W.LPCWSTR, W.LPCWSTR,
                                        W.LPCWSTR, W.LPWSTR,
                                        ctypes.POINTER(W.DWORD),
                                        W.LPWSTR, ctypes.POINTER(W.DWORD),
                                        W.DWORD, W.DWORD]
    pdh.PdhOpenQueryW.argtypes = [W.LPCWSTR, W.DWORD,
                                  ctypes.POINTER(W.HANDLE)]
    pdh.PdhAddCounterW.argtypes = [W.HANDLE, W.LPCWSTR, W.DWORD,
                                   ctypes.POINTER(W.HANDLE)]
    pdh.PdhCollectQueryData.argtypes = [W.HANDLE]
    # THREE args on this build (a 4th arg yields 0xC0000BBD); LPVOID as
    # the 3rd so the same declaration serves both FMTV layouts.
    pdh.PdhGetFormattedCounterValue.restype = W.DWORD
    pdh.PdhGetFormattedCounterValue.argtypes = [W.HANDLE, W.DWORD, W.LPVOID]
    pdh.PdhCloseQuery.restype = None
    pdh.PdhCloseQuery.argtypes = [W.HANDLE]

# pid_<pid>_luid_..._phys_N_eng_N_engtype_<KIND>[_<suffix>]
_INST_RE = re.compile(r"pid_(\d+)_.*_engtype_([A-Za-z0-9]+)")

# Kinds that render frames. Everything else is dropped so video players
# (videodecode only) never look like games.
_RENDER = frozenset(("3D", "GRAPHICS", "COMPUTE"))


def _is_render(kind):
    kind = kind.upper()
    return kind in _RENDER or kind.startswith("GRAPHICS")


def _enum():
    """Enumerate the "GPU Engine" object; return (rc, [instance names])."""
    if pdh is None:
        return 0xC0000005, []
    csz = W.DWORD(0)
    isz = W.DWORD(0)
    pdh.PdhEnumObjectItemsW(None, None, "GPU Engine", None,
                            ctypes.byref(csz), None,
                            ctypes.byref(isz), 0, 0)
    cb = ctypes.create_unicode_buffer(max(csz.value, 2))
    ib = ctypes.create_unicode_buffer(max(isz.value, 2))
    rc = pdh.PdhEnumObjectItemsW(None, None, "GPU Engine", cb,
                                 ctypes.byref(csz), ib,
                                 ctypes.byref(isz), 0, 0)
    names = [t for t in bytes(ib).decode("utf-16", "ignore")
             .split("\0") if t]
    return rc, names


def _render_instances(names):
    """Parse instance names into rendering-engine (pid, name) pairs.

    Sorted by (pid, name) and capped at CAP; the dropped tail is logged
    once at debug.
    """
    parsed = []
    for n in names:
        m = _INST_RE.match(n)
        if not m:
            continue
        pid, kind = int(m.group(1)), m.group(2)
        if _is_render(kind):
            parsed.append((pid, n))
    parsed.sort()
    if len(parsed) > CAP:
        logger.debug("GPU instance cap: dropped %d of %d rendering "
                     "instances", len(parsed) - CAP, len(parsed))
        parsed = parsed[:CAP]
    return parsed


def _add_counters(q, parsed):
    """Add a utilization counter per (pid, name) to the open query.

    Returns (handles, pids) on success, or None on any rc failure. On
    failure the query stays open: usage()'s finally owns the close.
    """
    handles, pids = [], []
    for pid, n in parsed:
        h = W.HANDLE()
        rc = pdh.PdhAddCounterW(
            q, "\\GPU Engine(%s)\\Utilization Percentage" % n,
            0, ctypes.byref(h))
        if rc:
            logger.debug("PdhAddCounterW rc=%x for %s", rc, n)
            return None
        handles.append(h)
        pids.append(pid)
    return handles, pids


def _read_all(handles, struct):
    """Read every counter with the given FMTV layout; [float] or None.

    None means a read rc was nonzero; the caller's finally closes the
    query.
    """
    out = []
    for h in handles:
        f = struct()
        rc = pdh.PdhGetFormattedCounterValue(h, PDH_FMT_DOUBLE,
                                             ctypes.byref(f))
        if rc:
            logger.debug("PdhGetFormattedCounterValue rc=%x", rc)
            return None
        out.append(f.Value)
    return out


def usage():
    """Per-process rendering-GPU utilization: {pid: percent}.

    Builds a FRESH PDH query on every call (module docstring explains
    why a reused query is stale by design) and closes it in a finally
    before returning. A failed fresh build just returns {}; there is
    no module-level state to rebuild from.

    Runs one PDH collect pair (collect, ~1.2 s gap, collect), so it
    blocks about 1.2 s per call BY DESIGN - callers run it off the UI
    thread. Fails open: returns {} on any problem and never raises.
    """
    if pdh is None:
        return {}
    q = None
    try:
        rc, names = _enum()
        if rc or not names:
            logger.debug("GPU enumeration failed rc=%x names=%d",
                         rc, len(names))
            return {}
        parsed = _render_instances(names)
        if not parsed:
            return {}
        hq = W.HANDLE()
        rc = pdh.PdhOpenQueryW(None, 0, ctypes.byref(hq))
        if rc:
            logger.debug("PdhOpenQueryW rc=%x", rc)
            return {}
        q = hq
        added = _add_counters(q, parsed)
        if added is None:
            return {}
        handles, pids = added
        if pdh.PdhCollectQueryData(q):
            return {}
        time.sleep(COLLECT_GAP_SEC)
        if pdh.PdhCollectQueryData(q):
            return {}
        vals = _read_all(handles, _FMTV)
        if vals is None:
            return {}
        if not any(v != 0.0 for v in vals):
            alt = _read_all(handles, _FMTV16)
            if alt is None:
                return {}
            if any(v != 0.0 for v in alt):
                vals = alt
        totals = {}
        for pid, v in zip(pids, vals):
            totals[pid] = totals.get(pid, 0.0) + v
        return {pid: t for pid, t in totals.items()
                if round(t, 1) != 0.0}
    except Exception:
        return {}
    finally:
        if q is not None:
            try:
                pdh.PdhCloseQuery(q)
            except Exception:
                pass
