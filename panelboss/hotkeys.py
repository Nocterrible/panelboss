"""Global keybinds: four named verbs, one window, RegisterHotKey.

THE LAW (owner, Oct 24 launch day): a hotkey is unbound until the owner
gives one, binds on keypress, esc clears, and does nothing until it is
given. Four verbs ship: pause dimming, movie-theater mode, restore my
windows, and the detection consent switch. Every verb's bound word is
stored as [mods, vk] where vk is the WINDOWS virtual-key code - the one
number RegisterHotKey speaks.

THE THREE ROOT CAUSES (the repeat-failure class, Oct 24, all fixed here):
1. THE VK MISMATCH. The old card fed Tk's ``event.keycode`` straight into
   RegisterHotKey as the vk. Tk uses the X11 keysym numbering even on
   Windows (F12 = 96, PrintScrn = 111), NOT the win32 VK (F12 = 0x7B =
   123, VK_SNAPSHOT = 0x2C). RegisterHotKey accepts any vk 1..254 and
   "succeeded", but the pressed key never matched, so WM_HOTKEY never
   fired. ``capture`` converts a Tk keysym (the reliable, documented
   name) to the win32 VK at capture time. The stored word with a CORRECT vk
   keeps its meaning: [mods, vk] as always. A word stored by the
   BROKEN era (vk from the Tk keycode) may name a different key than
   the one you gave - esc and re-bind once; the card seeds its
   toggles either way.
2. THE MODS LIE - DELETED BY DESIGN, NOT MAPPED (the owner's ruling,
   refresh E). The first capture read Tk's event.state to learn the
   chord - but Tk stamps that field from GetKeyState, the key state the
   CALLING THREAD's message queue maintains, and a focus-switch that
   ate a WM_KEYUP latches modifiers FOR OUR THREAD ALONE: a bare F12
   arrived as state=0x4000C (0x40000 is Tk's documented Windows-only
   'Extended' per-event flag - a scan-code fact about the KEY, not a
   held modifier; the bind manual names it) and the old loop stored
   [3, 123] = MOD_ALT|MOD_CONTROL MANUFACTURED out of a bare press.
   The registration then waited faithfully for a chord nobody ever
   pressed. The fixer's autopsy blamed a physically stuck Alt - FALSE,
   and the owner's F4 physics said so at the desk (verbatim: 'ALT IS
   NOT STUCK DOWN - nothing else other than Panelboss binding acts
   like Alt is stuck down': a stuck modifier would speak across the
   whole desk; the machine was clean). The design ruling that followed
   binds the class away: ctrl/alt/shift are TOGGLES beside the bind
   button, the capture reads ONLY the key, event.state is never
   consulted - the bug class dies by deletion, not by mapping, and
   every user of every future hotkey gets it for free. The stored
   word [mods, vk] keeps its byte-compat meaning; the mods are
   computed from the toggles (MOD_NOREPEAT joins at registration,
   never in the store).
3. THE DELIVERY THREAD. The arm first registered against the display
   watcher's hidden window on its own pump thread, through a cross-thread
   note (the 1408 law). On the live desk the registration still returned
   success and STILL no WM_HOTKEY ever reached that thread's queue.
   Ride two (the Tk root window) died too: Tk's own mainloop retrieves
   and drops the unrecognized WM_HOTKEY before any after-loop poll can
   PeekMessage it. Ride three, the shape now: a DEDICATED thread
   registers with a NULL hwnd - RegisterHotKey(NULL) posts WM_HOTKEY to
   the CALLING thread's queue - and drains that queue with a short
   PeekMessage poll. One thread owns the registration and the read,
   cradle to grave; the UI beat only books changed words.

SIZE LAW: one file, the four-verb registry plus the pure capture and the
ffi. The actions stay at their owners (dimmer's pause flag, the UI's
restore/theater/detection dispatch) - this module is the registry and the
router, nothing else.
"""

from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes

log = logging.getLogger("hotkeys")

MOD_ALT = 0x1
MOD_CONTROL = 0x2
MOD_SHIFT = 0x4
MOD_WIN = 0x8
MOD_NOREPEAT = 0x4000          # autorepeat is not a press
ERROR_HOTKEY_ALREADY_REGISTERED = 1409
WM_HOTKEY = 0x0312               # winuser.h (the display-era cross-ref
#                                 died with that era; this is the
#                                 message's OWN number)

