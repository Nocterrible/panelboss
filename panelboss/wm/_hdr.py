"""Color state: the SendInput hotkey fallback first (the app only
ever SENDS the key there), then the DisplayConfig route that reads
HDR back for real, plus the per-monitor SET. Formerly wm.py lines
637-900; the import-time size asserts are kept verbatim - a wrong
size is a silent overwrite, not an error."""

import ctypes
from ctypes import wintypes

from ._winapi import sizeof, u32


# ------------------------------------------------------------- HDR ------
# The C# project's honest conclusion: there is no API it could reach
# that reads HDR back, only the Win+Alt+B hotkey (which has moved
# between Windows versions, hence the configurable key), so the app
# only ever SENDS the key and keeps its own belief about the state.
# Same deal here: press when the belief disagrees with the profile,
# flip the belief, never claim to know.
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1
VK = {"win": 0x5B, "windows": 0x5B, "alt": 0x12, "ctrl": 0x11,
      "control": 0x11, "shift": 0x10}


class KEYBDINPUT(ctypes.Structure):
    """The x64 INPUT for a keyboard event: 40 bytes exactly (their
    C# pins it with Size=40) - a smaller struct is not INPUT-shaped
    and SendInput refuses it in silence."""
    _fields_ = [("type", wintypes.UINT), ("pad", wintypes.UINT),
                ("vk", wintypes.USHORT), ("scan", wintypes.USHORT),
                ("flags", wintypes.UINT), ("time", wintypes.UINT),
                ("extra", ctypes.c_ulonglong),
                ("tail", ctypes.c_ulonglong)]


assert ctypes.sizeof(KEYBDINPUT) == 40, "INPUT drift, SendInput is blind"


def press_keys(combination):
    """Press a combination ("win+alt+b"): every key down, then up in
    reverse, one SendInput batch. Returns the trouble string (empty
    = the batch was accepted - whether HDR followed is, again,
    unknowable from here)."""
    keys = []
    for part in combination.lower().replace("-", "+").split("+"):
        part = part.strip()
        if not part:
            continue
        if part in VK:
            keys.append(VK[part])
        elif len(part) == 1 and part.isalnum():
            keys.append(ord(part.upper()))
        elif part.startswith("f") and len(part) <= 3 \
                and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            keys.append(0x70 + int(part[1:]) - 1)
    if not keys:
        return "'%s' is not a key combination like win+alt+b" \
            % combination
    batch = (KEYBDINPUT * (len(keys) * 2))()
    for i, vk in enumerate(keys):
        batch[i] = KEYBDINPUT(INPUT_KEYBOARD, 0, vk, 0, 0, 0, 0)
        batch[len(keys) * 2 - 1 - i] = KEYBDINPUT(
            INPUT_KEYBOARD, 0, vk, 0, KEYEVENTF_KEYUP, 0, 0)
    u32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p,
                              ctypes.c_int]
    n = u32.SendInput(len(batch), batch, sizeof(KEYBDINPUT))
    if n != len(batch):
        return "windows took %d of %d key events" % (n, len(batch))
    return ""


# ------------------------------------------------- HDR, actually read --
# The research result, measured HERE (October 2026): Windows reports
# per-monitor HDR through the DisplayConfig device-info API. Type 15,
# GET_ADVANCED_COLOR_INFO_2 (build 26100+), carries the truth field:
# activeColorMode SDR=0 / WCG=1 / HDR=2, plus a value bitmask whose
# bit 4 says whether the panel can do HDR at all. The old type 9 is
# NOT HDR - it is "advanced color", HDR and wide-gamut merged; on
# this desk it answers supported+enabled for a monitor that has no
# HDR whatsoever. So: ask 15 first; a refusal (50) means an old OS
# and only then the hotkey-with-belief below is the honest path.
# The join rules, from the same measured source: the adapter/id the
# header must carry come from the TARGET's MODE entry (the source
# side is the GPU's), and the monitor is named by the DISPLAY#<model>#
# segment of the target device path - never by the friendly name
# (which is a marketing string: this desk's IOC912B calls itself
# "GA27W1Q"). Sizes are asserted at import exactly like every other
# struct here: a wrong size is not an error, it is a silent overwrite.
class LUID(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.LONG)]


class DC_RATIONAL(ctypes.Structure):
    _fields_ = [("num", wintypes.UINT), ("den", wintypes.UINT)]


class DC_HEADER(ctypes.Structure):
    _fields_ = [("type", wintypes.UINT), ("size", wintypes.UINT),
                ("adapter", LUID), ("id", wintypes.UINT)]


