#!/usr/bin/env python
"""gsync_probe.py - READ-ONLY NVAPI / DRS VRR feasibility probe.

Answers the open question from docs/vrr-findings.md: do *unprivileged* DRS
READS work (vs the documented elevation requirement for DRS *writes*)?

Per NVIDIA display it reports the raw (signed) NvAPI status of:
  * VRR_MODE            0x1194F158
  * VRRREQUESTSTATE     0x1094F1F7
  * VRR_APP_OVERRIDE    0x10A879CF   (is the per-app override list readable?)
plus NvAPI_Disp_GetVRRInfo per display, and which NVAPI exports resolve.

SAFETY / DESIGN
  * READ-ONLY: zero NvAPI_DRS_Set* / Save* / Create* calls. Only Initialize,
    session create/load/get-base/get-setting, display enum, GetVRRInfo,
    GetErrorMessage, GetSettingNameFromId.
  * Release 590 nvapi64.dll is a SAL proxy: it exports ONLY
    nvapi_QueryInterface + nvapi_Direct_GetMethod; every other NvAPI function
    is fetched as a function pointer via nvapi_QueryInterface(method_id).
    IDs come from the canonical NVIDIA/nvapi nvapi_interface.h table
    (NVAPI_INTERFACE_TABLE), embedded below.
  * Crash isolation: on this box a ctypes access violation kills the whole
    python process, so the DRIVER (no args) spawns ONE child venv-python per
    crashy attempt; each child is self-contained (builds its own DRS session)
    and prints a single verdict line. A native AV therefore only costs that
    one child (detected via nonzero exit code), the rest still report.
  * Over-allocated out-buffers + version field: the caller passes a buffer
    LARGER than the driver's struct and the struct-version size, so a
    version mismatch is reported cleanly (NVAPI_INCOMPATIBLE_STRUCT_VERSION)
    instead of overflowing our buffer.
  * Always exits 0 (even on partial failure). Nonzero NvAPI codes are
    FINDINGS (printed raw), not bugs.

Run:  .venv\\Scripts\\python.exe scripts\\gsync_probe.py
"""
import os
import sys
import ctypes
import subprocess

# --- environment (measured, see docs/vrr-findings.md) -------------------------
VENV_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       ".venv", "Scripts", "python.exe")
NVAPI_DLL = "nvapi64.dll"
NVAPI_SYSTEM32 = r"C:\Windows\System32\nvapi64.dll"

# --- DRS setting IDs (from docs/vrr-findings.md) ------------------------------
ID_VRR_MODE = 0x1194F158
ID_VRR_REQUEST_STATE = 0x1094F1F7
ID_VRR_APP_OVERRIDE = 0x10A879CF

# --- NVAPI method IDs (NVIDIA/nvapi nvapi_interface.h, NVAPI_INTERFACE_TABLE) --
# Release 590 nvapi64.dll no longer exports NvAPI_* by name; it exports only
# nvapi_QueryInterface (ord 2) + nvapi_Direct_GetMethod (ord 1). Every NvAPI
# function is fetched as a function pointer: ptr = nvapi_QueryInterface(id).
FN_IDS = {
    "NvAPI_Initialize": 0x0150E828,
    "NvAPI_Unload": 0xD22BDD7E,
    "NvAPI_GetErrorMessage": 0x6C2D048C,
    "NvAPI_EnumNvidiaDisplayHandle": 0x9ABDD40D,
    "NvAPI_Disp_GetVRRInfo": 0xDF8FDA57,
    "NvAPI_DRS_CreateSession": 0x0694D52E,
    "NvAPI_DRS_DestroySession": 0xDAD9CFF8,
    "NvAPI_DRS_LoadSettings": 0x375DBD6B,
    "NvAPI_DRS_GetCurrentGlobalProfile": 0x617BFF9F,
    "NvAPI_DRS_GetSetting": 0x73BF8338,
    "NvAPI_DRS_GetSettingNameFromId": 0xD61CBE6E,
    "NvAPI_DRS_GetBaseProfile": 0xDA8466A0,
    "NvAPI_EnumPhysicalGPUs": 0xE5AC921F,
    "NvAPI_GPU_GetConnectedDisplayIds": 0x0078DBA2,
}

