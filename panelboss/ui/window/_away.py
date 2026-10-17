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
(Growth, 2026-10-14 off wave: the per-row choice rule, the
never-reached why-line and the off preview's countdown chain are all
card paint and stay in this file - splitting the card would scatter
the away UI to buy nothing.)
"""

from __future__ import annotations

import logging
import threading

import customtkinter as ctk

from ... import wm
from ._widgets import desk_position, set_text

log = logging.getLogger("ui")

OFF_TEXT = "monitors off"
DIM_TEXT = "dim"
DISC_TEXT = "off (disconnect)"
# the row-menu LABEL -> the engine WORD (the offdisc-preview fix:
# the picker answers labels, _away_apply_row dispatches on words;
# an unmapped label used to fall through the engine's chain to the
# silent dim leg - the confession added engine-side, the map made
# EXHAUSTIVE here and pinned in awaymode_test):
MODE_BY_LABEL = {"blackout": "blackout", "dim": "dim",
                 "off": "off", DISC_TEXT: "offdisc"}


def off_choice(bright, gdi):
    """A row's sub-mode menu. The D6 OFF is offered on every panel
    this app REACHED - physical handles opened; the AOC answered
    brightness at a one-shot probe's NAK-rate all morning and the
    PROBE LAW says that door works (owner correction: capability
    verdicts come from in-app attempts with a spent retry budget, so
    the state machine's UNKNOWN is selectable, unbelieved, and gray
    was always for never-reached panels only). The DISCONNECT rides
    the adapter's own CCD door - no DDC/CI needed, firmware never
    consulted - so it is offered everywhere, and a row whose sdc leg
    refused after the budget KEEPS the choice: the dated status word
    is the state machine's truth, gray would be a pre-judgment."""
    vals = ["blackout", "dim"]
    if bright.reachable(gdi):
        vals.append("off")
    vals.append(DISC_TEXT)
    return vals

