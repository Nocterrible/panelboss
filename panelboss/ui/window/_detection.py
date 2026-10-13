"""Detection tab: person and motion rows, mode picker,
timers, and their change callbacks.
"""

from __future__ import annotations

import customtkinter as ctk

from .. import theme
from ... import config
from ._constants import TIMER_SPECS, DEVICE_KEYS, DEVICE_BY_LABEL, PERSON_ROWS, MOTION_ROWS, TIPS
from ._widgets import SkewCombo


class _DetectionMixin:
    # ---------------------------------------------------------- detection --
    def _build_detection(self, page):
        # THE consent header (redesign law 2): one big switch owns the
        # whole tab; OFF on a virgin boot, and the gray-out is the
        # body - the tab stays legible, every control behind the
        # switch loses its state. Built first so the band (and the
        # camera card beside it) lands under it in the pack order.
        self.consent_switch = ctk.CTkSwitch(
            page, text="enable camera detection",
            font=self.skin.font(14, "bold"),
            command=self._consent_flipped, **self.skin.switch_style())
        self.consent_switch.pack(anchor="w", padx=theme.S_SECTION,
                                 pady=(theme.S_ROW, 0))
        self.consent_note = ctk.CTkLabel(page, text="",
                                         font=self.skin.font(11),
                                         wraplength=640, justify="left",
                                         anchor="w",
                                         **self.skin.text_style("sub"))
        self.consent_note.pack(anchor="w", padx=theme.S_SECTION,
                               pady=(theme.S_FIELD, theme.S_ROW))
        # ONE band anchored top-left: the camera card mounts beside
        # the settings column, never against the window edge -
        # stretching the window opens spare room to the RIGHT of the
        # pair, not in a canyon between its halves
        band = ctk.CTkFrame(page, fg_color="transparent")
        band.pack(anchor="nw")
        self._consent_band = band                # the gray-out's scope
        left = ctk.CTkFrame(band, width=380, fg_color="transparent")
        left.pack(side="left", fill="y")
        self._build_detect_card(left)
        self._build_timers(left)
        self._build_camera_card(band)
        self._sync_consent_switch()              # paint from cfg truth


    def _consent_flipped(self):
        """OFF is a door anyone may shut; ON is only real through the
        setup screen (owner design: toggling ON ASKS, and a "No"
        costs nothing but the flip back - an enabled app with a blind
        picker is exactly the lockout the redesign blew away)."""
        want = bool(self.consent_switch.get())
        if want == bool(self.cfg["camera"].get("enabled")):
            return                               # repaint echo, no-op
        if not want:
            self.monitor.events.put(("camera_enabled", False))
            return                               # no dialog for a
                                                 # close: the drain
                                                 # happens in state
        ans = None
        try:
            ans = ctk.CTkMessagebox(
                "camera detection",
                "Would you like to go through first-time setup?",
                choices=["Yes", "No"], icon="question", parent=self)
        except Exception:
            ans = "Yes"                          # headless harnesses
                                                 # and old ctk builds:
                                                 # the setup is the
                                                 # safe answer
        if ans == "Yes":
            self._rescan_setup()                 # THE one path: the
                                                 # dialog's OK posts
                                                 # camera_enabled and
                                                 # the resync paints
                                                 # this tab
            return
        self._sync_consent_switch()              # "No": the switch
                                                 # flips back, the
                                                 # truth never moved


    def _sync_consent_switch(self):
        """Repaint the header and the gray-out from cfg truth - the
        state loop owns the key, the UI reads the snapshot (the same
        resync the identity writes ride)."""
        on = bool(self.cfg["camera"].get("enabled"))
        try:
            if on:
                self.consent_switch.select()
            else:
                self.consent_switch.deselect()
        except Exception:
            pass
        self.consent_note.configure(
            text="" if on else
            "Detection is off - cameras will not be opened until you "
            "enable it.")
        state = "normal" if on else "disabled"
        self._gate_widgets(self._consent_band, state)

    def _gate_widgets(self, widget, state):
        """Walk the band's tree and give every widget that HAS a
        state one (CTk and ttk both do; plain tk mostly does); the
        rest - labels, frames, the ones that never took input
        anyway - carry no state and must not crash the walk. The
        switch above the band is deliberately outside the scope:
        the door is never locked."""
        try:
            widget.configure(state=state)
        except Exception:
            pass
        for child in widget.winfo_children():
            self._gate_widgets(child, state)


    def _build_detect_card(self, left):
        box = self._card(left, "Detection")
        # the mode row leads the card: motion mode has no model at all,
        # so the model's device and thresholds below it are mere trivia
        row = self._row(box, "mode", TIPS["mode"], hint_chars=42)
        self.mode_button = ctk.CTkSegmentedButton(
            row, values=["person (AI)", "motion (no AI)"], height=26,
            width=230, command=self._detect_mode_changed,
            **self.skin.segmented_style())
        self.mode_button.set(self._detect_mode_label(self.cfg))
        self.mode_button.grid(row=0, column=1, sticky="e")
        rows = [("mode", row)]

        row = self._row(box, "device", TIPS["device"], hint_chars=42)
        menu = SkewCombo(row, values=[label for _, label in
                                              DEVICE_KEYS], width=160,
                                 command=self._device_changed,
                                 **self.skin.menu_style())
        menu.grid(row=0, column=1, sticky="e")
        menu.set(dict(DEVICE_KEYS).get(
            self.cfg["inference"]["device"],
            dict(DEVICE_KEYS)["auto"]))
        rows.append(("device", row))

        from ... import inference
        self.gpu_ids = inference.cuda_gpus()
        if not self.gpu_ids:
            self.gpu_ids = [(n, "") for n in range(4)]
        labels = ["%s %s" % (gid, name[:40]) for gid, name in self.gpu_ids]
        row = self._row(box, "cuda gpu id", TIPS["gpu"], hint_chars=42)
        gpu_menu = SkewCombo(
            row, values=labels, width=300, command=self._gpu_changed,
            **self.skin.menu_style())
        gpu_menu.grid(row=0, column=1, sticky="e")
        for gid, name in self.gpu_ids:
            if gid == self.cfg["inference"]["device_id"]:
                self._set_menu(gpu_menu, "%s %s" % (gid, name[:40]))
                break
        rows.append(("cuda gpu id", row))

        row = self._row(box, "confidence", TIPS["confidence"], hint_chars=42)
        self.conf_label = ctk.CTkLabel(row, font=self.skin.font(12),
                                       **self.skin.text_style("sub"))
        self.conf_label.grid(row=0, column=2, sticky="e", padx=(theme.S_FIELD, 0))
        slider = ctk.CTkSlider(row, from_=0.1, to=0.9,
                               number_of_steps=80, width=180,
                               command=self._confidence_changed,
                               **self.skin.slider_style())
        slider.set(self.cfg["inference"]["confidence"])
        slider.grid(row=0, column=1, sticky="e")
        self.conf_label.configure(
            text="%.2f" % self.cfg["inference"]["confidence"])
        rows.append(("confidence", row))

        row = self._row(box, "min hits", TIPS["min_hits"], hint_chars=42)
        hits = ctk.CTkSegmentedButton(
            row, values=["1", "2", "3", "4"], height=26, width=170,
            command=self._min_hits_changed, **self.skin.segmented_style())
        hits.set(str(self.cfg["inference"]["min_hits"]))
        hits.grid(row=0, column=1, sticky="e")
        rows.append(("min hits", row))

        # motion's own knobs, hidden in person mode exactly as the
        # model's knobs are hidden here: each mode shows its controls
        row = self._row(box, "frame changes", TIPS["frame changes"], hint_chars=42)
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
        shown.grid(row=0, column=2, sticky="e", padx=(theme.S_FIELD, 0))
        shown.configure(text="%.4f" % self.cfg["detection"]["ratio"])
        self.motion_labels["ratio"] = shown
        rows.append(("frame changes", row))

        row = self._row(box, "pixel delta", TIPS["pixel delta"], hint_chars=42)
        slider = ctk.CTkSlider(row, from_=1, to=128, number_of_steps=127,
                               width=180,
                               command=lambda v, k="diff_level":
                               self._motion_changed(k, v),
                               **self.skin.slider_style())
        slider.set(self.cfg["detection"]["diff_level"])
        slider.grid(row=0, column=1, sticky="e")
        shown = ctk.CTkLabel(row, font=self.skin.font(12),
                             **self.skin.text_style("sub"))
        shown.grid(row=0, column=2, sticky="e", padx=(theme.S_FIELD, 0))
        shown.configure(text="%d" % self.cfg["detection"]["diff_level"])
        self.motion_labels["diff_level"] = shown
        rows.append(("pixel delta", row))

        row = self._row(box, "motion hold", TIPS["motion hold"], hint_chars=42)
        slider = ctk.CTkSlider(row, from_=10, to=600, number_of_steps=59,
                               width=180,
                               command=lambda v, k="hold_sec":
                               self._motion_changed(k, v),
                               **self.skin.slider_style())
        slider.set(self.cfg["detection"]["hold_sec"])
        slider.grid(row=0, column=1, sticky="e")
        shown = ctk.CTkLabel(row, font=self.skin.font(12),
                             **self.skin.text_style("sub"))
        shown.grid(row=0, column=2, sticky="e", padx=(theme.S_FIELD, 0))
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
                widget.pack(fill="x", pady=(0, theme.S_ROW))
        self.detect_note.pack_forget()
        self.detect_note.configure(
            text=("no model: the differencer is rebuilt the moment a "
                  "slider moves; the confidence threshold sets the "
                  "motion ratio in this mode" if mode == "motion" else
                  "device applies immediately; the model file itself "
                  "needs a restart"))
        self.detect_note.pack(anchor="w", pady=(theme.S_FIELD, 0))


    def _build_timers(self, left):
        box = self._card(left, "Timers",
                         "written to config.toml, applied while the "
                         "loop runs")
        self.timer_labels = {}
        for section, key, label, lo, hi, step, tip in TIMER_SPECS:
            row = self._row(box, label, tip, hint_chars=42)
            value_label = ctk.CTkLabel(row, font=self.skin.font(12),
                                       **self.skin.text_style("sub"))
            value_label.grid(row=0, column=2, sticky="e", padx=(theme.S_FIELD, 0))
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
        self.worst_label.pack(anchor="w", pady=(theme.S_FIELD, 0))
        self._update_worst()


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
        # gate MED (misses list) + third-gate ledger 5 (the copy was
        # the wrong transform: conf domain is 0.05..0.95, ratio domain
        # is 0.0005..0.02 - a raw copy could push the motion knob to
        # ~47x its legal top and the screens would sleep on a present
        # user). Linear domain map, same direction (more confidence
        # required == bigger change required); cfg first (a rebuild
        # reads it back), then the hot-write - the exact seam the
        # ("confidence", v) event uses for detector.conf, mirrored for
        # the knob this mode actually gates on.
        if (self.cfg.get("detection") or {}).get("mode") == "motion":
            frac = (min(0.95, max(0.05, float(value))) - 0.05) / 0.9
            ratio = 0.0005 + frac * (0.02 - 0.0005)
            self.cfg["detection"]["ratio"] = ratio
            det = self.monitor.detector
            if hasattr(det, "ratio"):
                det.ratio = ratio
            shown = getattr(self, "motion_labels", {}).get("ratio")
            if shown is not None:
                shown.configure(text="%.4f" % ratio)
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

