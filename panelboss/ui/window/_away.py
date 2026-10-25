"""The away card: what the app does, per monitor, when it turns the
displays off.

SIZE LAW header: UI only. The sub-mode laws, the ledger, the
fallback chain and the adopt-vs-revert law live engine-side
(panelboss/state/_away.py); the paint and the brightness ride
wm/_overlay.py and wm/_bright.py. This file draws one card, keeps its
rows honest about what the desk just did, and runs the preview on a
threading.Timer whose revert calls INTO the engine law, never around
it.

The global mode row is DEAD (owner ruling, Oct 22): the per-monitor
pickers own every answer, and the [away] mode key stays readable as
the rows' fallback WORD (state/_away._row_mode is the chain;
config.normalize_away ships its default). Visual language: the pickers
are the detection tab's own segmented idiom (same widget, same skin
call as person/motion); the rows follow the profile monitor list
(short name first - duplicate models get the gdi slot tail, same
disambiguation the mode editor uses). The card now also hosts the
away-decision trio (the reskin wave's one-section law): the hold-off,
the lock and the window restore - the last two traveled in from the
power-plan tab (owner, Oct 22), same labels, same keys, same write
paths, because settings live where their behavior is negotiated.
(Growth, 2026-10-14 off wave: the per-row choice rule, the
never-reached why-line and the off preview's countdown chain are all
card paint and stay in this file - splitting the card would scatter
the away UI to buy nothing.)
"""

from __future__ import annotations

import logging
import threading

import customtkinter as ctk

from ... import config, wm
from ._widgets import monitor_row_label, set_text

log = logging.getLogger("ui")

DISC_TEXT = "off (disconnect)"
DDC_TEXT = "off (DDC fast)"        # the word in the file stays "off"
                                   # (byte-identical migration, owner
                                   # law); only the LABEL says DDC
# THE LAUNCH-GATE BLOCK TEXT (owner ruling at 08:2x, Oct 23, decided
# at the dump pile): 'off (DDC fast)' is kernel-freeze-adjacent on
# NVIDIA drivers (0x133 DPC_WATCHDOG, published NVIDIA bucket
# 0x133_ISR_nvlddmkm, current driver lines) - on such a desk the
# segment is configured DISABLED (gray, NOT hidden: the choice stays
# visible, its own tip says why) and every tip on it carries these
# words. The text is DATA, pinned verbatim in awaymode_test; a
# re-word is a deliberate act. The ENGINE is untouched: a config
# that says off:True on an NVIDIA desk still runs the VCP trio - the
# escape hatch for the bug's survivors and for us; the gate is
# UI-only, and the vendor's patch re-opens the door by answering the
# probe (wm.display_vendor_is_nvidia) False. REWORDED AT THE FINAL GATE
# (Oct 25): the freeze claim now reads as OBSERVED (bugcheck 0x133, the
# DPC watchdog, a family seen on the same driver with this app not
# running - our own notes carry that no-app freeze); the module
# attribution stays INFERRED, the elevated minidump parse awaits the
# owner. "the vendor has a kernel bug" stated the inference as fact.
DDC_NVIDIA_TIP = ("disabled: resumes from this off have frozen some "
                  "nvidia-driver machines (bugcheck 0x133, the DPC "
                  "watchdog) - observed without this app running too. "
                  "returns once a driver is proven safe; off "
                  "(disconnect) darkens the same way.")
