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
import re
import threading

import tkinter as tk
import customtkinter as ctk

from ... import companion, dimmer, hider, jog, wm, nmhost
from ...config import (DIMMER_IDLE_CEIL, DIMMER_IDLE_DEFAULT,
                       DIMMER_IDLE_FLOOR, DIMMER_LEVEL_CEIL,
                       DIMMER_LEVEL_DEFAULT, DIMMER_LEVEL_FLOOR,
                       DIMMER_RAMP_CEIL, DIMMER_RAMP_DEFAULT,
                       DIMMER_RAMP_FLOOR)
from ...config import (VIDEODIM_IDLE_CEIL, VIDEODIM_IDLE_DEFAULT,
                       VIDEODIM_IDLE_FLOOR, VIDEODIM_LEVEL_CEIL,
                       VIDEODIM_LEVEL_DEFAULT, VIDEODIM_LEVEL_FLOOR)
from ...config import HOLD_SEC_CEIL, HOLD_SEC_FLOOR, HOLD_SEC_DEFAULT
from ...config import (JOG_CYCLE_CEIL, JOG_CYCLE_DEFAULT,
                   JOG_CYCLE_FLOOR, JOG_STEP_CEIL,
                   JOG_STEP_DEFAULT, JOG_STEP_FLOOR)
from .. import theme
from ._widgets import desk_position, set_text

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
          "may return. nothing dims until you opt in, per monitor. "
          "WINDOWS THAT RUN AS ADMINISTRATOR (Task Manager's class) "
          "stay bright: a non-admin app's veil cannot guarantee its "
          "place in the stacking order next to an elevated window, "
          "and a veil that slips a band too high dims the app ABOVE "
          "its target - the double veil you saw on Task Manager. The "
          "veil does reach those windows if this app itself runs as "
          "administrator - not recommended: the elevation then "
          "inherits into everything the tray launches, and the "
          "exemptions that spare your menus get weaker, not "
          "stronger, from on high.",
    "row": "dim veils on THIS monitor only (the opt-in law, shared "
           "with the strip and the refresh).",
    "always": "dim this panel WITHOUT the idle wait: the veils land "
              "the moment the focus leaves the panel, and lift when "
              "it returns - the one you are using never dims. the "
              "sound exemption and the pause ride here too; only "
              "the idle countdown is skipped. an opt-in sub-mode, "
              "exactly like the strip's reveal scope: a panel that "
              "never opted in never dims by itself.",
    "idle": "how still the input must be before the veils land.",
    "ramp": "how long the fade takes once input returns: the veils "
            "step down at most three times and are gone - a dimmer "
            "that blinks off is a screensaver. at zero the blink is "
            "the choice: the drop is immediate.",
    "level": "how dark the veils are, in percent.",
    "row_level": "this panel's OWN veil percent. panels answer "
                 "differently - the same number goes DARK on one and "
                 "is barely a tint on another - so a panel with a row "
                 "here ignores the global \"veil level\". the slider "
                 "opens at the global; the first move stores this "
                 "panel's number, and only this panel's.",
    "lift_fade": "when off (the default), the veil drops the instant "
                 "you touch the desk - no lift ceremony; the \"fade "
                 "within\" ramp applies to the plain veils only when "
                 "this is on. the theater frame has its own twin "
                 "switch on its card.",
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


