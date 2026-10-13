"""Camera identity wizard: walk visible devices one by one with a live
preview, label them, hide the virtual ones.

Identity is the PnP InstanceId (camera.camera_devices): indexes drift
on replugs, so labels, hides, and BINDINGS ride the instance path. A
device's CURRENT index resolves in precedence order: the owner's bind
(camera.bindings - a human assertion that evicts guesses), the unique
name join (identity_map), then the relaxed preview fallback
(preview_map: one shared-name feed lights every twin, confessed).
Unclaimed open indexes still walk as synthetic idx:N rows so the
wizard covers every feed the picker shows - and every such row is
itself a bind candidate for the twin case.

Frames are BORROWED (v1, packet item 5): Camera opens directly on a
private worker - the monitor's framebox carries the duty mosaic, not
candidates, and driving the lease would rewrite the roster per cycle.
Duty eyes release between polls under boot_per_poll; the worker's
attempt has three honest endings in the note line: WARMING while the
serialized door is waited for, BUSY only where the open is proven
held, and a bounded no-frames verdict (NOSTREAM) that hands the
handle back instead of holding a device for a stare.

SIZE LAW: 720, justified, one window - the step machine and its borrowed-frame
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
from ._widgets import SkewCombo
from ... import camera

log = logging.getLogger("ui")

BUSY = ("the monitor is holding this camera - pause it from the tray "
        "and retry")
WARMING = ("opening this camera - the driver serializes opens behind the "
           "monitor's lease; frames appear when the door delivers")
NOSTREAM = ("opens, but serves no frames yet - the door may still be "
            "settling or the stream stays dark; try next and come back")
FRAME_BUDGET = 12.0  # seconds a step waits for its FIRST frame before
                     # confessing NOSTREAM and handing the handle back:
                     # an owner staring at "no live view" deserves a
                     # verdict, and an idle open is a device held for
                     # nobody (measured Oct 13: contended auto-door
                     # opens burn 18 s and some MF doors never sample)
DUP = ("two identical models share this name: the app cannot tell them "
       "apart. Wave at one camera and bind the device to the feed that "
       "moves - the bind is stored on the device, replugs and all.")


def identity_map(devs, found, bindings=None):
    """{instance: index}. The human answer FIRST of all: camera.bindings
    (the wizard's "this device is that feed") is applied LAST over the
    name join and EVICTS a guess standing on the same index - a bind
    whose instance is not in the PnP rows maps nothing (unplugged: the
    claim waits in the toml, exactly like a hidden instance waits).
    With no bind, a device maps only when its friendly name appears
    EXACTLY once in the PnP list and one scanned entry carries that
    name - uniqueness is the fallback clue; identical models now have
    the bind as their way, replacing the unplug-and-rerun dance."""
    hits = {}
    present = set()
    for d in devs or []:
        present.add(str(d["instance"]))
        hits.setdefault(str(d["name"]).lower(), []).append(d["instance"])
    out = {}
    for entry in found or []:
        got = hits.get(str(entry[3] or "").lower(), [])
        if len(got) == 1:
            out[got[0]] = entry[0]
    for inst, idx in (bindings or {}).items():
        try:                            # hand-edited toml is input
            idx = int(idx)              # like every other value here
        except (TypeError, ValueError):
            continue
        if str(inst) in present:
            for guess, gidx in list(out.items()):
                if gidx == idx and guess != str(inst):
                    del out[guess]      # the human evicts the guess
            out[str(inst)] = idx
    return out


def display_names(devs, found, cfg_camera):
    """index -> the name the UI may show: the user's label for the
    identity that index maps to (BIND first, honest unique-name join
    second), the scan's positional guess as fallback, NOTHING rather
    than a lie. The panes that caption cameras call this instead of
    trusting entry[3]."""
    ids = identity_map(devs, found, (cfg_camera or {}).get("bindings") or {})
    labels = (cfg_camera or {}).get("labels") or {}
    out = {idx: str(labels.get(inst, "") or "") for inst, idx in ids.items()}
    for entry in found or []:
        got = out.setdefault(entry[0], "")
        if not got and len(entry) > 3 and entry[3]:
            out[entry[0]] = str(entry[3])        # positional fallback:
    return out                                   # better than nothing,
                                                 # never more than truth


def bind_candidates(devs, found, bindings=None):
    """Open scanned indexes no identity claims (bind or join): the
    feeds only a human eye can assign - the wizard offers exactly
    these to "bind this device to a feed"."""
    owned = set(identity_map(devs, found, bindings).values())
    return [entry[0] for entry in found or []
            if len(entry) > 1 and entry[1] and entry[0] not in owned]


def preview_map(devs, found):
    """{instance: (index, shared)}: identity_map's pessimism RELAXED
    for the wizard's live view only. When a name is carried by several
    PnP rows but exactly ONE scanned index answers to it (the common
    shape: a twin-sensor module where only the color stream ever
    opens), that feed shows for every twin and the step line confesses
    the twins are indistinguishable. The picker and hidden filter keep
    the strict map - there a guess HIDES the wrong device, here it
    only lights the wrong preview, and the user sees which it is.
    Two+ indexes for one name: ordinal order is a coin flip, nothing
    maps (the UAT gap this closes: identical models made a streaming
    physical cam untestable in the wizard)."""
    rows = {}
    for d in devs:
        rows.setdefault(d["name"].lower(), []).append(d["instance"])
    idxs = {}
    for entry in found or []:
        idxs.setdefault(str(entry[3] or "").lower(), []).append(entry[0])
    out = {}
    for name, insts in rows.items():
        got = idxs.get(name, [])
        if len(got) == 1:
            for inst in insts:
                out[inst] = (got[0], len(insts) > 1)
    return out


def all_rows(devs, found, bindings=None):
    """PnP rows + a synthetic row per OPEN scanned index that no PnP
    row claimed: the wizard walks what the picker shows (the owner's
    UAT law - identify gives the add pane its names and hides, so it
    must see EVERYTHING the add pane can open). A claimed index is one
    identity_map or preview_map resolved; the synthetic remainder keys
    policy on "idx:N" - drifts on replug renumbering, the honest
    documented twin of the unplug-and-rerun pattern for identical
    models. The DSHOW/MF ordinal->instance oracle that would name
    these properly lives in panelboss/dshow.py's ledger note: this
    box registers no SystemDeviceEnum class (cv2 carries its own), so
    until the enumeration route is cracked, synthetic rows are the
    truthful stand-in - preview works, labels persist, no positional
    name lie rides them."""
    ids = identity_map(devs, found, bindings)
    mapped = set(ids.values())
    mapped |= {got[0] for got in preview_map(devs, found).values()}
    try:
        from ... import dshow              # the ordinal oracle: {} on a
        truth = dshow.index_instances()    # box without the registered
    except Exception:                      # SystemDeviceEnum class
        truth = {}                         # (the dev desk today)
    rows = [dict(d) for d in (devs or [])]   # copies: the idx attach
    for row in rows:                          # below must not leak
        idx = ids.get(row["instance"])        # back into _devs
        if idx is not None:
            row["idx"] = idx
    for entry in found or []:
        if len(entry) < 2 or not entry[1] or entry[0] in mapped:
            continue
        nm = str(entry[3]).strip() if len(entry) > 3 and entry[3] else ""
        inst = truth.get(entry[0])
        rows.append({"name": nm or ("camera %d" % entry[0]),
                     "instance": inst or ("idx:%d" % entry[0]),
                     "status": "OK",
                     # UNKNOWN is not SOFTWARE: only a resolved
                     # non-USB instance may hide a synthetic row by
                     # default; an unresolved one shows, previews and
                     # waits for the owner's verdict (that IS the
                     # wizard's job)
                     "virtual": bool(inst) and camera.is_virtual_camera(inst),
                     "idx": entry[0]})
    return rows


def hidden_indices(devs, found, hidden, bindings=None):
    """Scan indexes to suppress in the picker and menu lines. An
    unmappable hidden device suppresses nothing - it stays visible
    here, so the wizard remains its way out. The "idx:N" synthetic
    keys (all_rows) hide by index directly: that IS their whole
    identity claim."""
    hidden = list(hidden or [])
    out = {int(str(i)[4:]) for i in hidden
           if str(i).startswith("idx:") and str(i)[4:].isdigit()}
    out |= {idx for inst, idx in identity_map(devs, found, bindings).items()
            if inst in set(hidden)}
    return out


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
        self._busy_note = None                   # the step text BUSY
                                                 # displaced, restored
        self._held = False                       # by the first frame;
                                                 # BUSY (held) vs
        self._nostream = False                   # WARMING (door) is
                                                 # the corpse arm's
                                                 # distinction
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
        # the owner's UAT call: software filters (Broadcast/OBS/DroidCam)
        # are nobody's default pick - glass first, tick to reveal. The
        # reveal is session-only on purpose: a permanent per-device hide
        # already exists (the hide button writes the policy row).
        self._show_virtual = False
        self._vbox = ctk.CTkCheckBox(
            self, text="show virtual cameras", font=self.skin.font(10),
            command=self._toggle_virtual, checkbox_width=14,
            checkbox_height=14, fg_color=self.skin.accent,
            hover_color=self.skin.accent_hover,
            border_color=self.skin.border_raised,
            text_color=self.skin.text,
            text_color_disabled=self.skin.txt3)
        self._vbox.pack(anchor="w", padx=theme.S_SECTION,
                        pady=(theme.S_ROW, 0))
        # the twin answer (owner UAT): the app cannot tell identical
        # models apart, the owner's eyes can. Shown only on steps with
        # no index and at least one unowned open feed; picking a feed
        # and saving stores instance -> index (camera.bindings), the
        # one identity clue that outranks every guess.
        self._bind_map = {}
        self.bind_menu = SkewCombo(self, values=[], width=220,
                                   **self.skin.menu_style())
        self.bind_menu.set("bind this device to a feed")
        self._bind_pady = (0, theme.S_ROW)
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
                if self._busy_note is not None:
                    # the first real frame retires the BUSY line -
                    # the note goes back to whatever the step said
                    self.note.configure(text=self._busy_note)
                    self._busy_note = None
                self._busy = False
                self._show(frame)
            elif self._nostream:
                # the bounded attempt confessed: the worker already
                # handed the handle back (no device held for a stare);
                # the note owns the verdict, the preview keeps its
                # harmless still per the CTk doctrine
                self._nostream = False
                self._busy = False
                self._held = False
                self._busy_note = None          # a verdict does not
                self.note.configure(text=NOSTREAM)  # ride a restore
            elif self._busy and self._busy_note is None:
                # the state line, marshaled: the worker only flips the
                # flag; this tick is the main-thread render (no naked
                # self.after from a worker anywhere in this file).
                # RENDERED IN THE NOTE LINE, not the preview label:
                # CTkLabel's image=None branch leaves the inner label
                # holding a dangling pyimage NAME after dropping the
                # reference (measured, Oct 13: frame -> BUSY -> frame
                # dies in the text-before-image configure order of
                # ctk_label.py:238-253), and the UAT found the wizard
                # preview frozen exactly that way. A configured label
                # never goes back to image=None here; the note is the
                # state channel this wizard already owns. WARMING
                # while the door is waited for, BUSY only when the
                # corpse arm proved the monitor holds the device.
                self._busy_note = self.note.cget("text")
                self.note.configure(text=BUSY if self._held else WARMING)
        except Exception:
            log.exception("camid pump failed; the loop goes on")
        try:
            self.after(120, self._pump)          # window gone mid-tick
        except Exception:
            pass

    def _candidates(self, devs):
        """Visible steps + the honest counts of what the filter skipped:
        hidden never (a hide is a policy row, not a candidate drop),
        unhealthy (PnP Status not OK) never earns a step or a wasted
        open, and SOFTWARE rows stay hidden unless the checkbox says
        otherwise - the owner's call, GPU filters are nobody's default
        camera. The verdict rides the row's "virtual" flag, not a
        re-derivation here: rows from camera_devices carry the
        namespace classification, all_rows encodes the UNKNOWN-is-not-
        -software law for synthetic idx: rows on exactly this channel
        (re-classifying "idx:2" by namespace here would hide the owner's
        physical cam2 behind a checkbox - the UAT smoke caught this
        exact shape). PnP-sourced rows always carry the key; a row from
        any other caller without it falls back to the namespace.
        Filtering is candidate-list-only - a skipped device stays
        labelable through the checkbox or the unhide path, never
        policy-destroyed."""
        hidden = set(self.app.cfg["camera"].get("hidden") or [])
        show_virtual = getattr(self, "_show_virtual", False)
        unhealthy = vhidden = 0
        cands = []
        for d in devs or []:
            if d["instance"] in hidden:
                continue
            if not (str(d.get("status") or "OK").lower() == "ok"):
                unhealthy += 1
                continue
            soft = d.get("virtual")
            if soft is None:
                soft = camera.is_virtual_camera(d["instance"])
            if not show_virtual and soft:
                vhidden += 1
                continue
            cands.append(d)
        return cands, unhealthy, vhidden

    def _skip_note(self):
        """The confession suffix: whatever the candidate filter dropped
        rides the note line, joined on the separator the wizard
        already uses."""
        parts = []
        if getattr(self, "_skipped", 0):
            parts.append("%d unhealthy camera(s) skipped (PnP status)"
                         % self._skipped)
        if getattr(self, "_vhidden", 0):
            parts.append("%d virtual camera(s) hidden (software)"
                         % self._vhidden)
        return ("  ·  " + "  ·  ".join(parts)) if parts else ""

    def _toggle_virtual(self):
        """Session-only reveal (no config churn): tick, the software
        rows join the steps; untick, they retreat. Before the first
        build the pump picks the state up on its own tick."""
        self._show_virtual = bool(self._vbox.get())
        if not self._built or not self._devs:
            return
        self._cands, self._skipped, self._vhidden = self._candidates(
            all_rows(self._devs, self.app._cams or [],
                     self.app.cfg["camera"].get("bindings") or {}))
        self._pos = 0
        if self._cands:
            self._start_step()
        else:
            self.idline.configure(text="no visible cameras")

    def _build(self):
        self._cands, self._skipped, self._vhidden = self._candidates(
            all_rows(self._devs, self.app._cams or [],
                     self.app.cfg["camera"].get("bindings") or {}))
        self._pos = 0
        if self._cands:
            return self._start_step()
        self.idline.configure(text="no visible cameras")
        if self._skipped or self._vhidden:
            self.note.configure(text=self._skip_note().strip(" ·"))

    def _start_step(self):
        self._gen += 1                           # retires the old worker
        self._busy = True                        # the WARMING line
        self._held = False                       # stands from tick one:
        self._nostream = False                   # an attempt without a
        self._frame = None                       # first frame ends in
        self._busy_note = None                   # a verdict, never in
                                                 # silence - and a note
                                                 # captured mid-WARMING
                                                 # must not ride onto
                                                 # the next step's line
        dev = self._cands[self._pos]             # any busy line the old
        inst = dev["instance"]                   # worker may have queued
        idx = dev.get("idx")             # all_rows answered this once:
        shared = False                 # bind, join, or the row's own
        if idx is None:                  # synthetic index - the step
            # the strict map refused (name collision): the relaxed map  # machine must not
            # may still know the one feed answering to this name       # re-derive
            got = preview_map(self._devs, self.app._cams or []).get(inst)
            if got is not None:
                idx, shared = got
        # the bind menu: only for a row with no index (and not itself
        # an index-keyed synthetic), only over feeds nothing claims
        bindings = self.app.cfg["camera"].get("bindings") or {}
        opts = (bind_candidates(self._devs, self.app._cams or [],
                                bindings)
                if idx is None and not str(inst).startswith("idx:")
                else [])
        if opts:
            self._bind_map = {("bind to feed %d" % n): n for n in opts}
            self.bind_menu.configure(values=list(self._bind_map))
            self.bind_menu.set("bind this device to a feed")
            self.bind_menu.pack(after=self._vbox, anchor="w",
                                padx=theme.S_SECTION, pady=self._bind_pady)
        else:
            self._bind_map = {}
            self.bind_menu.pack_forget()
        stored = (self.app.cfg["camera"].get("labels") or {}).get(inst, "")
        self.entry.delete(0, "end")
        self.entry.insert(0, stored or dev["name"])
        self.idline.configure(text="%d/%d  %s · ...%s · %s" % (
            self._pos + 1, len(self._cands), dev["name"], inst[-12:],
            dev["status"] or "?"))
        if shared:
            note = ("index %s right now (name shared with an identical"
                    " model: every twin shows this one feed)" % idx)
        else:
            note = step_warning(self._devs, dev) or (
                "index %s right now" % idx if idx is not None else
                "no openable index in the last scan - rescan first")
        note += self._skip_note()
        self.note.configure(text=note)
        if idx is None:
            # no worker is coming for this step: the busy flag goes
            # down by hand, or WARMING would lie forever on a step
            # that never attempts an open (the same CTkLabel
            # image=None landmine as the pump's BUSY branch keeps
            # the preview on its last harmless still here)
            self._busy = False
            return self.note.configure(text=note + "  ·  no live view")
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
                self._held = self._busy = True   # step retired) must
            return                               # not queue a BUSY
        try:
            give_up = time.monotonic() + FRAME_BUDGET
            got = False                          # worker-local first-
            while (not self._dying and self._gen == gen  # frame latch:
                   and (got or time.monotonic() < give_up)):  # once ONE
                frame = cam.read(timeout=1, screen=0)  # frame lands,
                if frame is not None:                    # the budget is
                    got = True                           # retired - the
                    self._frame = frame                  # pump drains
        finally:                                       # the mailbox,
            cam.release()                              # a latch beats
            if self._gen == gen:                       # a mailbox read
                self._busy = False
                if not got:
                    self._nostream = True        # the pump confesses it

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
        if dev is None:
            return
        payload = {"instance": dev["instance"], "label": self.entry.get()}
        pick = self.bind_menu.get() if self._bind_map else None
        if pick in self._bind_map:
            payload["bind"] = self._bind_map[pick]
        self.app.monitor.events.put(("camera_identity", payload))
        self.note.configure(text="saved - the loop writes the toml")
        if "bind" in payload and not self._ladder_busy:
            # the row flip (device lights, synthetic placeholder
            # retires) rides the SAME re-read ladder the unhide uses:
            # the loop owns the toml turn
            self._ladder_start()

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
        self._cands, self._skipped, self._vhidden = self._candidates(
            all_rows(self._devs, self.app._cams or [],
                     self.app.cfg["camera"].get("bindings") or {}))
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
