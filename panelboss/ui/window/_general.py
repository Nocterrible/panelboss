"""General tab: skin, tray start, updates, deps,
autostart.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import textwrap
import threading
import time
import tkinter as tk

import customtkinter as ctk

from ... import config
from .. import deps, theme
from ._constants import TIPS
from ._widgets import SkewCombo

log = logging.getLogger("ui")


class _GeneralMixin:
    # -------------------------------------------------------------- general --
    def _build_general(self, page):
        from ... import startup
        col = ctk.CTkFrame(page, width=460, fg_color="transparent")
        col.pack(side="left", fill="y")
        box = self._card(col, "General")
        row = self._row(box, "skin", TIPS["skin"])
        self.skin_menu = SkewCombo(
            row, values=[s.label for s in theme.SKINS.values()],
            width=140, command=self._skin_changed,
            **self.skin.menu_style())
        self.skin_menu.grid(row=0, column=1, sticky="e")
        self.skin_menu.set(self.skin.label)
        row = self._row(box, "start minimized to tray", TIPS["min"])
        self.min_switch = ctk.CTkSwitch(row, text="",
                                        font=self.skin.font(12),
                                        command=self._start_min_changed,
                                        **self.skin.switch_style())
        self.min_switch.grid(row=0, column=1, sticky="e")
        if self.cfg["ui"].get("start_minimized"):
            self.min_switch.select()
        # the updater lives here because it is meta: it replaces the
        # app, not anything the app watches. the frozen exe has no
        # repo to pull, so the row hides itself there.
        row = self._row(box, "check for updates", TIPS["update"])
        self.update_row = row
        self.update_button = ctk.CTkButton(
            row, text="update now", width=110, command=self._update_now,
            **self.skin.secondary())
        self.update_button.grid(row=0, column=1, sticky="e")
        if getattr(sys, "frozen", False):
            row.pack_forget()
        row = self._row(box, "open log folder", TIPS["logs"])
        ctk.CTkButton(row, text="open", width=110, command=self._open_log,
                      **self.skin.secondary()).grid(row=0, column=1,
                                                    sticky="e")
        # the switch mirrors the HKCU Run key, not a config rumor: a
        # stale entry from a deleted folder lights it up honest, and
        # the note spells out where the entry actually points (move the
        # app folder and the old entry keeps firing at logon; one flip
        # off and on re-points it here)
        row = self._row(box, "start with Windows", TIPS["startup"])
        self.startup_switch = ctk.CTkSwitch(row, text="",
                                            font=self.skin.font(12),
                                            command=self._startup_changed,
                                            **self.skin.switch_style())
        self.startup_switch.grid(row=0, column=1, sticky="e")
        self.startup_note = ctk.CTkLabel(box, text="",
                                         font=self.skin.font(11),
                                         wraplength=420, justify="left",
                                         anchor="w",
                                         **self.skin.text_style("sub"))
        self.startup_note.pack(anchor="w")
        self._startup_sync(startup.enabled())


    # ------------------------------------------------------------- helpers --
    @staticmethod
    def _set_menu(menu, value):
        try:
            menu.set(value)
        except Exception:
            pass                            # values not populated yet


    @staticmethod
    def _mode_label(stored):
        return "boot per poll" if stored == "boot_per_poll" else "always on"


    @staticmethod
    def _mode_value(shown):
        return "boot_per_poll" if shown == "boot per poll" else "always_on"


    def _skin_changed(self, label):
        for skin in theme.SKINS.values():
            if skin.label == label:
                self.cfg["ui"]["skin"] = skin.key
                break
        self._save()
        self.rebuild_for_skin()


    def _start_min_changed(self):
        # read once at boot (the tip says so): no live effect possible
        # on a window that is, at this moment, open
        self.cfg["ui"]["start_minimized"] = bool(self.min_switch.get())
        self._save()


    def _open_log(self):
        try:
            os.startfile(config.LOG_DIR)
        except Exception:
            os.system('start "" "%s"' % config.LOG_DIR)


    @staticmethod
    def update_script():
        """update.bat, beside the package - or None. The frozen exe
        carries no repo and no script, so it has nothing to run."""
        if getattr(sys, "frozen", False):
            return None
        root = os.path.dirname(os.path.dirname(
            os.path.abspath(config.__file__)))
        script = os.path.join(root, "update.bat")
        return script if os.path.exists(script) else None


    def _update_now(self, extra=()):
        """The update replaces the very files THIS app runs from, so
        the courtesies are in order: hand the job (plus the relaunch
        promise) to cmd, quit, let the script work on quiet files.
        cmd.exe must be the one to run the .bat - CreateProcess
        cannot exec a batch file directly; the app has no console of
        its own, so the script's console opens fresh, visible, and
        outlives us (it must, it carries the relaunch). extra carries
        the updater's other flags - ("deps",) when a feature is
        waiting on an optional package."""
        script = self.update_script()
        if not script:
            return
        self._save_now()                     # the debounced save may
                                             # never fire again - the
                                             # script reads the FILE
        try:
            subprocess.Popen(["cmd.exe", "/c", script] + list(extra)
                             + ["relaunch"], cwd=os.path.dirname(script))
        except Exception:
            log.exception("update refused to start; the app stays up")
            return
        self.monitor.events.put(("quit", True))


    def _dep_prompt(self, switch):
        """One prompt per missing package on screen at a time (a
        re-open just lifts the old one). switch=True when the user was
        picking the hello IR entry - installing then also SELECTS the
        camera, because that is what the click meant."""
        win = getattr(self, "_dep_win", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win._claim_focus()
                    return win
            except Exception:
                pass
        self._dep_win = deps.Deprompt(
            self, self.skin, "hello IR", "whircam",
            "The infrared-camera bridge is an optional package (MIT, "
            "a few hundred kB). The updater installs it and reopens "
            "the app a moment later; the desk is unsupervised only "
            "for that moment, and nothing in the timers or the power "
            "plan changes.",
            lambda: self._dep_install(switch))
        return self._dep_win


    def _dep_install(self, switch):
        from ... import camera
        if switch:
            self.cfg["camera"]["index"] = camera.HELLO_IR
            # no camera event: this process is about to quit, and the
            # one the updater reopens boots straight into hello IR
        self._update_now(extra=("deps",))


    # -------------------------------------------------------------- startup --
    def _startup_sync(self, stored):
        """Checkbox + note from the registry's answer (None | string)."""
        from ... import startup
        self.startup_switch.select() if stored else \
            self.startup_switch.deselect()
        if not stored:
            text = ""
        elif stored == startup.command():
            text = ("registered for this copy (see Task Manager's "
                    "startup apps)")
        else:
            text = ("entry points elsewhere: %s - flip off and on to "
                    "re-point here" % textwrap.shorten(stored, width=46))
        self.startup_note.configure(text=text)


    def _startup_changed(self):
        """The write verifies itself by re-read; the switch always ends
        on what the registry says, never on hope. Registry I/O is fast,
        but a locked-down hive can block on policy - the worker keeps
        even that worst case off the UI thread. Single-flight: the
        switch disables at click and wakes only when this round trip
        answers (last-click-wins: a second flip cannot over- or under-
        write the first in the window)."""
        from ... import startup
        want = bool(self.startup_switch.get())
        self.startup_switch.configure(state="disabled")

        def work():
            try:
                ok, msg = (startup.enable() if want
                           else startup.disable())
                stored = startup.enabled()
                try:
                    self.after(0,
                               lambda: self._startup_done(ok, msg, stored))
                except (tk.TclError, RuntimeError):   # +RuntimeError: measured, dead-root class
                    log.exception(               # mid-write: confess,
                        "autostart round trip lost the marshal")  # the
            except Exception:                    # registry already holds
                log.exception(                   # the real answer - the
                    "autostart round trip died")  # switch must still come
                                                  # back clickable: a dead
                                                  # worker with a dead
                                                  # switch is one more
                                                  # silent daemon death
                try:
                    self.after(0, lambda: self.startup_switch.configure(
                        state="normal"))
                except (tk.TclError, RuntimeError):
                    pass
        threading.Thread(target=work, daemon=True).start()


    def _startup_done(self, ok, msg, stored):
        if not ok:
            self.startup_note.configure(text=msg)      # the failure needs
            self.startup_switch.set(1 if stored else 0)     # to introduce
            self.startup_switch.configure(                  # itself
                state="normal")                             # on the truth
            return                                      # the registry gave
        self._startup_sync(stored)
        self.startup_switch.configure(state="normal")

