"""Camera identity wizard: walk visible devices one by one with a live
preview, label them, hide the virtual ones.

Identity is the PnP InstanceId (camera.camera_devices): indexes drift
on replugs, so labels and hidden ride the instance path. A device's
CURRENT index is annotated from the app's own last scan (app._cams)
matched by UNIQUE name - two identical models share one name and
neither maps; the step line says so instead of pretending.

Frames are BORROWED (v1, packet item 5): Camera opens directly on a
private worker - the monitor's framebox carries the duty mosaic, not
candidates, and driving the lease would rewrite the roster per cycle.
Duty eyes release between polls under boot_per_poll; a still-busy
device earns the honest busy line.

SIZE LAW: 414, justified, one window - the step machine and its borrowed-frame
worker share one _gen/_dying lifecycle, and splitting the widget
shell from the identity core would scatter a protocol debugged by
reading top to bottom (the importable helpers the picker filter reuses
stay module-level anyway).
"""

from __future__ import annotations

import logging
import threading
import time

import cv2
import customtkinter as ctk
from PIL import Image

from .. import theme
from ... import camera

log = logging.getLogger("ui")

BUSY = ("the monitor is holding this camera - pause it from the tray "
        "and retry")
DUP = ("two identical models share this name: the app cannot tell them "
       "apart. Unplug one and rerun this wizard to pin the other.")


def identity_map(devs, found):
    """{instance: index}: a device maps only when its friendly name
    appears EXACTLY once in the PnP list and one scanned entry carries
    that name - uniqueness is the only honest clue (the documented
    limit: identical models need the wizard re-run after a replug)."""
    hits = {}
    for d in devs:
        hits.setdefault(d["name"].lower(), []).append(d["instance"])
    out = {}
    for entry in found or []:
        got = hits.get(str(entry[3] or "").lower(), [])
        if len(got) == 1:
            out[got[0]] = entry[0]
    return out


def hidden_indices(devs, found, hidden):
    """Scan indexes to suppress in the picker and menu lines. An
    unmappable hidden device suppresses nothing - it stays visible
    here, so the wizard remains its way out."""
    return {idx for inst, idx in identity_map(devs, found).items()
            if inst in set(hidden or [])}


def step_warning(devs, dev):
    return DUP if sum(1 for d in devs if d["name"] == dev["name"]) > 1 \
        else ""


