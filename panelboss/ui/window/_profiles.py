"""Monitor-profiles tab skeleton: picker, section repaints,
and the per-desk monitor fills.

SIZE LAW: ~340, grandfathered skeleton; the Oct-12 two-column
restructure stayed net-neutral by retiring the single-column flow
notes below. The _repaint/_section double-buffer pair (_section
lives in _widgets.py) is the pane's whole paint pipeline and reads as
one story here; splitting the fills further would scatter a mechanism
that is debugged by reading top to bottom. No cover on repaints
(owner ruling, Oct 12 - see _repaint): a click shows one atomic
re-paint of its section, never a veil sweep.
"""

from __future__ import annotations

import customtkinter as ctk

from .. import theme
from ... import profiles, wm
from ._constants import TIPS, HDR_ASK_LABELS, HDR_MENU_ORDER
from ._widgets import SkewCombo, _fresh_pin_edit


class _ProfilesMixin:
    # ---------------------------------------------------- monitor profiles --
    def _build_profiles(self, page):
        # owner sketch (Oct 12): LEFT column = whole-desktop profiles
        # + the restore-at-start lever, RIGHT column = the pin half
        # (pick an app, the editor, the pinned seats). 620/520: the
        # page is ~1200 wide at the owner's window size and the
        # ScrollHost scrolls the rest.
        col = ctk.CTkFrame(page, width=620, fg_color="transparent")
        col.pack(side="left", fill="y")
        self._prof_left = col
        right = ctk.CTkFrame(page, width=520, fg_color="transparent")
        right.pack(side="left", fill="y")
        self._prof_right = right
        box = self._card(col, "whole-desktop profiles",
                         "one profile is the desk spelled out: the "
                         "panels by hardware identity, their places, "
                         "modes and rates, HDR, and the windows that "
                         "belong on it. applying re-shapes everything, "
                         "waits until the monitors ANSWER as asked, "
                         "and only then moves the windows")
        row = self._row(box, "profile", TIPS["profile_picker"])
        self._prof_data = profiles.load()
        self._prof_msg = ""
        self._prof_live = {}                    # last live_modes() pass
        self._mode_notes = {}                   # per-row last note (R2)
        self._mode_menus = {}                   # per-row res/rate menus
        self._mode_add_map = {}                 # picker label -> panel id
        self._mode_add = None
        self._pin_edit = _fresh_pin_edit()
        names = [profiles.NEW] + sorted(self._prof_data["profiles"])
        start = profiles.default_name(self._prof_data,
                                      wm.fingerprint()) or profiles.NEW
        self.profile_menu = SkewCombo(
            row, values=names, width=220, command=self._profile_picked,
            **self.skin.menu_style())
        self.profile_menu.set(start)
        self.profile_menu.grid(row=0, column=1, sticky="e")
        # (rescue lives on the actions bar now - always in reach)
        self._prof_sel = start
        # the anchor is packed ONCE; every render swaps a fresh body
        # into it (see _profiles_render) - the anchor itself is never
        # touched, so the swap cannot disturb anything around the pane
        self._prof_anchor = ctk.CTkFrame(box, fg_color="transparent")
        self._prof_anchor.pack(fill="x", pady=(theme.S_FIELD, 0))
        # the right column's anchor mirrors the left's: the pin
        # sections double-buffer into a body of their own - pack's
        # before= is PARENT-relative, so the fresh buffers must be
        # constructed with the right column's anchor as parent
        self._prof_anchor_right = ctk.CTkFrame(right,
                                               fg_color="transparent")
        self._prof_anchor_right.pack(fill="x")
        self._prof_body = None
        self._prof_pins_body = None
        self._profiles_render()


    def _profiles_render(self):
        """Swap a whole freshly built pane in, then callers may repain
        individual sections cheaply (see _section). Rebuilt whole on a
        profile switch because the lists of open windows and live
        monitor states are snapshots - a half-updated mix of old and
        new lines is worse. And the rebuild is DOUBLE BUFFERED: CTk
        constructors call update_idletasks(), so building the pane in
        place painted every half-built stage (the whole-window redraw
        storm on every click, user-reported). Built UNPACKED, those
        intermediate paints hit an invisible frame; the destroy-old
        pack-new swap is one redraw. BOTH bodies swap in lockstep:
        the left body carries the profile halves, the right body the
        pin halves - one render, one redraw, no half-mixed pane."""
        old = self._prof_body
        old_r = self._prof_pins_body
        self._prof_body = ctk.CTkFrame(self._prof_anchor,
                                       fg_color="transparent")
        self._prof_detail = self._prof_body
        self._prof_pins_body = ctk.CTkFrame(self._prof_anchor_right,
                                           fg_color="transparent")
        self._psec = {}
        self._psec_pady = {}           #   _repaint's in-place swaps
        self._psec_old = {}            #   buffers awaiting the swap
        self._status_lbl = None        # the idempotent fill must
        self._pin_rows = {}            #   rebuild on this fresh body,
        self._pins_inner = None        #   never configure a widget
        self._pins_empty = None        #   the destroyed body held
        self._pins_cols = None         #   (the pins list's sub-columns)
        try:
            self._profiles_fill()
        finally:
            for f in (old, old_r):
                if f is not None:
                    # BOTH bodies die together: the pin sections
                    # live on the right body now, not under the left
                    f.destroy()
            self._prof_body.pack(fill="x")
            self._prof_pins_body.pack(fill="x")
            self._page_region()   # same rule as _repaint: the whole
            #                   body just swapped - re-measure (see
            #                   scroll_probe, Oct 12)


    def _repaint(self, *names):
        """Re-run the named sections' builders (DETACHED, see
        _section), then pack each fresh frame back into its ORIGINAL
        slot - neighbours never move - and destroy what it replaced.
        NO COVER (owner ruling, Oct 12: "why is every button press
        drawing the whole ui... veiling works fine for the first
        load, but I don't like it for every click"): the veil-on-
        repaint had been HIDING a ~1 s section rebuild instead of
        shrinking it; a click gets ONE clean atomic repaint of the
        changed section, veils stay only on the heavy ops (tab
        switch, profile-switch render, skin rebuild). The double
        buffer is what makes that repaint a single paint instead of
        a crawl: CTk constructors call update_idletasks(), so
        building in place painted the whole mapped pane per
        half-built widget (measured: 688 ms for 12 rows in place,
        against the ~27 ms one paint a detached build + swap costs).
        An idempotent fill (status) builds no buffer and swaps
        nothing."""
        try:
            for name in names:
                getattr(self, "_fill_%s" % name)()
        finally:
            # the pin fills re-point the builder parent at the right
            # buffer (see _profiles_fill): pin it back even if a
            # fill raised, or the next LEFT fill would build there
            self._prof_detail = self._prof_body
        for name in names:
            olds = self._psec_old.get(name)
            if not olds:
                continue            # nothing was rebuilt: the section
                #                   updated in place (or first fill)
            self._psec[name].pack(
                fill="x", pady=self._psec_pady.get(name, (0, 0)),
                # anchor on the frame being REPLACED (still packed
                # until below): absolute slot, so untracked siblings
                # - the _restore_section block! - never drift (gate
                # finding; an after=chain reordered them)
                before=olds[-1])    # the new buffer enters
            # teardown SCOPED to this name (gate finding): a fill that
            # raised mid-repaint stashes an old frame; destroying ALL
            # stashes here would let the NEXT unrelated repaint kill
            # that section's visible frame. A stale stash instead waits
            # quietly until its own section repaints again.
            for f in self._psec_old.pop(name, []):
                f.destroy()
        self._page_region()         # the swap changed (or kept) the
        #                           pane's height: re-measure the page
        #                           scroll region after EVERY swap -
        #                           coalesced <Configure>s can leave a
        #                           stale region and the owner's dead
        #                           wheel (scroll_probe, Oct 12)


    def _page_region(self):
        """the ScrollHost of this tab, re-measured one loop turn
        late (sync_region): after a pack/destroy burst the pending
        geometry needs one idle pass before bbox("all") tells the
        truth."""
        host = self.pages.get("monitor profiles")
        if host is not None:
            host.sync_region()


    def _profiles_fill(self):
        """The pane's content, built into the (still unpacked) fresh
        bodies; self._prof_detail starts as the left body and the
        pin fills re-point it at the right one (see their heads)."""
        prof = self._prof_data["profiles"].get(self._prof_sel)
        if prof is None:                          # the create-new pane
            line = ctk.CTkFrame(self._prof_detail, fg_color="transparent")
            line.pack(fill="x")
            self._prof_name = ctk.CTkEntry(
                line, width=240, font=self.skin.font(12),
                placeholder_text="new profile name",
                fg_color=self.skin.field_bg, border_width=1,
                border_color=self.skin.border_raised,
                corner_radius=self.skin.radius)
            self._prof_name.pack(side="left")
            ctk.CTkButton(line, text="capture this desktop", width=150,
                          command=self._profile_create,
                          **self.skin.secondary()).pack(side="left",
                                                        padx=(theme.S_FIELD, 0))
            self._status_lbl = ctk.CTkLabel(
                self._prof_detail, text=self._prof_msg,
                font=self.skin.font(11), wraplength=560, justify="left",
                anchor="w", **self.skin.text_style("sub"))
            self._status_lbl.pack(anchor="w", pady=(theme.S_FIELD, 0))
            return

        mons = wm.monitors()
        gate = profiles.desk_mismatch(prof, mons)
        # the mode editor: one row per saved panel (resolution +
        # refresh menus), a blank-profile button, and an add-monitor
        # picker (R1-R5). live_modes() is read once inside and handed
        # to every row (R6); every mutation goes through a profiles
        # primitive and repaints the whole pane (R7).
        self._fill_monitors(mons)
        warn = ctk.CTkLabel(
            self._prof_detail,
            text=(gate + " - applying anyway is a gamble, best "
                  "effort below") if gate
            else "this desk matches the profile",
            font=self.skin.font(11), wraplength=560, justify="left",
            anchor="w", **self.skin.text_style("sub"))
        warn.pack(anchor="w", pady=(theme.S_FIELD, 0))

        opts = ctk.CTkFrame(self._prof_detail, fg_color="transparent")
        opts.pack(fill="x", pady=(theme.S_FIELD, 0))
        row = self._row(opts, "hdr", TIPS["profile_hdr"])
        self.hdr_menu = SkewCombo(
            row, values=[HDR_ASK_LABELS[k] for k in HDR_MENU_ORDER],
            width=310,        # measured (tkfont): the longest
            #                              value, "restore as
            #                              captured (per monitor)",
            #                              is 253 px of text (268
            #                              bold) + skew + arrow +
            #                              padding; 230 clipped it
            #                              (owner shot, Oct 12)
            command=self._prof_hdr,
            **self.skin.menu_style())
        self._set_menu(self.hdr_menu,
                       HDR_ASK_LABELS.get(prof.get("hdr", "snap"),
                                          HDR_ASK_LABELS["snap"]))
        self.hdr_menu.grid(row=0, column=1, sticky="e")
        btns = ctk.CTkFrame(self._prof_detail, fg_color="transparent")
        btns.pack(anchor="w", pady=(theme.S_FIELD, 0))
        ctk.CTkButton(btns, text="apply profile", width=130,
                      command=lambda: self._profile_apply(False),
                      **self.skin.primary()).pack(side="left")
        if gate:
            ctk.CTkButton(btns, text="try anyway (best effort)",
                          width=180,
                          command=lambda: self._profile_apply(True),
                          **self.skin.secondary()).pack(side="left",
                                                        padx=(theme.S_FIELD, 0))

        # ---- the pin half lives on its own column (owner sketch,
        # Oct 12): _fill_live/_fill_editor/_fill_pins each re-point
        # self._prof_detail at the right-hand buffer before their
        # _section call - the swap discipline is untouched because
        # _section parents to wherever the detail points and
        # _repaint's before= anchor is parent-relative. The editor
        # still sits above the seat list it edits, seats below
        # (the reorder note that single-column-era pack order kept).
        self._restore_section(self._prof_detail)
        self._fill_status()
        self._fill_live()
        self._fill_editor()
        self._fill_pins()
        self._prof_detail = self._prof_body


    def _fill_monitors(self, mons):
        """The mode editor (R1-R5): one row per saved panel, each with a
        resolution menu and a refresh menu built from what the LIVE panel
        offers (the saved value is kept when the driver no longer lists
        it, so an offline desk still edits - R1/R2). A blank-profile
        button and an add-monitor picker ride the same bar (R3/R4); every
        row carries its own remove (R5). live_modes() is read EXACTLY ONCE
        here and handed to every row (R6); a mutation goes through a
        profiles primitive and repaints the whole pane (R7); a failure is a
        gray status line, never a dialog (R8). Each row also carries the
        panel's LIVE hdr state note (on/off/no hdr/?) straight from the
        driver - silent {} on ancient Windows means no note, which is
        honest, and the power assistant's UI test watches for it."""
        sec = self._section("monitors", pady=(theme.S_ROW, 0))
        prof = self._prof_data["profiles"].get(self._prof_sel)
        if prof is None:                            # the create-new pane
            return
        self._mode_menus = {}        # last render's menus died with
        #                            its old body: start from clean
        live = profiles.live_modes()                # R6: once per pass
        self._prof_live = live
        hdr = {}
        try:
            hdr = {r["gdi"]: ("no hdr" if not r.get("supported")
                              else "hdr on"
                              if r.get("state") == "on"
                              else "hdr off"
                              if r.get("state") == "off"
                              else "hdr ?")
                   for r in wm.hdr_states()}
        except Exception:
            pass
        g_of = {m["id"]: m["gdi"] for m in mons}
        head = ctk.CTkFrame(sec, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text="edit panel modes",
                     font=self.skin.font(13, "bold"),
                     **self.skin.text_style()).pack(side="left")
        for d in prof.get("displays") or []:
            self._mode_row(sec, d, live,
                           hdr.get(g_of.get(d.get("id"), ""), ""))
        if not (prof.get("displays") or []):
            ctk.CTkLabel(sec, text="no panels yet - add one below",
                         font=self.skin.font(11),
                         **self.skin.text_style("sub")).pack(
                              anchor="w", pady=(theme.S_FIELD, 0))
        bar = ctk.CTkFrame(sec, fg_color="transparent")
        bar.pack(fill="x", pady=(theme.S_FIELD, 0))
        ctk.CTkButton(bar, text="blank profile", width=130,
                      command=self._prof_blank,
                      **self.skin.secondary()).pack(side="left")
        in_prof = {d.get("id") for d in prof.get("displays") or []}
        avail = [m for m in mons if m.get("id") not in in_prof]
        base = [(m.get("short") or m.get("id")) for m in avail]
        dupes = {b for b in base if base.count(b) > 1}
        add_vals, self._mode_add_map = [], {}
        for m, b in zip(avail, base):
            label = b
            if b in dupes:
                # two panels of one model share a short: append the
                # gdi slot tail so the menu can tell them apart
                label = "%s (%s)" % (
                    b, str(m.get("gdi") or "").rsplit("DISPLAY", 1)
                    [-1] or "?")
            add_vals.append(label)
            self._mode_add_map[label] = m["id"]
        self._mode_add = SkewCombo(
            bar, values=add_vals or ["(none)"], width=190,
            # SkewCombo._fire calls command(VALUE) - matching CTk,
            # the widget this replaced - so the bound command MUST
            # accept the arg or a dropdown pick dies TypeError inside
            # the widget, past every try here
            command=lambda v=None: self._prof_add_commit(),
            **self.skin.menu_style())
        self._set_menu(self._mode_add, add_vals[0] if add_vals else "(none)")
        self._mode_add.pack(side="left", padx=(theme.S_FIELD, 0))
        ctk.CTkButton(bar, text="add", width=48,
                      command=self._prof_add_commit,
                      **self.skin.secondary()).pack(
            side="left", padx=(theme.S_FIELD, 0))
        # the R8 status line: a small gray label under the rows that
        # every handler's failure lands in (no dialogs, ever)
        self._mode_status = ctk.CTkLabel(
            sec, text="", font=self.skin.font(11), wraplength=560,
            justify="left", anchor="w", **self.skin.text_style("sub"))
        self._mode_status.pack(anchor="w", pady=(theme.S_FIELD, 0))


    @staticmethod
    def _rates_for(live_list, res_text, saved_rate, offline):
        """The refresh values a panel offers at the chosen resolution,
        plus the saved rate when the driver no longer lists it. An
        offline panel offers only its saved rate (R2)."""
        if offline:
            return [saved_rate] if saved_rate else []
        rset = set()
        for m in live_list:
            if m.split("@")[0] == res_text:
                try:
                    rset.add(int(m.split("@")[1]))
                except (ValueError, IndexError):
                    pass
        if saved_rate:
            rset.add(saved_rate)
        return sorted(rset)

