"""The away card: what the app does when it turns the displays off.

SIZE LAW header: UI only. The sub-mode laws, the ledger and the
adopt-vs-revert law live engine-side (panelboss/state/_away.py); the
paint and the brightness ride wm/_overlay.py and wm/_bright.py. This
file draws one card, keeps its rows honest about what the desk just
did, and runs the 10 s preview on a threading.Timer whose revert
calls INTO the engine law, never around it.

Visual language: the mode picker is the detection tab's own segmented
idiom (same widget, same skin call as person/motion); the rows follow
the profile monitor list (short name first - duplicate models get
the gdi slot tail, same disambiguation the mode editor uses). Two
adaptations, logged honestly: the disabled-mode gray pass is written
HERE (this tab's sibling behavior is pack-forget hiding - no gray
walker existed to reuse), and the preview's dialog-above-the-paint
uses topmost+raise on the settings window: transient() is not a word
across Tk interpreters, and the overlay lives on its own thread.
"""

from __future__ import annotations

import logging
import threading

import customtkinter as ctk

from ... import wm
from ._widgets import set_text

log = logging.getLogger("ui")

OFF_TEXT = "monitors off"
DIM_TEXT = "dim"

TIP = {
    "mode": "off: the displays get the real power broadcast, exactly "
            "as always. dim: the panels STAY AWAKE and the app paints "
            "the dark - no cold re-enumeration on wake (the 16-38 s "
            "class), no driver drama. blackout rows wear an opaque "
            "black cover (a click on it wakes the desk); dim rows "
            "lose their HDR and drop to the brightness below for the "
            "spell and get it all back on lift. MEASURED ON THIS "
            "DESK CLASS: some panels accept brightness writes and "
            "never obey them - those rows degrade to blackout and "
            "say so on their status word, never silently.",
    "row": "blackout = the painted lie; dim = HDR off + the shared "
           "brightness level. a preview applies THIS row's effect "
           "for 10 s and reverts it (the second click cancels now; "
           "a real away arriving mid-preview keeps the effect and "
           "hands it back at the real wake instead).",
    "level": "where dim rows park their brightness while away, 1 to "
              "40 percent - shared by every dim row (per-monitor "
              "levels are a planned follow-up).",
}


