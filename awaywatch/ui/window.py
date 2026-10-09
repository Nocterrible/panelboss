"""The settings window (CTk, main thread - Tk always owns thread zero).

Rules this file lives by:
* it never touches the camera or the display: commands go through the
  state machine's queue, or into the shared config dicts the worker
  reads every tick (cfg["timers"] IS monitor.timers - writing it is
  applying it, no round trip needed)
* the debug view draws from monitor.framebox: the picture next to the
  camera picker is literally the frame the model just judged
* camera enumeration boots every index (this machine's virtual camera
  takes up to 16 s), so it always runs off the UI thread

Skins come from theme.py; nothing here hardcodes a color.
"""

from __future__ import annotations

import logging
import os
import queue
import textwrap
import threading
import time

import cv2
import customtkinter as ctk
from PIL import Image

from .. import config
from . import theme
from .shield import shield_pil

log = logging.getLogger("ui")

TIMER_SPECS = [          # section, key, label, min, max, step
    ("timers", "idle_gate_sec", "idle gate", 0, 180, 5),
    ("timers", "absent_confirm_sec", "absence confirm", 10, 300, 5),
    ("timers", "on_poll_sec", "poll while on", 1, 15, 1),
    ("timers", "off_poll_sec", "poll while off", 1, 15, 1),
    ("timers", "present_recheck_sec", "present recheck", 10, 300, 5),
    ("timers", "re_off_grace_sec", "re-off grace", 0, 120, 5),
    ("recovery", "leave_on_grace_sec", "leave-on grace", 10, 600, 10),
]

DEVICE_KEYS = [("auto", "auto"), ("cpu", "CPU"), ("cuda", "CUDA GPU")]
DEVICE_BY_LABEL = dict((label, key) for key, label in DEVICE_KEYS)


