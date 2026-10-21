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
                item = watcher.queue.get_nowait()
            except queue.Empty:
                break
            try:
                event, value, ts = item
            except (TypeError, ValueError):
                log.warning("display queue item %r is not an "
                            "event triple; dropped", item)
                continue
            if event == "monitor":               # the FIRST link is the
                try:                             # old path, untouched:
                    self._notice_screens(now, value)  # wake-burst law
                except Exception:
                    log.exception("display notice failed on %r", item)
                continue
            if event == "displaychange":
                # amendment 8: someone moved the color state or the
                # topology (this app's own hdr_set included - the
                # toggle re-enumerates the paths). No screens-off
                # reading (value 0.0 is a shape holder, not a dark
                # claim: a color flip says nothing about the lamps);
                # one ask upward, and the panes re-read the driver.
                # The away wave rides the SAME event: the brightness
                # handles were already invalidated watcher-side (the
                # ear), and the next engage reads the desk live.
                if getattr(self, "ui_events", None) is not None:
                    try:
                        self.ui_events.put(("hdr_sync", None))
                    except Exception:
                        log.debug("hdr_sync post failed", exc_info=True)
                continue
            if event == "away_lift":
                # a low-level hook (or an overlay click) says real
                # input arrived while the desk plays dead: that IS
                # the wake, same door the camera knocks on
                if self.state == "off":
                    log.info("away lifted (%s)", value)
                    self._wake(now, 0.0)
                continue
            if event == "session_unlock":
                # the lock-aware lift (lock-on-away): behind the lock
                # the raw ears are deaf by DESKTOP law, so the session
                # itself posts the wake. A stock (unpainted) dark needs
                # nothing here - unlocking IS input, and the idle gate
                # hands that one back to the old path untouched.
                if getattr(self, "away_status", None):
                    log.info("away: lifted on session unlock")
                    self._wake(now, 0.0)
                continue
            # unknown events: logged once per name, never silently
            # dropped - the silent-ignorance class this fleet died on
            # (HEAD's pass-through-to-notice is preserved one link up:
            # only "monitor" is named for the screens reading)
            if getattr(self, "_drain_seen", None) is None:
                self._drain_seen = set()
            if event not in self._drain_seen:
                self._drain_seen.add(event)
                log.info("display queue: event %r has no arm (ignored)",
                         event)

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
            self._post_hold_rows()           # the desk is lit: re-dress
            return                           # the power rows
        if self.state == "off" and value == 1.0:
            self._post_hold_rows()           # a self-woken screen must
            #                                not keep stale-on segments:
            #                                the gray law re-reads live
            #                                cfg on this existing wake
            #                                path
            self._away_lift()                # a dim spell ends here too:
                                             # the desk lit WITHOUT our
                                             # wake seam (power button),
                                             # the paint must not stay
                                             # over somebody's Sunday
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
            try:
                action, value = event[0], event[1]
            except (TypeError, ValueError, IndexError):
                log.warning("tray event %r is not an action/value pair; "
                            "dropped", event)
                continue
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
                want = bool(value)
                if want:
                    # the state-side belt (wave B): a True that rides
                    # to the file needs the task store's backing -
                    # the flag follows reality, never the other way
                    # round. This handler cannot tell an adoption
                    # post from a click post, so it checks the task
                    # instead; a True with no task behind it is the
                    # rumor class the screenshot caught.
                    from .. import power
                    want = power.task_installed()
                self.power_cfg["assistant_task"] = want
                self.blockers_until = 0.0          # the toggle must show
                                                   # its result, not the
                                                   # last week's reading
                from .. import config
                config.write_config(self.cfg)
                log.info("assistant flag written to disk: %s", want)
            elif action == "camera":
                # value is either a bare int (one camera, or the IR
                # sentinels - the historic contract) or the full
                # rotation LIST the window assembles when a camera is
                # ADDED beside the current ones
                self.camera_cfg["index"] = (
                    list(value) if isinstance(value, (list, tuple))
                    else int(value))
                # the word lands BEFORE the hand (Oct 19): the AV that
                # owned pid 23004 died in the release and took the toml
                # with it; camera_diag's order is the shape
                from .. import config
                config.write_config(self.cfg)
                log.info("camera roster now %s", self.camera_cfg["index"])
                self._release_camera()             # the next poll opens the
                                                   # chosen one
            elif action == "camera_enabled":
                # the consent gate (redesign law 1): cameras open
                # only after the owner says so. Loop-owned write (the
                # ui never touches the toml); flipping OFF drains
                # duty RIGHT HERE - release what is held, the roster
                # and the per-index tables survive the flush (the
                # _cams open gate is the standing enforcement; this
                # is the prompt half, so a mid-duty disable does not
                # wait for the next poll to let go of the LED).
                # The cameras resync (None = re-apply the cached
                # report) refreshes the panes against the moved key,
                # the same idiom the identity writes use.
                self.camera_cfg["enabled"] = bool(value)
                # write BEFORE the release (Oct 19, the vanished "No"):
                # the camera_enabled drain used to release the device
                # first, and a death in the release ate the owner's word
                # - the consent rides to disk before any hand moves
                from .. import config
                config.write_config(self.cfg)
                log.info("camera detection %s",
                         "enabled" if self.camera_cfg["enabled"]
                         else "disabled (duty drained)")
                if not self.camera_cfg["enabled"]:
                    self._release_camera()
                    # the door shut IS no verdict: recorded right here,
                    # so a 'present' row lets go on the next tick (0.2 s)
                    # and never waits out the old verdict to the next
                    # poll - the owner's release-the-moment law. The
                    # credit is FORFEITED (shuffled=False, the V catch):
                    # a two-leg desk whose eyes all spoke seconds ago
                    # must still let go the instant the owner shuts the
                    # door - the walk's ledger cannot outweigh a shut
                    # door, or the law's own words ('detection tab off'
                    # = no verdict) would age out behind a fresh roster.
                    self._note_verdict(None, shuffled=False)
                if self.ui_events is not None:
                    # the resync the comment promised (gate finding
                    # 3): the panes re-derive against the moved key,
                    # the identity-write idiom verbatim
                    self.ui_events.put(("cameras", None))
            elif action == "camera_diag":
                # the scan's probe verdict, keyed by the index set it
                # measured: a re-scan that finds the same set refreshes
                # at/noimg; a changed set REPLACES indices too (the
                # trigger condition for the next sweep is exactly this
                # set vs the scan's). Value is the whole record; store
                # as-is after coercing the two lists to ints.
                rec = dict(value or {})
                try:
                    rec["indices"] = [int(i) for i in rec.get("indices") or []]
                    rec["noimg"] = [int(i) for i in rec.get("noimg") or []]
                except (TypeError, ValueError):
                    rec = {}                        # junk record = no record
                rec["at"] = time.time()
                self.camera_cfg["diag"] = rec
                from .. import config
                config.write_config(self.cfg)
                log.info("camera diagnostic: %d of %d indexes serve no image",
                         len(rec.get("noimg") or []), len(rec.get("indices") or []))
                continue
            elif action == "camera_identity":
                # the wizard's hand-off: {"instance": str, "label": str
                # (empty clears), "hide": bool}. Keyed on the PnP
                # InstanceId because indexes drift on replugs; state
                # owns the toml write, the UI never edits it behind
                # the loop's back
                inst = str(value.get("instance") or "")
                if not inst and "index" in value:
                    # the orphan-proof label key (owner crash report,
                    # re-landed): an identity with no PnP join is
                    # STILL an identity - the "idx:N" key the
                    # synthetic rows are named by, and the ghost
                    # migration below carries it to the real instance
                    # when a bind later resolves. Without the
                    # fallback, renaming an unjoinable camera arrived
                    # and was silently dropped - the silent-ignorance
                    # class the load boundary already refuses.
                    try:
                        inst = "idx:%d" % int(value["index"])
                    except (TypeError, ValueError):
                        pass               # junk index: no identity,
                                           # the drop stays honest
                if inst:
                    if value.get("label") is not None:
                        labels = self.camera_cfg.setdefault("labels", {})
                        text = str(value["label"]).strip()
                        if text:
                            labels[inst] = text
                        else:
                            labels.pop(inst, None)
                    if value.get("show"):
                        # the one-at-a-time way back (owner amendment
                        # 2): the door per device - the blanket
                        # unhide-all stays as-is, a wipe is not a
                        # decision. Un-hide AND mark shown: future
                        # diagnostic sweeps must not re-hide what a
                        # human raised (all_rows's touched set reads
                        # this list - the stickiness is on the
                        # identity key, permanent, human-written)
                        hidden = self.camera_cfg.setdefault("hidden", [])
                        if inst in hidden:
                            hidden.remove(inst)
                        shown = self.camera_cfg.setdefault("shown", [])
                        if inst not in shown:
                            shown.append(inst)
                    if value.get("hide"):
                        hidden = self.camera_cfg.setdefault("hidden", [])
                        if inst not in hidden:
                            hidden.append(inst)
                    if value.get("unhide"):
                        # the door, not the cell (gate finding 5):
                        # removal is idempotent, like the hide above
                        hidden = self.camera_cfg.setdefault("hidden", [])
                        if inst in hidden:
                            hidden.remove(inst)
                    if "bind" in value:
                        # the wizard's twin answer: "this instance IS
                        # the feed at index N". Stored on the instance
                        # (survives label edits, composes with hide);
                        # a non-numeric bind clears the claim, the
                        # same shape as an empty label
                        bindings = self.camera_cfg.setdefault(
                            "bindings", {})
                        try:
                            bidx = int(value["bind"])
                        except (TypeError, ValueError):
                            bidx = None
                            bindings.pop(inst, None)
                        if bidx is not None:
                            bindings[inst] = bidx
                            # the name follows the camera: a label the
                            # owner wrote while the row was the
                            # anonymous "idx:N" migrates to the now-
                            # durable identity - otherwise naming the
                            # placeholder and THEN binding it (the
                            # owner's exact flow) orphaned the name
                            labels = self.camera_cfg.setdefault(
                                "labels", {})
                            ghost = "idx:%d" % bidx
                            if (ghost in labels
                                    and str(labels[ghost]).strip()
                                    and not str(labels.get(inst, "")
                                                or "").strip()):
                                labels[inst] = labels.pop(ghost)
                    from .. import config
                    config.write_config(self.cfg)
                    log.info("camera identity stored for %s", inst)
                    if self.ui_events is not None:
                        # the round-trip resync (audit LOW: badges
                        # stale after a wizard save - the picker and
                        # the (hidden) marks ride hidden/labels, and
                        # nothing but a scan re-fired the editor after
                        # the write). NONE value = no fresh scan rode
                        # the event: _apply_cameras re-applies its OWN
                        # cached report against the cfg the wizard
                        # just moved, the same re-apply idiom the
                        # row/remove paths use.
                        self.ui_events.put(("cameras", None))
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
            else:
                log.warning("unknown ui event %r (dropped)", event)

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
