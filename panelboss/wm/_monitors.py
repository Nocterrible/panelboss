"""The monitor side: enumeration by EDID identity, the topology
fingerprint, the movable-window list, and the naive re-open a pin
uses. Formerly wm.py lines 349-424 and the private shell32 block of
lines 434-459; `place` moved to _restore.py (it wraps _move) to keep
the part graph acyclic - its body is verbatim."""

import ctypes
from ctypes import wintypes

from ._inspect import _toplevel_facts, wanted
from ._winapi import (DEVMODEW, DISPLAY_DEVICEW,
                      DISPLAY_DEVICE_ATTACHED_TO_DESKTOP,
                      DISPLAY_DEVICE_MIRRORING_DRIVER,
                      DISPLAY_DEVICE_PRIMARY_DEVICE,
                      ENUM_CURRENT_SETTINGS, SW_SHOWNORMAL, byref,
                      sizeof, u32)


def _short_id(monitor_id):
    """"MONITOR\\AOC2790\\{...}\\0009" -> "AOC2790": the model token is
    the only part of the EDID path a human can read."""
    parts = str(monitor_id).split("\\")
    if len(parts) >= 2 and parts[0].upper() == "MONITOR":
        return parts[1]
    return str(monitor_id)[:24]


def _row_is_virtual(adapter_id):
    """Is this row a virtual (software-emitted) canvas, not a panel on
    a physical bus? The bus-root test, measured live on this box:
    RDP = SWD\\REMOTEDISPLAYENUM\\RDPIDD..., every name-able indirect
    = ROOT\\DISPLAY\\, real panels = PCI\\VEN_. Slots renumber (KVM),
    names LIE (any IddCx driver picks its own token), and the
    physical-monitor DDC door LIES (the fake bus answers nphys=1,
    reachable=True) - the bus root is the only survivor."""
    a = str(adapter_id or "").upper().replace("#", "\\")
    return not a.startswith(("PCI\\", "ACPI\\"))


def monitors():
    """Every attached monitor as {id, short, gdi, x, y, w, h, rate,
    bits, primary, adapter_id, virtual}. The identity is the MONITOR
    DeviceID (EDID-derived serial/model), not the \\.\DISPLAYn slot -
    slots get reshuffled by reconnect storms, the panel's own ID does
    not. The virtual flag is the row's bus-root truth: every
    per-monitor consumer reads m["virtual"] for free."""
    out = []
    i = 0
    while True:
        d = DISPLAY_DEVICEW()
        d.cb = sizeof(d)
        if not u32.EnumDisplayDevicesW(None, i, byref(d), 0):
            break
        i += 1
        if d.StateFlags & DISPLAY_DEVICE_MIRRORING_DRIVER:
            continue                       # the mirror of a real one
        if not d.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP:
            continue                       # not part of the desk
        monitor_id = d.DeviceID             # adapter identity as the
        sub = DISPLAY_DEVICEW()             # rest; the monitor under
        sub.cb = sizeof(sub)                # it knows better
        if u32.EnumDisplayDevicesW(d.DeviceName, 0, byref(sub), 0):
            monitor_id = sub.DeviceID or monitor_id
        dm = DEVMODEW()
        dm.dmSize = sizeof(dm)
        if not u32.EnumDisplaySettingsW(d.DeviceName,
                                        ENUM_CURRENT_SETTINGS,
                                        byref(dm)):
            continue                       # no current mode to place
        out.append({"id": monitor_id, "short": _short_id(monitor_id),
                    "gdi": d.DeviceName,
                    "x": dm.display.dmPosition.x,
                    "y": dm.display.dmPosition.y,
                    "w": int(dm.dmPelsWidth), "h": int(dm.dmPelsHeight),
                    "rate": int(dm.dmDisplayFrequency),
                    "bits": int(dm.dmBitsPerPel),
                    "primary": bool(d.StateFlags
                                    & DISPLAY_DEVICE_PRIMARY_DEVICE),
                    "adapter_id": d.DeviceID,
                    "virtual": _row_is_virtual(d.DeviceID)})
    return out


def monitor_for(rect):
    """The monitor owning a rect's centre - for labelling profile
    rows, nothing leans on the answer."""
    if not rect:
        return None
    cx, cy = rect[0] + rect[2] // 2, rect[1] + rect[3] // 2
    for m in monitors():
        if m["x"] <= cx < m["x"] + m["w"] and m["y"] <= cy < m["y"] + m["h"]:
            return m
    return None


def fingerprint():
    """Topology as one string: every monitor's hardware ID, place
    and size. Reconnecting the same monitor reproduces it exactly;
    swapping or unplugging one for good changes it - and then the
    saved rects belong to a desk that no longer exists."""
    return "|".join(sorted(
        "%s@%d,%d %dx%d%s" % (m["id"], m["x"], m["y"], m["w"], m["h"],
                              "P" if m["primary"] else "")
        for m in monitors()))


def list_windows():
    """Every window the app dares to move (wanted's rules), with the
    identity fields a profile needs."""
    return [w for w in _toplevel_facts() if wanted(w)]


# A PRIVATE shell32 handle: windll.shell32 is the one power.py already
# calls ShellExecuteW("runas") through, and argtypes bound there would
# bind there too (the user32 trap, learned the hard way). WinDLL() hands
# out a fresh copy whose prototype belongs to us alone.
_shell32 = ctypes.WinDLL("shell32")
_shell32.ShellExecuteW.restype = ctypes.c_int
_shell32.ShellExecuteW.argtypes = [wintypes.HWND, ctypes.c_wchar_p,
                                   ctypes.c_wchar_p, ctypes.c_wchar_p,
                                   ctypes.c_wchar_p, ctypes.c_int]


def launch(exe_path):
    """The naive re-open a pin with 'open it' makes: shell-execute
    the exe exactly as double-clicking it in Explorer would (so .lnk
    and app paths behave as they do for a human). Honest about its
    limits: store apps and stub-launchers start NOTHING under this
    name - the caller waits for a window and must not wait forever.
    Returns "" or the reason it could not even try."""
    if not exe_path:
        return "no exe path was saved for this pin"
    ret = _shell32.ShellExecuteW(None, "open", exe_path, None, None,
                                 SW_SHOWNORMAL)
    if ret <= 32:
        return "the shell refused to start %s (error %d)" % (
            exe_path.split("\\")[-1], ret)
    return ""