# --- NVDRS struct geometry (nvapi.h master, #pragma pack(4)) -------------------
# NvAPI_UnicodeString = NvU16[2048] = 4096 bytes
UNICODE_STR_LEN = 2048
# NVAPI_BINARY_DATA_MAX = 4096
BINARY_MAX = 4096
# NVDRS_BINARY_SETTING = { u32 valueLength; u8 valueData[4096]; } = 4100
BIN_SETTING_SIZE = 4 + BINARY_MAX          # 4100
# NVDRS_SETTING_V1:
#   u32 version; UnicodeString settingName; u32 settingId; u32 settingType;
#   u32 settingLocation; u32 isCurrentPredefined; u32 isPredefinedValid;
#   union{u32;NVDRS_BINARY_SETTING;UnicodeString;u64} predef;  (4100)
#   union{u32;NVDRS_BINARY_SETTING;UnicodeString;u64} current; (4100)
OFF_VERSION = 0
OFF_SETTING_NAME = 4
OFF_SETTING_ID = OFF_SETTING_NAME + (UNICODE_STR_LEN * 2)   # 4 + 4096 = 4100
OFF_SETTING_TYPE = OFF_SETTING_ID + 4                        # 4104
OFF_SETTING_LOCATION = OFF_SETTING_TYPE + 4                  # 4108
OFF_IS_CURRENT_PREDEFINED = OFF_SETTING_LOCATION + 4         # 4112
OFF_IS_PREDEFINED_VALID = OFF_IS_CURRENT_PREDEFINED + 4      # 4116
OFF_PREDEF_UNION = OFF_IS_PREDEFINED_VALID + 4               # 4120
OFF_CUR_UNION = OFF_PREDEF_UNION + BIN_SETTING_SIZE          # 4120 + 4100 = 8220
NVDRS_SETTING_SIZE = OFF_CUR_UNION + BIN_SETTING_SIZE        # 8220 + 4100 = 12320
# MAKE_NVAPI_VERSION(struct, ver) = sizeof(struct) | (ver << 16)
NVDRS_SETTING_VER = NVDRS_SETTING_SIZE | (1 << 16)

# NV_GET_VRR_INFO_V1 (24 bytes): u32 version; u32 bitfield; u32 reservedEx[4]
#   bits: 0 bIsVRREnabled 1 bIsVRRPossible 2 bIsVRRRequested
#         3 bIsVRRIndicatorEnabled 4 bIsDisplayInVRRMode
VRR_INFO_SIZE = 24
VRR_INFO_VER = VRR_INFO_SIZE | (1 << 16)

# NV_GPU_DISPLAYIDS (pack 4, 16B): version@0 connectorType@4 displayId@8 bitfield@12
GPUIDS_SIZE = 16
GPUIDS_VER = 16 | (3 << 16)     # NV_GPU_DISPLAYIDS_VER (VER2, version=3)
OFF_GPU_DID = 8                  # NvU32 displayId
MAX_GPUS = 64                    # NVAPI_MAX_PHYSICAL_GPUS

# NVAPI_DRS_GLOBAL_PROFILE == (NvDRSProfileHandle)-1  -> handle for GLOBAL settings
GLOBAL_PROFILE_HANDLE = 0xFFFFFFFFFFFFFFFF

# NvDRS setting-type enum: 0=DWORD 1=BINARY 2=STRING 3=WSTRING 4=QWORD
# NvDRs setting-location: 0=CURRENT 1=GLOBAL 2=BASE 3=DEFAULT

