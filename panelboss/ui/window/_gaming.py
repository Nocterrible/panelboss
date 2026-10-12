"""Gaming refresh-rate section of the power plan tab.
"""

from __future__ import annotations

import logging
import threading

import customtkinter as ctk

from .. import theme
from ... import wm
from ._constants import TIPS
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
        if g.get("enabled"):
            self.gaming_switch.select()
        # one row per live panel: the game rate first, the rate the
        # desktop gets back second - both only among the rates that
        # panel's driver offers
        self.gaming_menus = {}
        for m in wm.monitors():
            hz = self._offered_hz(m)
            if not hz:
                continue          # the driver said nothing: nothing
                                  # to offer this panel
            row = self._row(box, "%s - game rate" % m["short"],
                            TIPS["gaming_rates"])
            # 'VRR (pin max)' is not a rate: it declares the panel's
            # scanout belongs to the driver's variable rate, so the
            # watcher never flips it (and pins it at its max outside
            # games). The card's first entry stays 'auto' - the game
            # menu has no 'keep' (that is the desktop menu's word)
            game_vals = ["auto", "VRR (pin max)"] + [str(v) for v in hz]
            game_menu = SkewCombo(
                row, values=game_vals, width=120,
                command=lambda v, s=m["short"]:
                self._gaming_game_hz(s, v),
                **self.skin.menu_style())
            stored = (g.get("game_hz") or {}).get(m["short"])
            # a stored 'vrr' shows as its menu label; anything else
            # shows its own string, falling back to the default the
            # same way the desktop menu does
            shown = ("VRR (pin max)"
                     if str(stored).strip().lower() == "vrr"
                     else str(stored))
            game_menu.set(shown if stored is not None
                          and shown in game_vals[1:] else "auto")
            game_menu.grid(row=0, column=1, sticky="e")
            row = self._row(box, "%s - desktop rate" % m["short"],
                            TIPS["gaming_rates"])
            # 'keep' is not a rate, it is the ABSENCE of a rule - the
            # menu must show that truth, not a fake '60' that config
            # never agreed to (this exact lie is why the feature
            # looked broken: menus showed 60, cfg said {}, nothing was
            # configured, the watcher correctly held nothing)
            desk_vals = ["keep"] + [str(v) for v in hz]
            desk_menu = SkewCombo(
                row, values=desk_vals, width=100,
                command=lambda v, s=m["short"]:
                self._gaming_desk_hz(s, v),
                **self.skin.menu_style())
            stored = (g.get("desktop_hz") or {}).get(m["short"])
            desk_menu.set(str(stored) if stored is not None
                          and str(stored) in desk_vals[1:] else "keep")
            desk_menu.grid(row=0, column=1, sticky="e")
            self.gaming_menus[m["short"]] = (game_menu, desk_menu)
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
        self.add_fg_button = ctk.CTkButton(
            row, text="add what's in front of me", width=170,
            command=self._gaming_add_foreground, **self.skin.secondary())
        self.add_fg_button.grid(row=0, column=2, sticky="e",
                                padx=(theme.S_FIELD, 0))
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


    def _gaming_fill_list(self, key):
        box = self.games_box if key == "games" else self.ignore_box
        box.delete("1.0", "end")
        box.insert("1.0", "\n".join(self.cfg["gaming"].get(key) or []))


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