# the four verbs, in UI order. "section"/"key" name the [section].key
# that holds the bound word, None for unbound. The ids are distinct and
# stable - a WM_HOTKEY's wParam is one of these numbers alone.
SLOTS = (
    {"name": "pause",     "id": 0x5042, "section": "dimmer",  "key": "bound"},
    {"name": "theater",   "id": 0x5043, "section": "hotkeys", "key": "theater"},
    {"name": "restore",   "id": 0x5044, "section": "hotkeys", "key": "restore"},
    {"name": "detection", "id": 0x5045, "section": "hotkeys", "key": "detection"},
)
BY_ID = dict((s["id"], s["name"]) for s in SLOTS)
BY_NAME = dict((s["name"], s) for s in SLOTS)

# THE TOGGLE DESIGN (owner ruling, refresh E - see root cause 2): the
# chord flags are not read from the event at all, they are SETTINGS on
# the card. Each row is (toggle label, the winuser.h chord flag - the
# constants below are the documented numbers, verbatim: MOD_ALT
# 0x0001, MOD_CONTROL 0x0002, MOD_SHIFT 0x0004, and MOD_NOREPEAT
# 0x4000 joins at registration only). event.state is never consulted:
# a thread-local copy that has already been caught lying does not get
# a vote.
TOGGLES = (("ctrl", MOD_CONTROL), ("alt", MOD_ALT), ("shift", MOD_SHIFT))


def toggle_mods(on):
    """The card's mods computation, pure: `on` names the toggles the
    owner checked ('ctrl', 'alt', 'shift'); the stored word's mods are
    exactly this sum, nothing else reads the keyboard."""
    mods = 0
    for tname, tbit in TOGGLES:
        if tname in on:
            mods |= tbit
    return mods

# the pinned FFI (the x64 slot law - every handle is c_void_p, every VK
# is a c_uint; an unpinned call truncates a 64-bit handle to a corpse).
_u32 = ctypes.WinDLL("user32", use_last_error=True)
_u32.RegisterHotKey.restype = ctypes.c_int
_u32.RegisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                ctypes.c_uint, ctypes.c_uint]
_u32.UnregisterHotKey.restype = ctypes.c_int
_u32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
_u32.PeekMessageW.restype = ctypes.c_int
_u32.PeekMessageW.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]


def _register(hwnd, hkid, mods, vk):
    """The real RegisterHotKey. A seam function so the suite stands a
    fake in: (ok, errno) - errno 0 on success, the real number on a
    refusal (use_last_error is set, so ctypes carries the copy). hwnd is
    NULL (0) - see the delivery-thread note in the module docstring."""
    ok = bool(_u32.RegisterHotKey(hwnd, hkid, mods, vk))
    err = 0 if ok else ctypes.get_last_error()
    return ok, err


def _unregister(hwnd, hkid):
    """The real UnregisterHotKey. A seam, like _register."""
    ok = bool(_u32.UnregisterHotKey(hwnd, hkid))
    return ok, 0 if ok else ctypes.get_last_error()


# ---- the pump thread ----------------------------------------------------
# THE DELIVERY-THREAD FIX, ride three (Oct 24): two earlier homes failed
# - the display watcher's hidden window (registered success, WM_HOTKEY
# never reached its queue) and the Tk root window (Tk's own mainloop
# retrieves and drops the unrecognized WM_HOTKEY before this module's
# after-loop poll can PeekMessage it). The cure is a DEDICATED thread
# that registers against a NULL hwnd - RegisterHotKey(hWnd=NULL) posts
# WM_HOTKEY to the CALLING thread's own queue - and pumps that queue
# with GetMessage. No shared window, no Tk dispatch, no display pump:
# one thread owns the registration and the read, cradle to grave.
import queue as _queue
import threading as _threading

_req_q = _queue.Queue()          # (op, id, mods, vk, done_event, result)
_stop = _threading.Event()
_pump = None


