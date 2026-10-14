"""Power-plan tab: Windows timer hold-overrides, the powercfg
assistant, the Game DVR card, overrides viewer, hdr-while-away.
The gaming rate section lives in _gaming.py beside it: it shares
this tab's SECOND column (Oct 12, owner: the gaming cards moved
right) but trades monitor rates, not powercfg flags.
Size law (measured 479, Oct 13 after the widget-blind family's
both-branch paint landed - the two-column split and the defect-2
knob-from-truth paint came before it): this
is ONE page's paint-and-refresh
routine; splitting the cards across files would scatter the tab's
ordering lessons for zero readability the window/ split already
took its share - this one stays whole.
"""

from __future__ import annotations

import logging
import queue
import threading
import time

import tkinter as tk

import customtkinter as ctk

from .. import theme
from ..shield import shield_pil
from ._constants import TIPS
from ._text import SkewText
from ._widgets import SkewCombo

log = logging.getLogger("ui")


class _PowerMixin:
    # --------------------------------------------------------- power plan --
    def _build_power(self, page):
        col = ctk.CTkFrame(page, width=560, fg_color="transparent")
        col.pack(side="left", fill="y")
        # the profiles tab's two-column law, extended here on the
        # owner's word (Oct 12): the gaming refresh-rates card and
        # the Game DVR card move to column two - they are the
        # page's rare-visit knobs, not its timer story, and the
        # single-column page had grown into the owner's "too long"
        # complaint by exactly the distance their cards add
        col2 = ctk.CTkFrame(page, width=520, fg_color="transparent")
        col2.pack(side="left", fill="y")
        box = self._card(col, "override Windows' own timers",
                         "nothing in the power plan changes: the "
                         "timers are only held from firing while the app "
                         "is watching, and they are handed back the "
                         "moment it pauses, snoozes or quits")
        row = self._row(box, "screen power off", TIPS["hold_display"])
        self.hold_display_switch = ctk.CTkSwitch(row, text="",
                                                 font=self.skin.font(12),
                                                 command=self._hold_changed,
                                                 **self.skin.switch_style())
        self.hold_display_switch.grid(row=0, column=1, sticky="e")
        # knob-from-truth, BOTH branches (the _sync_consent_switch /
        # dd42d43 idiom, now the whole house's law): painting only
        # select() on the True case lets the false case ride the
        # widget's build default instead of the config - a fresh CTk
        # is off by accident, and the owner's afternoon of catching
        # widget-blind paints proved accidents do not survive reuse.
        if self.cfg["power"].get("hold_display"):
            self.hold_display_switch.select()
        else:
            self.hold_display_switch.deselect()
        row = self._row(box, "sleep", TIPS["hold_sleep"])
        self.hold_sleep_switch = ctk.CTkSwitch(row, text="",
                                               font=self.skin.font(12),
                                               command=self._hold_changed,
                                               **self.skin.switch_style())
        self.hold_sleep_switch.grid(row=0, column=1, sticky="e")
        if self.cfg["power"].get("hold_sleep"):
            self.hold_sleep_switch.select()
        else:
            self.hold_sleep_switch.deselect()

        box = self._card(col, "when the screens wake on their own")
        row = self._row(box, "unexpected wake", TIPS["wake"])
        self.policy_menu = SkewCombo(
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
                                               **self.skin.switch_style())
        self.fullscreen_switch.grid(row=0, column=1, sticky="e")
        if self.cfg["guards"]["fullscreen"]:
            self.fullscreen_switch.select()
        else:
            self.fullscreen_switch.deselect()
        row = self._row(box, "auto re-off", TIPS["reoff"])
        self.reoff_label = ctk.CTkLabel(row, text="on",
                                        font=self.skin.font(12),
                                        **self.skin.text_style("sub"))
        self.reoff_label.grid(row=0, column=1, sticky="e")
        self.reoff_button = ctk.CTkButton(
            row, text="resume now", width=110,
            command=lambda: self.monitor.events.put(("reoff", False)),
            **self.skin.secondary())
        self.reoff_button.grid(row=0, column=2, sticky="e",
                               padx=(theme.S_FIELD, 0))
        row = self._row(box, "put window positions back after wake",
                        TIPS["restore_windows"])
        self.restore_switch = ctk.CTkSwitch(row, text="",
                                            font=self.skin.font(12),
                                            command=self._restore_changed,
                                            **self.skin.switch_style())
        self.restore_switch.grid(row=0, column=1, sticky="e")
        if self.cfg["power"].get("restore_windows"):
            self.restore_switch.select()
        else:
            self.restore_switch.deselect()

        # the UAC shield before the assistant label is the honest hint
        # that ticking it means one admin confirm (drawn to match the
        # system icon: quartered blue/amber, silver cross, ui.shield)
        box = self._card(col, "powercfg assistant")
        cell = ctk.CTkFrame(box, fg_color="transparent")
        cell.pack(anchor="w")
        prow = ctk.CTkFrame(cell, fg_color="transparent")
        prow.pack(anchor="w")
        self._shield_img = ctk.CTkImage(
            light_image=shield_pil(16), dark_image=shield_pil(16),
            size=(16, 16))
        ctk.CTkLabel(prow, text="", image=self._shield_img,
                     fg_color="transparent", width=22).pack(side="left")
        self._assistant_gen = 0                # click round-trips: the
                                               # switch re-enables only on
                                               # the event for the click
                                               # that disabled it
        self.power_switch = ctk.CTkSwitch(
            prow, text="wait out other display locks",
            font=self.skin.font(12), command=self._power_assistant_changed,
            **self.skin.switch_style())
        self.power_switch.pack(side="left")
        # UI-1c reversal: the assistant paragraph pops on the switch's
        # own label (CTkSwitch.bind forwards to its canvas + text label)
        self.power_switch.bind(
            "<Enter>",
            lambda e=None: self.tips._schedule(TIPS["assistant"],
                                               self.power_switch),
            add="+")
        self.power_switch.bind(
            "<Leave>", lambda e=None: self.tips._hide_soon(), add="+")
        self._hint(cell, TIPS["assistant"])
        # THE RECONCILED SWITCH (the ruling the E2 ledger owed): the
        # truth thread below asks the task store once per build and
        # posts the answer; both branches now paint from cfg, so the
        # lie window is EXACTLY one truth beat: typical ~1 s
        # (schtasks /Query), doubt-loop worst ~12 s (3 reads x ~2 s
        # + 2 x 2 s sleeps), measured 3.4 s on this box (22:47:34
        # boot -> 22:47:37 truth line). A lying ON self-heals OFF
        # within that beat; the wave-B consent law keeps a stray task
        # from ever lighting an OFF switch (flag is consent). After
        # the beat the switch is store-honest until a click re-enters
        # the install/uninstall verify-poll (disabled + msg line,
        # 2 s cadence, 180 s human budget).
        if self.cfg["power"]["assistant_task"]:
            self.power_switch.select()
        else:
            self.power_switch.deselect()
        # the blockers report: the red lines are the apps that actually
        # hold the display (they pause the camera); everything else is
        # news. Scrollable: a crowded report never overflows the card.
        self.blockers_box = SkewText(
            box, height=132, width=500, font=self.skin.font(10),
            fg_color=self.skin.field_bg,
            border_color=self.skin.border_raised,
            border_width=1, corner_radius=self.skin.radius, wrap="word")
        self.blockers_box.pack(anchor="w", pady=(theme.S_FIELD, 0))
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
            try:
                from ... import power
                real = power.task_installed()
                for _ in range(3):
                    if real:
                        break
                    time.sleep(2)
                    real = power.task_installed()
                log.info("assistant truth: task store says %s", real)
                # NOT self.after(0, ...): this thread can beat
                # app.mainloop (measured: schtasks answered while the
                # constructor still ran) and tkinter then raises
                # "main thread is not in main loop" - pythonw ate the
                # traceback, the answer evaporated, and the switch
                # drifted from reality forever. The queue is
                # thread-safe whenever; _tick_ui drains it on the main
                # thread once the loop exists.
                self.ui_events.put(("assistant_truth", real))
            except Exception:
                # the task store itself is unreadable: post NOTHING
                # (absence already renders the default), but confess
                # loudly - pythonw has no stderr, and a silent truth
                # is how "does not persist" was born
                log.exception("assistant truth unreadable")
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
                                             **self.skin.switch_style())
        self.hdr_away_switch.grid(row=0, column=1, sticky="e")
        if bool(self.cfg["power"].get("hdr_off_when_away")):
            self.hdr_away_switch.select()
        else:
            self.hdr_away_switch.deselect()
        self._gaming_section(col2)      # column two (owner request)
        self._dvr_section(col2)


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
                               **self.skin.switch_style())
            # bind BOTH via defaults, after sw exists: binding
            # only tid left every lambda painting the LAST switch
            # from registry truth (the classic late-binding trap -
            # the clicked switch kept its raw state, repaint lied)
            sw.configure(command=lambda t=tid, s=sw:
                         self._dvr_toggle(t, s))
            sw.grid(row=0, column=1, sticky="e")
            # knob-from-truth, BOTH branches (the _sync_consent_switch
            # idiom): the old build painted only select() on the True
            # case, so the switch's position came from the widget's
            # default (off) rather than from what the registry actually
            # said - a switch that can never show "on" when the value is
            # absent, and that would keep a stale knob on a reused
            # widget. Paint the false case explicitly (defect 2).
            if tweaks.is_on(tid):
                sw.select()
            else:
                sw.deselect()
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
        """Reconcile the switch with the task store - one direction
        only (wave B, the consent law): the store losing the task
        un-lights a switch that would lie, but the flag is CONSENT
        and a stray task (this box's twin predates the wipe) gets no
        vote to flip an OFF switch or re-write True behind the user's
        back. The task rides inert while the flag is off: the loop
        never consults it (requests(assistant=False)) and the
        switch's own click path owns it from there (install re-points
        with /F, uninstall deletes)."""
        try:
            was = bool(self.power_switch.get())
            log.info("assistant adoption: switch says %s, store says %s",
                     was, real)
            if was != real:
                if real:
                    # store True vs a switch saying OFF: the flag
                    # wins, and the law says so out loud (silent
                    # ignorance is the bug class this whole wave is)
                    log.info("assistant off: adoption silent")
                else:
                    self.power_switch.set(real)      # set() is click-free
                    self.cfg["power"]["assistant_task"] = real
                    self.monitor.events.put(("power_assistant", real))
                    self._save()                     # the file learned the
                    # truth too, or a test that scribbled assistant_task=false
                    # over it keeps whispering lies to every future instance
                    # until some unrelated widget change happens to save it
        except Exception:
            log.exception("assistant adoption crashed")  # pythonw has no
            # stderr: without this the whole thread's answer evaporated
            # silently, which is exactly how "does not persist" was born
        self._assistant_ui(bool(self.cfg["power"]["assistant_task"]))


    def _assistant_ui(self, on, gen=None):
        """Everything that lives and dies with the assistant switch.
        When a generation is passed (the drain path), the switch
        re-enables only if this event is for the click that disabled
        it - a stale event from an older click must not un-quiet a
        switch a newer click has since disabled."""
        if gen is not None:
            # the re-enable is for the click that disabled the switch
            # - and only for that one, never for its stale predecessors
            if gen != self._assistant_gen:
                return
            try:
                self.power_switch.configure(state="normal")
            except tk.TclError:
                pass
        try:
            if on:
                if not self.overrides_button.winfo_manager():
                    self.overrides_button.pack(anchor="w",
                                               pady=(theme.S_FIELD, 0))
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
        paid on a worker thread so the window stays alive. The switch
        is disabled at click until the assistant_ui event for THIS
        click arrives (the generation counter) - a mid-flight flip
        would re-enter a task operation that is still in flight."""
        want = bool(self.power_switch.get())
        self._assistant_gen += 1
        gen = self._assistant_gen
        self.power_switch.configure(state="disabled")
        self.power_msg = ("waiting for the admin confirm - check the "
                          "taskbar if no prompt is visible"
                          if want else "removing the scheduled task...")
        self.power_msg_ts = time.time()

        def work():
            try:
                from ... import power
                ok, msg = power.install() if want else power.uninstall()
                self.cfg["power"]["assistant_task"] = bool(ok and want)
                self.monitor.events.put(("power_assistant", bool(ok and want)))
                self.ui_events.put(("assistant_ui", (bool(ok and want),
                                                      gen)))
                if not ok:
                    self.power_msg = msg
                    self.power_msg_ts = time.time()
                    self.after(0, lambda: self.power_switch.set(not want))
                else:
                    # the waiting line must die on success too, or the
                    # user never learns the truth until its expiry timer
                    # ends it
                    self.power_msg = ""
                    self.power_msg_ts = 0.0
                    try:    # read through the assistant just created
                             # (or honestly say admin after deleting),
                             # instead of letting last week's error
                             # string linger
                        self.monitor.blockers = power.requests(
                            self.cfg["power"]["ignore"],
                            assistant=bool(ok and want))
                    except Exception:
                        pass
                    self.after(0, self._update_blockers)
            except Exception:
                # the worker confesses: post a state event so the
                # switch RE-SYNCS against the truth (the drain reads
                # it through _assistant_truth) - a dead worker that
                # leaves the switch in the clicked state is a silent
                # lie
                log.exception("power assistant install/uninstall died")
                try:
                    real = power.task_installed()
                except Exception:
                    real = bool(self.cfg["power"]["assistant_task"])
                self.power_msg = ("the task store could not confirm "
                                  "the change - re-syncing")
                self.power_msg_ts = time.time()
                self.ui_events.put(("assistant_truth", real))
                self.ui_events.put(("assistant_ui", (bool(
                    self.cfg["power"]["assistant_task"]), gen)))
        threading.Thread(target=work, daemon=True).start()

