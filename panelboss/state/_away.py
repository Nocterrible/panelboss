"""The away engine: dim-mode substitution for the display power verb.

SIZE LAW header: this part owns the fake-off ledger and nothing else.
The state machine keeps its shape - _power.py calls _away_engage()
where it used to call the broadcast, _away_lift() where it wakes,
_events.py arms the two queue messages (away_lift from the input
hooks and the overlay click) and the unexpected-wake lift; the
policy, phase and camera machines are untouched, because the whole
point of the feature is that the presence engine keeps working
exactly as it does while dark.

The laws set here, from the 2026-10-14 probe (wm/_bright.py carries
the full education): a refused panel - DDC/CI silent, or accepting
writes and never obeying them - DEGRADES its row to blackout with
the confession recorded in away_status, never silent. HDR rides the
packet's per-row rule (a dim row's own hdr_set(False), remembered as
{"gdi","model"} rows exactly like the proven pair's snapshot) and
the handback rides profiles.hdr_away_restore VERBATIM - the
model-aware half that survives the standby slot-shuffle. And a
preview of a row the real away spell took over mid-way ADOPTS the
spell instead of reverting: un-dimming a real away is the bug this
seam exists to kill (the architect's owner-call, 2026-10-14). The
adopt law lives engine-side so the suite can fake it without a Tk.
"""

import logging

log = logging.getLogger("state")


class _AwayMixin:

    # ------------------------------------------------------------- engage --
    def _away_engage(self):
        """Called where the off broadcast used to stand: dim mode
        paints the dark INSTEAD of powering it - the blackout rows
        wear the overlay, the dim rows lose their HDR and drop to
        dim_level. Returns {} when the mode is the stock off - the
        caller takes the broadcast path untouched, and the legacy
        global hdr_off_when_away block stays readable and honored
        there (downgrade honesty, one release)."""
        away = self.cfg.get("away") or {}
        if away.get("mode") != "dim":
            return {}
        from .. import display
        self.away_status = {}
        self._away_bright = {}
        self._away_hdr = []
        rows = away.get("monitors") or {}
        for m in _live_desk():
            rec = self._away_apply_row(m, _row_blackout(rows, m),
                                       away.get("dim_level", 10))
            self.away_status[m["short"]] = rec["status"]
            self._away_hdr += rec.get("hdr") or []
        display.arm_input_lift(True)
        log.info("away: dim mode, %d monitors (%d HDR off, %d rows "
                 "blackout-degraded on refusal)", len(self.away_status),
                 len(self._away_hdr),
                 sum(1 for s in self.away_status.values()
                     if s.startswith("blackout (")))
        return self.away_status

    def _away_apply_row(self, m, blackout, level):
        """One monitor's effect, the SAME call the preview walks so a
        preview really tests what away will do - and the single
        footprint stays honest (a preview never dims a NEIGHBOUR's
        HDR). Ledger before write: the honest hand-back needs the
        prior answer, or max when the read itself refused."""
        from .. import wm
        from ..wm import _bright, _overlay
        if getattr(self, "_away_bright", None) is None:
            self._away_bright = {}
        rect = (m["x"], m["y"], m["w"], m["h"])
        rec = {"short": m["short"], "gdi": m["gdi"]}
        if blackout is None:                      # the row lost its
            _overlay.hide(m["gdi"])               # panel mid-preview
            rec["status"] = "gone"
            return rec
        if blackout:
            _overlay.show(m["gdi"], rect)
            rec["status"] = "blackout"
            return rec
        prior = _bright.get(m["gdi"])
        say = _bright.set(m["gdi"], level)
        self._away_bright[m["gdi"]] = prior
        if say:
            # the refusal law made concrete: the row the user asked
            # to be DIM goes black under an overlay instead, and the
            # status word carries the confession the card renders
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
        rec["status"] = "dim"
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
        _overlay.hide_all()                       # every cover first:
        #                                   paint dies before the panel
        #                                   underneath changes state
        for gdi, prior in bright.items():
            # get refused at the leaving moment? max is the honest
            # hand-back (the packet's law)
            _bright.restore(gdi, prior if prior is not None else 100)
        profiles.hdr_away_restore(hdr)            # only what WE offed
        display.arm_input_lift(False)
        self.away_status = {}
        self._away_bright = {}
        self._away_hdr = []
        log.info("away: lifted (%d brightness hand-back(s), %d HDR "
                 "panel(s))", len(bright), len(hdr))
        return status

    # ---------------------------------------------------------- the preview --
    def _away_release(self, short, rec):
        """One preview's effect back. The adopt-vs-revert law: if the
        real away spell covers this monitor now, ADOPT - the spell's
        own ledger owns the hand-back from here; else undo exactly
        this record, same order as the lift."""
        status = getattr(self, "away_status", None) or {}
        if short in status:
            log.info("away: the preview of %s folds into the real "
                     "dim - the spell hands it back", short)
            return "adopted"
        from .. import profiles
        from ..wm import _bright, _overlay
        _overlay.hide(rec["gdi"])
        if rec["gdi"] in (getattr(self, "_away_bright", None) or {}):
            prior = self._away_bright[rec["gdi"]]
            _bright.restore(rec["gdi"], prior if prior is not None
                            else 100)
            self._away_bright.pop(rec["gdi"], None)
        profiles.hdr_away_restore(rec.get("hdr") or [])
        log.info("away: preview of %s reverted (%s)", short,
                 rec["status"])
        return "reverted"


def _row_blackout(rows, m):
    """The row's answer, absent-defaulted to the dim sub-mode (the
    packet's rule: a monitor NOT in away.monitors is a dim row in
    dim mode - the migration promise, and the honest default for a
    panel that joined after the config was written)."""
    row = rows.get(m["short"])
    if row is None:
        return False
    return bool(row.get("blackout"))


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
