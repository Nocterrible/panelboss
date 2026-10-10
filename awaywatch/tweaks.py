"""registry tweaks the gaming pack can promise safely (docs/
apack-findings.md is the measured research; this module is the
mechanical part).

Truth is the registry itself: is_on() reads current values every
time, so a Settings-toggle by hand, a tweak script, or our own
apply all agree - no shadow state to drift. Every core toggle here
is HKCU: no admin, no dialogs, and most land live or at next
launch. Admin-only items (the machine-wide policy) attempt anyway
and return the honest error string instead of silently failing.

The FSO layer is per-app: same shape as the gaming.games list -
exe paths in, Layers values out, add/remove/idempotent apply all
handled by the list functions below.

Fail-open everywhere: registry denials return (False, msg);
nothing here may raise or open a dialog at the desk.
"""
import ctypes
import logging

import winreg

log = logging.getLogger("tweaks")

LAYERS = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
DISABLE_FSO = "~ DISABLEDXMAXIMIZEDWINDOWEDMODE"   # measured: this
# exact string is what the compat-tab checkbox writes (a live
# Palworld entry on this desk proved the format, 2026-10-10)

# id -> (label, hive_path, value_name, data, live_or_signout)
# core HKCU toggles; apply writes data, revert restores 1/absent
# per the findings doc. Elevation is N for all of these.
TOGGLES = {
    "overlay": ("Xbox Game Bar overlay (Win+G)",
                r"Software\Microsoft\GameBar",
                "UseNexusForGameBarEnabled", 0, "live"),
    "capture": ("background recording + record-what-happened",
                r"Software\Microsoft\Windows\CurrentVersion\GameDVR",
                "AppCaptureEnabled", 0, "sign-out to fully stop"),
    "history": ("\"record what happened\" alone",
                r"Software\Microsoft\Windows\CurrentVersion\GameDVR",
                "HistoricalCaptureEnabled", 0, "live"),
    "session": ("game session detection (GameDVR_Enabled)",
                r"System\GameConfigStore",
                "GameDVR_Enabled", 0, "sign-out"),
}
# the policy toggle for the ambitious: writes HKLM, needs admin,
# gpupdate + bcastdvr restart to bite; kept honestly labeled
POLICY = ("machine-wide DVR ban (all users, admin)",
          r"SOFTWARE\Policies\Microsoft\Windows\GameDVR",
          "AllowGameDVR", 0, "sign-out or longer")


def _get(path, name):
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
        try:
            return winreg.QueryValueEx(k, name)[0]
        finally:
            winreg.CloseKey(k)
    except OSError:
        return None


def _put(path, name, data):
    """REG_DWORD write (data None deletes the value). Returns
    (ok, error)."""
    try:
        k = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path,
                               0, winreg.KEY_WRITE)
        try:
            if data is None:
                try:
                    winreg.DeleteValue(k, name)
                except OSError:
                    pass        # absent is the goal anyway
            else:
                winreg.SetValueEx(k, name, data, None,
                                  winreg.REG_DWORD)
            return True, ""
        finally:
            winreg.CloseKey(k)
    except OSError as exc:
        return False, str(exc.strerror)


def is_on(tid):
    """Current registry truth for a core toggle: True if the DVR-
    suppressing value is in place (the data is our applied value)."""
    label, path, name, data, _ = TOGGLES[tid]
    return _get(path, name) == data


def apply(tid):
    """Suppress the feature. Returns (ok, error)."""
    label, path, name, data, _timing = TOGGLES[tid]
    return _put(path, name, data)


def revert(tid):
    """Hand the feature back to default (value removed)."""
    label, path, name, _data, _timing = TOGGLES[tid]
    return _put(path, name, None)


