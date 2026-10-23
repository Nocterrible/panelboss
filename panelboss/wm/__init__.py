"""Window and topology memory: the fix for monitors that fully
disconnect when they sleep.

Some panels unplug themselves from Windows on standby. Everything on
them survives in limbo, and when the display returns Windows re-lays
the desk - windows land on the wrong screen, resized, maximized
somewhere they never lived. The app owns the off edge (it fires the
broadcast while the truth is still intact) and hears about the on
edge from every source (its own wake, the camera, a jiggle through
the display watcher, the power button after a sleep), so it can
remember and hand back:

  off    snapshot every top-level window's pixel rect plus a
         fingerprint of the monitor set (hardware IDs + places)
  wake   wait for the topology to SETTLE (the reconnect storm relays
         windows while it runs; applying mid-storm just hands the
         re-layout more material), and only when the fingerprint is
         the one that was saved - the same monitors, same places.
         Then move everything back.

Honest limits, all fail-open: a different fingerprint (a monitor
swapped, unplugged for good) means the saved rects belong to a desk
that no longer exists - nothing is moved. Minimized windows are left
alone (they were not seen; Windows re-places them on the user's own
restore). Owned popups follow their owner's story. Cloaked windows
live on another virtual desktop and must not be dragged across.
Windows that went away in the dark are skipped, and Windows's own
correct placement is respected (same rect = no move).

The monitor side speaks EnumDisplayDevices/EnumDisplaySettings -
the path proven on this machine by the neighboring monitor_control
project. GetMonitorInfoW's old reputation here ("error 87, fails for
every struct shape") was a struct-size bug, not an API truth: the
2026-10-14 dxva2 probe drove it green with a cbSize-exact
MONITORINFOEXW, and wm/_bright.py rides that mapping today; the
DEVMODE route stays the identity source because it carries the EDID
identity of the physical panel, which the \\.\DISPLAYn slot names do
not.

This is the old single-module wm, kept as the same namespace: subject
parts own their pieces, every old name still resolves here, and the
module class at the bottom fans attribute WRITES through to the parts
- the suites patch this namespace (wm.time, wm.u32, wm._move, ...)
and the bodies' bare-name call sites must keep seeing those patches,
exactly as they did when there was only one module to patch.
"""

import ctypes
import logging
import sys
import threading
import time
from ctypes import wintypes

from . import (_bright, _detect, _displaycfg, _hdr, _inspect,
               _monitors, _overlay, _rescue, _restore, _sessions, _sdc,
               _winapi)

from ._winapi import (DEVMODEW, DISPLAY_DEVICEW,
                      DISPLAY_DEVICE_ATTACHED_TO_DESKTOP,
                      DISPLAY_DEVICE_MIRRORING_DRIVER,
                      DISPLAY_DEVICE_PRIMARY_DEVICE, DWMWA_CLOAKED,
                      ENUM_CURRENT_SETTINGS, FURNITURE_PREFIX,
                      GA_ROOT, GWL_EXSTYLE, GWL_STYLE, LOST_EDGE,
                      POINTL, PROCESS_QUERY_INFORMATION,
                      PROCESS_QUERY_LIMITED_INFORMATION,
                      PROCESS_VM_READ, RECT, SWP_NOACTIVATE,
                      SWP_NOOWNERZORDER, SWP_NOZORDER,
                      SWP_SHOWWINDOW, SW_SHOWMAXIMIZED,
                      SW_SHOWNORMAL, SW_RESTORE, WS_CHILD,
                      WS_EX_TOOLWINDOW, WS_EX_TRANSPARENT, WNDENUMPROC,
                      WINDOWPLACEMENT, _DisplayFields, _PrinterFields, _TYPED,
                      _DevmodeUnion, byref, dwm, k32, sizeof, u32)

from ._inspect import (_class_name, _cloaked, _facts, _proc_info,
                       _toplevel_facts, proc_name, true_rect,
                                              wanted, win_title)

from ._monitors import (_shell32, _short_id, display_vendor_is_nvidia,
                        display_vendor_scan, fingerprint, launch,
                        list_windows, monitor_for, monitors)

from ._sessions import (WTS_SESSION_INFOW, remote_session_ids,
                        session_connected, session_is_remote)

from ._displaycfg import (CDS_NORESET, CDS_SET_PRIMARY, CDS_TEST,
                          CDS_UPDATEREGISTRY, DM_DISPLAYFREQUENCY,
                          DM_PELSWIDTH, DM_PELSHEIGHT, DM_POSITION,
                          DISP_CHANGE_RESTART, DISP_CHANGE_SUCCESSFUL,
                          ENUM_REGISTRY_SETTINGS, apply_layout,
                          current_mode, offered_modes, set_mode)