# --- NvAPI_Status well-known labels (nvapi_lite_common.h) ---------------------
# NOTE (corrected against the authoritative enum): -103 = INVALID_COMBINATION,
# -104 = NOT_SUPPORTED, END_ENUMERATION = -7 (not -103/-104 as sometimes quoted).
STATUS = {
    0: "OK", -1: "ERROR", -2: "LIBRARY_NOT_FOUND", -3: "NO_IMPLEMENTATION",
    -4: "API_NOT_INITIALIZED", -5: "INVALID_ARGUMENT",
    -6: "NVIDIA_DEVICE_NOT_FOUND", -7: "END_ENUMERATION", -8: "INVALID_HANDLE",
    -9: "INCOMPATIBLE_STRUCT_VERSION", -10: "HANDLE_INVALIDATED",
    -100: "EXPECTED_LOGICAL_GPU_HANDLE", -101: "EXPECTED_PHYSICAL_GPU_HANDLE",
    -102: "EXPECTED_DISPLAY_HANDLE", -103: "INVALID_COMBINATION",
    -104: "NOT_SUPPORTED", -132: "FILE_NOT_FOUND", -134: "INVALID_CALL",
    -136: "FUNCTION_NOT_FOUND", -137: "INVALID_USER_PRIVILEGE",
    -160: "SETTING_NOT_FOUND", -161: "SETTING_SIZE_TOO_LARGE",
    -163: "PROFILE_NOT_FOUND", -166: "EXECUTABLE_NOT_FOUND",
    -168: "DATATYPE_MISMATCH", -169: "PROFILE_REMOVED",
    -174: "INSUFFICIENT_BUFFER", -175: "ACCESS_DENIED",
    -187: "INVALID_DISPLAY_ID",
}


def status_str(code):
    code = int(code)
    lab = STATUS.get(code)
    return (f"{code} {lab}").strip() if lab else str(code)


def hexlist(hs):
    return " ".join(f"0x{h:x}" for h in hs) if hs else "(none)"


# --- raw NVAPI plumbing (GetProcAddress, per docs recommendation) --------------
_k32 = ctypes.WinDLL("kernel32")
_k32.LoadLibraryW.restype = ctypes.c_void_p
_k32.LoadLibraryW.argtypes = [ctypes.c_wchar_p]
_k32.GetProcAddress.restype = ctypes.c_void_p
_k32.GetProcAddress.argtypes = [ctypes.c_void_p, ctypes.c_char_p]


def load_dll():
    h = _k32.LoadLibraryW(NVAPI_DLL)
    if not h:
        h = _k32.LoadLibraryW(NVAPI_SYSTEM32)
    return h or None


def resolve_addr(mod, name):
    if not mod:
        return None
    try:
        return _k32.GetProcAddress(mod, name.encode("ascii")) or None
    except Exception:
        return None


_qi_cache = None


def get_qi(mod):
    """nvapi_QueryInterface(u32 id) -> c_void_p function pointer (or None)."""
    global _qi_cache
    if _qi_cache is not None:
        return _qi_cache
    addr = resolve_addr(mod, "nvapi_QueryInterface")
    if not addr:
        return None
    try:
        _qi_cache = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_uint32)(addr)
    except Exception:
        return None
    return _qi_cache


def qi_addr(mod, name):
    """Function-pointer address for name via its NVAPI method ID, or None."""
    qi = get_qi(mod)
    if not qi:
        return None
    fid = FN_IDS.get(name)
    if fid is None:
        return None
    try:
        a = qi(ctypes.c_uint32(fid))
    except Exception:
        return None
    return a or None


def get_fn(mod, name, argtypes, restype=ctypes.c_int32):
    addr = qi_addr(mod, name)
    if not addr:
        return None
    try:
        return ctypes.CFUNCTYPE(restype, *argtypes)(addr)
    except Exception:
        return None


# --- small offset helpers over a base address ---------------------------------
def put_u32(base, off, val):
    ctypes.cast(base + off, ctypes.POINTER(ctypes.c_uint32))[0] = val


def get_u32(base, off):
    return ctypes.cast(base + off, ctypes.POINTER(ctypes.c_uint32))[0]


def get_u64(base, off):
    return ctypes.cast(base + off, ctypes.POINTER(ctypes.c_uint64))[0]


def read_wstr(base, off):
    try:
        return ctypes.wstring_at(base + off)
    except Exception:
        return ""


def driver_msg(mod, code):
    f = get_fn(mod, "NvAPI_GetErrorMessage",
               [ctypes.c_int32, ctypes.c_void_p])
    if not f:
        return ""
    buf = (ctypes.c_char * 64)()
    try:
        if f(ctypes.c_int32(int(code)), ctypes.cast(buf, ctypes.c_void_p)) == 0:
            return buf.value.decode("ascii", "replace")
    except Exception:
        pass
    return ""


