"""Gaming refresh-rate section of the power plan tab.
Size law (measured 345, Oct 15 - the DVR row's half of the sync
entry retired with the card's burial, from the Oct 13's 385; the
claim includes its own
lines; the knob-lie sync entry added the last sixteen, the
amendment-8 color selector the thirty before): the
card, its commits and the
exe browse are one story read top-to-bottom when a rate or a list
misbehaves; the pure list/commit helpers could split, but the
pair has been the debug surface for every gaming bug this month
(vrr lies, the front-of-me miss, the dead-box fill) - it stays
whole one file below the justify line, not two above it.
"""

from __future__ import annotations

import logging
import threading

import customtkinter as ctk
import tkinter as tk

from .. import theme
from ... import wm
from ._constants import HDR_SET_LABELS, TIPS
from ._text import SkewText
from ._widgets import SkewCombo

log = logging.getLogger("ui")


class _GamingMixin:
    def _gaming_section(self, col):
        """The refresh-rate watcher's face: it joins the power-plan
        tab (a fifth tab was refused on measured repaint cost) and
        reads its facts off the same cfg the watcher re-reads every
        tick, so writing cfg["gaming"] IS applying it. The rate menus
        offer only what the panel's driver already lists
        (wm.offered_modes - the same list wanted_hz trades from), so
        the UI can never ask for a mode the panel will not take."""
        g = self.cfg.get("gaming") or {}
        box = self._card(col, "gaming refresh rates",
                         "a fullscreen game takes its panel's top "
                         "rate; the desktop gets its own back when "
                         "the game leaves. only the rate is traded - "
                         "the resolution is never touched")
        row = self._row(box, "watch games and trade rates",
                        TIPS["gaming"])
        self.gaming_switch = ctk.CTkSwitch(row, text="",
                                           font=self.skin.font(12),
                                           command=self._gaming_changed,
                                           **self.skin.switch_style())
        self.gaming_switch.grid(row=0, column=1, sticky="e")
        # knob-from-truth at build (both branches, the _sync_consent_switch
        # idiom): a CTkSwitch defaults off so the false case is
        # coincidentally right on a FRESH widget, but the switch must be
        # painted from cfg, not from a default that happens to match -
        # a rebuild/selection on a reused widget would otherwise lie.
        if g.get("enabled"):
            self.gaming_switch.select()
        else:
            self.gaming_switch.deselect()
        # one row per live panel: the game rate first, the rate the
        # desktop gets back second - both only among the rates that
        # panel's driver offers. In their OWN frame: the desk can
        # change under a living window (Oct 17), and the fill is
        # discard-and-refill like the away rows.
        self.gaming_row_frame = ctk.CTkFrame(box, fg_color="transparent")
        self.gaming_row_frame.pack(anchor="w", fill="x")
        self._gaming_fill_rows()
        # the two exe lists: one name per line, and the lines ARE the
        # list - the commit on focus-out is the save
        row = self._row(box, "games (one exe per line)",
                        TIPS["gaming_games"])
        self.games_box = SkewText(
            row, height=84, width=230, font=self.skin.font(11),
            fg_color=self.skin.field_bg,
            border_color=self.skin.border_raised,
            border_width=1, corner_radius=self.skin.radius, wrap="word")
        self.games_box.grid(row=0, column=1, sticky="e")
        self.games_box.insert("1.0", "\n".join(g.get("games") or []))
        self.games_box.bind("<<FocusOut>>", self._gaming_games_commit)
        # foreground() can block for seconds (anti-cheat pids), so the
        # button only starts the probe: the answer comes back on the
        # main thread, and a miss just leaves the list alone
        btns = ctk.CTkFrame(row, fg_color="transparent")
        btns.grid(row=0, column=2, sticky="e", padx=(theme.S_FIELD, 0))
        self.add_fg_button = ctk.CTkButton(
            btns, text="add what's in front of me", width=170,
            command=self._gaming_add_foreground, **self.skin.secondary())
        self.add_fg_button.pack(anchor="e")
        # browse beats typing (owner, Oct 12): the exe picker appends
        # the BASE name to the box and commits at once - the same
        # form the free-text list stores, so the watcher's matching
        # never learns the difference
        ctk.CTkButton(btns, text="browse to exe...", width=170,
                      command=lambda: self._gaming_browse(self.games_box),
                      **self.skin.secondary()).pack(anchor="e",
                                                    pady=(4, 0))
        row = self._row(box, "never games (one exe per line)",
                        TIPS["gaming_ignore"])
        self.ignore_box = SkewText(
            row, height=60, width=230, font=self.skin.font(11),
            fg_color=self.skin.field_bg,
            border_color=self.skin.border_raised,
            border_width=1, corner_radius=self.skin.radius, wrap="word")
        self.ignore_box.grid(row=0, column=1, sticky="e")
        self.ignore_box.insert("1.0", "\n".join(g.get("ignore") or []))
        self.ignore_box.bind("<<FocusOut>>", self._gaming_ignore_commit)
        ctk.CTkButton(row, text="browse to exe...", width=170,
                      command=lambda: self._gaming_browse(self.ignore_box),
                      **self.skin.secondary()).grid(row=0, column=2,
                                                    sticky="e",
                                                    padx=(theme.S_FIELD, 0))
        # the plan a game earns: a name fragment or a guid; '' leaves
        # the plan alone entirely
        row = self._row(box, "power plan while gaming",
                        TIPS["gaming_plan"])
        self.plan_entry = ctk.CTkEntry(
            row, width=180, font=self.skin.font(12),
            placeholder_text="fragment or guid ('' = never)",
            fg_color=self.skin.field_bg, border_width=1,
            border_color=self.skin.border_raised,
            corner_radius=self.skin.radius)
        self.plan_entry.insert(0, g.get("power_plan") or "")
        self.plan_entry.grid(row=0, column=1, sticky="e")
        self.plan_entry.bind("<<FocusOut>>", self._gaming_plan_commit)


    def _gaming_fill_rows(self):
        """Discard-and-refill (the _away/_cam_rows idiom): one rate
        pair per live panel, into the card's row frame; the answers
        come from cfg and the driver, never from the dying widgets."""
        g = self.cfg.setdefault("gaming", {})
        for widget in self.gaming_row_frame.winfo_children():
            widget.destroy()
        self.gaming_menus = {}
        # the per-panel color selector (amendment 8) rides the
        # desktop-rate row of every panel a PRECISE driver read says
        # can do HDR; nowhere else - an absent selector is the
        # honest answer, a grayed one is a lie awaiting a driver
        # update
        self.gaming_hdr_menus = {}
        caps = wm.hdr_caps()
        for m in wm.monitors():
            # the driver's offered rates may be EMPTY (a silent or
            # fictional driver - the RDP session display lists one
            # made-up mode at best); the row still renders, because the
            # enforcement reads desktop_hz/game_hz per panel regardless
            # of whether the driver lists the rate (wanted_hz falls back
            # to the panel's current mode). A saved rate rides its menu
            # even when the driver stopped listing it, so a hand-set or
            # previously-chosen rate is never invisible; junk entries
            # die by name at the config normalize boundary (hzmap), the
            # same law as every other map - the menu only ever shows
            # what survived that filter.
            hz = self._offered_hz(m)
            gs = (g.get("game_hz") or {}).get(m["short"])
            ds = (g.get("desktop_hz") or {}).get(m["short"])
            game_hz = sorted(set(hz) | ({gs} if isinstance(gs, int) else set()))
            desk_hz = sorted(set(hz) | ({ds} if isinstance(ds, int) else set()))
            row = self._row(self.gaming_row_frame,
                            "%s - game rate" % m["short"],
                            TIPS["gaming_rates"])
            # 'VRR (pin max)' is not a rate: it declares the panel's
            # scanout belongs to the driver's variable rate, so the
            # watcher never flips it (and pins it at its max outside
            # games). The card's first entry stays 'auto' - the game
            # menu has no 'keep' (that is the desktop menu's word)
            game_vals = ["auto", "VRR (pin max)"] + [str(v) for v in game_hz]
            game_menu = SkewCombo(
                row, values=game_vals, width=120,
                command=lambda v, s=m["short"]:
                self._gaming_game_hz(s, v),
                **self.skin.menu_style())
            stored = gs
            # a stored 'vrr' shows as its menu label; anything else
            # shows its own string, falling back to the default the
            # same way the desktop menu does
            shown = ("VRR (pin max)"
                     if str(stored).strip().lower() == "vrr"
                     else str(stored))
            game_menu.set(shown if stored is not None
                          and shown in game_vals[1:] else "auto")
            game_menu.grid(row=0, column=1, sticky="e")
            row = self._row(self.gaming_row_frame,
                            "%s - desktop rate" % m["short"],
                            TIPS["gaming_rates"])
            # 'keep' is not a rate, it is the ABSENCE of a rule - the
            # menu must show that truth, not a fake '60' that config
            # never agreed to (this exact lie is why the feature
            # looked broken: menus showed 60, cfg said {}, nothing was
            # configured, the watcher correctly held nothing)
            desk_vals = ["keep"] + [str(v) for v in desk_hz]
            desk_menu = SkewCombo(
                row, values=desk_vals, width=100,
                command=lambda v, s=m["short"]:
                self._gaming_desk_hz(s, v),
                **self.skin.menu_style())
            stored = ds
            desk_menu.set(str(stored) if stored is not None
                          and str(stored) in desk_vals[1:] else "keep")
            desk_menu.grid(row=0, column=1, sticky="e")
            if caps.get(m["gdi"]):
                hdr_menu = SkewCombo(
                    row, values=[lab for lab, _ in HDR_SET_LABELS],
                    width=90,
                    command=lambda v, s=m["short"]:
                    self._gaming_hdr(s, v),
                    **self.skin.menu_style())
                stored = (g.get("hdr") or {}).get(m["short"])
                hdr_menu.set("hdr on" if stored is True
                             else "hdr off" if stored is False
                             else "keep")
                hdr_menu.grid(row=0, column=2, sticky="e",
                              padx=(theme.S_FIELD, 0))
                self.gaming_hdr_menus[m["short"]] = hdr_menu
            self.gaming_menus[m["short"]] = (game_menu, desk_menu)

    def _gaming_rebuild_rows(self):
        self._gaming_fill_rows()

    @staticmethod
    def _offered_hz(m):
        """A panel's rates as ascending ints, parsed from the driver's
        'WxH@Hz' list (the very list the watcher trades from); empty
        when the driver answers nothing."""
        out = set()
        for name in wm.offered_modes(m["gdi"]):
            try:
                out.add(int(name.rsplit("@", 1)[1]))
            except (IndexError, ValueError):
                continue
        return sorted(out)


    # ------------------------------------------------------------ gaming ---
    def _sync_gaming_switches(self):
        """Knob-lie belt (see _power._sync_power_switches): the enable
        switch from cfg - the truth its build reads, painted again at
        settled geometry. (The DVR row's registry repaint rode this
        same seam until the card's Oct-15 burial; the enable switch
        outlives it.)"""
        self.gaming_switch.select() if self.cfg["gaming"].get("enabled") \
            else self.gaming_switch.deselect()


    def _gaming_changed(self):
        # cfg["gaming"] IS the watcher's gcfg: the loop re-reads it
        # every tick, so writing is applying
        self.cfg["gaming"]["enabled"] = bool(self.gaming_switch.get())
        self._save()


    def _gaming_game_hz(self, short, label):
        if label == "VRR (pin max)":
            self.cfg["gaming"]["game_hz"][short] = "vrr"
        elif label == "auto" and (
                self.cfg["gaming"]["game_hz"].get(short) == "vrr"):
            # back to the default = the vrr rule comes off: pop the
            # rule, the same pattern the desktop keep uses ('auto'
            # and an unset entry answer the same, the panel's
            # fastest)
            self.cfg["gaming"]["game_hz"].pop(short, None)
        else:
            self.cfg["gaming"]["game_hz"][short] = (
                "auto" if label == "auto" else int(label))
        self._save()


    def _gaming_desk_hz(self, short, label):
        # 'keep' = delete the rule, not store a string: the watcher
        # must treat this panel as nobody's business again. int('keep')
        # would raise INSIDE the widget callback - silently, in
        # pythonw - and the pick would evaporate before _save().
        if label == "keep":
            self.cfg["gaming"]["desktop_hz"].pop(short, None)
        else:
            self.cfg["gaming"]["desktop_hz"][short] = int(label)
        self._save()


    def _gaming_hdr(self, short, label):
        """The desktop-color trinary (amendment 8): 'keep' DELETES the
        rule (TOML has no null - the absence of the key is the
        absence of the claim, and a written false would lie about a
        command), true/false tasks the desktop pass outside games.
        The write is cfg + _save exactly like the rate menus - the
        watcher re-reads cfg every tick, so writing the cfg IS
        applying it."""
        want = dict(HDR_SET_LABELS).get(label)
        hdr = self.cfg["gaming"].setdefault("hdr", {})
        if want is None:
            hdr.pop(short, None)
        else:
            hdr[short] = want
        self._save()


    def _gaming_games_commit(self, event=None):
        self._gaming_list_commit("games", self.games_box)


    def _gaming_ignore_commit(self, event=None):
        self._gaming_list_commit("ignore", self.ignore_box)


    def _gaming_list_commit(self, key, box):
        """Focus left a list box: the lines (blanks dropped) are the
        list now."""
        lines = [line.strip() for line in box.get("1.0", "end")
                 .splitlines()]
        self.cfg["gaming"][key] = [line for line in lines if line]
        self._save()


    def _gaming_browse(self, box):
        """The exe picker (owner: browse beats free-edit): the file
        dialog returns a path, the BOX stores the base name - the
        form every other entry takes and the matcher already speaks -
        appended once (duplicates are a no-op, not a shrug) and
        committed immediately. The dialog runs on the UI thread like
        every modal; the monitor loop is a different thread and never
        notices the pause."""
        from tkinter import filedialog
        from pathlib import Path
        import os
        start = os.environ.get("PROGRAMFILES") or "C:\\"
        path = filedialog.askopenfilename(
            parent=self, title="pick the game executable",
            initialdir=start, filetypes=[("Executables", "*.exe"),
                                         ("All files", "*.*")])
        if not path:
            return
        name = Path(path).name.lower()
        have = [line.strip().lower() for line in box.get("1.0", "end")
                .splitlines() if line.strip()]
        if name not in have:
            box.insert("end", ("\n" if have else "") + name)
        # commit through the SAME seam a typed line takes (the commit
        # functions themselves, not a queued virtual event - an
        # event_generate would land on the next loop turn and the box
        # would look uncommitted to anything reading right now)
        if box is self.games_box:
            self._gaming_games_commit()
        else:
            self._gaming_ignore_commit()


    def _gaming_fill_list(self, key):
        box = self.games_box if key == "games" else self.ignore_box
        try:
            box.delete("1.0", "end")
            box.insert("1.0", "\n".join(self.cfg["gaming"].get(key)
                                        or []))
        except tk.TclError:
            # a dead box must not eat the answer: the cfg append and
            # the save are the truth, the widget is a view - and
            # views die (observed: a second in-process CTk root's
            # teardown destroying this window's SkewText, taking the
            # deferred front-of-me callback with it)
            pass


    def _gaming_plan_commit(self, event=None):
        self.cfg["gaming"]["power_plan"] = (self.plan_entry.get()
                                            or "").strip()
        self._save()


    def _gaming_add_foreground(self):
        """wm.foreground() can block for seconds (anti-cheat pids), so
        it runs on a daemon thread and hands the answer back through
        the main thread. Fail open: a miss just leaves the list
        alone - the desk is never told what it cannot know."""
        def work():
            try:
                fg = wm.foreground()
            except Exception:
                log.exception("gaming: the foreground probe died")
                return
            if not fg or not fg.get("proc"):
                return

            def done():
                proc = fg["proc"]
                games = self.cfg["gaming"].setdefault("games", [])
                if proc in games:
                    return
                games.append(proc)
                self._gaming_fill_list("games")
                self._save()
            try:
                self.after(0, done)
            except Exception:
                pass            # the window closed while the probe ran

        threading.Thread(target=work, daemon=True).start()

