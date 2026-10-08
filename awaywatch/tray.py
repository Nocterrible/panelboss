"""Barebones system tray; full UI overhaul is scheduled later.

The icon is a circle that changes color with the machine state; the menu
pushes commands into the state machine's queue. pystray runs callbacks on
its own thread, so nothing here touches the camera or display directly.
"""

from __future__ import annotations

import threading
import time

from PIL import Image
from PIL import ImageDraw

import pystray


COLORS = {
    "active": (80, 200, 120),     # typing, the gate is closed
    "counting": (240, 200, 40),   # the camera is watching
    "off": (60, 60, 60),          # dark screens
    "paused": (240, 90, 40),      # snoozing or paused
}


def _image(state="active"):
    img = Image.new("RGB", (64, 64))       # the box is black until the
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
        menu = (pystray.MenuItem("Pause", action=self._pause),
                pystray.MenuItem("Resume", action=self._resume),
                pystray.MenuItem("Snooze 10 min",
                                action=lambda i: self._snooze(10)),
                pystray.MenuItem("Snooze 30 min",
                                action=lambda i: self._snooze(30)),
                pystray.MenuItem("Snooze 60 min",
                                action=lambda i: self._snooze(60)),
                pystray.MenuItem("Quit", action=self._quit))
        self.icon = pystray.Icon(title="ICU Presence Detector",
                           image=_image("active"),
                           menu=menu)
        self.icon.run(setup=lambda icon: None)   # the callback always runs
                                                 # after the icon

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
