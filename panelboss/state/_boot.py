"""The engine's body: construction, the run loop, the per-tick dispatch.
Formerly state.py lines 53-159 (the __init__ and the run section)."""

import logging
import math
import queue
import time

from .. import display
from .. import dimmer
from .. import hider
from .. import jog
from .. import videoeye
from ._preview import FrameBox

log = logging.getLogger("state")

# One dial: when a preview lease dies its OWN death (expiry, or the
# value<=0 cancel that lands the same way), the cameras do NOT release
# immediately - the wall stays warm this many seconds and an open still
# in flight COMPLETES AND PUBLISHES into it. The live desk proved the
# alternative a spiral: a 20-27 s driver open, released mid-flight by
# the next toggle's lease-end, restarted from zero and died to the next
# poke - forever. Inside the window a fresh lease ATTACHES (zero driver
# cost, wall live this tick); past it the release lands and the LED
# goes honestly off. Pause/snooze/quit still release instantly: those
# are not user flicker.
PREVIEW_COOLOFF_SEC = 5.0


class _BootMixin:

    def __init__(self, config, detector, faces=None, ui_events=None):
        self.cfg = config
        self.timers = config["timers"]
        self.camera_cfg = config["camera"]
        self.guards = config["guards"]
        self.recovery = config["recovery"]
        self.inference_cfg = config["inference"]
        # setdefault, not get: an old config file that predates the
        # section must still CONNECT, or a tray mode switch writes into
        # a dangling dict and the next rebuild reads stale mode
        self.detection_cfg = config.setdefault("detection", {})
        self.detector = detector
        self.faces = faces
        self.ui_events = ui_events           # the settings window listens
        self.events = queue.Queue()          # tray commands land here
        self.framebox = FrameBox()           # the debug view reads this
        # the screens' true state is unknowable at startup: the watcher
        # only learns from broadcasts, so a fresh instance that begins
        # while the monitors are dark (previous instance turned them
        # off, power plan did, a restart between) must not claim "on"
        # and then never wake - "unknown" behaves like counting but
        # takes the free SC_MONITORPOWER ON at the first proof of life
        self.state = "unknown"
        self.next_poll = math.inf            # the camera rests until the
                                             # gate opens
        self.absent_since = None              # when the absence started
        self.hits = 0                         # consecutive positive frames
        self._blind = {}              # index -> bool: served-black state
                                      # (transition-confessions only)
        self._round = None                # eyes that voted absent since
                                          # the last positive (OR/AND
                                          # tally, owner doctrine)
        self._vote_index = None           # eye whose verdict is in
                                          # flight (set by _note_vote)
        self.snooze_until = 0.0
        self.grace_until = 0.0                # leave_on budget
        self.re_off_deadline = math.inf       # counting-after-wake budget
        self.paused = False
        self.quit = False
        self.camera = None                    # opened lazily, per mode
        self.last_present = 0.0
        self.preview_until = 0.0              # debug window lease
        self.previewing = False
        self.preview_cool = 0.0               # warm-wall deadline after a
                                              # natural lease end (see
                                              # PREVIEW_COOLOFF_SEC)
        self._single_opener = None            # single-eye async-open
                                              # seam, built on first use
        self._pin_logged = False              # the pinned-by-an-open
                                              # confession runs once
                                              # per lease, not per tick
        self.wake_times = []                  # unexpected wakes, recent
        self.re_off_paused = False            # burst tripped; stays lit
        self.notifier = None                  # cli wires icon.notify
        self.tray_sink = None                 # cli wires icon.set_state
                                              # (the ui tick feeds it;
                                              # the tray's holes are
                                              # the status)
        self._hdr_snap = []                   # gdis HDR was on at the
                                              # moment the desk went
                                              # dark (power section)
        self.away_status = {}                 # the fake-off ledger:
        self._away_bright = {}                # status words, brightness
        self._away_hdr = []                   # priors, HDR snapshot
                                              # (see state/_away.py)
        self.power_cfg = config["power"]
        self.blockers = {"error": "not checked yet", "display": [],
                         "other": []}          # window reads this live
        self.blockers_until = 0.0             # throttle for powercfg
        self.display_held_reported = False
        self.layout = None                    # the desk as it was when we
        self.layout_gen = 0                   # turned it off (see wm)
        # per-index vote policy (config: [camera.on] / [camera.off]
        # tables + wear guard; see effective_mode). The monitor is the
        # source of truth the rotor's policy callable reads at vote
        # time, so a policy change (display-state flip, degradation)
        # needs no rotor rebuild
        self.armed = {}                       # index -> when its current
                                              # continuous always_on run
                                              # was armed (boot, or the
                                              # last flip INTO a table)
        self.last_vote = {}                   # index -> last frame vote;
                                              # the degraded cadence gate
        self._rearm("on")                     # boot: the on table applies
                                              # (unknown counts as on),
                                              # every effective always
                                              # eye starts its wear clock

    # ------------------------------------------------------------------ run
    def run(self):
        display.watch()                    # the sink always starts first
        hider.boot()                       # the faux-strip FSM: silent
                                           # until [hider] says on, and
                                           # ordinary windows die with
                                           # the process - a crash
                                           # unpaints by construction
        while not self.quit:
            d = None
            try:
                d = self._tick()
            except Exception:              # a driver hiccup (the virtual
                log.exception("tick failed; the loop goes on")   # camera
                self.preview_cool = 0.0    # has killed threads before):
                self._release_camera()     # the honest word is a
                                           # release NOW, cooloff or not
            time.sleep(0.2 if d is None else d)
        jog.teardown()                     # the ring forgets its place
        hider.teardown()                   # the orderly half of the same
                                           # promise, on every exit path
        dimmer.teardown()                  # every veil gone: ordinary
                                           # windows die with the process

    def _tick(self):
        """One loop cycle. Returns the lease's poll delay (seconds)
        while the preview lease is held, None everywhere else - the
        run loop's idle 0.2 s stays the whole story outside leases."""
        now = time.monotonic()             # the clock always comes after
                                           # every sleep
        self._drain_tray()
        self._drain_display(now)
        jog.tick_with_cfg(self.cfg, now)   # the refresh ring steps
                                           # BEFORE the strips read
                                           # their offset (one tick of
                                           # latency at most, and the
                                           # ring's zero is the resting
                                           # pose either way)
        hider.tick(self.cfg)               # the shell's own ears stay
                                           # outside the camera's pause:
                                           # a paused watch must still
                                           # let the taskbar come back
        dimmer.tick(self.cfg, now)         # the veils converge AFTER the
                                           # strips: the ring's offset is
                                           # already this beat's and the
                                           # census must not see a
                                           # half-moved desk
        videoeye.tick(self.cfg, now)       # the video eye reads the desk
                                           # AFTER the veils took the
                                           # last answer: one beat of
                                           # latency at most (0.2 s),
                                           # and a dead port may not
                                           # stall the camera phase
                                           # machine behind it
        if self.quit:
            return
        self._apply_hold(now)                # the policy is asserted every
                                             # tick: a stray clear (wake's
                                             # pulse) dies within a cycle
        leased = now < self.preview_until
        if leased:
            # the settings window holds the camera; the lease expires on
            # its own so a killed UI cannot pin the device. The lease
            # cadence is what the card's "~5 fps" promised; poll_while_*
            # stays untouched outside leases
            pps = max(50, min(2000, int((self.cfg.get("ui") or {})
                                        .get("preview_poll_ms",
                                             200)))) / 1000.0
            self.next_poll = now + pps
            self.previewing = True
            self._preview(now)
            return pps
        if self.previewing:
            # a natural lease end (expiry, or the value<=0 cancel that
            # lands right here): do NOT release. The wall goes WARM -
            # cameras and rotor stay exactly as they are, an open still
            # in flight completes and publishes into them (no
            # _invalidate: that is what made the owner's 27 s of driver
            # work restart from zero on every toggle), and a begin
            # inside PREVIEW_COOLOFF_SEC attaches to this wall for free
            self.previewing = False
            self._pin_logged = False            # the next lease gets its
                                                # own confession
            self.preview_cool = now + PREVIEW_COOLOFF_SEC
            self.next_poll = now               # the phase machine re-arms
                                               # its own cadence against
                                               # the warm camera
        elif self.preview_cool and now > self.preview_cool:
            self.preview_cool = 0.0
            self._release_camera()             # the warm window closed:
                                               # gen-bump + release, the
                                               # LED honestly off by now
            self.next_poll = now
        if self.paused or now < self.snooze_until:
            self.preview_cool = 0.0            # pause and snooze are not
            self._release_camera()             # user flicker: release NOW
            self.next_poll = math.inf
            return
        if self.next_poll == math.inf:
            # gate release re-arms: math.inf is ONLY ever set by the
            # paused/snooze gate above, so arriving here past the gate
            # means the gate just opened (unpause click or snooze
            # expiry) - without this the phase machine never polls
            # again (audit HIGH: lit desk stays lit all night, dark
            # desk camera-wakes only on physical input)
            self.next_poll = now
        idle = display.get_idle_time()     # the input gate always comes first
        if self.state == "off":
            self._off_phase(now, idle)
        else:
            self._on_phase(now, idle)
