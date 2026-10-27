"""Camera handling: the vote path (_poll/_grab), the duty roster's
rotor, stream holds and releases. Formerly state.py lines 510-734.
Since Oct 12 the VOTE opens ride the lease's AsyncOpener too: an eye
that is opening abstains, a known-dead single open keeps its
fail-closed ABSENT through the opener's failed record (and camera's
new evict keeps the boot blink off the loop thread), and no driver's
17 s tax is ever paid on the loop thread again.
SIZE LAW: measured 561 (Oct 22; refresh at the ghost-law gate - the header law is the point, the dark-camera record: _poll's
verdict wrapper + _note_verdict + the accessor grew the file's HEAD
by 27 - the record lives here because a second camera opinion is the
one sin the feature cannot commit, and pulling it out would put the
vote's truth one file from the code that casts it; Oct 22, the
ghost-law wave: the deaf-eye record (deaf_indices + _note_deaf, ~50
lines) rode in for the same reason - the wear clock it counts on is
this file's ledger, and the round budget is _roster_shuffling's own
arithmetic; formerly measured 368, Oct 13, after the consent gate
rode in at
_poll's head - one guard clause, the file's own doctrine): the two
single-desk vote arms grew, but they
ARE one contract (the (frame, opened) abstain/fail-closed split) and
splitting them from _grab would put the vote's truth two files away
from the code that casts it."""

import logging
import math
import time

from .. import wakesnap

log = logging.getLogger("state")

# the dark-eye notice (owner Oct 21, amendment included): the camera
# going dark is news on its own - UNCONDITIONAL, once per dark episode,
# re-armed by a recovery to present - because any user with detection
# on deserves to learn their eye went quiet. Phrased true for a desk
# with no 'present' rows too: with no verdict, presence-based behavior
# is exactly what paused.
CAMERA_DARK_MSG = ("the camera stopped seeing - presence-based behavior "
                   "is paused until it sees a person again")

DEAF_MIN_ROUNDS = 2      # law 4 (the ghost-law dispatch, Oct 22): an
                         # enrolled eye owes a vote EVERY duty round
                         # (one full sweep = present_recheck_sec x
                         # roster size, the _roster_shuffling
                         # arithmetic); this many silent rounds and
                         # the eye is DEAF - announced once per
                         # episode, badged on the detection tab's
                         # roster, cleared by the next vote. The
                         # 00:47 autopsy's class: "enrolled but deaf"
                         # must never render as invisibility.