class _AwayMixin:
    # ------------------------------------------------------------------ away --
    def _away_card(self, left):
        box = self._card(left, "when the app turns the displays off",
                         "play dead instead of asleep: the panels keep "
                         "their power, the desk gets the dark painted "
                         "on")
        row = self._row(box, "mode", TIP["mode"], hint_chars=42)
        self.away_mode_button = ctk.CTkSegmentedButton(
            row, values=[OFF_TEXT, DIM_TEXT], height=26, width=190,
            command=self._away_mode_changed,
            **self.skin.segmented_style())
        self.away_mode_button.set(
            DIM_TEXT if (self.cfg.get("away") or {}).get("mode") == "dim"
            else OFF_TEXT)
        self.away_mode_button.grid(row=0, column=1, sticky="e")

        # one row per live panel, the profile list's idiom
        self._away_rows = {}
        self._away_jobs = {}          # short -> {"timer", "rec"}
        self._away_says = {}          # short -> status word to show
        base = [m.get("short") or m.get("id") for m in wm.monitors()]
        dupes = {b for b in base if base.count(b) > 1}
        for m, short in zip(wm.monitors(), base):
            label = short
            if short in dupes:
                label = "%s (%s)" % (
                    short, str(m.get("gdi") or "").rsplit("DISPLAY", 1)
                    [-1] or "?")
            row = self._row(box, label, TIP["row"], hint_chars=42)
            seg = ctk.CTkSegmentedButton(
                row, values=["blackout", "dim"], height=26, width=150,
                command=lambda v, s=short: self._away_submode_changed(s, v),
                **self.skin.segmented_style())
            seg.set(self._away_row_blackout(short) and "blackout" or "dim")
            seg.grid(row=0, column=1, sticky="e")
            value = ctk.CTkLabel(row, font=self.skin.font(12),
                                 **self.skin.text_style("sub"))
            value.grid(row=0, column=3, sticky="e", padx=(6, 0))
            slider = ctk.CTkSlider(row, from_=1, to=40,
                                   number_of_steps=39, width=150,
                                   command=self._away_level_changed,
                                   **self.skin.slider_style())
            slider.set(self._away_level())
            slider.grid(row=0, column=2, sticky="e")
            value.configure(text="%d%%" % self._away_level())
            preview = ctk.CTkButton(row, text="preview", width=84,
                                    command=lambda s=short:
                                    self._away_preview_clicked(s),
                                    **self.skin.secondary())
            preview.grid(row=0, column=4, sticky="e", padx=(6, 0))
            say = ctk.CTkLabel(box, text="", font=self.skin.font(10),
                               wraplength=350, justify="left", anchor="w",
                               **self.skin.text_style("sub"))
            self._away_rows[short] = {"row": row, "seg": seg,
                                      "slider": slider, "value": value,
                                      "preview": preview, "say": say,
                                      "gdi": m["gdi"]}
            say.pack(anchor="w")
        self._away_sync()
        self.after(900, self._away_poll)

    # ------------------------------------------------------------ state reads --
    def _away_level(self):
        return int((self.cfg.get("away") or {}).get("dim_level", 10))

    def _away_row_blackout(self, short):
        rows = (self.cfg.get("away") or {}).get("monitors") or {}
        row = rows.get(short)
        return bool(row and row.get("blackout"))

    # ------------------------------------------------------------- handlers --
    def _away_mode_changed(self, label):
        # cfg["away"] IS the engine's dict: writing is applying, the
        # next _screens_off already engages (or doesn't) the new mode
        self.cfg.setdefault("away", {})["mode"] = \
            "dim" if label == DIM_TEXT else "off"
        self._away_sync()
        self._save()

    def _away_submode_changed(self, short, label):
        rows = self.cfg.setdefault("away", {}).setdefault("monitors", {})
        rows.setdefault(short, {})["blackout"] = label == "blackout"
        self._away_sync()
        self._save()

    def _away_level_changed(self, value):
        level = int(round(value))
        self.cfg.setdefault("away", {})["dim_level"] = level
        # the level is GLOBAL by design (per-monitor levels are the
        # named follow-up): every dim row shows the one answer
        for r in self._away_rows.values():
            if r["slider"].winfo_manager():
                r["value"].configure(text="%d%%" % level)
        self._save()

    # ------------------------------------------------------------------------------------------------------------------- preview --
    def _away_preview_clicked(self, short):
        job = self._away_jobs.pop(short, None)
        if job is not None:              # the second click = cancel NOW
            job["timer"].cancel()
            self._away_expiry(short, job["rec"], manual=True)
            return
        r = self._away_rows.get(short)
        if r is None:
            return
        rec = self.monitor._away_apply_row(
            {"short": short, "gdi": r["gdi"], **self._away_rect(short)},
            self._away_row_blackout(short), self._away_level())
        self._away_says[short] = rec["status"]
        if rec["status"].startswith("blackout"):
            self._away_rise(True)        # the dialog above the paint
        timer = threading.Timer(10.0, lambda: self._away_expiry(short, rec))
        timer.daemon = True              # a quit with a live preview must
        timer.start()                    # never hang the process 10 s
        self._away_jobs[short] = {"timer": timer, "rec": rec}
        set_text(r["preview"], "cancel")
        self._away_say(short)

    def _away_rect(self, short):
        for m in wm.monitors():
            if m["short"] == short:
                return {"x": m["x"], "y": m["y"],
                        "w": m["w"], "h": m["h"]}
        return {"x": 0, "y": 0, "w": 800, "h": 600}

    def _away_expiry(self, short, rec, manual=False):
        # the revert call rides the engine's law, on the timer thread
        try:
            verdict = self.monitor._away_release(short, rec)
        except Exception:
            log.debug("away: the preview revert failed", exc_info=True)
            return
        try:
            self.after(0, lambda: self._away_done(short, rec, verdict,
                                                  manual))
        except Exception:
            pass                          # window closed while reverting

    def _away_done(self, short, rec, verdict, manual):
        self._away_jobs.pop(short, None)
        self._away_rise(False)
        r = self._away_rows.get(short)
        if r is not None:
            set_text(r["preview"], "preview")
        if verdict == "adopted":
            self._away_says[short] = "away for real now"
        elif manual:
            self._away_says[short] = "preview cancelled"
        else:
            self._away_says[short] = ""
        self._away_say(short)

    def _away_rise(self, above):
        """Cross-interpreter transient(): the settings window lifts
        OVER its own blackout preview and drops back after. Topmost
        for the duration only - the window never camped there."""
        try:
            self.attributes("-topmost", bool(above))
            if above:
                self.lift()
            else:
                self.attributes("-topmost", False)
        except Exception:
            pass                          # gone mid-preview: fine

    # ------------------------------------------------------------------ paint --
    def _away_sync(self):
        """Visibility under one rule: the rows always render, the mode
        decides whether they SPEAK. Where the tab has the consent
        band (reskin wave), that walker owns the gray - including the
        wheel-swap the owner's UAT demanded, so enabling goes through
        _gate_widgets, never a bare state=: a mode pick must not
        unlock a consent-greyed card, so dim mode only enables while
        consent stands. Without a band (older trees) the card owns its
        own disable pass, the packet's law. Slider visibility follows
        the row's own sub-mode exactly like the detection card's mode
        rows."""
        band = getattr(self, "_consent_band", None)
        consent = True if band is None else \
            bool(self.cfg["camera"].get("enabled"))
        dim = consent and \
            (self.cfg.get("away") or {}).get("mode") == "dim"
        for short, r in self._away_rows.items():
            state = "normal" if dim else "disabled"
            gated = False
            if band is not None and hasattr(self, "_gate_widgets"):
                try:
                    self._gate_widgets(r["row"], state)
                    gated = True
                except Exception:
                    pass
            if not gated:
                for key in ("seg", "slider", "preview"):
                    try:
                        r[key].configure(state=state)
                    except Exception:
                        pass
            if self._away_row_blackout(short):
                r["slider"].grid_forget()
                r["value"].grid_forget()
            elif dim:
                r["slider"].grid(row=0, column=2, sticky="e")
                r["value"].grid(row=0, column=3, sticky="e",
                                padx=(6, 0))
            self._away_say(short)

    def _away_say(self, short):
        """The confession surface: the engine's live status word wins
        over the last preview's word (a real spell outranks a test)."""
        r = self._away_rows.get(short)
        if r is None:
            return
        live = (getattr(self.monitor, "away_status", None) or {}).get(short)
        text = live if live else self._away_says.get(short, "")
        set_text(r["say"], text)

    def _away_poll(self):
        """The row status words follow the engine while the card is
        alive - the refusal of a real spell surfaces here, not only in
        the log. 900 ms, self-rescheduling, diff-guarded (set_text)."""
        try:
            if getattr(self, "_dying", False):
                return
            for short in self._away_rows:
                self._away_say(short)
        except Exception:
            log.debug("away poll failed", exc_info=True)
        try:
            self.after(900, self._away_poll)
        except Exception:
            pass                          # destroyed mid-tick
