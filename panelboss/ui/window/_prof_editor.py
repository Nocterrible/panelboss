"""Profiles tab detail panes: live windows, the pin
editor, pins list, status section.

SIZE LAW: ~360. These are the pane's five section fills plus the
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
from ._widgets import SkewCombo
from ._scroll import ScrollHost


class _EditorMixin:
    def _fill_live(self):
        """The pick-list section: every open window, the chosen one
        highlighted. The row buttons are remembered, so selecting a
        window can re-highlight WITHOUT rebuilding the list at all.
        Oct 12: lives on the right column; past four windows the
        rows flow across two sub-columns (taller, narrower - owner
        sketch) via _pin_cols."""
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
        bw = 230 if len(cols) > 1 else 460
        for i, l in enumerate(live):
            key = (l["proc"], l["title"])
            picked = ed["pick"] == key
            b = ctk.CTkButton(
                cols[i % len(cols)], width=bw, anchor="w",
                text="%s   %s %dx%d at %d,%d on %s" % (
                    (l["title"] or "(untitled)")[:40],
                    l["proc"][:14], l["rect"][2], l["rect"][3],
                    l["rect"][0], l["rect"][1],
                    l["monitor"] or "?"),
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
        the proof the click landed."""
        self._prof_detail = self._prof_pins_body  # _section's parent
        sec = self._section("editor", pady=(theme.S_FIELD, 0))
        prof = self._prof_data["profiles"].get(self._prof_sel) \
            or {"wins": []}
        ed = self._pin_edit
        ctk.CTkLabel(sec,
                     text=("editing: %s" % (ed["key"][1] or ed["key"][0])
                           if ed["key"] else "the editor"),
                     font=self.skin.font(13, "bold"),
                     **self.skin.text_style()).pack(anchor="w")
        live = profiles.windows_now()
        picked = next((w for w in live
                       if (w["proc"], w["title"]) == ed["pick"]), None)
        saved_row = next((w for w in prof["wins"]
                          if (w["proc"], w["title"]) == ed["key"]),
                         None) if ed["key"] else None
        row = self._row(sec, "window matching", TIPS["profile_match"])
        self.match_menu = SkewCombo(
            row, values=list(profiles.MATCH_MODES), width=150,
            command=self._pin_match, **self.skin.menu_style())
        self.match_menu.set(ed["match"])
        self.match_menu.grid(row=0, column=1, sticky="e")
        row = self._row(sec, "open it if missing",
                        TIPS["profile_pin_open"])
        self.pin_open_box = ctk.CTkCheckBox(row, text="",
                                            font=self.skin.font(12),
                                            command=self._pin_open,
                                            checkbox_width=18,
                                            checkbox_height=18,
                                            border_color=self.skin.border_raised,
                                            fg_color=self.skin.accent,
                                            hover_color=self.skin.accent)
        self.pin_open_box.grid(row=0, column=1, sticky="e")
        if ed["open"]:
            self.pin_open_box.select()

        if ed["open"]:
            # the wish's advanced half: how long patience lasts,
            # and WHERE the wish knocks. the captured exe is often
            # the wrong door (store stubs, updater wrappers) and
            # only the human knows which launcher opens the window
            row = self._row(sec, "wait up to",
                            TIPS["profile_pin_wait"])
            self.pin_wait_menu = SkewCombo(
                row, values=["%d s" % s for s in WAIT_CHOICES],
                width=110, command=self._pin_wait,
                **self.skin.menu_style())
            self.pin_wait_menu.set("%d s" % ed["wait"])
            self.pin_wait_menu.grid(row=0, column=1, sticky="e")
            row = self._row(sec, "launches", TIPS["profile_pin_exe"])
            exf = ctk.CTkFrame(row, fg_color="transparent")
            show = (ed["exe"]
                    or (picked or saved_row or {}).get("exe")
                    or "(no exe captured yet - browse picks one)")
            ctk.CTkLabel(exf,
                         text=show if len(show) <= 44
                         else "..." + show[-41:],
                         font=self.skin.font(10),
                         **self.skin.text_style("sub")).pack(
                side="left")
            ctk.CTkButton(exf, text="browse...", width=80,
                          command=self._pin_browse,
                          **self.skin.secondary()).pack(side="left",
                                                        padx=(6, 0))
            exf.grid(row=0, column=1, sticky="e")

        # the honest fine print, only ever saying something true:
        # which rect the pin saves, that a process pin drags every
        # window of that app, and what "open it" really is
        notes = []
        if picked:
            notes.append("will save: %s %dx%d at %d,%d on %s" % (
                picked["proc"][:14], picked["rect"][2],
                picked["rect"][3], picked["rect"][0],
                picked["rect"][1], picked["monitor"] or "?"))
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
        for t in notes:
            ctk.CTkLabel(sec, text=t,
                         font=self.skin.font(10), wraplength=460,
                         justify="left", anchor="w",
                         **self.skin.text_style("sub")).pack(
                anchor="w", pady=(theme.S_FIELD, 0))
        cbtns = ctk.CTkFrame(sec, fg_color="transparent")
        cbtns.pack(anchor="w", pady=(theme.S_FIELD, 0))
        ctk.CTkButton(cbtns,
                      text="update pin" if ed["key"] else "pin it",
                      width=130, command=self._pin_commit,
                      **self.skin.primary()).pack(side="left")
        if ed["key"] or ed["pick"]:
            ctk.CTkButton(cbtns, text="cancel", width=80,
                          command=self._pin_cancel,
                          **self.skin.secondary()).pack(side="left",
                                                        padx=(6, 0))


    def _fill_pins(self):
        """The seats this profile owns - below the editor on purpose
        (see the reorder note in _profiles_fill). Oct 12 (owner,
        screenshot): the heading, the two buttons and the list own
        ONE ROW EACH - the old pack mixed side="left" head/buttons
        with a top-pack ScrollHost, so the buttons crowded into the
        heading's band and the ScrollHost landed squished right.
        Oct 12 (owner sketch): the section lives on the right
        column; past four seats the rows flow across two
        sub-columns."""
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
        # taller-not-wider flow (owner sketch): _pin_cols returns one
        # sub-column up to four rows, two past that; _pin_btn_w rides
        # along so _pin_row_upsert's appends match the layout
        self._pins_cols = cols = self._pin_cols(pinf.inner,
                                                len(prof["wins"]))
        self._pin_btn_w = 150 if len(cols) > 1 else 400
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
        so a status change repaints ZERO structure."""
        lbl = getattr(self, "_status_lbl", None)
        if lbl is not None and lbl.winfo_exists():
            lbl.configure(text=self._prof_msg,
                          **self.skin.text_style("sub"))
            return
        sec = self._section("status")
        self._status_lbl = ctk.CTkLabel(
            sec, text=self._prof_msg,
            font=self.skin.font(11), wraplength=560, justify="left",
            anchor="w", **self.skin.text_style("sub"))
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
                wt = int(w.get("wait") or 30)
            except (TypeError, ValueError):
                wt = 30
            badges += "  [open it%s]" % (
                "" if wt == 30 else " in %ds" % wt)
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

