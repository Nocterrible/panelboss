"""The HDR auto-switch watcher (amendment 8): a pure hysteresis
machine plus the arm that feeds it real senses. Own thread (cli's
arm), cadence POLL_SEC - it NEVER rides the duty _poll, which knows
cameras and nothing of color.

The tiers arrive as cfg [hdr] auto = {model: off|video|content}
(models are the EDID identities - the slot-agnostic key the profiles
already trust). video = PDH video-engine activity (a decoder is
playing something; the _videostats header tells why encode does not
count); content = the mpv pipe answers bt.2020+PQ. A tier that is
absent or "off" is nobody's business - the default-off law again.

Hysteresis, both constants named here for the owner to tune later:
ENGAGE_SEC of unbroken busy BEFORE the panel lights (a codec probe
flinching for a frame must not flicker someone's desktop), and
RELEASE_SEC of quiet BEFORE it goes (leaving HDR because of a two-
second pause is the flicker worse than the first). The machine is
PURE - state in, (state, verdict) out, the caller's clock - so the
suite fake-clocks the whole dance offline; only the arm touches
wm/_videostats and the driver. Every emit re-anchors its clock, so
a held edge commands once, not every tick.
"""

import logging
import time

from .. import wm
from ..wm import _videostats

log = logging.getLogger("state")

POLL_SEC = 2.0        # the watcher's heartbeat; the PDH collect gap
                      # (~1.2 s by that module's measured design)
                      # fits inside it by construction
ENGAGE_SEC = 2.0      # busy this long UNBROKEN before HDR lights
RELEASE_SEC = 30.0    # idle this long before it is handed back
BUSY_FLOOR = 0.5      # summed video-engine percent that counts as
                      # playing (a 0.4 % dust reading must not engage)
TIERS = ("off", "video", "content")


def hdr_step(st, now, busy, lit):
    """Pure hysteresis. st = the model's clocks; now = the caller's
    clock; busy = the tier's fact this tick; lit = the driver's READ
    answer (never a belief). Returns (st, want): want True/False is
    the command this tick, None is silence - and silence is the
    answer in every steady state, so the arm emits at edges."""
    st = dict(st)
    if busy:
        st["idle_since"] = None
        if lit:
            st["busy_since"] = None      # already wearing it: nothing
            return st, None             # owed, and no clock to hold
        if st.get("busy_since") is None:
            st["busy_since"] = now
        if now - st["busy_since"] >= ENGAGE_SEC:
            st["busy_since"] = None      # re-anchor: one command
            return st, True             # per edge, not per tick
        return st, None
    st["busy_since"] = None
    if not lit:
        st["idle_since"] = None          # dark and asked nothing
        return st, None
    if st.get("idle_since") is None:
        st["idle_since"] = now
    if now - st["idle_since"] >= RELEASE_SEC:
        st["idle_since"] = None          # re-anchor the release too
        return st, False
    return st, None


class _HdrWatchMixin:

    def hdr_watch(self, stop):
        """The thread body (cli's arm): tick, then wait out the
        cadence; the stop event answers a quit between the ticks."""
        log.info("hdr watcher alive")
        mst = {}
        while not stop.is_set():
            try:
                self._hdr_tick(mst, time.time())
            except Exception:
                log.exception("hdr tick failed; the loop goes on")
            stop.wait(POLL_SEC)

    def _hdr_tick(self, mst, now):
        """One pass: read the tiers, read the desk, read the senses,
        command the edges. Any trouble names itself in the log and
        the tick is over - a dead pipe or a wedged provider must
        never reach the camera work, which lives on other threads
        entirely."""
        cfg = self.cfg.get("hdr") or {}
        auto = cfg.get("auto") or {}
        tiers = {k: v for k, v in auto.items() if v in TIERS
                 and v != "off"}
        if not tiers:
            mst.clear()                  # nothing claimed: clocks rest
            return
        busy = {}
        if "video" in tiers.values():
            busy["video"] = _videostats.video_busy() >= BUSY_FLOOR
        if "content" in tiers.values():
            busy["content"] = _videostats.mpv_hdr_playing(
                cfg.get("mpv_pipe") or _videostats.MPV_PIPE_DEFAULT)
        for r in wm.hdr_states():
            tier = tiers.get(r.get("model"))
            if tier is None or not r.get("supported"):
                continue                 # not claimed, or cannot do it:
            st = mst.get(r["model"], {}) # no clocks, no lies
            st, want = hdr_step(st, now, bool(busy.get(tier)),
                                r.get("state") == "on")
            mst[r["model"]] = st
            if want is None:
                continue
            say = wm.hdr_set(r["gdi"], want)
            log.info("hdr auto: %s -> %s (%s)%s", r["model"],
                     "on" if want else "off", tier,
                     "" if not say else "; refused: " + say)
