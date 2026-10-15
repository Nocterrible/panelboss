"""The OLED tab, leg one: the faux taskbar hider's card.

Burn-in is the OLED problem and pixels sitting still are its cause, so
this tab owns the features that keep any given pixel from aging in
place. Leg one ships the taskbar strip; the per-window dimming follows.

The law this card obeys is the default-off law: nothing paints until
the user opts in, twice - once for the hider, once per monitor. And
the honesty law: the conflict line reports what the desk says about
Windows' own auto-hide (a fixed sentence, once per build), and the TIP
owns the strip's one weakness instead of hiding it - the strip covers
the bar without informing apps that queried the work area, so a
fullscreen may slip behind it.
"""

import logging

import customtkinter as ctk

from ... import hider, jog, wm
from ...config import HOLD_SEC_CEIL, HOLD_SEC_FLOOR, HOLD_SEC_DEFAULT
from ...config import (JOG_CYCLE_CEIL, JOG_CYCLE_DEFAULT,
                   JOG_CYCLE_FLOOR, JOG_STEP_CEIL,
                   JOG_STEP_DEFAULT, JOG_STEP_FLOOR)
from .. import theme
from ._widgets import set_text

log = logging.getLogger("ui.oled")

# label->word map, pinned against drift the same lesson taught at the
# away preview seam: the menu answers with LABELS, the config stores
# WORDS, and the belt between them names itself on a miss.
REVEAL_BY_LABEL = {"hovered only": "hovered", "every bar": "all"}
LABEL_BY_REVEAL = {w: s for s, w in REVEAL_BY_LABEL.items()}

TIP_JO = {
    "on": "static content is what ages an OLED unevenly - the bar "
          "that never moves prints itself in over months. micro-jog "
          "nudges the app covers around a small zero-drift ring on "
          "a timer, so no edge of glass ages permanently; the wash "
          "briefly lights the whole panel to even out what retention "
          "has already begun. the app cannot read your panel wear "
          "counters (the one register this desk ever answered was "
          "caught lying) - this is prevention, not a diagnosis.",
    "row": "jog covers on THIS monitor only (the same opt-in law as "
           "the taskbar strip: burn-in is the OLED problem).",
    "mode": "micro-jog moves the covers a few pixels every cycle. "
            "pixel wash is the button below - it never happens on its "
            "own, by law: a wash is a request, not a schedule.",
    "step": "how far the covers travel around the ring, in pixels - "
            "1..8; the ring returns to rest, so the travel never "
            "accumulates.",
    "cycle": "how often the ring steps: minutes between nudges.",
    "wash": "lights this monitor white for ten seconds, once. the "
            "first opted-in monitor answers the button; if none are "
            "opted in, the word beside the button says so - nothing "
            "is silent.",
}

TIP = {
    "on": "the taskbar is a fixed row of pixels that never moves - on "
          "an OLED, pixels that never move age unevenly and the bar "
          "eventually prints itself into the glass. this strip paints "
          "over the bar and steps aside for the cursor, so the pixels "
          "rest and the bar works when reached for. nothing changes "
          "here until you opt in, and nothing breaks if you never do: "
          "the strip is an ordinary window, and windows die with their "
          "app.",
    "row": "one strip per bar on THIS monitor. the opt-in is per "
           "monitor on purpose: burn-in is the OLED problem - a panel "
           "that cannot burn in has no reason to wear the strip.",
    "reveal": "'hovered only' bars the bar you actually reached for. "
              "'every bar' bares them all together the moment you "
              "reach for any one - the honest shape for a desk whose "
              "apps live on more screens than the one under the hand. "
              "returns stay per-bar timers either way.",
    "hold": "how long the cursor must stay clear of every bar before "
            "a withdrawn strip covers up again. typing holds it: while "
            "the caret sits in the search box the strip waits, "
            "counting its seconds only after the typing stops.",
    "conflict": "windows' own per-bar auto-hide is switched on for "
                "this desk. the strip covers the bar either way, so "
                "the two hiders may double-hide - the taskbar will "
                "still come back for the cursor, and the strip "
                "follows it.",
}