class _CamsMixin:

    @property
    def camera_present(self):
        """READ-ONLY accessor (the packet's one opinion): the camera's
        last verdict - True seen, False absent, None = no verdict
        (consent off, dead eye, blinded eye, no frame). The hold
        policy's 'present' rows read this; 'presence unknown ==
        absent' is applied at the decision, not by a second vote."""
        return self._camera_present

    def _roster_shuffling(self):
        """The gate MEDIUM's one guard (owner desk census: TWO camera
        legs, cam0/cam2): the rotation reads ONE eye per poll, so an
        abstain while the walk is mid-round is the ROSTER SHUFFLING,
        not the eye going dark - it must not clear the presence record
        nor file a balloon. The roster knowledge is the wear clock
        this file already keeps (last_vote: when each eye last
        delivered a frame): the round counts as spoken while ANY
        index of the CURRENT duty roster has delivered within the
        round's TRUE budget - two full sweeps (the roster SHARES the
        recheck cadence: per-eye period = present_recheck_sec x
        roster size) plus the named warm-open allowance (the duty
        door's measured 3.8-5.5 s on this desk, worst-warm 27 s by
        the camcore number). The window is not theory: the owner's
        live file tunes present_recheck_sec = 35, and the first
        shipped window (2 x recheck, roster-blind) aged exactly at
        that cadence's edge - True->None gaps of 69 s measured the
        evening of the merge, the hold flickering ~6 s per hand-off.
        NO rotation -> no guard: the single-eye exemption the law
        wants is the ABSENCE of a roster, not a pass; a single dead
        desk keeps its balloon."""
        if not self._multi_cam():
            return False
        from .. import config
        roster = config.normalize_index(self.camera_cfg.get("index", 0))
        grace = (2 * self.timers["present_recheck_sec"] * len(roster)
                 + 30.0)
        now = time.monotonic()
        return any(now - self.last_vote.get(i, -math.inf) <= grace
                   for i in roster)

    def _rest_credit(self):
        """Polling RESTARTING is not a roster dying: the camera rests
        while the owner types (the idle gate) and across a pause's
        gate-release, and the first duty open after any rest votes
        abstain through the door's seconds. Stamps are refreshed at
        the restart seams so the age the guard measures accrues only
        while the machine is really polling. No verdict is invented:
        the credit touches the walk's ledger, never the record."""
        from .. import config
        now = time.monotonic()
        for i in config.normalize_index(self.camera_cfg.get("index", 0)):
            self.last_vote[i] = now

    def deaf_indices(self, now=None):
        """LAW 4 (the ghost-law dispatch): {index: rounds} for every
        enrolled eye that has delivered no vote for at least
        DEAF_MIN_ROUNDS full duty rounds. The cadence is the walk's
        own bookkeeping (last_vote, the wear clock _note_vote keeps;
        the round budget is _roster_shuffling's arithmetic: the roster
        shares the recheck cadence, one full sweep costs
        present_recheck_sec x roster size). An eye that has never
        voted ages from the first moment the machine noticed it
        enrolled - a warm-open eye at boot is not yet deaf - and any
        delivered frame resets the streak, which IS the badge's clear.
        Read this for the detection tab's roster (the duty cards); the
        INFO confession is _note_deaf's job."""
        if now is None:
            now = time.monotonic()
        from .. import config
        roster = config.normalize_index(self.camera_cfg.get("index", 0))
        if not self.camera_cfg.get("enabled"):
            # the consent door is not deafness: while detection is off
            # NOTHING is due, so the silence is re-based on the spot
            # (and a door shut all night must not judge its eye at the
            # first poll after it opens - the stamps are re-based
            # throughout the shut period, not at the opening)
            for i in roster:
                if i in self.last_vote:
                    self.last_vote[i] = now
                else:
                    self._deaf_since[i] = now
            return {}
        sweep = self.timers["present_recheck_sec"] * max(1, len(roster))
        out = {}
        for i in roster:
            if self._policy(i) == "off":
                # a switched-off eye (or one cadence-held until its
                # fallback turn) owes no vote - it is parked, not
                # deaf (the _round_tally want-set's own exclusion)
                self._deaf_since.pop(i, None)
                continue
            stamp = self.last_vote.get(i)
            if stamp is None:
                stamp = self._deaf_since.setdefault(i, now)
            else:
                self._deaf_since[i] = stamp      # a vote re-bases the eye
            rounds = int((now - stamp) // sweep)
            if rounds >= DEAF_MIN_ROUNDS:
                out[i] = rounds
        return out

    def _note_deaf(self, now=None):
        """The loop side of law 4: the deaf report, INFO, ONE line per
        episode (re-armed by the eye's next vote - an episode is one
        continuous silence, not one silent round). Rides the _poll
        seam: the duty's own cadence is the only clock that may call
        an eye deaf, and the ledger is the one the wear guard already
        writes; no new thread, no new poll."""
        report = self.deaf_indices(now)
        self._deaf_reported &= set(report)       # a recovered eye's
        # episode is over: its next silence gets a fresh confession
        for index, rounds in sorted(report.items()):
            if index in self._deaf_reported:
                continue
            self._deaf_reported.add(index)
            log.info("eye %s enrolled but deaf: %d rounds without a vote"
                     " - check device/disconnected", index, rounds)
        return report

    def _note_verdict(self, present, shuffled=True):
        """The single record point for every camera verdict: _poll
        routes here, and the consent-off drain calls it directly (the
        instant the door shuts there is no verdict, and a 'present'
        row must let go THIS tick, not at the next poll). The
        seen-to-dark edge (a verdict that WAS present going
        no-verdict) files the balloon once; the dark->seen recovery
        re-arms the edge; absent (False) is the eye still talking,
        not an eye gone quiet - no balloon for a real verdict. The
        one exemption below it (gate MEDIUM): an abstain from a
        half-spoken multi-eye round is the roster SHUFFLING, not the
        eye going dark - the record holds, no edge, no balloon; a
        round whose EVERY eye has fallen silent IS dark (the guard
        falls away and the edge fires as the law says). shuffled=False
        (the consent drain) FORFEITS the credit: the door the owner
        just shut is the dark, however fresh the stamps are."""
        if (present is None and shuffled and self._roster_shuffling()):
            return present                     # the walk, not the dark
        was = self._camera_present
        self._camera_present = present
        if was is True and present is None and self.notifier is not None:
            try:
                self.notifier(CAMERA_DARK_MSG)
            except Exception:
                pass                             # the notice is a courtesy
        return present

    def _poll(self):
        """The duty vote wrapped at the one gate: every verdict the
        state machine holds is recorded here on its way out, so the
        hold's third state and the dark-eye notice read the SAME
        present the phase machine consumes - never a second opinion."""
        present, score = self._poll_camera()
        present = self._note_verdict(present)
        # LAW 4 (the ghost-law build): the deaf-eye badge runs at the
        # duty's own gate - every poll recounts the rounds, the arms
        # that never landed a frame included (that is exactly the
        # episode the badge confesses).
        self._note_deaf()
        return present, score

    def _poll_camera(self):
        if not self.camera_cfg.get("enabled"):
            # the consent gate (redesign law 1): NO camera opens
            # until the owner says so. The gate sits at the poll -
            # the one choke point every duty open (single, rotor,
            # async) rides - so a disable mid-duty drains THROUGH
            # this line: release what is held, keep the roster and
            # the tables, and abstain like any eye that did not
            # look: no verdict, no presence reset, no LED cost.
            if self.camera is not None:
                self._release_camera()
            return None, 0.0
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
        # the lazy imports match the file's habit (the arm at _new_camera
        # does the same): the condition needs the number, so they ride
        # ahead of the branch
        from .. import camera
        import numpy as np
        if int(frame.max()) < camera.BLACK_CEIL:
            # blinded eye (another app owns the sensor - the owner's
            # NVIDIA Broadcast does this during work calls - or the
            # room is genuinely dark): the frame carries LIGHT, and no
            # light carries no verdict. Voting absent here is what
            # slept the owner's screens on an occupied desk (Oct 12).
            self.framebox.put(frame, np.zeros((0, 4)), np.zeros(0))
            log.debug("vote: eye serving black; abstain")
            return None, 0.0
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
        if present and self.state == "off":
            # the wake-frames log (panelboss/wakesnap): the text row
            # is the always half (the owner's amendment, Oct 27: the
            # who-woke-it log costs nothing); the picture rides only
            # under [camera] wake_snap, gated inside remember itself.
            # The verdict's OWN frame, the verdict's OWN moment.
            # PHASE-GATED (reviewer gate): a camera wake can only
            # fire from off, so encoding while the desk is LIT buys
            # a JPEG that every next falsy wake will drop anyway.
            wakesnap.remember(frame, score, self._wake_cam_label())
        log.info("frame: present=%s score=%.2f", present, score)
        return present, score

    def _wake_cam_label(self):
        """The caption the wake log wears for the eye that just voted:
        the owner's label first (bindings and the synthetic "idx:N"
        key - the same identity table display_names reads, resolved
        from the cfg side; the UI's join needs the PnP scan this layer
        does not hold), the bare index when no name claims it (the
        honest fallback the packet named: "index %s"). The eye rides
        _vote_index, recorded by _note_vote at this very grab."""
        idx = getattr(self, "_vote_index", None)
        labels = self.camera_cfg.get("labels") or {}
        for inst, bound in (self.camera_cfg.get("bindings") or {}).items():
            try:
                hit = int(bound) == idx
            except (TypeError, ValueError):
                continue                      # hand-edited toml is input
            if hit:
                text = str(labels.get(str(inst)) or "").strip()
                if text:
                    return text
        text = str(labels.get("idx:%s" % idx) or "").strip()
        return text or ("index %s" % idx)

    def _mode(self):
        if self.state == "off":
            return self.camera_cfg["mode_off"]
        return self.camera_cfg["mode_on"]

    def _opener(self):
        """The single-eye desk's ONE AsyncOpener (created on first
        use; the preview lease builds and re-reads the same object):
        the VOTE path rides the lease's machinery now - the worker
        opens and warms off the loop thread, publishes into the
        opener's held dict, and the next vote adopts that handle.
        _preview_open is the factory: it never hands out a corpse,
        so a silent cv2 zombie records a failed open the vote can
        tell apart from an eye still opening."""
        op = self._single_opener
        if op is None:
            from .. import camera as camera_mod
            op = self._single_opener = camera_mod.AsyncOpener(
                self._preview_open)      # its own held dict: the vote
                                         # and the lease re-read it
        return op                        # every poll

    def _grab(self):
        """(frame, opened): opened is True when a camera handle was
        actually constructed and then failed to deliver a frame (a
        stall: today's fail-closed vote), False when the open itself
        failed (a real driver error, or a rotation in which no camera
        could open): that is an abstain, and an abstain is not a
        verdict. Since Oct 12 NO open blocks this thread: an eye that
        is opening votes ABSTAIN (the open itself failed contract in
        the shape of "not open yet"), and the single desk's KNOWN-dead
        open keeps its fail-closed ABSENT through the opener's failed
        record."""
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
                    # and release, or every poll starts on camera one.
                    # read(mode="boot_per_poll") opens through the
                    # rotor's AsyncOpener now: the eye that is opening
                    # abstains (rot.last_opened False = no frame), and
                    # the eye whose open landed votes, releases and
                    # evicts - the LED blink survives, the block dies
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
                op = self._opener()
                cam = op.open_async(index)
                if cam is None:
                    if index in op.dropped:
                        op.rearm(index)  # the vote retries like the
                    # old synchronous boot did: the no-re-pin tombstone
                    # guards the preview lease, and a vote never pins
                    dead = index in op.failed
                    log.debug("eye %s %s", index,
                              "open died; fail-closed" if dead
                              else "still opening; abstain")
                    # an eye that is merely OPENING abstains (the
                    # shipped no-verdict contract); an open that is
                    # KNOWN dead keeps the single desk's fail-closed
                    # ABSENT (multi_cam_test 7) - only never on this
                    # thread again
                    return None, dead
                try:
                    frame = cam.read()
                    self._note_vote(index, frame)
                    return frame, True
                finally:
                    op.evict(index)      # the LED rests; the user
                # can always notice the blink: ONE open-read-release
                # per vote, the boot promise intact, off the loop thread
            rot = self._rotor()
            if rot is not None:
                # a rotor is never recreated here: every index keeps
                # its own slot (a dead one retried on its turn, a
                # stalled one released and reopened) and the cursor
                # must outlive the dead ones, so a dead camera can
                # never veto a live one. The warm_up() pre-open is
                # gone: it paid the driver's tax (17.4 s measured) on
                # THIS thread, and read's lazy async open abstains
                # meanwhile - the wake transition loses a cycle, not
                # the whole loop
                frame = rot.read(mode="always_on")
                self._note_vote(rot.last_index, frame)
                return frame, rot.last_opened
            cam = self.camera
            if cam is None or not cam.is_open():
                if self.camera is not None:
                    self._release_camera()   # present-but-dead: the
                # honest release + detector reset before replacing it
                op = self._opener()
                cam = op.open_async(index)
                if cam is None:
                    if index in op.dropped:
                        op.rearm(index)
                    dead = index in op.failed
                    log.debug("eye %s %s", index,
                              "open died; fail-closed" if dead
                              else "still opening; abstain")
                    return None, dead
                self.camera = cam            # ADOPT the published
                # handle: every other seam (hold, lease, cooloff,
                # release) knows the desk's live eye through self.camera.
                # Null the store row on adoption (satellites F3): the
                # same handle in held AND self.camera was released
                # TWICE by _release_camera (sweep + self.camera), saved
                # only by cv2 idempotency one layer down - one owner
                # releases now. The None row is the sweep's own evict
                # footprint ("None rows are the vote's evict footprint:
                # already released on the spot"): verified while reading
                # the sweep, it releases only non-None rows, so the
                # adopted-None row lands in the already-safe shape.
                op.held[index] = None
            frame = cam.read()
            self._note_vote(index, frame)
            if frame is None and self.camera is not None:
                # a handle that stopped flowing IS a dead handle,
                # whatever is_open() swears (measured: the standby
                # transition leaves open-yet-frozen cameras behind;
                # reading the corpse every poll forever is exactly
                # the "no LED, no wake, mouse required" symptom). The
                # release sweeps the opener's row too (invalidate +
                # held release), so the next vote re-opens fresh
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
            # forever with nobody ever seen again). the async vote
            # arms honour the same split: a lone desk whose open has
            # ALREADY died votes absent through the opener's failed
            # record; only the not-yet-landed eye abstains
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
        self._vote_index = None          # a released eye has no verdict:
        self._round = None               # a credit armed before this
                                         # release must never be
                                         # consumed as an ABSENT verdict
                                         # by a later fail-closed tick
                                         # (audit: an eye with no verdict
                                         # cast one, closing the AND round
                                         # a whole preview lease early); a
                                         # half-collected AND round
                                         # straddling a release starts over
        self.preview_cool = 0.0          # a wall that just died cannot
                                         # be warm (gate finding 3: any
                                         # release path clears the flag)
        if self._single_opener is not None:
            self._single_opener.invalidate()   # the rotor carries its own
            # invalidation inside release(); the single-eye seam lives on
            # the monitor, so the gen bump that makes an in-flight open
            # release its own fresh handle has to happen here
            for held in list(self._single_opener.held.values()):
                if held is not None:       # gate finding 1 (HIGH): a
                    held.release()         # publish that landed
                # after the last leased tick would otherwise sit LED-on
                # with no owner - the rotor seam survives ONLY because
                # release() sweeps its store. None rows are the vote's
                # evict footprint: already released on the spot.
            self._single_opener.held.clear()
        if self.camera is not None:
            self.camera.release()
            self.camera = None
            reset = getattr(self.detector, "reset", None)
            if reset is not None:
                reset()      # MotionDetector: the next open may be a
                             # DIFFERENT camera, and diffing the new
                             # scene against the old one is a phantom
                             # motion hit worth hold_sec of presence