# THE VERDICT RIDES THE LABEL (launch amendment 3, owner at the desk,
# Oct 23 14:0x, shape endorsed off the live desk shot): a blocked
# segment SAYS why in the menu itself. The suffixed text is the
# DISPLAY value only - the state key stays DDC_TEXT (the engine's
# word, the config file, MODE_BY_LABEL's domain), and
# _sync_away_rows maps display <-> stored word.
# SHORTENED (owner ruling, Oct 24 at the desk: "the text on off (DDC
# fast) - this driver blocks it is too long and makes the button
# huge, I could see it causing clipping with a longer monitor name or
# if top right (primary) was relevant"): CTkSegmentedButton sizes each
# segment to its own text, so the old 24-character verdict widened the
# whole picker and pushed the row's brightness controls off its own
# right edge. The verdict stays ON the button - shorter - and the full
# why lives on the row's tooltip (DDC_NVIDIA_TIP below, bound to the
# row AND to the segment itself), which is where a why belongs.
DDC_BLOCKED_SUFFIX = " - blocked"
DDC_BLOCKED_LABEL = DDC_TEXT + DDC_BLOCKED_SUFFIX
# one INFO per card build/refresh at the probe call site (the owner
# question at the desk: 'also app writes anything about it to log?')
# so %APPDATA%\PanelBoss's log answers 'why is that button gray'
# without a repro. The verdict is the scan's, fail-closed included.
GATE_LOG = {
    "nvidia": "vendor gate: NVIDIA display driver present - off "
              "(DDC fast) blocked in UI (config word still honored)",
    "fail": "vendor gate: driver scan failed - off (DDC fast) "
            "blocked (fail-closed)",
    "clear": "vendor gate: no NVIDIA adapter found - off (DDC fast) "
             "available",
}


def vendor_gate():
    """The away card's per-build verdict: one call to the scan (the
    adapters are not hot - the card's fill IS the recompute seam,
    once per build/refresh, never per row), one confession line for
    the log, and the bool the builder paints from. Fail-closed: an
    unprovable desk is a blocked desk (the doctrine is the probe's,
    wm/_monitors.py)."""
    _verdict = wm.display_vendor_scan()
    log.info(GATE_LOG[_verdict])
    return _verdict != "clear"
# the row-menu LABEL -> the engine WORD (the offdisc-preview fix:
# the picker answers labels, _away_apply_row dispatches on words;
# an unmapped label used to fall through the engine's chain to the
# silent dim leg - the confession added engine-side, the map made
# EXHAUSTIVE here and pinned in awaymode_test):
MODE_BY_LABEL = {"blackout": "blackout", "dim": "dim",
                 DDC_TEXT: "off", DISC_TEXT: "offdisc"}
LABEL_BY_MODE = {word: label for label, word in MODE_BY_LABEL.items()}

# THE PREVIEW RUNS THIS LONG (owner law, Oct 22: the duration belongs
# IN the word - the button label interpolates it, the timer and the
# countdown seed ride it, and the suite pin re-sets the constant and
# expects the label to follow: a hardcoded "15s" next to a 10 s timer
# fails the pin).
PREVIEW_SEC = 10


def preview_label():
    return "preview (%ds)" % PREVIEW_SEC


def off_choice(bright, gdi):
    """A row's sub-mode menu, in the owner's reading order: dim, the
    two offs, and the painted blackout last. The D6 OFF - labeled
    'off (DDC fast)' - is offered on every panel this app REACHED
    (physical handles opened; the PROBE LAW says capability verdicts
    come from in-app attempts with a spent retry budget, never from a
    pre-sentence about firmware, and gray was always for
    never-reached panels only). Blackout is selectable because the
    state side ships it as an explicit row word (its label's tip says
    what it is); the refused row's degradation TO it is a confession,
    not a menu item. The DISCONNECT rides the adapter's own CCD door -
    no DDC/CI needed, firmware never consulted - so it is offered
    everywhere, and a row whose sdc leg refused after the budget KEEPS
    the choice: the dated status word is the state machine's truth,
    gray would be a pre-judgment."""
    vals = ["dim"]
    if bright.reachable(gdi):
        vals.append(DDC_TEXT)
    vals.append(DISC_TEXT)
    vals.append("blackout")
    return vals