class DC_SOURCE_NAME(ctypes.Structure):
    _fields_ = [("header", DC_HEADER), ("name", wintypes.WCHAR * 32)]


class DC_TARGET_NAME(ctypes.Structure):
    _fields_ = [("header", DC_HEADER), ("flags", wintypes.UINT),
                ("tech", wintypes.UINT),
                ("edid_man", wintypes.USHORT),
                ("edid_prod", wintypes.USHORT),
                ("connector", wintypes.UINT),
                ("friendly", wintypes.WCHAR * 64),
                ("path", wintypes.WCHAR * 128)]


class DC_COLOR_INFO(ctypes.Structure):          # type 9 payload
    _fields_ = [("header", DC_HEADER), ("value", wintypes.UINT),
                ("encoding", wintypes.UINT), ("bits", wintypes.UINT)]


class DC_COLOR_INFO_2(ctypes.Structure):        # type 15, 24H2+
    _fields_ = [("header", DC_HEADER), ("value", wintypes.UINT),
                ("encoding", wintypes.UINT), ("bits", wintypes.UINT),
                ("mode", wintypes.UINT)]        # 0 SDR / 1 WCG / 2 HDR


class DC_SET_STATE(ctypes.Structure):           # types 10 and 16
    _fields_ = [("header", DC_HEADER), ("value", wintypes.UINT)]


class DC_PATH_SOURCE(ctypes.Structure):
    _fields_ = [("adapter", LUID), ("id", wintypes.UINT),
                ("modeIdx", wintypes.UINT), ("status", wintypes.UINT)]


class DC_PATH_TARGET(ctypes.Structure):
    _fields_ = [("adapter", LUID), ("id", wintypes.UINT),
                ("modeIdx", wintypes.UINT), ("tech", wintypes.UINT),
                ("rotation", wintypes.UINT), ("scaling", wintypes.UINT),
                ("rate", DC_RATIONAL), ("order", wintypes.UINT),
                ("avail", wintypes.INT), ("status", wintypes.UINT)]


class DC_PATH(ctypes.Structure):
    _fields_ = [("src", DC_PATH_SOURCE), ("tgt", DC_PATH_TARGET),
                ("flags", wintypes.UINT)]


class DC_MODE(ctypes.Structure):
    _fields_ = [("kind", wintypes.UINT), ("id", wintypes.UINT),
                ("adapter", LUID), ("tail", ctypes.c_char * 48)]


for _n, _s, _want in (("DC_HEADER", DC_HEADER, 20), ("DC_MODE", DC_MODE, 64),
                      ("DC_PATH", DC_PATH, 72), ("DC_COLOR_INFO",
                                                 DC_COLOR_INFO, 32),
                      ("DC_COLOR_INFO_2", DC_COLOR_INFO_2, 36),
                      ("DC_SET_STATE", DC_SET_STATE, 24),
                      ("DC_SOURCE_NAME", DC_SOURCE_NAME, 84),
                      ("DC_TARGET_NAME", DC_TARGET_NAME, 420)):
    assert ctypes.sizeof(_s) == _want, "DisplayConfig layout drift: %s" % _n

QDC_ONLY_ACTIVE_PATHS = 0x2
DCI_GET_SOURCE_NAME = 1
DCI_GET_TARGET_NAME = 2
DCI_GET_ADVANCED_COLOR_INFO = 9
DCI_SET_ADVANCED_COLOR_STATE = 10
DCI_GET_ADVANCED_COLOR_INFO_2 = 15
DCI_SET_HDR_STATE = 16
ERROR_NOT_SUPPORTED = 50
u32.GetDisplayConfigBufferSizes.argtypes = [
    wintypes.UINT, ctypes.POINTER(wintypes.UINT),
    ctypes.POINTER(wintypes.UINT)]
u32.GetDisplayConfigBufferSizes.restype = ctypes.c_long
u32.QueryDisplayConfig.argtypes = [
    wintypes.UINT, ctypes.POINTER(wintypes.UINT),
    ctypes.POINTER(DC_PATH), ctypes.POINTER(wintypes.UINT),
    ctypes.POINTER(DC_MODE), ctypes.c_void_p]
u32.QueryDisplayConfig.restype = ctypes.c_long
u32.DisplayConfigGetDeviceInfo.argtypes = [ctypes.POINTER(DC_HEADER)]
u32.DisplayConfigGetDeviceInfo.restype = ctypes.c_long
u32.DisplayConfigSetDeviceInfo.argtypes = [ctypes.POINTER(DC_HEADER)]
u32.DisplayConfigSetDeviceInfo.restype = ctypes.c_long


