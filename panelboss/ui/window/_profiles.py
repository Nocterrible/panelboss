"""Monitor-profiles tab skeleton: picker, section repaints,
and the per-desk monitor fills.

SIZE LAW: measured 606 lines (Oct 24 launch-night recount; first claim
lied by two at the blob; the byte-count is the ruler and the
claim includes its own rewrite - recount at every touch,
the hdr-walk arm took the wake walk off the pump; the loud-voice
412 (same day) moved the status label to the gaze; the Oct-12 +36
header-trust lesson both restatements were born for stands). The
_repaint/_section double-buffer pair (_section
lives in _widgets.py) is the pane's whole paint pipeline and reads as
one story here; splitting the fills further would scatter a mechanism
that is debugged by reading top to bottom. No cover on repaints
(owner ruling, Oct 12 - see _repaint): a click shows one atomic
re-paint of its section, never a veil sweep.
"""

from __future__ import annotations

import logging
import threading

import customtkinter as ctk

from .. import theme
from ... import profiles, wm
from ._constants import TIPS, HDR_ASK_LABELS, HDR_MENU_ORDER
from ._present import present, clip_siblings
from ._widgets import SkewCombo, desk_position, \
    monitor_row_label, _fresh_pin_edit

log = logging.getLogger("ui")


class _ProfilesMixin:
    # ---------------------------------------------------- monitor profiles --
    def _build_profiles(self, page):
        # owner sketch (Oct 12): LEFT column = whole-desktop profiles
        # + the restore-at-start lever, RIGHT column = the pin half
        # (pick an app, the editor, the pinned seats). Oct 15: the widths
        # are no longer per-tab literals - every tab now shares ONE column
        # rhythm (_two_columns: equal widths, one gutter, flush edges), so
        # the eye finds the grid without hunting.
        gcol, gright = self._two_columns(page)
        # the two column frames the suite knows by name stay PACK-managed
        # (profiles_ui_test asserts winfo_manager() == "pack")
        col = ctk.CTkFrame(gcol, fg_color="transparent")
        col.pack(fill="both", expand=True)
        self._prof_left = col
        right = ctk.CTkFrame(gright, fg_color="transparent")
        right.pack(fill="both", expand=True)
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
        self._prof_sel_touched = False     # the picker's self-heal arm
        #                          (Oct-24 dossier): True the moment a
        #                          pick is DELIBERATE - the desk ear
        #                          may re-land an untouched opener,
        #                          never the owner's own choice
        self._prof_err = False     # the loud-voice wave: the failure
        #                          flag the status label SHOUTS with
        #                          (paints danger while set; resets
        #                          live in _profile_picked/_rescue_now)
        self._prof_live = {}                    # last live_modes() pass
        self._mode_notes = {}                   # per-row last note (R2)
        self._mode_menus = {}                   # per-row res/rate menus
        self._mode_add_map = {}                 # picker label -> panel id
        self._mode_add = None
        self._pin_edit = _fresh_pin_edit()
        names = [profiles.NEW] + sorted(self._prof_data["profiles"])
        # THE PICKER LANDS BY IDENTITY (Oct-24 dossier): the strict
        # fingerprint answer was a FROZEN INSTANT - a cold boot that
        # has not re-applied its modes yet wears a different fp, and
        # the profile that fits the desk's HARDWARE vanished from the
        # opener (the disappearing-profile report). name_for_desk is
        # the apply's own gate view (desk_mismatch): panels first,
        # modes are what a profile APPLIES, not what it demands.
        start = profiles.name_for_desk(self._prof_data,
                                       wm.monitors()) or profiles.NEW
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


    def _profiles_render(self, driver=None):
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
        pin halves - one render, one redraw, no half-mixed pane.
        driver (the freeze-fix wave): None = boot render, the pane's
        own synchronous walks (today's behavior); a dict = the
        hdr-walk's payload, painted WITHOUT touching the driver -
        see _hdr_refresh_async and the hdr_data arm in _runtime."""
        # THE SELF-HEAL (Oct-24 dossier, same law as the opener): the
        # desk ear already routes THIS method on a fingerprint change
        # (MONITOR_ROW_REBUILDERS), so when the modes finally land,
        # the untouched picker lands on the profile that fits - the
        # frozen instant thaws instead of staying frozen. A
        # DELIBERATE pick (the flag) is the owner's word and is never
        # stomped; reload first so a profile captured or edited
        # since the last paint is in the table the recompute reads.
        self._prof_data = profiles.load()
        if not getattr(self, "_prof_sel_touched", False):
            start = profiles.name_for_desk(self._prof_data,
                                           wm.monitors()) or profiles.NEW
            if start != self._prof_sel:
                self.profile_menu.configure(
                    values=[profiles.NEW] + sorted(
                        self._prof_data["profiles"]))
                self._prof_sel = start
                self.profile_menu.set(start)
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
        # the hdr-walk ledger (the freeze-fix wave): initialized at
        # this site but NEVER reset per render - an in-flight walk and
        # its coalesced demand belong to the window, not to one body
        if not hasattr(self, "_hdr_walk"):
            self._hdr_walk = None
            self._hdr_due = False
        self._status_lbl = None        # the idempotent fill must
        self._pin_rows = {}            #   rebuild on this fresh body,
        self._pins_inner = None        #   never configure a widget
        self._pins_empty = None        #   the destroyed body held
        self._pins_cols = None         #   (the pins list's ONE column
        try:
            self._profiles_fill(driver)
            fos = self._prof_data.get("_fossils") or {}
            if fos:
                # the kept-aside confession (owner law, Oct-24): one
                # line when rotted entries rode the loader out of the
                # picker and into _fossils - the store says so on the
                # tab, the load's warning names them in the log.
                n = len(fos)
                ctk.CTkLabel(
                    self._prof_body,
                    text=("%d entr%s you may not recognize kept "
                          "aside - see the log"
                          % (n, "y" if n == 1 else "ies")),
                    font=self.skin.font(11), wraplength=560,
                    justify="left", anchor="w",
                    **self.skin.text_style("sub")).pack(
                    anchor="w", pady=(theme.S_FIELD, 0))
        finally:
            # re-pin the fill target to the LEFT body no matter how
            # the fills went (gate finding 6): the pin fills retarget
            # it as they run, and a raise mid-fill must not leave an
            # idempotent status rebuild parenting its fresh frame
            # into the right body while the stash it replaces lives
            # in the left - before= anchors are parent-relative
            self._prof_detail = self._prof_body
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
            clip_siblings(self._prof_body)     # fresh-born widgets are
            clip_siblings(self._prof_pins_body)  # clip-blind until told
            present(self._body)   # ONE synchronous repaint of the swapped
            #                   pane: the fresh widgets map here, and
            #                   presenting them now (not on the next tick)
            #                   is what keeps the swap a single frame
            #                   instead of the old/new mix the owner saw.
            #                   GATE FINDING 3 (Oct 16): the clip pass in
            #                   build_all is a BUILD-TIME snapshot - the
            #                   widgets rebuilt HERE were born flag-free
            #                   and the forced present makes them paint
            #                   anyway, over the backdrop and the active
            #                   page if this pane's tab is hidden. Clip
            #                   the fresh bodies first (idempotent).


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
            clip_siblings(self._psec[name])   # the fresh buffer was born
            #                                 # after the build-time clip
            #                                 # pass (gate finding 3):
            #                                 # clip BEFORE the forced
            #                                 # paint below, or a repaint
            #                                 # that lands while this
            #                                 # pane's tab is hidden
            #                                 # paints over the backdrop
            #                                 # and the active page.
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
        present(self._body)         # ONE synchronous repaint of the
        #                           swapped section: pack-new-then-
        #                           destroy-old leaves both generations
        #                           mapped for an instant, and presenting
        #                           now collapses that instant to a single
        #                           complete frame


    def _page_region(self):
        """the ScrollHost of this tab, re-measured one loop turn
        late (sync_region): after a pack/destroy burst the pending
        geometry needs one idle pass before bbox("all") tells the
        truth."""
        host = self.pages.get("monitor profiles")
        if host is not None:
            host.sync_region()


    def _profiles_fill(self, driver=None):
        """The pane's content, built into the (still unpacked) fresh
        bodies; self._prof_detail starts as the left body and the
        pin fills re-point it at the right one (see their heads).
        driver rides through to the mode editor: the hdr-walk's
        payload, or None for the boot render's own walks."""
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
            self._prof_name.bind(
                "<KeyRelease>",
                lambda e=None: setattr(self, "_prof_sel_touched",
                                       True), add="+")
            # typing a create-name IS touching the opener (gate f3):
            # the heal will not yank a half-typed name when the desk
            # lands modes late - the create box outlives the flake
            # THE CAPTURE FREEZE (Oct-16, py-spy proven): this verb walks
            # every window on the box and now runs on a worker with the
            # SAME lock as the apply row - so it registers in _apply_btns
            # like its siblings (below, the saved-pane twin keeps the
            # tuple fresh across renders).
            btn_capture = ctk.CTkButton(line, text="capture this desktop",
                                        width=150,
                                        command=self._profile_create,
                                        **self.skin.secondary())
            self._prof_create_btn = btn_capture
            self._apply_btns = (btn_capture,)
            btn_capture.pack(side="left", padx=(theme.S_FIELD, 0))
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
        self._fill_monitors(mons, driver)
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
        btn_last = ctk.CTkButton(btns, text="apply profile", width=130,
                                 command=lambda: self._profile_apply(False),
                                 **self.skin.primary())
        btn_last.pack(side="left")
        # THE OWNER'S ONE CLICK (Oct 16): "applies the window layout from
        # the captured layout and opens missing windows". The verb already
        # exists - scope="windows" runs the windows leg alone (monitors
        # untouched) and its pins still spawn what is missing - the
        # spawn's patience is a BOOT grace (Oct-24): a manual click
        # launches and moves on without waiting (profiles.apply's open
        # leg, pinned by profiles_test 6b/6c) - so this button adds no
        # engine code and no
        # new dialect: it rides the same _profile_apply, which means the
        # say line, the refusal balloon, the no-shows dialog and the apply
        # lock are the same words and the same code as "apply profile".
        # Wording: the label is the owner's own phrase; the app's scope
        # vocabulary calls this "windows only (pinned apps)" and the
        # packet's suggested "re-arm + open" names nothing that exists in
        # this UI (there is no arming anywhere in the apply row), so the
        # owner's words win.
        btn_wins = ctk.CTkButton(
            btns, text="restore my windows", width=150,
            command=lambda: self._profile_apply(False, scope="windows"),
            **self.skin.secondary())
        btn_wins.pack(side="left", padx=(theme.S_FIELD, 0))
        btn_named = None
        if gate:
            btn_named = ctk.CTkButton(
                btns, text="try anyway (best effort)", width=180,
                command=lambda: self._profile_apply(True),
                **self.skin.secondary())
            btn_named.pack(side="left", padx=(theme.S_FIELD, 0))
        # C5b's disclosed interim retired here: the refs survive each
        # render (stored every paint), so _apply_buttons can lock the
        # real entry buttons instead of only the picker. The top bar's
        # restore clone (the placement trio, Oct 16) joins through its
        # own slot - getattr keeps pre-clone renders honest, and the
        # tuple is rebuilt on EVERY render exactly as before, so the
        # clone rides the same apply lock for its whole life.
        self._apply_btns = (btn_last, btn_named, btn_wins,
                            getattr(self, "restore_wins_button", None),
                            getattr(self, "_prof_create_btn", None))
        # THE VOICE LIVES AT THE GAZE (loud-voice wave, Oct 14): the
        # status label is built DIRECTLY UNDER the apply buttons, before
        # the restore section - the create-new pane's label placement is
        # the precedent (see the prof-None branch above). profiles_ui_test
        # 8c pins this geometry against re-basementing the voice below
        # the gaze where the owner's eyes never travel on a refusal.
        self._fill_status()

        # ---- the pin half lives on its own column (owner sketch,
        # Oct 12): _fill_live/_fill_editor/_fill_pins each re-point
        # self._prof_detail at the right-hand buffer before their
        # _section call - the swap discipline is untouched because
        # _section parents to wherever the detail points and
        # _repaint's before= anchor is parent-relative. The editor
        # still sits above the seat list it edits, seats below
        # (the reorder note that single-column-era pack order kept).
        self._restore_section(self._prof_detail)
        self._fill_live()
        self._fill_editor()
        self._fill_pins()
        self._prof_detail = self._prof_body


    def _fill_monitors(self, mons, driver=None):
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
        honest, and the power assistant's UI test watches for it.
        driver (the freeze-fix wave): None walks the driver here (boot,
        R6's once-per-pass); a dict takes the hdr-walk thread's payload
        and touches NO driver - the pump-side walk was the wake freeze,
        and a re-read inside a payload render would resurrect it."""
        sec = self._section("monitors", pady=(theme.S_ROW, 0))
        prof = self._prof_data["profiles"].get(self._prof_sel)
        if prof is None:                            # the create-new pane
            return
        self._mode_menus = {}        # last render's menus died with
        #                            its old body: start from clean
        if driver is None:
            live = profiles.live_modes()                # R6: once per pass
        else:
            live = driver.get("modes") or {}            # R6 rides the
            #                                 payload: zero driver calls
        self._prof_live = live
        hdr, cap = {}, {}
        try:
            # ONE walk: the live note (payload render: the walk thread
            # already did it - the source moves, the honesty does not)
            rows = (wm.hdr_states() if driver is None
                    else driver.get("hdr") or [])
            hdr = {r["gdi"]: ("no hdr" if not r.get("supported")
                              else "hdr on"
                              if r.get("state") == "on"
                              else "hdr off"
                              if r.get("state") == "off"
                              else "hdr ?") for r in rows}
            # and the dropdown gate (amendment 8): precise supported
            # only - a selector on incapable hardware is a gray lie
            cap = {r["gdi"]: bool(r.get("supported")
                                  and r.get("precise")) for r in rows}
        except Exception:
            pass                            # silent {} is honest
        g_of = {m["id"]: m["gdi"] for m in mons}
        head = ctk.CTkFrame(sec, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text="edit panel modes",
                     font=self.skin.font(13, "bold"),
                     **self.skin.text_style()).pack(side="left")
        _drects = [(d.get("x", 0), d.get("y", 0), d.get("w", 0),
                    d.get("h", 0)) for d in (prof.get("displays") or [])]
        for d in prof.get("displays") or []:
            self._mode_row(sec, d, live,
                           hdr.get(g_of.get(d.get("id"), ""), ""),
                           bool(cap.get(g_of.get(d.get("id"), ""))),
                           pos=desk_position(
                               _drects, d.get("x", 0), d.get("y", 0),
                               d.get("w", 0), d.get("h", 0)))
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
        add_vals, self._mode_add_map = [], {}
        for m in avail:
            # the seam's own tail law covers duplicate models (the
            # comment moved with it, Oct 22); the descriptor is
            # suppressed unless the listed set has variance to show
            label = monitor_row_label(avail, m)
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


    # ------------------------------------------------------------ hdr wake --
    def _hdr_refresh_async(self):
        """The hdr_sync ride-up's answer route (the freeze-fix wave,
        Oct 14): at wake the display driver is COLD, and this pane's
        walk (live_modes + hdr_states) is the resume class the camera
        side named at camera.py:56-58 (an OPEN measured 16-27 s, one
        enumeration 38 s - the lesson 0ffa77e wrote as WARMING). The
        owner's ~20 s window death at 07:19, back-solved through the
        idle-gate arithmetic, was the drain arm walking that driver
        synchronously ON THE TK PUMP; this is the pump's last walk.
        One walk at a time: an in-flight guard coalesces every later
        ride-up into _hdr_due, and the landing arm re-runs it ONCE -
        latest wins, the pane ends on the freshest truth. The answer
        posts ("hdr_data", payload) through the SAME ui_events queue
        the ear rides, so it lands on the pump without the pump ever
        walking. A walk that DIES keeps the pane's LAST truth (the
        debug line is the confession) - a driver shrug never blanks a
        pane; the window-closed race swallows the put, a dead window
        asked for nothing. The flags initialize at the _psec site and
        survive every render: the walk belongs to the window."""
        if getattr(self, "_hdr_walk", None) is not None:
            self._hdr_due = True          # coalesce; the landing arm
            return                        #   re-runs it once
        def walk():
            try:
                payload = {"modes": profiles.live_modes(),
                           "hdr": wm.hdr_states()}
            except Exception:
                log.debug("hdr walk died; the pane keeps its last "
                          "truth", exc_info=True)
                self._hdr_walk = None     # re-arming stays possible
                return
            try:
                self.ui_events.put(("hdr_data", payload))
            except Exception:
                self._hdr_walk = None     # gate finding 2: a lost post
                                          # must not arm the guard forever
                log.debug("hdr_data post lost (window closed?)",
                          exc_info=True)
        t = threading.Thread(target=walk, name="hdr-walk", daemon=True)
        self._hdr_walk = t
        t.start()

