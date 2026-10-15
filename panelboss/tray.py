"""System tray: barebones but with the settings that matter.

The icon is a circle that changes color with the machine state; the menu
carries the levers (detection device, camera, wake policy, pause/snooze).
pystray runs callbacks on its own pump thread, so nothing here touches
the camera or display directly; everything is persisted through the
state machine's queue and config.write_config.

pystray traps, all measured the hard way:
* Icon(name, icon=, title=, menu=) - the image keyword is icon= and a
  wrong image= is swallowed by **kwargs
* the icon starts HIDDEN; passing setup= replaces the default callback
  that sets visible=True, so NIM_ADD never reaches the Shell
* the menu HMENU is built by update_menu(); the constructor bypasses it
  and a right-click before any left-click shows nothing
* pystray 0.19.5 calls Shell_NotifyIcon through a struct it fills with
  hID=id(self), a field NOTIFYICONDATAW does not have: ctypes drops the
  unknown kwarg, every NIM_* call reaches the Shell with uID=0 and no
  NIF_GUID, and Windows keys the tray slot on (executable path, uID).
  That is the churn: the venv pythonw re-execs the base pythonw, a
  frozen exe is a third path, and each one invented a fresh un-pinned
  slot. _stamp_identity below fixes the identity at the one choke point
  every NIM_* call passes; pystray's own files are never touched
"""

from __future__ import annotations

from importlib import metadata

import logging
import threading
import time
import uuid

import pystray
from PIL import Image
from PIL import ImageDraw
from pystray._util import win32

log = logging.getLogger("tray")

# --------------------------------------------------------------- identity ---
# one fixed GUID, minted from the app name, so every NIM_* call of every
# process that runs this app (the venv pythonw, the base pythonw it
# re-execs, a frozen exe) keys on the SAME tray slot. Windows 10 1903
# and newer honor NIF_GUID: the registry key under Control Panel\
# NotifyIconSettings then IS the GUID instead of a hash of whatever
# interpreter path happens to be running. Wrap verified against pystray
# 0.19.5 (NOTIFYICONDATAW fields at _util\win32.py:153-168, the call
# site at _win32.py:337). The namespace string was reminted on the
# v0.1.0 rename, so the first run after it owes one re-pin out of the
# overflow flyout (the pre-rename slot stays registered until it is
# deleted).
_GUID = uuid.uuid5(uuid.NAMESPACE_DNS, "panelboss.tray")


def _guid_item(guid):
    """A NOTIFYICONDATAW.GUID holding `guid`'s sixteen bytes:
    mixed-endian - the first three fields are read big-endian from the
    bytes so the in-memory little-endian fields textify to the same
    value uuid str() prints; the last eight bytes go straight across.
    scripts/visible_test.py reuses this to swap in a TEST guid, so its
    ADD/DELETE never collide with a running app's icon."""
    item = win32.NOTIFYICONDATAW.GUID(
        Data1=int.from_bytes(guid.bytes[0:4], "big"),
        Data2=int.from_bytes(guid.bytes[4:6], "big"),
        Data3=int.from_bytes(guid.bytes[6:8], "big"))
    item.Data4[:] = guid.bytes[8:16]
    return item


_GUID_ITEM = _guid_item(_GUID)

_guid_live = True           # cleared by the NIM_ADD rejection fallback
try:
    # pystray binds this API with an errcheck that RAISES when the
    # registration returns 0, so the "Shell could not register" case
    # arrives as an exception, not as a zero: fail-open here, the
    # off-pump fallback swap in _warm_menu needs no message at all
    _MENU_READY = win32.RegisterWindowMessage(
        "PanelBossMenuReady")
except Exception:
    _MENU_READY = 0


def _stamp_identity(data):
    """uID=1 on every call, plus the NIF_GUID stamp while the Shell
    accepts it. pystray sends no uID at all (its hID kwarg is not a
    field of the struct and ctypes drops it), so without this every
    call carries uID=0 and each new process image gets a new slot."""
    data.uID = 1
    if _guid_live:
        data.uFlags |= win32.NIF_GUID
        data.guidItem = _GUID_ITEM


