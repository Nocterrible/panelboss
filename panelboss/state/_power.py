"""Power apply: the hold policy and every screens transition, plus the
layout memory handed to wm around the dark spell. Formerly state.py
lines 161-178 and 296-429."""

import logging
import math

from .. import display

log = logging.getLogger("state")


class _PowerMixin:

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

    def _force_on(self, now, reason):
        """SC_MONITORPOWER ON when the truth was unknown: on lit screens
        the broadcast is a no-op Windows itself sends on resume; on a
        dark desk a restart hid, it is the wake the state machine could
        not deduce. Free insurance, taken once per boot."""
        log.info("%s - sending the harmless power-on", reason)
        self._release_camera()                   # exclusive device, same
        self._away_lift()                        # dance as _wake: a
        self._away_boot_belt()                   # dim spell never slept,
        #                                    ... but a killed one left
        #                                    the ledger dead and a
        #                                    D6-off panel dark: the
        #                                    belt asks the CONFIG
        #                                    (gate finding 1)
        display.wake()                           # but an OS timeout may
                                                 # have blanked the paint
        self._hdr_back()
        self.state = "active"
        self._rearm("on")                     # the unknown->on edge is a
                                              # wake too: same rule
        self._apply_hold(now)                # present: the plan's timers
                                             # stay suppressed from here on
        self.absent_since = None
        self.hits = 0
        self.next_poll = now + self.timers["present_recheck_sec"]
        self._restore_layout()

    def _wake(self, now, score):
        if score is None:
            # input wake: the mouse spoke, no camera verdict exists -
            # printing 0.00 here read like "the cameras saw nobody" for
            # a wake the user's own hand caused (implication lie, fixed
            # at the owner's desk Oct 12)
            log.info("waking after %.0f s of absence (input: the user "
                     "is right here)",
                     now - self.last_present if self.last_present else -1)
        else:
            log.info("waking after %.0f s of absence (score %.2f)",
                     now - self.last_present if self.last_present else -1,
                     score)
        self._release_camera()                   # the device is exclusive;
                                                 # release before the paint
        self._away_lift()                        # comes off the panels
        display.wake()                           # come back up: a dim
                                                 # desk never slept and
                                                 # the ON is a no-op
                                                 # there (see _force_on),
                                                 # a timed-out one needs it
        self._hdr_back()
        self.state = "counting"
        self._rearm("on")                     # every on-table always eye
                                              # starts its wear clock with
                                              # the wake (owner rule)
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
        from .. import profiles
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
        # per-index stream-through: an eye whose off table says
        # always_on keeps its stream THROUGH the standby transition,
        # never released. Reopening inside the transition is the race
        # that produced forever-dead cameras (measured: the handle
        # says open, frames never flow again; a probe that opens
        # AFTER the panels are dark always streams fine). The duty
        # roster already caps at four streams (get_config dropped the
        # rest, loudly), so the kept set can never over-open.
        keep = [i for i in self._indexes()
                if self._table_mode(i, "off") == "always_on"]
        self._off_phase_hold(keep, "before")
        # dim mode plays dead instead of asleep: the away engine owns
        # the dark and the OFF BROADCAST IS NEVER SENT (the static ban
        # the awaymode suite pins: no power verb below a dim engage).
        # Stock mode falls through to today's exact path, fossil HDR
        # key and all - readable AND honored one release, downgrade
        # honesty both ways.
        if self._away_engage():
            pass
        else:
            if self.power_cfg.get("hdr_off_when_away"):
                from .. import profiles
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
        self._rearm("off")                     # the dark is a re-arm too:
                                               # every off-table always
                                               # eye's wear clock starts
                                               # with the dark (owner rule
                                               # re-arm after every wake)
        self._off_phase_hold(keep, "after")
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
            from .. import wm
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
            from .. import wm
            wm.restore_async(snap,
                             cancel=lambda: self.layout_gen != my_gen)
        except Exception:
            log.exception("layout restore could not start")