TIP = {
    "refresh": "forces the same two-second desk re-read by hand - the "
               "belt for a panel swap that changes nothing observable, "
               "like an identical model behind a KVM. Shows what the "
               "config already says.",
    "ddc": "the quick software power-down - some panels refuse the "
           "DDC/CI write (KVM chains especially); a refused row falls "
           "back to blackout",
    "row": "dim keeps the panel awake and drops its brightness; "
           "blackout paints an opaque cover (a click wakes the desk); "
           "off (DDC fast) sends the panel's own power code, and a "
           "refused send falls back to blackout; off (disconnect) "
           "retracts the signal at the adapter - the same act as the "
           "re-connect entry in Windows settings. A write accepted "
           "but unproven keeps its mode and says (unverified); a "
           "refusal says so next to the panel - never silent. A "
           "preview applies THIS row's effect for %d seconds and "
           "reverts (second click cancels). A disconnected panel "
           "survives this app: Settings -> Display brings it back, "
           "and a lone screen is never stranded." % PREVIEW_SEC,
    "offdisc": "the path is retracted AT THE ADAPTER (SetDisplayConfig): "
               "the panel never hears a code, it loses its signal, and "
               "it comes back as a replug. The state lives in Windows' "
               "own display store - it survives this app, Settings -> "
               "Display is always the recovery door, and the boot belt "
               "re-raises rows this app configured before it died. The "
               "word 'off (disconnected)' is the one dark this app can "
               "prove: the store is asked, never the row list (a hub "
               "can latch a picture the store no longer believes), and "
               "when the store's slot and the panel's own EDID name "
               "dispute which screen a row is, the row refuses with the "
               "dated word instead of darkening the wrong panel. A "
               "refused retraction (Windows guards the last active "
               "display) degrades to blackout, confessed.",
    "level": "where dim rows park their brightness while away, 1 to "
             "40 percent - shared by every dim row (per-monitor "
             "levels are a planned follow-up).",
    "lock": "Windows locks when nobody MOVES; this locks when nobody "
            "is HERE, and any real away that darks a row locks the "
            "session - a preview never locks. Behind the lock the "
            "spell answers the camera and the session unlock, not "
            "the mouse: raw input is per-desktop and Winlogon owns "
            "the desk.",
    # the two rows that moved in from the power-plan tab (owner
    # ruling, Oct 22): the entries travel VERBATIM with their labels
    # and write paths; the sweep re-worded them in place.
    "fullscreen": "exclusive-fullscreen games swallow the power-off "
                  "broadcast - the app keeps its hands off while a "
                  "game owns the display.",
    # THE PLAIN WORDS (launch amendment 3, owner at the desk Oct 23):
    # the row's tip is for the desk, not the changelog - the
    # technical why lives HERE, in the comment: some monitors unplug
    # themselves from Windows on sleep and Windows re-lays the
    # windows wrong on return; the app remembers every window's rect
    # and the monitors' hardware identity before the dark, moves
    # everything back after any wake once the topology settles, and
    # a swapped or unplugged monitor means the saved desk is another
    # desk - nothing moves. The restore law itself (owner ruling):
    # back-to-CAPTURED-state, position AND minimization - the
    # minimize bit in the capture record is the contract, no
    # heuristics about who minimized; see wm/_restore._move.
    "restore_windows": "Put windows back where they were after the "
                       "screens wake. Un-minimizes windows that were "
                       "open when the screens went dark; what you "
                       "minimized yourself stays minimized.",
}


