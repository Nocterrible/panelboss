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
                     "changing the model needs a restart",
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
        if bool(self.power_switch.get()) != real:
            self.power_switch.set(real)          # set() is click-free
            self.cfg["power"]["assistant_task"] = real
            self.monitor.events.put(("power_assistant", real))

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
            if not ok:
                self.power_msg = msg
                self.power_msg_ts = time.time()
                self.after(0, lambda: self.power_switch.set(not want))
            else:
                # the waiting line must die on success too, or the user
                # never learns the truth until its expiry timer ends it
                self.power_msg = ""
                self.power_msg_ts = 0.0
                self.after(0, self._update_blockers)
        threading.Thread(target=work, daemon=True).start()

    def _build_general(self):
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

    # ------------------------------------------------- camera + preview ---
    def _build_right(self):
        card = ctk.CTkFrame(self._body, **self.skin.panel_style())
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
        self.power_switch = ctk.CTkSwitch(
            card, text="power assistant: wait out other display locks",
            font=self.skin.font(12), command=self._power_assistant_changed,
            progress_color=self.skin.accent,
            border_color=self.skin.border)
        self.power_switch.pack(anchor="w", padx=14)
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
            self.after(0, lambda: self._assistant_truth(real))
        threading.Thread(target=truth, daemon=True).start()
        self.blockers_label = ctk.CTkLabel(
            card, text="", font=self.skin.font(10), justify="left",
            **self.skin.text_style("sub"))
        self.blockers_label.pack(anchor="w", padx=14, pady=(2, 4))
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
        self.preview_info.pack(anchor="w", padx=14, pady=(0, 10))

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
                self.after(0, self._apply_cameras, found)
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
    def _tick_ui(self):
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

    def _update_blockers(self):
        b = getattr(self.monitor, "blockers", None) or {}
        lines = []
        if self.power_msg and time.time() - self.power_msg_ts < 25:
            lines.append(self.power_msg)
        err = b.get("error")
        held = b.get("display") or []
        others = b.get("other") or []
        if err:
            lines.append(err)
        elif held:
            lines.append("holding the display: "
                         + "; ".join(x[:48] for x in held[:3]))
        if others:
            lines.append("sleep only (fine): "
                         + "; ".join(x[:48] for x in others[:3]))
        if not bool(self.power_switch.get()) and not (err or held):
            lines.append("off: powercfg needs admin, so nothing is "
                         "checked and polling never pauses; tick to "
                         "register a scheduled task (one admin confirm)")
        if not (err or held or others) and not lines:
            lines.append("nothing pins the display; the camera guards it")
        # tkinter wraps by pixels but breaks words anywhere: pre-wrap at
        # word boundaries and hand the label clean lines
        wrapped = []
        for line in lines:
            wrapped.extend(textwrap.wrap(line, width=68) or [""])
        self.blockers_label.configure(text="\n".join(wrapped))

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