def _pump_loop():
    """The waiter thread: applies register/unregister asks, then drains
    its own queue for WM_HOTKEY (which lands here because the keys were
    registered with a NULL hwnd on THIS thread). A short poll, never a
    blocking GetMessage - the first blocking GetMessage froze the pump
    with a pending register ask, the bug ride-three measured live."""
    msg = wintypes.MSG()
    _u32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 0)   # create the queue
    while not _stop.is_set():
        # drain any pending asks
        while True:
            try:
                op, hkid, mods, vk, done, res = _req_q.get_nowait()
            except _queue.Empty:
                break
            try:
                if op == "register":
                    res[0] = _register(0, hkid, mods, vk)
                else:
                    res[0] = _unregister(0, hkid)
            except Exception:
                res[0] = (False, ctypes.get_last_error())
            done.set()
        # drain WM_HOTKEY off this thread's queue
        while _u32.PeekMessageW(ctypes.byref(msg), 0, WM_HOTKEY,
                                WM_HOTKEY, 1):
            log.info("hotkeys: WM_HOTKEY wParam=%#x", msg.wParam)
            dispatch(msg.wParam)
        _stop.wait(0.02)                            # 20 ms poll, not latency


def _ensure_pump():
    global _pump
    if _pump is None or not _pump.is_alive():
        _pump = _threading.Thread(target=_pump_loop, daemon=True,
                                  name="hotkey-pump")
        _pump.start()


def _ask(op, hkid, mods=0, vk=0, timeout=5.0):
    """Send one verb to the pump thread and wait for its (ok, errno).
    A wedged pump answers (False, 0) after the bound, never a silent
    hang."""
    _ensure_pump()
    done = _threading.Event()
    res = [(False, 0)]
    _req_q.put((op, hkid, mods, vk, done, res))
    done.wait(timeout)
    return res[0]


# ---- registration state -------------------------------------------------
_hk = dict((s["name"], None) for s in SLOTS)        # live (mods, vk)
_tried = dict((s["name"], None) for s in SLOTS)     # last settled word
_notes = dict((s["name"], "") for s in SLOTS)       # the dated confession