TIP_COMP = {
    "on": "arm movie theater mode: a desk still for the \"veil after\" "
          "wait dims everything but the PLAYING video - the frame lands "
          "around the rect and the browser's chrome dims with it. off "
          "is the root law: no file is read, nothing happens. the eye "
          "learns the video's place from the buddy extension's native "
          "host: no flag, no port, no debugger.",
    "status": "live words: the consent rail and the buddy "
              "extension's last push, refreshed on the dimmer's "
              "own beat. the test-the-geometry answer lands here "
              "too. a missing answer reads as words, never a crash.",
    "veil": "test the geometry: measure the video on the clicked tab "
            "right now, one shot, no waiting on the idle rail. this "
            "is the calibration/test gesture - the FEATURE is the "
            "automatic lane (playing AND still), not this button.",
    "path": "the doorway the extension's native host writes: the "
            "app's own folder, a fixed path, every browser, every "
            "download config. the extension's id is the only ACL - "
            "no pairing, no token; the browser's install check is "
            "the whole handshake. install the host once (see the "
            "extension's README) - the one-click helper install "
            "rides this row: it runs the same script the README "
            "documents.",
    "install": "install the buddy's helper in one click: builds "
               "panelboss-host.exe (PyInstaller, ~40 s), registers "
               "it under HKCU, and tells the app where it lives. "
               "the entry is an optional id override - paste the "
               "32-char id from the browser's extensions page; "
               "empty derives it from the extension's own path. "
               "a bad shape answers a word and does NOT fire the "
               "installer. the manual route stays one line down: "
               "extension\\host\\install_host.ps1.",
    "caps": "what the buddy's API CAN send, read from the host "
            "itself (the open-API ruling: discover, never assume). "
            "no host installed reads as the honest words - press "
            "install above to register it. this line re-checks on "
            "the veil button and the switch.",
    "delay": "veil after: the desk frames a PLAYING video only once "
             "the input has been still this long - the dimmer's "
             "\"dim after\" shape, one knob for the on-delay and the "
             "re-arm (any mouse/keyboard move drops the veil until "
             "this passes again). 0 means instant. a film's sound "
             "never lifts the theater veils.",
    "level": "veil level: how dark the four theater pieces are, in "
             "percent - the theater's OWN darkness, not the idle "
             "dimmer's number. the movie can go darker (or lighter) "
             "than the plain idle veils.",
    "fade": "off (the default): the frame is GONE the moment you "
            "touch the mouse or press a key - no fade, no ceremony. "
            "on: the theater joins the ramp family - one beat of "
            "hold, then the frame retracts gently over the dimmer's "
            "\"fade within\" ramp, never a blink.",
    "mons": "per-monitor theater: the box keeps THIS panel's theater "
            "(a video on it frames; a panel with no video wears the "
            "full-field veil while the conjunction holds). unchecked, "
            "the panel gets no pieces at all and dims like any idle "
            "desk. the slider is the panel's OWN veil percent - until "
            "you move it the panel follows the \"veil level\" above. "
            "a panel you never touched reads checked but has no row "
            "yet: secondary panels wear the full-field veil only once "
            "you move one of their controls (rows save on first use).",
}


