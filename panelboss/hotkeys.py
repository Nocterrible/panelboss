"""Global keybinds: four named verbs, one window, RegisterHotKey.

THE LAW (owner, Oct 24 launch day): a hotkey is unbound until the owner
gives one, binds on keypress, esc clears, and does nothing until it is
given. Four verbs ship: pause dimming, movie-theater mode, restore my
windows, and the detection consent switch. Every verb's bound word is
stored as [mods, vk] where vk is the WINDOWS virtual-key code - the one
number RegisterHotKey speaks.

THE OCT-24 ROOT CAUSE (the repeat-failure this wave died on): the old
card fed Tk's ``event.keycode`` straight into RegisterHotKey as the vk.
Tk uses the X11 keysym numbering even on Windows (F12 = 96, PrintScrn =
111), NOT the win32 VK (F12 = 0x7B = 123, VK_SNAPSHOT = 0x2C). The
registration "succeeded" - RegisterHotKey accepts any vk in 1..254 - and
the press never matched, so nothing happened. The symptom was exactly
what the owner reported: it binds, and the key does nothing. The cure is
``capture``, which converts a Tk keysym (the reliable, documented name)
to the win32 VK at capture time. The stored word a working muscle-memory
already holds keeps its meaning: [mods, vk] with the CORRECT vk now.

THE REGISTRATION THREAD (the Oct-15 1408 law, unchanged): RegisterHotKey
must run on the thread that owns the window the key posts to, or the OS
refuses it (ERROR_INVALID_HOTKEY_WINDOW, measured cross-thread). The
display watcher owns a hidden pump window on its own thread, so every
verb here is a NOTE on that pump's queue (the _ear_req idiom): the note
carries (op, id, mods, vk), the pump applies it against its window, and
the (ok, errno) rides back on the note's event. A foreign WM_HOTKEY
falls through by id - the belt, not the fire.

SIZE LAW: one file, the four-verb registry plus the pure capture and the
banked request box. The display half stays in display.py (its window, its
queue), the actions stay at their owners (dimmer's pause flag, the UI's
restore/theater/detection event posts) - this module is the registry and
the router, nothing else.
"""

from __future__ import annotations

import ctypes
import logging
import time

log = logging.getLogger("hotkeys")

MOD_ALT = 0x1
MOD_CONTROL = 0x2
MOD_SHIFT = 0x4
MOD_WIN = 0x8
MOD_NOREPEAT = 0x4000          # autorepeat is not a press
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

# the four verbs, in UI order. "cfg" names the [section].key that holds
# the bound word, None for unbound. The ids are distinct and stable - the
# pump's WM_HOTKEY branch walks wParam against these numbers alone.
SLOTS = (
    {"name": "pause",     "id": 0x5042, "section": "dimmer",   "key": "bound"},
    {"name": "theater",   "id": 0x5043, "section": "hotkeys",  "key": "theater"},
    {"name": "restore",   "id": 0x5044, "section": "hotkeys",  "key": "restore"},
    {"name": "detection", "id": 0x5045, "section": "hotkeys",  "key": "detection"},
)
BY_ID = dict((s["id"], s["name"]) for s in SLOTS)
BY_NAME = dict((s["name"], s) for s in SLOTS)

# the Tk modifier mask -> the RegisterHotKey flag (event.state order):
# each row is (Tk bit, Win MOD_* flag). A chord is the OR of the held
# modifiers; a bare key is refused (a letter is typed, not stolen).
_TK_MODS = ((0x4, MOD_CONTROL), (0x8, MOD_ALT), (0x1, MOD_SHIFT),
            (0x40, MOD_WIN))


def _request(op, hkid, mods=0, vk=0):
    """The display pump's hotkey door: (op, id, mods, vk) -> (ok, err).
    The note crosses, the verb applies on the pump thread (the 1408
    law). Kept as a function so the suites can stand a fake in."""
    from . import display
    return display.request_hotkey(op, hkid, mods, vk)


