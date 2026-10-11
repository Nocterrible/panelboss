"""Profiles tab detail panes: live windows, the pin
editor, pins list, status section.
"""

from __future__ import annotations

import customtkinter as ctk

from ... import profiles
from ._constants import TIPS, WAIT_CHOICES
from ._scroll import ScrollHost


class _EditorMixin:
    def _fill_live(self):
        """The pick-list section: every open window, the chosen one
        highlighted. The row buttons are remembered, so selecting a
        window can re-highlight WITHOUT rebuilding the list at all."""
        sec = self._section("live", pady=(10, 0))
        ed = self._pin_edit
        head = ctk.CTkFrame(sec, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text="pin an app - click a window, it "
                                "lands in the editor below",
                     font=self.skin.font(13, "bold"),
                     **self.skin.text_style()).pack(side="left")
        self.tips.button(head, TIPS["profile_match"]).pack(
            side="left", padx=(6, 0))
        lif = ScrollHost(sec, bg=self.skin.panel, width=590, height=132)
        lif.pack(fill="x")
        self._live_rows = {}
        live = profiles.windows_now()
        for l in live:
            key = (l["proc"], l["title"])
            picked = ed["pick"] == key
            b = ctk.CTkButton(
                lif.inner, width=540, anchor="w",
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
                text_color="#10131a" if picked else self.skin.text,
                corner_radius=self.skin.radius)
            b.pack(anchor="w", pady=1)
            self._live_rows[key] = b
        if not live:
            ctk.CTkLabel(lif.inner, text="no open windows to pick",
                         font=self.skin.font(11),
                         **self.skin.text_style("sub")).pack(
                anchor="w", pady=4, padx=4)


    def _restyle_live(self):
        """the highlight move, without a rebuild: paint exactly the
        rows whose picked-state changed"""
        pick = self._pin_edit["pick"]
        for key, b in getattr(self, "_live_rows", {}).items():
            on = key == pick
            try:
                b.configure(fg_color=self.skin.accent if on
                            else self.skin.field_bg,
                            text_color="#10131a" if on
                            else self.skin.text)
            except Exception:
                pass                    # a destroyed row: harmless


    def _fill_editor(self):
        """The conditions + fine print for the editor's subject, live
        or remembered. The section carries its own 'editing:' title -
        it is what changes when a seat is clicked, and the title is
        the proof the click landed."""
        sec = self._section("editor", pady=(4, 0))
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
        self.match_menu = ctk.CTkOptionMenu(
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
                                            border_color=self.skin.border,
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
            self.pin_wait_menu = ctk.CTkOptionMenu(
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
                         font=self.skin.font(10), wraplength=580,
                         justify="left", anchor="w",
                         **self.skin.text_style("sub")).pack(
                anchor="w", pady=(2, 0))
        cbtns = ctk.CTkFrame(sec, fg_color="transparent")
        cbtns.pack(anchor="w", pady=(4, 0))
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
        (see the reorder note in _profiles_fill)."""
        sec = self._section("pins", pady=(10, 0))
        prof = self._prof_data["profiles"].get(self._prof_sel) \
            or {"wins": []}
        ctk.CTkLabel(sec, text="pinned apps",
                     font=self.skin.font(13, "bold"),
                     **self.skin.text_style()).pack(side="left")
        self.tips.button(sec, TIPS["profile_pins"]).pack(
            side="left", padx=(6, 0))
        ctk.CTkButton(sec, text="pin every open app", width=150,
                      command=self._prof_pin_all,
                      **self.skin.secondary()).pack(side="left",
                                                    padx=(8, 0))
        ctk.CTkButton(sec, text="re-scan", width=80,
                      command=self._prof_rescan,
                      **self.skin.secondary()).pack(side="left",
                                                    padx=(6, 0))
        pinf = ScrollHost(sec, bg=self.skin.panel, width=590, height=112)
        pinf.pack(fill="x")
        live_key = {(w["proc"], w["title"]): w
                    for w in profiles.windows_now()}
        for w in prof["wins"]:
            self._pin_row(pinf.inner, w, live_key.get((w["proc"], w["title"])))
        if not prof["wins"]:
            ctk.CTkLabel(pinf.inner,
                         text="nothing pinned yet - seat an app above",
                         font=self.skin.font(11),
                         **self.skin.text_style("sub")).pack(
                anchor="w", pady=4, padx=4)


    def _fill_status(self):
        sec = self._section("status")
        self._prof_status = ctk.CTkLabel(
            sec, text=self._prof_msg,
            font=self.skin.font(11), wraplength=560, justify="left",
            anchor="w", **self.skin.text_style("sub"))
        self._prof_status.pack(anchor="w", pady=(6, 0))


    def _pin_row(self, parent, w, live):
        """One pinned seat. The row itself is the button that lifts
        the pin back into the editor ('click it and it pops back
        up'), the pencil says the same out loud, the x forgets the
        seat. Badges tell the truth the plain text cannot: closed,
        'open it', a non-default match."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(anchor="w", fill="x", pady=1)
        badges = ""
        if w.get("open"):
            try:
                wt = int(w.get("wait") or 30)
            except (TypeError, ValueError):
                wt = 30
            badges += "  [open it%s]" % (
                "" if wt == 30 else " in %ds" % wt)
            ex = (w.get("exe") or "").split("\\")[-1].lower()
            if ex and ex != (w.get("proc") or "").lower():
                badges += "  [via %s]" % ex[:18]
        if (w.get("match") or "process") != "process":
            badges += "  [%s]" % w.get("match")
        ctk.CTkButton(
            row, width=470, anchor="w",
            text="%s  %s  %dx%d at %d,%d on %s%s%s" % (
                (w["title"] or w["proc"])[:36], w["proc"][:14],
                w["rect"][2], w["rect"][3], w["rect"][0],
                w["rect"][1], w.get("monitor") or "?",
                "" if live else "  (closed)", badges),
            font=self.skin.font(11),
            command=lambda r=w: self._pin_load(r),
            fg_color="transparent", hover_color=self.skin.panel,
            text_color=self.skin.text,
            corner_radius=self.skin.radius).pack(side="left")
        ctk.CTkButton(row, text="edit", width=48,
                      command=lambda r=w: self._pin_load(r),
                      **self.skin.secondary()).pack(side="left",
                                                    padx=(4, 0))
        ctk.CTkButton(row, text="x", width=30,
                      command=lambda r=w: self._pin_remove(r),
                      **self.skin.secondary()).pack(side="left",
                                                    padx=(4, 0))

