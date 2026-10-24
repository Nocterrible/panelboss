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

from ... import config, update
from .. import deps, theme
from ._constants import TIPS
from ._widgets import SkewCombo, set_text

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
        # knob-from-truth, BOTH branches (the _sync_consent_switch
        # idiom): painting only select() on the True case let the false
        # case ride the widget's build default instead of the config -
        # the consent-switch init family fixed once in _detection; every
        # switch in this pane now paints from truth at build.
        if self.cfg["ui"].get("start_minimized"):
            self.min_switch.select()
        else:
            self.min_switch.deselect()
        # the updater lives here because it is meta: it replaces the
        # app, not anything the app watches. BOTH installs answer to
        # the row now: the git one runs update.bat (its visible
        # console carries the relaunch), the msi one asks GitHub and
        # hands a downloaded -user.msi to a one-shot cmd (update.py);
        # the frozen era of hiding the row is over.
        row = self._row(box, "check for updates", TIPS["update"])
        self.update_row = row
        self.update_status = ctk.CTkLabel(row, text="",
                                          font=self.skin.font(11),
                                          anchor="w",
                                          **self.skin.text_style("sub"))
        self.update_status.grid(row=0, column=1, sticky="e",
                                padx=(0, theme.S_ROW))
        self.check_button = ctk.CTkButton(
            row, text="check now", width=90, command=self._check_updates,
            **self.skin.secondary())
        self.check_button.grid(row=0, column=2, sticky="e")
        self.update_button = ctk.CTkButton(
            row, text="update now", width=110, command=self._update_now,
            **self.skin.secondary())
        self.update_button.grid(row=0, column=3, sticky="e",
                                padx=(theme.S_ROW, 0))
        # design 3: the row states the version it is running (so a
        # user can see what they have, not only whether an answer
        # came); _update_status_line repaints the very same widget.
        self.update_status.configure(text="running " + update.__version__)
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
        self._build_hotkeys(col)


    # ------------------------------------------------------ keybindings --
    # Four verbs, one card (the four-verb wave, Oct 24): the pause
    # hotkey moved here from the dimmer card. Each verb binds on
    # keypress, esc clears, and is unbound until the owner gives one.
    # The capture rides hotkeys.capture (keysym -> the win32 VK), the
    # arm rides hotkeys.sync on the state loop's beat, and the say row
    # shows the dated confession - never a silent lie. The registry owns
    # the RegisterHotKey; this card owns only the words' UI.
    _HOTKEY_VERBS = (("pause", "pause dimming",
                      "pause the dimmer without touching its settings; "
                      "one press pauses, the next resumes"),
                     ("theater", "movie theater",
                      "toggle movie theater mode - the same switch the "
                      "companion card owns"),
                     ("restore", "restore my windows",
                      "put the windows back where the captured profile "
                      "left them"),
                     ("detection", "detection toggle",
                      "flip the detection tab's big consent switch "
                      "on or off"))

    def _build_hotkeys(self, col):
        box = self._card(col, "keybindings",
                         "bind a combo on keypress, esc clears it; "
                         "nothing is stolen until you give one - a "
                         "taken combo keeps its predecessor and says so")
        self._hotkey_btns = {}
        self._hotkey_says = {}
        from ... import hotkeys
        for name, label, tip in self._HOTKEY_VERBS:
            row = self._row(box, label, tip, hint_chars=42)
            btn = ctk.CTkButton(
                row, text="press a key to bind", height=26, width=170,
                command=lambda n=name: self._hotkey_bind(n),
                **self.skin.secondary())
            btn.grid(row=0, column=1, sticky="e")
            say = ctk.CTkLabel(row, text="", font=self.skin.font(11),
                               wraplength=120, justify="left", anchor="e",
                               **self.skin.text_style("sub"))
            say.grid(row=0, column=2, sticky="e",
                     padx=(theme.S_FIELD, 0))
            self._hotkey_btns[name] = btn
            self._hotkey_says[name] = say
            self._hotkey_words(name)
        self.after(1000, self._hotkey_poll)

    def _hotkey_bind(self, name):
        if getattr(self, "_hk_pending", None) == name:
            self._hotkey_disarm()
            return
        self._hk_pending = name
        self.bind_all("<KeyPress>", self._hotkey_capture)
        self.bind("<FocusOut>", self._hotkey_focus_out)
        self._hotkey_btns[name].configure(text="press a key now")

    def _hotkey_disarm(self):
        self._hk_pending = None
        self.unbind_all("<KeyPress>")
        self.unbind("<FocusOut>")
        for name in self._hotkey_btns:
            self._hotkey_btns[name].configure(text="press a key to bind")

    def _hotkey_focus_out(self, _event=None):
        if getattr(self, "_hk_pending", None) is not None:
            self._hotkey_disarm()

    def _hotkey_capture(self, event):
        name = getattr(self, "_hk_pending", None)
        if name is None:
            return
        if event.keysym in ("Control_L", "Control_R", "Shift_L",
                            "Shift_R", "Alt_L", "Alt_R",
                            "Super_L", "Super_R"):
            return "break"          # a modifier's own keydown carries
                                    # state=0; keep waiting for the chord
        self._hotkey_disarm()
        from ... import hotkeys
        if event.keysym == "Escape":
            hotkeys.set_bound(self.cfg, name, None)
            self._save()
            self._hotkey_words(name)
            return
        pair, word = hotkeys.capture(event.keysym, event.state)
        log.info("hotkeys: capture: %s keysym=%r state=%#x -> stored %r",
                 name, event.keysym, event.state, pair)
        if word:
            set_text(self._hotkey_says[name], word)
            return
        hotkeys.set_bound(self.cfg, name, pair)
        self._save()
        self._hotkey_words(name)

    def _hotkey_words(self, name):
        from ... import hotkeys
        note = hotkeys.note(name)
        if note:
            set_text(self._hotkey_says[name], note)     # the dated refusal
        elif hotkeys.live(name):
            set_text(self._hotkey_says[name], "live")
        elif hotkeys.bound(name, self.cfg):
            set_text(self._hotkey_says[name], "stored - answers next beat")
        else:
            set_text(self._hotkey_says[name], "unbound")

    def _hotkey_poll(self):
        """The say rows follow the engine (a taken combo answered AFTER
        the capture surfaces here) - the away card's poll idiom."""
        try:
            if getattr(self, "_dying", False):
                return
            for name in self._hotkey_btns:
                self._hotkey_words(name)
        except Exception:
            log.debug("hotkey poll failed", exc_info=True)
        try:
            self.after(1000, self._hotkey_poll)
        except Exception:
            pass                            # destroyed mid-tick


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


    def _sync_general_switches(self):
        """Knob-lie belt (see _power._sync_power_switches): the two
        truths this pane builds from - cfg and the Run key - painted
        again at settled geometry. _startup_sync is the build's own
        entry point (registry read, note re-set), reused verbatim."""
        from ... import startup
        self.min_switch.select() if self.cfg["ui"].get("start_minimized") \
            else self.min_switch.deselect()
        self._startup_sync(startup.enabled())


    def _open_log(self):
        # the door's fallback, not os.system: 'start ""' is cmd's own
        # verb and cmd brings its window; explorer.exe is a GUI
        # process and answers the folder request without one
        from ... import _spawn
        try:
            os.startfile(config.LOG_DIR)
        except Exception:
            _spawn.run(["explorer.exe", config.LOG_DIR])


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
        waiting on an optional package. On a FROZEN install this is
        the msi handoff below instead (and extra belongs to the bat:
        the installed app's optional bridges come inside the next
        release's package, not a pip run)."""
        if getattr(sys, "frozen", False):
            self._msi_handoff()
            return
        script = self.update_script()
        if not script:
            return
        self._save_now()                     # the debounced save may
                                             # never fire again - the
                                             # script reads the FILE
        try:
            # the package's ONE declared console-verb opt-out: the
            # updater WANTS its window (the console is the progress
            # UI and it carries the relaunch past our exit), so it
            # rides creationflags zero explicitly, never the door's
            # belt pair. startup_test/gaming_test count this line:
            # a second bare or bare-flagged spawn fails the build.
            subprocess.Popen(["cmd.exe", "/c", script] + list(extra)
                             + ["relaunch"], cwd=os.path.dirname(script),
                             creationflags=0)   # CONSOLE: deliberate
        except Exception:
            log.exception("update refused to start; the app stays up")
            return
        self.monitor.events.put(("quit", True))


    def _check_updates(self):
        """"check now": the answer is a sentence in the row, and the
        network is a worker thread's job (the _startup_changed
        idiom: daemon thread, after(0) marshal, dead-root caught);
        a re-click while one round trip is in flight is ignored -
        one flight at a time, one sentence at a time."""
        if getattr(self, "_update_flight", False):
            return
        self._update_flight = True

        def work():
            try:
                answer = update.check()
            except Exception:                # check() catches ALL by
                log.exception("update check died")   # design; even a
                answer = ("error", None)             # dead worker owes
                                                 # the row a sentence
                                                 # and the flag an
                                                 # unlock
            try:
                self.after(0, lambda: self._update_status_line(*answer))
            except (tk.TclError, RuntimeError):   # +RuntimeError:
                log.exception("update check lost the marshal")  # dead-
                                                 # root class, the
                                                 # measured one
        threading.Thread(target=work, daemon=True).start()


    def _update_status_line(self, status, version):
        """The row's reporting half: current and behind name their
        numbers, error says offline and nothing else (offline-by-
        default is a sentence, never a traceback, never a balloon)."""
        self._update_flight = False
        if status == "error":
            self.update_status.configure(text="could not check - "
                                              "offline?")
        elif status == "behind":
            self.update_status.configure(text="%s available" % version)
        else:
            self.update_status.configure(text="up to date (%s)" % version)


    def _msi_handoff(self):
        """The frozen 'update now': the check decides whether anything
        is worth fetching, the download brings it, and a one-shot
        apply.bat installs it once the app stops moving. A 'current'
        click does not download; an 'error' click MAY ride the stored
        url of the last honest 'behind' (the last one is remembered
        for exactly this - a flaky API must not unship a known
        release), and an error with nothing stored says so and the
        app stays up. check AND download are network verbs, so the
        whole round trip rides the worker; the quit sequence mirrors
        the source path exactly - debounced save, spawn, event."""
        if getattr(self, "_update_flight", False):
            return
        self._update_flight = True

        def go():
            msi = None
            status, version = update.check()  # self-catching: never
            #                                 # raises - only download
            #                                 # can, and its failure
            #                                 # must keep 'behind' to
            rel = update.stored_release()     # reach the right sentence
            try:
                if rel and (status == "behind"
                            or (status == "error"
                                and update.is_newer(rel["version"],
                                                    update.__version__))):
                    msi = update.download(rel["url"])
            except Exception:
                log.exception("the msi update round trip died")
            try:
                self.after(0, lambda: self._msi_done(status, version,
                                                     msi))
            except (tk.TclError, RuntimeError):
                log.exception("msi update lost the marshal")
        threading.Thread(target=go, daemon=True).start()


    def _msi_done(self, status, version, msi):
        """The UI-thread half of the handoff: the row reports what the
        round trip meant, and a fetched msi gets its script and its
        spawn here. The spawn is the update.bat line's twin and the
        package's SECOND registered console opt-out - startup_test's
        ledger counts both, gaming_test's ban accepts both, and the
        third bare spawn still fails the build."""
        self._update_flight = False
        if msi is None:
            if status == "behind":           # the download died; the
                self.update_status.configure(     # app stays up honest
                    text="download failed - try again")
            else:
                self._update_status_line(status, version)
            return
        self._save_now()                     # the debounced save may
                                             # never fire again - the
                                             # source path's courtesy,
                                             # kept
        exe = os.path.join(os.path.dirname(sys.executable),
                           "PanelBoss.exe")
        bat = update.write_apply(msi, exe, os.getpid(),
                                 os.path.dirname(msi))
        try:
            subprocess.Popen(["cmd.exe", "/c", bat],
                             cwd=os.path.dirname(bat),
                             creationflags=0)   # CONSOLE: deliberate
        except Exception:
            log.exception("the msi handoff refused to start; the "
                          "app stays up")
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
        from ... import camera, config
        if switch:
            # law 3 (the ghost-law build): the roster word rides the
            # ONE funnel. The process is about to quit and the one the
            # updater reopens boots straight into hello IR, but the
            # word goes out anyway: the ("camera", ...) event lands
            # the toml, the "camera roster now" line, and the honest
            # release in the same drain that carries the quit - a
            # silent in-memory move is the class this funnel exists to
            # bury (and _update_now's own save has the file correct
            # either way before the script runs).
            config.set_camera_roster(self.cfg, camera.HELLO_IR,
                                     events=self.monitor.events)
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