def _wrap_shell_notify():
    """The identity stamp lives at the one choke point every NIM_* call
    passes: the module attribute pystray._win32.Icon._message looks up
    at call time. Whatever is there now gets wrapped (the raw windll
    function, or a test spy that got there first), so an outer
    observer still sees the stamped struct."""
    global _guid_live
    inner = win32.Shell_NotifyIcon

    def stamped(code, data):
        global _guid_live
        _stamp_identity(data)
        if code == win32.NIM_ADD and not getattr(
                stamped, "_added_once", False):
            # ghost reclaim (owner UAT, Oct 15): every forced kill of the
            # day - and Stop-Process kills skip NIM_DELETE - leaves the
            # Shell holding our (path, uID) slot with a dead owner. The
            # fresh ADD then ANSWERS TRUE and renders NOTHING: a stale
            # entry is the one shell state that dedupes a live one.
            # Delete our identity before the first ADD of the process
            # (a missing slot is a legitimate FALSE), then add clean.
            stamped._added_once = True
            inner(win32.NIM_DELETE, data)
            time.sleep(0.05)
        ok = bool(inner(code, data))
        if not ok and code == win32.NIM_ADD and _guid_live:
            # the common refused ADD is our OWN hide-then-show race
            # (display change: NIM_DELETE then immediate NIM_ADD while
            # the Shell still holds the GUID slot -> already-exists),
            # not a Shell that predates NIF_GUID. Reclaim first: delete
            # the very identity we are adding (a missing slot is a
            # legitimate FALSE), breathe, re-ADD unchanged - only
            # after two refusals treat the Shell as GUID-blind.
            for _attempt in range(2):
                inner(win32.NIM_DELETE, data)
                time.sleep(0.05)
                ok = bool(inner(code, data))
                if ok:
                    log.info("tray: reclaimed the GUID slot after a "
                             "refused add (the Shell was mid-release)")
                    return True
            # still refused: a Shell that predates NIF_GUID (or a test
            # double). The identity then rests on uID alone - keep
            # uID=1, drop the GUID, say so once, retry. The latch is
            # never raised again: a GUID-less registration must not
            # get GUID-stamped MODIFYs.
            _guid_live = False
            log.warning("the Shell refused the NIF_GUID add; the tray "
                        "identity now rests on uID=1 alone")
            data.uFlags &= ~win32.NIF_GUID
            data.guidItem = win32.NOTIFYICONDATAW.GUID()
            ok = bool(inner(code, data))
        return ok

    win32.Shell_NotifyIcon = stamped
    return stamped


_wrap_shell_notify()

try:                       # the wrap, the _message_handlers table and
    _PS_VERSION = metadata.version("pystray")   # the hID bug were all
except Exception:          # verified against pystray 0.19.5 only:
    _PS_VERSION = "?"      # shout before the silent breakage does
if _PS_VERSION != "0.19.5":
    log.warning("tray identity shim is verified against pystray "
                "0.19.5, running %s: check that the Shell_NotifyIcon "
                "wrap still fits" % _PS_VERSION)

# ------------------------------------------------------------- modal menu ---
# The warm-worker swap (_warm_menu -> _try_swap) must not destroy the
# HMENU a TrackPopupMenuEx is showing: its modal loop pumps this
# thread's messages, pystray re-shows the TRACKED handle after the
# return, and a handle destroyed under the user's open menu is the
# audit MED. pystray exposes no menu-open state, so the flag lives at
# the same class of choke point as the identity wrap: the module
# attribute pystray._win32 looks up at CALL time.
_menu_modal = False


def _wrap_track_popup():
    global _menu_modal
    inner = win32.TrackPopupMenuEx

    def tracked(*args):
        global _menu_modal
        _menu_modal = True
        try:
            return inner(*args)
        finally:
            _menu_modal = False

    win32.TrackPopupMenuEx = tracked
    return tracked


_wrap_track_popup()

COLORS = {
    "active": (80, 200, 120),     # typing, the gate is closed
    "counting": (240, 200, 40),   # the camera is watching
    "off": (60, 60, 60),          # dark screens
    "paused": (240, 90, 40),      # snoozing or paused
}


