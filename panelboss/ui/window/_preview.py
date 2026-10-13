"""Camera card and its preview panel: the framebox debug
view is the exact frame the detector judged.
"""

from __future__ import annotations

import concurrent.futures as cf
import logging
import threading

import cv2
import customtkinter as ctk
from PIL import Image

from .. import theme
from ._camedit import ADD_LABEL, duty_roster
from ._camid import diag_suffix, display_names, hidden_indices, open_identify
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
        head_lbl = ctk.CTkLabel(head, text="Camera",
                                font=self.skin.font(15, "bold"),
                                **self.skin.text_style())
        head_lbl.pack(side="left")
        # the camera card is a preview_width+30 (~350 px) column; the
        # paragraph that used to ride the inline hint line now pops on
        # the heading's hover (UI-1c reversal - bubbles back)
        head_lbl.bind("<Enter>",
                      lambda e=None: self.tips._schedule(TIPS["camera"],
                                                         head_lbl),
                      add="+")
        head_lbl.bind("<Leave>", lambda e=None: self.tips._hide_soon(),
                      add="+")
        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.pack(fill="x", padx=theme.S_SECTION,
                      pady=(theme.S_FIELD, 0))
        self.camera_menu = SkewCombo(
            controls, values=["scanning cameras..."], width=300,
            command=self._camera_changed, **self.skin.menu_style())
        self.camera_menu.pack(side="left")
        ctk.CTkButton(controls, text="rescan", width=80,
                      command=lambda: self._scan_cameras(force=True),
                      # the rescan BUTTON forces the diagnostic sweep
                      # (owner law: rescan performs the same check
                      # manually - the automatic triggers are the
                      # record's, the button's is the human's); the
                      # bare boot/wizard call sites keep force=False
                      **self.skin.secondary()).pack(
            side="left", padx=theme.S_FIELD)
        ctk.CTkButton(controls, text="identify...", width=80,
                      command=lambda: open_identify(self),
                      **self.skin.secondary()).pack(side="left")
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
        if shown == ADD_LABEL:
            return                        # the widget's face, not a wish
        if shown == self.IR_INSTALL:
            self._apply_cameras(self._cams)   # undo the menu choice -
            self._dep_prompt(switch=True)     # picking the invitation
            return                            # is not picking a camera
        for entry in (self._cams or []):
            if shown.startswith("index %s " % entry[0]):
                # picking ADDS to duty beside the current roster -
                # it never replaces (owner): joining cameras should
                # not send the veterans home, and the engine rotates
                # the whole list (one vote per poll, multi_cam_test)
                roster = duty_roster(self.cfg["camera"])
                if entry[0] not in roster:
                    roster.append(entry[0])
                self.cfg["camera"]["index"] = roster
                self.monitor.events.put(("camera", list(roster)))
                self._apply_cameras(self._cams)   # row + picker rebuild
                self._save()
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
    def _diag_needed(self, found):
        """Pure read of the diagnostic record: the automatic sweep runs
        when NO record exists yet (first launch) or when the scanned
        index set differs from the record's. No clock condition on
        purpose: a dark-room verdict is refreshed by TOUCHING a camera,
        which reindexes the door caches and lands a different set on
        the next scan - the event that makes a re-measure meaningful,
        not a timer deciding for the owner. Worker-safe: the cfg dict
        is shared state under the GIL, and a torn read here only
        re-sweeps (or skips) once, never corrupts the record (state
        owns that write)."""
        cfg = self.cfg["camera"].get("diag") or {}
        idx = sorted(e[0] for e in found)
        return (not cfg) or sorted(cfg.get("indices") or []) != idx

    def _scan_probe(self, found, force=False):
        """The worker's sweep decision, split out so the offline suite
        can drive the OR without threads: force (the rescan button -
        the owner's deliberate re-measure verb) sweeps whatever the
        record says; the automatic paths (boot, wizard fill) answer to
        _diag_needed's record-vs-set rule alone."""
        return bool(force) or self._diag_needed(found)

    def _scan_cameras(self, force=False):
        """Opening every index is slow (the virtual camera alone takes
        up to 16 s), so enumerate on a helper thread and hand the
        answer back through after(). When the sweep is due (the record
        rule, or a forced rescan) the SAME worker probes the openable
        indexes before reporting, so the list and the verdict land on
        the window together - behind the veil. The veil's lifetime is
        the sweep's LIVENESS plus a 35 s dead-man margin (owner
        amendment 4): every probe beats from both ends of its attempt,
        the re-dress renews the lease, and no fixed budget enters
        anywhere - the stopwatch is only the engine's own wedged-open
        deadline, the silence proof."""
        def worker():
            from ... import camera
            try:
                devs = camera.camera_devices()
                self._devs = devs                # identities ride the
                # same scan report. A name attaches to an OpenCV index
                # ONLY when it is unique across the whole PnP list:
                # camera_names() concedes the PnP enumeration order
                # need not match the OpenCV index order, so a
                # positional attach on a repeated name can only be a
                # guess (gate finding 8: the positional-label lie) - a
                # confidently wrong label hides the wrong menu line.
                # An empty name drops the same way: it must not shift
                # every later label through the positional mapping
                # (gate finding 2). The wizard is the disambiguator
                # for that case, by preview.
                names = [d["name"].strip() for d in devs]
                counts = {n: names.count(n) for n in names if n}
                found = [(index, opened, width,
                          names[index]
                          if index < len(names)
                          and counts.get(names[index], 0) == 1 else "")
                         for index, opened, width
                         in camera.enumerate_cameras() if opened]
            except Exception:
                log.exception("camera scan failed")
                found = []
            # the diagnostic sweep (feature law 1): give every OPEN
            # index 15 s to deliver ANY frame - black counts, it IS an
            # image; no frame at all is "no image". Camera.read's own
            # contract (camera.py def read, ~line 571): the deadline
            # loop samples until the timeout, and screen=0 means ANY
            # frame wins the screening. The veil is the worker's own
            # first post: the page wears it for the sweep's duration,
            # progress re-dressed in place, and the report below is
            # what lifts it (_diag_veiled is the handoff flag).
            if self._scan_probe(found, force):
                idxs = [e[0] for e in found]

                def one(idx):
                    # the probe BEGINS: the veil's first heartbeat of
                    # this attempt (owner amendment 4, both ends of
                    # every probe): posted from the worker thread -
                    # the standing marshaling law, queue in, widget
                    # touch only in the drain - so a probe that then
                    # waits behind the serialized door is a LOUD
                    # silence: the veil knows the sweep lives
                    self.ui_events.put((
                        "cameras_veil",
                        "testing cameras, please wait (probing %s)" % idx))
                    # the probe for ONE index: opens at the configured
                    # size (the duty size, not a smaller lie), waits
                    # 15 s for any frame, releases in every ending
                    try:
                        cam = camera.Camera(
                            index=idx, warmup=2,
                            width=int(self.cfg["camera"].get(
                                "width", 1280)),
                            height=int(self.cfg["camera"].get(
                                "height", 720)))
                    except Exception:
                        return False       # no handle: no image
                    try:
                        return cam.read(timeout=15, screen=0) is not None
                    except Exception:
                        return False       # the stream confessed
                    finally:
                        cam.release()
                try:
                    self.ui_events.put(("cameras_veil",
                                        "testing cameras, please wait"))
                    noimg = []
                    done = 0
                    lock = threading.Lock()    # the counter is worker-
                    # thread-only today (one consumer, the as_completed
                    # loop); the lock names that invariant rather than
                    # trusting it, so a second consumer cannot arrive
                    # silently
                    #
                    # The opens still SERIALIZE on the engine's own
                    # _open_lock (camera.py's device-tree law: the
                    # NVIDIA driver dies on concurrent opens, measured
                    # - the deadline door is _open_timed's own answer).
                    # What the threads OVERLAP is the 15 s first-frame
                    # budgets, which touch no shared driver state once
                    # the cap is open. Worst case is therefore
                    # sum(short opens) + max(15 s), not 6x15 s. The
                    # veil rides the same law (amendment 4): a slow
                    # auto-door holding the open for its own 30 s
                    # deadline sits inside ONE beat's silence - the
                    # probe announced itself before waiting - and the
                    # 35 s dead-man only fires on a thread that has
                    # stopped talking at all.
                    with cf.ThreadPoolExecutor(
                            max_workers=min(8,
                                            max(1, len(idxs)))) as ex:
                        futs = {ex.submit(one, i): i for i in idxs}
                        for fut in cf.as_completed(futs):
                            if not fut.result():
                                noimg.append(futs[fut])
                            with lock:
                                done += 1
                                n = done
                            try:      # progress re-dresses the ONE
                                self.ui_events.put((   # veil in place
                                    "cameras_veil",
                                    "testing cameras, please wait "
                                    "(%d of %d done)" % (n, len(idxs))))
                            except Exception:
                                pass  # window closed: the sweep loses
                                      # its audience, not the verdict
                    noimg.sort()       # the record reads sorted: the
                    # toml stays stable when a reindex moves nothing
                    self.ui_events.put(("camera_diag",
                                        {"indices": [e[0] for e in found],
                                         "noimg": noimg}))
                except Exception:
                    log.exception("camera diagnostic sweep failed")
            try:
                self.ui_events.put(("cameras", found))
            except Exception:
                pass                    # the window closed mid-scan
        threading.Thread(target=worker, daemon=True, name="ui-scan").start()


    def _apply_cameras(self, found):
        from ... import camera
        if found is None:
            # the identity-write flag (audit LOW: "(hidden)" badges and
            # the picker stale after a wizard save - the loop owns the
            # toml and nothing re-fired this after its write). NONE =
            # no fresh scan rode the event: re-apply the CACHED report
            # against the cfg that just moved, the same re-apply idiom
            # the row/remove paths use. No cache yet (a resync beating
            # the boot scan): nothing to re-apply, the first report
            # paints it anyway.
            if self._cams is None:
                return
            found = self._cams
        self._cams = found
        # the picker is an ADD widget: on-duty cameras own policy rows
        # below, not menu lines (the old listing was the redundancy
        # the owner named); rostered entries vanish from the menu
        roster = set(duty_roster(self.cfg["camera"]))
        hidden = self.cfg["camera"].get("hidden") or []
        if hidden and getattr(self, "_devs", None) is None:
            try:                                 # one lazy fetch: the
                self._devs = camera.camera_devices()   # mapping needs
            except Exception:                    # the PnP list
                self._devs = []
        hid = hidden_indices(getattr(self, "_devs", None) or [],
                             found, hidden,
                             self.cfg["camera"].get("bindings") or {})
        labels = []
        # the truth about an index's name (display_names): user label
        # via bind or honest join FIRST, the scan's positional guess as
        # fallback, nothing rather than a lie
        name_of = display_names(getattr(self, "_devs", None) or [], found,
                                self.cfg["camera"])
        diag = self.cfg["camera"].get("diag") or {}
        diag_covers = bool(diag) and \
            sorted(diag.get("indices") or []) == sorted(e[0] for e in found)
        for index, opened, width, name in found:
            if (index in roster and index >= 0) or index in hid:
                continue
            label = "index %s (%s px)" % (index, int(width))
            nm = name_of.get(index) or name
            if nm:
                label += " %s" % nm
            # the sweep's verdict rides the picker line, but ONLY
            # while the record covers this exact scan: a verdict of an
            # older index set says nothing about a camera it never
            # measured (the sweep is keyed by its set on both ends)
            label += diag_suffix(self.cfg["camera"], index) \
                if diag_covers else ""
            labels.append(label)
        if not found:
            labels = ["no camera opens"]
        labels.insert(0, ADD_LABEL)
        # the hello IR entry rides on the end either way: the real
        # groups when the whircam bridge lives, an invitation when it
        # does not - the feature must be reachable without ever
        # opening config.toml
        if camera.optional_present("whircam"):
            for name in camera.hello_ir_names():
                if ("ir:" + name) in (hidden if isinstance(
                        hidden, (list, tuple, set)) else []):
                    continue          # hidden from the wizard's IR
                lbl = (self.cfg["camera"].get("labels") or {}).get(
                    "ir:" + name) or name          # row like any other
                labels.append("index %s hello IR %s"
                              % (camera.HELLO_IR, lbl))
        else:
            labels.append(self.IR_INSTALL)
        self.camera_menu.configure(values=labels)
        # an ADD widget wears its verb: the face is the invitation,
        # never a selection echo (duty is visible as policy rows
        # below); the ONE exception is hello IR, which has no row
        # machinery and must keep showing as the chosen eye
        roster_list = duty_roster(self.cfg["camera"])
        current = roster_list[0] if roster_list else -1
        self._set_menu(self.camera_menu, ADD_LABEL)
        if current == camera.HELLO_IR:
            want = self.IR_INSTALL if not camera.optional_present(
                "whircam") else None
            for label in labels:
                if label == want or label.startswith(
                        "index %s" % camera.HELLO_IR):
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


    def _preview_placeholder(self):
        """The main pane's half of the reset law (the owner's: a list
        change must NEVER leave a stale frame from the previous
        device reading as live). The CTk trap is general, not wizard-
        local: a CTkLabel preview resets to a configured PLACEHOLDER
        image, never back to image=None (the Oct 13 freeze's law) -
        one image per window, cheap, built on the first reset."""
        img = Image.new("RGB",
                        (int(self.cfg["ui"]["preview_width"]), 90),
                        (24, 26, 33))
        self._ph_img = self._ph_img or ctk.CTkImage(
            light_image=img, dark_image=img, size=(img.size[0], 90))
        self.preview_label.configure(image=self._ph_img, text="")
        self.preview_info.configure(
            text="camera list changed - the placeholder replaces the "
                 "previous device's frame")


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

