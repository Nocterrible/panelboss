"""The away engine: dim-mode substitution for the display power verb.

SIZE LAW header: this part owns the fake-off ledger and nothing else -
and at ~620 lines (post the park wave, owner Oct 17; the
stage-two timer rode it three days and fell to the OS screen timer,
Oct 19) the whole is still one
law: the ledgers, the door
calls and the status words interlock line-for-line,
and splitting the prose from its call sites (or the lift from the
engage) would sell a seam for nothing. The off wave's and the lock
wave's growth are this file's due; the card paint lives in
ui/window/_away.py; the widening's ctypes core moved OUT to
wm/_sdc.py exactly where a seam existed to be sold.
The state machine keeps its shape - _power.py calls _away_engage()
where it used to call the broadcast, _away_lift() where it wakes,
_events.py arms the queue lifts (away_lift from the input ears and
the overlay click, and the session_unlock knock the locked desk
still makes, and the unexpected-wake lift); the
policy, phase and camera machines are untouched, because the whole
point of the feature is that the presence engine keeps working
exactly as it does while dark.

The laws set here, from the 2026-10-14 probes (wm/_bright.py carries
the full education and the two honest halves): a REFUSED row - the
send failed with the retry budget spent - DEGRADES to blackout with
the confession recorded in away_status, never silent; an UNVERIFIED
row - write accepted, readback a stranger - keeps its sub-mode and
says "(unverified)" on its status word (the PROBE LAW's correction:
the old blanket readback-law lied about the panels that WORK).
HDR rides the
packet's per-row rule (a dim row's own hdr_set(False), remembered as
{"gdi","model"} rows exactly like the proven pair's snapshot) and
the handback rides profiles.hdr_away_restore VERBATIM - the
model-aware half that survives the standby slot-shuffle. And a
preview of a row the real away spell took over mid-way ADOPTS the
spell instead of reverting: un-dimming a real away is the bug this
seam exists to kill (the architect's owner-call, 2026-10-14). The
adopt law lives engine-side so the suite can fake it without a Tk.
The OFF sub-mode (2026-10-14 growth wave, owner sheet + correction):
a row may instead ask for the panel's OWN power code through the
brightness door - no overlay (the panel IS the overlay), the
refusal falls back to blackout confessed, an unanswered readback
earns the trust word "(unverified)", the lift's power hand-back is
UNCONDITIONAL on every wake reason (see the asymmetry law at the
engage side), and covered rows bring the corner jail. The PROBE LAW
owns the capability story: off is selectable on every reached
panel, and the verdict lives in these status words, timestamped -
never in a pre-sentence about firmware. The off flavor WIDENED
(final wave, 2026-10-14): "off" is the D6 power code and "offdisc"
is the adapter retraction (wm/_sdc.py) - the two flavors earn
different epistemic words, "off (unverified)" is trust and "off
(disconnected)" is PROOF (the CCD re-query witnessed it). LOCK-ON-
AWAY (owner-ruled, 2026-10-14): the same engage may end by locking
the workstation - see _away_lock for the law and the lock-aware
wake it commits to.
"""

import logging
import time

log = logging.getLogger("state")