class SettingsWindow(ctk.CTk):

    def __init__(self, cfg, monitor, ui_events):
        super().__init__()
        self.cfg = cfg
        self.monitor = monitor
        self.ui_events = ui_events
        self.skin = theme.get_skin(cfg["ui"]["skin"])
        self.title("ICU Presence Detector")
        self.geometry("920x640")
        self.minsize(760, 520)
        self.protocol("WM_DELETE_WINDOW", self._hide)     # close = to tray
        self._cams = None
        self._shown_ts = None
        self._ctkimg = None
        self._save_job = None
        self._lease_ticks = 0
        ctk.set_appearance_mode(self.skin.mode)
        self.configure(fg_color=self.skin.bg)
        self.build_all()
        self._scan_cameras()
        self.after(90, self._tick_ui)

    # ------------------------------------------------------------- build --
    def build_all(self):
        self._top = ctk.CTkFrame(self, fg_color="transparent")
        self._top.pack(fill="x", padx=14, pady=(12, 6))
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self._build_top()
        self._build_right()                  # camera + preview column so
        self._build_left()                   # it exists beside the picker

    def rebuild_for_skin(self):
        for widget in (self._top, self._body):
            widget.destroy()
        self.skin = theme.get_skin(self.cfg["ui"]["skin"])
        ctk.set_appearance_mode(self.skin.mode)
        self.configure(fg_color=self.skin.bg)
        self._shown_ts = None                # repaint the preview fresh
        build_all = self.build_all()

    def _card(self, parent, title, sub=""):
        frame = ctk.CTkFrame(parent, **self.skin.panel_style())
        frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(frame, text=title, font=self.skin.font(15, "bold"),
                     **self.skin.text_style()).pack(anchor="w", padx=14,
                                               pady=(10, 0))
        if sub:
            ctk.CTkLabel(frame, text=sub, font=self.skin.font(11),
                         **self.skin.text_style("sub")).pack(anchor="w",
                                                        padx=14)
        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=(6, 12))
        return inner

    def _row(self, parent, label):
        """One settings row: label left, widget right. Widgets are
        created ON THE ROW so grid only ever manages children of the
        row, pack only ever manages children of the card."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=2)
        row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(row, text=label, font=self.skin.font(12),
                     **self.skin.text_style()).grid(row=0, column=0, sticky="w")
        return row

    # ------------------------------------------------------------ top bar --
    def _build_top(self):
        ctk.CTkLabel(self._top, text="ICU Presence Detector",
                     font=self.skin.font(18, "bold"),
                     **self.skin.text_style()).pack(side="left")
        self.chip = ctk.CTkLabel(self._top, text=self.monitor.state,
                                 width=90, pady=3, corner_radius=10,
                                 font=self.skin.font(12, "bold"),
                                 text_color="#10131a",
                                 fg_color=self.skin.chip(
                                     self.monitor.state))
        self.chip.pack(side="left", padx=14)
        self.idle_label = ctk.CTkLabel(self._top, text="",
                                       font=self.skin.font(12),
                                       **self.skin.text_style("sub"))
        self.idle_label.pack(side="left")
        right = ctk.CTkFrame(self._top, fg_color="transparent")
        right.pack(side="right")
        self.pause_button = ctk.CTkButton(right, text="Pause", width=90,
                                          command=self._pause_toggle,
                                          **self.skin.secondary())
        self.pause_button.pack(side="right", padx=3)
        for minutes in (10, 30, 60):
            ctk.CTkButton(right, text="zzz %s" % minutes, width=72,
                          command=lambda m=minutes: self.monitor.events.put(
                              ("snooze", m)),
                          **self.skin.secondary()).pack(side="right",
                                                        padx=3)
        ctk.CTkButton(right, text="Quit", width=70, command=self._quit,
                      fg_color=self.skin.off,
                      hover_color=self.skin.button,
                      text_color=self.skin.text,
                      corner_radius=self.skin.radius).pack(side="right",
                                                           padx=3)

    # ------------------------------------------------------------- left ---
    def _build_left(self):
        self.left = ctk.CTkScrollableFrame(self._body, width=360,
                                           fg_color="transparent",
                                           scrollbar_button_color=
                                           self.skin.button,
                                           scrollbar_fg_color=
                                           self.skin.panel)
        self.left.pack(side="left", fill="y", padx=(0, 12))
        self._build_detection()
        self._build_timers()
        self._build_behavior()
        self._build_general()

    def _build_detection(self):
        box = self._card(self.left, "Detection")
        # the mode row leads the card: motion mode has no model at all,
        # so device and gpu id below it are then mere trivia
        row = self._row(box, "mode")
        self.mode_button = ctk.CTkSegmentedButton(
            row, values=["person (AI)", "motion (no AI)"], height=26,
            width=230, command=self._detect_mode_changed,
            **self.skin.segmented_style())
        self.mode_button.set(self._detect_mode_label(self.cfg))
        self.mode_button.grid(row=0, column=1, sticky="e")
        row = self._row(box, "device")
        menu = ctk.CTkOptionMenu(row, values=[label for _, label in
                                              DEVICE_KEYS], width=160,
                                 command=self._device_changed,
                                 **self.skin.menu_style())
        menu.grid(row=0, column=1, sticky="e")
        menu.set(dict(DEVICE_KEYS)[self.cfg["inference"]["device"]])

        from .. import inference
        self.gpu_ids = inference.cuda_gpus()
        if not self.gpu_ids:
            self.gpu_ids = [(n, "") for n in range(4)]
        labels = ["%s %s" % (gid, name[:32]) for gid, name in self.gpu_ids]
        row = self._row(box, "cuda gpu id")
        gpu_menu = ctk.CTkOptionMenu(row, values=labels, width=200,
                                     command=self._gpu_changed,
                                     **self.skin.menu_style())
        gpu_menu.grid(row=0, column=1, sticky="e")
        for gid, name in self.gpu_ids:
            if gid == self.cfg["inference"]["device_id"]:
                self._set_menu(gpu_menu, "%s %s" % (gid, name[:32]))
                break

        row = self._row(box, "confidence")
        self.conf_label = ctk.CTkLabel(row, font=self.skin.font(12),
                                       **self.skin.text_style("sub"))
        self.conf_label.grid(row=0, column=2, sticky="e", padx=(6, 0))
        slider = ctk.CTkSlider(row, from_=0.1, to=0.9,
                               number_of_steps=80,
                               width=180, command=self._confidence_changed,
                               **self.skin.slider_style())
        slider.set(self.cfg["inference"]["confidence"])
        slider.grid(row=0, column=1, sticky="e")
        self.conf_label.configure(
            text="%.2f" % self.cfg["inference"]["confidence"])

        row = self._row(box, "min hits")
        hits = ctk.CTkSegmentedButton(
            row, values=["1", "2", "3", "4"], height=26, width=170,
            command=self._min_hits_changed, **self.skin.segmented_style())
        hits.set(str(self.cfg["inference"]["min_hits"]))
        hits.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(box, text="device and gpu id apply immediately; "
                     "changing the model needs a restart; motion mode "
                     "loads no model, so device and id are ignored there",
                     font=self.skin.font(10),
                     **self.skin.text_style("sub")).pack(anchor="w", pady=(6, 0))

    def _build_timers(self):
        box = self._card(self.left, "Timers",
                         "written to config.toml, applied while the "
                         "loop runs")
        self.timer_labels = {}
        for section, key, label, lo, hi, step in TIMER_SPECS:
            row = self._row(box, label)
            value_label = ctk.CTkLabel(row, font=self.skin.font(12),
                                       **self.skin.text_style("sub"))
            value_label.grid(row=0, column=2, sticky="e", padx=(6, 0))
            slider = ctk.CTkSlider(row, from_=lo, to=hi,
                                   number_of_steps=int((hi - lo) / step),
                                   width=180,
                                   command=lambda v, s=section, k=key:
                                   self._timer_changed(s, k, v),
                                   **self.skin.slider_style())
            slider.set(self.cfg[section][key])
            slider.grid(row=0, column=1, sticky="e")
            value_label.configure(text="%ss" % self.cfg[section][key])
            self.timer_labels[key] = value_label
        self.worst_label = ctk.CTkLabel(box, font=self.skin.font(11),
                                        **self.skin.text_style("sub"))
        self.worst_label.pack(anchor="w", pady=(6, 0))
        self._update_worst()

    def _build_behavior(self):
        box = self._card(self.left, "Behavior")
        row = self._row(box, "unexpected wake")
        self.policy_menu = ctk.CTkOptionMenu(
            row, values=["re-off after wake", "leave on after wake"],
            width=180, command=self._policy_changed,
            **self.skin.menu_style())
        self.policy_menu.grid(row=0, column=1, sticky="e")
        self.policy_menu.set(
            "re-off after wake"
            if self.cfg["recovery"]["wake_policy"] == "re_off"
            else "leave on after wake")
        self.fullscreen_switch = ctk.CTkSwitch(
            box, text="hold off while a fullscreen app owns the display",
            font=self.skin.font(12), command=self._fullscreen_changed,
            progress_color=self.skin.accent,
            border_color=self.skin.border)
        if self.cfg["guards"]["fullscreen"]:
            self.fullscreen_switch.select()
        self.fullscreen_switch.pack(anchor="w", pady=6)
        row = self._row(box, "auto re-off")
        self.reoff_label = ctk.CTkLabel(row, text="on",
                                        font=self.skin.font(12),
                                        **self.skin.text_style("sub"))
        self.reoff_label.grid(row=0, column=1, sticky="e")
        self.reoff_button = ctk.CTkButton(
            row, text="resume now", width=110,
            command=lambda: self.monitor.events.put(("reoff", False)),
            **self.skin.secondary())
        self.reoff_button.grid(row=0, column=2, sticky="e", padx=(6, 0))

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
                    self.overrides_button.pack(anchor="w", padx=14,
                                               pady=(0, 10))
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
        from . import overrides
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
            from .. import power
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
                try:    # read through the assistant we just created (or
                        # honestly say admin after deleting it), instead
                        # of letting last week's error string linger
                    self.monitor.blockers = power.requests(
                        self.cfg["power"]["ignore"],
                        assistant=bool(ok and want))
                except Exception:
                    pass
                self.after(0, self._update_blockers)
        threading.Thread(target=work, daemon=True).start()

    def _build_general(self):
        from .. import startup
        box = self._card(self.left, "General")
        row = self._row(box, "skin")
        self.skin_menu = ctk.CTkOptionMenu(
            row, values=[s.label for s in theme.SKINS.values()],
            width=140, command=self._skin_changed,
            **self.skin.menu_style())
        self.skin_menu.grid(row=0, column=1, sticky="e")
        self.skin_menu.set(self.skin.label)
        row = self._row(box, "logs")
        ctk.CTkButton(row, text="open log folder", width=130,
                      command=self._open_log,
                      **self.skin.secondary()).grid(row=0, column=1,
                                                    sticky="e")
        # the switch mirrors the HKCU Run key, not a config rumor: a
        # stale entry from a deleted folder lights it up honest, and the
        # note below spells out where the entry actually points (move
        # the app folder and the old entry keeps firing at logon; one
        # flip off and on re-points it here)
        self.startup_switch = ctk.CTkSwitch(
            box, text="start with Windows",
            font=self.skin.font(12), command=self._startup_changed,
            progress_color=self.skin.accent,
            border_color=self.skin.border)
        self.startup_switch.pack(anchor="w", pady=(6, 0))
        self.startup_note = ctk.CTkLabel(box, text="",
                                          font=self.skin.font(11),
                                          justify="left", anchor="w",
                                          wraplength=300,
                                          **self.skin.text_style("sub"))
        self.startup_note.pack(anchor="w")
        self._startup_sync(startup.enabled())

    def _startup_sync(self, stored):
        """Checkbox + note from the registry's answer (None | string)."""
        from .. import startup
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
        even that worst case off the UI thread."""
        from .. import startup
        want = bool(self.startup_switch.get())

        def work():
            ok, msg = (startup.enable() if want else startup.disable())
            stored = startup.enabled()
            self.after(0, lambda: self._startup_done(ok, msg, stored))
        threading.Thread(target=work, daemon=True).start()

    def _startup_done(self, ok, msg, stored):
        if not ok:
            self.startup_note.configure(text=msg)     # the failure needs
            self.startup_switch.set(1 if stored else 0)   # to introduce
            return                                          # itself
        self._startup_sync(stored)

    # ------------------------------------------------- camera + preview ---
    def _build_right(self):
        # scrollable like its left twin: the card now carries preview +
        # report + switch stacked, and the window cannot promise that
        # height fits - unscrollable, the power switch was simply born
        # below the clip edge (seen live: the pane complained about
        # admin rights while the box to fix it was off-screen). The
        # textbox keeps its own wheel (ctk excludes it from column
        # scroll), everything else scrolls the card.
        card = ctk.CTkScrollableFrame(
            self._body, scrollbar_button_color=self.skin.button,
            scrollbar_fg_color=self.skin.panel,
            **self.skin.panel_style())
        card.pack(side="right", fill="both", expand=True)
        ctk.CTkLabel(card, text="Camera", font=self.skin.font(15, "bold"),
                     **self.skin.text_style()).pack(anchor="w", padx=14,
                                               pady=(10, 0))
        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.pack(fill="x", padx=14, pady=(6, 2))
        self.camera_menu = ctk.CTkOptionMenu(
            controls, values=["scanning cameras..."], width=300,
            command=self._camera_changed, **self.skin.menu_style())
        self.camera_menu.pack(side="left")
        ctk.CTkButton(controls, text="rescan", width=80,
                      command=self._scan_cameras,
                      **self.skin.secondary()).pack(side="left", padx=6)
        for key, label in (("mode_on", "while screens are on"),
                           ("mode_off", "while screens are off")):
            row = self._row(card, label)
            menu = ctk.CTkOptionMenu(row, values=["boot per poll",
                                                  "always on"], width=150,
                                     command=self._mode_changed(key),
                                     **self.skin.menu_style())
            menu.grid(row=0, column=1, sticky="e")
            menu.set(self._mode_label(self.cfg["camera"][key]))
        self.live_switch = ctk.CTkSwitch(
            card, text="live preview (holds the camera, ~5 fps)",
            font=self.skin.font(12), command=self._live_changed,
            progress_color=self.skin.accent,
            border_color=self.skin.border)
        self.live_switch.pack(anchor="w", padx=14, pady=(4, 8))
        self.power_msg = ""                      # install/uninstall result
        self.power_msg_ts = 0.0
        self.preview_frame = ctk.CTkFrame(card, fg_color=self.skin.field_bg,
                                          corner_radius=self.skin.radius)
        self.preview_frame.pack(pady=(0, 4), padx=14)
        self.preview_label = ctk.CTkLabel(self.preview_frame,
                                          text="no frames yet - flip on "
                                          "live preview",
                                          font=self.skin.font(12),
                                          **self.skin.text_style("sub"))
        self.preview_label.pack()
        self.preview_info = ctk.CTkLabel(card, text="",
                                         font=self.skin.font(10),
                                         **self.skin.text_style("sub"))
        self.preview_info.pack(anchor="w", padx=14, pady=(0, 4))
        # the blockers pane: below the preview, as wide as it is, and
        # scrollable so a crowded powercfg report never overflows the
        # card; the only RED lines are the ones that actually hold the
        # display (what pauses the camera) - everything else is news
        self.blockers_box = ctk.CTkTextbox(
            card, height=132, width=int(self.cfg["ui"]["preview_width"]),
            font=self.skin.font(10), fg_color=self.skin.field_bg,
            border_color=self.skin.border, border_width=1,
            corner_radius=self.skin.radius, wrap="word")
        self.blockers_box.pack(anchor="w", padx=14, pady=(0, 10))
        # NOT state="disabled": that repaints every tag the same flat
        # color (measured - the red vanished). It stays enabled so the
        # tag colors live, and reads as a report by swallowing edits
        for seq in ("<Key>", "<<Paste>>", "<<Cut>>", "<<Undo>>",
                    "<Control-v>", "<Control-V>", "<Control-x>",
                    "<Control-X>", "<Control-z>", "<Control-Z>"):
            self.blockers_box.bind(seq, lambda event: "break")
        # the switch below the report, not above the preview: the
        # blockers ARE the story of this card, the switch only feeds it;
        # the UAC shield before the label is the honest hint that
        # ticking it involves one admin confirm (drawn to match the
        # system icon: quartered blue/amber, silver cross, see ui.shield)
        prow = ctk.CTkFrame(card, fg_color="transparent")
        prow.pack(anchor="w", padx=14)
        self._shield_img = ctk.CTkImage(
            light_image=shield_pil(16), dark_image=shield_pil(16),
            size=(16, 16))
        ctk.CTkLabel(prow, text="", image=self._shield_img,
                     fg_color="transparent",
                     width=22).pack(side="left")
        self.power_switch = ctk.CTkSwitch(
            prow, text="powercfg assistant: wait out other display locks",
            font=self.skin.font(12), command=self._power_assistant_changed,
            progress_color=self.skin.accent,
            border_color=self.skin.border)
        self.power_switch.pack(side="left")
        if self.cfg["power"]["assistant_task"]:
            self.power_switch.select()
        # the switch must show REALITY (the task store), not the config
        # rumor - the task can outlive or predate the config flag, and
        # /Query costs ~2 s here, so ask in background; the answer may
        # also be sampled while an install is mid-flight (delete then
        # create), so a first "gone" gets re-asked before believed
        def truth():
            from .. import power
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
        # joins and leaves with the switch, never lies about having data
        self.overrides_button = ctk.CTkButton(
            card, text="manage powercfg overrides", width=250,
            command=self._show_overrides, **self.skin.secondary())
        self._assistant_ui(bool(self.cfg["power"]["assistant_task"]))

    # ----------------------------------------------------------- helpers ---
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

    # ----------------------------------------------------------- changes ---
    def _save(self):
        if self._save_job is not None:
            self.after_cancel(self._save_job)
        self._save_job = self.after(400, self._save_now)

    def _save_now(self):
        self._save_job = None
        try:
            config.write_config(self.cfg, self.cfg["_path"])
        except Exception:
            log.exception("config save failed")

    def _device_changed(self, label):
        name = DEVICE_BY_LABEL[label]
        self.cfg["inference"]["device"] = name
        self.monitor.events.put(("device", name))
        self._save()

    def _gpu_changed(self, label):
        gid = int(str(label).split(" ")[0])
        self.cfg["inference"]["device_id"] = gid
        self.monitor.events.put(("device_id", gid))
        self._save()

    def _confidence_changed(self, value):
        self.cfg["inference"]["confidence"] = round(float(value), 2)
        self.conf_label.configure(text="%.2f" % value)
        self.monitor.events.put(("confidence", round(float(value), 2)))
        self._save()

    def _min_hits_changed(self, value):
        if value:
            self.cfg["inference"]["min_hits"] = int(value)
            self._save()

    @staticmethod
    def _detect_mode_label(cfg):
        return ("motion (no AI)"
                if (cfg.get("detection") or {}).get("mode") == "motion"
                else "person (AI)")

    def _detect_mode_changed(self, label):
        mode = "motion" if str(label).startswith("motion") else "person"
        # the tray and the monitor read THIS dict; the event rebuilds the
        # detector through the factory (motion: no onnx touched at all)
        self.cfg["detection"]["mode"] = mode
        self.monitor.events.put(("detection_mode", mode))
        self._save()

    def _timer_changed(self, section, key, value):
        self.cfg[section][key] = int(round(value))
        # monitor.timers / monitor.recovery are these very dicts:
        # writing is applying
        self.timer_labels[key].configure(text="%ss" % round(value))
        self._update_worst()
        self._save()

    def _update_worst(self):
        timers = self.cfg["timers"]
        worst = timers["idle_gate_sec"] + timers["absent_confirm_sec"]
        self.worst_label.configure(
            text="worst case: dark %.0f s after the last keystroke" % worst)

    def _policy_changed(self, label):
        name = "re_off" if label.startswith("re-off") else "leave_on"
        self.cfg["recovery"]["wake_policy"] = name
        self.monitor.events.put(("wake_policy", name))
        self._save()

    def _fullscreen_changed(self):
        self.cfg["guards"]["fullscreen"] = bool(self.fullscreen_switch.get())
        self._save()

    def _skin_changed(self, label):
        for skin in theme.SKINS.values():
            if skin.label == label:
                self.cfg["ui"]["skin"] = skin.key
                break
        self._save()
        self.rebuild_for_skin()

    def _mode_changed(self, key):
        def command(label):
            self.cfg["camera"][key] = self._mode_value(label)
            self._save()
        return command

    def _camera_changed(self, shown):
        for entry in (self._cams or []):
            if shown.startswith("index %s" % entry[0]):
                self.cfg["camera"]["index"] = entry[0]
                self.monitor.events.put(("camera", entry[0]))
                self._save()
                return

    def _live_changed(self):
        on = bool(self.live_switch.get())
        self.monitor.events.put(("preview", 1.5 if on else 0))

    def _pause_toggle(self):
        self.monitor.events.put(("pause", not self.monitor.paused))

    def _quit(self):
        self.monitor.events.put(("quit", True))

    def _open_log(self):
        try:
            os.startfile(config.LOG_DIR)
        except Exception:
            os.system('start "" "%s"' % config.LOG_DIR)

    # ----------------------------------------------------------- cameras ---
    def _scan_cameras(self):
        """Opening every index is slow (the virtual camera alone takes
        up to 16 s), so enumerate on a helper thread and hand the answer
        back through after()."""
        def worker():
            from .. import camera
            try:
                names = camera.camera_names()
                found = [(index, opened, width,
                          names[index] if index < len(names) else "")
                         for index, opened, width
                         in camera.enumerate_cameras() if opened]
            except Exception:
                log.exception("camera scan failed")
                found = []
            try:
                self.ui_events.put(("cameras", found))
            except Exception:
                pass                    # the window closed mid-scan
        threading.Thread(target=worker, daemon=True, name="ui-scan").start()

    def _apply_cameras(self, found):
        self._cams = found
        labels = []
        for index, opened, width, name in found:
            label = "index %s (%s px)" % (index, int(width))
            if name:
                label += " %s" % name
            labels.append(label)
        if not labels:
            labels = ["no camera opens"]
        self.camera_menu.configure(values=labels)
        current = self.cfg["camera"]["index"]
        for label in labels:
            if label.startswith("index %s " % current) or \
                    label == "index %s" % current:
                self._set_menu(self.camera_menu, label)
                break

    # -------------------------------------------------------------- tick ---
    def destroy(self):
        """destroy() tears children down first while Tk still processes
        the queue - a pending tick then reschedules itself on the
        half-dead interpreter forever (measured: an endless "ui tick
        failed" loop whose mainloop never returned). Flag the dying
        state and the chain just quits."""
        self._dying = True
        super().destroy()

    def _tick_ui(self):
        if getattr(self, "_dying", False):
            return
        try:
            self._tick_inner()
        except Exception:
            log.exception("ui tick failed; the loop goes on")
        try:
            self.after(90, self._tick_ui)
        except Exception:
            pass                        # the window was destroyed

    def _tick_inner(self):
        now = time.monotonic()
        self._drain_ui_events()
        slot = self.monitor.framebox.get()
        if slot is not None and slot[3] != self._shown_ts:
            self._draw(slot)
        self._update_status(now, slot)
        if bool(self.live_switch.get()) and self.state() == "normal":
            self._lease_ticks += 1
            if self._lease_ticks % 6 == 0:      # ~0.5 s heartbeats for
                self.monitor.events.put(("preview", 1.5))    # a 1.5 s
                                                    # lease

    def _drain_ui_events(self):
        while True:
            try:
                message, _value = self.ui_events.get_nowait()
            except queue.Empty:
                break
            if message == "quit":
                self.destroy()
                return
            if message == "open":
                self.deiconify()
                self.lift()
                self.focus_force()
            if message == "assistant_truth":
                self._assistant_truth(_value)
            if message == "assistant_ui":
                self._assistant_ui(_value)
            if message == "startup":
                from .. import startup
                self._startup_sync(startup.enabled())
            if message == "cameras":
                self._apply_cameras(_value)

    def _update_status(self, now, slot):
        state = self.monitor.state
        if self.monitor.paused:
            state = "paused"
        self.chip.configure(text=state, fg_color=self.skin.chip(state))
        idle = self._idle()
        age = "never" if slot is None else "%.1f s" % (now - slot[3])
        self.idle_label.configure(
            text="idle %.0f s · frame %s old · %d seen"
            % (idle, age, len(slot[1]) if slot else 0))
        self.pause_button.configure(
            text="Resume" if self.monitor.paused else "Pause")
        paused_re = getattr(self.monitor, "re_off_paused", False)
        self.reoff_label.configure(
            text="PAUSED (camera slipped?)" if paused_re else "on")
        self.reoff_button.configure(
            state="normal" if paused_re else "disabled")
        self._update_blockers()
        want = self._detect_mode_label(self.cfg)   # a tray flip lands here
        if self.mode_button.get() != want:      # through the shared cfg
            self.mode_button.set(want)          # dict; set() fires no command

    def _update_blockers(self):
        b = getattr(self.monitor, "blockers", None) or {}
        err = b.get("error")
        held = b.get("display") or []
        others = b.get("other") or []
        over = b.get("overridden") or []     # "*OVERRIDE ..." already
        rows = []                            # (text, mood) - moods are
        if self.power_msg and time.time() - self.power_msg_ts < 25:
            rows.append((self.power_msg, "warn"))
        if err:                              # palette keys, nothing more
            rows.append((err, "warn"))
        if held:
            rows.append(("holding the display - the camera waits:",
                         "danger"))
            rows += [("  " + x[:80], "danger") for x in held[:6]]
        if over:
            rows.append(("user-overridden in powercfg - camera does "
                         "not wait for these:", "sub"))
            rows += [(x[:88], "sub") for x in over[:6]]
        if others:
            rows.append(("sleep only (fine): "
                         + "; ".join(x[:48] for x in others[:3]), "sub"))
        if not bool(self.power_switch.get()) and not (err or held):
            rows.append(("off: powercfg needs admin, so nothing is "
                         "checked and polling never pauses; tick to "
                         "register a scheduled task (one admin confirm)",
                         "sub"))
        if not rows:
            rows.append(("nothing pins the display; the camera guards it",
                         "ok"))
        colors = {"danger": self.skin.danger, "warn": self.skin.paused,
                  "sub": self.skin.subtext, "ok": self.skin.ok}
        sig = tuple(rows)
        if getattr(self, "_blockers_sig", None) == sig:
            return                    # identical text: never touch the
                                      # box - delete+insert snaps the
                                      # view to the top, and this runs
                                      # every tick, so the pane was
                                      # un-scrollable (user-confirmed)
        self._blockers_sig = sig
        box = self.blockers_box
        # customtkinter 6 turns tags= into a bare tag NAME and leaves
        # foreground empty (measured: tags on char 1.0 = ('#ff5d5d',)
        # with fg "") - the color goes on the inner tk.Text, per mood
        inner = getattr(box, "_textbox", box)
        for mood, color in colors.items():
            try:
                inner.tag_configure(mood, foreground=color)
            except Exception:
                pass
        try:                          # survive a real content change
            was = float(inner.yview()[0])      # where the user was
        except Exception:
            was = 0.0
        box.delete("1.0", "end")
        for text, mood in rows:
            box.insert("end", text + "\n", tags=mood)
        if was > 0.0:
            try:
                inner.yview_moveto(0, was)     # fraction of content:
            except Exception:                  # the honest best we can
                pass                           # do for changed text

    @staticmethod
    def _idle():
        from .. import display
        try:
            return display.get_idle_time()
        except Exception:
            return float("inf")

    def _draw(self, slot):
        frame, boxes, scores, ts = slot
        self._shown_ts = ts
        img = frame.copy()
        for box, score in zip(boxes, scores):
            cv2.rectangle(img, box[:2].astype(int), box[2:].astype(int),
                          color=self.skin.box_bgr, thickness=2)
            cv2.putText(img, "%.2f" % float(score),
                        (int(box[0]), max(int(box[1]) - 6, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.skin.box_bgr, 2)
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        width = int(self.cfg["ui"]["preview_width"])
        height = int(width * img.shape[0] / max(img.shape[1], 1))
        image = Image.fromarray(rgb).resize((width, height))
        self._ctkimg = ctk.CTkImage(light_image=image, dark_image=image,
                                    size=(width, height))
        self.preview_label.configure(image=self._ctkimg, text="")
        self.preview_info.configure(
            text="%dx%d · %d box%s · the exact frame the model judged"
            % (img.shape[1], img.shape[0], len(boxes),
               "" if len(boxes) == 1 else "es"))

    # ------------------------------------------------------------- close ---
    def _hide(self):
        self.withdraw()                   # the app keeps running in the
        self.monitor.events.put(("preview", 0))   # tray; the lease dies


def run(cfg, monitor, ui_events):
    window = SettingsWindow(cfg, monitor, ui_events)
    window.mainloop()
    return window
