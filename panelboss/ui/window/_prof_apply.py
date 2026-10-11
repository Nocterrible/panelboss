"""Profiles tab verbs: mode edits, profile create and
apply, the noshows dialog, rescue.
"""

from __future__ import annotations

import logging
import threading

import customtkinter as ctk

from ... import profiles, wm
from ._constants import HDR_BY_LABEL
from ._widgets import SkewCombo, _fresh_pin_edit

log = logging.getLogger("ui")


class _ModeMixin:
    def _mode_row(self, parent, d, live, hdr_note=""):
        """One editable panel row: short name (plus its LIVE hdr state,
        the driver's truth, silent when unknowable), a resolution menu, a
        refresh menu, a remove. A panel not on the live desk offers only
        its saved values and a gray 'panel not live' hint; a UNVERIFIED
        note from the last edit is painted gray under the row (R2)."""
        mon_id = d.get("id")
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=1)
        ctk.CTkLabel(
            row, anchor="w",
            text="%s%s%s" % (d.get("short") or mon_id,
                             " (primary)" if d.get("primary") else "",
                             "   " + hdr_note if hdr_note else ""),
            font=self.skin.font(11),
            **self.skin.text_style()).pack(side="left")
        try:
            saved_w = int(d.get("w") or 0)
            saved_h = int(d.get("h") or 0)
            saved_rate = int(d.get("rate") or 0)
        except (TypeError, ValueError):
            saved_w = saved_h = saved_rate = 0
        saved_res = "%dx%d" % (saved_w, saved_h)
        live_list = live.get(mon_id) or []
        if live_list:
            res_set = set(m.split("@")[0] for m in live_list)
            res_set.add(saved_res)
            resolutions = sorted(res_set)
            offline = False
        else:                                        # R2: saved only
            resolutions = ([saved_res]
                           if saved_res and saved_res != "0x0"
                           else ["?"])
            offline = True
        res_menu = SkewCombo(
            row, values=resolutions, width=150,
            command=lambda v, m=mon_id: self._mode_res(m, v),
            **self.skin.menu_style())
        self._set_menu(res_menu, saved_res)
        res_menu.pack(side="left", padx=(6, 0))
        rates = self._rates_for(live_list, saved_res, saved_rate, offline)
        rate_menu = SkewCombo(
            row, values=[str(r) for r in rates] or ["?"], width=80,
            command=lambda v, m=mon_id: self._mode_rate(m, v),
            **self.skin.menu_style())
        self._set_menu(rate_menu, str(saved_rate) if saved_rate else "?")
        rate_menu.pack(side="left", padx=(4, 0))
        self._mode_menus[mon_id] = (res_menu, rate_menu)
        ctk.CTkButton(row, text="remove", width=66,
                      command=lambda m=mon_id: self._mode_remove(m),
                      **self.skin.secondary()).pack(side="left", padx=(4, 0))
        if offline:
            ctk.CTkLabel(parent, text="panel not live",
                         font=self.skin.font(10),
                         **self.skin.text_style("sub")).pack(
                             anchor="w", padx=92)
        note = self._mode_notes.get(mon_id, "")
        if "UNVERIFIED" in note:
            ctk.CTkLabel(parent, text=note, font=self.skin.font(10),
                         **self.skin.text_style("sub")).pack(
                             anchor="w", padx=92)


    # ---- profiles: handlers ---------------------------------------------
    def _profile_picked(self, name):
        self._prof_sel = name
        self._prof_msg = ""
        self._mode_notes = {}                   # stale per-row notes
        self._pin_edit = _fresh_pin_edit()
        self._profiles_render()


    def _profile_create(self):
        name = (self._prof_name.get() or "").strip()
        if not name:
            self._prof_msg = "give it a name first"
            self._prof_status.configure(text=self._prof_msg)
            return
        profiles.create(self._prof_data, name)
        self.profile_menu.configure(values=[profiles.NEW] + sorted(
            self._prof_data["profiles"]))
        self.profile_menu.set(name)
        self._profile_picked(name)


    def _prof_blank(self):
        """R3: a profile that starts empty, auto-named profile-N (the
        next unused). The editor switches to it; nothing is ever asked
        - no dialogs."""
        try:
            taken = set(self._prof_data["profiles"])
            n = 1
            while ("profile-%d" % n) in taken:
                n += 1
            name = "profile-%d" % n
            ok, note = profiles.blank(self._prof_data, name)
            if not ok:
                self._mode_fail(note or "could not create a blank profile")
                return
            self.profile_menu.configure(values=[profiles.NEW] + sorted(
                self._prof_data["profiles"]))
            self._set_menu(self.profile_menu, name)
            self._profile_picked(name)
        except Exception as e:
            self._mode_fail("blank profile: %s" % e)


    def _prof_add_commit(self):
        """R4: pull the picked LIVE panel into the profile; the
        primitive seeds it with the panel's current mode. Resolution is
        by the label->id map _fill_monitors built THIS render, so two
        same-model panels never collide (finding: name scan picked the
        first)."""
        try:
            sel = self._mode_add.get()
            if not sel or sel == "(none)":
                self._mode_fail("pick a panel to add")
                return
            mon_id = (self._mode_add_map or {}).get(sel)
            if mon_id is None:
                self._mode_fail("no such panel on the desk")
                return
            ok, note = profiles.add_display(
                self._prof_data, self._prof_sel, mon_id)
            if not ok:
                self._mode_fail(note or "could not add the panel")
                return
            self._profiles_render()
        except Exception as e:
            self._mode_fail("add panel: %s" % e)


    def _mode_res(self, mon_id, res_text):
        """R1: the resolution changed; keep the saved rate when the new
        panel still offers it there, else the first rate it offers."""
        try:
            w, h = (int(x) for x in res_text.split("x"))
            prof = self._prof_data["profiles"].get(self._prof_sel) or {}
            row = next((d for d in prof.get("displays") or []
                        if d.get("id") == mon_id), None)
            if row is None:
                return
            live_list = (self._prof_live or {}).get(mon_id) or []
            rset = set()
            for m in live_list:
                if m.split("@")[0] == res_text:
                    try:
                        rset.add(int(m.split("@")[1]))
                    except (ValueError, IndexError):
                        pass
            cur = int(row.get("rate") or 0)
            rate = cur if cur in rset else (min(rset) if rset else cur)
            ok, note = profiles.set_display_mode(
                self._prof_data, self._prof_sel, mon_id, w, h, rate)
            self._apply_mode_note(mon_id, note, ok)
            self._profiles_render()
        except Exception as e:
            self._mode_fail("change resolution: %s" % e)


    def _mode_rate(self, mon_id, rate_text):
        """R1: the refresh changed; the resolution is the row's saved
        one. An offline panel saves any rate as UNVERIFIED (no driver
        to check it) - which is exactly what the gray note reports."""
        try:
            rate = int(rate_text)
            prof = self._prof_data["profiles"].get(self._prof_sel) or {}
            row = next((d for d in prof.get("displays") or []
                        if d.get("id") == mon_id), None)
            if row is None:
                return
            ok, note = profiles.set_display_mode(
                self._prof_data, self._prof_sel, mon_id,
                int(row.get("w") or 0), int(row.get("h") or 0), rate)
            self._apply_mode_note(mon_id, note, ok)
            self._profiles_render()
        except Exception as e:
            self._mode_fail("change rate: %s" % e)


    def _mode_remove(self, mon_id):
        """R5: drop one panel; the last row is removable too."""
        try:
            ok, note = profiles.drop_display(
                self._prof_data, self._prof_sel, mon_id)
            if not ok:
                self._mode_fail(note or "could not remove the panel")
                return
            self._mode_notes.pop(mon_id, None)
            self._profiles_render()
        except Exception as e:
            self._mode_fail("remove panel: %s" % e)


    def _apply_mode_note(self, mon_id, note, ok):
        """Remember the last note per row so a UNVERIFIED one is painted
        gray under it on the next repaint (R2); a clean edit clears it,
        and a refusal also lands in the gray status line (R8)."""
        self._mode_notes[mon_id] = note or ""
        if not ok:
            self._mode_fail(note or "the panel refused the mode")


    def _mode_fail(self, msg):
        """R8: a failure is a gray status line, never a dialog, and
        nothing raises into the mainloop."""
        try:
            self._mode_status.configure(text=msg)
        except Exception:
            pass


    def _profile_apply(self, force=False):
        # the reshuffle takes seconds (modes, settle-poll, windows
        # and maybe a 30 s wait for a pinned app to wake), and Tk
        # must not sit frozen through any of it
        name, data = self._prof_sel, self._prof_data
        self._prof_msg = "reshaping the desktop..."
        self._prof_status.configure(text=self._prof_msg)

        def work():
            ok, text, info = profiles.apply(data, name,
                                            best_effort=force)
            log.info("profile '%s' %s: %s", name,
                     "applied" if ok else "refused", text)

            def done():
                self._prof_msg = text
                self._profiles_render()
                misses = (info or {}).get("no_shows") or []
                if misses:
                    self._noshows_ask(misses)
            self.after(0, done)
        threading.Thread(target=work, daemon=True).start()


    def _noshows_ask(self, misses):
        """Loud, but only once: pinned apps that never turned up.
        'I'll fix it' leaves them loud and opens the editor for
        them; 'let it be' marks them quiet and the same failure is
        silent from now on - until one answers a profile again,
        which lifts the quiet automatically."""
        names = "\n".join("  %s" % (m["title"] or m["proc"])[:60]
                          for m in misses)
        dlg = ctk.CTkToplevel(self)
        self.noshows_dialog = dlg
        dlg.title("pinned apps that stayed away")
        dlg.resizable(False, False)
        dlg.configure(fg_color=self.skin.bg)
        dlg.transient(self)
        ctk.CTkLabel(
            dlg, text="these pinned apps did not turn up:\n%s\n\n"
                      "Fix the profile? 'let it be' keeps them "
                      "quiet about future failures." % names,
            font=self.skin.font(12), justify="left",
            **self.skin.text_style()).pack(padx=20, pady=(14, 8))
        line = ctk.CTkFrame(dlg, fg_color="transparent")
        line.pack(pady=(0, 14))

        def fix():
            if len(misses) == 1:
                self._pin_load({"proc": misses[0]["proc"],
                                "title": misses[0]["title"],
                                "rect": [0, 0, 0, 0]})
            dlg.destroy()

        def quiet():
            prof = self._prof_data["profiles"].get(self._prof_sel)
            if prof:
                for m in misses:
                    for w in prof["wins"]:
                        if (w["proc"], w["title"]) == (m["proc"],
                                                       m["title"]):
                            w["quiet"] = True
                profiles.save(self._prof_data)
            dlg.destroy()
        ctk.CTkButton(line, text="I'll fix it", width=110,
                      command=fix, **self.skin.primary()).pack(
            side="left", padx=(0, 6))
        ctk.CTkButton(line, text="let it be", width=110,
                      command=quiet, **self.skin.secondary()).pack(
            side="left")
        dlg.after(30, dlg.focus_force)       # the measured claim:
                                             # Windows steals focus
                                             # back without this


    def _rescue_now(self):
        brought = wm.rescue_lost()
        self._prof_msg = ("brought back: %s" % ", ".join(brought)
                          if brought else "nothing was off screen")
        self._profiles_render()


    def _prof_hdr(self, ask):
        # the menu hands labels; unknown strings pass through raw
        # (a hand-edited profile or a test speaks the engine's
        # tongue directly)
        ask = HDR_BY_LABEL.get(ask, ask)
        self._prof_data["profiles"][self._prof_sel]["hdr"] = ask
        profiles.save(self._prof_data)


    def _prof_rescan(self):
        self._prof_msg = ""
        self._profiles_render()

