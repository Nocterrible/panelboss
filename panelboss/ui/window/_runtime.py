"""The tick loop: UI refresh, tray-event drain, status and
blocker lines, teardown.
"""

from __future__ import annotations

import logging
import queue
import time

from ... import wm
from ._widgets import set_text

log = logging.getLogger("ui")


class _RuntimeMixin:
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
        try:
            from ... import hotkeys
            hotkeys.teardown()        # the orderly half, CALLED (gate
            #                          f5): release the chords on quit,
            #                          don't just promise to
        except Exception:
            pass
        super().destroy()


    def _tick_ui(self):
        if getattr(self, "_dying", False):
            return
        try:
            self._tick_inner()
            self._hotkey_beat()
            now = time.monotonic()
            if now - getattr(self, "_desk_fp_t", 0.0) >= 2.0:
                self._desk_fp_t = now
                self._desk_check()
        except Exception:
            log.exception("ui tick failed; the loop goes on")
        try:
            self.after(90, self._tick_ui)
        except Exception:
            pass                        # the window was destroyed


    def _hotkey_beat(self):
        """The four-verb hotkey beat: sync re-arms on a changed stored
        word (the registry's dedicated pump thread does the register and
        the WM_HOTKEY read - no window, no Tk dispatch)."""
        from ... import hotkeys
        hotkeys.sync(self.cfg)


    # ------------------------------------------------------- desk ear --
    # The engine re-enumerates its desk every tick and hot-plug-robust
    # it is; the CARDS froze (the owner's zero-monitor boot, Oct 17 -
    # the window opened onto no panels and every monitor row stayed
    # born-empty). The ear: the pump asks wm.fingerprint() every 2 s
    # (one Enum pass - the suite drives it for exactly that); on any
    # change the monitor-row sections discard and refill from cfg.
    # The belt: the away card's button, for the swap no fingerprint
    # can see - an identical-model panel behind a KVM.
    MONITOR_ROW_REBUILDERS = ("_away_rebuild_rows", "_gaming_rebuild_rows",
                              "_oled_rebuild_rows", "_profiles_render")

    def refresh_monitor_rows(self, why="desk ear"):
        """Every monitor-row card re-reads the desk. One broken
        section must not strand the others (per-section guard); the
        log line names the trigger so a button-mash is honest in the
        transcript."""
        for name in self.MONITOR_ROW_REBUILDERS:
            fn = getattr(self, name, None)
            if fn is None:
                continue
            try:
                fn()
            except Exception:
                log.warning("the %s section refused its desk rebuild",
                            name, exc_info=True)
        log.info("ui: monitor rows rebuilt (%s)", why)

    def _desk_check(self):
        fp = wm.fingerprint()
        was = getattr(self, "_desk_fp", None)
        self._desk_fp = fp
        if was is None:
            return                       # seed; a boot-time desk is
        #                                 today's truth, not a change
        if fp != was:
            self.refresh_monitor_rows()


    def _tick_inner(self):
        now = time.monotonic()
        # the veil holds the TOP, not just at birth: tk stacks every
        # later-created sibling ABOVE it, and the boot sweep is
        # exactly when late widgets are born (roster tiles, first
        # status fills). One raise per tick while it lives is the
        # cheap invariant - a widget that pops over the veil has
        # <=1 tick (~90 ms) of daylight before it's buried again.
        if getattr(self, "_veil_lbl", None) is not None:
            try:
                self._veil_lbl.tkraise()
            except Exception:
                pass                      # mid-teardown: the dying
                                          # flag ends the ticks
        # veil watchdog: a veil that outlives its rebuild is a bricked
        # UI, and every failure path between veil() and unveil() would
        # otherwise be allowed to leave one up. The tick lifts it after
        # ITS OWN budget and confesses in the log - loud stop, not
        # silent stuck. The budget is per-veil now (the hold= the
        # caller passed, staged in _veil_hold): every stock veil holds
        # 3 s exactly as before, and only the camera diagnostic sweep
        # asks for longer, because waiting on a driver IS its job.
        if getattr(self, "_veil_lbl", None) is not None \
                and time.time() - self._veil_since > getattr(
                    self, "_veil_hold", 3.0):
            log.warning("ui: veil stuck past its rebuild window; lifting")
            self._unveil()
        self._drain_ui_events()
        slot = self.monitor.framebox.get()
        if slot is not None and slot[3] != self._shown_ts:
            if self._tab == "detection":
                self._draw(slot)
            # else: the detection tab is AWAY (the owner's leave-reset,
            # _preview_leave): the well shows the placeholder and the
            # new frame's bitmap is built by the FIRST tick after the
            # tab returns, not smuggled in by a hidden poll.
        elif slot is None and self._shown_ts is not None:
            # the cleared slot (a list change, _drain_ui_events) is
            # the reset signal: a None arm that only SKIPS the redraw
            # would leave the canvas painted with the old picture -
            # the previous device's last frame, reading as live. The
            # placeholder takes it (one paint at the transition, not
            # every tick: the flag goes down with the shown ts)
            self._shown_ts = None
            self._preview_placeholder()
        self._update_status(now, slot)
        self._wake_strip_refresh()         # the wake log rides this
        #                              same tick (no new timer): five
        #                              cheap label texts, diff-guarded
        #                              inside the refresh
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
                # NOT a bare deiconify: the first open of a
                # start-minimized app maps a window that has never
                # painted (Tk draws no pixels while withdrawn), and a
                # raw map replays the whole build sweep on screen -
                # _show_first owns every veiled map. manual=True:
                # this request came from the tray, the owner asked
                # for this window, and it is the map the veil budget
                # is for (an unasked boot map may veil, but may not
                # spend the owner's one ceremony)
                self._show_first(manual=True)
                self.focus_force()
            if message == "restore_windows":
                # the tray's 'restore my windows' (the placement trio,
                # Oct 16): the same route as the profiles card's button
                # - scope="windows" applies the captured layout's
                # windows leg alone and opens what is missing. The
                # lock, say line and refusal balloon are the apply
                # path's own; the pane repaints even when its tab is
                # hidden, because the voice must reach a gaze that is
                # not looking at the profiles tab right now.
                try:
                    self._profile_apply(False, scope="windows")
                except Exception:
                    log.exception("tray restore_windows lost in the "
                                  "window pump")
            if message == "companion_sync":
                # the theater hotkey's repaint (the toggle wrote cfg on
                # the pump thread; the switch re-reads it here on the Tk
                # thread - never a cross-Tk checkbox write).
                if hasattr(self, "_sync_companion_switches"):
                    self._sync_companion_switches()
            if message == "later":
                # the queue-side fallback for a worker's done() marshal
                # when the pump thread was not yet in its loop (the
                # Oct-14 marshal law, queue form): the value IS the
                # callable, run on the pump. A dead root means no drain
                # runs, and the loss stays honest.
                try:
                    _value()
                except Exception:
                    log.exception("later() lost in the window pump")
            if message == "assistant_truth":
                self._assistant_truth(_value)
            if message == "assistant_ui":
                # the boot path posts a bare bool; a click's round trip
                # posts (state, generation) - the switch re-enables
                # only on the generation of the click that disabled it
                if isinstance(_value, tuple):
                    self._assistant_ui(_value[0], _value[1])
                else:
                    self._assistant_ui(_value)
            if message == "startup":
                from ... import startup
                self._startup_sync(startup.enabled())
            if message == "power_rows":
                # the state machine's wake post (screen came up on its
                # own, or our own wake re-lit the desk): the hold rows
                # re-derive their selection AND their gray state from
                # live cfg - a self-woken screen with detection off
                # must show 'while present' grayed, not stale-on
                if hasattr(self, "_sync_hold_rows"):
                    self._sync_hold_rows()
            if message == "hdr_sync":
                # amendment 8: a WM_DISPLAYCHANGE ride-up - the color
                # state moved under us. The profiles pane's hdr notes
                # and per-row dropdowns are re-read FROM THE DRIVER
                # (its render walks hdr_states() itself), and the
                # gaming card refreshes the next time its tab paints;
                # an unbuilt pane is not an error, it simply has no
                # row to correct yet
                # THE FREEZE-FIX WAVE (Oct 14) moved that re-read OFF
                # the pump: at wake the driver is COLD, and this pane's
                # walk (live_modes + hdr_states) is the resume class
                # camera.py:56-58 names for an OPEN (measured 16-27 s,
                # 38 s for one enumeration - the lesson 0ffa77e wrote
                # as WARMING on the camera side). The owner's ~20 s
                # window death at 07:19, back-solved through the idle-
                # gate arithmetic, was this arm walking a 16-38 s driver
                # synchronously on the Tk pump - the last pump-side
                # holdout. The walk now runs on the hdr-walk thread and
                # answers through the hdr_data arm below; until it lands
                # the pane keeps its last truth. An unbuilt pane is
                # still not an error: it simply has no row to correct,
                # and the walk costs it only two driver reads.
                self._hdr_refresh_async()
            if message == "hdr_data":
                # the walk's answer lands ON THE PUMP and paints FROM
                # THE PAYLOAD - re-reading the driver here is the exact
                # freeze this wave buried. The in-flight flag goes down
                # before the re-run so latest-wins may spawn; ride-ups
                # that arrived during the walk coalesced into _hdr_due
                # and re-arm exactly ONE fresh walk here (the storm
                # law hdrwake_test pins).
                try:
                    self._profiles_render(driver=_value)
                except Exception:
                    pass
                self._hdr_walk = None
                if getattr(self, "_hdr_due", False):
                    self._hdr_due = False
                    self._hdr_refresh_async()
            if message == "cameras":
                self._apply_cameras(_value)
                if hasattr(self, "_sync_consent_switch"):
                    # the consent repaint (redesign law 2): every
                    # state-side write already fans a resync post
                    # through this arm - the header switch and the
                    # gray-out read the moved key on the same turn,
                    # no second channel
                    self._sync_consent_switch()
                if hasattr(self, "_sync_hold_rows"):
                    # the power card joins the same turn (Oct 21):
                    # detection flipped - the 'while present' segments
                    # re-gray (or un-gray) live, no restart
                    self._sync_hold_rows()
                # every list change resets the debug view's slot (the
                # owner's law: never a stale frame from the previous
                # device) - the draw arm below takes the None slot as
                # the signal to paint the placeholder, so the reset is
                # visible without touching a widget off-thread
                self.monitor.framebox.clear()
                if getattr(self, "_diag_veiled", False):
                    self._diag_veiled = False
                    self._unveil()       # the report lands: the sweep
                                        # (if this scan rode one) is
                                        # over, the list is dressed
            if message == "cameras_veil":
                # the diagnostic sweep's HEARTBEAT (owner amendment
                # 4): the first post veils, every later post re-
                # dresses the ONE veil in place AND renews its lease
                # (_shell's re-dress branch re-stamps the deadline).
                # The watchdog rides the engine's own worst honest
                # silence: 35 s = camera.py's OPEN_LOCK_TIMEOUT (30 s,
                # the deadline one wedged open can hold the device
                # tree) + margin. NOT a budget - the veil lives while
                # the sweep beats; 35 s of silence proves the sweep
                # thread dead, the watchdog lifts, and any later post
                # re-raises fresh (this arm takes _veil's fresh-veil
                # branch the moment _veil_lbl is gone - no extra
                # machinery for the re-raise)
                self._diag_veiled = True
                self._veil(_value, absolute=True, hold=35.0)
            if message == "camera_diag":
                # the sweep's verdict rides to the state loop, which
                # owns the toml write (camera_diag branch); the record
                # reaches the panes through the report resync, not a
                # second UI-side write
                self.monitor.events.put(("camera_diag", _value))
        if getattr(self, "_veil_lbl", None) is not None:
            # tk law: fresh children stack OVER the veil, and the
            # handlers above build exactly such children. This end-of-
            # drain raise lands in the same tick, before any paint -
            # a drain-born tile never gets one frame of daylight. The
            # head-of-tick raise in _tick_inner covers the draw-path
            # births; together they make the veil hold the top for its
            # whole lifetime, not just at birth (owner: items drawn
            # "above" the veil during the boot sweep).
            try:
                self._veil_lbl.tkraise()
            except Exception:
                pass


    def _update_status(self, now, slot):
        state = self.monitor.state
        if self.monitor.paused:
            state = "paused"
        # every write below is diffed (set_text / cget): each CTk label
        # and button is a software canvas and a no-op configure still
        # repaints it whole - this runs every tick, so unchanged text
        # must cost nothing (the 0.4 s tick repaint, profiled)
        chip = {"text": state}
        color = self.skin.chip(state)
        sink = getattr(self.monitor, "tray_sink", None)
        if sink is not None:
            sink(state)                      # the tray recolors on the
                                             # same truth the chip
                                             # paints (diff-guarded)
        if self.chip.cget("fg_color") != color:
            chip["fg_color"] = color
        if len(chip) == 1:
            set_text(self.chip, state)      # text-only: diff-guarded
        else:
            self.chip.configure(**chip)     # color moved: whole repaint
        idle = self._idle()
        age = "never" if slot is None else "%.1f s" % (now - slot[3])
        set_text(self.idle_label,
                 "idle %.0f s · frame %s old · %d seen"
                 % (idle, age, len(slot[1]) if slot else 0))
        set_text(self.pause_button,
                 "Resume" if self.monitor.paused else "Pause")
        paused_re = getattr(self.monitor, "re_off_paused", False)
        set_text(self.reoff_label,
                 "PAUSED (camera slipped?)" if paused_re else "on")
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
        from ... import display
        try:
            return display.get_idle_time()
        except Exception:
            return float("inf")