# ---- per-slot arm state -------------------------------------------------
_hk = dict((s["name"], None) for s in SLOTS)        # live (mods, vk)
_tried = dict((s["name"], None) for s in SLOTS)     # last settled word
_notes = dict((s["name"], "") for s in SLOTS)       # the dated confession

# the pump's call-in: each press is ONE flag; the action owner flips it
# on its own beat (the cross-Tk law - a checkbox write from the pump
# thread is the bug class, so the registry hands a name, never a widget).
_press = {}


def _dated(word):
    return time.strftime("%H:%M ") + word


def _norm_bound(want):
    """A stored [mods, vk] in its canonical (int, int) shape, or None."""
    if isinstance(want, (list, tuple)) and len(want) == 2:
        try:
            return (int(want[0]), int(want[1]))
        except (TypeError, ValueError):
            return None
    return None


def bound(name, cfg):
    """The stored word for one verb, or None (unbound)."""
    slot = BY_NAME[name]
    return _norm_bound((cfg.get(slot["section"]) or {}).get(slot["key"]))


def live(name):
    """True only while this verb's hotkey is actually registered."""
    return _hk.get(name) is not None


def note(name):
    """The arm's dated confession ('' when it has nothing to say)."""
    return _notes.get(name, "")


def sync(cfg):
    """The per-tick bookkeeping: one attempt per CHANGED stored word per
    verb (not once a tick); an old key is released before a new one; a
    taken combo keeps the old binding and dates the word; a headless
    attempt is NOT marked tried, so the arm retries once a pump lives."""
    from . import display
    hwnd = display.hotkey_window()
    for slot in SLOTS:
        name = slot["name"]
        want = bound(name, cfg)
        if want == _tried[name]:
            continue
        old = _hk[name]
        if old is not None and hwnd:
            _request("unregister", slot["id"])
            _hk[name] = None
        if not want:
            _tried[name], _notes[name] = None, ""
            continue
        if hwnd is None:
            # a headless attempt is NOT marked tried, so the arm retries
            # once a pump lives - the card answers a word, never a lie
            _notes[name] = _dated("no message pump lives to hold the "
                                  "key yet")
            continue
        mods = want[0] | MOD_NOREPEAT
        ok, err = _request("register", slot["id"], mods, want[1])
        if ok:
            _hk[name], _tried[name], _notes[name] = want, want, ""
            log.info("hotkeys: %s arm: stored [%#x, %#x] registered "
                     "mods=%#x vk=%#x on hwnd=%#x", name, want[0], want[1],
                     mods, want[1], hwnd or 0)
            continue
        log.warning("hotkeys: %s arm: stored [%#x, %#x] refused on "
                    "hwnd=%#x: mods=%#x vk=%#x errno=%d%s", name, want[0],
                    want[1], hwnd or 0, mods, want[1], err,
                    " (ERROR_HOTKEY_ALREADY_REGISTERED)"
                    if err == ERROR_HOTKEY_ALREADY_REGISTERED
                    else " - NOT a collision")
        back = (" (clear and rebind to retry once the other app lets "
                "go)")
        if old and _request("register", slot["id"],
                            old[0] | MOD_NOREPEAT, old[1])[0]:
            _hk[name] = old
            back = "; the old binding stands" + back
        _tried[name] = want
        if err == ERROR_HOTKEY_ALREADY_REGISTERED:
            _notes[name] = _dated("that combo is taken on this desk" + back)
        else:
            _notes[name] = _dated("the desk refused that combo - windows "
                                  "error %d, not a clash" % err)


def teardown():
    """Release every live registration; the process dying releases them
    anyway, this is the orderly half."""
    from . import display
    for slot in SLOTS:
        name = slot["name"]
        if _hk[name] is not None and display.hotkey_window():
            _request("unregister", slot["id"])
        _hk[name] = _tried[name] = None
        _notes[name] = ""


# ---- the pump's call-in -------------------------------------------------
INVOKE = {}


def dispatch(hkid):
    """The display pump's WM_HOTKEY branch: wParam (the id) names the
    verb, the registry runs it. A foreign id falls through untouched -
    a hotkey registered by someone else is not ours to fire."""
    name = BY_ID.get(hkid)
    if name is None:
        return
    fn = INVOKE.get(name)
    if fn is None:
        return
    try:
        fn()
    except Exception:
        log.exception("hotkeys: the %s verb raised in dispatch", name)