def setting_name(mod, sid):
    f = get_fn(mod, "NvAPI_DRS_GetSettingNameFromId",
               [ctypes.c_uint32, ctypes.c_void_p])
    if not f:
        return "?"
    buf = (ctypes.c_uint16 * UNICODE_STR_LEN)()
    try:
        if f(ctypes.c_uint32(sid), ctypes.cast(buf, ctypes.c_void_p)) == 0:
            return read_wstr(ctypes.addressof(buf), 0)
    except Exception:
        pass
    return "?"


def read_drs_value(base):
    """Parse the current-value union from an NVDRS_SETTING buffer."""
    vtype = get_u32(base, OFF_SETTING_TYPE)
    vloc = get_u32(base, OFF_SETTING_LOCATION)
    iscur = get_u32(base, OFF_IS_CURRENT_PREDEFINED)
    ispre = get_u32(base, OFF_IS_PREDEFINED_VALID)
    u32 = get_u32(base, OFF_CUR_UNION)
    u64 = get_u64(base, OFF_CUR_UNION)
    parts = [f"type={vtype}", f"loc={vloc}", f"isCur={iscur}", f"isPre={ispre}"]
    if vtype == 0:            # DWORD
        parts.append(f"dword={u32}")
    elif vtype == 4:          # QWORD
        parts.append(f"qword={u64}")
    elif vtype == 1:          # BINARY
        blen = get_u32(base, OFF_CUR_UNION)
        head = 0
        if blen:
            n = min(blen, 32)
            head = int.from_bytes(
                bytes((ctypes.c_uint8 * n).from_address(base + OFF_CUR_UNION + 4)),
                "little")
        parts.append(f"binlen={blen} head32=0x{head:x}")
    elif vtype in (2, 3):     # STRING / WSTRING
        parts.append(f"str={read_wstr(base, OFF_CUR_UNION)!r}")
    else:
        parts.append(f"u32={u32} u64={u64}")
    return " ".join(parts)


# --- the individual attempts (each runs in its own child) ---------------------
EXPORT_NAMES = ["nvapi_QueryInterface", "nvapi_Direct_GetMethod"]
ID_NAMES = list(FN_IDS)


def do_resolve():
    mod = load_dll()
    if not mod:
        return "DLL_LOAD_FAIL"
    exp = [n for n in EXPORT_NAMES if resolve_addr(mod, n)]
    missing_exp = [n for n in EXPORT_NAMES if not resolve_addr(mod, n)]
    res = {n: bool(qi_addr(mod, n)) for n in ID_NAMES}
    present = [n for n in ID_NAMES if res[n]]
    absent = [n for n in ID_NAMES if not res[n]]
    return (f"loaded=1 exports={exp if exp else '[]'} "
            f"missing_exports={missing_exp if missing_exp else '[]'} "
            f"qi_present({len(present)})=[{', '.join(present)}] "
            f"absent={absent if absent else '[]'}")


def do_init():
    mod = load_dll()
    if not mod:
        return "DLL_LOAD_FAIL"
    init = get_fn(mod, "NvAPI_Initialize", [])
    if not init:
        return "RESOLVE_FAIL NvAPI_Initialize"
    st = init()
    extra = f" msg={driver_msg(mod, st)!r}" if st != 0 else ""
    return f"init={status_str(st)}{extra}"


