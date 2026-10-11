"""Camera handling: the vote path (_poll/_grab), the duty roster's
rotor, stream holds and releases. Formerly state.py lines 510-734."""

import logging

log = logging.getLogger("state")


class _CamsMixin:

    def _poll(self):
        if self.detector is None:
            # the warm-up has not landed yet: abstain like a failed
            # open - no camera touched, no verdict, no presence hits
            return None, 0.0
        frame, opened = self._grab()
        if frame is None:
            if not opened:
                # the open itself failed: no camera looked, so no
                # verdict - an abstain never confirms absence and
                # never resets the presence hits
                return None, 0.0
            return False, 0.0                    # device busy or died
        # two-tier, letterboxed: a clear hit is present, a borderline one
        # counts only if it moved; motion mode has no detect_lively, so
        # it takes the plain detect path
        lively = getattr(self.detector, "detect_lively", None)
        if lively is not None:
            boxes, scores, present = lively(frame)
        else:
            boxes, scores = self.detector.detect(frame)
            present = len(boxes) > 0
        score = float(scores.max()) if len(scores) else 0.0
        if self.faces is not None:                     # only known faces count
            present = present and self.faces.known(frame)
        self.framebox.put(frame, boxes, scores)        # the debug view sees
                                                       # the same truth
        log.debug("frame: present=%s score=%.2f", present, score)
        return present, score

    def _mode(self):
        if self.state == "off":
            return self.camera_cfg["mode_off"]
        return self.camera_cfg["mode_on"]

    def _grab(self):
        """(frame, opened): opened is True when a camera handle was
        actually constructed and then failed to deliver a frame (a
        stall: today's fail-closed vote), False when the open itself
        failed (a real driver error, or a rotation in which no camera
        could open): that is an abstain, and an abstain is not a
        verdict."""
        try:
            indexes = self._indexes()
            index = indexes[0] if indexes else 0
            if len(indexes) <= 1 and self._policy(index) == "off":
                # a switched-off eye (or a degraded one whose fallback
                # cadence has not turned) never votes: an abstain,
                # never a verdict - the state machine keeps going
                return None, False
            # the single camera's branch is its OWN effective mode -
            # a per-index table entry wins over the table's global;
            # the rotor's branch stays on the table's global, because
            # its walk decides per eye anyway
            branch = (self.effective_mode(index) if len(indexes) <= 1
                      else self._mode())
            if branch == "boot_per_poll":
                rot = self._rotor()
                if rot is not None:
                    # the rotation keeps one persistent adapter across
                    # polls: the cursor must outlive the per-poll open
                    # and release, or every poll starts on camera one
                    frame = rot.read(mode="boot_per_poll")
                    self._note_vote(rot.last_index, frame)
                    return frame, rot.last_opened
                if self.camera is not None:
                    # gate finding 1: a degraded always stream must
                    # hand its held handle back FIRST - opening the
                    # boot-poll eye over a live exclusive device means
                    # the LED never rests and the second open is
                    # refused by real drivers (the vote comes back
                    # None = fail-closed absent, every fallback tick)
                    self._release_camera()
                cam = self._new_camera()
                try:
                    cam.warm_up()
                    frame = cam.read()
                    self._note_vote(index, frame)
                    return frame, True
                finally:
                    cam.release()                # the LED rests; the user
                # can always notice the blink
            rot = self._rotor()
            if rot is not None:
                # a rotor is never recreated here: every index keeps
                # its own slot (a dead one retried on its turn, a
                # stalled one released and reopened) and the cursor
                # must outlive the dead ones, so a dead camera can
                # never veto a live one
                if not rot.is_open():
                    rot.warm_up()
                frame = rot.read(mode="always_on")
                self._note_vote(rot.last_index, frame)
                return frame, rot.last_opened
            cam = self.camera
            if cam is None or not cam.is_open():
                cam = self.camera = self._new_camera()
                cam.warm_up()
            frame = cam.read()
            self._note_vote(index, frame)
            if frame is None and self.camera is not None:
                # a handle that stopped flowing IS a dead handle,
                # whatever is_open() swears (measured: the standby
                # transition leaves open-yet-frozen cameras behind;
                # reading the corpse every poll forever is exactly
                # the "no LED, no wake, mouse required" symptom)
                self._release_camera()
            return frame, True
        except Exception:
            log.exception("grab failed; treating this poll as no frame")
            self._release_camera()               # half-dead device: next
            # poll opens a fresh one. the vote shape is the shipped
            # one: with no rotor behind this failure nobody else is
            # watching, so a single-camera desk keeps its fail-closed
            # absent - only a rotation may abstain (a dead camera must
            # never veto a live one; a lone dead camera has no live
            # one to veto, and abstaining would keep the screens lit
            # forever with nobody ever seen again)
            return None, not self._multi_cam()

    def _multi_cam(self):
        """True when the duty roster holds more than one camera. Pure
        config math plus one honest exception: a rotor that open-time
        resolution handed us owns this desk until the config itself
        says otherwise (the hot-plug case the load probe missed).
        Safe to call from an except arm. name matches are merged INTO
        the index list at config load (config.get_config), so the
        length check is the whole truth, names included."""
        from .. import config
        if getattr(self.camera, "rotating", False):
            return True
        return len(config.normalize_index(self.camera_cfg.get("index", 0))) > 1

    def _roster_words(self):
        """"camera index 2" or "cameras [0, 2]" - the burst notice has
        to read right whichever roster is on duty."""
        r = self.camera_cfg["index"]
        if isinstance(r, (list, tuple)):
            if len(r) > 1:
                return "cameras %s" % (list(r),)
            r = r[0] if r else None
        return "camera index %s" % r

    def _rotor(self):
        """The shared RotatingCamera while the config holds more than
        one camera; None for a single one (the single path keeps its
        exact old open and close shape - a single camera never goes
        through rotation code at all). The adapter is created on
        demand, so a pause or snooze that releases it simply gets a
        fresh one next poll."""
        from .. import config
        indexes = config.normalize_index(self.camera_cfg.get("index", 0))
        if len(indexes) <= 1:
            if getattr(self.camera, "rotating", False):
                return self.camera    # the load probe missed it, the
                                      # open-time one found it: the rotor
                                      # that exists keeps voting (single
                                      # logic would drop it every poll)
            return None
        if self.camera is None or not getattr(self.camera, "rotating", False):
            self.camera = self._new_camera()
        return self.camera

    def _new_camera(self):
        from .. import camera
        # index -2 = hello IR. The per-index policy is a live call
        # into the monitor (effective mode + the degraded cadence
        # gate), so the rotor consults the display state and the wear
        # clock at read time; policy changes need no rotor rebuild
        return camera.open_camera(self.camera_cfg, policy=self._policy)

    def _hold_camera(self):
        if self.camera is None or not self.camera.is_open():
            self._release_camera()               # a present-but-dead
            # device still gets its honest release + detector reset;
            # letting the destructor eat it skips both
            self.camera = self._new_camera()
            self.camera.warm_up()

    def _off_phase_hold(self, keep, phase):
        """The per-index stream-through, in its two moments.
        phase="before": the panels are still lit - the eyes that do NOT
        stream through let go now, while an honest release is cheap,
        and nobody is opened: a camera can only ride the transition
        if it is open BEFORE it, and what is already open stays.
        phase="after": the panels are dark - every kept eye is proven
        open now, the one moment an open is proven safe (a probe that
        opens after the dark always streams fine), and the non-kept
        eyes stay released. keep is None (the pre-policy shape) means
        hold the whole current camera, as today."""
        rot = self.camera
        if rot is not None and getattr(rot, "rotating", False):
            for index in list(rot.indexes):
                cam = rot.cameras.get(index)
                kept = keep is None or index in keep
                if phase == "before":
                    if not kept and cam is not None:
                        cam.release()
                        rot.cameras[index] = None
                elif kept:
                    if cam is None or not cam.is_open():
                        cam = rot._open(index)
                        rot.cameras[index] = cam
                        if cam is not None:
                            cam.warm_up()
                elif cam is not None:
                    cam.release()
                    rot.cameras[index] = None
            return
        kept = keep is None or len(keep) == 1
        if kept:
            self._hold_camera()
        else:
            self._release_camera()

    def _release_camera(self):
        if self.camera is not None:
            self.camera.release()
            self.camera = None
            reset = getattr(self.detector, "reset", None)
            if reset is not None:
                reset()      # MotionDetector: the next open may be a
                             # DIFFERENT camera, and diffing the new
                             # scene against the old one is a phantom
                             # motion hit worth hold_sec of presence
