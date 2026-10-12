"""Every event source outside the camera: the display watcher's queue,
the wake-burst recovery policy, and the tray/window commands. Formerly
state.py lines 828-1034."""

import logging
import math
import queue
import time

from .. import display

log = logging.getLogger("state")


class _EventsMixin:

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
            if not self.previewing:          # the boot edge into the on
                                             # table: same rule - but a
                                             # display broadcast during a
                                             # live preview lease must not
                                             # revert the tight cadence
                                             # (the lease owns next_poll
                                             # and _rearm until it expires)
                self._rearm("on")
            return
        if self.state == "off" and value == 1.0:
            if not self.previewing:          # an unexpected wake re-arms
                                             # the on table's wear clocks
                                             # like any wake - same lease
                                             # guard as the arm above
                self._rearm("on")
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
                    was_live = time.monotonic() < self.preview_until
                    self.preview_until = max(self.preview_until,
                                             time.monotonic() + value)
                    if (value > 0 and not was_live):
                        # a FRESH lease (not a heartbeat stretching a live
                        # one): poll now, do not wait out the old table's
                        # next_poll, or the first preview frame is late
                        self.next_poll = time.monotonic()
                        if self.preview_cool:
                            # ATTACH: the lease died inside
                            # PREVIEW_COOLOFF_SEC and the wall (plus any
                            # open still in flight) is still warm - the
                            # first tick composes instead of paying the
                            # driver's 20+ s again. This is the exact
                            # toggle pattern the cooloff exists to kill
                            # the spiral of.
                            self.preview_cool = 0.0
                            for seam in (self.camera, self._single_opener):
                                rearm = getattr(seam, "rearm", None)
                                if rearm is not None:
                                    rearm()    # gate finding 2: an
                                    #                   attached lease must not
                                    #                   inherit this lease's
                                    #                   grace tombstones
                            log.info("preview lease re-attached a warm "
                                     "wall - no reopen")
                        else:
                            log.info("preview lease began; polling now")
                    # NOTE: a heartbeat arriving AFTER the cool window
                    # (camera already released) does NOT re-pin from
                    # here - the lease-branch pin (_pin_lease) covers
                    # the whole window that matters (begin -> ticks ->
                    # opens land), and re-pinning over RELEASED
                    # (gen-stale) workers would revive a lease whose
                    # opens are doomed to self-release
            elif action == "confidence":
                self.inference_cfg["confidence"] = float(value)
                if self.detector is not None:
                    self.detector.conf = float(value)       # hot, no
                                                            # rebuild
                # a slider move before the detector lands is not lost:
                # the warm worker reads the config dict on its build
            elif action == "pause":
                self.paused = bool(value)
            elif action == "snooze":
                self.snooze_until = time.monotonic() + value * 60
            elif action == "wake_policy":
                self.recovery["wake_policy"] = value
                self.wake_times = []
                self._resume_re_off("the wake policy changed")
                from .. import config
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
                from .. import config
                config.write_config(self.cfg)
                log.info("assistant flag written to disk: %s", bool(value))
            elif action == "camera":
                # value is either a bare int (one camera, or the IR
                # sentinels - the historic contract) or the full
                # rotation LIST the window assembles when a camera is
                # ADDED beside the current ones
                self.camera_cfg["index"] = (
                    list(value) if isinstance(value, (list, tuple))
                    else int(value))
                self._release_camera()             # the next poll opens the
                                                   # chosen one
                from .. import config
                config.write_config(self.cfg)
                log.info("camera roster now %s", self.camera_cfg["index"])
            elif action == "camera_identity":
                # the wizard's hand-off: {"instance": str, "label": str
                # (empty clears), "hide": bool}. Keyed on the PnP
                # InstanceId because indexes drift on replugs; state
                # owns the toml write, the UI never edits it behind
                # the loop's back
                inst = str(value.get("instance") or "")
                if inst:
                    if value.get("label") is not None:
                        labels = self.camera_cfg.setdefault("labels", {})
                        text = str(value["label"]).strip()
                        if text:
                            labels[inst] = text
                        else:
                            labels.pop(inst, None)
                    if value.get("hide"):
                        hidden = self.camera_cfg.setdefault("hidden", [])
                        if inst not in hidden:
                            hidden.append(inst)
                    from .. import config
                    config.write_config(self.cfg)
                    log.info("camera identity stored for %s", inst)
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
        from .. import config
        from .. import detector as detector_module
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
