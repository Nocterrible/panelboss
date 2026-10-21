"""Power apply: the hold policy and every screens transition, plus the
layout memory handed to wm around the dark spell. Formerly state.py
lines 161-178 and 296-429."""

import logging
import math

from .. import config
from .. import display

log = logging.getLogger("state")


class _PowerMixin:

    def _post_hold_rows(self):
        """Every transition to a LIT desk re-asks the window to
        re-derive the power-card rows (owner Oct 21: a self-woken
        screen with detection off must show 'while present' grayed,
        never stale-on - and the on-phase re-adopts the hold against
        the fresh verdict). The post rides the existing wake path; a
        miss costs one tick of belt (the reveal repaints anyway)."""
        if getattr(self, "ui_events", None) is not None:
            try:
                self.ui_events.put(("power_rows", None))
            except Exception:
                log.debug("power_rows post lost", exc_info=True)

    def _hold_on(self, key):
        """The third state, read at the hold's own cadence: the row's
        value in its canonical word decides. 'present' holds ONLY
        while the state machine's camera verdict says a person is
        here - absent and no-verdict (dead camera, no frame, consent
        off, detection tab off) both hand the timer back to the plan
        the moment they land: presence unknown == absent, the owner's
        explicit ruling, the fail-into-Windows branch. Today's
        booleans stay valid and mean on/off (hold_state)."""
        word = config.hold_state(self.power_cfg.get(key))
        if word == "present":
            return self._camera_present is True
        return word == "on"

    def _apply_hold(self, now):
        """Windows' execution-state policy, restated every tick:
        hold_display suppresses the plan's display timeout, hold_sleep
        the sleep timeout - either may live alone, and each row answers
        'off', 'on' or 'present' (the third state: held only while the
        camera sees you, _hold_on). The display bit always lets go
        while dark (holding a display is claiming the screens are
        wanted); the system bit survives the dark ONLY if the row's
        answer says so - it is what keeps the watcher alive to see the
        return, and without it the box sleeps and the app re-arms on
        the power-button press (unknown-state boot). Paused or snoozing
        releases everything: the app then behaves exactly like an app
        that is not running. The transition log line is the one honest
        dump the burn-in desk reads (diff-guarded: it speaks only when
        the answer moves)."""
        if self.paused or now < self.snooze_until:
            bits = (False, False)
        elif self.state == "off":
            bits = (False, self._hold_on("hold_sleep"))
        else:
            bits = (self._hold_on("hold_display"),
                    self._hold_on("hold_sleep"))
        if bits != self._hold_bits:
            log.info("hold restated: display=%s sleep=%s (camera_present"
                     "=%r)", bits[0], bits[1], self._camera_present)
            self._hold_bits = bits
        display.set_hold(bits[0], bits[1])

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
        self._post_hold_rows()               # a lit desk re-dresses the
        #                                    card: gray law from live cfg

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
        self._post_hold_rows()               # the wake re-dresses the card

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
        # only if the row's answer says so - it keeps the watcher alive to
        # catch the return ('present' rows read the verdict, _hold_on)
        display.set_hold(False, self._hold_on("hold_sleep"))
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