class _AwayMixin:

    # ------------------------------------------------------------- engage --
    def _away_engage(self):
        """Called where the off broadcast used to stand: dim mode
        paints the dark INSTEAD of powering it - the blackout rows
        wear the overlay, the dim rows lose their HDR and drop to
        dim_level, and the OFF rows ask the panel's own power code
        through the brightness door (no overlay - the panel IS the
        overlay; a refusal degrades that row to blackout, confessed).
        Covered rows also bring the pointer law (Oct 17, two halves):
        a spell that PAINTS parks the cursor at park_point - bottom-
        middle of the lowest monitor, one SetCursorPos, no restore
        (a white arrow at a black panel's corner is the most visible
        pixel on the dark); a SLEEP-only spell keeps the corner jail
        (display.jail_cursor: the cursor parks at a covered rect's
        far corner, ONCE per engage - SetCursorPos generates no raw
        input, so neither verb can wake what it covers). Returns {}
        when
        the mode is the stock off - the caller takes the broadcast
        path untouched, and the legacy global hdr_off_when_away block
        stays readable and honored there (downgrade honesty, one
        release)."""
        away = self.cfg.get("away") or {}
        from .. import display, wm
        # THE EXEMPTION (2026-10-15, the owner's black remote screen):
        # session_is_remote() read ONCE per engage. True exempts the
        # WHOLE desk - the canvas is not a panel and the DDC door
        # ACKs and LIES for it (measured from inside the session:
        # reachable=True, nphys=1; the D6-attempt-once proposal is
        # REJECTED by that measurement: an attempt that looks like
        # success and leaves a dead canvas is the exact bug class).
        # None (a refused query) is UNKNOWN and unknown does not
        # exempt: the console desk is the common case and a silent
        # door must not strand a physical panel lit. The row's own
        # bus-root flag is the per-row door either way.
        remote = wm.session_is_remote() is True
        if away.get("mode") != "dim" and not remote:
            return {}
        self.away_status = {}
        # the ledgers ACCUMULATE, never reset: a live preview already
        # holds the true priors (the value at the leaving moment), and
        # a reset here would replace them with the dimmed values the
        # spell itself wrote. _away_lift is the one clear site.
        self._away_bright = getattr(self, "_away_bright", None) or {}
        self._away_hdr = getattr(self, "_away_hdr", None) or []
        self._away_off = getattr(self, "_away_off", None) or {}
        self._away_disc = getattr(self, "_away_disc", None) or {}
        rows = away.get("monitors") or {}
        jail = None
        painted = None
        desk = _live_desk()
        for m in desk:
            mode = _row_mode(rows, m)
            if remote and mode is not None:
                mode = None                # the remote session exempts
                #                          the whole desk: the None leg
                #                          below is its stand-down
            rec = self._away_apply_row(m, mode, away.get("dim_level", 10))
            if mode is None:
                # the EXEMPTION word, the sibling of "gone": the row
                # did not lose its panel - the panel is virtual glass
                # (bus-root flag) or the desk is a remote canvas, and
                # every off leg stands down (no D6, no retraction, no
                # blackout paint; the cover is hidden, the ledgers
                # stay clean, and _row_went_dark does not know this
                # word: an all-exempt engage never locks the session).
                # An engage that darked NOTHING still returns the
                # dict: _screens_off's guard is what skips the
                # power broadcast too - no painting into nothing.
                rec["status"] = "exempt (virtual/remote)"
            self.away_status[m["short"]] = rec["status"]
            self._away_hdr += rec.get("hdr") or []
            if rec.get("off"):
                # the ledger carries the MOMENT of the attempt (gate
                # finding 5b): a refused hand-back at lift logs when
                # the spell asked, not just that it hurts now
                self._away_off[m["gdi"]] = rec.get("tried", time.time())
            if rec.get("saved"):
                # the offdisc ledger lives beside _away_off (in-memory,
                # the packet's law) and holds the RESTORE RECORD the
                # lift hands back; a refused offdisc row owes no record
                # (nothing took effect - the door validated before it
                # touched the glass, or restored its own wrong victim)
                self._away_disc[m["gdi"]] = rec["saved"]
            if painted is None and mode in ("blackout", "dim"):
                # a PAINTED row (owner, Oct 17): the pointer gets the
                # PARK, not the corner jail - a white arrow at a black
                # panel's far corner is the most visible pixel on the
                # dark. Bottom-middle hides it below the eye line, and
                # under the strip where a hider runs; the jail keeps
                # the sleep rows it was written for.
                painted = m
            elif jail is None and mode in ("off", "offdisc"):
                jail = (m["x"], m["y"], m["w"], m["h"])
        if painted is not None:
            display.park_cursor(*self.park_point(desk))
        elif jail:
            display.jail_cursor(jail)
        display.arm_input_lift(True)
        log.info("away: dim mode, %d monitors (%d HDR off, %d VCP-off "
                 "asked, %d disconnected, %d rows blackout-degraded on refusal)",
                 len(self.away_status), len(self._away_hdr),
                 len(self._away_off), len(self._away_disc),
                 sum(1 for s in self.away_status.values()
                     if s.startswith("blackout (") or
                     s.startswith("off refused") or
                     s.startswith("offdisc refused")))
        self._away_lock(away.get("lock"))   # the spell's last chore:
        #                                   rows, jail, THEN the lock -
        #                                   a locked desktop with a
        #                                   parked cursor is harmless
        return self.away_status

    @staticmethod
    def park_point(monitors):
        """The painted-away park point (owner, Oct 17): the bottom
        middle of the LOWEST monitor - ties broken toward the panel
        whose center sits nearest the desk's horizontal middle, the
        one you look at. Two pixels in from the edge: the taskbar
        strip, or the bezel's last line, takes the rest of the arrow.
        No restore on return, the owner's own words: 'no restore,
        noone remembers where there cursor was after leaving the
        room' - a pointer teleported back under the hand is a
        stranger's gesture; a parked one is where you left it."""
        left = min(m["x"] for m in monitors)
        right = max(m["x"] + m["w"] for m in monitors)
        bottom = max(m["y"] + m["h"] for m in monitors)
        mid = (left + right) / 2.0
        m = min((m for m in monitors if m["y"] + m["h"] == bottom),
                key=lambda m: abs((m["x"] + m["w"] / 2.0) - mid))
        return (m["x"] + m["w"] // 2, m["y"] + m["h"] - 2)

    def _away_lock(self, lock_on):
        """lock-on-away (owner-ruled, 2026-10-14): a real engage that
        darked at least one row locks the workstation, so the dark
        belongs to the LOCK SCREEN and a returning face gets their own
        desk back, never somebody else's. The law's edges, all the
        owner's: a PREVIEW NEVER LOCKS (this rides the engage only -
        the preview walks _away_apply_row, not here; the mid-preview
        handoff locks when the REAL engage fires); a zero-row or an
        all-refused engage locks nothing (a dark that is only the
        degradation the summary line counts is nobody's applied
        effect); the corner jail ran first (a locked desktop with a
        parked cursor is harmless, the reverse is a hunt); and a
        refused lock is a WARNING, never a raise into the spell - the
        dark stands, unlocked, honest.
        THE LOCK-AWARE WAKE this commits to: raw input is per-desktop,
        so while Winlogon owns the desk the lift EARS are deaf by
        construction. The lift path answers to input NOT at all (it is
        queue-driven): the spell comes off from the camera's presence
        eye, which keeps its stream through the lock (VERIFIED in the
        phase machine: the off-phase polls and _wake lifts without
        ever consulting an input event - and GetLastInputInfo counts
        the locked session as idle, README's own note, so the absence
        logic stays honest the whole spell), and from the watcher's
        session-unlock ear, which posts the same away_lift the overlay
        click rides."""
        if not lock_on or not any(_row_went_dark(s)
                                  for s in self.away_status.values()):
            return
        from .. import display
        try:
            ok = bool(display.u32.LockWorkStation())
        except Exception:
            ok = False
        if ok:
            log.info("away: workstation locked (lock-on-away)")
        else:
            log.warning("away: the workstation lock refused; the spell "
                        "stays dark, unlocked")

    def _away_apply_row(self, m, mode, level):
        """One monitor's effect, the SAME call the preview walks so a
        preview really tests what away will do - and the single
        footprint stays honest (a preview never dims a NEIGHBOUR's
        HDR). Ledger before write: the honest hand-back needs the
        prior answer, or max when the read itself refused. SIZE LAW
        (owner, 2026-10-14): the off sub-mode lifts this method's
        effect budget from ≤40 to ≤80 lines - the door's two honest
        halves and the blackout fallback do not fit in 40 without
        splitting the law's prose from its call sites."""
        from .. import wm
        from ..wm import _bright, _overlay
        if getattr(self, "_away_bright", None) is None:
            self._away_bright = {}
        rect = (m["x"], m["y"], m["w"], m["h"])
        rec = {"short": m["short"], "gdi": m["gdi"], "mode": mode}
        if mode is None:                      # the row lost its
            _overlay.hide(m["gdi"])           # panel mid-preview
            rec["status"] = "gone"
            return rec
        if mode == "off":
            rec["off"] = True                 # even a refused row:
            # the lift's D6=1 rides UNCONDITIONALLY, on EVERY wake
            # reason, for every row that ever asked for off - the
            # raw-input wake asymmetry (the owner's experiment,
            # 2026-10-14: Windows believes a VCP-offed panel is ON
            # and reports no input from a dead face, so that panel
            # can NEVER lift the spell on its own pixels; the write
            # is the only way back, and a late-NAKing bus may have
            # darkened it while reporting failure anyway).
            sent, say = _bright.vcp(m["gdi"], _bright.VCP_POWER,
                                    _bright.VCP_POWER_OFF)
            rec["tried"] = time.time()        # a refusal is a fact
                                              # about THIS attempt -
                                              # dated at the moment
                                              # the budget spent
            if not sent:
                # blackout fallback, confessed on the word, silent
                # nowhere (the refusal half of the door's law)
                _overlay.show(m["gdi"], rect)
                rec["status"] = ("off refused - blackout instead (%s)"
                                 % say)
                return rec
            # the UNIVERSAL word (gate finding 4, 2026-10-14): the
            # control panel's power register answered "on" straight
            # through a fully-ACKed dark window (DOSSIER UPDATE: the
            # register cannot track DPMS state), so no readback can
            # certify the dark - the first pass's bare-"off"
            # promotion on an answering register is retired, and the
            # engage does not even TRAFFIC the bus for one. The
            # preview is the human judge; "(unverified)" is the
            # ceiling of what this door can ever promise from here.
            rec["status"] = "off (unverified)"
            return rec
        if mode == "offdisc":
            # the DISCONNECT flavor (final wave, 2026-10-14): the path
            # retracts AT THE ADAPTER - works regardless of firmware
            # (the panel never hears a code, it loses its signal), and
            # it comes back as a replug. wm/_sdc.py carries the measured
            # law: PATH-MINUS, the 0x6A0 verb set, and the CCD re-query
            # as the ONLY honest verification (the GDI rows lie through
            # the KVM). The word below is therefore PROVED, not trusted
            # - the deliberate contrast with the D6 branch above.
            from ..wm import _sdc
            rec["offdisc"] = True             # even a refused row: the
            # jail and the summary count it class-wide (the blackout
            # fallback's confession rides the word below)
            ok, say = _sdc.retract(m)
            rec["tried"] = time.time()        # the dated-law timestamp
            if not ok:
                _overlay.show(m["gdi"], rect)
                rec["status"] = ("offdisc refused (%s - blackout "
                                 "instead)" % say)
                return rec
            rec["saved"] = say                # the restore record: the
            #                    captured arrays with the victim ACTIVE;
            #                    the lift's restore carries SAVE too
            #                    (or the store reboots the panel dark)
            rec["status"] = "off (disconnected)"
            return rec
        if mode == "blackout":
            _overlay.show(m["gdi"], rect)
            rec["status"] = "blackout"
            return rec
        if mode != "dim":
            # the silent-wrong-leg class, confessed (the offdisc-preview
            # fix): a word this dispatch does not know used to fall
            # through to the dim leg with a shrug - the dim default
            # stands (harmless to the real spells, which are worded),
            # but a caller sending labels instead of words must say so
            # at the point of fall-through, not in a bug report later
            log.warning("away: unknown sub-mode %r on %s - the dim leg "
                        "is the default; check the caller's label "
                        "mapping", mode, m["short"])
        prior = _bright.get(m["gdi"])
        say, verified = _bright.set(m["gdi"], level)
        if m["gdi"] not in self._away_bright:
            # first question wins: a preview already asked, and its
            # prior is the TRUE one (the value at the leaving moment,
            # not the dimmed value a later engage would read back)
            self._away_bright[m["gdi"]] = prior
        if say:
            # the refusal law made concrete (the SEND half - a deaf
            # READBACK is the trust half, worded below): the row the
            # user asked to be DIM goes black under an overlay
            # instead, and the status word carries the confession the
            # card renders
            _overlay.show(m["gdi"], rect)
            rec["status"] = "blackout (%s)" % say
            return rec
        try:
            for r in wm.hdr_states():
                if r["gdi"] == m["gdi"] and r.get("precise") and \
                        r.get("supported") and r.get("state") == "on" \
                        and wm.hdr_set(m["gdi"], False) == "":
                    rec["hdr"] = [{"gdi": r["gdi"],
                                   "model": r.get("model") or ""}]
        except Exception:
            log.debug("away: the HDR read refused on %s, dim continues "
                      "without it", m["short"], exc_info=True)
        rec["status"] = "dim" if verified else "dim (unverified)"
        return rec

    # --------------------------------------------------------------- lift --
    def _away_lift(self):
        """Overlays down, brightness back, HDR back - this exact
        order (a panel revealed at 10% under a late overlay reads as
        a bug even when every step is right). The handback rides the
        model-aware pair verbatim. A no-op when nothing was dimmed:
        the stock off spell and the never-away desk pass through
        untouched."""
        status = getattr(self, "away_status", None) or {}
        if not status:
            return ""
        from .. import display, profiles
        from ..wm import _bright, _overlay, _sdc
        bright = getattr(self, "_away_bright", None) or {}
        hdr = getattr(self, "_away_hdr", None) or []
        off = getattr(self, "_away_off", None) or {}
        disc = getattr(self, "_away_disc", None) or {}
        for gdi, tried in off.items():
            # UNCONDITIONAL on every wake reason - the asymmetry note
            # lives at the engage side; the wake can only have come
            # from the LIT panels (ears) or the gates: an offed panel
            # reports nothing, so this write is its only way back.
            sent, say = _bright.vcp(gdi, _bright.VCP_POWER,
                                    _bright.VCP_POWER_ON)
            if not sent:
                log.warning("away: the power hand-back on %s refused "
                            "(%s) - the panel may sit dark until its "
                            "own button (the spell asked at %s; the "
                            "next spell's probe will say what the bus "
                            "says)", gdi, say,
                            time.strftime("%Y-%m-%d %H:%M:%S",
                                          time.localtime(tried)))
        for gdi, saved in disc.items():
            # the disconnect hand-back rides the SAME unconditional
            # law, and the SAVE bit rides inside _sdc.restore (a
            # restore without it leaves the CCD store rebooting the
            # panel dark - the footgun, closed at every write). A
            # refusal here is not the end: the belt's offdisc door
            # re-asks the store at the next boot.
            ok, say = _sdc.restore(saved)
            if not ok:
                log.warning("away: the disconnect hand-back on %s "
                            "refused (%s) - the panel sits dark until "
                            "the belt or Settings raises it (the spell "
                            "asked at %s)", gdi, say,
                            time.strftime("%Y-%m-%d %H:%M:%S",
                                          time.localtime(saved["at"])))
        _overlay.hide_all()                       # every cover first:
        #                                   paint dies before the panel
        #                                   underneath changes state
        for gdi, prior in bright.items():
            # get refused at the leaving moment? max is the honest
            # hand-back (the packet's law)
            _bright.restore(gdi, prior if prior is not None else 100)
        profiles.hdr_away_restore(hdr)            # only what WE offed
        display.unjail_cursor()                   # the cursor goes home
        #                                   with the spell (no-op if
        #                                   the spell never covered)
        display.arm_input_lift(False)
        self.away_status = {}
        self._away_bright = {}
        self._away_hdr = []
        log.info("away: lifted (%d brightness hand-back(s), %d HDR "
                 "panel(s), %d power hand-back(s), %d disconnect "
                 "hand-back(s))", len(bright), len(hdr), len(off),
                 len(disc))
        self._away_off = {}
        self._away_disc = {}
        return status

    def _away_boot_belt(self):
        """The boot belt (gate finding 1, 2026-10-14): the ledger is
        in-memory, so a quit or a kill mid-spell dies with it and a
        D6-off panel sits DARK forever - the boot's _force_on asks an
        empty ledger and learns nothing. So boot asks the CONFIG:
        every row that asks for off gets one idempotent D6=1 on the
        reachable live desk, full retry budget spent by the door's
        own law. One log line per row reached; NEVER-reached rows
        (no door) stay silent; the whole pass never raises into boot
        - a belt that can break the boot is worse than the dark
        panel it saves (the physical button remains undefeated).
        THE SECOND DOOR (final wave): every row configured offdisc
        gets a CCD re-query - and if its target sits INACTIVE in the
        store (a crash, a quit, or an update between the retraction
        and its hand-back: the SAVE bit keeps the disconnect past
        this app, the documented footgun), the path is raised back
        with SAVE too. THIS is the answer to the survives-the-app
        footgun from inside the app - an uninstall's dark stays a
        changelog sentence, the belt cannot help a deleted app. The
        door asks the CONFIG's EDID token, not the desk's rows: a
        retracted panel may answer to no GDI row at all (or only to
        a lying ghost). A desk with no offdisc rows never reaches
        the CCD at all - the belt's first live act is silence."""
        from ..wm import _bright, _sdc
        away = self.cfg.get("away") or {}
        rows = away.get("monitors") or {}
        # THE EXEMPTION reaches the belt too (the canvas is not a
        # panel: the DDC door ACKs and LIES on it - reachable=True,
        # nphys=1, measured from inside the session). The short set
        # is precomputed OUTSIDE both try-blocks (gate fix 3 stays
        # honored: a raising D6 row must not skip the disconnect
        # pass), and it is total: _live_desk answers fail-soft and
        # every read below is a .get.
        desk = _live_desk()
        virtual = {m.get("short") for m in desk if m.get("virtual")}
        try:
            for m in desk:
                row = rows.get(m["short"])
                if not (row or {}).get("off"):
                    continue
                if m.get("virtual"):
                    continue          # the belt says nothing to a
                    #                 # canvas: no DDC door, no door
                if not _bright.reachable(m["gdi"]):
                    continue          # no door: the belt says nothing
                sent, say = _bright.vcp(m["gdi"], _bright.VCP_POWER,
                                        _bright.VCP_POWER_ON)
                log.info("away belt: boot power-on for %s %s",
                         m["short"], "sent" if sent
                         else "refused (%s)" % say)
        except Exception:
            log.debug("away belt: the boot power-on pass failed",
                      exc_info=True)
        # the second door keeps its OWN try-block (gate fix 3): a
        # raising D6 row must not skip the disconnect pass - one
        # belt, two doors, each dying alone
        try:
            for short, row in rows.items():
                if not (row or {}).get("offdisc"):
                    continue
                if short in virtual:
                    continue          # the row answers the live desk
                    #                 as a canvas: no retraction to
                    #                 raise back (a withdrawn canvas
                    #                 that answers NO row stays the
                    #                 belt's existing silent class)
                # gdi unknown for a retracted row (no desk slot to
                # name): the token join carries it, and an ambiguous
                # twin answers None = silent, never a gamble - and
                # at THIS call shape a slot/token dispute cannot even
                # form (no gdi to cross-check): disputes stay silent
                # by design on the belt's road, the loud refusal
                # belongs to the gdi-naming callers (engage side)
                verdict = _sdc.revive({"short": short, "gdi": ""})
                if verdict is not None:
                    log.info("away belt: boot disconnect-restore for "
                             "%s %s", short,
                             "sent" if verdict[0]
                             else "refused (%s)" % verdict[1])
        except Exception:
            log.debug("away belt: the boot disconnect pass failed",
                      exc_info=True)

    # ---------------------------------------------------------- the preview --
    def _away_release(self, short, rec):
        """One preview's effect back. The adopt-vs-revert law: if the
        real away spell covers this monitor now, ADOPT - the spell's
        own ledger owns the hand-back from here; else undo exactly
        this record, same order as the lift."""
        status = getattr(self, "away_status", None) or {}
        if short in status:
            # fold the preview's HDR record into the spell's ledger (the
            # spell's own read already sees the panel dark, so IT cannot
            # record the hand-back - the preview's record is the only
            # witness that WE turned it off), and leave the brightness
            # prior in the shared ledger: the spell hands it back.
            for e in rec.get("hdr") or []:
                if e not in (getattr(self, "_away_hdr", None) or []):
                    self._away_hdr.append(e)
            if rec.get("saved"):
                # the offdisc fold rides the SAME witness law as the
                # HDR fold: a retracted panel answers to no GDI row
                # (ghost or not), so the spell's own pass may never
                # have walked it - the preview's record is the only
                # witness of the retraction, and the lift pays it
                self._away_disc = getattr(self, "_away_disc", None) or {}
                self._away_disc[rec["gdi"]] = rec["saved"]
            log.info("away: the preview of %s folds into the real "
                     "dim - the spell hands it back", short)
            return "adopted"
        from .. import profiles
        from ..wm import _bright, _overlay, _sdc
        _overlay.hide(rec["gdi"])
        if rec.get("off"):
            # the preview's own D6=1 - same unconditional law as the
            # lift, this time earned by the preview rather than owed
            # by a spell (a refused-off preview wore the fallback
            # overlay instead; the ON is the no-op it deserves)
            sent, say = _bright.vcp(rec["gdi"], _bright.VCP_POWER,
                                    _bright.VCP_POWER_ON)
            if not sent:
                log.warning("away: the preview's power hand-back on %s "
                            "refused (%s) - the panel may sit dark "
                            "until its own button", rec["gdi"], say)
        if rec.get("saved"):
            # and the preview's own disconnect hand-back, same law in
            # the other flavor (the refused-offdisc preview wore the
            # fallback overlay; the restore is the no-op it deserves)
            ok, say = _sdc.restore(rec["saved"])
            if not ok:
                log.warning("away: the preview's disconnect hand-back "
                            "on %s refused (%s) - the panel may sit "
                            "dark until the belt raises it",
                            rec["gdi"], say)
        if rec["gdi"] in (getattr(self, "_away_bright", None) or {}):
            prior = self._away_bright[rec["gdi"]]
            _bright.restore(rec["gdi"], prior if prior is not None
                            else 100)
            self._away_bright.pop(rec["gdi"], None)
        profiles.hdr_away_restore(rec.get("hdr") or [])
        log.info("away: preview of %s reverted (%s)", short,
                 rec["status"])
        return "reverted"


def _row_mode(rows, m):
    """The row's sub-mode ("blackout" | "dim" | "off" | "offdisc"),
    absent-defaulted to DIM (the packet's rule: a monitor NOT in
    away.monitors is a dim row in dim mode - the migration promise,
    and the honest default for a panel that joined after the config
    was written). normalize ships the triple; precedence on a
    hand-edited file that sets several: offdisc beats off beats
    blackout (a retracted path cannot hear a power code, and the
    retraction is the most explicit ask on the row). A VIRTUAL row
    (the bus-root flag, wm/_monitors._row_is_virtual) answers None:
    the exemption is not a sub-mode, it is the stand-down of every
    off leg - the engage's None leg carries the word."""
    if m.get("virtual"):
        return None
    row = rows.get(m["short"])
    if not row:
        return "dim"
    if row.get("offdisc"):
        return "offdisc"
    if row.get("off"):
        return "off"
    return "blackout" if row.get("blackout") else "dim"


def _row_went_dark(status):
    """Did this row's dark get APPLIED (the lock-on-away predicate)?
    A WHITELIST of the exact applied words (gate fix 5), not a
    prefix pattern: a future status word must be an explicit
    decision at this table, never a silent yank of the session (or
    a silent skip) by sharing someone else's prefix. The degraded
    refusals ("blackout (word)", "off refused - blackout instead",
    "offdisc refused (...)") and the "gone" row are absent - the
    summary line's degradation count is not an applied dark, and
    an all-refused engage must not yank the session."""
    return status in ("blackout", "dim", "dim (unverified)",
                      "off (unverified)", "off (disconnected)")


def _live_desk():
    """The desk's rows, fail-soft: a topology storm mid-engage gets
    the panels the enum can still name, and never a crash inside the
    off transition (the layout memory's own religion)."""
    from .. import wm
    try:
        return list(wm.monitors())
    except Exception:
        log.debug("away: the desk cannot be enumerated right now",
                  exc_info=True)
        return []
