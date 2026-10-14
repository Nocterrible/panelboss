"""The away engine: dim-mode substitution for the display power verb.

SIZE LAW header: this part owns the fake-off ledger and nothing else -
and at 307 lines the whole is still one law: the ledgers, the door
calls and the status words interlock line-for-line, and splitting the
prose from its call sites (or the lift from the engage) would sell a
seam for nothing. The off wave's growth is this file's due; the card
paint lives in ui/window/_away.py.
The state machine keeps its shape - _power.py calls _away_engage()
where it used to call the broadcast, _away_lift() where it wakes,
_events.py arms the two queue messages (away_lift from the input
hooks and the overlay click) and the unexpected-wake lift; the
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
never in a pre-sentence about firmware.
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
        Covered rows also bring the corner jail (display.jail_cursor:
        the cursor parks at a covered rect's far corner, ONCE per
        engage - SetCursorPos generates no raw input, so the jail
        itself can never wake what it covers; the owner's request,
        and the off/blackout rows need it equally). Returns {} when
        the mode is the stock off - the caller takes the broadcast
        path untouched, and the legacy global hdr_off_when_away block
        stays readable and honored there (downgrade honesty, one
        release)."""
        away = self.cfg.get("away") or {}
        if away.get("mode") != "dim":
            return {}
        from .. import display
        self.away_status = {}
        # the ledgers ACCUMULATE, never reset: a live preview already
        # holds the true priors (the value at the leaving moment), and
        # a reset here would replace them with the dimmed values the
        # spell itself wrote. _away_lift is the one clear site.
        self._away_bright = getattr(self, "_away_bright", None) or {}
        self._away_hdr = getattr(self, "_away_hdr", None) or []
        self._away_off = getattr(self, "_away_off", None) or []
        rows = away.get("monitors") or {}
        jail = None
        for m in _live_desk():
            mode = _row_mode(rows, m)
            rec = self._away_apply_row(m, mode, away.get("dim_level", 10))
            self.away_status[m["short"]] = rec["status"]
            self._away_hdr += rec.get("hdr") or []
            if rec.get("off") and m["gdi"] not in self._away_off:
                self._away_off.append(m["gdi"])
            if jail is None and (mode == "off" or
                                 rec["status"].startswith("blackout")):
                jail = (m["x"], m["y"], m["w"], m["h"])
        if jail:
            display.jail_cursor(jail)
        display.arm_input_lift(True)
        log.info("away: dim mode, %d monitors (%d HDR off, %d VCP-off "
                 "asked, %d rows blackout-degraded on refusal)",
                 len(self.away_status), len(self._away_hdr),
                 len(self._away_off),
                 sum(1 for s in self.away_status.values()
                     if s.startswith("blackout")))
        return self.away_status

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
            time.sleep(_bright.CONFIRM_SLEEP_SEC)
            answered, val = _bright.vcp_read(m["gdi"], _bright.VCP_POWER)
            # the trust half - and the DEFAULT word here: the control
            # panel's power register answered "on" straight through a
            # fully-ACKed off window (scripts/sdc_off_probe.py), so
            # on panels like this (unverified) is the ceiling of what
            # a write can prove, and the preview is the human judge.
            # Panels with honest registers do earn the plain word.
            rec["status"] = ("off" if answered and val is not None and
                             val == _bright.VCP_POWER_OFF
                             else "off (unverified)")
            return rec
        if mode == "blackout":
            _overlay.show(m["gdi"], rect)
            rec["status"] = "blackout"
            return rec
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
        from ..wm import _bright, _overlay
        bright = getattr(self, "_away_bright", None) or {}
        hdr = getattr(self, "_away_hdr", None) or []
        off = getattr(self, "_away_off", None) or []
        for gdi in off:
            # UNCONDITIONAL on every wake reason - the asymmetry note
            # lives at the engage side; the wake can only have come
            # from the LIT panels (ears) or the gates: an offed panel
            # reports nothing, so this write is its only way back.
            sent, say = _bright.vcp(gdi, _bright.VCP_POWER,
                                    _bright.VCP_POWER_ON)
            if not sent:
                log.warning("away: the power hand-back on %s refused "
                            "(%s) - the panel may sit dark until its "
                            "own button, and the next spell's probe "
                            "will say what the bus says", gdi, say)
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
                 "panel(s), %d power hand-back(s))", len(bright), len(hdr),
                 len(off))
        self._away_off = []
        return status

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
            log.info("away: the preview of %s folds into the real "
                     "dim - the spell hands it back", short)
            return "adopted"
        from .. import profiles
        from ..wm import _bright, _overlay
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
    """The row's sub-mode ("blackout" | "dim" | "off"), absent-
    defaulted to DIM (the packet's rule: a monitor NOT in
    away.monitors is a dim row in dim mode - the migration promise,
    and the honest default for a panel that joined after the config
    was written). normalize ships the pair shape; off beats blackout
    on a hand-edited file that sets both, since the panel cannot do
    both."""
    row = rows.get(m["short"])
    if not row:
        return "dim"
    if row.get("off"):
        return "off"
    return "blackout" if row.get("blackout") else "dim"


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