def attach(hwnd):
    """Legacy no-op: registration no longer needs a window (the pump
    thread uses a NULL hwnd). Kept so the UI wiring stays stable."""
    return None


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
    """The bookkeeping (run from any thread): one attempt per CHANGED
    stored word per verb (not once a tick); an old key is released
    before a new one; a taken combo keeps the old binding and dates the
    word. The verbs cross to the pump thread as asks and register there,
    so the WM_HOTKEY lands on the thread that pumps it."""
    for slot in SLOTS:
        name = slot["name"]
        want = bound(name, cfg)
        if want == _tried[name]:
            continue
        old = _hk[name]
        if old is not None:
            _ask("unregister", slot["id"])
            _hk[name] = None
        if not want:
            _tried[name], _notes[name] = None, ""
            continue
        mods = want[0] | MOD_NOREPEAT
        ok, err = _ask("register", slot["id"], mods, want[1])
        if ok:
            _hk[name], _tried[name], _notes[name] = want, want, ""
            log.info("hotkeys: %s arm: stored [%#x, %#x] registered "
                     "mods=%#x vk=%#x on the pump thread", name, want[0],
                     want[1], mods, want[1])
            continue
        log.warning("hotkeys: %s arm: stored [%#x, %#x] refused: "
                    "mods=%#x vk=%#x errno=%d%s", name, want[0], want[1],
                    mods, want[1], err,
                    " (ERROR_HOTKEY_ALREADY_REGISTERED)"
                    if err == ERROR_HOTKEY_ALREADY_REGISTERED
                    else " - NOT a collision")
        back = (" (clear and rebind to retry once the other app lets "
                "go)")
        if old and _ask("register", slot["id"],
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
    """Release every live registration and stop the pump; the process
    dying releases them anyway, this is the orderly half."""
    _stop.set()
    for slot in SLOTS:
        name = slot["name"]
        if _hk[name] is not None:
            _ask("unregister", slot["id"])
        _hk[name] = _tried[name] = None
        _notes[name] = ""


# ---- the press call-in --------------------------------------------------
INVOKE = {}


def dispatch(hkid):
    """wParam (the id) names the verb; the registry runs it. A foreign
    id falls through untouched - a hotkey registered by someone else is
    not ours to fire."""
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
    "AudioPrev": 0xB1, "AudioMute": 0xAD, "AudioRaiseVolume": 0xAF,
    "AudioLowerVolume": 0xAE, "AudioMedia": 0xB4,
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
        c = keysym.lower()            # a physical Shift+p arrives as the
        if "a" <= c <= "z":           # keysym 'P' - the VK is the key,
            return ord(c.upper())     # the shift lives in the toggles
        if "0" <= c <= "9":
            return ord(c)
    return _KEYSYM_VK.get(keysym)


# The bare-bindable plain keys (the owner's desk order, refresh E):
# function keys, media/launch keys, PrintScr, ScrollLock, Pause, Apps.
# These keys TYPE NOTHING - the consent law forbids stealing letters,
# which the user types, and this table keeps that promise: a bare
# letter or a bare space presses on, unbound.
_PLAIN_OK = (frozenset(("Print", "Scroll_Lock", "Pause", "Break", "Menu"))
             | frozenset(k for k in _KEYSYM_VK if k.startswith("Launch_")
                         or k.startswith("Audio")))


def _plain_bare_ok(keysym):
    if keysym.startswith("F") and keysym[1:].isdigit():
        return True
    return keysym in _PLAIN_OK


def capture(keysym, mods):
    """The card's capture rule, pure: the KEY decides the vk (keysym
    -> win32 VK; a modifier press does not change which key it was -
    Shift+p arrives as keysym 'P' and binds as P under whatever the
    toggles say), and the mods argument is the CARD's toggle sum
    (toggle_mods), not an event stamp. event.state is not even an
    argument: the thread-local copy behind it latched Alt/Ctrl for our
    thread ALONE and manufactured the phantom chord (root cause 2) -
    the field never gets a vote. Returns ([mods, vk], None) for a
    bindable press; a bare letter or an unbindable key answers
    (None, word) and the old binding stands."""
    vk = keysym_to_vk(keysym)
    if vk is None:
        return None, "that key has no binding on this desk"
    if mods == 0 and not _plain_bare_ok(keysym):
        return None, ("a bare letter types where you type - toggle a "
                      "modifier, or bind a function or media key "
                      "plain; esc clears")
    return [mods, vk], None


def set_bound(cfg, name, word):
    """Write a verb's stored word (None clears it). The pause key's
    storage stays [dimmer].bound for the byte-compat law; the three new
    verbs live under [hotkeys].<name>, absent = unbound."""
    slot = BY_NAME[name]
    cfg.setdefault(slot["section"], {})[slot["key"]] = word


# the VK -> a human name, for the card's say row (the owner wanted the
# bound combo spelled out, not the bare word "live" or the raw pair).
_VK_NAMES = {"Return": 0x0D, "Escape": 0x1B, "Tab": 0x09, "BackSpace": 0x08,
             "space": 0x20, "Delete": 0x2E, "Insert": 0x2D, "Home": 0x24,
             "End": 0x23, "Prior": 0x21, "Next": 0x22, "Left": 0x25,
             "Right": 0x27, "Up": 0x26, "Down": 0x28, "Print": 0x2C,
             "Pause": 0x13, "Scroll_Lock": 0x91, "Num_Lock": 0x90,
             "Caps_Lock": 0x14, "Menu": 0x5D,
             "KP_Divide": 0x6F, "KP_Multiply": 0x6A, "KP_Subtract": 0x6D,
             "KP_Add": 0x6B, "KP_Decimal": 0x6E,
             "minus": 0xBD, "equal": 0xBB, "comma": 0xBC, "period": 0xBE,
             "slash": 0xBF, "grave": 0xC0}
_VK_NAME = dict((v, k) for k, v in _VK_NAMES.items())

_MOD_NAMES = ((MOD_CONTROL, "ctrl"), (MOD_SHIFT, "shift"),
              (MOD_ALT, "alt"), (MOD_WIN, "win"))


def describe(name, cfg):
    """The stored word as a human combo ('ctrl+shift+F12') or the empty
    string when unbound. The card's say row shows this, not the bare
    'live'."""
    word = bound(name, cfg)
    if not word:
        return ""
    mods, vk = word
    parts = [n for m, n in _MOD_NAMES if mods & m]
    key = "F%d" % (vk - 0x6F) if 0x70 <= vk <= 0x87 else _VK_NAME.get(
        vk, chr(vk))
    return "+".join(parts + [key])