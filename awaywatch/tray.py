"""Barebones system tray; full UI overhaul is scheduled later.

The icon is a circle that changes color with the machine state; the menu
pushes commands into the state machine's queue. pystray runs callbacks on
its own thread, so nothing here touches the camera or display directly.

pystray's first argument is 'name', not 'title' (verified against the
installed 0.19.5); getting that wrong raised inside the tray thread and
the traceback went to a console pythonw.exe does not have.
"""

from __future__ import annotations

import logging
import threading
import time

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

    def __init__(self, queue_, config):
        super().__init__(daemon=True, name="tray")
        self.events = queue_
        self.config = config
        self.icon = None

    def run(self):
        menu = pystray.Menu(
            pystray.MenuItem("Pause", action=self._pause),
            pystray.MenuItem("Resume", action=self._resume),
            pystray.MenuItem("Snooze 10 min",
                             action=lambda i: self._snooze(10)),
            pystray.MenuItem("Snooze 30 min",
                             action=lambda i: self._snooze(30)),
            pystray.MenuItem("Snooze 60 min",
                             action=lambda i: self._snooze(60)),
            pystray.MenuItem("Quit", action=self._quit))
        try:
            self.icon = pystray.Icon(name="ICU Presence Detector",
                                     icon=_image("active"),
                                     title="ICU Presence Detector",
                                     menu=menu)
            self.icon.run(setup=self._ready)   # the callback always runs
                                               # after the icon
        except Exception:
            log.exception("the tray always runs last and pythonw has no "
                          "console; the failure would otherwise vanish")

    def _ready(self, icon):
        icon.visible = True       # pystray starts hidden and the default
                                  # setup function (which we replaced by
                                  # passing setup=) is what shows it; the
                                  # class docstring says so. NIM_ADD never
                                  # reaches the Shell otherwise.
        log.info("tray icon ready")
        try:
            icon.notify("ICU Presence Detector",
                        "running; quit from the icon menu")
        except Exception:
            pass                        # notifications are a courtesy

    def _pause(self, icon=None):
        self.events.put(("pause", True, time.monotonic()))

    def _resume(self, icon=None):
        self.events.put(("pause", False, time.monotonic()))

    def _snooze(self, minutes, icon=None):
        self.events.put(("snooze", minutes, time.monotonic()))

    def _quit(self, icon=None):
        self.events.put(("quit", True, time.monotonic()))

    def set_state(self, state):
        """Recolor the circle; the full UI overhaul wires this later."""
        if self.icon is not None:
            self.icon.icon = _image(state)

    def stop(self):
        if self.icon is not None:
            self.icon.stop()
