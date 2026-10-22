"""The two display phases: the counting path while lit, the dark path
while off. Formerly state.py lines 180-294."""

import logging
import math

log = logging.getLogger("state")


class _PhaseMixin:

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
            self._rest_credit()                 # a rest's end must not age
            #                                   the roster into a false
            #                                   dark: the first duty open
            #                                   after any rest abstains
            #                                   through the door's seconds
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
        from .. import power
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
            self._round = None      # stale off-phase round bookkeeping
                                    # does not cross the wake boundary
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
            self._wake(now, None)                # the user is right here
            return
        if now >= self.next_poll:
            # a door camera voting at night wakes the desk (the owner
            # accepted the trade: a person at the door IS the presence
            # the desk wants); nothing here changes that
            present, score = self._poll()
            if present is None:
                # dead camera: no verdict, no round progress, no reset
                # (and no reschedule - the off phase re-polls every
                # tick once the deadline is due, as today)
                pass
            else:
                self._round_tally(present)
                # the dark room is OURS and it blinds the eye - a ghost
                # with a pulse must not re-light a desk: assist-tier
                # frames (below the strict confidence gate) accrue
                # hits while dark but only a strict-tier frame closes
                # the round; returners are strict the moment the panel
                # lights, and physical input covers the rest
                if (present
                        and score >= self.inference_cfg["confidence"]
                        and self.hits >= self.cfg["inference"]["min_hits"]):
                    self._wake(now, score)
