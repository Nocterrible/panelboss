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
        # setdefault, not get: an old config file that predates the
        # section must still CONNECT, or a tray mode switch writes into
        # a dangling dict and the next rebuild reads stale mode
        self.detection_cfg = config.setdefault("detection", {})
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
        self._hdr_snap = []                   # gdis HDR was on at the
                                              # moment the desk went
                                              # dark (power section)
        self.power_cfg = config["power"]
        self.blockers = {"error": "not checked yet", "display": [],
                         "other": []}          # window reads this live
        self.blockers_until = 0.0             # throttle for powercfg
        self.display_held_reported = False
        self.layout = None                    # the desk as it was when we
        self.layout_gen = 0                   # turned it off (see wm)

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
        self._apply_hold(now)                # the policy is asserted every
                                             # tick: a stray clear (wake's
                                             # pulse) dies within a cycle
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

    def _apply_hold(self, now):
        """Windows' execution-state policy, restated every tick:
        hold_display suppresses the plan's display timeout, hold_sleep
        the sleep timeout - either may live alone. The display bit
        always lets go while dark (holding a display is claiming the
        screens are wanted); the system bit survives the dark ONLY if
        the user kept hold_sleep on - it is what keeps the watcher
        alive to see the return, and without it the box sleeps and
        the app re-arms on the power-button press (unknown-state
        boot). Paused or snoozing releases everything: the app then
        behaves exactly like an app that is not running."""
        if self.paused or now < self.snooze_until:
            display.set_hold(False, False)
        elif self.state == "off":
            display.set_hold(False, bool(self.power_cfg.get("hold_sleep")))
        else:
            display.set_hold(bool(self.power_cfg.get("hold_display")),
                             bool(self.power_cfg.get("hold_sleep")))

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
            if present is None:
                # no camera delivered a frame: no verdict. It neither
                # starts the absence clock, nor logs "nobody at the
                # desk", nor forces anything on; the next poll gets
                # its own turn
                self.next_poll = now + self.on_poll()
                return
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
            self.re_off_deadline = math.inf   # a confirmed person voids
            # the re-off budget: the promise was "off again if still
            # nobody shows up" - somebody showed up
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
            if present is None:
                # dead camera: no verdict, no reset of the presence
                # hits, and no reschedule (the off phase re-polls
                # every tick once the deadline is due, as today)
                pass
            elif present:
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
        self._hdr_back()
        self.state = "active"
        self._apply_hold(now)                # present: the plan's timers
                                             # stay suppressed from here on
        self.absent_since = None
        self.hits = 0
        self.next_poll = now + self.timers["present_recheck_sec"]
        self._restore_layout()

    def _wake(self, now, score):
        log.info("waking after %.0f s of absence (score %.2f)",
                 now - self.last_present if self.last_present else -1, score)
        self._release_camera()                   # the device is exclusive;
                                                 # release before the screens
        display.wake()                           # come back up
        self._hdr_back()
        self.state = "counting"
        self._apply_hold(now)                # back: hold the timers again
        self.absent_since = None
        self.re_off_deadline = math.inf
        self.hits = 0
        self.next_poll = now + self.on_poll()
        self._restore_layout()

    def _hdr_back(self):
        """HDR the user had at the leaving moment comes home with
        them; nothing else touches it. Quiet unless there was a
        handback."""
        if not self._hdr_snap:
            return
        from . import profiles
        profiles.hdr_away_restore(self._hdr_snap)
        log.info("hdr: handed back %d display(s)", len(self._hdr_snap))
        self._hdr_snap = []

    def _screens_off(self, now):
        if self.guards["fullscreen"] and display.foreground_is_fullscreen():
            log.debug("a fullscreen app owns the display; "
                      "the message never reaches the swap chain")
            self.next_poll = now + self.on_poll()
            return
        self._remember_layout()                # panels lit = the truth
                                               # still intact (see wm)
        # the display hold lets go BEFORE the broadcast (a held display is
        # a claim the screens are wanted); the sleep hold survives the dark
        # only if the user kept it - it keeps the watcher alive to catch
        # the return
        display.set_hold(False, bool(self.power_cfg.get("hold_sleep")))
        # mode always_on: the stream rides THROUGH the standby
        # transition, never released. Reopening inside the transition
        # is the race that produced forever-dead cameras (measured:
        # the handle says open, frames never flow again; a probe that
        # opens AFTER the panels are dark always streams fine). If the
        # device died mid-count we retry once right now, while the
        # screens are still lit and an honest open is cheap.
        if self.camera_cfg["mode_off"] == "always_on":
            self._hold_camera()
        else:
            self._release_camera()
        if self.power_cfg.get("hdr_off_when_away"):
            from . import profiles
            self._hdr_snap = profiles.hdr_away_off()
            if self._hdr_snap:
                log.info("hdr: %d display(s) off for the absence, "
                         "the return will hand them back",
                         len(self._hdr_snap))
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

    # ------------------------------------------------------- layout memory --
    def _remember_layout(self):
        """Snapshot every window's rect and the monitor fingerprint
        while the panels are still lit. Some monitors fully disconnect
        from Windows on standby; on return Windows re-lays the whole
        desk. Fail-soft: a snapshot that cannot be taken just means the
        dark spell carries no memory and the wake does nothing."""
        self.layout = None
        if not self.power_cfg.get("restore_windows"):
            return
        try:
            from . import wm
            snap = wm.snapshot()
            if snap["wins"]:
                self.layout = snap
                self.layout_gen += 1
        except Exception:
            log.exception("layout snapshot failed; the desk is on its own")

    def _restore_layout(self):
        """Called on every transition back to a lit desk, whoever lit
        it (our own wake, the camera, a mouse jiggle the watcher
        reported, the power button after a sleep). Hands the saved
        snapshot to a helper thread that waits for the monitor
        topology to settle and then moves everything back; superseded
        by a newer snapshot the instant one exists."""
        snap, self.layout = self.layout, None
        if snap is None:
            return
        my_gen = self.layout_gen
        try:
            from . import wm
            wm.restore_async(snap,
                             cancel=lambda: self.layout_gen != my_gen)
        except Exception:
            log.exception("layout restore could not start")

    # ------------------------------------------------------------ cameras ---
    def on_poll(self):
        return self.timers["on_poll_sec"]

    def _poll(self):
        frame, opened = self._grab()
        if frame is None:
            if not opened:
                # the open itself failed: no camera looked, so no
                # verdict - an abstain never confirms absence and
                # never resets the presence hits
                return None, 0.0
            return False, 0.0                    # device busy or died
        # two-tier, letterboxed: a clear hit is present, a borderline one
        # counts only if it moved; motion mode has no detect_lively, so
        # it takes the plain detect path
        lively = getattr(self.detector, "detect_lively", None)
        if lively is not None:
            boxes, scores, present = lively(frame)
        else:
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
        """(frame, opened): opened is True when a camera handle was
        actually constructed and then failed to deliver a frame (a
        stall: today's fail-closed vote), False when the open itself
        failed (a real driver error, or a rotation in which no camera
        could open): that is an abstain, and an abstain is not a
        verdict."""
        try:
            if self._mode() == "boot_per_poll":
                rot = self._rotor()
                if rot is not None:
                    # the rotation keeps one persistent adapter across
                    # polls: the cursor must outlive the per-poll open
                    # and release, or every poll starts on camera one
                    frame = rot.read(mode="boot_per_poll")
                    return frame, rot.last_opened
                cam = self._new_camera()
                try:
                    cam.warm_up()
                    return cam.read(), True
                finally:
                    cam.release()                # the LED rests; the user
                # can always notice the blink
            rot = self._rotor()
            if rot is not None:
                # a rotor is never recreated here: every index keeps
                # its own slot (a dead one retried on its turn, a
                # stalled one released and reopened) and the cursor
                # must outlive the dead ones, so a dead camera can
                # never veto a live one
                if not rot.is_open():
                    rot.warm_up()
                frame = rot.read(mode="always_on")
                return frame, rot.last_opened
            cam = self.camera
            if cam is None or not cam.is_open():
                cam = self.camera = self._new_camera()
                cam.warm_up()
            frame = cam.read()
            if frame is None and self.camera is not None:
                # a handle that stopped flowing IS a dead handle,
                # whatever is_open() swears (measured: the standby
                # transition leaves open-yet-frozen cameras behind;
                # reading the corpse every poll forever is exactly
                # the "no LED, no wake, mouse required" symptom)
                self._release_camera()
            return frame, True
        except Exception:
            log.exception("grab failed; treating this poll as no frame")
            self._release_camera()               # half-dead device: next
            # poll opens a fresh one. the vote shape is the shipped
            # one: with no rotor behind this failure nobody else is
            # watching, so a single-camera desk keeps its fail-closed
            # absent - only a rotation may abstain (a dead camera must
            # never veto a live one; a lone dead camera has no live
            # one to veto, and abstaining would keep the screens lit
            # forever with nobody ever seen again)
            return None, not self._multi_cam()

    def _multi_cam(self):
        """True when the duty roster holds more than one camera. Pure
        config math plus one honest exception: a rotor that open-time
        resolution handed us owns this desk until the config itself
        says otherwise (the hot-plug case the load probe missed).
        Safe to call from an except arm. name matches are merged INTO
        the index list at config load (config.get_config), so the
        length check is the whole truth, names included."""
        from . import config
        if getattr(self.camera, "rotating", False):
            return True
        return len(config.normalize_index(self.camera_cfg.get("index", 0))) > 1

    def _roster_words(self):
        """"camera index 2" or "cameras [0, 2]" - the burst notice has
        to read right whichever roster is on duty."""
        r = self.camera_cfg["index"]
        if isinstance(r, (list, tuple)):
            if len(r) > 1:
                return "cameras %s" % (list(r),)
            r = r[0] if r else None
        return "camera index %s" % r

    def _rotor(self):
        """The shared RotatingCamera while the config holds more than
        one camera; None for a single one (the single path keeps its
        exact old open and close shape - a single camera never goes
        through rotation code at all). The adapter is created on
        demand, so a pause or snooze that releases it simply gets a
        fresh one next poll."""
        from . import config
        indexes = config.normalize_index(self.camera_cfg.get("index", 0))
        if len(indexes) <= 1:
            if getattr(self.camera, "rotating", False):
                return self.camera    # the load probe missed it, the
                                      # open-time one found it: the rotor
                                      # that exists keeps voting (single
                                      # logic would drop it every poll)
            return None
        if self.camera is None or not getattr(self.camera, "rotating", False):
            self.camera = self._new_camera()
        return self.camera

    def _new_camera(self):
        from . import camera
        return camera.open_camera(self.camera_cfg)   # index -2 = hello IR

    def _hold_camera(self):
        if self.camera is None or not self.camera.is_open():
            self._release_camera()               # a present-but-dead
            # device still gets its honest release + detector reset;
            # letting the destructor eat it skips both
            self.camera = self._new_camera()
            self.camera.warm_up()

    def _release_camera(self):
        if self.camera is not None:
            self.camera.release()
            self.camera = None
            reset = getattr(self.detector, "reset", None)
            if reset is not None:
                reset()      # MotionDetector: the next open may be a
                             # DIFFERENT camera, and diffing the new
                             # scene against the old one is a phantom
                             # motion hit worth hold_sec of presence

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
                # Fn key, a resume glitch): the truth is off NOW, and
                # the away chores (layout memory, hdr, camera policy)
                # run exactly as they would for our own off - panels
                # were still lit when the broadcast arrived, so the
                # layout snapshot is still the truth. turn_off on dark
                # panels is a harmless no-op.
                log.info("screens went dark unasked; adopting and "
                         "running the away chores")
                self.state = "off"
                self.hits = 0
                self.next_poll = now + self.timers["off_poll_sec"]
                self._screens_off(now)
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
            self._restore_layout()               # a jiggle lit the desk:
                                                 # its windows may be adrift
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
                    "nobody ever confirmed (%s pointing at "
                    "a wall?)", len(self.wake_times), window,
                    self._roster_words())
        burst = len(self.wake_times) >= self.recovery["wake_burst_count"]
        if self.notifier is not None and burst:
            try:
                self.notifier(
                    "auto re-off paused: the screens woke %d times in "
                    "%d s but the %s never saw a person. "
                    "If it slipped off the monitor, point it back; auto "
                    "off resumes as soon as it sees somebody (or from "
                    "the tray / window)." % (
                        len(self.wake_times), window,
                        self._roster_words()))
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
                self.inference_cfg["device"] = value
                self._rebuild_detector()        # cpu<->gpu swap
            elif action == "device_id":
                self.inference_cfg["device_id"] = int(value)
                self._rebuild_detector()        # same provider, new card
            elif action == "detection_mode":
                self.detection_cfg["mode"] = value
                self._rebuild_detector()        # motion never loads a model;
                                                # person opens the session now
                log.info("detection mode switched to %s", value)

    def _rebuild_detector(self):
        """Re-open whatever the CURRENT mode wants: motion rebuilds the
        differencer (no model, no session, no provider talk), person
        re-opens the onnx session with whatever device/device_id/
        confidence the config dicts hold now; a CUDA request on a
        CPU-only onnxruntime (or a GPU id that does not exist) falls
        back inside get_session and the log says which provider
        loaded."""
        from . import config
        from . import detector as detector_module
        try:
            self.detector = detector_module.build(self.cfg)
            if hasattr(self.detector, "session"):
                log.info("detector rebuilt (device=%s id=%s providers=%s)",
                         self.inference_cfg["device"],
                         self.inference_cfg["device_id"],
                         self.detector.session.get_providers())
            else:
                log.info("detector rebuilt (motion, ratio=%s hold=%ss)",
                         self.detection_cfg.get("ratio"),
                         self.detection_cfg.get("hold_sec"))
        except Exception:
            log.exception("detector rebuild failed; keeping the old one")
        config.write_config(self.cfg)
