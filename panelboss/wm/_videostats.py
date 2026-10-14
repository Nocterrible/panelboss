"""Video-engine activity and HDR-content presence, for the auto-switch
(amendment 8). Two public probes, both fail-open, neither elevates:

  video_busy()  PDH's GPU Engine UTILIZATION counters, summed over the
                video-family engines only - Task Manager's own source,
                public and unelevated. The instance shape is measured
                on this box (Oct 13): ``pid_<pid>_luid_<luid>_phys_<n>_
                eng_<ordinal>_engtype_<KIND>`` (NVIDIA spells the kind
                ``VideoDecode``, an iGPU with spaces, ``video decode
                1``; the matcher normalizes both). The engine-type
                enum: DXGK/D3DKMT ENGINE_TYPE - VIDEO_DECODE=2,
                VIDEO_ENCODE=3, VIDEO_PROCESSING=4, per the manifest
                docs:
                https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3dkmdt/ne-d3dkmdt-dxgk_engine_type
                We take DECODE(2) and PROCESSING(4) and deliberately
                NOT ENCODE(3): encoding means recording/streaming,
                and someone recording the desktop is not watching
                HDR. JPEG decode and the vendor "video codec" catch-
                alls are excluded the same way - photos are not a
                movie.

  mpv_hdr_playing(pipe)  the player-ipc tier: ask an mpv (started
                with --input-ipc-server=<pipe>) for video-params and
                let the PURE matcher mpv_is_hdr() decide: primaries
                bt.2020 and gamma pq/hlg is HDR content, per mpv's
                own docs; the matching is deliberately loose (case,
                punctuation, the documented gamma aliases) because
                mpv warns its property shapes may gain spellings.
                MPC-HC's command channel is a documented FOLLOW-UP.

Size law (~150, Oct 13, the claim includes its own lines): the module
is the counter/pipe vocabulary plus two probes over it; the state
machine that ACTS on the verdicts lives in state/_hdrwatch.py (pure,
fake-clocked tests). The mechanics mirror panelboss/gpu.py (measured
on this build: fresh query per call, one collect pair, wildcard array
reads die of heap corruption so every counter is added per-instance);
the one deliberate difference: PdhAddEnglishCounterPathW, the
locale-proof door - gpu.py entered through the localized one and
survives only because this desk speaks English.
"""

import ctypes
import json
import logging
import re
import time
from ctypes import wintypes as W

log = logging.getLogger("videostats")

try:
    pdh = ctypes.WinDLL("pdh.dll")
except (OSError, AttributeError):
    pdh = None

# the vocabulary the offline suite asserts against (no live counters
# in tests - amendment 8 item 3): one path template over the measured
# instance names, English, locale-proof through
# PdhAddEnglishCounterPathW.
OBJECT = "GPU Engine"
COUNTER = "Utilization Percentage"
COUNTER_PATH = "\\GPU Engine(%s)\\Utilization Percentage"

# engine-kind fragments, normalized (lower, non-alnum stripped): the
# decode(2)/processing(4) family - see the module header for why
# encode(3) and the jpeg/codec catch-alls stay out
VIDEO_KINDS = ("videodecode", "videoprocessing")

MPV_PIPE_DEFAULT = r"\\.\pipe\mpv-video"   # the convention: mpv was
# started --input-ipc-server=\.\pipe\mpv-video; cfg [hdr] mpv_pipe
# overrides, one player per desk for now
MPV_HDR_GAMMAS = ("pq", "smptestpq", "hlg", "aribstdb67")
PIPE_WAIT_MS = 100        # no server: bound the wait, answer not-hdr
COLLECT_GAP_SEC = 1.2     # the PDH delta window (gpu.py's measured
                          # number, same provider same truth)
CAP = 400                 # instances tracked per call (gpu.py's net)

_INST_RE = re.compile(r"pid_(\d+)_", re.I)


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def is_video_instance(name):
    """True when the GPU Engine instance name is a video-family engine
    we trust as a watch signal (decode/processing; not encode, not
    jpeg, not the vendor codec catch-all)."""
    s = _norm(name)
    return any(frag in s for frag in VIDEO_KINDS)


if pdh is not None:
    pdh.PdhEnumObjectItemsW.argtypes = [W.LPCWSTR, W.LPCWSTR, W.LPCWSTR,
                                        W.LPWSTR, ctypes.POINTER(W.DWORD),
                                        W.LPWSTR, ctypes.POINTER(W.DWORD),
                                        W.DWORD, W.DWORD]
    pdh.PdhOpenQueryW.argtypes = [W.LPCWSTR, W.DWORD,
                                  ctypes.POINTER(W.HANDLE)]
    pdh.PdhAddEnglishCounterPathW.argtypes = [W.HANDLE, W.LPCWSTR, W.DWORD,
                                              ctypes.POINTER(W.HANDLE)]
    pdh.PdhCollectQueryData.argtypes = [W.HANDLE]
    pdh.PdhGetFormattedCounterValue.restype = W.DWORD
    pdh.PdhGetFormattedCounterValue.argtypes = [
        W.HANDLE, W.DWORD, ctypes.POINTER(W.DWORD), W.LPVOID]
    pdh.PdhCloseQuery.restype = None
    pdh.PdhCloseQuery.argtypes = [W.HANDLE]