def _open_session(mod):
    """Return (dict-of-fns, hSession, status_line) or a failure line."""
    init = get_fn(mod, "NvAPI_Initialize", [])
    create = get_fn(mod, "NvAPI_DRS_CreateSession", [ctypes.POINTER(ctypes.c_void_p)])
    load = get_fn(mod, "NvAPI_DRS_LoadSettings", [ctypes.c_void_p])
    destroy = get_fn(mod, "NvAPI_DRS_DestroySession", [ctypes.c_void_p])
    missing = [n for n, f in [("init", init), ("create", create), ("load", load)] if not f]
    if missing:
        return None, None, None, f"RESOLVE_FAIL missing={missing}"
    st = init()
    if st != 0:
        return None, None, None, f"init={status_str(st)}"
    sess = ctypes.c_void_p()
    stc = create(ctypes.byref(sess))
    hS = sess.value
    if stc != 0 or not hS:
        return None, None, None, f"init=OK create={status_str(stc)} hS={hS}"
    stl = load(hS)
    fns = {"destroy": destroy}
    if stl != 0:
        fns["hS"] = hS
        return fns, hS, None, f"init=OK create=OK load={status_str(stl)}"
    return fns, hS, destroy, "session=OK"


def do_drs_session():
    """Pure session-read test: create + load + get-base/global, no setting read."""
    mod = load_dll()
    if not mod:
        return "DLL_LOAD_FAIL"
    fns, hS, destroy, line = _open_session(mod)
    if line is None:
        return "DLL_LOAD_FAIL"
    if hS is None:
        return line
    getbase = get_fn(mod, "NvAPI_DRS_GetBaseProfile",
                     [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)])
    getglob = get_fn(mod, "NvAPI_DRS_GetCurrentGlobalProfile",
                     [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)])
    extra = []
    if getbase:
        hp = ctypes.c_void_p()
        stb = getbase(hS, ctypes.byref(hp))
        extra.append(f"base={status_str(stb)} hP={hp.value}")
    else:
        extra.append("base=N/A")
    if getglob:
        hp = ctypes.c_void_p()
        stg = getglob(hS, ctypes.byref(hp))
        extra.append(f"curglobal={status_str(stg)} hP={hp.value}")
    else:
        extra.append("curglobal=N/A")
    if destroy:
        try:
            destroy(hS)
        except Exception:
            pass
    return line + " " + " ".join(extra)


def do_drs_get(sid, label):
    mod = load_dll()
    if not mod:
        return f"{label}: DLL_LOAD_FAIL"
    fns, hS, destroy, line = _open_session(mod)
    if hS is None:
        return f"{label}: {line}"
    name = setting_name(mod, sid)
    getbase = get_fn(mod, "NvAPI_DRS_GetBaseProfile",
                     [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)])
    getglob = get_fn(mod, "NvAPI_DRS_GetCurrentGlobalProfile",
                     [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)])
    # 4-arg modern GetSetting(hSession, hProfile, sid, NVDRS_SETTING*). The
    # hProfile MUST be a real profile handle (from GetBaseProfile /
    # GetCurrentGlobalProfile); the GLOBAL_PROFILE_HANDLE sentinel
    # (0xFFFFFFFFFFFFFFFF) is DEREFERENCED as a pointer by the driver and AVs.
    getset = get_fn(mod, "NvAPI_DRS_GetSetting",
                    [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p])
    if not getset:
        if destroy:
            destroy(hS)
        return f"{label}: RESOLVE_FAIL NvAPI_DRS_GetSetting (via nvapi_QueryInterface)"

    def fresh_buf():
        buf = (ctypes.c_char * (NVDRS_SETTING_SIZE + 1024))()
        base = ctypes.addressof(buf)
        put_u32(base, OFF_VERSION, NVDRS_SETTING_VER)
        put_u32(base, OFF_SETTING_ID, sid)
        return buf, base

    attempts = []

    def read_with(hP, tag):
        buf, base = fresh_buf()
        st = getset(hS, hP, ctypes.c_uint32(sid), ctypes.cast(buf, ctypes.c_void_p))
        val = f" val=[{read_drs_value(base)}]" if st == 0 else ""
        return f"{tag}={status_str(st)}{val}"

    # global read via the CURRENT-GLOBAL profile handle (never the sentinel)
    if getglob:
        hp = ctypes.c_void_p()
        stg = getglob(hS, ctypes.byref(hp))
        attempts.append(read_with(hp.value, "global")
                        if stg == 0 and hp.value
                        else f"global=getglob={status_str(stg)}")
    else:
        attempts.append("global=N/A(no GetCurrentGlobalProfile)")

    # base read via the BASE profile handle
    if getbase:
        hp = ctypes.c_void_p()
        stb = getbase(hS, ctypes.byref(hp))
        attempts.append(read_with(hp.value, "base")
                        if stb == 0 and hp.value
                        else f"base=getbase={status_str(stb)}")
    else:
        attempts.append("base=N/A(no GetBaseProfile)")

    if destroy:
        try:
            destroy(hS)
        except Exception:
            pass
    head = attempts[0] if attempts else "none"
    first_code = head.split("=", 1)[1].split(" ", 1)[0]
    msg = driver_msg(mod, first_code) if first_code.lstrip("-").isdigit() else ""
    return (f"{label}(id=0x{sid:x},name={name}) " + " ".join(attempts) +
            (f" msg={msg!r}" if msg else ""))


