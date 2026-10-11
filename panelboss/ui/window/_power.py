"""Power-plan tab: Windows timer hold-overrides, the powercfg
assistant, the Game DVR card, overrides viewer, hdr-while-away.
The gaming rate section lives in _gaming.py beside it: it shares
this tab's column but trades monitor rates, not powercfg flags.
"""

from __future__ import annotations

import logging
import queue
import threading
import time

import customtkinter as ctk

from ..shield import shield_pil
from ._constants import TIPS

log = logging.getLogger("ui")


class _PowerMixin:
    # --------------------------------------------------------- power plan --
    def _build_power(self, page):
        col = ctk.CTkFrame(page, width=560, fg_color="transparent")
        col.pack(side="left", fill="y")
        box = self._card(col, "override Windows' own timers",
                         "nothing in the power plan changes: the "
                         "timers are only held from firing while the app "
                         "is watching, and they are handed back the "
                         "moment it pauses, snoozes or quits")
        row = self._row(box, "screen power off", TIPS["hold_display"])
        self.hold_display_switch = ctk.CTkSwitch(row, text="",
                                                 font=self.skin.font(12),
                                                 command=self._hold_changed,
                                                 progress_color=self.skin.accent,
                                                 border_color=self.skin.border)
        self.hold_display_switch.grid(row=0, column=1, sticky="e")
        if self.cfg["power"].get("hold_display"):
            self.hold_display_switch.select()
        row = self._row(box, "sleep", TIPS["hold_sleep"])
        self.hold_sleep_switch = ctk.CTkSwitch(row, text="",
                                               font=self.skin.font(12),
                                               command=self._hold_changed,
                                               progress_color=self.skin.accent,
                                               border_color=self.skin.border)
        self.hold_sleep_switch.grid(row=0, column=1, sticky="e")
        if self.cfg["power"].get("hold_sleep"):
            self.hold_sleep_switch.select()

        box = self._card(col, "when the screens wake on their own")
        row = self._row(box, "unexpected wake", TIPS["wake"])
        self.policy_menu = ctk.CTkOptionMenu(
            row, values=["re-off after wake", "leave on after wake"],
            width=180, command=self._policy_changed,
            **self.skin.menu_style())
        self.policy_menu.grid(row=0, column=1, sticky="e")
        self.policy_menu.set(
            "re-off after wake"
            if self.cfg["recovery"]["wake_policy"] == "re_off"
            else "leave on after wake")
        row = self._row(box, "hold off while a fullscreen app owns "
                        "the display", TIPS["fullscreen"])
        self.fullscreen_switch = ctk.CTkSwitch(row, text="",
                                               font=self.skin.font(12),
                                               command=self._fullscreen_changed,
                                               progress_color=self.skin.accent,
                                               border_color=self.skin.border)
        self.fullscreen_switch.grid(row=0, column=1, sticky="e")
        if self.cfg["guards"]["fullscreen"]:
            self.fullscreen_switch.select()
        row = self._row(box, "auto re-off", TIPS["reoff"])
        self.reoff_label = ctk.CTkLabel(row, text="on",
                                        font=self.skin.font(12),
                                        **self.skin.text_style("sub"))
        self.reoff_label.grid(row=0, column=1, sticky="e")
        self.reoff_button = ctk.CTkButton(
            row, text="resume now", width=110,
            command=lambda: self.monitor.events.put(("reoff", False)),
            **self.skin.secondary())
        self.reoff_button.grid(row=0, column=2, sticky="e", padx=(6, 0))
        row = self._row(box, "put window positions back after wake",
                        TIPS["restore_windows"])
        self.restore_switch = ctk.CTkSwitch(row, text="",
                                            font=self.skin.font(12),
                                            command=self._restore_changed,
                                            progress_color=self.skin.accent,
                                            border_color=self.skin.border)
        self.restore_switch.grid(row=0, column=1, sticky="e")
        if self.cfg["power"].get("restore_windows"):
            self.restore_switch.select()

        # the UAC shield before the assistant label is the honest hint
        # that ticking it means one admin confirm (drawn to match the
        # system icon: quartered blue/amber, silver cross, ui.shield)
        box = self._card(col, "powercfg assistant")
        prow = ctk.CTkFrame(box, fg_color="transparent")
        prow.pack(anchor="w")
        self._shield_img = ctk.CTkImage(
            light_image=shield_pil(16), dark_image=shield_pil(16),
            size=(16, 16))
        ctk.CTkLabel(prow, text="", image=self._shield_img,
                     fg_color="transparent", width=22).pack(side="left")
        self.power_switch = ctk.CTkSwitch(
            prow, text="wait out other display locks",
            font=self.skin.font(12), command=self._power_assistant_changed,
            progress_color=self.skin.accent,
            border_color=self.skin.border)
        self.power_switch.pack(side="left")
        self.tips.button(prow, TIPS["assistant"]).pack(side="left",
                                                        padx=(6, 0))
        if self.cfg["power"]["assistant_task"]:
            self.power_switch.select()
        # the blockers report: the red lines are the apps that actually
        # hold the display (they pause the camera); everything else is
        # news. Scrollable: a crowded report never overflows the card.
        self.blockers_box = ctk.CTkTextbox(
            box, height=132, width=500, font=self.skin.font(10),
            fg_color=self.skin.field_bg, border_color=self.skin.border,
            border_width=1, corner_radius=self.skin.radius, wrap="word")
        self.blockers_box.pack(anchor="w", pady=(6, 0))
        # NOT state="disabled": that repaints every tag the same flat
        # color (measured - the red vanished). It stays enabled so the
        # tag colors live, and reads as a report by swallowing edits
        for seq in ("<Key>", "<<Paste>>", "<<Cut>>", "<<Undo>>",
                    "<Control-v>", "<Control-V>", "<Control-x>",
                    "<Control-X>", "<Control-z>", "<Control-Z>"):
            self.blockers_box.bind(seq, lambda event: "break")
        # the truth check: the switch must show REALITY (the task
        # store), not the config rumor - the task can outlive or
        # predate the flag, and /Query costs ~2 s here, so it asks in
        # the background; the answer may land while an install is mid-
        # flight (delete then create), so a first "gone" is doubted and
        # re-asked before believed
        def truth():
            from ... import power
            real = power.task_installed()
            for _ in range(3):
                if real:
                    break
                time.sleep(2)
                real = power.task_installed()
            log.info("assistant truth: task store says %s", real)
            # NOT self.after(0, ...): this thread can beat app.mainloop
            # (measured: schtasks answered while the constructor still
            # ran) and tkinter then raises "main thread is not in main
            # loop" - pythonw ate the traceback, the answer evaporated,
            # and the switch drifted from reality forever. The queue is
            # thread-safe whenever; _tick_ui drains it on the main
            # thread once the loop exists.
            self.ui_events.put(("assistant_truth", real))
        threading.Thread(target=truth, daemon=True).start()
        # the overrides manager exists only while the assistant does:
        # its entire data source is the assistant's dump, so the button
        # joins and leaves with the switch, never lies about data
        self.assistant_box = box
        self.overrides_button = ctk.CTkButton(
            box, text="manage powercfg overrides", width=250,
            command=self._show_overrides, **self.skin.secondary())
        self._assistant_ui(bool(self.cfg["power"]["assistant_task"]))
        row = self._row(col, "turn HDR off while away (OLED panels)",
                        TIPS["hdr_away"])
        self.hdr_away_switch = ctk.CTkSwitch(row, text="",
                                             font=self.skin.font(12),
                                             command=self._hdr_away_changed,
                                             progress_color=self.skin.accent,
                                             border_color=self.skin.border)
        self.hdr_away_switch.grid(row=0, column=1, sticky="e")
        if bool(self.cfg["power"].get("hdr_off_when_away")):
            self.hdr_away_switch.select()
        self._gaming_section(col)
        self._dvr_section(col)


    def _dvr_section(self, col):
        """The Game DVR card: one switch per registry tweak the
        gaming pack can promise (docs/apack-findings.md). The
        registry is the truth - a Settings page may rewrite the
        values at any time - so the switches read their state
        from the registry at render and hand it back after
        every click, and a failed write is reported in the
        status line instead of a dialog."""
        from ... import tweaks
        box = self._card(col, "Game DVR", TIPS["dvr"])
        self.dvr_switches = {}
        for tid, (label, _path, _name, _data, _timing) in tweaks.TOGGLES.items():
            row = self._row(box, label)
            sw = ctk.CTkSwitch(row, text="",
                               font=self.skin.font(12),
                               progress_color=self.skin.accent,
                               border_color=self.skin.border)
            # bind BOTH via defaults, after sw exists: binding
            # only tid left every lambda painting the LAST switch
            # from registry truth (the classic late-binding trap -
            # the clicked switch kept its raw state, repaint lied)
            sw.configure(command=lambda t=tid, s=sw:
                         self._dvr_toggle(t, s))
            sw.grid(row=0, column=1, sticky="e")
            if tweaks.is_on(tid):
                sw.select()
            self.dvr_switches[tid] = sw
        self.dvr_status = ctk.CTkLabel(
            box, text="", font=self.skin.font(11),
            **self.skin.text_style("sub"))
        self.dvr_status.pack(anchor="w")


    def _dvr_toggle(self, tid, sw):
        """The registry decides, not the click: apply when off,
        revert when on, then repaint the switch from the
        registry again (the user's click may have lost to a
        Settings page) and surface the error in the status
        line - no dialogs."""
        from ... import tweaks
        if tweaks.is_on(tid):
            ok, err = tweaks.revert(tid)
        else:
            ok, err = tweaks.apply(tid)
        if tweaks.is_on(tid):
            sw.select()
        else:
            sw.deselect()
        self.dvr_status.configure(text="" if ok else err)


    def _policy_changed(self, label):
        name = "re_off" if label.startswith("re-off") else "leave_on"
        self.cfg["recovery"]["wake_policy"] = name
        self.monitor.events.put(("wake_policy", name))
        self._save()


    def _fullscreen_changed(self):
        self.cfg["guards"]["fullscreen"] = bool(self.fullscreen_switch.get())
        self._save()


    def _hold_changed(self):
        # cfg["power"] IS monitor.power_cfg, and the loop re-asserts
        # the execution state every tick: both switches are live within
        # 0.2 s, each on its own
        self.cfg["power"]["hold_display"] = bool(
            self.hold_display_switch.get())
        self.cfg["power"]["hold_sleep"] = bool(
            self.hold_sleep_switch.get())
        self._save()


    def _restore_changed(self):
        # cfg["power"] IS monitor.power_cfg: the snapshot/restore hooks
        # read restore_windows fresh at every off/wake edge
        self.cfg["power"]["restore_windows"] = bool(
            self.restore_switch.get())
        self._save()


    def _hdr_away_changed(self):
        self.cfg["power"]["hdr_off_when_away"] = bool(
            self.hdr_away_switch.get())
        self._save()


    # -------------------------------------------------------- power assistant --
    def _assistant_truth(self, real):
        """Adopt the task store's answer as the switch state and tell
        the monitor, so config, UI and reality cannot disagree."""
        try:
            was = bool(self.power_switch.get())
            log.info("assistant adoption: switch says %s, store says %s",
                     was, real)
            if was != real:
                self.power_switch.set(real)          # set() is click-free
                self.cfg["power"]["assistant_task"] = real
                self.monitor.events.put(("power_assistant", real))
                self._save()                         # the file learned the
                # truth too, or a test that scribbled assistant_task=false
                # over it keeps whispering lies to every future instance
                # until some unrelated widget change happens to save it
        except Exception:
            log.exception("assistant adoption crashed")  # pythonw has no
            # stderr: without this the whole thread's answer evaporated
            # silently, which is exactly how "does not persist" was born
        self._assistant_ui(real)


    def _assistant_ui(self, on):
        """Everything that lives and dies with the assistant switch."""
        try:
            if on:
                if not self.overrides_button.winfo_manager():
                    self.overrides_button.pack(anchor="w", pady=(6, 0))
            else:
                self.overrides_button.pack_forget()
        except Exception:
            pass                        # still building, or already gone


    def _show_overrides(self):
        """One manager window; opening it again just lifts the old one."""
        win = getattr(self, "_overrides_win", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win._claim_focus()          # the trick that works,
                    return win                    # not a bare lift
            except Exception:
                pass
        from .. import overrides
        self._overrides_win = overrides.OverridesWindow(
            self.cfg, self.monitor, self.skin, parent=self)
        return self._overrides_win


    def _power_assistant_changed(self):
        """Tick ON registers the task (one UAC confirm, which can flash
        up behind this borderless window); tick OFF deletes it. Both
        paid on a worker thread so the window stays alive."""
        want = bool(self.power_switch.get())
        self.power_msg = ("waiting for the admin confirm - check the "
                          "taskbar if no prompt is visible"
                          if want else "removing the scheduled task...")
        self.power_msg_ts = time.time()

        def work():
            from ... import power
            ok, msg = power.install() if want else power.uninstall()
            self.cfg["power"]["assistant_task"] = bool(ok and want)
            self.monitor.events.put(("power_assistant", bool(ok and want)))
            self.ui_events.put(("assistant_ui", bool(ok and want)))
            if not ok:
                self.power_msg = msg
                self.power_msg_ts = time.time()
                self.after(0, lambda: self.power_switch.set(not want))
            else:
                # the waiting line must die on success too, or the user
                # never learns the truth until its expiry timer ends it
                self.power_msg = ""
                self.power_msg_ts = 0.0
                try:    # read through the assistant just created (or
                        # honestly say admin after deleting), instead of
                        # letting last week's error string linger
                    self.monitor.blockers = power.requests(
                        self.cfg["power"]["ignore"],
                        assistant=bool(ok and want))
                except Exception:
                    pass
                self.after(0, self._update_blockers)
        threading.Thread(target=work, daemon=True).start()