k32 = ctypes.windll.kernel32        # the pipe gate lives here, not
k32.WaitNamedPipeW.restype = W.BOOL  # in pdh.dll (measured: it is not
k32.WaitNamedPipeW.argtypes = [W.LPCWSTR, W.DWORD]   # a pdh export)


class _FMTV(ctypes.Structure):
    """The plain PDH counter value layout gpu.py picked as the winner
    of record on this build (its header carries the measurement)."""
    _fields_ = [("CStatus", W.DWORD), ("Pad", W.DWORD),
                ("Value", ctypes.c_double)]


def _video_instances():
    csz, isz = W.DWORD(0), W.DWORD(0)
    pdh.PdhEnumObjectItemsW(None, None, OBJECT, None, ctypes.byref(csz),
                            None, ctypes.byref(isz), 0, 0)
    cb = ctypes.create_unicode_buffer(max(csz.value, 2))
    ib = ctypes.create_unicode_buffer(max(isz.value, 2))
    if pdh.PdhEnumObjectItemsW(None, None, OBJECT, cb, ctypes.byref(csz),
                               ib, ctypes.byref(isz), 0, 0):
        return []
    names = [t for t in bytes(ib).decode("utf-16", "ignore").split("\0")
             if t and is_video_instance(t)]
    names.sort()
    return names[:CAP]


def video_busy():
    """Total video-engine utilization percent right now (float, >= 0).
    Blocks ~COLLECT_GAP_SEC by design (the PDH delta window - gpu.py's
    measured law); callers run off the UI thread. Fail-open: 0.0 on
    any trouble, including no pdh.dll and an ancient Windows."""
    if pdh is None:
        return 0.0
    q = None
    try:
        inst = _video_instances()
        if not inst:
            return 0.0
        hq = W.HANDLE()
        if pdh.PdhOpenQueryW(None, 0, ctypes.byref(hq)):
            return 0.0
        q = hq
        handles = []
        for n in inst:
            h = W.HANDLE()
            if pdh.PdhAddEnglishCounterPathW(q, COUNTER_PATH % n, 0,
                                             ctypes.byref(h)):
                continue          # died mid-enum->add: churn, keep going
            handles.append(h)
        if not handles:
            return 0.0
        if pdh.PdhCollectQueryData(q):
            return 0.0
        time.sleep(COLLECT_GAP_SEC)
        if pdh.PdhCollectQueryData(q):
            return 0.0
        total = 0.0
        for h in handles:
            f = _FMTV()
            if pdh.PdhGetFormattedCounterValue(h, 0x00000800, None,
                                               ctypes.byref(f)):
                continue
            total += f.Value
        return max(total, 0.0)
    except Exception:
        log.debug("video_busy failed", exc_info=True)
        return 0.0
    finally:
        if q is not None:
            try:
                pdh.PdhCloseQuery(q)
            except Exception:
                pass


def mpv_is_hdr(params):
    """PURE matcher over one mpv video-params dict: primaries bt.2020
    AND gamma in (pq, hlg) (+ the documented aliases) is HDR content.
    Missing keys, a non-dict, an SDR answer - all False. The loose
    normalization (case, dots, dashes) is mpv's own warning made
    code: the property vocabulary may gain spellings, the two facts
    we ask are not among them."""
    if not isinstance(params, dict):
        return False
    return (_norm(params.get("primaries")) == "bt2020"
            and _norm(params.get("gamma")) in MPV_HDR_GAMMAS)


def mpv_hdr_playing(pipe=MPV_PIPE_DEFAULT):
    """The live half: ask the pipe for video-params, hand the answer
    to the matcher. No server inside PIPE_WAIT_MS (or a player with
    no video, or a dead pipe) answers False - fail-open, the watcher
    simply never engages for a player that is not playing."""
    try:
        if not k32.WaitNamedPipeW(pipe, PIPE_WAIT_MS):
            return False
        with open(pipe, "w+b", buffering=0) as fh:
            fh.write(b'{"command":["get_property","video-params"]}\n')
            fh.flush()
            reply = json.loads(fh.readline().decode("utf-8"))
        return mpv_is_hdr(reply.get("data"))
    except Exception:
        log.debug("mpv pipe probe failed for %s", pipe, exc_info=True)
        return False