def do_enum():
    mod = load_dll()
    if not mod:
        return "DLL_LOAD_FAIL"
    init = get_fn(mod, "NvAPI_Initialize", [])
    enum = get_fn(mod, "NvAPI_EnumNvidiaDisplayHandle",
                  [ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)])
    if not init or not enum:
        return f"RESOLVE_FAIL init={bool(init)} enum={bool(enum)}"
    st = init()
    if st != 0:
        return f"init={status_str(st)}"
    handles = []
    for i in range(32):
        h = ctypes.c_void_p()
        stc = enum(ctypes.c_uint32(i), ctypes.byref(h))
        if stc != 0:
            if stc == -7:  # END_ENUMERATION
                break
            return f"init=OK idx={i} first_err={status_str(stc)} handles={hexlist(handles)}"
        if h.value:
            handles.append(h.value)
        else:
            break
    return f"init=OK count={len(handles)} handles={hexlist(handles)}"


def do_vrrinfo():
    mod = load_dll()
    if not mod:
        return "DLL_LOAD_FAIL"
    init = get_fn(mod, "NvAPI_Initialize", [])
    gvr = get_fn(mod, "NvAPI_Disp_GetVRRInfo", [ctypes.c_uint32, ctypes.c_void_p])
    enumgpu = get_fn(mod, "NvAPI_EnumPhysicalGPUs",
                     [ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint32)])
    getids = get_fn(mod, "NvAPI_GPU_GetConnectedDisplayIds",
                    [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint32])
    enumdisp = get_fn(mod, "NvAPI_EnumNvidiaDisplayHandle",
                      [ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)])
    if not init or not gvr:
        return "RESOLVE_FAIL init/gvr"
    st = init()
    if st != 0:
        return f"init={status_str(st)}"

    # GetVRRInfo's displayId is the "combined physical display + GPU id" from
    # NvAPI_GPU_GetConnectedDisplayIds -- NOT the low-32 of NvDisplayHandle
    # (that yields -187 INVALID_DISPLAY_ID).
    display_ids = []
    note = "gpu-enum-unavailable"
    if enumgpu and getids:
        gpuarr = (ctypes.c_void_p * MAX_GPUS)()
        cnt = ctypes.c_uint32(MAX_GPUS)
        stg = enumgpu(ctypes.cast(gpuarr, ctypes.POINTER(ctypes.c_void_p)),
                      ctypes.byref(cnt))
        gpus = [gpuarr[i] for i in range(min(cnt.value, MAX_GPUS)) if gpuarr[i]]
        if stg != 0:
            note = f"enumgpus={status_str(stg)}"
        elif not gpus:
            note = "0-gpus"
        else:
            note = f"{len(gpus)}-gpu"
            for gh in gpus:
                c1 = ctypes.c_uint32(0)
                stc = getids(gh, None, ctypes.byref(c1), ctypes.c_uint32(0))
                n = c1.value
                if stc != 0 or n == 0:
                    continue
                buf = (ctypes.c_char * (GPUIDS_SIZE * n + 64))()
                base = ctypes.addressof(buf)
                for j in range(n):
                    put_u32(base + j * GPUIDS_SIZE, 0, GPUIDS_VER)
                c2 = ctypes.c_uint32(n)
                stc2 = getids(gh, ctypes.cast(buf, ctypes.c_void_p),
                              ctypes.byref(c2), ctypes.c_uint32(0))
                if stc2 == 0:
                    for j in range(min(c2.value, n)):
                        did = get_u32(base + j * GPUIDS_SIZE, OFF_GPU_DID)
                        if did:
                            display_ids.append(did)
    if not display_ids and enumdisp:
        for i in range(32):
            h = ctypes.c_void_p()
            stc = enumdisp(ctypes.c_uint32(i), ctypes.byref(h))
            if stc != 0:
                break
            if h.value:
                display_ids.append(int(h.value) & 0xFFFFFFFF)
        if display_ids:
            note += " +handle-fallback"
    if not display_ids:
        return f"init=OK no-displayIds ({note})"
    parts = []
    for did in display_ids:
        buf = (ctypes.c_char * (VRR_INFO_SIZE + 64))()
        base = ctypes.addressof(buf)
        put_u32(base, 0, VRR_INFO_VER)
        st2 = gvr(ctypes.c_uint32(did), ctypes.cast(buf, ctypes.c_void_p))
        if st2 == 0:
            word = get_u32(base, 4)
            # E=enabled P=possible R=requested I=indicator M=inVRRMode
            fl = (f"E{int(word & 1)}P{int(word & 2 >> 1)}"
                  f"R{int(word & 4 >> 2)}I{int(word & 8 >> 3)}M{int(word & 16 >> 4)}")
            parts.append(f"0x{did:x}[{fl}]")
        else:
            parts.append(f"0x{did:x}:{status_str(st2)}")
    return f"{note} " + " ".join(parts)