# ---- capture: Tk keysym -> the stored [mods, vk] ------------------------
# VK codes the publisher tables (winuser.h): letters are 0x41..0x5A,
# digits 0x30..0x39, F1..F24 are 0x70..0x87, and the navigation/media
# keys below are the same numbers SendInput/WM_KEYDOWN already carry in
# this codebase (display.py's VK_CONTROL, wm/_hdr.py's key batches).
_KEYSYM_VK = {
    "Return": 0x0D, "KP_Enter": 0x0D, "Escape": 0x1B, "Tab": 0x09,
    "BackSpace": 0x08, "space": 0x20, "Delete": 0x2E, "Insert": 0x2D,
    "Home": 0x24, "End": 0x23, "Prior": 0x21, "Next": 0x22,
    "Left": 0x25, "Right": 0x27, "Up": 0x26, "Down": 0x28,
    "Print": 0x2C, "Scroll_Lock": 0x91, "Pause": 0x13, "Break": 0x13,
    "Caps_Lock": 0x14, "Num_Lock": 0x90,
    "minus": 0xBD, "equal": 0xBB, "bracketleft": 0xDB,
    "bracketright": 0xDD, "backslash": 0xDC, "semicolon": 0xBA,
    "apostrophe": 0xDE, "comma": 0xBC, "period": 0xBE, "slash": 0xBF,
    "grave": 0xC0,
    "KP_Divide": 0x6F, "KP_Multiply": 0x6A, "KP_Subtract": 0x6D,
    "KP_Add": 0x6B, "KP_Decimal": 0x6E, "KP_Separator": 0x6C,
    "Super_L": 0x5B, "Super_R": 0x5C, "Menu": 0x5D,
    "Launch_Mail": 0xB4, "Launch_App1": 0xB6, "Launch_App2": 0xB7,
    "AudioPlay": 0xB3, "AudioStop": 0xB2, "AudioNext": 0xB0,
    "AudioPrev": 0xB1, "AudioMute": 0xAD, "AudioRaiseVolume": 0x0B,
    "AudioLowerVolume": 0x0A, "AudioMedia": 0x0B,
}


def keysym_to_vk(keysym):
    """A Tk keysym -> the Windows virtual-key code, or None when the
    symbol has no win32 VK (a key that does not bind on this desk)."""
    if not keysym:
        return None
    if keysym.startswith("F") and keysym[1:].isdigit():
        n = int(keysym[1:])
        return 0x6F + n if 1 <= n <= 24 else None          # VK_F1 = 0x70
    if keysym.startswith("KP_") and keysym[3:].isdigit():
        return 0x60 + int(keysym[3:])                      # VK_NUMPAD0
    if len(keysym) == 1:
        c = keysym
        if "a" <= c <= "z":
            return ord(c.upper())
        if "0" <= c <= "9":
            return ord(c)
    return _KEYSYM_VK.get(keysym)


def capture(keysym, state):
    """The card's capture rule, pure so the suite can drive it with a
    fake event: returns ([mods, vk], None) when the press is a chord,
    and (None, word) when it was a bare or unbindable key. A letter is
    something the user TYPES - stealing it bare would be the theft the
    consent law forbids; the old binding stands."""
    mods = 0
    for tk_mask, win_mod in _TK_MODS:
        if state & tk_mask:
            mods |= win_mod
    if mods == 0:
        return None, ("a letter is not a chord - bind a combo, "
                      "esc clears")
    vk = keysym_to_vk(keysym)
    if vk is None:
        return None, "that key has no binding on this desk"
    return [mods, vk], None


def set_bound(cfg, name, word):
    """Write a verb's stored word (None clears it). The pause key's
    storage stays [dimmer].bound for the byte-compat law; the three new
    verbs live under [hotkeys].<name>, absent = unbound."""
    slot = BY_NAME[name]
    cfg.setdefault(slot["section"], {})[slot["key"]] = word