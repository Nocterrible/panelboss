"""Profiles tab detail panes: live windows, the pin
editor, pins list, status section.

SIZE LAW: measured 419 (Oct 15 LIST-law recount - the two-
sub-column prose retired with the flow, from the Oct 14 loud-voice
wave's 440; the status
label's danger paint landed here; the Oct 13 claim - the checkbox's
both-branch paint and the knob-lie sync entry, corrected in-commit
after drifting from ~360 - is superseded by this one).
These are the pane's five section fills plus the
row builder - one story (what a section looks like when painted),
split from the VERBS (_prof_pins.py) that mutate them in place, and
from the row-flow helper (_PinMixin._pin_cols) the two pin lists
share. The fills must stay together for _repaint's readers;
splitting the row builder off would strand _pin_row_text from its
only caller's view.
"""

from __future__ import annotations

import customtkinter as ctk

from .. import theme
from ... import profiles
from ._constants import TIPS, WAIT_CHOICES
from ._widgets import SkewCombo, set_text
from ._present import clip_siblings
from ._scroll import ScrollHost


class _EditorMixin:
    def _fill_live(self):
        """The pick-list section: every open window, the chosen one
        highlighted. The row buttons are remembered, so selecting a
        window can re-highlight WITHOUT rebuilding the list at all.
        Oct 12: lives on the right column. Oct 15 (owner order, UAT):
        the list is a LIST - one packed row per window, full width -
        the two-sub-column flow is retired in _pin_cols itself."""
        self._prof_detail = self._prof_pins_body  # _section's parent
        #                    (each pin fill re-points it, so a solo
        #                    _repaint("live") builds in the right col)
        sec = self._section("live", pady=(theme.S_ROW, 0))
        ed = self._pin_edit
        cell = ctk.CTkFrame(sec, fg_color="transparent")
        cell.pack(anchor="w", fill="x")
        head = ctk.CTkFrame(cell, fg_color="transparent")
        head.pack(anchor="w")
        ctk.CTkLabel(head, text="pin an app - click a window, it "
                                "lands in the editor below",
                     font=self.skin.font(13, "bold"),
                     **self.skin.text_style()).pack(side="left")
        self._hint(cell, TIPS["profile_match"])
        lif = ScrollHost(sec, bg=self.skin.panel, width=490, height=132)
        lif.pack(fill="x")
        self._live_rows = {}
        live = profiles.windows_now()
        cols = self._pin_cols(lif.inner, len(live))
        bw = 460                         # the LIST law: one column,
        for i, l in enumerate(live):     # so always the wide button
            key = (l["proc"], l["title"])
            picked = ed["pick"] == key
            b = ctk.CTkButton(
                cols[i % len(cols)], width=bw, anchor="w",
                text="%s   %s %dx%d at %d,%d on %s" % (
                    (l["title"] or "(untitled)")[:40],
                    l["proc"][:14], l["rect"][2], l["rect"][3],
                    l["rect"][0], l["rect"][1],
                    l.get("monitor") or "?"),
                font=self.skin.font(11),
                command=lambda k=key: self._pin_select(k),
                fg_color=self.skin.accent if picked
                else self.skin.field_bg,
                hover_color=self.skin.accent_hover,
                text_color=self.skin.on_accent if picked else self.skin.text,
                corner_radius=self.skin.radius)
            b.pack(anchor="w", pady=(theme.S_FIELD, 0))
            self._live_rows[key] = b
        if not live:
            ctk.CTkLabel(lif.inner, text="no open windows to pick",
                         font=self.skin.font(11),
                         **self.skin.text_style("sub")).pack(
                anchor="w", pady=theme.S_FIELD, padx=theme.S_FIELD)


    def _restyle_live(self):
        """the highlight move, without a rebuild: paint exactly the
        rows whose picked-state changed"""
        pick = self._pin_edit["pick"]
        for key, b in getattr(self, "_live_rows", {}).items():
            on = key == pick
            try:
                b.configure(fg_color=self.skin.accent if on
                            else self.skin.field_bg,
                            text_color=self.skin.on_accent if on
                            else self.skin.text)
            except Exception:
                pass                    # a destroyed row: harmless


    def _fill_editor(self):
        """The conditions + fine print for the editor's subject, live
        or remembered. The section carries its own 'editing:' title -
        it is what changes when a seat is clicked, and the title is
        the proof the click landed.

        THE FURNITURE IS LAID ONCE (owner ruling, Oct 24 part 2:
        "editing a pinned app still redraws half the UI in an
        extremely ugly way"). Every field save goes through
        _sync_editor, which configures the widgets whose content
        actually moved; nothing below is rebuilt by an edit - only a
        real subject change (this fill, or a full render) comes here.
        The advanced half stays LAZY (its absence before the flip is
        pinned by power_assistant_test) but it is built into its own
        slot frame, so revealing it costs two rows, never the editor."""
        self._prof_detail = self._prof_pins_body  # _section's parent
        sec = self._section("editor", pady=(theme.S_FIELD, 0))
        self._ed_sec = sec
        self._ed_head = ctk.CTkLabel(sec, text="",
                                     font=self.skin.font(13, "bold"),
                                     **self.skin.text_style())
        self._ed_head.pack(anchor="w")
        row = self._row(sec, "window matching", TIPS["profile_match"])
        self.match_menu = SkewCombo(
            row, values=list(profiles.MATCH_MODES), width=150,
            command=self._pin_match, **self.skin.menu_style())
        self.match_menu.grid(row=0, column=1, sticky="e")
        row = self._row(sec, "open it if missing",
                        TIPS["profile_pin_open"])
        # a SWITCH, not a bare checkbox (owner Oct 15, the legibility
        # pass): an 18 px empty checkbox with no text beside it is a
        # rounded outline on a dark canvas - it read as a broken widget,
        # not an off toggle. Every other lone boolean in the house (live
        # preview, the movie-theater master) is a switch.
        self.pin_open_box = ctk.CTkSwitch(row, text="",
                                          font=self.skin.font(12),
                                          command=self._pin_open,
                                          **self.skin.switch_style())
        self.pin_open_box.grid(row=0, column=1, sticky="e")
        # the advanced half's own SLOT: packed only while the wish
        # stands (nothing of it exists before the first flip - the
        # suite's 'advanced rows leak' pin keeps its meaning), built
        # once by _ed_adv_build, and the only structure a wish flip
        # ever costs
        self._ed_slot = ctk.CTkFrame(sec, fg_color="transparent")
        self._ed_adv = None
        # the note lines: a POOL of labels, reused (a slot that is not
        # needed is unmapped, never destroyed). The fine print is the
        # one variable-length list in this section - it is the only
        # thing a subject change rewrites.
        self._ed_notes = ctk.CTkFrame(sec, fg_color="transparent")
        self._ed_notes.pack(fill="x")
        self._ed_note_lbls = []
        self._ed_cbtns = ctk.CTkFrame(sec, fg_color="transparent")
        self._ed_cbtns.pack(anchor="w", pady=(theme.S_FIELD, 0))
        self._ed_commit = ctk.CTkButton(self._ed_cbtns, text="pin it",
                                        width=130,
                                        command=self._pin_commit,
                                        **self.skin.primary())
        self._ed_commit.pack(side="left")
        self._ed_cancel = ctk.CTkButton(self._ed_cbtns, text="cancel",
                                        width=80,
                                        command=self._pin_cancel,
                                        **self.skin.secondary())
        self._sync_editor()


    def _ed_adv_build(self):
        """The wish's advanced half, built ONCE into its slot: how long
        patience lasts, and WHERE the wish knocks. The captured exe is
        often the wrong door (store stubs, updater wrappers) and only
        the human knows which launcher opens the window. Idempotent -
        _sync_editor may call it on every flip."""
        adv = getattr(self, "_ed_adv", None)
        if adv is not None and adv.winfo_exists():
            return
        adv = ctk.CTkFrame(self._ed_slot, fg_color="transparent")
        adv.pack(fill="x")
        row = self._row(adv, "wait up to", TIPS["profile_pin_wait"])
        self.pin_wait_menu = SkewCombo(
            row, values=["%d s" % s for s in WAIT_CHOICES],
            width=110, command=self._pin_wait,
            **self.skin.menu_style())
        self.pin_wait_menu.grid(row=0, column=1, sticky="e")
        row = self._row(adv, "launches", TIPS["profile_pin_exe"])
        exf = ctk.CTkFrame(row, fg_color="transparent")
        self._ed_exe_lbl = ctk.CTkLabel(exf, text="",
                                        font=self.skin.font(10),
                                        **self.skin.text_style("sub"))
        self._ed_exe_lbl.pack(side="left")
        ctk.CTkButton(exf, text="browse...", width=80,
                      command=self._pin_browse,
                      **self.skin.secondary()).pack(side="left",
                                                    padx=(6, 0))
        exf.grid(row=0, column=1, sticky="e")
        self._ed_adv = adv
        # GATE FINDING 3's class, twice paid for: widgets born after
        # the build-time clip pass are flag-free, so a fresh row can
        # paint over whatever overlaps it until told (the same seam
        # _repaint calls clip_siblings for). Idempotent.
        clip_siblings(adv)


    @staticmethod
    def _editor_notes(ed, picked, saved_row, live):
        """The honest fine print, only ever saying something true:
        which rect the pin saves, that a process pin drags every
        window of that app, and what "open it" really is. Pure over
        what it is handed, so the fill and the in-place sync can
        never disagree about the words."""
        notes = []
        if picked:
            notes.append("will save: %s %dx%d at %d,%d on %s" % (
                picked["proc"][:14], picked["rect"][2],
                picked["rect"][3], picked["rect"][0],
                picked["rect"][1], picked.get("monitor") or "?"))
        elif saved_row:
            notes.append("saved seat: %dx%d at %d,%d on %s (the "
                         "window is closed; move the window and hit "
                         "update pin while it is open to move the "
                         "seat)" % (saved_row["rect"][2],
                                    saved_row["rect"][3],
                                    saved_row["rect"][0],
                                    saved_row["rect"][1],
                                    saved_row.get("monitor") or "?"))
        else:
            notes.append("pick one of the open windows above")
        if (picked or saved_row) and ed["match"] == "process":
            who = (picked or saved_row)["proc"].lower()
            n = sum(1 for l in live if l["proc"].lower() == who)
            if n > 1:
                notes.append("WARNING: %d windows of %s are open - "
                             "this pin moves ALL of them, not just "
                             "the one you picked" % (n, who))
        if (picked or saved_row) and ed["open"]:
            exe = ((ed["exe"] or (picked or {}).get("exe")
                    or (saved_row or {}).get("exe") or "?")
                   ).split("\\")[-1]
            notes.append("will run %s to wake it - a naive exe run; "
                         "store apps and stub launchers may start "
                         "nothing, then it waits %d s and reports"
                         % (exe, ed["wait"]))
        return notes


    def _notes_show(self, lines):
        """Paint the fine print from the pool: configure what is
        reused, map what is needed, unmap the tail. Diff-guarded
        (set_text) because the sync runs on every field save and a
        no-op configure redraws a CTk canvas whole."""
        lbls = getattr(self, "_ed_note_lbls", None)
        if lbls is None:
            return                      # no editor on this pane
        while len(lbls) < len(lines):
            lbls.append(ctk.CTkLabel(
                self._ed_notes, text="", font=self.skin.font(10),
                wraplength=460, justify="left", anchor="w",
                **self.skin.text_style("sub")))
        for i, lbl in enumerate(lbls):
            try:
                if i < len(lines):
                    set_text(lbl, lines[i])
                    if lbl.winfo_manager() != "pack":
                        lbl.pack(anchor="w", pady=(theme.S_FIELD, 0))
                elif lbl.winfo_manager() == "pack":
                    lbl.pack_forget()
            except Exception:
                pass                    # dying pane: the fill rebuilds


    def _sync_editor(self):
        """THE EDITOR'S IN-PLACE PAINT (owner ruling, Oct 24 part 2: a
        pin edit repaints its row, not its neighbourhood). Every save
        path lands here instead of rebuilding the section: the heading
        word, the match menu, the wish switch, the advanced slot's
        packedness and its two fields, the commit word, the cancel
        button's presence, and the fine print - each one configured
        only when its content actually moved. Cost is a handful of
        diffs, not 125 ms of CTk construction.

        A missing editor is a MISS, never an error: a fill that has not
        run yet, or a pane mid-swap, has no furniture to configure and
        the next render paints the same truth from its own dicts."""
        sec = getattr(self, "_ed_sec", None)
        if sec is None or not sec.winfo_exists():
            return
        ed = self._pin_edit
        prof = self._prof_data["profiles"].get(self._prof_sel) \
            or {"wins": []}
        live = profiles.windows_now()
        picked = next((w for w in live
                       if (w["proc"], w["title"]) == ed["pick"]), None)
        saved_row = next((w for w in prof["wins"]
                          if (w["proc"], w["title"]) == ed["key"]),
                         None) if ed["key"] else None
        set_text(self._ed_head,
                 ("editing: %s" % (ed["key"][1] or ed["key"][0])
                  if ed["key"] else "the editor"))
        self._set_menu(self.match_menu, ed["match"])
        # knob-from-truth, BOTH branches (the editor checkbox is the
        # family's ninth member): the wish state comes from the
        # editor's dict, and the false arm must paint, not lean on the
        # widget's build default
        self.pin_open_box.select() if ed["open"] \
            else self.pin_open_box.deselect()
        if ed["open"]:
            self._ed_adv_build()
            if self._ed_slot.winfo_manager() != "pack":
                self._ed_slot.pack(fill="x", before=self._ed_notes)
                # RE-MEASURE, DON'T REPAINT (measured, Oct 24): the
                # reveal grows the editor, so the page's scroll region
                # follows (the wheel must still know the pane). A
                # scoped present(self._prof_pins_body) was tried HERE
                # to collapse the pane's own repaint into one pass and
                # it came back WORSE in the mid-repaint frame - the
                # ERASE pass tore the column (labels truncated, the
                # seat rows gone) where the loop's own repaint only
                # ghosts the moved glyphs. The loop keeps this paint.
                self._page_region()
            self._set_menu(self.pin_wait_menu, "%d s" % ed["wait"])
            self._set_menu(self.pin_wait_menu, "%d s" % ed["wait"])
            show = (ed["exe"]
                    or (picked or saved_row or {}).get("exe")
                    or "(no exe captured yet - browse picks one)")
            set_text(self._ed_exe_lbl,
                     show if len(show) <= 44 else "..." + show[-41:])
        elif self._ed_slot.winfo_manager() == "pack":
            self._ed_slot.pack_forget()
        set_text(self._ed_commit, "update pin" if ed["key"] else "pin it")
        if ed["key"] or ed["pick"]:
            if self._ed_cancel.winfo_manager() != "pack":
                self._ed_cancel.pack(side="left", padx=(6, 0))
        elif self._ed_cancel.winfo_manager() == "pack":
            self._ed_cancel.pack_forget()
        self._notes_show(self._editor_notes(ed, picked, saved_row, live))



    # ----------------------------------------------------------- repaint --
    def _sync_editor_switches(self):
        """Knob-lie belt (see _power._sync_power_switches): the open-
        wish box from the editor's own dict - the truth _fill_editor
        reads. The pane's swap discipline owns the widget slot, so a
        stale reference is a miss, not an error: the fresh fill paints
        from the same dict."""
        ed = getattr(self, "_pin_edit", None)
        box = getattr(self, "pin_open_box", None)
        if ed is None or box is None:
            return
        try:
            box.select() if ed["open"] else box.deselect()
        except Exception:
            pass                            # destroyed row: harmless


    def _fill_pins(self):
        """The seats this profile owns - below the editor on purpose
        (see the reorder note in _profiles_fill). Oct 12 (owner,
        screenshot): the heading, the two buttons and the list own
        ONE ROW EACH - the old pack mixed side="left" head/buttons
        with a top-pack ScrollHost, so the buttons crowded into the
        heading's band and the ScrollHost landed squished right.
        Oct 15 (owner order, UAT): the list is a LIST - one row per
        seat, full width - the Oct-12 two-sub-column sketch is
        retired where it lives, in _PinMixin._pin_cols."""
        self._prof_detail = self._prof_pins_body  # _section's parent
        sec = self._section("pins", pady=(theme.S_ROW, 0))
        prof = self._prof_data["profiles"].get(self._prof_sel) \
            or {"wins": []}
        hrow = ctk.CTkFrame(sec, fg_color="transparent")
        hrow.pack(fill="x")
        head = ctk.CTkLabel(hrow, text="pinned apps",
                            font=self.skin.font(13, "bold"),
                            **self.skin.text_style())
        head.pack(anchor="w")
        # UI-1c reversal (gate catch): the paragraph rides this heading's
        # hover, the exact path the old "?" chip used
        head.bind("<Enter>",
                  lambda e=None: self.tips._schedule(TIPS["profile_pins"],
                                                     head),
                  add="+")
        head.bind("<Leave>", lambda e=None: self.tips._hide_soon(), add="+")
        brow = ctk.CTkFrame(sec, fg_color="transparent")
        brow.pack(fill="x", pady=(theme.S_FIELD, 0))
        ctk.CTkButton(brow, text="pin every open app", width=150,
                      command=self._prof_pin_all,
                      **self.skin.secondary()).pack(side="left")
        ctk.CTkButton(brow, text="re-scan", width=80,
                      command=self._prof_rescan,
                      **self.skin.secondary()).pack(side="left",
                                                    padx=(theme.S_FIELD, 0))
        # _hint is the hover-era no-op; kept so every old call site compiles
        self._hint(sec, TIPS["profile_pins"])
        pinf = ScrollHost(sec, bg=self.skin.panel, width=490, height=112)
        pinf.pack(fill="x", pady=(theme.S_FIELD, 0))
        # the in-place-update trackers (owner ruling, Oct 12): a pin
        # click appends or reconfigures ONE row, an unpin destroys its
        # own row - the section itself only rebuilds on a full render
        # or the bulk verb
        self._pin_rows = {}
        self._pins_inner = pinf.inner
        # placeholder BEFORE the rows loop (gate finding 2): a row's
        # x-button emptied mid-fill must find it built, not None
        self._pins_empty = ctk.CTkLabel(
            pinf.inner,
            text="nothing pinned yet - seat an app above",
            font=self.skin.font(11),
            **self.skin.text_style("sub"))
        live_key = {(w["proc"], w["title"]): w
                    for w in profiles.windows_now()}
        # the LIST law (owner order, Oct 15): _pin_cols answers ONE
        # column now, so every row button wears the full width;
        # _pin_row_upsert's appends match the layout through the same
        # _pin_btn_w.
        self._pins_cols = cols = self._pin_cols(pinf.inner,
                                                len(prof["wins"]))
        self._pin_btn_w = 400
        for i, w in enumerate(prof["wins"]):
            self._pin_row(cols[i % len(cols)], w,
                          live_key.get((w["proc"], w["title"])))
        if not prof["wins"]:
            self._pins_empty.pack(anchor="w", pady=theme.S_FIELD,
                                  padx=theme.S_FIELD)


    def _fill_status(self):
        """ONE label, idempotent (owner ruling, Oct 12): the first
        fill builds it inside the status section; every later fill -
        every _repaint("status") there is - just configures its text,
        so a status change repaints ZERO structure. The loud-voice
        wave (Oct 14): while _prof_err is set the label paints in
        skin.danger - the COLOR is the shout, the sub font is kept
        (a red paragraph that still reads as fine print shouts
        exactly as hard as a red headline)."""
        style = dict(self.skin.text_style("sub"))
        if getattr(self, "_prof_err", False):
            style["text_color"] = self.skin.danger
        lbl = getattr(self, "_status_lbl", None)
        if lbl is not None and lbl.winfo_exists():
            lbl.configure(text=self._prof_msg, **style)
            return
        sec = self._section("status")
        self._status_lbl = ctk.CTkLabel(
            sec, text=self._prof_msg,
            font=self.skin.font(11), wraplength=560, justify="left",
            anchor="w", **style)
        self._status_lbl.pack(anchor="w", pady=(theme.S_FIELD, 0))


    def _pin_hover_full(self, btn, w, live):
        """The hover carrier's live decision (gate finding 3): the
        bubble shows the full label ONLY while the row reads
        shortened - read fresh, so the in-place upsert can never
        strand the tooltip on the row's birth state."""
        bubble = self._pin_row_text(w, live, full=True)
        if bubble != btn.cget("text"):
            # only shortened rows get a bubble - the full label IS
            # the text otherwise, and a bubble under the cursor that
            # says nothing is noise with a tooltip costume
            self.tips._schedule(bubble, btn)
        return "break"

    def _pin_row_text(self, w, live, full=False):
        """The row's whole label, one builder: used at fill time and
        when an update-pin reconfigures the row in place (Oct 12).
        Badges tell the truth the plain text cannot: closed,
        'open it', a non-default match. Oct 12 (owner): a pin whose
        EFFECTIVE match (the row's, else the profile's, else
        process - the same chain the runtime applies) is PROCESS
        reads shortened: the exe basename leads, the proc echo
        drops. The full title-led label survives in the row's hover
        bubble - the caller passes full=True for it. Title-matched
        pins keep their title label."""
        badges = ""
        if w.get("open"):
            try:
                wt = int(w.get("wait") or 0)
            except (TypeError, ValueError):
                wt = 0
            badges += "  [open it%s]" % (
                "" if not wt else " in %ds" % wt)   # a 0-s wait is the
            #                                       bare verb (gate f1;
            #                                       the old ==30 special
            #                                       case was the former
            #                                       default's ghost)
            ex = (w.get("exe") or "").split("\\")[-1].lower()
            if ex and ex != (w["proc"] or "").lower():
                badges += "  [via %s]" % ex[:18]
        if (w.get("match") or "process") != "process":
            badges += "  [%s]" % w.get("match")
        seat = "%dx%d at %d,%d on %s%s%s" % (
            w["rect"][2], w["rect"][3], w["rect"][0], w["rect"][1],
            w.get("monitor") or "?",
            "" if live else "  (closed)", badges)
        whole = "%s  %s  %s" % ((w["title"] or w["proc"])[:36],
                                w["proc"][:14], seat)
        if full:
            return whole
        prof = (self._prof_data.get("profiles") or {}).get(
            self._prof_sel) or {}
        if (w.get("match") or prof.get("match") or "process") \
                .lower() == "process":
            # basename of the exe (or of the proc when no exe was
            # captured) - the house idiom is the split, not pathlib
            for src in (w.get("exe"), w.get("proc")):
                base = (src or "").replace("/", "\\") \
                    .split("\\")[-1].strip()[:36]
                if base:
                    return "%s  %s" % (base, seat)
        return whole


    def _pin_row(self, parent, w, live):
        """One pinned seat. The row itself is the button that lifts
        the pin back into the editor ('click it and it pops back
        up'), the pencil says the same out loud, the x forgets the
        seat - and hands the row's OWN frame to the removal, so the
        unpin destroys just this widget (Oct 12). Registers into
        _pin_rows under the pin's (proc, title) identity so a later
        commit can find and reconfigure it without a section swap.
        The button width follows the section's flow (_pin_btn_w:
        narrow inside a sub-column); a shortened row keeps the full
        label on its hover bubble."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(anchor="w", fill="x", pady=theme.S_FIELD)
        btn = ctk.CTkButton(
            row, width=getattr(self, "_pin_btn_w", 400), anchor="w",
            text=self._pin_row_text(w, live),
            font=self.skin.font(11),
            command=lambda r=w: self._pin_load(r),
            fg_color="transparent", hover_color=self.skin.panel,
            text_color=self.skin.text,
            corner_radius=self.skin.radius)
        btn.pack(side="left")
        # hover ALWAYS binds (gate finding 3): the decision "is this
        # row shortened?" is taken live at hover time, so a row that
        # was born with its full label and later became a process
        # pin still carries the whole story - a conditional bind
        # froze the bubble on the birth state and the in-place
        # upsert never rebinds
        btn.bind("<Enter>",
                 lambda e=None, b=btn: self._pin_hover_full(b, w, live),
                 add="+")
        btn.bind("<Leave>", lambda e=None: self.tips._hide_soon(),
                 add="+")
        ctk.CTkButton(row, text="edit", width=48,
                      command=lambda r=w: self._pin_load(r),
                      **self.skin.secondary()).pack(side="left",
                                                    padx=(theme.S_FIELD, 0))
        ctk.CTkButton(row, text="x", width=30,
                      command=lambda r=w, f=row: self._pin_remove(r, f),
                      **self.skin.secondary()).pack(side="left",
                                                    padx=(theme.S_FIELD, 0))
        self._pin_rows[(w["proc"], w["title"])] = (row, btn)

