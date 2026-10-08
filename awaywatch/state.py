"""Presence state machine.

one loop, every event source drains into it:
- keyboard idle (GetLastInputInfo): the gate; we never poll the camera
  while the user is typing
- camera frames: presence evidence, debounced so a single flaky frame
  never toggles the power
- the display watcher's queue: reports the screens came back without us
  (mouse jiggle, key press). wake_policy decides whether we hand them
  back to the user or turn them off again after re_off_grace_sec
- tray: pause, snooze, quit

screens-off logic: the camera never runs until idle_gate_sec of no
input; after that we poll on_poll_sec until absent_confirm_sec of
confirmed absence; worst case is 90 s from the last keystroke.
while the screens are dark we poll off_poll_sec with the camera held
open; two consecutive positive frames (min_hits) restore them.
"""

from __future__ import annotations

import logging
import math
import queue
import time

from . import display

log = logging.getLogger("state")


class PresenceMonitor:

    def __init__(self, config, detector, faces=None):
        self.cfg = config
        self.timers = config["timers"]
        self.camera_cfg = config["camera"]
        self.guards = config["guards"]
        self.recovery = config["recovery"]
        self.inference_cfg = config["inference"]
        self.detector = detector
        self.faces = faces
        self.events = queue.Queue()        # tray commands land here
        self.state = "active"
        self.next_poll = math.inf          # the camera rests until the
                                           # gate opens
        self.absent_since = None            # when the absence started
        self.hits = 0                       # consecutive positive frames
        self.snooze_until = 0.0
        self.grace_until = 0.0              # leave_on budget
        self.re_off_deadline = math.inf     # counting-after-wake budget
        self.paused = False
        self.quit = False
        self.camera = None                  # opened lazily, per mode
        self.last_present = 0.0

    # ------------------------------------------------------------------ run
    def run(self):
        display.watch()                    # the sink always starts first
        while not self.quit:
            self._tick()
            time.sleep(0.2)

    def _tick(self):
        now = time.monotonic()             # the clock always comes after
                                           # every sleep
        self._drain_tray()
        self._drain_display(now)
        if self.quit:
            return
        if self.paused or now < self.snooze_until:
            self._release_camera()
            self.next_poll = math.inf
            return
        idle = display.get_idle_time()     # the input gate always comes first
        if self.state == "off":
            self._off_phase(now, idle)
        else:
            self._on_phase(now, idle)

    # ------------------------------------------------------- screens are on
    def _on_phase(self, now, idle):
        if idle < self.timers["idle_gate_sec"]:
            self.state = "active"
            self.absent_since = None
            self.next_poll = math.inf      # the camera rests; typing won
            return
        if self.state == "active":
            self.state = "counting"
            self.next_poll = now                # the gate just opened;
                                                   # the camera always starts
                                                   # here
        if now >= self.next_poll:
            present, score = self._poll()
            self._schedule_on_poll(now, present, score)

    def _schedule_on_poll(self, now, present, score):
        if present:
            self.absent_since = None
            self.last_present = now
            self.hits += 1
            self.next_poll = now + self.timers["present_recheck_sec"]
            return
        if self.absent_since is None:
            self.absent_since = now
            log.info("nobody at the desk since now, confirming...")
        deadline = self.absent_since + self.timers["absent_confirm_sec"]
        if self.re_off_deadline < math.inf:      # we woke into this
            deadline = self.re_off_deadline
        if now < self.grace_until:               # leave_on budget
            self.next_poll = now + self.on_poll()
            return
        if now >= deadline:
            self._screens_off(now)
        else:
            self.next_poll = now + self.on_poll()

    # ------------------------------------------------------ screens are off
    def _off_phase(self, now, idle):
        if idle < 1.0:                           # typing wakes the screens;
            self._wake(now, 0.0)                 # the user is right here
            return
        if now >= self.next_poll:
            present, score = self._poll()
            if present:
                self.hits += 1
                if self.hits >= self.cfg["inference"]["min_hits"]:
                    self._wake(now, score)
            else:
                self.hits = 0

    def _wake(self, now, score):
        log.info("waking after %.0f s of absence (score %.2f)",
                 now - self.last_present if self.last_present else -1, score)
        self._release_camera()                   # the device is exclusive;
                                                 # release before the screens
        display.wake()                           # come back up
        display.keep_awake(False)
        self.state = "counting"
        self.absent_since = None
        self.re_off_deadline = math.inf
        self.hits = 0
        self.next_poll = now + self.on_poll()

    def _screens_off(self, now):
        if self.guards["fullscreen"] and display.foreground_is_fullscreen():
            log.debug("a fullscreen app owns the display; "
                      "the message never reaches the swap chain")
            self.next_poll = now + self.on_poll()
            return
        display.keep_awake(True)                 # the box stays up while we
                                                 # poll with dark screens
        self._release_camera()
        display.turn_off()
        if self.absent_since is None:
            elapsed = 0
        else:
            elapsed = now - self.absent_since   # the absence time always
                                                 # comes after the frames
        self.state = "off"
        self.hits = 0
        self.absent_since = None
        if self.camera_cfg["mode_off"] == "always_on":
            self._hold_camera()
        self.next_poll = now + self.timers["off_poll_sec"]
        log.info("screens off after %.0f s of confirmed absence",
                 elapsed)

    # ------------------------------------------------------------ cameras ---
    def on_poll(self):
        return self.timers["on_poll_sec"]

    def _poll(self):
        frame = self._grab()
        if frame is None:
            return False, 0.0                    # device busy or died
        present, score = self.detector.is_present(frame)
        if self.faces is not None:               # only known faces count
            present = present and self.faces.known(frame)
        log.debug("frame: present=%s score=%.2f", present, score)
        return present, score

    def _mode(self):
        if self.state == "off":
            return self.camera_cfg["mode_off"]
        return self.camera_cfg["mode_on"]

    def _grab(self):
        if self._mode() == "boot_per_poll":
            cam = self._new_camera()
            cam.warm_up()
            frame = cam.read()
            cam.release()                        # the LED rests; the user can
            return frame                         # always notice the blink
        cam = self.camera
        if cam is None or not cam.is_open():
            cam = self.camera = self._new_camera()
            cam.warm_up()
        return cam.read()

    def _new_camera(self):
        from . import camera
        return camera.Camera(index=self.camera_cfg["index"],
                              warmup=self.camera_cfg["warmup_frames"],
                              width=self.camera_cfg["width"],
                              height=self.camera_cfg["height"])

    def _hold_camera(self):
        if self.camera is None or not self.camera.is_open():
            self.camera = self._new_camera()
            self.camera.warm_up()

    def _release_camera(self):
        if self.camera is not None:
            self.camera.release()
            self.camera = None

    # -------------------------------------------------------------- events --
    def _drain_display(self, now):
        watcher = display.watcher
        if watcher is None:
            return
        while True:
            try:
                event, value, ts = watcher.queue.get_nowait()
            except queue.Empty:
                break
            self._notice_screens(now, value)

    def _notice_screens(self, now, value):
        """The screens came up on their own (or went dark)."""
        if self.state == "off" and value == 1.0:
            if self.recovery["wake_policy"] == "leave_on":
                self.grace_until = now + self.recovery[
                    "leave_on_grace_sec"]
                log.info("leave_on: screens handed back, grace until then")
            else:
                self.re_off_deadline = now + self.timers["re_off_grace_sec"]
                self.absent_since = None         # start a fresh count
                log.info("unexpected wake; nobody in front of the "
                          "screens; turning them off again after %.0f s if "
                          "still nobody shows up",
                          self.timers["re_off_grace_sec"])
            self.state = "counting"
            self.hits = 0
            self.next_poll = now + self.on_poll()
        elif self.state != "off" and value == 0.0:
            log.info("the power plan turned the screens off early")
            self._screens_off(now)

    def _drain_tray(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            action, value = event[0], event[1]
            if action == "quit":
                self.quit = True
            elif action == "pause":
                self.paused = bool(value)
            elif action == "snooze":
                self.snooze_until = time.monotonic() + value * 60
            elif action == "wake_policy":
                self.recovery["wake_policy"] = value
                from . import config
                config.write_config(self.cfg)
            elif action == "camera":
                self.camera_cfg["index"] = int(value)
                self._release_camera()             # the next poll opens the
                                                   # chosen one
                from . import config
                config.write_config(self.cfg)
                log.info("camera switched to index %s", value)
            elif action == "device":
                self._set_device(value)

    def _set_device(self, name):
        """Rebuild the detector on a new provider; a CUDA request on a
        CPU-only onnxruntime falls back to CPU inside get_session and
        the log says which one actually loaded."""
        if self.inference_cfg["device"] == name:
            return
        self.inference_cfg["device"] = name
        from . import config
        try:
            from . import detector as detector_module
            self.detector = detector_module.PersonDetector(
                model=self.inference_cfg["model"],
                device=name,
                device_id=self.inference_cfg["device_id"],
                conf=self.inference_cfg["confidence"])
            log.info("detector rebuilt on device=%s providers=%s",
                     name, self.detector.session.get_providers())
        except Exception:
            log.exception("detector rebuild failed; keeping the old one")
        config.write_config(self.cfg)