class _OledMixin:
    # ------------------------------------------------------------------ oled --
    def _build_oled(self, parent):
        # the two-column law (owner, Oct 15), now on the HOUSE rhythm
        # (_two_columns): equal widths, one gutter, flush edges - the
        # old per-tab 560/520 literals were a second rhythm the eye had
        # to re-learn on every tab, and pack's propagate meant they were
        # never honored anyway (the columns sized to their content).
        # LEFT: hider over dimmer - the pixels that rest; RIGHT: the
        # refresh card over the veil card - the pixels that move. Pack
        # order is the owner's cell order, column by column.
        col, col2 = self._two_columns(parent)
        box = self._card(col, "taskbar hider",
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
        # disambiguated by the gdi slot the rows already carry) - and
        # like the away card's, inside THEIR OWN frame: the desk can
        # change under a living window (the owner's zero-monitor boot,
        # Oct 17) and every monitor row on this tab is discard-and-
        # refill now, one idiom, four sections.
        self._oled_row_frame = ctk.CTkFrame(box, fg_color="transparent")
        self._oled_row_frame.pack(anchor="w", fill="x")
        self._oled_fill_rows()
        hid = self.cfg.setdefault("hider", {})

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
        self._build_refresh(col2)               # right column, top cell
        self._build_dimmer(col)                 # left column, under the hider
        self._build_companion(col2)             # right column, under the jog
        self._oled_sync()

    # ------------------------------------------------- monitor rows --
    # Four sections, one idiom (the _cam_rows discard-and-refill): the
    # widgets are disposable, cfg is the truth, and the desk is allowed
    # to change under a living window (owner's zero-monitor boot,
    # Oct 17). Each fill re-derives its own dupes/labels from the
    # fresh enumeration; nothing cached survives the swap.

    def _oled_fill_rows(self):
        for widget in self._oled_row_frame.winfo_children():
            widget.destroy()
        self._oled_rows = {}
        hid = self.cfg.setdefault("hider", {})
        _live = wm.monitors()
        base = [m.get("short") or m.get("id") for m in _live]
        dupes = {b for b in base if base.count(b) > 1}
        for m, short in zip(_live, base):
            label = short
            if short in dupes:
                label = "%s (%s)" % (
                    short, str(m.get("gdi") or "").rsplit("DISPLAY", 1)
                    [-1] or "?")
            label = label + desk_position(
                [(mm.get("x", 0), mm.get("y", 0), mm.get("w", 0),
                  mm.get("h", 0)) for mm in _live],
                m.get("x", 0), m.get("y", 0), m.get("w", 0), m.get("h", 0))
            row = self._row(self._oled_row_frame, label, TIP["row"],
                            hint_chars=42)
            box2 = ctk.CTkCheckBox(
                row, text="strip",
                command=lambda s=short: self._oled_row_changed(s),
                font=self.skin.font(12), checkbox_width=18,
                checkbox_height=18,
                border_color=self.skin.border_raised,
                fg_color=self.skin.accent, hover_color=self.skin.accent,
                text_color=self.skin.text,
                text_color_disabled=self.skin.txt3)
            box2.set(bool((hid.get("monitors") or {}).get(short)))
            box2.grid(row=0, column=1, sticky="e")
            self._oled_rows[short] = box2

    def _jog_fill_rows(self):
        for widget in self._jog_row_frame.winfo_children():
            widget.destroy()
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
            row = self._row(self._jog_row_frame, label, TIP_JO["row"],
                            hint_chars=42)
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

    def _dim_fill_rows(self):
        for widget in self._dim_row_frame.winfo_children():
            widget.destroy()
        self._dim_rows = {}
        self._dim_always = {}
        self._dim_level = {}
        dim = self.cfg.setdefault("dimmer", {})
        base = [m.get("short") or m.get("id") for m in wm.monitors()]
        dupes = {b for b in base if base.count(b) > 1}
        for m, short in zip(wm.monitors(), base):
            label = short
            if short in dupes:
                label = "%s (%s)" % (
                    short, str(m.get("gdi") or "").rsplit("DISPLAY", 1)
                    [-1] or "?")
            row = self._row(self._dim_row_frame, label, TIP_DIM["row"],
                            hint_chars=42)
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
            # the Oct-15 always sub-mode, per row - the same opt-in
            # discipline as the strip's reveal scope: it only ever
            # modifies a row that is already opted in
            abox = ctk.CTkCheckBox(
                row, text="always",
                command=lambda s=short: self._oled_dim_always_changed(s),
                font=self.skin.font(12), checkbox_width=18,
                checkbox_height=18,
                border_color=self.skin.border_raised,
                fg_color=self.skin.accent, hover_color=self.skin.accent,
                text_color=self.skin.text,
                text_color_disabled=self.skin.txt3)
            abox.set(bool((dim.get("always") or {}).get(short)))
            abox.grid(row=0, column=2, sticky="e",
                      padx=(theme.S_FIELD, 0))
            # the same hover-tip path _row wires on its label
            abox.bind("<Enter>",
                      lambda e=None, b=abox: self.tips._schedule(
                          TIP_DIM["always"], b), add="+")
            abox.bind("<Leave>",
                      lambda e=None: self.tips._hide_soon(), add="+")
            self._dim_always[short] = abox
            # the per-panel veil percent (the Oct-16 wave absorbs the
            # ADDON entry - panels answer differently): the row opens
            # at the card's "veil level" and the FIRST move saves
            # dimmer.levels[short]; an untouched panel keeps following
            # the global (the honest absent-key law).
            srow = self._row(self._dim_row_frame, "%s veil %%" % label,
                             TIP_DIM["row_level"], hint_chars=42)
            lv = (dim.get("levels") or {}).get(short)
            if lv is None:
                lv = int(dim.get("level", DIMMER_LEVEL_DEFAULT))
            slabel = ctk.CTkLabel(srow, font=self.skin.font(12),
                                  **self.skin.text_style("sub"))
            sslider = ctk.CTkSlider(
                srow, from_=DIMMER_LEVEL_FLOOR, to=DIMMER_LEVEL_CEIL,
                number_of_steps=DIMMER_LEVEL_CEIL - DIMMER_LEVEL_FLOOR,
                width=180,
                command=lambda v, s=short:
                self._oled_dim_level_changed(s, v),
                **self.skin.slider_style())
            sslider.set(int(lv))
            sslider.grid(row=0, column=1, sticky="e")
            slabel.configure(text="%s%%" % int(lv))
            slabel.grid(row=0, column=2, sticky="e",
                        padx=(theme.S_FIELD, 0))
            self._dim_level[short] = (sslider, slabel)

    def _comp_fill_rows(self):
        for widget in self._comp_row_frame.winfo_children():
            widget.destroy()
        self._comp_mon_rows = {}
        vdm = (self.cfg.setdefault("videodim", {})).get("monitors") or {}
        base_c = [m.get("short") or m.get("id") for m in wm.monitors()]
        dupes_c = {b for b in base_c if base_c.count(b) > 1}
        for m, short in zip(wm.monitors(), base_c):
            label = short
            if short in dupes_c:
                label = "%s (%s)" % (
                    short, str(m.get("gdi") or "").rsplit("DISPLAY", 1)
                    [-1] or "?")
            crow = self._row(self._comp_row_frame, " ", TIP_COMP["mons"],
                             hint_chars=42)
            cbox = ctk.CTkCheckBox(
                crow, text="theater on " + label,
                command=lambda s=short: self._oled_comp_row_changed(s),
                font=self.skin.font(12), checkbox_width=18,
                checkbox_height=18, border_color=self.skin.border_raised,
                fg_color=self.skin.accent, hover_color=self.skin.accent,
                text_color=self.skin.text,
                text_color_disabled=self.skin.txt3)
            r = vdm.get(short)
            r = r if isinstance(r, dict) else {}
            cbox.set(bool(r.get("on", True)))
            cbox.grid(row=0, column=1, sticky="e")
            lvl = r.get("level")
            if lvl is None:
                lvl = int((self.cfg.get("videodim") or {}).get(
                    "level", VIDEODIM_LEVEL_DEFAULT))
            cslider = ctk.CTkSlider(
                crow, from_=VIDEODIM_LEVEL_FLOOR,
                to=VIDEODIM_LEVEL_CEIL,
                number_of_steps=VIDEODIM_LEVEL_CEIL -
                                VIDEODIM_LEVEL_FLOOR,
                width=140,
                command=lambda v, s=short:
                self._oled_comp_row_level_changed(s, v),
                **self.skin.slider_style())
            cslider.set(int(lvl))
            cslider.grid(row=0, column=2, sticky="e",
                         padx=(theme.S_FIELD, 0))
            clabel = ctk.CTkLabel(crow, font=self.skin.font(12),
                                  **self.skin.text_style("sub"))
            clabel.configure(text="%s%%" % int(lvl))
            clabel.grid(row=0, column=3, sticky="e",
                        padx=(theme.S_FIELD, 0))
            self._comp_mon_rows[short] = (cbox, cslider, clabel)

    def _oled_rebuild_rows(self):
        """The oled tab's share of the desk refresh: four sections,
        then the sync walker re-grays what the mode and consent say
        must not speak (a fresh row never outranks gray-not-lie)."""
        self._oled_fill_rows()
        self._jog_fill_rows()
        self._dim_fill_rows()
        self._comp_fill_rows()
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

        self._jog_row_frame = ctk.CTkFrame(box, fg_color="transparent")
        self._jog_row_frame.pack(anchor="w", fill="x")
        self._jog_fill_rows()
        jog_cfg = self.cfg.setdefault("jog", {})

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
        self.oled_say2 = ctk.CTkLabel(row, text="", font=self.skin.font(11),
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
                         "using; touch lifts a veil at once, and a "
                         "window whose process makes sound keeps its "
                         "own light while it speaks (then for a "
                         "settle beat after)")
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

        self._dim_row_frame = ctk.CTkFrame(box, fg_color="transparent")
        self._dim_row_frame.pack(anchor="w", fill="x")
        self._dim_fill_rows()
        dim = self.cfg.setdefault("dimmer", {})

        row = self._row(box, "dim after", TIP_DIM["idle"],
                        hint_chars=42)
        self.oled_idle_label = ctk.CTkLabel(row, font=self.skin.font(12),
                                            **self.skin.text_style("sub"))
        slider = ctk.CTkSlider(row, from_=DIMMER_IDLE_FLOOR,
                               to=DIMMER_IDLE_CEIL,
                               number_of_steps=(DIMMER_IDLE_CEIL
                                                - DIMMER_IDLE_FLOOR),
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
        # the plain veil's lift style (owner, Oct 16: "60 s veil lift
        # is dumb"), beside its ramp - the theater card's fade switch
        # is the twin idiom, two keys two owners' words. OFF (the
        # default) = the veil is gone the instant you touch the desk;
        # the ramp to its left applies to the plain veils only when
        # this is on.
        self.oled_dim_lift_fade = ctk.CTkSwitch(
            row, text="lift fade", font=self.skin.font(12),
            command=self._oled_dim_fade_changed,
            **self.skin.switch_style())
        self.oled_dim_lift_fade.select() if dim.get("fade") is True \
            else self.oled_dim_lift_fade.deselect()
        self.oled_dim_lift_fade.grid(row=0, column=3, sticky="e",
                                     padx=(theme.S_FIELD, 0))
        self.oled_dim_lift_fade.bind(
            "<Enter>", lambda e=None, b=self.oled_dim_lift_fade:
            self.tips._schedule(TIP_DIM["lift_fade"], b), add="+")
        self.oled_dim_lift_fade.bind(
            "<Leave>", lambda e=None: self.tips._hide_soon(), add="+")

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
        # zero-size on purpose: CTk's frame default is 200x200, and this
        # box is EMPTY until an app is excluded - the default request was
        # a 200 px hole in the middle of the card (measured in the
        # baseline shot, owner's "even spacing" finding)
        self._dim_apps_box = ctk.CTkFrame(row, width=0, height=0,
                                          fg_color="transparent")
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
            self._comp_words()          # the companion's status
            #                            # line rides this same
            #                            # beat (the packet's law:
            #                            # one cadence in the tab)
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

    def _oled_dim_always_changed(self, short):
        """The Oct-15 always sub-mode rail: [dimmer.always] is the
        panel's own word, stored per row exactly like the opt-in it
        modifies - a false row is the plain idle law, and a row that
        never opted in dims by an always that has no effect."""
        box = self._dim_always.get(short)
        if box is None:
            return
        self.cfg.setdefault("dimmer", {}).setdefault("always", {})[short] \
            = bool(box.get())
        self._save()

    def _oled_dim_fade_changed(self):
        # [dimmer].fade - the plain lift toggle (owner, Oct 16: "60 s
        # veil lift is dumb"). OFF (the stock default) = the plain
        # veil drops the instant the desk is touched; the ramp family
        # is the opt-in. The theater's twin switch (_oled_comp_fade_
        # changed) is a separate key by law.
        self.cfg.setdefault("dimmer", {})["fade"] = bool(
            self.oled_dim_lift_fade.get())
        self._save()

    def _oled_dim_level_changed(self, short, value):
        # [dimmer.levels] - the per-panel veil percent (the Oct-16
        # wave absorbs the ADDON): the row stores ITS panel's number;
        # the card's "veil level" stays the default for unlisted
        # panels.
        pair = self._dim_level.get(short)
        if pair is None:
            return
        self.cfg.setdefault("dimmer", {}).setdefault(
            "levels", {})[short] = int(round(value))
        pair[1].configure(text="%s%%" % round(value))
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
        if not apps:
            # the honest empty state: with the card chrome gone (owner
            # Oct 15) a bare "excluded" label over nothing read as a
            # broken row rather than an empty one
            ctk.CTkLabel(self._dim_apps_box,
                         text="none - every app wears a veil",
                         font=self.skin.font(11), anchor="e",
                         **self.skin.text_style("sub")).pack(
                side="right", padx=(theme.S_FIELD, 0))
            return
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
        if event.keysym in ("Control_L", "Control_R", "Shift_L",
                            "Shift_R", "Alt_L", "Alt_R",
                            "Super_L", "Super_R"):
            # the ordering truth the mask pins cannot see (gate, F4):
            # a modifier's OWN keydown carries state=0 - disarming
            # here would refuse the first half of every real chord
            # before its letter ever arrived. keep waiting.
            return "break"
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
        # the Oct-15 truth line for the false-"taken" hunt: raw
        # event.state as Tk THIS platform set it, and the word the
        # table made of it - a dropped or phantom modifier is now
        # visible before registration ever calls it a clash. MOD_
        # NOREPEAT rides only at registration; it has no Tk analogue
        # (0x40000000 in state is Tk's own lock-mask territory and
        # the table reads neither it nor 0x2 capslock in/out).
        log.info("dimmer: capture: raw state=%#x keycode=%#x -> "
                 "stored %r", event.state, event.keycode, pair)
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

    # ------------------------------------------------------------------
    # fourth card: the video-dim companion (Oct 15; native-messaging
    # reality Oct 16). There is one consent key: [videodim].on. The
    # geometry arrives from the buddy extension through its local native
    # host (extension/), which writes the app's own doorway file - there
    # is no debug port, no flag list, no opt-in rail beyond the one
    # switch. The master switch is a truth switch (the _power idiom:
    # knob from cfg, BOTH branches) and rides the _shell.SWITCH_SYNC
    # dispatch, so hide/show can never leave it drawing a lying knob.
    # The status line rides the dimmer poll's own beat; every answer
    # renders from .get chains - a missing key is words, never a crash.
    # ------------------------------------------------------------------

    def _build_companion(self, parent):
        box = self._card(parent, "Movie theater mode",
                         "a playing video dims the desk around it, "
                         "once the input sits still for the \"veil "
                         "after\" wait; touch lifts the frame at once "
                         "and a film's sound never does - only the "
                         "mouse and keys drop it")
        row = self._row(box, "Movie theater mode", TIP_COMP["on"],
                        hint_chars=42)
        self.oled_comp_box = ctk.CTkSwitch(
            row, text="", font=self.skin.font(12),
            command=self._oled_comp_changed, **self.skin.switch_style())
        self.oled_comp_box.grid(row=0, column=1, sticky="e")
        self.oled_comp_box.select() if (self.cfg.get("videodim") or
                                        {}).get("on") is True \
            else self.oled_comp_box.deselect()

        # "veil after" - the automatic lane's IDLE rail, the dimmer's
        # idle_sec sibling (owner, Oct 16: "same as window dimming" and
        # "if the user moves mouse veil drops until x secs"): a playing
        # video frames the desk only when the input has been still this
        # long. ONE knob for the on-delay and the re-arm - the dimmer's
        # symmetric shape. Sound never lifts the theater veils.
        row = self._row(box, "veil after", TIP_COMP["delay"],
                        hint_chars=42)
        self.oled_vee_delay_label = ctk.CTkLabel(
            row, font=self.skin.font(12), **self.skin.text_style("sub"))
        slider = ctk.CTkSlider(
            row, from_=VIDEODIM_IDLE_FLOOR, to=VIDEODIM_IDLE_CEIL,
            number_of_steps=VIDEODIM_IDLE_CEIL - VIDEODIM_IDLE_FLOOR,
            width=180, command=self._oled_comp_delay_changed,
            **self.skin.slider_style())
        slider.set(int((self.cfg.get("videodim") or {}).get(
            "idle_sec", VIDEODIM_IDLE_DEFAULT)))
        slider.grid(row=0, column=1, sticky="e")
        self.oled_vee_delay_label.configure(
            text="%s s" % int((self.cfg.get("videodim") or {}).get(
                "idle_sec", VIDEODIM_IDLE_DEFAULT)))
        self.oled_vee_delay_label.grid(row=0, column=2, sticky="e",
                                       padx=(theme.S_FIELD, 0))

        # "veil level" - the theater pieces' OWN darkness (owner, Oct
        # 16): the four dark pieces draw at THIS percent, not the idle
        # dimmer's [dimmer].level. Sibling of the dimmer's veil-level
        # rail, same clamp (10..90), same honesty.
        row = self._row(box, "veil level", TIP_COMP["level"],
                        hint_chars=42)
        self.oled_vee_level_label = ctk.CTkLabel(
            row, font=self.skin.font(12), **self.skin.text_style("sub"))
        slider = ctk.CTkSlider(
            row, from_=VIDEODIM_LEVEL_FLOOR, to=VIDEODIM_LEVEL_CEIL,
            number_of_steps=VIDEODIM_LEVEL_CEIL - VIDEODIM_LEVEL_FLOOR,
            width=180, command=self._oled_comp_level_changed,
            **self.skin.slider_style())
        slider.set(int((self.cfg.get("videodim") or {}).get(
            "level", VIDEODIM_LEVEL_DEFAULT)))
        slider.grid(row=0, column=1, sticky="e")
        self.oled_vee_level_label.configure(
            text="%s%%" % int((self.cfg.get("videodim") or {}).get(
                "level", VIDEODIM_LEVEL_DEFAULT)))
        self.oled_vee_level_label.grid(row=0, column=2, sticky="e",
                                       padx=(theme.S_FIELD, 0))

        # "fade out" - the theater retract style (owner, Oct 16: "I
        # don't like the fade, so I won't use it - but having the
        # option is the right move"): OFF by default, the frame is
        # gone the tick input returns; ON opts into the ramp family
        # (one-tick hold, retract over the dimmer's ramp, no blink).
        row = self._row(box, "fade out", TIP_COMP["fade"],
                        hint_chars=42)
        self.oled_comp_fade = ctk.CTkSwitch(
            row, text="", font=self.skin.font(12),
            command=self._oled_comp_fade_changed,
            **self.skin.switch_style())
        self.oled_comp_fade.select() if (self.cfg.get("videodim") or
                                         {}).get("fade") is True \
            else self.oled_comp_fade.deselect()
        self.oled_comp_fade.grid(row=0, column=1, sticky="e")

        # THE PER-MONITOR THEATER (owner, Oct 16): every panel gets a
        # row. CHECKED (the default when no row exists - a row is
        # written to opt OUT too) keeps the panel's theater: its own
        # video frames as usual, and a panel with no video on it
        # wears a FULL-FIELD veil while the conjunction holds. An
        # UNCHECKED panel gets no pieces at all - a video on it dims
        # like any idle desk. The slider is the panel's OWN veil
        # percent: it opens at the global "veil level" and the first
        # move stores the row (an untouched slider = follow the
        # global, the honest absent-key law).
        self._comp_row_frame = ctk.CTkFrame(box, fg_color="transparent")
        self._comp_row_frame.pack(anchor="w", fill="x")
        self._comp_fill_rows()

        # THE DEBUG PORT IS GONE FROM THE SURFACE (owner, Oct 16,
        # second instruction): the per-family checkboxes made the dead
        # route look alive - the flag path restarted a browser with a
        # port open to every local process, the infostealer classic.
        # The native-messaging host answers instead: the extension's id
        # is the only ACL, the host writes the app's doorway.

        row = self._row(box, "test the geometry", TIP_COMP["veil"],
                        hint_chars=42)
        self.oled_comp_btn = ctk.CTkButton(
            row, text="measure now", height=26, width=120,
            command=self._oled_comp_veil, **self.skin.secondary())
        self.oled_comp_btn.grid(row=0, column=1, sticky="e")
        self.oled_comp_say = ctk.CTkLabel(row, font=self.skin.font(11),
                                          wraplength=240, justify="left",
                                          anchor="e",
                                          **self.skin.text_style("sub"))
        self.oled_comp_say.grid(row=0, column=2, sticky="e",
                                padx=(theme.S_FIELD, 0))

        row = self._row(box, " ", TIP_COMP["path"], hint_chars=42)
        ctk.CTkLabel(row, text=companion.door_dir(),
                     font=self.skin.font(11), wraplength=300,
                     justify="left", anchor="w",
                     **self.skin.text_style("sub")).grid(
            row=0, column=1, columnspan=2, sticky="w")
        # the one-click helper install (Oct 16): the SAME script the
        # README documents, run from the app - build, register, and
        # host.json in one gesture, worker-ized like the capture verb
        # (PyInstaller takes ~40 s, a walk that belongs on no pump).
        # The entry is an optional id override (the store-publish
        # case); empty derives from the extension's on-disk path.
        # The dimmer's exclusion row (entry + small verb) is the
        # row's own rhythm - this card keeps it.
        self.oled_comp_helper = ctk.CTkEntry(
            row, width=150, font=self.skin.font(11),
            placeholder_text="id override",
            fg_color=self.skin.field_bg, border_width=1,
            border_color=self.skin.border_raised,
            corner_radius=self.skin.radius)
        self.oled_comp_helper.grid(row=1, column=1, sticky="e",
                                   pady=(theme.S_FIELD, 0))
        self.oled_comp_inst_btn = ctk.CTkButton(
            row, text="install the helper", height=26, width=150,
            command=self._helper_install, **self.skin.secondary())
        self.oled_comp_inst_btn.grid(row=1, column=2, sticky="e",
                                     padx=(theme.S_FIELD, 0),
                                     pady=(theme.S_FIELD, 0))

        # the capability-discovery line: what the buddy's API CAN send,
        # READ from the host (nmhost.capabilities), never assumed. The
        # card asks the host directly - the owner's mandate, and the
        # one place the "what can it do" question is answered on-screen.
        row = self._row(box, " ", TIP_COMP["caps"], hint_chars=42)
        self.oled_comp_caps = ctk.CTkLabel(
            row, font=self.skin.font(11), wraplength=420,
            justify="left", anchor="w", **self.skin.text_style("sub"))
        self.oled_comp_caps.grid(row=0, column=1, columnspan=2,
                                 sticky="e")
        self._comp_words()
        self._helper_install_words()

    def _helper_install_words(self):
        """The doorway row's button reads "install the helper" until
        the host is INSTALLED - then "reinstall" (the same verb, the
        manifest and host.json get rewritten, the id override still
        stands). Never raises: a junk host.json answers the default."""
        try:
            installed = nmhost.host_path() is not None
        except Exception:
            installed = False
        try:
            self.oled_comp_inst_btn.configure(
                text="reinstall" if installed else "install the helper")
        except (tk.TclError, RuntimeError):
            pass            # the paint superseded: the next _comp_words
                             # beat (or a rebuild) repants from the host

    def _comp_words(self, force=False):
        """The status line, on the dimmer poll's beat: companion.say
        for the rail and the doorway, companion.caps_words for the
        discovered API surface. Junk shapes read as words. force
        re-asks the host (the switch and the veil button earn it -
        the tip promises a re-check there, gate 2nd-pass finding 3;
        a wedged host costs its bounded 2 s ON THE CLICK, never on
        the silent beat)."""
        if getattr(self, "oled_comp_say", None) is None:
            return
        set_text(self.oled_comp_say, companion.say(self.cfg))
        self._helper_install_words()
        if getattr(self, "oled_comp_caps", None) is not None:
            set_text(self.oled_comp_caps, companion.caps_words(force=force))

    def _oled_comp_changed(self):
        # one gesture, one key: [videodim].on is the single consent
        # the engine gates on - there is no companion rail to pair it
        # with any more (the enabled/flag_families pair retired Oct 16).
        vd = self.cfg.setdefault("videodim", {})
        vd["on"] = bool(self.oled_comp_box.get())
        self._save()
        self._comp_words(force=True)

    def _oled_comp_delay_changed(self, value):
        # [videodim].idle_sec - the automatic lane's ONE idle knob (the
        # dimmer's idle_sec sibling): on-delay and re-arm, symmetric.
        self.cfg.setdefault("videodim", {})["idle_sec"] = int(round(value))
        self.oled_vee_delay_label.configure(text="%s s" % round(value))
        self._save()

    def _oled_comp_level_changed(self, value):
        # [videodim].level - the theater pieces' OWN darkness (the
        # dimmer's veil-level sibling): the frame draws at THIS, not the
        # idle dimmer's level. Clamped 10..90 by the slider's own range.
        self.cfg.setdefault("videodim", {})["level"] = int(round(value))
        self.oled_vee_level_label.configure(text="%s%%" % round(value))
        self._save()

    def _oled_comp_fade_changed(self):
        vd = self.cfg.setdefault("videodim", {})
        vd["fade"] = bool(self.oled_comp_fade.get())
        self._save()

    def _oled_comp_row_changed(self, short):
        # [videodim].monitors[short].on - the per-panel theater box.
        # The row is WRITTEN on the gesture (a checked box after an
        # absent row stores the same True the absence meant - honest,
        # and the opt-out becomes revocable in the same seam).
        pair = self._comp_mon_rows.get(short)
        if pair is None:
            return
        self.cfg.setdefault("videodim", {}).setdefault(
            "monitors", {}).setdefault(short, {})["on"] = bool(
            pair[0].get())
        self._save()

    def _oled_comp_row_level_changed(self, short, value):
        # [videodim].monitors[short].level - the panel's OWN theater
        # darkness. The slider opened at the global (the label shows
        # what it shows); the first move stores the number and the
        # panel stops following.
        pair = self._comp_mon_rows.get(short)
        if pair is None:
            return
        self.cfg.setdefault("videodim", {}).setdefault(
            "monitors", {}).setdefault(short, {})["level"] = int(
            round(value))
        pair[2].configure(text="%s%%" % round(value))
        self._save()

    def _oled_comp_veil(self):
        # the one-shot answers in the status line itself (the wash
        # button's idiom): the rect it saw, or the no-click words; the
        # explicit click also re-checks what the API can send (force).
        set_text(self.oled_comp_say, companion.veil_now(self.cfg))
        if getattr(self, "oled_comp_caps", None) is not None:
            set_text(self.oled_comp_caps, companion.caps_words(
                force=True))

    def _helper_install(self):
        # the one-click helper install, WORKER-IZED like
        # _profile_create's capture: PyInstaller takes ~40 s - a walk
        # that belongs on no pump. The lock is CARD-LOCAL (the helper
        # verb is not a desktop verb; the shared _applying flag is the
        # capture/apply pair's, and this verb contends nothing they
        # own). The sibling's documented laws ride verbatim: every
        # paint above the lock is plain (a raise on the way in must
        # not wedge the button into a permanent "already working"),
        # the flag goes up LAST, and done() marshals through after(0)
        # with the ghost-tolerance the capture verb demonstrates
        # (queue-fallback drain on a dead root - the Oct-14 class).
        entry = (self.oled_comp_helper.get() or "").strip().lower()   # browser ids are a-p lowercase; a hand-typed paste   # folds (gate finding 3)
        if entry and not re.match(r"^[a-p]{32}$", entry):
            # the client-side id law: a bad shape answers a word and
            # does NOT fire the installer (the ps1's own validation is
            # the same shape - this one just refuses earlier).
            set_text(self.oled_comp_say,
                     "bad id override - 32 lowercase a-p chars")
            return
        if getattr(self, "_helper_running", False):
            set_text(self.oled_comp_say,
                     "installing the buddy's helper...")
            return
        set_text(self.oled_comp_say,
                 "installing the buddy's helper...")
        self.oled_comp_inst_btn.configure(state="disabled")
        self._helper_running = True

        def work():
            try:
                ok, words = nmhost.install(entry or None)
                err = None
            except Exception as e:                    # the worker
                log.exception("the helper install died in the worker")  # confesses
                ok, err = False, "the install raised: %s" % e
            if err:
                words = err

            def done():
                if not getattr(self, "_helper_running", False):
                    return             # already landed (belt + timer
                self._helper_running = False          # both)
                try:
                    self.oled_comp_inst_btn.configure(state="normal")
                    self._comp_words(force=True)      # the fresh host's
                                                       # own caps line -
                                                       # the probe IS the
                                                       # proof-of-install
                    set_text(self.oled_comp_say, words)
                    # RESULT on the say line: success = the fresh
                    # capability words; failure = the honest step word
                    # + the manual ps1 route (nmhost.install's words
                    # carry it - the console path stays documented).
                except (tk.TclError, RuntimeError):
                    log.exception("the helper install paint was "
                                  "superseded (the root is a ghost) - "
                                  "the next beat repaints")
            try:
                self.after(0, done)
            except (tk.TclError, RuntimeError):
                try:
                    self.ui_events.put(("later", done))
                except Exception:
                    pass
        threading.Thread(target=work, daemon=True).start()

    def _sync_companion_switches(self):
        """Knob-lie belt (_shell.SWITCH_SYNC): the master switch and
        the fade switch painted from the rail at settled geometry -
        both branches, no commands fired (the _power idiom's law)."""
        vd = self.cfg.get("videodim") or {}
        on = vd.get("on") is True
        self.oled_comp_box.select() if on \
            else self.oled_comp_box.deselect()
        fade = vd.get("fade") is True
        self.oled_comp_fade.select() if fade \
            else self.oled_comp_fade.deselect()