# --- child / driver split -----------------------------------------------------
STEPS = [
    ("resolve", []),
    ("init", []),
    ("drs_session", []),
    ("get:VRR_MODE", [str(ID_VRR_MODE)]),
    ("get:VRR_REQUEST_STATE", [str(ID_VRR_REQUEST_STATE)]),
    ("get:VRR_APP_OVERRIDE", [str(ID_VRR_APP_OVERRIDE)]),
    ("enum_displays", []),
    ("vrrinfo", []),
]


def child_main(step, args):
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except Exception:
        pass
    pid = os.getpid()

    def emit(s):
        print(f"pid={pid} step={step} {s}")
        sys.stdout.flush()

    try:
        if step == "resolve":
            emit(do_resolve())
        elif step == "init":
            emit(do_init())
        elif step == "drs_session":
            emit(do_drs_session())
        elif step.startswith("get:"):
            label = step[4:]
            sid = int(args[0], 0) if args else 0
            emit(do_drs_get(sid, label))
        elif step == "enum_displays":
            emit(do_enum())
        elif step == "vrrinfo":
            emit(do_vrrinfo())
        else:
            emit("unknown step")
    except BaseException as e:  # Python-level; native AVs are NOT caught here
        emit(f"EXC {type(e).__name__}: {e}")
    return 0


def run_child(py, script, step, *args):
    cmd = [py, script, "--child", step] + [str(a) for a in args]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return "TIMEOUT(90s)"
    except Exception as e:
        return f"SPAWN_EXC {type(e).__name__}: {e}"
    out = (p.stdout or "").strip()
    if p.returncode != 0:  # native crash (e.g. AV) -> this child is the casualty
        tail = out.splitlines()[-1].strip() if out else ""
        return f"CRASH rc={p.returncode} {tail}"
    return out or "(no output)"


def driver_main():
    if os.name != "nt":
        print("Windows only (nvapi64.dll). Skipping.")
        return 0
    py = VENV_PY if os.path.exists(VENV_PY) else sys.executable
    script = os.path.abspath(__file__)
    print("=== gsync_probe: READ-ONLY NVAPI/DRS VRR feasibility (unprivileged) ===")
    print(f"python={py} venv_shim={os.path.exists(VENV_PY)} script={script}")
    print(f"nvapi={NVAPI_DLL}  READ-ONLY (0 SET calls)  nonzero codes = FINDINGS (raw)")
    for step, args in STEPS:
        print("[child] " + run_child(py, script, step, *args))
    print("=== end ===")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--child":
        sys.exit(child_main(sys.argv[2], sys.argv[3:]))
    else:
        sys.exit(driver_main())