class _AwayMixin:
    # ------------------------------------------------------------------ away --
    def _away_card(self, left):
        box = self._card(left, "when the app turns the displays off",
                         "per-monitor off: dim the panel, paint the "
                         "dark, or take the signal away")
        # THE GLOBAL MODE ROW IS DEAD (owner ruling, Oct 22). What
        # remains is the away-decision trio in behavior chronology:
        # the hold-off (before the dark), the lock (at the dark), the
        # window restore (after the wake) - the outer two traveled in
        # from the power-plan tab's rows on purpose: they negotiate
        # this section's decisions.
        row = self._row(box, "hold off while a fullscreen app owns "
                             "the display", TIP["fullscreen"],
                        hint_chars=42)
        self.fullscreen_switch = ctk.CTkSwitch(
            row, text="", font=self.skin.font(12),
            command=self._fullscreen_changed,
            **self.skin.switch_style())
        self.fullscreen_switch.grid(row=0, column=1, sticky="e")
        if self.cfg["guards"]["fullscreen"]:
            self.fullscreen_switch.select()
        else:
            self.fullscreen_switch.deselect()
        row = self._row(box, "lock when away starts", TIP["lock"],
                        hint_chars=42)
        self.away_lock_box = ctk.CTkCheckBox(
            row, text="",
            command=self._away_lock_changed,
            font=self.skin.font(12), checkbox_width=18,
            checkbox_height=18, border_color=self.skin.border_raised,
            fg_color=self.skin.accent, hover_color=self.skin.accent,
            text_color=self.skin.text,
            text_color_disabled=self.skin.txt3)
        self.away_lock_box.set(bool((self.cfg.get("away") or {})
                                    .get("lock")))
        self.away_lock_box.grid(row=0, column=1, sticky="e")
        row = self._row(box, "put window positions back after wake",
                        TIP["restore_windows"], hint_chars=42)
        self.restore_switch = ctk.CTkSwitch(
            row, text="", font=self.skin.font(12),
            command=self._restore_changed,
            **self.skin.switch_style())
        self.restore_switch.grid(row=0, column=1, sticky="e")
        if self.cfg["power"].get("restore_windows"):
            self.restore_switch.select()
        else:
            self.restore_switch.deselect()

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
        self._sync_away_rows()
        self.after(900, self._away_poll)

    def _away_fill_rows(self):
        """Discard-and-refill (the _cam_rows idiom): every live panel
        owns a row in the card's row frame; the settings the rows
        edit come from cfg, so a rebuild cannot lie and cannot lose
        an answer. The gray state is PAINTED FROM THE ROW'S MODE WORD
        HERE, at build (the first-boot lie, owner Oct 22 - the pump/
        hold rows' lesson in segmented clothes: never wait for the
        first change event to tell a control it is disabled)."""
        for widget in self._away_row_frame.winfo_children():
            widget.destroy()
        self._away_rows = {}
        _live = wm.monitors()
        # THE VENDOR SCAN, ONE CALL PER BUILD/REFRESH (launch posture
        # + amendment 3, owner Oct 23): adapters are not hot - the
        # rebuild IS the recompute seam - and the verdict rides one
        # INFO line, so the log answers 'why is that button gray'
        # without a repro.
        _nvidia = vendor_gate()
        # the label (short name, duplicate-model tail, and the edge
        # descriptor WHEN IT CARRIES NEWS - law 7, Oct 22) is built at
        # the one seam every identity row shares
        for m, short in zip(_live, [mm.get("short") or mm.get("id")
                                    for mm in _live]):
            label = monitor_row_label(_live, m)
            vals = off_choice(wm._bright, m["gdi"])
            _offered = DDC_TEXT in vals
            _blocked = _nvidia and _offered
            if _blocked:
                # the verdict rides the LABEL (amendment 3): display
                # value only - the state key, the config word, and
                # the MODE_BY_LABEL domain stay DDC_TEXT below
                vals = [DDC_BLOCKED_LABEL if v == DDC_TEXT else v
                        for v in vals]
            row = self._row(
                self._away_row_frame, label,
                TIP["row"] + (" " + DDC_NVIDIA_TIP if _blocked else ""),
                hint_chars=42)
            seg = ctk.CTkSegmentedButton(
                row, values=vals, height=26, width=200,
                command=lambda v, s=short: self._away_submode_changed(s, v),
                **self.skin.segmented_style())
            mode = self._away_row_mode(short)
            # the display<->word seam of the suffixed label: a row the
            # chain answers DDC_TEXT SELECTS the suffixed button on a
            # blocked row (gray not lie; _away_submode_changed maps
            # back by startswith, and a disabled segment cannot be
            # clicked to trip it anyway)
            _cur = (DDC_BLOCKED_LABEL if mode == DDC_TEXT and _blocked
                    else mode)
            seg.set(_cur if _cur in vals else "dim")
            if not _offered:
                # gray not lie (owner correction): the choice is
                # ABSENT here because this app never reached the
                # panel's DDC door - said in one line, in words
                # about our reach, not the firmware's soul. The
                # disconnect is NOT absent: the CCD door is the
                # adapter's, and it does not ask the panel. The
                # test rides the PRE-SWAP offer (gate round, Oct 23):
                # a gated row carries the value under its suffix,
                # and a swap must never fake a never-reached
                # confession under the gray.
                self._away_says[short] = ("the power-code off needs a "
                                          "DDC/CI door; none answered "
                                          "for this monitor (the "
                                          "disconnect does not)")
            # TWO LINES, ONE GRID (owner ruling, Oct 24: the long
            # verdict text "makes the button huge" and the row clipped
            # its own tail): line 1 carries the panel's identity and
            # the mode picker; line 2 carries the brightness strip -
            # slider, its percent, the preview button - which used to
            # fight the picker for the same 500 px and lost (measured:
            # the slider and the % were gridded past the row's right
            # edge and simply never appeared). Now the picker owns its
            # line at the row's right edge and the strip owns the line
            # below it, so a longer monitor name or a longer verdict
            # moves NOTHING but its own line's height.
            seg.grid(row=0, column=1, columnspan=4, sticky="e")
            # the disconnect's paragraph hangs on the picker itself:
            # the label's tip is the row-wide one, and the off
            # choices are where the question forms (same hover path
            # as the card sub-lines). CTkSegmentedButton.bind raises
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
            # the DDC segment's OWN law text rides the segment button
            # (owner law, Oct 22: 'off (DDC fast)' says what it is
            # and where it breaks); same default-capture discipline.
            # THE LAUNCH GATE (owner, Oct 23): on an NVIDIA desk the
            # law text is REPLACED by the block text and the segment
            # is configured DISABLED - gray, not hidden: the choice
            # stays visible, the tip says why, and a configured-off
            # row keeps its selection UNDER the gray (the hold rows'
            # exact precedent: gray not lie). The state rides the
            # _buttons_dict/_state seam, and _sync_away_rows defends
            # it against the consent cascade.
            _ddc_tip = DDC_NVIDIA_TIP if _blocked else TIP["ddc"]
            try:
                _d = seg._buttons_dict.get(
                    DDC_BLOCKED_LABEL if _blocked else DDC_TEXT)
                if _d is not None:
                    _d.bind("<Enter>",
                            lambda e=None, w=_d, t=_ddc_tip:
                            self.tips._schedule(t, w), add="+")
                    _d.bind("<Leave>",
                            lambda e=None: self.tips._hide_soon(),
                            add="+")
                    if _blocked:
                        _d.configure(state="disabled")
            except Exception:
                pass
            value = ctk.CTkLabel(row, font=self.skin.font(12),
                                 **self.skin.text_style("sub"))
            # line 2, right-aligned strip (see the row's grid note above)
            value.grid(row=1, column=2, sticky="e", padx=(6, 0))
            slider = ctk.CTkSlider(row, from_=1, to=40,
                                   number_of_steps=39, width=150,
                                   command=self._away_level_changed,
                                   **self.skin.slider_style())
            slider.set(self._away_level())
            if mode != "dim":
                # an off-mode row's brightness control never gets to
                # look live, before any event fires (the knob-lie
                # family's away-card corpse, owner UAT Oct 22)
                slider.configure(state="disabled")
            slider.grid(row=1, column=1, sticky="e")
            value.configure(text="%d%%" % self._away_level())
            preview = ctk.CTkButton(row, text=preview_label(), width=84,
                                    command=lambda s=short:
                                    self._away_preview_clicked(s),
                                    **self.skin.secondary())
            preview.grid(row=1, column=3, sticky="e", padx=(6, 0))
            say = ctk.CTkLabel(self._away_row_frame, text="",
                               font=self.skin.font(10),
                               wraplength=350, justify="left", anchor="w",
                               **self.skin.text_style("sub"))
            self._away_rows[short] = {"row": row, "seg": seg, "vals": vals,
                                      "slider": slider, "value": value,
                                      "preview": preview, "say": say,
                                      "gdi": m["gdi"],
                                      # the launch gate's truth, per
                                      # row: the state the sync must
                                      # defend, the tip the probes read
                                      "ddc_blocked": _blocked,
                                      "ddc_tip": _ddc_tip}
            say.pack(anchor="w")
        self._sync_away_rows()

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
        """The MENU LABEL for the row: the triple shape normalize
        ships ({"blackout": b, "off": b, "offdisc": b}) and the
        legacy bare-bool row read honestly (one release - the file
        shape the dim wave wrote). THE SAME FALLBACK CHAIN the
        engine's _row_mode runs, mirrored for paint (owner ruling,
        Oct 22): no explicit mode -> the global [away] key when it
        names a row word -> the shipped default (offdisc, the label
        'off (disconnect)'). A present row's words answer byte-
        identical, the all-False triple is the explicit dim the card
        wrote. The answer is a MENU LABEL: the disconnect's and the
        DDC off's labels differ from their stored words, and the
        row-menu maps label -> triple."""
        away = self.cfg.get("away") or {}
        rows = away.get("monitors") or {}
        row = rows.get(short)
        if row is None or row == {}:
            word = away.get("mode")
            if word not in ("blackout", "dim", "off", "offdisc"):
                word = config.AWAY_ROW_DEFAULT
            return LABEL_BY_MODE[word]
        if isinstance(row, bool):
            return "blackout" if row else "dim"
        if row.get("offdisc"):
            return DISC_TEXT
        if row.get("off"):
            return DDC_TEXT
        return "blackout" if row.get("blackout") else "dim"

    # ------------------------------------------------------------- handlers --
    def _away_lock_changed(self):
        # the same write-is-applying law: the flag rides the live
        # away dict, the next real engage reads it at its own end
        # (every away mode can lock now - the engine locks on any
        # engage that darked a row, and the box grays for consent
        # only)
        self.cfg.setdefault("away", {})["lock"] = \
            bool(self.away_lock_box.get())
        self._sync_away_rows()
        self._save()

    def _restore_changed(self):
        # cfg["power"] IS monitor.power_cfg: the snapshot/restore hooks
        # read restore_windows fresh at every off/wake edge
        self.cfg["power"]["restore_windows"] = bool(
            self.restore_switch.get())
        self._save()

    def _fullscreen_changed(self):
        self.cfg["guards"]["fullscreen"] = bool(self.fullscreen_switch.get())
        self._save()

    def _away_submode_changed(self, short, label):
        if label == DDC_BLOCKED_LABEL:
            label = DDC_TEXT          # the suffixed display unwraps
            #                         to the state word (the blocked
            #                         segment cannot be clicked -
            #                         disabled - this is the seam's
            #                         honesty, not a live path)
        word = MODE_BY_LABEL.get(label)
        if word is None:
            return                          # a label from another menu
        rows = self.cfg.setdefault("away", {}).setdefault("monitors", {})
        rows[short] = {"blackout": word == "blackout",
                       "off": word == "off",
                       "offdisc": word == "offdisc"}
        #                    the file shape stays byte-identical: the
        #                    dim choice arrives as the all-False
        #                    triple it always wrote
        self._sync_away_rows()
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

    # -------------------------------------------------------------------------------------------------------------------- preview --
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
                self._away_cd_left = PREVIEW_SEC
                self._away_countdown()
        timer = threading.Timer(PREVIEW_SEC,
                                lambda: self._away_expiry(short, rec))
        timer.daemon = True              # a quit with a live preview must
        timer.start()                    # never hang the process
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
            set_text(r["preview"], preview_label())
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
    def _sync_away_rows(self):
        """KNOB-FROM-TRUTH, both branches, for the whole card (the
        pump/hold idiom of 60e0348/e59383a, applied to the away rows
        after the first-boot lie: the gray state PAINTS FROM THE MODE
        AT BUILD and on every reveal - the detection tab's
        SWITCH_SYNC entry calls this by name, the builder ends call
        it directly, and no interaction is ever the first to learn
        the truth). The consent band (the reskin wave) owns the
        card-wide gray through _gate_widgets, never a bare state=: a
        mode pick must not unlock a consent-greyed card. Per row: the
        picker shows the row's own mode word (the fallback chain
        applied), the brightness slider lives only on a dim row and
        is DISABLED wherever it is not the row's business, and the
        preview button - the test of the mode itself - rides consent
        only. The trio above the rows paints from cfg: the lock
        speaks for EVERY away mode (the engine locks any engage that
        darked a row - owner law, Oct 22), so its box grays for
        consent alone."""
        band = getattr(self, "_consent_band", None)
        consent = True if band is None else \
            bool(self.cfg["camera"].get("enabled"))
        away = self.cfg.get("away") or {}
        try:
            want = bool(away.get("lock"))
            if bool(self.away_lock_box.get()) != want:
                self.away_lock_box.set(want)          # set fires no command
        except Exception:
            pass                                      # rebuilt mid-toggle
        self._pair_switch(self.away_lock_box, consent)
        p = self.cfg["power"]
        self.restore_switch.select() if p.get("restore_windows") \
            else self.restore_switch.deselect()
        self._pair_switch(self.restore_switch, consent)
        self.fullscreen_switch.select() \
            if self.cfg["guards"]["fullscreen"] \
            else self.fullscreen_switch.deselect()
        self._pair_switch(self.fullscreen_switch, consent)
        for short, r in self._away_rows.items():
            state = "normal" if consent else "disabled"
            gated = False
            if band is not None and hasattr(self, "_gate_widgets"):
                try:
                    self._gate_widgets(r["row"], state)
                    gated = True
                except Exception:
                    pass
            if not gated:
                for key in ("seg", "preview"):
                    try:
                        r[key].configure(state=state)
                    except Exception:
                        pass
            # a segmented picker keeps its segments in their OWN
            # buttons (the power card's gray law reads the same
            # seam) - cascade consent into them whatever the band
            # walker did, diff-cheap. THE LAUNCH GATE survives the
            # cascade (owner, Oct 23): the gated DDC segment answers
            # disabled at EVERY sync, consent on or off, band or no
            # band - the gray is the law's own, never a paint race.
            try:
                for _lbl, _b in r["seg"]._buttons_dict.items():
                    _want = ("disabled"
                             if r.get("ddc_blocked") and _lbl in (
                                 DDC_TEXT, DDC_BLOCKED_LABEL)
                             else state)
                    if _b._state != _want:
                        _b.configure(state=_want)
            except Exception:
                pass
            mode = self._away_row_mode(short)
            if r.get("ddc_blocked") and mode == DDC_TEXT:
                mode = DDC_BLOCKED_LABEL       # the suffixed value is
            #                                 the picker's own; the
            #                                 chain's word maps here
            if mode in r["vals"] and r["seg"].get() != mode:
                r["seg"].set(mode)                    # set fires no command
            dim_row = consent and mode == "dim"
            try:                                      # the slider is the
                #                            row's mode's own business,
                #                            band or no band: a dim
                #                            control on an off-mode row
                #                            is the knob-lie in place
                r["slider"].configure(state="normal" if dim_row
                                      else "disabled")
            except Exception:
                pass
            if mode != "dim":
                # blackout hides the paint's level, off the panel's -
                # only a DIM row has a brightness to speak of
                r["slider"].grid_forget()
                r["value"].grid_forget()
            elif dim_row:
                # line 2 of the row's own grid (the Oct-24 two-line law
                # in _away_fill_rows): the strip parks under the picker
                r["slider"].grid(row=1, column=1, sticky="e")
                r["value"].grid(row=1, column=2, sticky="e",
                                padx=(6, 0))
            r["value"].configure(text="%d%%" % self._away_level())
            self._away_say(short)

    def _pair_switch(self, widget, consent):
        """Enable/gray one moved-in switch (diff-guarded; CTkSwitch
        tracks its own state string) - the trio's consent gate, the
        band or the bare card both ending here."""
        want = "normal" if consent else "disabled"
        try:
            if widget.cget("state") != want:
                widget.configure(state=want)
        except Exception:
            pass

    def _away_say(self, short):
        """The confession surface: the engine's live status word wins
        over the last preview's word (a real spell outranks a test).
        This is also the carry the DDC law owed (owner, Oct 22): the
        engine's refused-VCP word - 'off refused - blackout instead
        (say)' - lands HERE, next to the panel it happened to, for as
        long as the spell holds; the poll below is the one field's
        delivery, zero new plumbing."""
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
