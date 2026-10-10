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
"""

from __future__ import annotations

import logging
import threading

import pystray
from PIL import Image
from PIL import ImageDraw

log = logging.getLogger("tray")

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

    def run(self):
        try:
            self.icon = pystray.Icon(name="ICU Presence Detector",
                                     icon=_image("active"),
                                     title="ICU Presence Detector",
                                     menu=self._build_menu())
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

    # ------------------------------------------------------------- menu ---
    def _build_menu(self):
        devices = pystray.Menu(
            pystray.MenuItem("auto", action=lambda i: self._device("auto"),
                             checked=self._device_checker("auto")),
            pystray.MenuItem("CPU", action=lambda i: self._device("cpu"),
                             checked=self._device_checker("cpu")),
            pystray.MenuItem("CUDA GPU",
                             action=lambda i: self._device("cuda"),
                             checked=self._device_checker("cuda")))
        policies = pystray.Menu(
            pystray.MenuItem("re-off after wake",
                             action=lambda i: self._policy("re_off"),
                             checked=self._policy_checker("re_off")),
            pystray.MenuItem("leave on after wake",
                             action=lambda i: self._policy("leave_on"),
                             checked=self._policy_checker("leave_on")))
        from . import inference
        gpus = inference.cuda_gpus() or [(n, "gpu %s" % n)
                                         for n in range(4)]
        gpu_menu = pystray.Menu(*[
            pystray.MenuItem("gpu %s: %s" % (gid, name),
                             action=self._gpu_picker(gid),
                             checked=self._gpu_checker(gid))
            for gid, name in gpus])
        modes = pystray.Menu(
            pystray.MenuItem("person (ONNX model)",
                             action=lambda i: self._mode("person"),
                             checked=self._mode_checker("person")),
            pystray.MenuItem("motion (no model; IR/depth OK)",
                             action=lambda i: self._mode("motion"),
                             checked=self._mode_checker("motion")))
        return pystray.Menu(
            # first item + default=True: the win32 backend maps a plain
            # LEFT click of the icon (WM_LBUTTONUP -> icon.__call__) to
            # the menu's default item - settings open on a click, the
            # full menu stays the right-click affair
            pystray.MenuItem("Settings...", action=self._settings,
                             default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Detection device", devices),
            pystray.MenuItem("CUDA GPU id", gpu_menu),
            pystray.MenuItem("Camera", self._camera_menu()),
            pystray.MenuItem("Detection mode", modes),
            pystray.MenuItem("Wake policy", policies),
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
            pystray.MenuItem("Quit", action=self._quit))

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
