"""Per-camera vote policy: the tables, the wear clock, the degraded
cadence gate. The rotor reads these at vote time, so a policy change
needs no rotor rebuild. Formerly state.py lines 431-508."""

import logging
import time

from .. import camera

log = logging.getLogger("state")


class _PolicyMixin:

    # ------------------------------------------------------------ cameras ---
    def on_poll(self):
        return self.timers["on_poll_sec"]

    def _indexes(self):
        """The duty roster: the index list exactly as the config holds
        it (normalized; get_config already applied the four-stream cap
        and dropped the rest, loudly)."""
        from .. import config
        return config.normalize_index(self.camera_cfg.get("index", 0))

    def _table_mode(self, index, table):
        """The RAW per-index mode: the table wins, the table's global
        default fills the gap; no tables at all is the old behavior
        (the global decides for everybody)."""
        fallback = (self.camera_cfg["mode_off"] if table == "off"
                    else self.camera_cfg["mode_on"])
        return self.camera_cfg.get(table, {}).get(index, fallback)

    def _rearm(self, table):
        """The wear clock restarts on every flip INTO a table - wake
        AND dark both re-arm (owner rule: re-arm after every wake, and
        the dark transition is where an off-table stream starts). An
        always_on eye resuming its continuous stream is as fresh as
        one that has streamed since boot."""
        now = time.monotonic()
        for index in self._indexes():
            if self._table_mode(index, table) == "always_on":
                self.armed[index] = now

    def effective_mode(self, index):
        """This eye's vote mode right now, display state included:
        the per-index table wins, the table's global fills the gap,
        and an always_on eye whose arming aged past the wear guard
        degrades to boot_per_poll (open, vote, release) until the next
        re-arm."""
        mode = self._table_mode(index,
                                "off" if self.state == "off" else "on")
        if mode == "always_on":
            armed = self.armed.get(index)
            if armed is None:
                # first sight of an always eye (the boot arming missed
                # it, or the table changed under us): a fresh run
                self.armed[index] = time.monotonic()
            elif time.monotonic() - armed > \
                    self.camera_cfg["always_timeout_sec"]:
                return "boot_per_poll"        # degraded: the LED gets
                                              # its rest between votes
        return mode

    def _policy(self, index):
        """The live per-index view handed to the rotor (and read by the
        tray). The effective mode, with one twist: a DEGRADED eye
        (always_on whose wear clock ran out) that is not yet due under
        the fallback cadence reports as OFF - the rotation walk skips
        it exactly like a switched-off one, and a tick in which no
        eye is due abstains instead of opening devices. Native
        boot_per_poll eyes are never cadence-gated: they vote on the
        normal cadence, as today.

        THE CADENCE IS SPLIT BY TABLE (owner law, Oct 13 night): the
        dark table's degraded eye is read like you mean it - one
        second, floor one - because holding the stream is the whole
        point of paying for it, and a 1 s read is strictly cheaper
        than the boot-per-poll dance it replaces. The LIT table keeps
        the old 10 s / floor 5 under its own name: an eye degraded in
        front of a witness rests in minutes, not seconds (the law
        speaks the dark hour; one constant used to gate both tables,
        which is why the dark number could never honestly be 1)."""
        table = "off" if self.state == "off" else "on"
        if self._table_mode(index, table) != "always_on":
            return self.effective_mode(index)
        if self.effective_mode(index) == "always_on":
            return "always_on"                # fresh: votes when the
                                              # walk gets to it
        cadence_key = ("always_fallback_poll_sec" if table == "off"
                       else "always_fallback_poll_on_sec")
        due = index not in self.last_vote or \
            time.monotonic() - self.last_vote[index] >= \
            self.camera_cfg[cadence_key]
        return "boot_per_poll" if due else "off"

    def _note_vote(self, index, frame):
        """The wear clock's evidence. The fallback cadence counts
        from a vote that actually carried a frame: an abstain (a dead
        or stalled camera) must never refresh the clock, or one bad
        frame could buy an entire hour of wear time for an eye that
        is genuinely due."""
        if index is not None and frame is not None:
            self.last_vote[index] = time.monotonic()
            # the wear clock counts a BLACK delivered frame as
            # delivered on purpose: it IS a frame (the sensor answered);
            # the fallback-cadence question is unrelated to verdict
            # casting, and the abstain itself lives in the vote path
            # (_cams._poll). The lines below only confess the
            # blind/seeing transitions (INFO once per edge: per-poll
            # cadence would spam).
            blind = int(frame.max()) < camera.BLACK_CEIL
            was = self._blind.get(index, False)
            if blind and not was:
                log.info("eye %d serving black; abstaining until it "
                         "sees something (Broadcast has it, or the room "
                         "is dark)", index)
            elif was and not blind:
                log.info("eye %d frames came back", index)
            self._blind[index] = blind
            # a BLACK frame abstains in _poll, so its slot must not leak
            # a round credit to an eye that never gave a verdict
            self._vote_index = index if not blind else None

    def _round_tally(self, present):
        """Presence is an OR: any eye that sees somebody counts and ends
        the round. Absence is an AND: the streak resets only when EVERY
        eye on duty this table state has had its turn since the last
        positive and none of them saw anybody (owner door-cam doctrine,
        Oct 12 - an empty door must never veto a warm desk). Blind eyes
        abstained before reaching here - the want-set now excludes them,
        matching the claim; policy-off eyes never entered
        the round at all; the round can only close on verdicts."""
        if getattr(self, "_vote_index", None) is None:
            if not present:              # fail-closed ABSENT (stall/died
                self.hits = 0            # verdict, no recorded eye):
                self._round = None       # the shipped AND behavior
            return
        idx = self._vote_index
        self._vote_index = None
        if present:
            self.hits += 1
            self._round = None           # a positive ENDS the round
            return
        table = "off" if self.state == "off" else "on"
        # blind eyes abstained BEFORE this tally - counting them makes
        # the round unclosable: hits freezes at 1 forever, degrading
        # min_hits to "one more ever"
        want = {i for i in self._indexes()
                if self._table_mode(i, table) != "off"
                and not self._blind.get(i, False)}
        if self._round is None:
            self._round = {idx}
        else:
            self._round.add(idx)
        if want and want <= self._round:
            self.hits = 0                # the full rotation came back
            self._round = None           # empty: THAT is absence