class IdentifyWindow(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(master=app, fg_color=app.skin.panel)
        self.app, self.skin = app, app.skin
        self.title("identify cameras")
        self.geometry("480x560")
        self._dying, self._built = False, False
        self._frame, self._img, self._gen = None, None, 0
        self._devs, self._cands, self._pos = [], [], 0
        self._busy = False                       # worker -> pump, the
        # ONLY marshaling path (no naked self.after from workers):
        self._ladder_busy = False                # the unhide recheck
        self._ladder_left, self._ladder_prev = 0, None   # ladder state
        self._fetched = False                    # a fresh count to beat
        self._deadline = time.time() + 30        # the first scan may fail
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=theme.S_SECTION, pady=(theme.S_ROW, 0))
        self._label(head, 15, "bold", text="identify cameras").pack(
            side="left")
        ctk.CTkButton(head, text="done", width=70, command=self.destroy,
                      **self.skin.secondary()).pack(side="right")
        self.note = self._label(self, 10, wraplength=440, anchor="w")
        self.note.configure(text="scanning cameras...")
        self.note.pack(anchor="w", padx=theme.S_SECTION, pady=theme.S_FIELD)
        self.preview = self._label(self, 12)
        self.preview.configure(text="no live view")
        self.preview.pack(pady=theme.S_ROW)
        self.idline = self._label(self, 11, tier="text")
        self.idline.pack(anchor="w", padx=theme.S_SECTION)
        self.entry = ctk.CTkEntry(self, font=self.skin.font(12))
        self.entry.pack(fill="x", padx=theme.S_SECTION, pady=theme.S_FIELD)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=theme.S_SECTION)
        ctk.CTkButton(row, text="save", width=80, command=self._save,
                      **self.skin.primary()).pack(side="left")
        ctk.CTkButton(row, text="hide this device", width=140,
                      command=self._hide,
                      **self.skin.secondary()).pack(side="left",
                                                    padx=theme.S_FIELD)
        ctk.CTkButton(row, text="next", width=70, command=self._next,
                      **self.skin.secondary()).pack(side="right")
        ctk.CTkButton(row, text="unhide all", width=100,
                      command=self._unhide_all,
                      **self.skin.secondary()).pack(side="right",
                                                    padx=theme.S_FIELD)
        if not app._cams:
            app._scan_cameras()                  # fills app._cams/_devs
        threading.Thread(target=self._gather, daemon=True,
                         name="camid-gather").start()
        self.after(120, self._pump)
        try:                                     # the OverridesWindow
            self.transient(app)                  # discipline: transient
        except Exception:                        # + the topmost-blink
            pass                                 # wins the focus round
        self.after(30, self._claim_focus)

    def _label(self, parent, size, weight="", tier="sub", **kw):
        font = self.skin.font(size, weight) if weight else self.skin.font(size)
        return ctk.CTkLabel(parent, font=font, justify="left",
                            **self.skin.text_style(tier), **kw)

    def _claim_focus(self):                      # the trick that works,
        try:                                     # copied from overrides
            self.attributes("-topmost", True)
            self.lift()
            self.focus_force()
            self.after(140, self._drop_topmost)
        except Exception:
            pass

    def _drop_topmost(self):
        try:
            self.attributes("-topmost", False)
        except Exception:
            pass

    # ------------------------------------------------------------- flow --
    def _gather(self):
        try:
            self._devs = camera.camera_devices()
        except Exception:
            log.exception("identity query failed")
            self._devs = []

    def _gather_reload(self):
        # the _gather idiom on the reload path: the app's own last scan
        # is empty and the powershell query may not land on the tk
        # thread; a later ladder reload (and the pump's deadline
        # build) pick up the answer
        try:
            setattr(self.app, "_devs", camera.camera_devices())
        except Exception:
            log.exception("identity query failed")
            setattr(self.app, "_devs", [])

    def _pump(self):
        if self._dying:
            return
        try:
            if not self._built and self._devs and (
                    self.app._cams is not None or time.time() > self._deadline):
                self._built = True
                self._build()
            frame, self._frame = self._frame, None
            if frame is not None:
                self._show(frame)
            elif self._busy:
                # the BUSY line, marshaled: the worker only flips the
                # flag; this tick is the main-thread render (no naked
                # self.after from a worker anywhere in this file)
                self.preview.configure(image=None, text=BUSY)
        except Exception:
            log.exception("camid pump failed; the loop goes on")
        try:
            self.after(120, self._pump)          # window gone mid-tick
        except Exception:
            pass

    def _candidates(self, devs):
        """Visible steps + the honest count of what the filter skipped:
        hidden never (a hide is a policy row, not a candidate drop) and
        unhealthy (PnP Status not OK) never earns a step or a wasted
        open. Filtering is candidate-list-only - an unhealthy device
        stays labelable through the unhide path, never policy-destroyed."""
        hidden = set(self.app.cfg["camera"].get("hidden") or [])
        unhealthy = 0
        cands = []
        for d in devs or []:
            if d["instance"] in hidden:
                continue
            if not (str(d.get("status") or "OK").lower() == "ok"):
                unhealthy += 1
                continue
            cands.append(d)
        return cands, unhealthy

    def _build(self):
        self._cands, self._skipped = self._candidates(self._devs)
        self._pos = 0
        if self._cands:
            return self._start_step()
        self.idline.configure(text="no visible cameras")
        if self._skipped:
            self.note.configure(text="%d unhealthy camera(s) skipped (PnP status)" % self._skipped)

    def _start_step(self):
        self._gen += 1                           # retires the old worker
        self._busy = False                       # a new step replaces
        dev = self._cands[self._pos]             # any busy line the old
        inst = dev["instance"]                   # worker may have queued
        idx = identity_map(self._devs, self.app._cams or []).get(inst)
        stored = (self.app.cfg["camera"].get("labels") or {}).get(inst, "")
        self.entry.delete(0, "end")
        self.entry.insert(0, stored or dev["name"])
        self.idline.configure(text="%d/%d  %s · ...%s · %s" % (
            self._pos + 1, len(self._cands), dev["name"], inst[-12:],
            dev["status"] or "?"))
        note = step_warning(self._devs, dev) or (
            "index %s right now" % idx if idx is not None else
            "no openable index in the last scan - rescan first")
        if getattr(self, "_skipped", 0):
            note += "  ·  %d unhealthy camera(s) skipped (PnP status)" \
                % self._skipped
        self.note.configure(text=note)
        if idx is None:
            return self.preview.configure(image=None, text="no live view")
        threading.Thread(target=self._work, daemon=True,
                         args=(self._gen, idx), name="camid-view").start()

    def _work(self, gen, idx):
        cam_cfg = self.app.cfg["camera"]
        try:
            cam = camera.Camera(index=idx, warmup=2,
                                width=int(cam_cfg.get("width", 1280)),
                                height=int(cam_cfg.get("height", 720)))
        except Exception:
            cam = None
        if cam is None or not cam.is_open():
            if cam is not None:
                cam.release()
            if self._gen == gen:                 # a stale worker (its
                self._busy = True                # step retired) must
            return                               # not queue a BUSY
        try:
            while not self._dying and self._gen == gen:
                frame = cam.read(timeout=1, screen=0)
                if frame is not None:
                    self._frame = frame
        finally:
            cam.release()

    def _show(self, frame):                      # the _draw resize, shared
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        width = int(self.app.cfg["ui"]["preview_width"])
        height = max(int(width * frame.shape[0] / max(frame.shape[1], 1)), 1)
        image = Image.fromarray(rgb).resize((width, height))
        self._img = ctk.CTkImage(light_image=image, dark_image=image,
                                 size=(width, height))
        self.preview.configure(image=self._img, text="")

    # ---------------------------------------------------------- buttons --
    def _ident(self):
        return self._cands[self._pos] if self._cands else None

    def _save(self):
        dev = self._ident()
        if dev is not None:
            self.app.monitor.events.put(("camera_identity", {
                "instance": dev["instance"], "label": self.entry.get()}))
            self.note.configure(text="saved - the loop writes the toml")

    def _hide(self):
        dev = self._ident()
        if dev is None:
            return
        self.app.monitor.events.put(("camera_identity", {
            "instance": dev["instance"], "hide": True}))
        self._cands.pop(self._pos)
        self._pos %= max(len(self._cands), 1)
        if not self._cands:
            return self.idline.configure(text="nothing left visible")
        self._start_step()

    def _unhide_all(self):
        """The way OUT (gate finding 5): hiding is a door, not a
        cell. The step line counts the tenants so the verb cannot
        be a blind wipe. The reload is DEFERRED because the loop
        owns the toml and applies events on its own turn - reading
        the cfg back synchronously would see the pre-unhide world
        and rebuild the very list we came to free. A single deferred
        call used to ASSUME that turn had drained by then; a tick
        blocked on a slow open (a virtual camera takes ~16 s) drains
        later and the reload read stale hidden, ending at "nothing
        left visible" with no re-trigger. So the reload rides a
        BOUNDED recheck ladder: each reload compares the visible
        candidate count to the previous one - unchanged and attempts
        remain, reschedule (500 ms spacing, cap 8, ~4 s); changed,
        the reload stands and the ladder stops. One ladder per view:
        a click mid-ladder enqueues its events and the running
        ladder re-reads them, no second ladder piles up."""
        hidden = self.app.cfg["camera"].get("hidden") or []
        if not hidden:
            self.note.configure(text="nothing is hidden")
            return
        for inst in list(hidden):
            self.app.monitor.events.put(("camera_identity", {
                "instance": inst, "unhide": True}))
        self.note.configure(text="unhidden %d device(s)" % len(hidden))
        if not self._ladder_busy:
            # one ladder per view: the running ladder re-reads the cfg
            # (its events are already queued), a second click must not
            # schedule a second ladder behind the first
            self._ladder_start()

    def _ladder_start(self):
        self._ladder_busy = True                 # one in-flight ladder
        self._ladder_left = 8                    # per view: a second
        self._ladder_prev = len(self._cands)     # click re-runs on the
        self.after(250, self._reload_steps)      # FIRST (the stale
                                                 # count to beat), never
                                                 # piles up

    def _ladder_stop(self):
        self._ladder_busy = False
        self._ladder_left = 0
        self._ladder_prev = None

    def _ladder_check(self):
        """One step of the unhide recheck: the reload counts as
        STANDING when the visible-candidate count CHANGED (the drain
        landed) or when the attempts are spent; only an UNCHANGED
        count reschedules the next reload at 500 ms, capped, so a
        blocked state loop is waited for but never shadowed by an
        infinite pump. A reload that rode the off-thread PnP fetch has
        no fresh count to compare yet (the branch left _cands stale):
        it reschedules on the remaining budget alone. Each reload
        does its own normal work - the ladder only decides the next
        500 ms."""
        if not self._ladder_busy:
            return
        if self._fetched:                        # the full path ran:
            self._fetched = False                # a CHANGED count is
            if len(self._cands) != self._ladder_prev:   # the drain -
                self._ladder_stop()              # the reload stands
                return
        if self._ladder_left <= 0:
            self._ladder_stop()                  # cap spent: the ride
            return                               # ends honest, bounded
        self._ladder_prev = len(self._cands)     # unchanged: compare
        self._ladder_left -= 1                   # the next reload to
        self.after(500, self._reload_steps)      # THIS count

    def _reload_steps(self):
        if self._dying:
            return                               # destroyed mid-ladder
        self._fetched = False
        if not getattr(self.app, "_devs", None):
            # the first reload may not see the app's own last scan: the
            # PnP query is a ~10 s powershell round trip and must not
            # run on the tk thread (it froze the wizard mid-unhide).
            # Route it through the worker idiom _gather uses; the pump's
            # next tick sees the result and this step only keeps the
            # ladder alive.
            threading.Thread(target=self._gather_reload, daemon=True,
                             name="camid-reload").start()
            self._ladder_check()
            return
        self._devs = self.app._devs
        self._cands, self._skipped = self._candidates(self._devs)
        self._pos = 0
        if self._cands:
            self._start_step()
        else:
            self.idline.configure(text="nothing left visible")
        self._fetched = True                     # the comparison to
        self._ladder_check()                     # beat is a FRESH one

    def _next(self):
        if self._cands:
            self._pos = (self._pos + 1) % len(self._cands)
            self._start_step()

    def destroy(self):
        self._dying = True
        self._gen += 1
        super().destroy()


def open_identify(app):
    """One manager window; opening it again just lifts the old one (the
    _show_overrides pattern the overrides button follows)."""
    win = getattr(app, "_camid_win", None)
    if win is not None:
        try:
            if win.winfo_exists():
                win._claim_focus()
                return win
        except Exception:
            pass
    app._camid_win = IdentifyWindow(app)
    return app._camid_win