def apply_policy(on=True):
    """HKLM attempt: fails honestly on unelevated shells (the
    caller shows the message; no UAC is opened here)."""
    label, path, name, data, _ = POLICY
    try:
        k = winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, path,
                               0, winreg.KEY_WRITE)
        try:
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD,
                              data if on else 1)
            return True, ""
        finally:
            winreg.CloseKey(k)
    except OSError as exc:
        return False, ("admin needed: " + (exc.strerror or ""))


# - per-app fullscreen-optimizations off --------------------------
# same shape as gaming.games: list of full exe paths in cfg; the
# registry mirror is what counts, so these functions take the list
# straight and never store a second copy.

def fso_state(exe_path):
    """True if DISABLEDXMAXIMIZEDWINDOWEDMODE is set for this exe."""
    v = _get(LAYERS, exe_path)
    return isinstance(v, str) and "DISABLEDXMAXIMIZEDWINDOWEDMODE" \
        in v


def fso_set(exe_path, off=True):
    """Set/remove the per-app FSO layer (takes effect NEXT launch
    of that exe - measured folklore-free, see findings doc)."""
    if off:
        return _put_str(LAYERS, exe_path, DISABLE_FSO)
    return _put(LAYERS, exe_path, None)


def _put_str(path, name, data):
    try:
        k = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path,
                               0, winreg.KEY_WRITE)
        try:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, data)
            return True, ""
        finally:
            winreg.CloseKey(k)
    except OSError as exc:
        return False, str(exc.strerror)


def fso_sync(paths):
    """Make the Layers key match the list: set every path in it,
    remove the layer from any DISABLED exe that fell off the list.
    Returns [(action, exe, ok, err), ...] so the UI can report
    each line honestly. Other vendors' Layers entries (people run
    more than our tweaks here) are preserved untouched: we only
    ever add/strip OUR token."""
    out = []
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, LAYERS)
        i = 0
        mine = {}
        while True:
            try:
                name = winreg.EnumValue(k, i)[0]
            except OSError:
                break
            i += 1
            val = winreg.QueryValueEx(k, name)[0]
            if isinstance(val, str) and \
                    "DISABLEDXMAXIMIZEDWINDOWEDMODE" in val:
                mine[name] = val
        winreg.CloseKey(k)
    except OSError:
        mine = {}
    want = set(paths or [])
    for exe in want:
        if exe not in mine:
            ok, err = fso_set(exe, True)
            out.append(("disable-fso", exe, ok, err))
    for exe in mine:
        if exe not in want:
            # a bare "~" (no token) is a stale leftover of our write,
            # not a vendor token - do not preserve it
            rest = " ".join(t for t in mine[exe].split()
                            if t != "~" and
                            "DISABLEDXMAXIMIZEDWINDOWEDMODE"
                            not in t).strip()
            if rest:      # someone else's tokens stay in the value
                ok, err = _put_str(LAYERS, exe, rest)
                out.append(("strip-our-token", exe, ok, err))
            else:
                ok, err = fso_set(exe, False)
                out.append(("clear-fso-flag", exe, ok, err))
    return out


# - timer resolution (the 0.5 ms fix, live, no admin, no reboot) --
# measured: this desk already sits at 0.5 ms WHILE a requester
# runs, and the registry form is undocumented; the honest tool is
# the documented API, held only while a game owns the desk.
_winmm = None


def timer_boost(on):
    """timeBeginPeriod(1)/timeEndPeriod(1): the documented way to
    pin the system clock to 1 ms granularity while we hold it.
    Returns True/False; callers must pair every True with a False
    on the way out (gaming_watch owns that discipline)."""
    global _winmm
    try:
        if _winmm is None:
            _winmm = ctypes.WinDLL("winmm.dll")
            _winmm.timeBeginPeriod.argtypes = [ctypes.c_uint]
            _winmm.timeEndPeriod.argtypes = [ctypes.c_uint]
        if on:
            return _winmm.timeBeginPeriod(1) == 0
        _winmm.timeEndPeriod(1)
        return True
    except Exception:
        return False
