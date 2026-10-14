"""Display configuration: the current-mode base, the offered-mode
list, single-monitor set_mode and the profile's two-pass
apply_layout. Formerly wm.py lines 462-634, the banner and its
measured lessons included."""

import ctypes
import time
from ctypes import wintypes

from ._monitors import monitors
from ._winapi import DEVMODEW, ENUM_CURRENT_SETTINGS, byref, sizeof, u32


# --------------------------------------------------- desktop application --
# The procedures below are stolen from the monitor_control project
# (both halves of it), with its measured lessons baked in: the driver
# is the truth about sizes (the display-config API reported widths
# that disagreed with the desktop - measured), the current DEVMODE
# must be the base of any change (one copied from the mode list has
# an empty dmDeviceName and every request then comes back -2), a
# CDS_TEST ask costs nothing and saves a blink, Windows reports
# success BEFORE the modes settle (so everything is read back), and
# it refuses with 87 to drop the display that owns the desktop in
# the same call that hands the desktop over.
ENUM_REGISTRY_SETTINGS = -2
CDS_UPDATEREGISTRY = 0x01
CDS_TEST = 0x02
CDS_SET_PRIMARY = 0x10
CDS_NORESET = 0x10000000
DM_POSITION = 0x20
DM_PELSWIDTH = 0x80000
DM_PELSHEIGHT = 0x40000
DM_DISPLAYFREQUENCY = 0x400000
DISP_CHANGE_SUCCESSFUL = 0
DISP_CHANGE_RESTART = 1

# A refusal the user cannot read is silence with extra steps (the
# loud-voice wave, Oct 14): ChangeDisplaySettingsExW's error codes,
# in human words. An unmapped rc still speaks its number - the fall-
# through string is the belt, the map is the voice.
RC_WHY = {-1: "the driver failed the switch",
          -2: "the driver does not offer that mode",
          -3: "the registry could not be written",
          -4: "the request carried bad flags",
          -5: "the request carried bad params",
          -6: "dualview forbids the change"}

u32.ChangeDisplaySettingsExW.argtypes = [
    ctypes.c_wchar_p, ctypes.POINTER(DEVMODEW), ctypes.c_void_p,
    wintypes.DWORD, ctypes.c_void_p]
u32.ChangeDisplaySettingsExW.restype = ctypes.c_long


def current_mode(gdi):
    """The DEVMODE to base a change on. A turned-off monitor has no
    current mode, and one copied fresh from the mode list carries an
    empty dmDeviceName (every non-trivial request then answers -2,
    the "monitor unplugged itself" illusion) - so: current first,
    registry second, both with the name the driver recognises."""
    dm = DEVMODEW()
    dm.dmSize = sizeof(dm)
    if u32.EnumDisplaySettingsW(gdi, ENUM_CURRENT_SETTINGS, byref(dm)) \
            and dm.dmPelsWidth:
        return dm
    if u32.EnumDisplaySettingsW(gdi, ENUM_REGISTRY_SETTINGS, byref(dm)):
        return dm
    return None


def offered_modes(gdi, limit=400):
    """The modes the driver offers, spelled "WxH@Hz", driver order,
    deduplicated - the profile UI shows this list next to each
    monitor so a user cannot ask for a mode the panel will not
    take."""
    out = []
    for i in range(limit):
        dm = DEVMODEW()
        dm.dmSize = sizeof(dm)
        if not u32.EnumDisplaySettingsW(gdi, i, byref(dm)):
            break
        if not dm.dmPelsWidth:
            continue
        name = "%dx%d@%d" % (dm.dmPelsWidth, dm.dmPelsHeight,
                             dm.dmDisplayFrequency)
        if name not in out:
            out.append(name)
    return out


def set_mode(gdi, w, h, rate):
    """Size (and rate when asked) on one monitor, the Modes.Set
    procedure: current DEVMODE as the base, the mode must be on the
    driver's list (an unlisted one answers -2 like a dead cable),
    CDS_TEST before touching the screen, believe the driver over the
    return code."""
    dm = current_mode(gdi)
    if dm is None:
        return "the driver will not say what %s is set to" % gdi
    if int(dm.dmPelsWidth) == w and int(dm.dmPelsHeight) == h and \
            (rate <= 0 or int(dm.dmDisplayFrequency) == rate):
        return "already %dx%d@%d" % (w, h, dm.dmDisplayFrequency)
    want = "%dx%d@%d" % (w, h, rate)
    if rate > 0 and want not in offered_modes(gdi):
        return "%s is not among the modes this monitor offers" % want
    dm.dmPelsWidth = w
    dm.dmPelsHeight = h
    dm.dmFields |= DM_PELSWIDTH | DM_PELSHEIGHT
    if rate > 0:
        dm.dmDisplayFrequency = rate
        dm.dmFields |= DM_DISPLAYFREQUENCY
    if u32.ChangeDisplaySettingsExW(gdi, byref(dm), None, CDS_TEST,
                                    None) != DISP_CHANGE_SUCCESSFUL:
        return "%s is on the list but the driver will not switch" % want
    rc = u32.ChangeDisplaySettingsExW(gdi, byref(dm), None, 0, None)
    if rc == DISP_CHANGE_RESTART:          # the keep-settings dialog
        u32.ChangeDisplaySettingsExW(None, None, None, 0, None)
    time.sleep(0.9)                        # the mode lands async
    return "asked %s (driver answer %d)" % (want, rc)