class _OledMixin:
    # ------------------------------------------------------------------ oled --
    def _build_oled(self, parent):
        box = self._card(parent, "taskbar hider",
                         "a painted strip that keeps the bar's pixels "
                         "from aging in place")
        self._oled_box = box
        row = self._row(box, "taskbar hider", TIP["on"], hint_chars=42)
        self.oled_on_box = ctk.CTkCheckBox(
            row, text="cover the bars", command=self._oled_on_changed,
            font=self.skin.font(12), checkbox_width=18, checkbox_height=18,
            border_color=self.skin.border_raised,
            fg_color=self.skin.accent, hover_color=self.skin.accent,
            text_color=self.skin.text, text_color_disabled=self.skin.txt3)
        self.oled_on_box.set(bool((self.cfg.get("hider") or {}).get("on")))
        self.oled_on_box.grid(row=0, column=1, sticky="e")

        # one opt-in row per live panel (the away card's idiom, dupes
        # disambiguated by the gdi slot the rows already carry)
        self._oled_rows = {}
        hid = self.cfg.setdefault("hider", {})
        base = [m.get("short") or m.get("id") for m in wm.monitors()]
        dupes = {b for b in base if base.count(b) > 1}
        for m, short in zip(wm.monitors(), base):
            label = short
            if short in dupes:
                label = "%s (%s)" % (
                    short, str(m.get("gdi") or "").rsplit("DISPLAY", 1)
                    [-1] or "?")
            row = self._row(box, label, TIP["row"], hint_chars=42)
            box2 = ctk.CTkCheckBox(
                row, text="strip", command=lambda s=short: self._oled_row_changed(s),
                font=self.skin.font(12), checkbox_width=18, checkbox_height=18,
                border_color=self.skin.border_raised,
                fg_color=self.skin.accent, hover_color=self.skin.accent,
                text_color=self.skin.text, text_color_disabled=self.skin.txt3)
            box2.set(bool((hid.get("monitors") or {}).get(short)))
            box2.grid(row=0, column=1, sticky="e")
            self._oled_rows[short] = box2

        row = self._row(box, "reveal", TIP["reveal"], hint_chars=42)
        self.oled_reveal_button = ctk.CTkSegmentedButton(
            row, values=list(REVEAL_BY_LABEL), height=26, width=190,
            command=self._oled_reveal_changed,
            **self.skin.segmented_style())
        stored = hid.get("reveal", "hovered")
        self.oled_reveal_button.set(LABEL_BY_REVEAL.get(stored, "hovered only"))
        self.oled_reveal_button.grid(row=0, column=1, sticky="e")

        row = self._row(box, "return after", TIP["hold"], hint_chars=42)
        self.oled_hold_label = ctk.CTkLabel(row, font=self.skin.font(12),
                                            **self.skin.text_style("sub"))
        slider = ctk.CTkSlider(row, from_=HOLD_SEC_FLOOR, to=HOLD_SEC_CEIL,
                               number_of_steps=HOLD_SEC_CEIL - HOLD_SEC_FLOOR,
                               width=180, command=self._oled_hold_changed,
                               **self.skin.slider_style())
        slider.set(int(hid.get("hold_sec", HOLD_SEC_DEFAULT)))
        slider.grid(row=0, column=1, sticky="e")
        self.oled_hold_label.configure(
            text="%ss" % int(hid.get("hold_sec", HOLD_SEC_DEFAULT)))
        self.oled_hold_label.grid(row=0, column=2, sticky="e",
                                  padx=(theme.S_FIELD, 0))

        # the conflict line: the desk's own auto-hide, confessed once
        # per build, on its own row so the card's pack law holds
        srow = self._row(box, " ", TIP["conflict"], hint_chars=42)
        self.oled_say = ctk.CTkLabel(srow, font=self.skin.font(11),
                                     wraplength=420, justify="left",
                                     anchor="w",
                                     **self.skin.text_style("sub"))
        self.oled_say.grid(row=0, column=1, sticky="e")
        self._oled_host = parent
        self._build_refresh(self._oled_host)   # second card, same tab
        self._oled_sync()

    # ------------------------------------------------------- refresh --
    JOG_BY_LABEL = {"move pixels": "shuffle", "wash pixels": "wash"}

    def _build_refresh(self, parent):
        box = self._card(parent, "panel refresh",
                         "micro-jog moves the covers a few pixels; a "
                         "wash briefly lights the panel")
        row = self._row(box, "panel refresh", TIP_JO["on"], hint_chars=42)
        self.oled_jog_box = ctk.CTkCheckBox(
            row, text="arm the refresh", command=self._oled_jog_changed,
            font=self.skin.font(12), checkbox_width=18, checkbox_height=18,
            border_color=self.skin.border_raised,
            fg_color=self.skin.accent, hover_color=self.skin.accent,
            text_color=self.skin.text, text_color_disabled=self.skin.txt3)
        self.oled_jog_box.set(bool((self.cfg.get("jog") or {}).get("on")))
        self.oled_jog_box.grid(row=0, column=1, sticky="e")

        self._jog_rows = {}
        jog_cfg = self.cfg.setdefault("jog", {})
        base = [m.get("short") or m.get("id") for m in wm.monitors()]
        dupes = {b for b in base if base.count(b) > 1}
        for m, short in zip(wm.monitors(), base):
            label = short
            if short in dupes:
                label = "%s (%s)" % (
                    short, str(m.get("gdi") or "").rsplit("DISPLAY", 1)
                    [-1] or "?")
            row = self._row(box, label, TIP_JO["row"], hint_chars=42)
            box2 = ctk.CTkCheckBox(
                row, text="jog",
                command=lambda s=short: self._oled_jog_row_changed(s),
                font=self.skin.font(12), checkbox_width=18,
                checkbox_height=18,
                border_color=self.skin.border_raised,
                fg_color=self.skin.accent, hover_color=self.skin.accent,
                text_color=self.skin.text, text_color_disabled=self.skin.txt3)
            box2.set(bool((jog_cfg.get("monitors") or {}).get(short)))
            box2.grid(row=0, column=1, sticky="e")
            self._jog_rows[short] = box2

        row = self._row(box, "refresh mode", TIP_JO["mode"], hint_chars=42)
        self.oled_jog_mode = ctk.CTkSegmentedButton(
            row, values=list(self.JOG_BY_LABEL), height=26, width=190,
            command=self._oled_jog_mode_changed,
            **self.skin.segmented_style())
        self.oled_jog_mode.set(self.JOG_BY_LABEL.get(
            jog_cfg.get("mode", "shuffle"), "move pixels"))
        self.oled_jog_mode.grid(row=0, column=1, sticky="e")

        row = self._row(box, "jog step", TIP_JO["step"], hint_chars=42)
        self.oled_step_label = ctk.CTkLabel(row, font=self.skin.font(12),
                                            **self.skin.text_style("sub"))
        slider = ctk.CTkSlider(row, from_=JOG_STEP_FLOOR, to=JOG_STEP_CEIL,
                               number_of_steps=JOG_STEP_CEIL
                                               - JOG_STEP_FLOOR,
                               width=180, command=self._oled_step_changed,
                               **self.skin.slider_style())
        slider.set(int(jog_cfg.get("step_px", JOG_STEP_DEFAULT)))
        slider.grid(row=0, column=1, sticky="e")
        self.oled_step_label.configure(
            text="%s px" % int(jog_cfg.get("step_px", JOG_STEP_DEFAULT)))
        self.oled_step_label.grid(row=0, column=2, sticky="e",
                                  padx=(theme.S_FIELD, 0))

        row = self._row(box, "every", TIP_JO["cycle"], hint_chars=42)
        self.oled_cycle_label = ctk.CTkLabel(row, font=self.skin.font(12),
                                             **self.skin.text_style("sub"))
        slider = ctk.CTkSlider(row, from_=JOG_CYCLE_FLOOR,
                               to=JOG_CYCLE_CEIL,
                               number_of_steps=(JOG_CYCLE_CEIL
                                                - JOG_CYCLE_FLOOR) // 5,
                               width=180, command=self._oled_cycle_changed,
                               **self.skin.slider_style())
        slider.set(int(jog_cfg.get("cycle_min", JOG_CYCLE_DEFAULT)))
        slider.grid(row=0, column=1, sticky="e")
        self.oled_cycle_label.configure(
            text="%s min" % int(jog_cfg.get("cycle_min",
                                            JOG_CYCLE_DEFAULT)))
        self.oled_cycle_label.grid(row=0, column=2, sticky="e",
                                   padx=(theme.S_FIELD, 0))

        row = self._row(box, "pixel wash", TIP_JO["wash"], hint_chars=42)
        self.oled_wash_btn = ctk.CTkButton(
            row, text="run wash now", height=26, width=120,
            command=self._oled_wash_now, **self.skin.secondary())
        self.oled_wash_btn.grid(row=0, column=1, sticky="e")
        self.oled_say2 = ctk.CTkLabel(row, font=self.skin.font(11),
                                      wraplength=200, justify="left",
                                      anchor="e",
                                      **self.skin.text_style("sub"))
        self.oled_say2.grid(row=0, column=2, sticky="e",
                            padx=(theme.S_FIELD, 0))

    def _oled_jog_changed(self):
        self.cfg.setdefault("jog", {})["on"] = bool(
            self.oled_jog_box.get())
        self._save()

    def _oled_jog_row_changed(self, short):
        box = self._jog_rows.get(short)
        if box is None:
            return
        self.cfg.setdefault("jog", {}).setdefault("monitors", {})[short] = \
            bool(box.get())
        self._save()

    def _oled_jog_mode_changed(self, label):
        word = self.JOG_BY_LABEL.get(label)
        if word is None:                     # the word-seam belt again
            log.warning("oled refresh choice %r is not in the map; "
                        "move pixels stands", label)
            word = "shuffle"
        self.cfg.setdefault("jog", {})["mode"] = word
        self._save()

    def _oled_step_changed(self, value):
        self.cfg.setdefault("jog", {})["step_px"] = int(round(value))
        self.oled_step_label.configure(text="%s px" % round(value))
        self._save()

    def _oled_cycle_changed(self, value):
        self.cfg.setdefault("jog", {})["cycle_min"] = int(round(value))
        self.oled_cycle_label.configure(text="%s min" % round(value))
        self._save()

    def _oled_wash_now(self):
        # every opted-in monitor lights, in row order (owner UAT: the
        # dict's first key is not the user's whole set)
        set_text(self.oled_say2, jog.wash_all(self.cfg))

    def _oled_sync(self):
        if getattr(self, "oled_say", None) is None:
            return
        try:
            self.conflict_visible = bool(hider.autohide())
        except Exception:
            self.conflict_visible = False
        on = bool(self.oled_on_box.get()) and self.conflict_visible
        set_text(self.oled_say, TIP["conflict"] if on else " ")

    # handlers: the write-is-applying law, straight from the timers card
    def _oled_on_changed(self):
        self.cfg.setdefault("hider", {})["on"] = bool(self.oled_on_box.get())
        self._oled_sync()
        self._save()

    def _oled_row_changed(self, short):
        box = self._oled_rows.get(short)
        if box is None:
            return
        self.cfg.setdefault("hider", {}).setdefault("monitors", {})[short] = \
            bool(box.get())
        self._save()

    def _oled_reveal_changed(self, label):
        word = REVEAL_BY_LABEL.get(label)
        if word is None:
            # the belt: a menu value the map never heard of names
            # itself instead of silently selecting a leg (the word-seam
            # lesson, applied on the way in this time)
            log.warning("oled reveal choice %r is not in the map; "
                        "hovered only stands", label)
            word = "hovered"
        self.cfg.setdefault("hider", {})["reveal"] = word
        self._save()

    def _oled_hold_changed(self, value):
        self.cfg.setdefault("hider", {})["hold_sec"] = int(round(value))
        self.oled_hold_label.configure(text="%ss" % round(value))
        self._save()
