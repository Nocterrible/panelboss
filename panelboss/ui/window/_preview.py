"""Camera card and its preview panel: the framebox debug
view is the exact frame the detector judged.
"""

from __future__ import annotations

import logging
import threading

import cv2
import customtkinter as ctk
from PIL import Image

from .. import theme
from ... import config
from ._constants import TIPS
from ._widgets import SkewCombo

log = logging.getLogger("ui")


class _CameraMixin:
    # ----------------------------------------------------- camera + preview --
    def _build_camera_card(self, band):
        # beside the settings column (see _build_detection): the
        # window cannot promise the preview height fits, so the page
        # scrolls (unscrollable, the switch was simply born below the
        # clip edge - seen live)
        # the card matches the preview width for column alignment, but
        # NEVER narrower than its own form (320 px zone + section
        # pads): a debug-sized preview_width (the harness config's 140)
        # used to clip every label mid-word - the card bows to the
        # preview, not below its own content
        card = ctk.CTkFrame(band, width=max(
            int(self.cfg["ui"]["preview_width"]) + 30, 360),
            **self.skin.panel_style())
        card.pack(anchor="nw", padx=(theme.S_SECTION, 0))
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(anchor="w", padx=theme.S_SECTION,
                  pady=(theme.S_ROW, 0))
        ctk.CTkLabel(head, text="Camera", font=self.skin.font(15, "bold"),
                     **self.skin.text_style()).pack(side="left")
        # the camera card is a preview_width+30 (~350 px) column; the
        # hint line caps to the zone's 320 px budget (chars, not px -
        # an uncapped hint balloons the card and pack clips the label
        # mid-word, screenshot-verified before the cap)
        self._hint(card, TIPS["camera"], padx=theme.S_SECTION, chars=42)
        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.pack(fill="x", padx=theme.S_SECTION,
                      pady=(theme.S_FIELD, 0))
        self.camera_menu = SkewCombo(
            controls, values=["scanning cameras..."], width=300,
            command=self._camera_changed, **self.skin.menu_style())
        self.camera_menu.pack(side="left")
        ctk.CTkButton(controls, text="rescan", width=80,
                      command=self._scan_cameras,
                      **self.skin.secondary()).pack(
            side="left", padx=theme.S_FIELD)
        # the label zone is a 320 px form, not the card's full width:
        # full width flings labels to one edge and menus to the other
        # and the eye has to cross a canyon to read the pair (the
        # screenshot's complaint); 320 keeps every control's right
        # edge on one line, close enough to its label to belong to it
        zone = ctk.CTkFrame(card, width=320, fg_color="transparent")
        zone.pack(anchor="w", padx=theme.S_SECTION)
        for key, label, tip in (("mode_on", "while screens are on",
                                 TIPS["cam_on"]),
                                ("mode_off", "while screens are off",
                                 TIPS["cam_off"])):
            row = self._row(zone, label, tip, hint_chars=42)
            menu = SkewCombo(row, values=["boot per poll",
                                                  "always on"], width=150,
                                     command=self._mode_changed(key),
                                     **self.skin.menu_style())
            menu.grid(row=0, column=1, sticky="e")
            menu.set(self._mode_label(self.cfg["camera"][key]))
        # the per-camera policy rows ride below the global pair (the
        # pair is the DEFAULT for rows left on follow global); the
        # rows themselves are _camedit's - the size-law seam
        self._build_cam_policy_zone(zone)
        row = self._row(zone, "live preview", TIPS["live"], hint_chars=42)
        self.live_switch = ctk.CTkSwitch(row, text="", font=self.skin.font(12),
                                         command=self._live_changed,
                                         **self.skin.switch_style())
        self.live_switch.grid(row=0, column=1, sticky="e",
                              padx=(0, theme.S_FIELD))
        self.power_msg = ""                      # install/uninstall result
        self.power_msg_ts = 0.0
        self.preview_frame = ctk.CTkFrame(card, fg_color=self.skin.field_bg,
                                          corner_radius=self.skin.radius)
        self.preview_frame.pack(anchor="w",
                                pady=(theme.S_FIELD, theme.S_FIELD),
                                padx=theme.S_SECTION)
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
        self.preview_info.pack(anchor="w", padx=theme.S_SECTION,
                               pady=(0, theme.S_ROW))


    def _mode_changed(self, key):
        def command(label):
            self.cfg["camera"][key] = self._mode_value(label)
            # the global pair IS the fallback tier for every follow-
            # global row: its change moves their dim truth under the
            # engine's own feet, so re-verify all of them now (gate
            # finding 2: a row dimmed via inherited-off must un-dim
            # the moment the global it inherits from turns on)
            self._cam_refresh()
            self._save()
        return command


    def _camera_changed(self, shown):
        from ... import camera
        if shown == self.IR_INSTALL:
            self._apply_cameras(self._cams)   # undo the menu choice -
            self._dep_prompt(switch=True)     # picking the invitation
            return                            # is not picking a camera
        for entry in (self._cams or []):
            if shown.startswith("index %s " % entry[0]):
                self.cfg["camera"]["index"] = entry[0]
                self.monitor.events.put(("camera", entry[0]))
                self._cam_refresh()          # duty labels follow the
                self._save()                 # roster the same instant
                return
        if shown.startswith("index %s" % camera.HELLO_IR):
            # "index -2 hello IR <group>": the bridge lives, the wish
            # is recorded, the state machine swaps the camera
            self.cfg["camera"]["index"] = camera.HELLO_IR
            self.monitor.events.put(("camera", camera.HELLO_IR))
            self._save()


    def _live_changed(self):
        on = bool(self.live_switch.get())
        self.monitor.events.put(("preview", 1.5 if on else 0))


    # --------------------------------------------------------------- cameras --
    def _scan_cameras(self):
        """Opening every index is slow (the virtual camera alone takes
        up to 16 s), so enumerate on a helper thread and hand the
        answer back through after()."""
        def worker():
            from ... import camera
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
        from ... import camera
        self._cams = found
        labels = []
        for index, opened, width, name in found:
            label = "index %s (%s px)" % (index, int(width))
            if name:
                label += " %s" % name
            labels.append(label)
        if not labels:
            labels = ["no camera opens"]
        # the hello IR entry rides on the end either way: the real
        # groups when the whircam bridge lives, an invitation when it
        # does not - the feature must be reachable without ever
        # opening config.toml
        if camera.optional_present("whircam"):
            for name in camera.hello_ir_names():
                labels.append("index %s hello IR %s"
                              % (camera.HELLO_IR, name))
        else:
            labels.append(self.IR_INSTALL)
        self.camera_menu.configure(values=labels)
        # the roster may be a list (multi-camera); the picker is a
        # one-choice widget, so it shows the rotation's first post
        # and picking any single entry collapses the roster onto it
        current = config.normalize_index(self.cfg["camera"]["index"])[0]
        want = self.IR_INSTALL if current == camera.HELLO_IR else None
        for label in labels:
            if label == want or \
                    label.startswith("index %s " % current) or \
                    label == "index %s" % current:
                self._set_menu(self.camera_menu, label)
                break
        # config already points at hello IR but the bridge is missing
        # (a hand-edited config, or a venv rebuilt without -Optional):
        # the camera would only fail into the log - ask instead, once
        if (current == camera.HELLO_IR
                and not camera.optional_present("whircam")
                and not getattr(self, "_dep_asked", False)):
            self._dep_asked = True
            self._dep_prompt(switch=False)
        # the per-camera editor mirrors the SAME scan: rebuild the
        # rows from the tables (never from the outgoing widgets), so a
        # rescan that renames the set cannot strand stale rows
        self._rebuild_cam_rows(found)


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