def _image(state="active"):
    img = Image.new("RGB", (64, 64))        # the box is black until the
    draw = ImageDraw.Draw(img)              # background is applied
    draw.rectangle((0, 0, 63, 63), fill=(255, 255, 255))
    color = COLORS.get(state, COLORS["active"])
    draw.ellipse((8, 8, 56, 56), fill=color)   # the circle comes last
    return img


class Tray(threading.Thread):

    def __init__(self, queue_, config, ui_events=None, monitor=None):
        super().__init__(daemon=True, name="tray")
        self.events = queue_
        self.ui_events = ui_events             # "open" the window requests
        self.config = config
        self.monitor = monitor                 # the live source for the
                                               # picker's mode tail
        self.icon = None
        self._pending_menu = None              # the warm worker's result,
                                               # consumed at a pump-safe
                                               # instant by _on_menu_ready

    def run(self):
        # the first menu is deliberately light: the two submenus whose
        # building costs seconds (camera enumeration, the gpu probe)
        # start as honest "probing..." placeholders, and the warm
        # worker swaps in the real ones when it finishes
        try:
            self.icon = pystray.Icon(name="PanelBoss",
                                     icon=_image("active"),
                                     title="PanelBoss",
                                     menu=self._light_menu())
            self.icon.run(setup=self._ready)
            if self.monitor is not None and not self.monitor.quit:
                # pystray 0.19.5's own _mainloop swallows pump
                # exceptions and NIM_DELETEs the icon, so run() returns
                # cleanly with the icon gone and no control surface left;
                # the box is the only channel pythonw has for a dead pump
                log.error("the tray pump exited without a quit request - "
                          "the icon is gone; shutting the app down "
                          "instead of living uncontrollably")
                # enqueue FIRST, box second (second-gate note): the
                # quit event closes the window and releases the
                # instance mutex WHILE the user reads the box -
                # ordering them the other way kept the lock and a
                # live window hostage to a modal 10 s funeral
                self.monitor.events.put(("quit", True))
                                                # the REAL quit verb: the
                                                # loop drains it, closes
                                                # the window via ui_events
                                                # (_events.py:159-163) and
                                                # releases the lock - a
                                                # bare quit=True would
                                                # stop the monitor but
                                                # leave window+process
                                                # holding the instance
                                                # mutex with no icon
                                                # (final-gate blocker 1)
                from .cli import timeout_notice   # the box helper
                timeout_notice("PanelBoss: the tray icon died "
                               "unexpectedly...",
                               "PanelBoss", 10000)
        except Exception:
            log.exception("the tray always runs last and pythonw has no "
                          "console; the failure would otherwise vanish")
            if self.monitor is not None and not self.monitor.quit:
                # third-gate ledger 10: a RAISED death is the B1 class
                # too - icon never lived, the loop would run ownerless
                # behind a held mutex; queue the real quit, no box
                # (the log line above is the confession here)
                self.monitor.events.put(("quit", True))

    def _ready(self, icon):
        icon.visible = True       # pystray starts hidden; our setup
                                  # replaced the default one that shows it
        icon.update_menu()        # and the constructor skipped the HMENU
        log.info("tray icon ready")
        try:
            icon.notify("PanelBoss",
                        "running; quit from the icon menu")
        except Exception:
            pass                        # notifications are a courtesy
        if _MENU_READY:      # the pump-gate (audit MED, W3A): the
                             # handler is the deferred path's pump half
                             # only when the private message registered;
                             # a fake icon without the handlers table
                             # must not die in setup over it
            icon._message_handlers[_MENU_READY] = self._on_menu_ready
        # the heavy submenus are built OFF the pump thread (blocking it
        # ~13 s would leave right-clicks dead until the camera probe
        # finished) and posted back for the swap when they are ready
        threading.Thread(target=self._warm_menu, args=(icon,),
                         daemon=True, name="tray-menu").start()

    def _warm_menu(self, icon):
        """Build the full menu off the pump thread, then land the swap
        (icon.menu + the HMENU rebuild) at a pump-safe instant: the
        pump's own _on_menu_ready while the private message is
        registered, else the worker's single gated attempt. Until the
        swap lands, a right-click gets the light menu with its
        placeholders - everything except the two slow submenus works
        the whole time.

        THE MODAL-LOOP HAZARD (audit MED, W3A): the right-click path
        (pystray's _on_notify) runs TrackPopupMenuEx ON THE PUMP
        THREAD - a modal loop that keeps pumping this window's
        messages while the menu is on screen. A swap from the warm
        worker while that loop runs destroys the HMENU the user is
        looking at under pystray's re-show of the tracked handle -
        the menu vanishes mid-paint, and with the pump-death-is-fatal
        law the blast radius grew. pystray exposes no menu-open state,
        so _wrap_track_popup brackets the _menu_modal flag around the
        call at the same class of choke point as the identity wrap,
        and the worker's ONE attempt is gated on pump liveness AND
        that flag - and it runs only in the no-message world, where
        the pump has no consume site. The pump's own handler is
        pump-safe BY CONSTRUCTION (see _on_menu_ready). One attribute,
        one consume site, one attempt - no new threads."""
        try:
            menu = self._build_menu()
        except Exception:
            log.exception("the warm menu failed; the light menu stays")
            return
        self._pending_menu = menu
        if _MENU_READY:
            # the pump consumes the pending menu at a pump-safe
            # instant (see _on_menu_ready); no worker race at all
            win32.PostMessage(icon._hwnd, _MENU_READY, 0, 0)
            return
        log.warning("the private menu message would not register; the "
                    "worker's gated attempt is the only swap path")
        self._try_swap(icon)
        if self._pending_menu is not None:
            log.info("tray: the full menu arrived while a menu was "
                     "open; the light menu stays")

    def _try_swap(self, icon):
        """The worker's ONE attempt, pump-gated (see _warm_menu's
        hazard note): swap only while the pump thread lives and
        _menu_modal says no TrackPopupMenuEx loop can be re-showing
        the handle this swap destroys. fail-open on every read: the
        light menu is the designed fallback."""
        try:
            if (not _menu_modal and icon is not None
                    and getattr(icon, "_thread", None) is not None
                    and icon._thread.is_alive()):
                icon.menu = self._pending_menu   # the setter rebuilds
                self._pending_menu = None        # the HMENU
                log.info("tray: full menu in place")
        except Exception:
            pass                   # the swap is a courtesy; the light
                                   # menu is the designed fallback

    def _on_menu_ready(self, wparam, lparam):
        """Runs on the pump thread (pystray's _message_handlers table,
        the same mechanism as WM_TASKBARCREATED). Pump-safe by the
        right-click ORDERING (reviewer gate, Oct 13): inside pystray's
        right-click path the menu re-attaches only AFTER
        TrackPopupMenuEx returns, so this handler either runs in the
        flat pump loop or in the modal pump while the menu is already
        closed. RESIDUAL, named rather than probed: whether the modal
        pump delivers OUR registered message before TrackPopupMenuEx
        returns is asserted, not measured - if it does, the swap
        destroys the on-screen HMENU once and the user's open menu
        closes early (bounded: single consume, only in the first ~13 s
        of process life; no crash, no stuck app). A rebuild landing
        between the close and the re-show is exactly what re-tracks
        the FULL menu for this same open."""
        if self._pending_menu is not None:
            icon = self.icon
            icon.menu = self._pending_menu   # the setter rebuilds the HMENU
            self._pending_menu = None        # one handle, one swap: a
            log.info("tray: full menu in place")  # repeat _MENU_READY is
                                             # a no-op, not a double swap

    # ------------------------------------------------------------- menu ---
    def _build_menu(self):
        return pystray.Menu(
            # first item + default=True: the win32 backend maps a plain
            # LEFT click of the icon (WM_LBUTTONUP -> icon.__call__) to
            # the menu's default item - settings open on a click, the
            # full menu stays the right-click affair
            pystray.MenuItem("Settings...", action=self._settings,
                             default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Detection device", self._device_menu()),
            pystray.MenuItem("CUDA GPU id", self._gpu_menu()),
            pystray.MenuItem("Camera", self._camera_menu()),
            pystray.MenuItem("Detection mode", self._mode_menu()),
            pystray.MenuItem("Wake policy", self._policy_menu()),
            *self._quick_items())

    def _probing(self):
        """A fresh disabled placeholder for a submenu the warm worker
        is still building: action None (asserted to a no-op by
        pystray) and enabled False, which the win32 backend maps to
        the grayed-out MFS_DISABLED state."""
        return pystray.Menu(pystray.MenuItem("probing...", None,
                                             enabled=False))

    def _light_menu(self):
        """The first right-click gets everything except the two
        submenus whose building costs seconds (camera enumeration is
        ~13 s on a box with a dead index; the gpu probe is a
        subprocess): those slots carry an honest "probing..."
        placeholder until the warm worker swaps in the real ones."""
        return pystray.Menu(
            pystray.MenuItem("Settings...", action=self._settings,
                             default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Detection device", self._device_menu()),
            pystray.MenuItem("CUDA GPU id", self._probing()),
            pystray.MenuItem("Camera", self._probing()),
            pystray.MenuItem("Detection mode", self._mode_menu()),
            pystray.MenuItem("Wake policy", self._policy_menu()),
            *self._quick_items())

    def _quick_items(self):
        """The tail both menus share: every one of these is a plain
        queue put or a fast config read, so none of them waits on the
        slow submenus."""
        return [
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Pause", action=self._pause),
            pystray.MenuItem("Resume", action=self._resume),
            pystray.MenuItem("Pause auto re-off",
                             action=lambda i: self.events.put(("reoff", True))),
            pystray.MenuItem("Resume auto re-off",
                             action=lambda i: self.events.put(("reoff", False))),
            pystray.MenuItem("Snooze 10 min", action=lambda i: self._snooze(10)),
            pystray.MenuItem("Snooze 30 min", action=lambda i: self._snooze(30)),
            pystray.MenuItem("Snooze 60 min", action=lambda i: self._snooze(60)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("start with Windows",
                             action=self._startup,
                             checked=self._startup_checked),
            pystray.MenuItem("Quit", action=self._quit)]

    def _device_menu(self):
        return pystray.Menu(
            pystray.MenuItem("auto", action=lambda i: self._device("auto"),
                             checked=self._device_checker("auto")),
            pystray.MenuItem("CPU", action=lambda i: self._device("cpu"),
                             checked=self._device_checker("cpu")),
            pystray.MenuItem("CUDA GPU",
                             action=lambda i: self._device("cuda"),
                             checked=self._device_checker("cuda")))

    def _policy_menu(self):
        return pystray.Menu(
            pystray.MenuItem("re-off after wake",
                             action=lambda i: self._policy("re_off"),
                             checked=self._policy_checker("re_off")),
            pystray.MenuItem("leave on after wake",
                             action=lambda i: self._policy("leave_on"),
                             checked=self._policy_checker("leave_on")))

    def _gpu_menu(self):
        from . import inference
        gpus = inference.cuda_gpus() or [(n, "gpu %s" % n)
                                         for n in range(4)]
        return pystray.Menu(*[
            pystray.MenuItem("gpu %s: %s" % (gid, name),
                             action=self._gpu_picker(gid),
                             checked=self._gpu_checker(gid))
            for gid, name in gpus])

    def _mode_menu(self):
        return pystray.Menu(
            pystray.MenuItem("person (ONNX model)",
                             action=lambda i: self._mode("person"),
                             checked=self._mode_checker("person")),
            pystray.MenuItem("motion (no model; IR/depth OK)",
                             action=lambda i: self._mode("motion"),
                             checked=self._mode_checker("motion")))

    def _camera_menu(self):
        """Which index opens; the PnP names come after the indexes and
        are unreliable (documented in the README). Each picker carries
        the eye's mode right now as a tail - display only, the tray
        never edits the policy."""
        from . import camera
        if not self.config["camera"].get("enabled"):
            # the consent gate (redesign law 1): the enumeration
            # below OPENS every index on the desk - a right-click
            # on a tray menu must not touch a driver the owner has
            # not consented to. One honest info row instead (the
            # detection tab's switch owns the door).
            return pystray.Menu(pystray.MenuItem(
                "detection is off", action=lambda i: None,
                enabled=False))
        names = camera.camera_names()
        items = []
        ir = camera.hello_ir_names()   # [] without the whircam bridge;
        if ir:                         # first entry = IR group 0
            items.append(pystray.MenuItem(
                "hello IR: %s%s" % (ir[0],
                                    self._mode_suffix(camera.HELLO_IR)),
                action=self._camera_picker(camera.HELLO_IR),
                checked=self._camera_checker(camera.HELLO_IR)))
        for index, opened, width in camera.enumerate_cameras():
            if not opened:
                continue
            label = "index %s (%s px wide)" % (index, int(width))
            if index < len(names):
                label += " %s" % names[index]
            label += self._mode_suffix(index)
            items.append(pystray.MenuItem(
                label, action=self._camera_picker(index),
                checked=self._camera_checker(index)))
        if not items:
            return pystray.Menu(pystray.MenuItem("no camera opens",
                                                 action=lambda i: None,
                                                 enabled=False))
        return pystray.Menu(*items)

    # ---------------------------------------------------------- actions ---
    def _device(self, name):
        self.config["inference"]["device"] = name
        self.events.put(("device", name))

    def _mode(self, name):
        self.config["detection"]["mode"] = name
        self.events.put(("detection_mode", name))

    def _mode_checker(self, name):
        def check(item):
            return self.config["detection"].get("mode") == name
        return check

    def _device_checker(self, name):
        def check(item):
            return self.config["inference"]["device"] == name
        return check

    def _policy(self, name):
        self.config["recovery"]["wake_policy"] = name
        self.events.put(("wake_policy", name))

    def _policy_checker(self, name):
        def check(item):
            return self.config["recovery"]["wake_policy"] == name
        return check

    def _gpu_picker(self, gid):
        def action(icon):
            self.config["inference"]["device_id"] = gid
            self.events.put(("device_id", gid))
        return action

    def _gpu_checker(self, gid):
        def check(item):
            return self.config["inference"]["device_id"] == gid
        return check

    def _camera_picker(self, index):
        def action(icon):
            self.config["camera"]["index"] = index
            self.events.put(("camera", index))
        return action

    def _camera_checker(self, index):
        def check(item):
            # a multi-camera roster ticks every eye on duty:
            # the rotation really does check with each of them
            from . import config
            return index in config.normalize_index(
                self.config["camera"]["index"])
        return check

    def _mode_suffix(self, index):
        """The picker's tail: "- always on", "- poll" or "- off", the
        eye's mode right now (the live state decides: an always eye
        past its wear guard reads "poll"). Display only, and it must
        never kill the warm menu, so a failure degrades to no tail."""
        if self.monitor is None:
            return ""
        from . import config
        try:
            mode = self.monitor.effective_mode(index)
        except Exception:
            return ""
        return " - %s" % config.MODE_LABELS.get(mode, mode)

    def _settings(self, icon=None):
        if self.ui_events is not None:
            self.ui_events.put(("open", None))    # the window listens

    def _startup(self, icon=None):
        """One click flips whatever the Run key holds right now (the
        registry is the truth, and a stale entry from a moved folder
        deserves the same one-click fix); the open window resyncs."""
        from . import startup
        ok, msg = (startup.disable() if startup.enabled() is not None
                   else startup.enable())
        if not ok:
            log.warning("start with Windows: %s", msg)
        if self.ui_events is not None:
            self.ui_events.put(("startup", None))

    def _startup_checked(self, item):
        from . import startup
        return startup.enabled() is not None

    def _pause(self, icon=None):
        self.events.put(("pause", True))

    def _resume(self, icon=None):
        self.events.put(("pause", False))

    def _snooze(self, minutes, icon=None):
        self.events.put(("snooze", minutes))

    def _quit(self, icon=None):
        self.events.put(("quit", True))

    def notify(self, message):
        """Balloon from the state machine (burst warnings and such)."""
        if self.icon is not None:
            try:
                self.icon.notify(message, "PanelBoss")
            except Exception:
                pass                        # notifications are a courtesy

    def set_state(self, state):
        """Recolor the circle; the full UI overhaul wires this later."""
        if self.icon is not None:
            self.icon.icon = _image(state)

    def stop(self):
        if self.icon is not None:
            self.icon.stop()