from ._hdr import (DCI_GET_ADVANCED_COLOR_INFO,
                   DCI_GET_ADVANCED_COLOR_INFO_2,
                   DCI_GET_SOURCE_NAME, DCI_GET_TARGET_NAME,
                   DCI_SET_ADVANCED_COLOR_STATE, DCI_SET_HDR_STATE,
                   DC_COLOR_INFO, DC_COLOR_INFO_2, DC_HEADER,
                   DC_MODE, DC_PATH, DC_PATH_SOURCE, DC_PATH_TARGET,
                   DC_RATIONAL, DC_SET_STATE, DC_SOURCE_NAME,
                   DC_TARGET_NAME, ERROR_NOT_SUPPORTED, INPUT_KEYBOARD,
                   KEYBDINPUT, KEYEVENTF_KEYUP, LUID,
                   QDC_ONLY_ACTIVE_PATHS, VK, _dc_targets, _n, _s,
                   _want, hdr_caps, hdr_set, hdr_set_model,
                   hdr_states, press_keys)

from ._rescue import GRAB_EDGE, lost, rescue_lost

from ._restore import (SETTLE_SEC, WAIT_BUDGET_SEC, _move, apply,
                       place, restore, restore_async, snapshot,
                       wait_settled)

from ._detect import foreground, has_xinput

log = logging.getLogger("wm")

# SIZE LAW note: this facade is ~175 lines and the bulk IS the
# contract - the old docstring (history-bearing) plus the re-export
# roster every caller and test-patch site leans on. Splitting the
# roster out would hide the contract behind an indirection.
__all__ = [
    "CDS_NORESET", "CDS_SET_PRIMARY", "CDS_TEST", "CDS_UPDATEREGISTRY",
    "DCI_GET_ADVANCED_COLOR_INFO", "DCI_GET_ADVANCED_COLOR_INFO_2",
    "DCI_GET_SOURCE_NAME", "DCI_GET_TARGET_NAME",
    "DCI_SET_ADVANCED_COLOR_STATE", "DCI_SET_HDR_STATE", "DC_COLOR_INFO",
    "DC_COLOR_INFO_2", "DC_HEADER", "DC_MODE", "DC_PATH",
    "DC_PATH_SOURCE", "DC_PATH_TARGET", "DC_RATIONAL", "DC_SET_STATE",
    "DC_SOURCE_NAME", "DC_TARGET_NAME", "DEVMODEW",
    "DISPLAY_DEVICEW", "DISPLAY_DEVICE_ATTACHED_TO_DESKTOP",
    "DISPLAY_DEVICE_MIRRORING_DRIVER", "DISPLAY_DEVICE_PRIMARY_DEVICE",
    "DM_DISPLAYFREQUENCY", "DM_PELSWIDTH", "DM_PELSHEIGHT",
    "DM_POSITION", "DWMWA_CLOAKED", "DISP_CHANGE_RESTART",
    "DISP_CHANGE_SUCCESSFUL", "ENUM_CURRENT_SETTINGS",
    "ENUM_REGISTRY_SETTINGS", "ERROR_NOT_SUPPORTED", "FURNITURE_PREFIX",
    "GA_ROOT", "GRAB_EDGE", "GWL_EXSTYLE", "GWL_STYLE", "INPUT_KEYBOARD",
    "KEYBDINPUT", "KEYEVENTF_KEYUP", "LOST_EDGE", "LUID", "POINTL",
    "PROCESS_QUERY_INFORMATION", "PROCESS_QUERY_LIMITED_INFORMATION",
    "PROCESS_VM_READ", "QDC_ONLY_ACTIVE_PATHS", "RECT", "SETTLE_SEC",
    "SWP_NOACTIVATE", "SWP_NOOWNERZORDER", "SWP_NOZORDER",
    "SWP_SHOWWINDOW",
    "SW_SHOWMAXIMIZED", "SW_SHOWNORMAL", "SW_RESTORE", "VK",
    "WAIT_BUDGET_SEC", "WS_CHILD", "WS_EX_TOOLWINDOW",
    "WS_EX_TRANSPARENT", "WNDENUMPROC", "WINDOWPLACEMENT", "apply", "apply_layout",
    "byref", "ctypes", "current_mode", "display_vendor_is_nvidia",
    "display_vendor_scan", "dwm", "foreground",
    "fingerprint", "has_xinput", "k32", "launch", "list_windows",
    "log", "lost", "monitor_for", "monitors", "offered_modes",
    "place", "proc_name", "press_keys", "rescue_lost", "restore",
    "restore_async", "remote_session_ids", "set_mode",
    "session_connected", "session_is_remote",
    "sizeof", "snapshot", "threading", "time", "true_rect", "u32",
    "wait_settled", "wanted", "win_title", "WTS_SESSION_INFOW",
    "wintypes",
]

_FANOUT = (_winapi, _inspect, _monitors, _displaycfg, _hdr, _rescue,
           _restore, _detect, _bright, _overlay, _sdc, _sessions)


class _WmPackage(type(sys.modules[__name__])):
    """Module subclass: a write to this namespace rebinds the name in
    every part that holds it. The suites monkey-patch wm (time, u32,
    _move, fingerprint, ...), and those names resolve as bare globals
    inside OTHER parts' bodies; copying them onto the facade alone
    would fork the state - internal calls keep answering to the old
    object. Reads need no magic: the re-exports are the parts' own
    objects."""

    def __setattr__(self, name, value):
        for _part in self.__dict__.get("_FANOUT", ()):
            if name in _part.__dict__:
                setattr(_part, name, value)
        object.__setattr__(self, name, value)


sys.modules[__name__].__class__ = _WmPackage
