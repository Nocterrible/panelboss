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
        except Exception:
            log.exception("camid pump failed; the loop goes on")
        try:
            self.after(120, self._pump)          # window gone mid-tick
        except Exception:
            pass

    def _build(self):
        hidden = set(self.app.cfg["camera"].get("hidden") or [])
        self._cands = [d for d in self._devs if d["instance"] not in hidden]
        self._pos = 0
        if self._cands:
            return self._start_step()
        self.idline.configure(text="no visible cameras")

    def _start_step(self):
        self._gen += 1                           # retires the old worker
        dev = self._cands[self._pos]
        inst = dev["instance"]
        idx = identity_map(self._devs, self.app._cams or []).get(inst)
        stored = (self.app.cfg["camera"].get("labels") or {}).get(inst, "")
        self.entry.delete(0, "end")
        self.entry.insert(0, stored or dev["name"])
        self.idline.configure(text="%d/%d  %s · ...%s · %s" % (
            self._pos + 1, len(self._cands), dev["name"], inst[-12:],
            dev["status"] or "?"))
        self.note.configure(text=step_warning(self._devs, dev) or (
            "index %s right now" % idx if idx is not None else
            "no openable index in the last scan - rescan first"))
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
            try:                                 # closed inside the open
                self.after(0, lambda: self.preview.configure(
                    image=None, text=BUSY))      # is a silent no-op
            except Exception:
                pass
            return
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