def apply_layout(entries):
    """Turn the profile's display plan on the desk: enable pass
    first (new primary LAST so it can steal 0,0 cleanly, CDS_SET_
    PRIMARY), then the disable pass (0x0 at 0,0), then one commit;
    everything CDS_UPDATEREGISTRY | CDS_NORESET. entries:
    [{gdi, on, primary, x, y, w, h, rate}] - devices already in the
    wanted state are skipped, so a profile applied onto its own desk
    never blinks (the switcher's rule: a change nobody asked for is
    still a change)."""
    lines = []
    wanted = [e for e in entries if e.get("on", True)]
    disabled = [e for e in entries if not e.get("on", True)]
    if not wanted:
        return False, ["no monitor would stay on - refusing"]
    primary = next((e["gdi"] for e in wanted if e.get("primary")),
                   wanted[0]["gdi"])

    def already(dev, want_on):
        now = {m["gdi"]: m for m in monitors()}
        cur = now.get(dev)
        if want_on:
            if cur is None:
                return False
            e = next(x for x in entries if x["gdi"] == dev)
            px = 0 if dev == primary else int(e["x"])
            py = 0 if dev == primary else int(e["y"])
            return (cur["w"] == int(e["w"]) and cur["h"] == int(e["h"])
                    and cur["x"] == px and cur["y"] == py
                    and (dev != primary or cur["primary"])
                    and (not e.get("rate")
                         or cur["rate"] == int(e["rate"])))
                    # rate too: a profile edited to a new Hz on the
                    # same w/h/position is a REAL change (the manual
                    # editor makes this state reachable every day)
        return cur is None                 # already off

    pend = [e for e in wanted if not already(e["gdi"], True)]
    order = [e for e in pend if e["gdi"] != primary] + \
            [e for e in pend if e["gdi"] == primary]
    refused = []   # (name, why): a device the desk will not take -
    #                named by the profile short when the entry has one
    for e in order:
        dm = current_mode(e["gdi"])
        if dm is None:
            # The banner's measured shape: a fresh DEVMODEW carries an
            # empty dmDeviceName and every request off it answers -2,
            # so the refusal is named BEFORE any staging.
            refused.append((e.get("short") or e["gdi"], "no current mode"))
            lines.append("refuse %s: no current mode (an empty DEVMODEW "
                         "answers -2)" % e["gdi"])
            continue
        base = dm
        base.dmSize = sizeof(base)
        base.dmDriverExtra = 0
        base.dmPelsWidth = int(e["w"])
        base.dmPelsHeight = int(e["h"])
        if e.get("rate"):
            base.dmDisplayFrequency = int(e["rate"])
        base.display.dmPosition.x = (0 if e["gdi"] == primary
                                     else int(e["x"]))
        base.display.dmPosition.y = (0 if e["gdi"] == primary
                                     else int(e["y"]))
        base.dmFields = DM_POSITION | DM_PELSWIDTH | DM_PELSHEIGHT
        if e.get("rate"):
            base.dmFields |= DM_DISPLAYFREQUENCY
        flags = CDS_UPDATEREGISTRY | CDS_NORESET
        if e["gdi"] == primary:
            flags |= CDS_SET_PRIMARY
        rc = u32.ChangeDisplaySettingsExW(e["gdi"], byref(base), None,
                                          flags, None)
        lines.append("enable %s %dx%d@%d -> %d" % (
            e["gdi"], e["w"], e["h"], e.get("rate") or 0, rc))
        if rc not in (DISP_CHANGE_SUCCESSFUL, DISP_CHANGE_RESTART):
            refused.append((e.get("short") or e["gdi"],
                            RC_WHY.get(rc, "the driver answered %d" % rc)))
    for e in disabled:
        if already(e["gdi"], False):
            continue
        dm = DEVMODEW()
        dm.dmSize = sizeof(dm)
        dm.dmFields = DM_POSITION | DM_PELSWIDTH | DM_PELSHEIGHT
        dm.dmPelsWidth = 0
        dm.dmPelsHeight = 0
        rc = u32.ChangeDisplaySettingsExW(e["gdi"], byref(dm), None,
                                          CDS_UPDATEREGISTRY
                                          | CDS_NORESET, None)
        lines.append("disable %s -> %d" % (e["gdi"], rc))
        if rc not in (DISP_CHANGE_SUCCESSFUL, DISP_CHANGE_RESTART):
            refused.append((e.get("short") or e["gdi"],
                            RC_WHY.get(rc, "the driver answered %d" % rc)))
    rc = u32.ChangeDisplaySettingsExW(None, None, None, 0, None)
    lines.append("commit -> %d" % rc)
    if rc not in (DISP_CHANGE_SUCCESSFUL, DISP_CHANGE_RESTART):
        # the gate's finding 4: a bare commit number is a wordless
        # sentence - the FINAL commit answers through the same
        # RC_WHY law, named 'commit' (no panel owns it), and the
        # profiles.py refusal filter covers it for free
        lines.append("refused commit: %s (desk left partial)"
                     % RC_WHY.get(rc, "the driver answered %d" % rc))
    for who, why in refused:
        lines.append("refused %s: %s (desk left partial)" % (who, why))
    ok = rc in (DISP_CHANGE_SUCCESSFUL, DISP_CHANGE_RESTART)
    return ok and not refused, lines
