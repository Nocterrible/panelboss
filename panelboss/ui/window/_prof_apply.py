"""Profiles tab verbs: mode edits, profile create and
apply, the noshows dialog, rescue.
Size law (measured 467, Oct 13 - the claim includes its own lines;
the amendment-8 per-panel color selector added the last thirty and
the 2026-10 claim had drifted before that): the apply pipeline is
one transaction -
snapshot, layout plan, dialog, rescue - whose halves argue over
shared state; split cost paid per read beats the split itself here.
"""

from __future__ import annotations

from .. import theme

import logging
import sys
import threading
import tkinter as tk

import customtkinter as ctk

from ... import profiles, wm
from ._constants import HDR_BY_LABEL, HDR_SET_LABELS
from ._widgets import SkewCombo, _fresh_pin_edit

log = logging.getLogger("ui")


class _ModeMixin:
    def _mode_row(self, parent, d, live, hdr_note="", hdr_cap=False):
        """One editable panel row: short name (plus its LIVE hdr state,
        the driver's truth, silent when unknowable), a resolution menu, a
        refresh menu, a remove. A panel not on the live desk offers only
        its saved values and a gray 'panel not live' hint; a UNVERIFIED
        note from the last edit is painted gray under the row (R2).
        hdr_cap (amendment 8) adds the per-panel color selector between
        the rate menu and the remove - it renders ONLY where a precise
        driver read reported the panel capable: a selector on hardware
        that cannot use it is the gray lie the owner refused, and the
        absence of the selector is itself the honest answer."""
        mon_id = d.get("id")
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=theme.S_FIELD)
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
        res_menu.pack(side="left", padx=(theme.S_FIELD, 0))
        rates = self._rates_for(live_list, saved_res, saved_rate, offline)
        rate_menu = SkewCombo(
            row, values=[str(r) for r in rates] or ["?"], width=80,
            command=lambda v, m=mon_id: self._mode_rate(m, v),
            **self.skin.menu_style())
        self._set_menu(rate_menu, str(saved_rate) if saved_rate else "?")
        rate_menu.pack(side="left", padx=(theme.S_FIELD, 0))
        self._mode_menus[mon_id] = (res_menu, rate_menu)
        if hdr_cap:
            # the per-panel color ask (amendment 8): same row, same
            # commit-through-primitive law as res and rate
            hdr_menu = SkewCombo(
                row, values=[lab for lab, _ in HDR_SET_LABELS],
                width=90,
                command=lambda v, m=mon_id: self._mode_hdr(m, v),
                **self.skin.menu_style())
            want = d.get("hdr")
            hdr_menu.set("hdr on" if want is True
                         else "hdr off" if want is False else "keep")
            hdr_menu.pack(side="left", padx=(theme.S_FIELD, 0))
        ctk.CTkButton(row, text="remove", width=66,
                      command=lambda m=mon_id: self._mode_remove(m),
                      **self.skin.secondary()).pack(side="left", padx=(theme.S_FIELD, 0))
        if offline:
            ctk.CTkLabel(parent, text="panel not live",
                         font=self.skin.font(10),
                         **self.skin.text_style("sub")).pack(
                             anchor="w", padx=92)  # column indent, not a gap
        note = self._mode_notes.get(mon_id, "")
        if "UNVERIFIED" in note:
            ctk.CTkLabel(parent, text=note, font=self.skin.font(10),
                         **self.skin.text_style("sub")).pack(
                             anchor="w", padx=92)  # column indent, not a gap


    # ---- profiles: handlers ---------------------------------------------
    def _profile_picked(self, name):
        self._prof_sel = name
        self._prof_msg = ""
        self._mode_notes = {}                   # stale per-row notes
        self._pin_edit = _fresh_pin_edit()
        self._profiles_render()


    def _profile_create(self):
        # the create-now verb must die LOUD like its blank-profile
        # sibling, never silent in pythonw: profiles.create() calls
        # capture() -> wm.monitors(), a real driver read that can raise
        # mid-enumeration; an unguarded raise lands in the Tk callback
        # and the event loop swallows it whole - the button looked dead
        # (the same silent-ignorance class as the consent switch). The
        # failure goes to the gray status line (R8); nothing raises.
        name = (self._prof_name.get() or "").strip()
        if not name:
            self._prof_msg = "give it a name first"
            self._status_lbl.configure(text=self._prof_msg)
            return
        try:
            profiles.create(self._prof_data, name)
            # the primitive returns the dict it stored; a save that
            # could not write still leaves the in-memory card, so the
            # picker is rebuilt from the data the store now holds -
            # exactly one default-filled entry for the fresh name
            self.profile_menu.configure(values=[profiles.NEW] + sorted(
                self._prof_data["profiles"]))
            self.profile_menu.set(name)
            self._profile_picked(name)
        except Exception as e:
            # the create pane builds _status_lbl and NEVER _mode_status
            # (_fill_monitors early-returns on prof None), so routing
            # through _mode_fail would die into _mode_fail's own
            # except-pass - the exact silent vanish this guard exists to
            # cure. Report on the label that EXISTS here, mirroring the
            # empty-name branch above (gate finding, the real fix).
            self._prof_msg = "create profile: %s" % e
            self._status_lbl.configure(text=self._prof_msg)


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


    def _mode_hdr(self, mon_id, label):
        """Per-panel color ask (amendment 8), same commit-through-
        primitive law as res and rate: 'keep' DELETES the key (hands
        off is the absence of a rule, never a written false), true/
        false store the command. The profile's whole file re-saves
        and the pane repaints; hdr itself moves at APPLY time -
        editing the row must not flicker the owner's desk."""
        try:
            prof = self._prof_data["profiles"].get(self._prof_sel) or {}
            row = next((d for d in prof.get("displays") or []
                        if d.get("id") == mon_id), None)
            if row is None:
                return
            want = dict(HDR_SET_LABELS).get(label)
            if want is None:
                row.pop("hdr", None)
            else:
                row["hdr"] = want
            profiles.save(self._prof_data)
            self._profiles_render()
        except Exception as e:
            self._mode_fail("change hdr: %s" % e)


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


    def _apply_buttons(self, state):
        """Quiet the apply path while a reshuffle runs. C5b's interim
        (lock the picker, the only control whose reference survived a
        render) lives on as the fallback: _profiles.py now STORES the
        two entry buttons' references on every render (_apply_btns),
        so when they are present the visible lock is the buttons the
        click actually enters through; a pane whose buttons have not
        been painted yet falls back to the picker. The re-entrancy
        guard in _profile_apply stays the belt either way."""
        refs = getattr(self, "_apply_btns", None)
        if refs:
            for btn in refs:
                if btn is None:              # no-gate render: the
                    continue                   # best-effort twin absent
                try:
                    btn.configure(state=state)
                except Exception:
                    pass                     # a superseded render's
                    # ghost: the live twins own the lock now
        else:
            try:
                self.profile_menu.configure(state=state)
            except Exception:
                pass                  # a mid-teardown window has no picker

    def _profile_apply(self, force=False):
        # the reshuffle takes seconds (modes, settle-poll, windows
        # and maybe a 30 s wait for a pinned app to wake), and Tk
        # must not sit frozen through any of it
        if getattr(self, "_applying", False):        # one apply at a time:
            self._prof_msg = ("already reshaping the desktop - one "
                              "apply at a time")
            self._status_lbl.configure(text=self._prof_msg)
            return
        self._applied_name = self._prof_sel          # captured: the user
                                                     # can switch profiles
        # mid-apply, and the outcome belongs to the one that was applied
        self._apply_buttons("disabled")              # the visible lock (see
        # _apply_buttons); the re-entrancy guard above is the belt for
        # the two entry buttons themselves. The flag goes up LAST: a
        # raise on the way in must not wedge the pane into permanent
        # "already reshaping"
        self._applying = True
        name, data = self._prof_sel, self._prof_data
        self._prof_msg = "reshaping the desktop..."
        self._status_lbl.configure(text=self._prof_msg)

        def work():
            try:
                ok, text, info = profiles.apply(data, name,
                                                best_effort=force)
                log.info("profile '%s' %s: %s", name,
                         "applied" if ok else "refused", text)
                failed = None
            except Exception:                    # the worker confesses
                log.exception("profile apply died for '%s'", name)
                ok, text, info = (False, "apply died: %s"
                                  % sys.exc_info()[1], None)
                failed = text

            def done():
                self._apply_buttons("normal")
                self._applying = False
                self._prof_msg = text
                if self._prof_sel == self._applied_name:
                    self._profiles_render()
                else:                            # the user switched
                    self._status_lbl.configure(  # mid-apply: show the
                                                 # outcome, skip the repaint
                    text=self._prof_msg)
                if not failed:
                    misses = (info or {}).get("no_shows") or []
                    if misses:
                        self._noshows_ask(misses)
            try:
                self.after(0, done)
            except (tk.TclError, RuntimeError):   # +RuntimeError: measured, dead-root class
                                                 # the apply ran - the worker
                                                 # still confesses
                log.exception("profile apply done() lost the marshal "
                              "for '%s'", name)
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
            **self.skin.text_style()).pack(padx=theme.S_SECTION, pady=(theme.S_SECTION, theme.S_ROW))
        line = ctk.CTkFrame(dlg, fg_color="transparent")
        line.pack(pady=(0, theme.S_SECTION))

        def retire():
            # ONE scheduled retire for this dialog (gate finding 1,
            # the wave's crash law): both buttons AND the X ride it;
            # destroy inside a live callback - button or protocol -
            # is the same 0xc0000374 double-destroy shape
            dlg.withdraw()
            dlg.after(0, dlg.destroy)

        def fix():
            if len(misses) == 1:
                self._pin_load({"proc": misses[0]["proc"],
                                "title": misses[0]["title"],
                                "rect": [0, 0, 0, 0]})
            retire()

        def quiet():
            prof = self._prof_data["profiles"].get(self._prof_sel)
            if prof:
                for m in misses:
                    for w in prof["wins"]:
                        if (w["proc"], w["title"]) == (m["proc"],
                                                       m["title"]):
                            w["quiet"] = True
                profiles.save(self._prof_data)
            retire()
        dlg.protocol("WM_DELETE_WINDOW", retire)
        ctk.CTkButton(line, text="I'll fix it", width=110,
                      command=fix, **self.skin.primary()).pack(
            side="left", padx=(0, theme.S_FIELD))
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