TIP = {
    "refresh": "the monitor rows in this window follow the desk: a "
               "panel that joins or leaves is noticed within two "
               "seconds and the cards re-read. The button forces the "
               "same re-read by hand - an identical-model panel "
               "swapped behind a KVM changes nothing observable, so "
               "this is the belt the poll cannot wear. Nothing here "
               "edits a setting you made: the rows show what the "
               "config already says.",
    "mode": "off: the displays get the real power broadcast, exactly "
            "as always. dim: the panels STAY AWAKE and the app paints "
            "the dark - no cold re-enumeration on wake (the 16-38 s "
            "class), no driver drama. blackout rows wear an opaque "
            "black cover (a click on it wakes the desk); dim rows "
            "lose their HDR and drop to the brightness below for the "
            "spell and get it all back on lift; OFF rows ask the "
            "panel's own power code through the same door the "
            "brightness rides - the panel itself goes DPMS-dark, no "
            "paint, and a power write brings it back at the wake (an "
            "offed panel cannot report input: the desk wakes on the "
            "lit panels' ears or the idle gate). MEASURED ON THIS "
            "DESK CLASS: a write accepted and never proven by the "
            "readback keeps its sub-mode and says (unverified) on the "
            "row's status word; only a send refused after the retries "
            "degrades the row to blackout, and it says that too - "
            "never silent.",
    "row": "blackout = the painted lie; dim = HDR off + the shared "
           "brightness level; off = the panel's own power code (0xD6) "
           "through the brightness door, blackout as the confessed "
           "fallback if the send itself refuses. a preview applies "
           "THIS row's effect for 10 s and reverts it (the second "
           "click cancels now; a real away arriving mid-preview keeps "
           "the effect and hands it back at the real wake instead); "
           "an off preview counts its seconds on this window - the "
           "dark panel cannot carry a digit - and a dark panel also cannot prove its own darkness: 'off (unverified)' means the write was accepted and the register (or nothing) disagrees, so the eyes and the physical button remain the honest witnesses. an OFF row is a real retraction: the display is disconnected at the adapter, the same act as the re-connect entry in Windows settings, and the state SURVIVES this app - if a panel is left off, Settings -> Display brings it back (windows refuses to disconnect the last active display, so a lone screen can never be stranded).",
    "offdisc": "'off (disconnect)' is the other off: the path is "
               "retracted AT THE ADAPTER (SetDisplayConfig), so it "
               "works regardless of firmware - the panel never hears "
               "a code, it loses its signal - and it comes back as a "
               "replug: a re-enumeration, the panel waking like a "
               "cold attach. Unlike the power-code off its state "
               "lives in Windows' own display store (it survives the "
               "app), so Settings -> Display is ALWAYS the recovery "
               "door, and the app's boot belt re-raises rows it "
               "configured before it died. The row's word 'off "
               "(disconnected)' is the ONE dark this app can PROVE, "
               "and note what 'gone' names here: gone from the "
               "display store - what got cut is the signal, and "
               "through your cable that IS the dark. A hub that "
               "latches its last frame can keep showing a picture "
               "the store no longer believes, so the app asks the "
               "store, never the row list (through exactly that "
               "latch the rows keep lying); and when the store's "
               "slot and the panel's own EDID name disagree about "
               "which screen this row is, the row refuses with the "
               "dated word instead of darkening the wrong panel. A "
               "refused retraction (Windows guards the last active "
               "display) degrades the row to blackout with the dated "
               "word, exactly like a refused power code.",
    "level": "where dim rows park their brightness while away, 1 to "
              "40 percent - shared by every dim row (per-monitor "
              "levels are a planned follow-up).",
    "lock": "Windows locks when nobody MOVES; this locks when nobody "
            "is HERE - the presence verdict, not a screensaver clock. "
            "A returning face gets the lock screen, never somebody "
            "else's desktop. Behind the lock the dark spell answers "
            "the camera and the session unlock, NOT the mouse: raw "
            "input is per-desktop and the lift ears go deaf while "
            "Winlogon owns the desk (the camera stream is ours and "
            "keeps running through the lock). A preview never locks - "
            "yanking the session at setup time would be hostile; the "
            "lock lands only with a real away that darked at least "
            "one row, after the corner jail.",
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
        # lock-on-away, beside the mode pick: it only speaks for a dim
        # spell (the stock broadcast owns its own dark), so _away_sync
        # gates its state with the rows - consent and dim mode both,
        # never a live-looking box on a mode that never locks
        self.away_lock_box = ctk.CTkCheckBox(
            row, text="lock when away starts", command=self._away_lock_changed,
            font=self.skin.font(12), checkbox_width=18, checkbox_height=18,
            border_color=self.skin.border_raised,
            fg_color=self.skin.accent, hover_color=self.skin.accent,
            text_color=self.skin.text, text_color_disabled=self.skin.txt3)
        self.away_lock_box.set(bool((self.cfg.get("away") or {})
                                    .get("lock")))
        self.away_lock_box.grid(row=0, column=2, sticky="e", padx=(10, 0))

        # stage two (owner, Oct 17): painted dark at once, the panel's
        # own power code after a timer. Gray-not-lie: _away_sync gates
        # this row exactly like the lock box - a second stage on a
        # spell that never paints is a slider that cannot speak.
        drow = self._row(box, "deep sleep (disconnect) after",
                         "stage two: after this many minutes away, the "
                         "painted monitors get the monitor-power-off "
                         "command - the GPU stops presenting and the "
                         "panels rest for real; the wake on return "
                         "takes a beat longer. blackout and dim rows "
                         "only. The pointer is parked at the bottom of "
                         "the lowest monitor when away engages, and "
                         "stays there when you return.",
                         hint_chars=42)
        self.away_deep_value = ctk.CTkLabel(drow, font=self.skin.font(12),
                                            **self.skin.text_style("sub"))
        self.away_deep_value.grid(row=0, column=3, sticky="e", padx=(6, 0))
        self.away_deep_slider = ctk.CTkSlider(
            drow, from_=0, to=240, number_of_steps=48, width=150,
            # 5-minute stops (owner UAT, Oct 17): 241 positions on a
            # 150-px slider is target practice, and nobody wants a
            # 17-minute nap. A hand-set odd value rides the label
            # honestly; the knob snaps to its nearest stop.
            command=self._away_deep_changed,
            **self.skin.slider_style())
        self.away_deep_slider.set(
            (self.cfg.get("away") or {}).get("off_after_min", 0))
        self.away_deep_slider.grid(row=0, column=2, sticky="e")
        self._away_deep_say()

        # one row per live panel, the profile list's idiom - inside
        # THEIR OWN frame: the desk can change under a living window
        # (the owner's zero-monitor boot, Oct 17), and the rebuild
        # discards and refills that frame without touching the
        # desk-independent rows above or the countdown below. One
        # idiom for the whole window now: _cam_rows'
        # destroy-children-then-rebuild, the values live in cfg, the
        # widgets are disposable.
        self._away_row_frame = ctk.CTkFrame(box, fg_color="transparent")
        self._away_row_frame.pack(anchor="w", fill="x")
        self._away_jobs = {}          # short -> {"timer", "rec"}
        self._away_says = {}          # short -> status word to show
        self._away_fill_rows()
        # the manual ear (owner, Oct 17): the poll catches a swap by
        # its fingerprint within two seconds, but an identical-model
        # panel behind a KVM changes NOTHING observable - the button
        # is the belt the law cannot automate
        brow = self._row(box, "panels come and go", TIP["refresh"],
                         hint_chars=42)
        self.away_refresh_btn = ctk.CTkButton(
            brow, text="refresh monitors", width=140,
            command=lambda: self.refresh_monitor_rows("away card button"),
            **self.skin.secondary())
        self.away_refresh_btn.grid(row=0, column=1, sticky="e")
        self._away_cd = ctk.CTkLabel(box, text="", font=self.skin.font(12),
                                     **self.skin.text_style("sub"))
        self._away_cd.pack(anchor="e", pady=(2, 0))
        self._away_cd_left = 0
        self._away_cd_job = None            # the after-idle of ONE chain
        self._away_sync()
        self.after(900, self._away_poll)

    def _away_fill_rows(self):
        """Discard-and-refill (the _cam_rows idiom): every live panel
        owns a row in the card's row frame; the settings the rows
        edit come from cfg, so a rebuild cannot lie and cannot lose
        an answer."""
        for widget in self._away_row_frame.winfo_children():
            widget.destroy()
        self._away_rows = {}
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
            row = self._row(self._away_row_frame, label, TIP["row"],
                            hint_chars=42)
            vals = off_choice(wm._bright, m["gdi"])
            seg = ctk.CTkSegmentedButton(
                row, values=vals, height=26, width=200,
                command=lambda v, s=short: self._away_submode_changed(s, v),
                **self.skin.segmented_style())
            mode = self._away_row_mode(short)
            seg.set(mode if mode in vals else "dim")
            if "off" not in vals:
                # gray not lie (owner correction): the choice is
                # ABSENT here because this app never reached the
                # panel's DDC door - said in one line, in words
                # about our reach, not the firmware's soul. The
                # disconnect is NOT absent: the CCD door is the
                # adapter's, and it does not ask the panel.
                self._away_says[short] = ("the power-code off needs a "
                                          "DDC/CI door; none answered "
                                          "for this monitor (the "
                                          "disconnect does not)")
            seg.grid(row=0, column=1, sticky="e")
            # the disconnect's paragraph hangs on the picker itself:
            # the label's tip is the row-wide one, and the 4th choice
            # is where the question forms (same hover path as the
            # card sub-lines). CTkSegmentedButton.bind raises
            # NotImplementedError (measured via hdrwake's live window
            # build) - the button's own canvas takes the bindings and
            # covers the same pixels (the wheel-swap walker already
            # reaches through this seam)
            try:
                seg._canvas.bind(
                    "<Enter>", lambda e=None, w=seg: self.tips._schedule(
                        TIP["offdisc"], w), add="+")   # w= default-captures
                #                    the loop var (gate fix 4 - the
                #                    file's own s=short idiom: late
                #                    binding would anchor every row's
                #                    paragraph to the LAST picker)
                seg._canvas.bind("<Leave>",
                                 lambda e=None: self.tips._hide_soon(),
                                 add="+")
            except Exception:
                pass                       # no paragraph, no crime
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
            say = ctk.CTkLabel(self._away_row_frame, text="",
                               font=self.skin.font(10),
                               wraplength=350, justify="left", anchor="w",
                               **self.skin.text_style("sub"))
            self._away_rows[short] = {"row": row, "seg": seg,
                                      "slider": slider, "value": value,
                                      "preview": preview, "say": say,
                                      "gdi": m["gdi"]}
            say.pack(anchor="w")
        self._away_sync()

    def _away_rebuild_rows(self):
        """The desk moved, or the button said so. A live preview is
        cancelled through its OWN cancel path first (the panel gets
        its brightness back BEFORE its editor row dies - the row is
        disposable, the applied effect is not), then discard-refill.
        The _away_done guard for a gone row (r is None) covers the
        after(0) hop the manual cancel takes."""
        for short, job in list(self._away_jobs.items()):
            self._away_expiry(short, job["rec"], manual=True)
        self._away_fill_rows()

    def _away_countdown(self):
        """The off preview's seconds, on the settings window - the
        covered panel cannot carry them (it is OFF, or painted
        black), the glyph lives where the eyes are (owner decision,
        shipped as this card label). One shared chain: the newest
        off preview CANCELS its predecessor before re-arming (gate
        finding 3), expiry/cancel/window-death stop it, and the
        death-path word goes under the same TclError courtesy the
        poll uses - one caught exception, no crash at teardown.
        """
        try:
            if getattr(self, "_dying", False) or self._away_cd_left <= 0:
                set_text(self._away_cd, "")
                self._away_cd_job = None
                return
            set_text(self._away_cd, "dark for %d s" % self._away_cd_left)
        except Exception:
            self._away_cd_job = None
            return                          # gone mid-tick: fine
        self._away_cd_left -= 1
        try:
            self._away_cd_job = self.after(1000, self._away_countdown)
        except Exception:
            self._away_cd_job = None        # destroyed mid-tick

    # ------------------------------------------------------------ state reads --
    def _away_level(self):
        return int((self.cfg.get("away") or {}).get("dim_level", 10))

    def _away_row_mode(self, short):
        """The triple shape normalize ships ({"blackout": b, "off": b,
        "offdisc": b}); the legacy bare-bool row reads honestly too
        (one release - the file shape the dim wave wrote). The answer
        is a MENU LABEL: the disconnect's label differs from its
        stored word, and the row-menu maps label -> triple."""
        rows = (self.cfg.get("away") or {}).get("monitors") or {}
        row = rows.get(short)
        if not row:
            return "dim"
        if isinstance(row, bool):
            return "blackout" if row else "dim"
        if row.get("offdisc"):
            return DISC_TEXT
        if row.get("off"):
            return "off"
        return "blackout" if row.get("blackout") else "dim"

    # ------------------------------------------------------------- handlers --
    def _away_mode_changed(self, label):
        # cfg["away"] IS the engine's dict: writing is applying, the
        # next _screens_off already engages (or doesn't) the new mode
        self.cfg.setdefault("away", {})["mode"] = \
            "dim" if label == DIM_TEXT else "off"
        self._away_sync()
        self._save()

    def _away_lock_changed(self):
        # the same write-is-applying law: the flag rides the live
        # away dict, the next real engage reads it at its own end
        self.cfg.setdefault("away", {})["lock"] = \
            bool(self.away_lock_box.get())
        self._away_sync()
        self._save()

    def _away_submode_changed(self, short, label):
        rows = self.cfg.setdefault("away", {}).setdefault("monitors", {})
        rows[short] = {"blackout": label == "blackout",
                       "off": label == "off",
                       "offdisc": label == DISC_TEXT}
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

    def _away_deep_changed(self, value):
        # write-is-applying like every neighbour: the NEXT engage reads
        # the count (a spell in flight keeps its stage), with one
        # honest exception - the beat re-reads the table every tick,
        # so a 0 written mid-spell disarms it right there
        self.cfg.setdefault("away", {})["off_after_min"] = \
            max(0, min(240, int(round(value))))
        self._away_deep_say()
        self._save()

    def _away_deep_say(self):
        mins = (self.cfg.get("away") or {}).get("off_after_min", 0)
        try:
            self.away_deep_value.configure(
                text="never" if not mins else "%d min" % mins)
        except Exception:
            pass                          # rebuilt mid-toggle: fine

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
            MODE_BY_LABEL[self._away_row_mode(short)], self._away_level())
        self._away_says[short] = rec["status"]
        if rec["status"].startswith("blackout") or \
                rec["status"].startswith("off"):
            self._away_rise(True)        # the dialog above the paint -
            #                    and above the DARK: an off row turns
            #                    the panel itself off, so the settings
            #                    window is where the eyes are (owner
            #                    decision: the countdown ships HERE)
            if rec["status"].startswith("off"):
                # ONE chain for the shared label (gate finding 3): the
                # previous preview's chain is cancelled before a new
                # one is armed, or two counts double-decrement one word
                if self._away_cd_job is not None:
                    try:
                        self.after_cancel(self._away_cd_job)
                    except Exception:
                        pass
                self._away_cd_left = 10
                self._away_countdown()
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
        self._away_cd_left = 0
        if getattr(self, "_away_cd_job", None) is not None:
            try:
                self.after_cancel(self._away_cd_job)
            except Exception:
                pass
            self._away_cd_job = None
        set_text(self._away_cd, "")       # the word goes now
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
        # the lock box rides the same gate as the rows: a lock with no
        # dim spell is a checkbox that cannot speak (the stock path
        # owns its own dark), and gray-not-lie is this card's law
        try:
            self.away_lock_box.configure(state="normal" if dim
                                         else "disabled")
        except Exception:
            pass                          # rebuilt mid-toggle: fine
        for w in (self.away_deep_slider, self.away_deep_value):
            try:
                w.configure(state="normal" if dim else "disabled")
            except Exception:
                pass
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
            if self._away_row_mode(short) != "dim":
                # blackout hides the paint's level, off the panel's -
                # only a DIM row has a brightness to speak of
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
