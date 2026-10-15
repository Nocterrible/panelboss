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

from ... import dimmer, hider, jog, wm
from ...config import (DIMMER_IDLE_CEIL, DIMMER_IDLE_DEFAULT,
                       DIMMER_IDLE_FLOOR, DIMMER_LEVEL_CEIL,
                       DIMMER_LEVEL_DEFAULT, DIMMER_LEVEL_FLOOR,
                       DIMMER_RAMP_CEIL, DIMMER_RAMP_DEFAULT,
                       DIMMER_RAMP_FLOOR)
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


TIP_DIM = {
    "on": "an idle desk puts a dark click-through veil over every "
          "window you are not using: the still ones dim, the one you "
          "touch lights up instantly, and anything the sound sensor "
          "hears stays bright - a video that just went quiet keeps "
          "its brightness for four honest seconds before the veil "
          "may return. nothing dims until you opt in, per monitor.",
    "row": "dim veils on THIS monitor only (the opt-in law, shared "
           "with the strip and the refresh).",
    "idle": "how still the input must be before the veils land.",
    "ramp": "how long the fade takes once input returns: the veils "
            "step down at most three times and are gone - a dimmer "
            "that blinks off is a screensaver.",
    "level": "how dark the veils are, in percent.",
    "apps": "apps that never wear a veil, by exe file name as the "
            "title bar shows it (chrome.exe). the exclusion is "
            "yours, per app; it edits here, in the card.",
    "key": "press a key to bind the pause toggle, esc clears it. no "
           "chord is stolen before you give one: the app registers "
           "the hotkey only while the window's pump lives, a binding "
           "while headless answers with a word and retries once the "
           "pump is back, a taken combo keeps its predecessor and "
           "says so, dated. one press pauses, one resumes.",
    "pause": "pause the dimmer without touching its settings: the "
             "field fades out within the ramp and returns the tick "
             "the pause lifts.",
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
        self._build_dimmer(parent)       # third card, same tab

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

    # ------------------------------------------------------------------
    # third card: the background dimmer. The capture seam is honest:
    # the button arms a pending flag, the ONE <KeyPress> the all-tag
    # routes while it stands becomes the binding (esc clears it), and
    # the module does the actual RegisterHotKey against the watcher's
    # pump - the say row carries the confession (taken / no pump yet),
    # never a silent lie.
    # ------------------------------------------------------------------
    _DIM_BIND_TXT = "press a key to bind (esc clears)"

    def _build_dimmer(self, parent):
        box = self._card(parent, "background dimmer",
                         "an idle desk dims the windows you are not "
                         "using; touch or sound lifts a veil at once")
        row = self._row(box, "background dimmer", TIP_DIM["on"],
                        hint_chars=42)
        self.oled_dim_box = ctk.CTkCheckBox(
            row, text="arm the dimmer", command=self._oled_dim_changed,
            font=self.skin.font(12), checkbox_width=18,
            checkbox_height=18, border_color=self.skin.border_raised,
            fg_color=self.skin.accent, hover_color=self.skin.accent,
            text_color=self.skin.text,
            text_color_disabled=self.skin.txt3)
        self.oled_dim_box.set(bool((self.cfg.get("dimmer") or {})
                                   .get("on")))
        self.oled_dim_box.grid(row=0, column=1, sticky="e")

        self._dim_rows = {}
        dim = self.cfg.setdefault("dimmer", {})
        base = [m.get("short") or m.get("id") for m in wm.monitors()]
        dupes = {b for b in base if base.count(b) > 1}
        for m, short in zip(wm.monitors(), base):
            label = short
            if short in dupes:
                label = "%s (%s)" % (
                    short, str(m.get("gdi") or "").rsplit("DISPLAY", 1)
                    [-1] or "?")
            row = self._row(box, label, TIP_DIM["row"], hint_chars=42)
            box2 = ctk.CTkCheckBox(
                row, text="dim",
                command=lambda s=short: self._oled_dim_row_changed(s),
                font=self.skin.font(12), checkbox_width=18,
                checkbox_height=18,
                border_color=self.skin.border_raised,
                fg_color=self.skin.accent, hover_color=self.skin.accent,
                text_color=self.skin.text,
                text_color_disabled=self.skin.txt3)
            box2.set(bool((dim.get("monitors") or {}).get(short)))
            box2.grid(row=0, column=1, sticky="e")
            self._dim_rows[short] = box2

        row = self._row(box, "dim after", TIP_DIM["idle"],
                        hint_chars=42)
        self.oled_idle_label = ctk.CTkLabel(row, font=self.skin.font(12),
                                            **self.skin.text_style("sub"))
        slider = ctk.CTkSlider(row, from_=DIMMER_IDLE_FLOOR,
                               to=DIMMER_IDLE_CEIL,
                               number_of_steps=(DIMMER_IDLE_CEIL
                                                - DIMMER_IDLE_FLOOR) // 60,
                               width=180, command=self._oled_idle_changed,
                               **self.skin.slider_style())
        slider.set(int(dim.get("idle_sec", DIMMER_IDLE_DEFAULT)))
        slider.grid(row=0, column=1, sticky="e")
        self.oled_idle_label.configure(
            text="%s s" % int(dim.get("idle_sec", DIMMER_IDLE_DEFAULT)))
        self.oled_idle_label.grid(row=0, column=2, sticky="e",
                                  padx=(theme.S_FIELD, 0))

        row = self._row(box, "fade within", TIP_DIM["ramp"],
                        hint_chars=42)
        self.oled_ramp_label = ctk.CTkLabel(row, font=self.skin.font(12),
                                            **self.skin.text_style("sub"))
        slider = ctk.CTkSlider(row, from_=DIMMER_RAMP_FLOOR,
                               to=DIMMER_RAMP_CEIL,
                               number_of_steps=DIMMER_RAMP_CEIL
                                               - DIMMER_RAMP_FLOOR,
                               width=180, command=self._oled_ramp_changed,
                               **self.skin.slider_style())
        slider.set(int(dim.get("ramp_sec", DIMMER_RAMP_DEFAULT)))
        slider.grid(row=0, column=1, sticky="e")
        self.oled_ramp_label.configure(
            text="%s s" % int(dim.get("ramp_sec", DIMMER_RAMP_DEFAULT)))
        self.oled_ramp_label.grid(row=0, column=2, sticky="e",
                                  padx=(theme.S_FIELD, 0))

        row = self._row(box, "veil level", TIP_DIM["level"],
                        hint_chars=42)
        self.oled_level_label = ctk.CTkLabel(row, font=self.skin.font(12),
                                             **self.skin.text_style("sub"))
        slider = ctk.CTkSlider(row, from_=DIMMER_LEVEL_FLOOR,
                               to=DIMMER_LEVEL_CEIL,
                               number_of_steps=DIMMER_LEVEL_CEIL
                                               - DIMMER_LEVEL_FLOOR,
                               width=180, command=self._oled_level_changed,
                               **self.skin.slider_style())
        slider.set(int(dim.get("level", DIMMER_LEVEL_DEFAULT)))
        slider.grid(row=0, column=1, sticky="e")
        self.oled_level_label.configure(
            text="%s%%" % int(dim.get("level", DIMMER_LEVEL_DEFAULT)))
        self.oled_level_label.grid(row=0, column=2, sticky="e",
                                   padx=(theme.S_FIELD, 0))

        # the exclusion editor, IN the card (one flow, no dialog): the
        # entry, the add, and the stored names each with a small
        # remove - the profiles card's row idiom
        row = self._row(box, "never dim", TIP_DIM["apps"], hint_chars=42)
        self.dim_app_entry = ctk.CTkEntry(
            row, width=150, font=self.skin.font(12),
            placeholder_text="chrome.exe",
            fg_color=self.skin.field_bg, border_width=1,
            border_color=self.skin.border_raised,
            corner_radius=self.skin.radius)
        self.dim_app_entry.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(row, text="exclude", height=26, width=80,
                      command=self._oled_dim_app_add,
                      **self.skin.secondary()).grid(
            row=0, column=2, sticky="e", padx=(theme.S_FIELD, 0))
        row = self._row(box, "excluded", TIP_DIM["apps"], hint_chars=42)
        self._dim_apps_box = ctk.CTkFrame(row, fg_color="transparent")
        self._dim_apps_box.grid(row=0, column=1, columnspan=2, sticky="e")
        self._dim_apps_repaint()

        row = self._row(box, "pause hotkey", TIP_DIM["key"],
                        hint_chars=42)
        self.oled_bind_btn = ctk.CTkButton(
            row, text=self._DIM_BIND_TXT, height=26, width=220,
            command=self._oled_dim_bind, **self.skin.secondary())
        self.oled_bind_btn.grid(row=0, column=1, sticky="e")
        self.oled_say3 = ctk.CTkLabel(row, font=self.skin.font(11),
                                      wraplength=200, justify="left",
                                      anchor="e",
                                      **self.skin.text_style("sub"))
        self.oled_say3.grid(row=0, column=2, sticky="e",
                            padx=(theme.S_FIELD, 0))

        row = self._row(box, "pause", TIP_DIM["pause"], hint_chars=42)
        self.oled_pause_box = ctk.CTkCheckBox(
            row, text="pause dimming", command=self._oled_pause_changed,
            font=self.skin.font(12), checkbox_width=18,
            checkbox_height=18, border_color=self.skin.border_raised,
            fg_color=self.skin.accent, hover_color=self.skin.accent,
            text_color=self.skin.text,
            text_color_disabled=self.skin.txt3)
        self.oled_pause_box.set(dimmer.paused())
        self.oled_pause_box.grid(row=0, column=1, sticky="e")
        self._dim_words()
        self.after(1000, self._dim_poll)

    def _dim_poll(self):
        """The confession and the pause switch follow the engine
        while the card is alive - a taken combo answered AFTER the
        capture (the arm speaks on a later beat than the click)
        surfaces here, not only in the log. 1000 ms,
        self-rescheduling, diff-guarded (set_text): the away card's
        _away_poll idiom, verbatim."""
        try:
            if getattr(self, "_dying", False):
                return
            self._dim_words()
            self.oled_pause_box.set(dimmer.paused())
        except Exception:
            log.debug("dimmer poll failed", exc_info=True)
        try:
            self.after(1000, self._dim_poll)
        except Exception:
            pass                          # destroyed mid-tick

    def _oled_dim_changed(self):
        self.cfg.setdefault("dimmer", {})["on"] = bool(
            self.oled_dim_box.get())
        self._save()

    def _oled_dim_row_changed(self, short):
        box = self._dim_rows.get(short)
        if box is None:
            return
        self.cfg.setdefault("dimmer", {}).setdefault("monitors", {})[short] \
            = bool(box.get())
        self._save()

    def _oled_idle_changed(self, value):
        self.cfg.setdefault("dimmer", {})["idle_sec"] = int(round(value))
        self.oled_idle_label.configure(text="%s s" % round(value))
        self._save()

    def _oled_ramp_changed(self, value):
        self.cfg.setdefault("dimmer", {})["ramp_sec"] = int(round(value))
        self.oled_ramp_label.configure(text="%s s" % round(value))
        self._save()

    def _oled_level_changed(self, value):
        self.cfg.setdefault("dimmer", {})["level"] = int(round(value))
        self.oled_level_label.configure(text="%s%%" % round(value))
        self._save()

    def _oled_dim_app_add(self):
        name = (self.dim_app_entry.get() or "").strip().lower()
        if not name:
            set_text(self.oled_say3, "the entry was empty - nothing "
                                     "was excluded")
            return
        self.cfg.setdefault("dimmer", {}).setdefault(
            "apps", {})[name] = True
        self.dim_app_entry.delete(0, "end")
        self._dim_apps_repaint()
        self._save()

    def _oled_dim_app_rm(self, name):
        apps = self.cfg.setdefault("dimmer", {}).get("apps") or {}
        if apps.pop(name, None) is None:
            return
        self._dim_apps_repaint()
        self._save()

    def _dim_apps_repaint(self):
        for c in self._dim_apps_box.winfo_children():
            c.destroy()
        apps = (self.cfg.get("dimmer") or {}).get("apps") or {}
        for name in sorted(apps):
            line = ctk.CTkFrame(self._dim_apps_box, fg_color="transparent")
            line.pack(fill="x")
            ctk.CTkLabel(line, text=name, font=self.skin.font(11),
                         **self.skin.text_style("sub")).pack(
                side="left", padx=(theme.S_FIELD, 0))
            ctk.CTkButton(line, text="remove", height=22, width=64,
                          command=lambda n=name: self._oled_dim_app_rm(n),
                          **self.skin.secondary()).pack(
                side="right", padx=theme.S_FIELD // 2)

    def _oled_dim_bind(self):
        if getattr(self, "_dim_pending", False):
            self._oled_dim_disarm()
            return
        self._dim_pending = True
        self.bind_all("<KeyPress>", self._oled_dim_capture)
        # the cancel on walking away: while the capture flag stands,
        # the window losing focus (an alt+tab, a click on another app)
        # disarms it - a pending capture that outlives the intent is
        # the stolen-keystroke class of bug
        self.bind("<FocusOut>", self._oled_dim_focus_out)
        self.oled_bind_btn.configure(text="press a key now")

    def _oled_dim_disarm(self):
        self._dim_pending = False
        self.unbind_all("<KeyPress>")
        self.unbind("<FocusOut>")
        self.oled_bind_btn.configure(text=self._DIM_BIND_TXT)

    def _oled_dim_focus_out(self, _event=None):
        if getattr(self, "_dim_pending", False):
            self._oled_dim_disarm()

    def _oled_dim_capture(self, event):
        if not getattr(self, "_dim_pending", False):
            return
        self._oled_dim_disarm()
        dim = self.cfg.setdefault("dimmer", {})
        if event.keysym == "Escape":
            dim["bound"] = None
            set_text(self.oled_say3, "unbound")
            self._save()
            return
        # the bare-key rule lives in the module (capture_word) so the
        # suite can drive it with fake events: a letter is typed, not
        # stolen, and the OLD binding stands
        pair, word = dimmer.capture_word(event.state, event.keycode)
        if word:
            set_text(self.oled_say3, word)
            return
        dim["bound"] = pair
        self._save()
        self._dim_words()

    def _dim_words(self):
        note = dimmer.bind_note()
        if note:
            set_text(self.oled_say3, note)      # the dated refusal
        elif dimmer.bound_live():
            set_text(self.oled_say3, "live - one press pauses")
        elif (self.cfg.get("dimmer") or {}).get("bound"):
            set_text(self.oled_say3, "stored - the loop answers "
                                     "next beat")
        else:
            set_text(self.oled_say3, "unbound - nothing is stolen "
                                     "from your desk")

    def _oled_pause_changed(self):
        dimmer.set_paused(bool(self.oled_pause_box.get()))
