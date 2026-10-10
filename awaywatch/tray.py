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
# site at _win32.py:337).
_GUID = uuid.uuid5(uuid.NAMESPACE_DNS, "icu-presence-detector.tray")


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
        "ICUPresenceDetectorMenuReady")
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
        ok = bool(inner(code, data))
        if not ok and code == win32.NIM_ADD and _guid_live:
            # a Shell that predates NIF_GUID (or a test double) refused
            # the GUID-stamped ADD: the identity then rests on uID
            # alone - keep uID=1, drop the GUID, say so once, retry
            # (NIM_DELETE legitimately fails for missing icons, so the
            # fallback is an ADD-only question)
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

    def __init__(self, queue_, config, ui_events=None):
        super().__init__(daemon=True, name="tray")
        self.events = queue_
        self.ui_events = ui_events             # "open" the window requests
        self.config = config
        self.icon = None
        self._full_menu = None                 # the warm worker's result,
                                              # read by _on_menu_ready

    def run(self):
        # the first menu is deliberately light: the two submenus whose
        # building costs seconds (camera enumeration, the gpu probe)
        # start as honest "probing..." placeholders, and the warm
        # worker swaps in the real ones when it finishes
        try:
            self.icon = pystray.Icon(name="ICU Presence Detector",
                                     icon=_image("active"),
                                     title="ICU Presence Detector",
                                     menu=self._light_menu())
            self.icon.run(setup=self._ready)
        except Exception:
            log.exception("the tray always runs last and pythonw has no "
                          "console; the failure would otherwise vanish")

    def _ready(self, icon):
        icon.visible = True       # pystray starts hidden; our setup
                                  # replaced the default one that shows it
        icon.update_menu()        # and the constructor skipped the HMENU
        log.info("tray icon ready")
        try:
            icon.notify("ICU Presence Detector",
                        "running; quit from the icon menu")
        except Exception:
            pass                        # notifications are a courtesy
        icon._message_handlers[_MENU_READY] = self._on_menu_ready
        # the heavy submenus are built OFF the pump thread (blocking it
        # ~13 s would leave right-clicks dead until the camera probe
        # finished) and posted back for the swap when they are ready
        threading.Thread(target=self._warm_menu, args=(icon,),
                         daemon=True, name="tray-menu").start()

    def _warm_menu(self, icon):
        """Build the full menu off the pump thread, then post a private
        window message so the swap (icon.menu + the HMENU rebuild)
        happens on the pump thread, where the HMENU belongs. Until the
        swap lands, a right-click gets the light menu with its
        placeholders - everything except the two slow submenus works
        the whole time."""
        try:
            menu = self._build_menu()
        except Exception:
            log.exception("the warm menu failed; the light menu stays")
            return
        self._full_menu = menu
        if _MENU_READY:
            win32.PostMessage(icon._hwnd, _MENU_READY, 0, 0)
            return
        log.warning("the private menu message would not register; the "
                    "swap runs off the pump thread instead")
        icon.menu = menu      # the property setter rebuilds the HMENU
        log.info("tray: full menu in place")

    def _on_menu_ready(self, wparam, lparam):
        """Runs on the pump thread (pystray's _message_handlers table,
        the same mechanism as WM_TASKBARCREATED)."""
        if self._full_menu is not None:
            icon = self.icon
            icon.menu = self._full_menu    # the setter rebuilds the HMENU
            log.info("tray: full menu in place")

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
        are unreliable (documented in the README)."""
        from . import camera
        names = camera.camera_names()
        items = []
        ir = camera.hello_ir_names()   # [] without the whircam bridge;
        if ir:                         # first entry = IR group 0
            items.append(pystray.MenuItem(
                "hello IR: %s" % ir[0],
                action=self._camera_picker(camera.HELLO_IR),
                checked=self._camera_checker(camera.HELLO_IR)))
        for index, opened, width in camera.enumerate_cameras():
            if not opened:
                continue
            label = "index %s (%s px wide)" % (index, int(width))
            if index < len(names):
                label += " %s" % names[index]
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
                self.icon.notify(message, "ICU Presence Detector")
            except Exception:
                pass                        # notifications are a courtesy

    def set_state(self, state):
        """Recolor the circle; the full UI overhaul wires this later."""
        if self.icon is not None:
            self.icon.icon = _image(state)

    def stop(self):
        if self.icon is not None:
            self.icon.stop()
