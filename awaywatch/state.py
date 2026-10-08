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
import threading
import time

from . import display

log = logging.getLogger("state")


class FrameBox:
    """The newest frame slot: the state machine writes after every
    detect, the settings window reads at its own pace. Newest wins,
    so the debug view can drop frames but never shows a stale model
    result next to a fresh picture."""

    def __init__(self):
        self._lock = threading.Lock()
        self.latest = None            # (bgr, boxes, scores, ts)

    def put(self, frame, boxes, scores):
        with self._lock:
            # cv2 hands out buffers it may recycle; the slot is a snapshot
            self.latest = (frame.copy(), boxes, scores, time.monotonic())

    def get(self):
        with self._lock:
            return self.latest


class PresenceMonitor:

    def __init__(self, config, detector, faces=None, ui_events=None):
        self.cfg = config
        self.timers = config["timers"]
        self.camera_cfg = config["camera"]
        self.guards = config["guards"]
        self.recovery = config["recovery"]
        self.inference_cfg = config["inference"]
        self.detector = detector
        self.faces = faces
        self.ui_events = ui_events           # the settings window listens
        self.events = queue.Queue()          # tray commands land here
        self.framebox = FrameBox()           # the debug view reads this
        # the screens' true state is unknowable at startup: the watcher
        # only learns from broadcasts, so a fresh instance that begins
        # while the monitors are dark (previous instance turned them
        # off, power plan did, a restart between) must not claim "on"
        # and then never wake - "unknown" behaves like counting but
        # takes the free SC_MONITORPOWER ON at the first proof of life
        self.state = "unknown"
        self.next_poll = math.inf            # the camera rests until the
                                             # gate opens
        self.absent_since = None              # when the absence started
        self.hits = 0                         # consecutive positive frames
        self.snooze_until = 0.0
        self.grace_until = 0.0                # leave_on budget
        self.re_off_deadline = math.inf       # counting-after-wake budget
        self.paused = False
        self.quit = False
        self.camera = None                    # opened lazily, per mode
        self.last_present = 0.0
        self.preview_until = 0.0              # debug window lease
        self.previewing = False
        self.wake_times = []                  # unexpected wakes, recent
        self.re_off_paused = False            # burst tripped; stays lit
        self.notifier = None                  # cli wires icon.notify
        self.power_cfg = config["power"]
        self.blockers = {"error": "not checked yet", "display": [],
                         "other": []}          # window reads this live
        self.blockers_until = 0.0             # throttle for powercfg
        self.display_held_reported = False

    # ------------------------------------------------------------------ run
    def run(self):
        display.watch()                    # the sink always starts first
        while not self.quit:
            try:
                self._tick()
            except Exception:              # a driver hiccup (the virtual
                log.exception("tick failed; the loop goes on")   # camera
                self._release_camera()     # has killed threads before)
            time.sleep(0.2)

    def _tick(self):
        now = time.monotonic()             # the clock always comes after
                                           # every sleep
        self._drain_tray()
        self._drain_display(now)
        if self.quit:
            return
        leased = now < self.preview_until
        if leased:
            # the settings window holds the camera; the lease expires on
            # its own so a killed UI cannot pin the device
            self.previewing = True
            self._preview(now)
            return
        if self.previewing:
            self.previewing = False
            self._release_camera()             # back to the scheduled modes
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
            if self.state == "unknown":
                self._force_on(now, "fresh input after a boot that did not "
                                    "know the screens' state")
                return
            if self.power_cfg.get("assistant_task"):
                # the window reads monitor.blockers live; without a
                # check here the readout would freeze the moment the
                # user touches the keyboard (throttled inside)
                self._check_blockers(now)
            self.state = "active"
            self.absent_since = None
            self.next_poll = math.inf      # the camera rests; typing won
            return
        unknown_start = self.state == "unknown"   # the poll below may
                                                   # resolve that question
        if self.state in ("active", "unknown"):
            self.state = "counting"
            self.next_poll = now                # the gate just opened;
                                                   # the camera always starts
                                                   # here
        if self.re_off_paused and idle <= 2 * self.timers["re_off_grace_sec"]:
            self.grace_until = now + self.recovery[
                "leave_on_grace_sec"]    # the desk is still hot: stay lit
        if now >= self.next_poll:
            if self.power_cfg["skip_camera_when_blocked"]:
                self._check_blockers(now)
                if self.blockers["display"]:
                    # some app already pins the screens; polling to
                    # defend them is wasted light and cpu
                    self.next_poll = now + self.power_cfg["poll_sec"]
                    return
            present, score = self._poll()
            if unknown_start and present:
                self._force_on(now, "somebody sits at a desk whose screens"
                                    " the app cannot prove are lit")
                return
            self._schedule_on_poll(now, present, score)

    def _check_blockers(self, now):
        """Throttled powercfg peek; unknown means unblocked (see power)."""
        if now < self.blockers_until:
            return
        self.blockers_until = now + self.power_cfg["poll_sec"]
        from . import power
        self.blockers = power.requests(
            self.power_cfg["ignore"],
            self.power_cfg.get("assistant_task", False))
        held = bool(self.blockers["display"])
        if held:
            self.absent_since = None   # absence restarts when they let go
        if held and not self.display_held_reported:
            log.info("apps hold the display awake (%s); the camera waits",
                     "; ".join(self.blockers["display"])[:300])
        elif not held and self.display_held_reported:
            log.info("the display is free again; the camera resumes")
        self.display_held_reported = held

    def _schedule_on_poll(self, now, present, score):
        if present:
            self.absent_since = None
            self.last_present = now
            self.hits += 1
            if (self.re_off_paused
                    and self.hits >= self.inference_cfg["min_hits"]):
                self._resume_re_off("the camera saw somebody again")
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

    def _force_on(self, now, reason):
        """SC_MONITORPOWER ON when the truth was unknown: on lit screens
        the broadcast is a no-op Windows itself sends on resume; on a
        dark desk a restart hid, it is the wake the state machine could
        not deduce. Free insurance, taken once per boot."""
        log.info("%s - sending the harmless power-on", reason)
        self._release_camera()                   # exclusive device, same
        display.wake()                           # dance as _wake
        display.keep_awake(False)
        self.state = "active"
        self.absent_since = None
        self.hits = 0
        self.next_poll = now + self.timers["present_recheck_sec"]

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
        boxes, scores = self.detector.detect(frame)
        present = len(boxes) > 0
        score = float(scores.max()) if len(scores) else 0.0
        if self.faces is not None:                     # only known faces count
            present = present and self.faces.known(frame)
        self.framebox.put(frame, boxes, scores)        # the debug view sees
                                                       # the same truth
        log.debug("frame: present=%s score=%.2f", present, score)
        return present, score

    def _mode(self):
        if self.state == "off":
            return self.camera_cfg["mode_off"]
        return self.camera_cfg["mode_on"]

    def _grab(self):
        try:
            if self._mode() == "boot_per_poll":
                cam = self._new_camera()
                try:
                    cam.warm_up()
                    return cam.read()
                finally:
                    cam.release()                # the LED rests; the user
                # can always notice the blink
            cam = self.camera
            if cam is None or not cam.is_open():
                cam = self.camera = self._new_camera()
                cam.warm_up()
            return cam.read()
        except Exception:
            log.exception("grab failed; treating this poll as no frame")
            self._release_camera()               # half-dead device: next
            return None                          # poll opens a fresh one

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

    def _preview(self, now):
        """Debug frames while the lease is live: the camera is held,
        detection runs, and the gate and timers are on holiday; the
        phase machine resumes untouched when the lease runs out."""
        if self.camera is None or not self.camera.is_open():
            self._hold_camera()
            if self.camera is None or not self.camera.is_open():
                return                                 # still booting
        frame = self.camera.read()
        if frame is None:
            return
        boxes, scores = self.detector.detect(frame)
        self.framebox.put(frame, boxes, scores)

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
        if value == 0.0:
            if self.state != "off":
                # darkened externally (power-plan timeout, somebody's
                # Fn key, a resume glitch): adopt the truth, or the
                # machine would keep believing in lit screens and
                # never wake them for the person it can see
                log.info("screens went dark unasked; the camera will "
                         "wake them for whoever shows up")
                self.state = "off"
                self.hits = 0
                self.next_poll = now + self.timers["off_poll_sec"]
                if self.camera_cfg["mode_off"] == "always_on":
                    self._hold_camera()
            return
        if self.state == "unknown":
            self.state = "counting"          # an on-broadcast answers
            self.next_poll = now + self.on_poll()   # the boot question
            return
        if self.state == "off" and value == 1.0:
            self.wake_times = [t for t in self.wake_times
                               if now - t <= self.recovery[
                                   "wake_burst_window_sec"]]
            self.wake_times.append(now)
            self.state = "counting"
            self.hits = 0
            self.next_poll = now + self.on_poll()
            self.absent_since = None             # start a fresh count
            if self.re_off_paused:
                self.grace_until = now + self.recovery[
                    "leave_on_grace_sec"]    # lit while the desk is hot
                log.info("unexpected wake while auto re-off is paused; "
                         "the screens stay lit")
                return
            if (self.recovery["wake_policy"] == "re_off"
                    and len(self.wake_times)
                    >= self.recovery["wake_burst_count"]):
                self._pause_re_off()
                return
            if self.recovery["wake_policy"] == "leave_on":
                self.grace_until = now + self.recovery[
                    "leave_on_grace_sec"]
                log.info("leave_on: screens handed back, grace until then")
            else:
                self.re_off_deadline = now + self.timers["re_off_grace_sec"]
                log.info("unexpected wake; nobody in front of the "
                          "screens; turning them off again after %.0f s if "
                          "still nobody shows up",
                          self.timers["re_off_grace_sec"])
        elif self.state != "off" and value == 0.0:
            log.info("the power plan turned the screens off early")
            self._screens_off(now)

    def _pause_re_off(self):
        """Two unexpected wakes with nobody ever seen: the classic
        symptom is a slipped camera looking at the wall. Keep the
        screens lit and tell the human; a confirmed person, a policy
        change or a manual resume re-arms the auto off."""
        now = time.monotonic()
        self.re_off_paused = True
        self.grace_until = now + self.recovery["leave_on_grace_sec"]
        window = self.recovery["wake_burst_window_sec"]
        log.warning("auto re-off paused: %d unexpected wakes in %s s and "
                    "nobody ever confirmed (camera index %s pointing at "
                    "a wall?)", len(self.wake_times), window,
                    self.camera_cfg["index"])
        burst = len(self.wake_times) >= self.recovery["wake_burst_count"]
        if self.notifier is not None and burst:
            try:
                self.notifier(
                    "auto re-off paused: the screens woke %d times in "
                    "%d s but the camera (index %s) never saw a person. "
                    "If it slipped off the monitor, point it back; auto "
                    "off resumes as soon as it sees somebody (or from "
                    "the tray / window)." % (
                        len(self.wake_times), window,
                        self.camera_cfg["index"]))
            except Exception:
                pass                             # the notice is a courtesy

    def _resume_re_off(self, reason):
        if not self.re_off_paused:
            return
        self.re_off_paused = False
        self.grace_until = 0.0
        self.wake_times = []
        self.re_off_deadline = math.inf
        log.info("auto re-off resumed (%s)", reason)
        if self.notifier is not None:
            try:
                self.notifier("auto re-off resumed (%s)" % reason)
            except Exception:
                pass

    def _drain_tray(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            action, value = event[0], event[1]
            if action == "quit":
                self.quit = True
                if self.ui_events is not None:
                    self.ui_events.put(("quit", None))   # close the window
                                                        # too
            elif action == "stop":
                self.quit = True                        # the window closed
                                                        # the app
            elif action == "preview":
                if value <= 0:
                    self.preview_until = 0.0
                else:
                    self.preview_until = max(self.preview_until,
                                             time.monotonic() + value)
            elif action == "confidence":
                self.inference_cfg["confidence"] = float(value)
                self.detector.conf = float(value)       # hot, no rebuild
            elif action == "pause":
                self.paused = bool(value)
            elif action == "snooze":
                self.snooze_until = time.monotonic() + value * 60
            elif action == "wake_policy":
                self.recovery["wake_policy"] = value
                self.wake_times = []
                self._resume_re_off("the wake policy changed")
                from . import config
                config.write_config(self.cfg)
            elif action == "reoff":
                if value:
                    self._pause_re_off()
                else:
                    self._resume_re_off("manual resume (tray/window)")
            elif action == "power_assistant":
                self.power_cfg["assistant_task"] = bool(value)
                self.blockers_until = 0.0          # the toggle must show
                                                   # its result, not the
                                                   # last week's reading
                from . import config
                config.write_config(self.cfg)
                log.info("assistant flag written to disk: %s", bool(value))
            elif action == "camera":
                self.camera_cfg["index"] = int(value)
                self._release_camera()             # the next poll opens the
                                                   # chosen one
                from . import config
                config.write_config(self.cfg)
                log.info("camera switched to index %s", value)
            elif action == "device":
                self.inference_cfg["device"] = name
                self._rebuild_detector()
            elif action == "device_id":
                self.inference_cfg["device_id"] = int(value)
                self._rebuild_detector()        # same provider, new card

    def _rebuild_detector(self):
        """Re-open the session with whatever device/device_id/confidence
        the config dicts hold now; a CUDA request on a CPU-only
        onnxruntime (or a GPU id that does not exist) falls back to CPU
        inside get_session and the log says which provider loaded."""
        from . import config
        try:
            from . import detector as detector_module
            self.detector = detector_module.PersonDetector(
                model=self.inference_cfg["model"],
                device=self.inference_cfg["device"],
                device_id=self.inference_cfg["device_id"],
                conf=self.inference_cfg["confidence"])
            log.info("detector rebuilt (device=%s id=%s providers=%s)",
                     self.inference_cfg["device"],
                     self.inference_cfg["device_id"],
                     self.detector.session.get_providers())
        except Exception:
            log.exception("detector rebuild failed; keeping the old one")
        config.write_config(self.cfg)