def _dc_targets():
    """Every active display path as rows {gdi, model, adapter, id} -
    adapter/id the TARGET-side mode coordinates, the only ones the
    advanced-color calls accept."""
    n_path, n_mode = wintypes.UINT(0), wintypes.UINT(0)
    if u32.GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS,
                                       ctypes.byref(n_path),
                                       ctypes.byref(n_mode)) != 0:
        return []
    paths = (DC_PATH * n_path.value)()
    modes = (DC_MODE * n_mode.value)()
    if u32.QueryDisplayConfig(QDC_ONLY_ACTIVE_PATHS,
                              ctypes.byref(n_path), paths,
                              ctypes.byref(n_mode), modes,
                              None) != 0:
        return []
    out = []
    for p in paths:
        if p.tgt.modeIdx == 0xFFFFFFFF or p.tgt.modeIdx >= n_mode.value:
            continue
        src = DC_SOURCE_NAME()
        src.header.type, src.header.size = DCI_GET_SOURCE_NAME, \
            ctypes.sizeof(src)
        src.header.adapter, src.header.id = p.src.adapter, p.src.id
        if u32.DisplayConfigGetDeviceInfo(ctypes.byref(src.header)):
            continue
        tgt = DC_TARGET_NAME()
        tgt.header.type, tgt.header.size = DCI_GET_TARGET_NAME, \
            ctypes.sizeof(tgt)
        tgt.header.adapter, tgt.header.id = p.tgt.adapter, p.tgt.id
        u32.DisplayConfigGetDeviceInfo(ctypes.byref(tgt.header))
        model = tgt.path.split("#")[1] if "#" in tgt.path else ""
        m = modes[p.tgt.modeIdx]
        out.append({"gdi": src.name, "model": model,
                    "adapter": m.adapter, "id": m.id})
    return out


def hdr_states():
    """One row per attached monitor: {gdi, model, supported, state,
    precise}. state is "on"/"off" (and "supported" says whether the
    panel could do it); on a pre-24H2 OS precise is False and state
    is "unknown" - the old API answers about HDR-or-wide-gamut
    merged, which is not a fact worth believing (measured: it says
    enabled on this desk's HDR-less third monitor)."""
    out = []
    for t in _dc_targets():
        a = DC_COLOR_INFO_2()
        a.header.type, a.header.size = DCI_GET_ADVANCED_COLOR_INFO_2, \
            ctypes.sizeof(a)
        a.header.adapter, a.header.id = t["adapter"], t["id"]
        if u32.DisplayConfigGetDeviceInfo(ctypes.byref(a.header)) == 0:
            out.append({"gdi": t["gdi"], "model": t["model"],
                        "supported": bool(a.value & 0x10),
                        "state": "on" if a.mode == 2 else
                        ("off" if a.mode in (0, 1) else "unknown"),
                        "mode": a.mode, "precise": True})
            continue
        b = DC_COLOR_INFO()
        b.header.type, b.header.size = DCI_GET_ADVANCED_COLOR_INFO, \
            ctypes.sizeof(b)
        b.header.adapter, b.header.id = t["adapter"], t["id"]
        rc = u32.DisplayConfigGetDeviceInfo(ctypes.byref(b.header))
        out.append({"gdi": t["gdi"], "model": t["model"],
                    "supported": bool(b.value & 1) if rc == 0 else False,
                    "state": "unknown", "mode": None,
                    "precise": False})
    return out


def hdr_set(gdi, on):
    """Command HDR on one monitor (type 16, build 24H2+): a real
    SET, not the hotkey's toggle-in-the-dark. Returns the trouble
    string ('' = accepted - believe the read-back afterwards, as
    always). Changing HDR re-enumerates the display paths, so this
    re-walks the topology every call and never trusts a cached id."""
    for t in _dc_targets():
        if t["gdi"] != gdi:
            continue
        s = DC_SET_STATE()
        s.header.type, s.header.size = DCI_SET_HDR_STATE, ctypes.sizeof(s)
        s.header.adapter, s.header.id = t["adapter"], t["id"]
        s.value = 1 if on else 0
        rc = u32.DisplayConfigSetDeviceInfo(ctypes.byref(s.header))
        if rc == 0:
            return ""
        return ("the monitor refuses the change (error %d)" % rc
                if rc != ERROR_NOT_SUPPORTED
                else "this monitor cannot do HDR")
    return "no active display path for %s any more" % gdi
