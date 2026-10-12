"""The tick loop: UI refresh, tray-event drain, status and
blocker lines, teardown.
"""

from __future__ import annotations

import logging
import queue
import time

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
        super().destroy()


    def _tick_ui(self):
        if getattr(self, "_dying", False):
            return
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
        # veil watchdog: a veil that outlives its rebuild is a bricked
        # UI, and every failure path between veil() and unveil() would
        # otherwise be allowed to leave one up. The tick lifts it after
        # 3 s and confesses in the log - loud stop, not silent stuck.
        if getattr(self, "_veil_lbl", None) is not None \
                and time.time() - self._veil_since > 3.0:
            log.warning("ui: veil stuck past its rebuild window; lifting")
            self._unveil()
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
            if message == "assistant_truth":
                self._assistant_truth(_value)
            if message == "assistant_ui":
                self._assistant_ui(_value)
            if message == "startup":
                from ... import startup
                self._startup_sync(startup.enabled())
            if message == "cameras":
                self._apply_cameras(_value)


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

