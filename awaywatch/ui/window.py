"""The settings window (CTk, main thread - Tk always owns thread zero).

Rules this file lives by:
* it never touches the camera or the display: commands go through the
  state machine's queue, or into the shared config dicts the worker
  reads every tick (cfg["timers"] IS monitor.timers - writing it is
  applying it, no round trip needed)
* the debug view draws from monitor.framebox: the picture next to the
  camera picker is literally the frame the detector judged
* camera enumeration boots every index (this machine's virtual camera
  takes up to 16 s), so it always runs off the UI thread
* three tabs, one scroll page each: what belongs together is
  detected together (detection + timers + camera), what guards the
  desk belongs to the power plan (hold overrides, wake behavior, the
  powercfg assistant), and what only configures the app itself
  (skin, autostart, logs) is meta - it goes in General
* anything that needs a paragraph carries a "?" (ui.helpbtn); the
  rows themselves stay one line short

Skins come from theme.py; nothing here hardcodes a color.
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import textwrap
import threading
import time

import cv2
import customtkinter as ctk
from PIL import Image

from .. import config
from . import theme
from .helpbtn import Tips
from .shield import shield_pil

log = logging.getLogger("ui")

TIMER_SPECS = [          # section, key, label, min, max, step, help
    ("timers", "idle_gate_sec", "idle gate", 0, 180, 5,
     "the camera never runs while typing; this is how long recent "
     "input still counts as typing"),
    ("timers", "absent_confirm_sec", "absence confirm", 10, 300, 5,
     "how long absence must be seen before the screens go dark - "
     "one unseen frame is never trusted"),
    ("timers", "on_poll_sec", "poll while on", 1, 15, 1,
     "how often the camera wakes while the screens are on and "
     "absence is being confirmed"),
    ("timers", "off_poll_sec", "poll while off", 1, 15, 1,
     "how often the camera watches for a return while the screens "
     "are dark (the LED is invisible anyway)"),
    ("timers", "present_recheck_sec", "present recheck", 10, 300, 5,
     "how often a confirmed person is re-checked while they sit there"),
    ("timers", "re_off_grace_sec", "re-off grace", 0, 120, 5,
     "after an unexpected wake this is the camera's chance to find "
     "the person before the screens go dark again"),
    ("recovery", "leave_on_grace_sec", "leave-on grace", 10, 600, 10,
     "with the leave-on wake policy: how long the screens are left "
     "alone for whoever woke them before the app starts guarding "
     "them again"),
]

DEVICE_KEYS = [("auto", "auto"), ("cpu", "CPU"), ("cuda", "CUDA GPU")]
DEVICE_BY_LABEL = dict((label, key) for key, label in DEVICE_KEYS)

TABS = ("detection", "power plan", "general")

PERSON_ROWS = ("device", "cuda gpu id", "confidence", "min hits")
MOTION_ROWS = ("frame changes", "pixel delta", "motion hold")

TIPS = {
    "mode": "person: the ONNX model judges every frame. motion: pure "
            "frame differencing - no ML, nothing learned about faces, "
            "and it drives infrared and depth sensors exactly like a "
            "webcam. Switching rebuilds the detector immediately; the "
            "model's device and thresholds vanish here.",
    "device": "where the model runs. auto lets onnxruntime choose, "
                "CPU always works, CUDA is faster when a card exists. "
                "Applies immediately - the session is rebuilt.",
    "gpu": "which card, for the record, when device is CUDA. Applies "
            "immediately.",
    "confidence": "how sure a detection must be before a frame counts "
                   "as a person. Applied to the next frame; no restart.",
    "min_hits": "consecutive positive frames before the screens are "
                "re-woken. One lucky frame is never believed.",
    "frame changes": "share of the (downscaled) frame that must move "
                      "before a poll counts as motion. Applies "
                      "immediately.",
    "pixel delta": "how much one pixel must shift to count as a change "
                    "- raise it for noisy depth or infrared sensors. "
                    "Applies immediately.",
    "motion hold": "presence lingers this long after the LAST motion: "
                    "reading a page is stillness, not absence. Applies "
                    "immediately.",
    "wake": "the screens came back on their own (a mouse jiggle, a "
             "wake word). re-off darkens them again after the re-off "
             "grace unless a person is confirmed; leave-on hands the "
             "desk over for its grace period instead. Applies "
             "immediately.",
    "fullscreen": "exclusive-fullscreen games swallow the power-off "
                   "broadcast - the app keeps its hands off while a "
                   "game owns the display.",
    "reoff": "after two unexpected wakes in a row the app stops "
               "believing its own camera and leaves the screens lit "
               "until a person shows up or this is resumed here.",
    "hold_display": "Windows is not allowed to turn the screens off "
                     "while the app watches a lit desk. Nothing in the "
                     "power plan changes - the timer is only held back, "
                     "and only while this app runs: pausing, snoozing "
                     "or quitting hands it back.",
    "hold_sleep": "the plan's sleep timer is held back too. While the "
                   "screens are dark this is what keeps the watcher "
                   "alive to notice the return; with it off the box "
                   "sleeps on schedule and the app re-arms when the "
                   "power button is pressed.",
    "camera": "which camera the frames come from. Opening every index "
               "is slow (the virtual camera alone takes 16 s), so the "
               "list fills in after the window opens and rescans on "
               "demand.",
    "cam_on": "camera life while the screens are on: boot per poll "
               "rests the LED, always on streams through the standby "
               "transition.",
    "cam_off": "camera life while the screens are dark: always on is "
                "the measured-reliable choice (a device reopened "
                "INSIDE the standby transition never streams again).",
    "live": "holds the camera open for this window at ~5 fps so the "
            "picture shows exactly what the detector judged. The hold "
            "is a lease: closing the window releases the device.",
    "assistant": "powercfg /requests needs administrator rights, so a "
                  "scheduled task dumps it silently instead (one "
                  "confirm on tick). While another app holds the "
                  "display - a video wake lock, a presentation - the "
                  "camera stops defending a screen it does not own.",
    "skin": "the palette. The layout and all behavior are identical.",
    "startup": "the per-user Run key - exactly the entry Task "
                "Manager's startup tab lists. No admin, and the app "
                "verifies it by reading the registry back.",
    "logs": "every decision and the reason, in %APPDATA%\\ICU-"
             "PresenceDetector\\logs.",
    "update": "runs update.bat: pulls the newest copy and refreshes "
               "the dependencies. the app quits first - its own files "
               "are the ones being replaced - and the script reopens "
               "it when it finishes. if it stays closed, the update "
               "window says why; run.bat starts it by hand.",
}


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
        self._tab = TABS[0]
        ctk.set_appearance_mode(self.skin.mode)
        self.configure(fg_color=self.skin.bg)
        self.build_all()
        self._scan_cameras()
        self.after(90, self._tick_ui)

    # ------------------------------------------------------------- build --
    def build_all(self):
        self._top = ctk.CTkFrame(self, fg_color="transparent")
        self._top.pack(fill="x", padx=14, pady=(12, 6))
        self._tabs_bar = ctk.CTkFrame(self, fg_color="transparent")
        self._tabs_bar.pack(fill="x", padx=14)
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.pack(fill="both", expand=True, padx=14, pady=(6, 12))
        self.tips = Tips(self.skin, self)
        self._build_top()
        self.tab_buttons = {}
        for key in TABS:
            b = ctk.CTkButton(self._tabs_bar, text=key, width=120,
                              height=30,
                              command=lambda k=key: self._show_tab(k))
            b.pack(side="left", padx=(0, 6), pady=(0, 8))
            self.tab_buttons[key] = b
        self.pages = {}
        for key in TABS:
            self.pages[key] = ctk.CTkScrollableFrame(
                self._body, fg_color="transparent",
                scrollbar_button_color=self.skin.button,
                scrollbar_fg_color=self.skin.panel)
        self._build_detection(self.pages["detection"])
        self._build_power(self.pages["power plan"])
        self._build_general(self.pages["general"])
        self._show_tab(self._tab)

    def _show_tab(self, key):
        self.tips.kill()                 # a tooltip anchored to a row
        self._tab = key                  # would float over the new page
        for page in self.pages.values():
            page.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        for k, b in self.tab_buttons.items():
            b.configure(**(self.skin.primary() if k == key
                          else self.skin.secondary()))

    def rebuild_for_skin(self):
        self.tips.kill()
        for widget in (self._top, self._tabs_bar, self._body):
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
            # wraplength or the label clips: the sub lines are longer
            # than any column, and clipped text reads like a bug in the
            # app, not in the label
            ctk.CTkLabel(frame, text=sub, font=self.skin.font(11),
                         wraplength=480, justify="left", anchor="w",
                         **self.skin.text_style("sub")).pack(
                anchor="w", padx=14)
        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=(6, 12))
        return inner

    def _row(self, parent, label, tip=""):
        """One settings row: label left, widget right. Widgets are
        created ON THE ROW so grid only ever manages children of the
        row, pack only ever manages children of the card. The label
        cell hosts the "?" beside the text."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=2)
        row.grid_columnconfigure(0, weight=1)
        cell = ctk.CTkFrame(row, fg_color="transparent")
        cell.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(cell, text=label, font=self.skin.font(12),
                     **self.skin.text_style()).pack(side="left")
        if tip:
            self.tips.button(cell, tip).pack(side="left", padx=(6, 0))
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

    # ---------------------------------------------------------- detection --
    def _build_detection(self, page):
        left = ctk.CTkFrame(page, width=380, fg_color="transparent")
        left.pack(side="left", fill="y")
        self._build_detect_card(left)
        self._build_timers(left)
        self._build_camera_card(page)

    def _build_detect_card(self, left):
        box = self._card(left, "Detection")
        # the mode row leads the card: motion mode has no model at all,
        # so the model's device and thresholds below it are mere trivia
        row = self._row(box, "mode", TIPS["mode"])
        self.mode_button = ctk.CTkSegmentedButton(
            row, values=["person (AI)", "motion (no AI)"], height=26,
            width=230, command=self._detect_mode_changed,
            **self.skin.segmented_style())
        self.mode_button.set(self._detect_mode_label(self.cfg))
        self.mode_button.grid(row=0, column=1, sticky="e")
        rows = [("mode", row)]

        row = self._row(box, "device", TIPS["device"])
        menu = ctk.CTkOptionMenu(row, values=[label for _, label in
                                              DEVICE_KEYS], width=160,
                                 command=self._device_changed,
                                 **self.skin.menu_style())
        menu.grid(row=0, column=1, sticky="e")
        menu.set(dict(DEVICE_KEYS)[self.cfg["inference"]["device"]])
        rows.append(("device", row))

        from .. import inference
        self.gpu_ids = inference.cuda_gpus()
        if not self.gpu_ids:
            self.gpu_ids = [(n, "") for n in range(4)]
        labels = ["%s %s" % (gid, name[:32]) for gid, name in self.gpu_ids]
        row = self._row(box, "cuda gpu id", TIPS["gpu"])
        gpu_menu = ctk.CTkOptionMenu(
            row, values=labels, width=200, command=self._gpu_changed,
            **self.skin.menu_style())
        gpu_menu.grid(row=0, column=1, sticky="e")
        for gid, name in self.gpu_ids:
            if gid == self.cfg["inference"]["device_id"]:
                self._set_menu(gpu_menu, "%s %s" % (gid, name[:32]))
                break
        rows.append(("cuda gpu id", row))

        row = self._row(box, "confidence", TIPS["confidence"])
        self.conf_label = ctk.CTkLabel(row, font=self.skin.font(12),
                                       **self.skin.text_style("sub"))
        self.conf_label.grid(row=0, column=2, sticky="e", padx=(6, 0))
        slider = ctk.CTkSlider(row, from_=0.1, to=0.9,
                               number_of_steps=80, width=180,
                               command=self._confidence_changed,
                               **self.skin.slider_style())
        slider.set(self.cfg["inference"]["confidence"])
        slider.grid(row=0, column=1, sticky="e")
        self.conf_label.configure(
            text="%.2f" % self.cfg["inference"]["confidence"])
        rows.append(("confidence", row))

        row = self._row(box, "min hits", TIPS["min_hits"])
        hits = ctk.CTkSegmentedButton(
            row, values=["1", "2", "3", "4"], height=26, width=170,
            command=self._min_hits_changed, **self.skin.segmented_style())
        hits.set(str(self.cfg["inference"]["min_hits"]))
        hits.grid(row=0, column=1, sticky="e")
        rows.append(("min hits", row))

        # motion's own knobs, hidden in person mode exactly as the
        # model's knobs are hidden here: each mode shows its controls
        row = self._row(box, "frame changes", TIPS["frame changes"])
        self.motion_labels = {}
        slider = ctk.CTkSlider(row, from_=0.0005, to=0.02,
                               number_of_steps=39, width=180,
                               command=lambda v, k="ratio":
                               self._motion_changed(k, v),
                               **self.skin.slider_style())
        slider.set(self.cfg["detection"]["ratio"])
        slider.grid(row=0, column=1, sticky="e")
        shown = ctk.CTkLabel(row, font=self.skin.font(12),
                             **self.skin.text_style("sub"))
        shown.grid(row=0, column=2, sticky="e", padx=(6, 0))
        shown.configure(text="%.4f" % self.cfg["detection"]["ratio"])
        self.motion_labels["ratio"] = shown
        rows.append(("frame changes", row))

        row = self._row(box, "pixel delta", TIPS["pixel delta"])
        slider = ctk.CTkSlider(row, from_=1, to=128, number_of_steps=127,
                               width=180,
                               command=lambda v, k="diff_level":
                               self._motion_changed(k, v),
                               **self.skin.slider_style())
        slider.set(self.cfg["detection"]["diff_level"])
        slider.grid(row=0, column=1, sticky="e")
        shown = ctk.CTkLabel(row, font=self.skin.font(12),
                             **self.skin.text_style("sub"))
        shown.grid(row=0, column=2, sticky="e", padx=(6, 0))
        shown.configure(text="%d" % self.cfg["detection"]["diff_level"])
        self.motion_labels["diff_level"] = shown
        rows.append(("pixel delta", row))

        row = self._row(box, "motion hold", TIPS["motion hold"])
        slider = ctk.CTkSlider(row, from_=10, to=600, number_of_steps=59,
                               width=180,
                               command=lambda v, k="hold_sec":
                               self._motion_changed(k, v),
                               **self.skin.slider_style())
        slider.set(self.cfg["detection"]["hold_sec"])
        slider.grid(row=0, column=1, sticky="e")
        shown = ctk.CTkLabel(row, font=self.skin.font(12),
                             **self.skin.text_style("sub"))
        shown.grid(row=0, column=2, sticky="e", padx=(6, 0))
        shown.configure(text="%ss" % self.cfg["detection"]["hold_sec"])
        self.motion_labels["hold_sec"] = shown
        rows.append(("motion hold", row))

        self._det_rows = rows               # build order is display order
        self.detect_note = ctk.CTkLabel(box, font=self.skin.font(10),
                                       wraplength=350, justify="left",
                                       anchor="w",
                                       **self.skin.text_style("sub"))
        self._show_mode_rows()

    def _show_mode_rows(self):
        """One truth: the model's knobs and the differencer's knobs
        never share the screen; whichever the mode does not use hides
        itself (a slider that changes nothing is a liar)."""
        mode = (self.cfg.get("detection") or {}).get("mode", "person")
        keep = MOTION_ROWS if mode == "motion" else PERSON_ROWS
        for key, widget in self._det_rows:
            widget.pack_forget()
        for key, widget in self._det_rows:
            if key == "mode" or key in keep:
                widget.pack(fill="x", pady=2)
        self.detect_note.pack_forget()
        self.detect_note.configure(
            text=("no model: the differencer is rebuilt the moment a "
                  "slider moves" if mode == "motion" else
                  "device applies immediately; the model file itself "
                  "needs a restart"))
        self.detect_note.pack(anchor="w", pady=(6, 0))

    def _build_timers(self, left):
        box = self._card(left, "Timers",
                         "written to config.toml, applied while the "
                         "loop runs")
        self.timer_labels = {}
        for section, key, label, lo, hi, step, tip in TIMER_SPECS:
            row = self._row(box, label, tip)
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
                                         wraplength=350, justify="left",
                                         anchor="w",
                                         **self.skin.text_style("sub"))
        self.worst_label.pack(anchor="w", pady=(6, 0))
        self._update_worst()

    # ----------------------------------------------------- camera + preview --
    def _build_camera_card(self, page):
        # beside the picker: the window cannot promise the preview
        # height fits, so the page scrolls (unscrollable, the switch
        # was simply born below the clip edge - seen live)
        card = ctk.CTkFrame(page, width=int(self.cfg["ui"]["preview_width"])
                            + 30, **self.skin.panel_style())
        card.pack(side="right", fill="y")
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(anchor="w", padx=14, pady=(10, 0))
        ctk.CTkLabel(head, text="Camera", font=self.skin.font(15, "bold"),
                     **self.skin.text_style()).pack(side="left")
        self.tips.button(head, TIPS["camera"]).pack(side="left",
                                                    padx=(6, 0))
        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.pack(fill="x", padx=14, pady=(6, 2))
        self.camera_menu = ctk.CTkOptionMenu(
            controls, values=["scanning cameras..."], width=300,
            command=self._camera_changed, **self.skin.menu_style())
        self.camera_menu.pack(side="left")
        ctk.CTkButton(controls, text="rescan", width=80,
                      command=self._scan_cameras,
                      **self.skin.secondary()).pack(side="left", padx=6)
        for key, label, tip in (("mode_on", "while screens are on",
                                 TIPS["cam_on"]),
                                ("mode_off", "while screens are off",
                                 TIPS["cam_off"])):
            row = self._row(card, label, tip)
            menu = ctk.CTkOptionMenu(row, values=["boot per poll",
                                                  "always on"], width=150,
                                     command=self._mode_changed(key),
                                     **self.skin.menu_style())
            menu.grid(row=0, column=1, sticky="e")
            menu.set(self._mode_label(self.cfg["camera"][key]))
        row = self._row(card, "live preview", TIPS["live"])
        self.live_switch = ctk.CTkSwitch(row, text="", font=self.skin.font(12),
                                         command=self._live_changed,
                                         progress_color=self.skin.accent,
                                         border_color=self.skin.border)
        self.live_switch.grid(row=0, column=1, sticky="e", padx=(0, 4))
        self.power_msg = ""                      # install/uninstall result
        self.power_msg_ts = 0.0
        self.preview_frame = ctk.CTkFrame(card, fg_color=self.skin.field_bg,
                                          corner_radius=self.skin.radius)
        self.preview_frame.pack(pady=(4, 4), padx=14)
        self.preview_label = ctk.CTkLabel(self.preview_frame,
                                          text="no frames yet - flip on "
                                          "live preview",
                                          font=self.skin.font(12),
                                          **self.skin.text_style("sub"))
        self.preview_label.pack()
        self.preview_info = ctk.CTkLabel(card, text="",
                                         font=self.skin.font(10),
                                         wraplength=400, justify="left",
                                         anchor="w",
                                         **self.skin.text_style("sub"))
        self.preview_info.pack(anchor="w", padx=14, pady=(0, 10))

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
        # joins and leaves with the switch, never lies about data
        self.assistant_box = box
        self.overrides_button = ctk.CTkButton(
            box, text="manage powercfg overrides", width=250,
            command=self._show_overrides, **self.skin.secondary())
        self._assistant_ui(bool(self.cfg["power"]["assistant_task"]))

    # -------------------------------------------------------------- general --
    def _build_general(self, page):
        from .. import startup
        col = ctk.CTkFrame(page, width=460, fg_color="transparent")
        col.pack(side="left", fill="y")
        box = self._card(col, "General")
        row = self._row(box, "skin", TIPS["skin"])
        self.skin_menu = ctk.CTkOptionMenu(
            row, values=[s.label for s in theme.SKINS.values()],
            width=140, command=self._skin_changed,
            **self.skin.menu_style())
        self.skin_menu.grid(row=0, column=1, sticky="e")
        self.skin_menu.set(self.skin.label)
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
                                            progress_color=self.skin.accent,
                                            border_color=self.skin.border)
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

    # ------------------------------------------------------------ changes ---
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

    def _motion_changed(self, key, value):
        value = float(value)
        self.cfg["detection"][key] = (int(value) if key == "diff_level"
                                       else value)
        fmt = {"ratio": "%.4f", "diff_level": "%d", "hold_sec": "%.0f s"}
        self.motion_labels[key].configure(text=fmt[key] % value)
        # the differencer reads its numbers once, at build; refiring
        # the mode event rebuilds it around whatever the sliders hold
        # now (no model to load in this mode, so it stays cheap)
        self.monitor.events.put(("detection_mode", "motion"))
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
        # the tray and the monitor read THIS dict; the event rebuilds
        # the detector through the factory (motion: no onnx touched)
        self.cfg["detection"]["mode"] = mode
        self.monitor.events.put(("detection_mode", mode))
        self._show_mode_rows()
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

    def _hold_changed(self):
        # cfg["power"] IS monitor.power_cfg, and the loop re-asserts
        # the execution state every tick: both switches are live within
        # 0.2 s, each on its own
        self.cfg["power"]["hold_display"] = bool(
            self.hold_display_switch.get())
        self.cfg["power"]["hold_sleep"] = bool(
            self.hold_sleep_switch.get())
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

    def _update_now(self):
        """The update replaces the very files THIS app runs from, so
        the courtesies are in order: hand the job (plus the relaunch
        promise) to cmd, quit, let the script work on quiet files.
        cmd.exe must be the one to run the .bat - CreateProcess
        cannot exec a batch file directly; the app has no console of
        its own, so the script's console opens fresh, visible, and
        outlives us (it must, it carries the relaunch)."""
        script = self.update_script()
        if not script:
            return
        try:
            subprocess.Popen(["cmd.exe", "/c", script, "relaunch"],
                             cwd=os.path.dirname(script))
        except Exception:
            log.exception("update refused to start; the app stays up")
            return
        self.monitor.events.put(("quit", True))

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

    # -------------------------------------------------------------- startup --
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
            return                                      # itself
        self._startup_sync(stored)

    # --------------------------------------------------------------- cameras --
    def _scan_cameras(self):
        """Opening every index is slow (the virtual camera alone takes
        up to 16 s), so enumerate on a helper thread and hand the
        answer back through after()."""
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

    # ----------------------------------------------------------------- tick --
    def destroy(self):
        """destroy() tears children down first while Tk still processes
        the queue - a pending tick then reschedules itself on the
        half-dead interpreter forever (measured: an endless "ui tick
        failed" loop whose mainloop never returned). Flag the dying
        state and the chain just quits."""
        self._dying = True
        try:
            self.tips.kill()
        except Exception:
            pass
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
            self._show_mode_rows()               # and the rows follow suit

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
            text="%dx%d · %d box%s · the exact frame the detector judged"
            % (img.shape[1], img.shape[0], len(boxes),
               "" if len(boxes) == 1 else "es"))

    # ---------------------------------------------------------------- close --
    def _hide(self):
        self.withdraw()                   # the app keeps running in the
        self.tips.kill()                  # tray; the lease dies
        self.monitor.events.put(("preview", 0))


def run(cfg, monitor, ui_events):
    window = SettingsWindow(cfg, monitor, ui_events)
    window.mainloop()
    return window
