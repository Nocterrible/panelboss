"""The restore-at-start lever inside the profiles tab:
arm, profile, scope, when.
"""

from __future__ import annotations

from .. import theme

import customtkinter as ctk

from ... import profiles, wm
from ._constants import TIPS, RESTORE_LAST, RESTORE_SCOPES, RESTORE_WHENS
from ._widgets import SkewCombo


class _RestoreMixin:
    # ------------------------------------------------- restore at start --
    @staticmethod
    def _pair_label(pairs, value):
        return dict(pairs).get(value, pairs[0][1])


    def _restore_section(self, parent):
        """The pre-armed lever, living ON the profiles tab with the
        profiles it arms (it hid under General; the user hunted for it
        here). Rebuilt with the pane, so the picker always knows about
        profiles captured since the window opened. Which COPY is the
        logon one is not inferred (the shell gives no clue) - the Run
        entry installed by the startup row stamps --autostart on
        itself, and cli reads that stamp as proof."""
        rst = self.cfg.setdefault("restore", {})
        self._restorep_gone = False
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.pack(fill="x", pady=(theme.S_ROW, 0))
        ctk.CTkLabel(head, text="restore a profile at start",
                     font=self.skin.font(13, "bold"),
                     **self.skin.text_style()).pack(side="left")
        # (the chip is gone: the "armed" row below already carries
        # this same tip as its inline hint - the chip was a duplicate)
        row = self._row(parent, "armed", TIPS["restore_on"])
        self.restorep_switch = ctk.CTkSwitch(row, text="",
                                             font=self.skin.font(12),
                                             command=self._restorep_changed,
                                             **self.skin.switch_style())
        self.restorep_switch.grid(row=0, column=1, sticky="e")
        if rst.get("enabled"):
            self.restorep_switch.select()
        row = self._row(parent, "which profile", TIPS["restore_profile"])
        armed = rst.get("profile") or "last"
        self.restorep_menu = SkewCombo(
            row, values=self._restorep_names(), width=240,
            command=self._restorep_pick, **self.skin.menu_style())
        # the "last" label resolves to the desk's last-used name when
        # the store has one - the picker and the armed row speak the
        # same truth, and a store that never met this desk (login boot,
        # pre-any-save) falls back to the literal label via name_for_desk
        self._set_menu(self.restorep_menu,
                       self._restorep_label(self._restorep_value(armed)))
        self.restorep_menu.grid(row=0, column=1, sticky="e")
        row = self._row(parent, "what to restore", TIPS["restore_scope"])
        self.restorep_scope_menu = SkewCombo(
            row, values=[lbl for _, lbl in RESTORE_SCOPES], width=240,
            command=self._restorep_scope, **self.skin.menu_style())
        self._set_menu(self.restorep_scope_menu,
                       self._pair_label(RESTORE_SCOPES,
                                        rst.get("scope") or "full"))
        self.restorep_scope_menu.grid(row=0, column=1, sticky="e")
        row = self._row(parent, "applies to", TIPS["restore_when"])
        self.restorep_when_menu = SkewCombo(
            row, values=[lbl for _, lbl in RESTORE_WHENS], width=240,
            command=self._restorep_when, **self.skin.menu_style())
        self._set_menu(self.restorep_when_menu,
                       self._pair_label(RESTORE_WHENS,
                                        rst.get("when") or "autostart"))
        self.restorep_when_menu.grid(row=0, column=1, sticky="e")
        self.restorep_warn = None
        self.restorep_note = ctk.CTkLabel(
            parent, text=self._restorep_note(), font=self.skin.font(11),
            wraplength=560, justify="left", anchor="w",
            **self.skin.text_style("sub"))
        self.restorep_note.pack(anchor="w")
        self._restorep_gone_check()


    def _restorep_names(self):
        """'last' first, then every profile by name - the picker on
        the profiles tab and this one read the same truth. The in-
        memory store wins when one exists (a profile captured since
        the window opened shows without a reload); the login-boot
        path - before any store exists - still loads from disk."""
        data = getattr(self, "_prof_data", None) or profiles.load()
        return [RESTORE_LAST[1]] + sorted(data["profiles"])

    def _armed_restore_name(self):
        """The armed profile's NAME: 'last' resolves through the store
        to the desk's last-used profile (None when the store never met
        this desk - the pre-store login-boot case)."""
        armed = self.cfg.get("restore", {}).get("profile") or "last"
        if armed == "last":
            data = getattr(self, "_prof_data", None) or profiles.load()
            return profiles.name_for_desk(data, wm.monitors())
        return armed

    def _restorep_label(self, value):
        """The picker button's text. An armed profile absent from the
        built list renders with a ' (gone)' suffix on its own line
        rather than a silent ghost selection: the name the store still
        points at, visibly missing."""
        label = value
        if value == "last":
            label = self._armed_restore_name() or RESTORE_LAST[1]
        if label not in self._restorep_names():
            label = label + " (gone)"
        return label

    def _restorep_value(self, label):
        if label in (RESTORE_LAST[1],
                     (self._armed_restore_name() or RESTORE_LAST[1])
                     + " (gone)"):
            return "last"
        return label.rsplit(" (gone)", 1)[0]


    def _restorep_gone_check(self):
        """User-visible notice when the armed profile is gone - the
        SAME shape as the named-gone path (the ' (gone)' suffix on its
        own line, spoken by the note under the picker): the no-match
        'last' case and the named-gone case both say so out loud,
        never a silent ghost selection."""
        self._restorep_gone = False
        armed = self.cfg.get("restore", {}).get("profile") or "last"
        gone = armed if armed != "last" else self._armed_restore_name()
        if gone and gone not in self._restorep_names():
            self._restorep_gone = True
            self.restorep_note.configure(
                text=("the profile this restore is armed for is gone "
                      "- %s no longer exists. re-pick a profile, or "
                      "let the first login re-arm a live one."
                      % gone))
            self._set_menu(self.restorep_menu, self._restorep_label(armed))
            return
        self.restorep_note.configure(text=self._restorep_note())

    def _restorep_note(self):
        """fine print that tells the truth about how long login will
        wait - the calibration promise, or the learned number"""
        data = profiles.load()
        lg = data.get("login") or {}
        head = ("login gets the grace a storm needs, and results "
                "arrive as tray balloons - no dialog holds a "
                "half-woken desktop hostage. ")
        try:
            mx = float(lg.get("max") or 0)
        except (TypeError, ValueError):
            mx = 0.0
        if mx > 0:
            return head + ("learned from your logins: the slowest "
                           "app took %d s to show after launch, so "
                           "launches now wait %d s."
                           % (int(mx), int(profiles.launch_delay(
                               data))))
        return head + ("the FIRST login waits 2 full minutes "
                       "before launching anything and times every "
                       "app that shows up; after that, launches "
                       "wait only the slowest boot + 20 s (never "
                       "under 30 s, never over 10 min).")


    def _restorep_warn(self):
        """the first-login promise, spoken when the lever is armed -
        and only then: once a metric exists there is nothing new to
        warn about"""
        if (profiles.load().get("login") or {}).get("max"):
            return
        dlg = ctk.CTkToplevel(self)
        self.restorep_warn = dlg
        dlg.title("first login restore")
        dlg.resizable(False, False)
        dlg.configure(fg_color=self.skin.bg)
        dlg.transient(self)
        ctk.CTkLabel(
            dlg, text="the FIRST login restore will wait longer: 2 "
                      "full minutes before launching anything, "
                      "because it is timing how long this machine "
                      "needs. every login after that waits only "
                      "the slowest boot it measured + 20 s (never "
                      "under 30 s, never over 10 min).",
            font=self.skin.font(12), justify="left", wraplength=340,
            **self.skin.text_style()).pack(padx=theme.S_SECTION, pady=(theme.S_SECTION, theme.S_ROW))

        def close():
            dlg.destroy()
            if self.restorep_warn is dlg:
                self.restorep_warn = None

        ctk.CTkButton(dlg, text="got it", width=110, command=close,
                      **self.skin.primary()).pack(pady=(0, theme.S_SECTION))
        dlg.after(30, dlg.focus_force)       # Windows steals focus
                                             # back without this


    def _restorep_changed(self):
        on = bool(self.restorep_switch.get())
        self.cfg.setdefault("restore", {})["enabled"] = on
        self._save()
        if on:
            self._restorep_warn()
        self._restorep_gone_check()


    def _restorep_pick(self, label):
        self.cfg.setdefault("restore", {})["profile"] = \
            self._restorep_value(label)
        self._save()
        self._restorep_gone_check()


    def _restorep_scope(self, label):
        for value, lbl in RESTORE_SCOPES:
            if lbl == label:
                self.cfg.setdefault("restore", {})["scope"] = value
                break
        self._save()


    def _restorep_when(self, label):
        for value, lbl in RESTORE_WHENS:
            if lbl == label:
                self.cfg.setdefault("restore", {})["when"] = value
                break
        self._save()

