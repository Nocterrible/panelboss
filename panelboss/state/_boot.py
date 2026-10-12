"""The engine's body: construction, the run loop, the per-tick dispatch.
Formerly state.py lines 53-159 (the __init__ and the run section)."""

import logging
import math
import queue
import time

from .. import display
from ._preview import FrameBox

log = logging.getLogger("state")


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
        self.snooze_until = 0.0
        self.grace_until = 0.0                # leave_on budget
        self.re_off_deadline = math.inf       # counting-after-wake budget
        self.paused = False
        self.quit = False
        self.camera = None                    # opened lazily, per mode
        self.last_present = 0.0
        self.preview_until = 0.0              # debug window lease
        self.previewing = False
        self._pin_logged = False              # the pinned-by-an-open
                                              # confession runs once
                                              # per lease, not per tick
        self.wake_times = []                  # unexpected wakes, recent
        self.re_off_paused = False            # burst tripped; stays lit
        self.notifier = None                  # cli wires icon.notify
        self._hdr_snap = []                   # gdis HDR was on at the
                                              # moment the desk went
                                              # dark (power section)
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
        while not self.quit:
            d = None
            try:
                d = self._tick()
            except Exception:              # a driver hiccup (the virtual
                log.exception("tick failed; the loop goes on")   # camera
                self._release_camera()     # has killed threads before)
            time.sleep(0.2 if d is None else d)

    def _tick(self):
        """One loop cycle. Returns the lease's poll delay (seconds)
        while the preview lease is held, None everywhere else - the
        run loop's idle 0.2 s stays the whole story outside leases."""
        now = time.monotonic()             # the clock always comes after
                                           # every sleep
        self._drain_tray()
        self._drain_display(now)
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
            self.previewing = False
            self._pin_logged = False            # the next lease gets its
                                                # own confession
            self._release_camera()             # back to the scheduled modes
            self.next_poll = now               # the phase machine re-arms
                                               # its own cadence next tick
        if self.paused or now < self.snooze_until:
            self._release_camera()
            self.next_poll = math.inf
            return
        idle = display.get_idle_time()     # the input gate always comes first
        if self.state == "off":
            self._off_phase(now, idle)
        else:
            self._on_phase(now, idle)
