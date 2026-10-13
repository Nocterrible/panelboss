"""The camera setup screen (redesign stage 2): ONE path from rescan
or first-run to named, hidden, photographed cameras.

The owner's design, in module shape: the screen opens every index
(consent was given - the switch brought you here), takes ONE frame
per feed as a snapshot (black frames are an answer: a stream that
serves dark serves real pixels - the Kiyo law the wizard learned),
and spawns a card per feed AS IT REPORTS: header (index, name,
device detail), snapshot, a rename entry (names are optional; the
DIFF-ONLY law from d4000b1 - a label travels only when the entry
differs from its prefill), and a "hide this camera" checkbox. Feeds
that timed out still get cards - preview area says "request timed
out - non-responsive", the box arrives CHECKED (the pre-mark: an
untouched card hides the dark feed; unchecking means shown, and
shown is sticky per amendment 2). IR bridge groups are first-class
rows here - the sentinel seat finally gets its card, header
"hello IR · bridge group <G>", snapshot through the same
HelloIrCamera adapter the duty engine uses.

Workers post results through a queue.Queue and the pump (root.after)
drains - no widget is ever touched from a worker thread (the standing
marshaling law). The close path is the destroy law from birth:
withdraw + after(0, destroy); the X and OK ride it, and OK's verbs
are the EXISTING identity events (label/hide/show, instance or
"idx:N" keys) plus ("camera_enabled", True) - the state loop still
owns every toml byte.

SIZE LAW: ~370 at birth, and the split seam is named: everything
above the class line (rows_from, card_spec, ok_verbs) is the pure
data contract - importable, testable without a display (camdiag
section 9); the SetupWindow class is the widget shell. If the shell
grows dialog-section machinery, it splits by section the way
_camedit did from _preview, not by helper archaeology.
"""

import logging
import queue
import threading

import cv2
import customtkinter as ctk
from PIL import Image

from .. import theme
from . import _camid
from ... import camera

log = logging.getLogger("ui")

FRAME_BUDGET = 15.0        # seconds a feed gets for its FIRST frame
SNAP_W, SNAP_H = 220, 140  # the card's photo box: 8 seats at ~400px


# ------------------------------------------------------------- pure core --
def rows_from(devs, enumerated, ir_names, cfg_camera):
    """The screen's seat list: one row per enumerated index (opened
    or not - a dead index still earns a timed-out card, the owner
    must SEE the seat that failed), plus one row per bridge group.
    Returns (rows, n): rows are dicts the worker walks; n is the
    progress denominator, and the scan ceiling (0..7) is the same
    bound the probe worker already keeps."""
    cfg_camera = cfg_camera or {}
    labels = cfg_camera.get("labels") or {}
    ids = _camid.identity_map(devs, enumerated,
                              cfg_camera.get("bindings") or {})
    joined = {}                            # index -> instance, or
    for inst, idx in ids.items():          # None when a name was
        if idx in joined:                  # claimed by twins (the
            joined[idx] = None             # ambiguous join resolves
        else:                              # to nothing honest)
            joined[idx] = inst
    counts = {}
    for d in devs or []:
        n = str(d["name"]).strip()
        if n:
            counts[n] = counts.get(n, 0) + 1
    rows = []
    for entry in enumerated or []:
        index, opened = entry[0], entry[1]
        width = entry[2] if len(entry) > 2 else 0.0
        scan_name = str(entry[3]).strip() if len(entry) > 3 and entry[3] \
            else ""
        inst = joined.get(index)
        detail = ""
        name = labels.get(inst or "", "") if inst else ""
        if not name and scan_name:
            name = scan_name
        if inst is not None:               # unambiguous join: the
            detail = str(inst).split("\\")[-1]   # device tail rides
        elif scan_name and counts.get(scan_name, 0) == 1:
            detail = scan_name             # unique friendly name
        rows.append({"idx": index, "group": None,
                     "key": inst if inst is not None
                          else ("idx:%d" % index),
                     "name": name or ("camera %d" % index),
                     "detail": detail,
                     "opened": bool(opened), "width": float(width)})
    for g in ir_names or []:
        rows.append({"idx": None, "group": str(g),
                     "key": "ir:" + str(g),
                     "name": labels.get("ir:" + str(g), "") or str(g),
                     "detail": "bridge group %s" % g,
                     "opened": True, "width": 0.0})
    return rows, len(rows)


def card_spec(row, timed_out):
    """The pure verdict behind every card (tested offline): key the
    identity verbs ride, the entry prefill (a saved label wins over
    the display name - the diff-only rule then sends only what the
    owner re-typed), the hide checkbox (a timed-out feed arrives
    CHECKED: the box was dark, the dark default is hidden, and
    unchecking it is the owner OVERRIDING with a shown-sticky verb),
    and the header line."""
    head = "index %s" % row["idx"] if row["idx"] is not None \
        else "hello IR"
    if row["detail"]:
        head += "  ·  %s" % row["detail"]
    elif row["idx"] is not None and not row.get("opened", True):
        head += "  ·  never opened"
    return {"key": row["key"], "prefill": row["name"],
            "checked": bool(timed_out), "header": head}


def ok_verbs(cards):
    """The events OK posts, as a pure function over the card states
    [(key, prefill, text, checked, started_checked)] - the diff-only
    law and the hide/show asymmetry, importable and testable. An
    unchanged entry says NOTHING (the d4000b1 finding: a manufactured
    prefill must not poison the bind migration); a re-typed one is a
    label; hide True is a hide, and hide False on a card that STARTED
    checked (a dark feed the owner kept anyway) is the shown verb -
    stickiness per amendment 2. A card that started unchecked and
    stayed so is the owner's silence, which is not a claim."""
    out = []
    for key, prefill, text, checked, started_checked in cards:
        verb = {"instance": key}
        if text != prefill:
            verb["label"] = text
        if checked:
            verb["hide"] = True
        elif started_checked:
            verb["show"] = True
        if len(verb) > 1:
            out.append(("camera_identity", verb))
    return out


# --------------------------------------------------------------- window ---
class SetupWindow(ctk.CTkToplevel):
    """The setup screen. Parented to the (hidden) window root like the
    wizard it replaces: transient, the topmost-blink focus claim, and
    the destroy law from birth - the X and OK both withdraw-then-
    schedule, never destroying under a live callback."""

    def __init__(self, app):
        super().__init__(master=app, fg_color=app.skin.panel)
        self.app, self.skin = app, app.skin
        self.title("camera setup")
        self.geometry("480x600")
        self._dying = False
        self._cards = []                           # dicts: key, prefill,
        self._results = queue.Queue()              #   entry, var, started
        self._done = 0
        self._total = 0
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=theme.S_SECTION, pady=(theme.S_ROW, 0))
        ctk.CTkLabel(head, text="camera setup",
                     font=self.skin.font(15, "bold"),
                     **self.skin.text_style()).pack(side="left")
        # the finish row stays PACKED the whole life and toggles its
        # CHILDREN's visibility: a conditional pack() here would land
        # at the BOTTOM of the pack order, below the veil - the wrong
        # order for the one frame that must read instantly
        self._finish = ctk.CTkFrame(self, fg_color="transparent")
        self._finish.pack(side="bottom", fill="x", padx=theme.S_SECTION,
                          pady=(theme.S_FIELD, theme.S_ROW))
        self.ok_button = ctk.CTkButton(self._finish, text="OK", width=90,
                                       command=self._ok,
                                       **self.skin.primary())
        self.rerun_note = ctk.CTkLabel(
            self._finish,
            text="you can rerun this setup from the rescan button "
                 "any time",
            font=self.skin.font(10), **self.skin.text_style("sub"))
        self.veil = ctk.CTkLabel(self, text="testing cameras...",
                                 font=self.skin.font(13, "bold"),
                                 **self.skin.text_style("sub"))
        self.veil.pack(side="bottom", pady=theme.S_ROW)
        self._host = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._host.pack(fill="both", expand=True,
                        padx=theme.S_SECTION, pady=(0, theme.S_FIELD))
        threading.Thread(target=self._gather, daemon=True,
                         name="assign-gather").start()
        self.after(60, self._pump)
        try:
            self.transient(app)
        except Exception:
            pass
        self.after(30, self._claim_focus)
        self.protocol("WM_DELETE_WINDOW", self._close)

    # ------------------------------------------------------------- worker --
    def _gather(self):
        """Enumerate + one snapshot per row, off the tk thread. The
        opens serialize on the engine's own _open_lock (device-tree
        law); what the threads OVERLAP are the frame budgets (the
        amendment-1 doctrine, inherited whole)."""
        import concurrent.futures as cf
        try:
            devs = camera.camera_devices()   # never raises: [] on a
        except Exception:                    # dead PnP door (proven
            devs = []                        # in camid section 1)
        cfg_cam = self.app.cfg["camera"]
        try:
            enumerated = camera.enumerate_cameras()
        except Exception:
            log.exception("setup: enumerate failed")
            enumerated = []
        rows, self._total = rows_from(devs, enumerated,
                                      camera.hello_ir_names(), cfg_cam)

        def one(row):
            # the both-ends discipline of the wave's probe: the card
            # spawns on the SETTLE, so the k-of-n never lies
            cam = None
            try:
                if row["group"] is not None:
                    cam = camera.HelloIrCamera(group=row["group"],
                                               warmup=2)
                else:
                    cam = camera.Camera(
                        index=row["idx"], warmup=2,
                        width=int(cfg_cam.get("width", 1280)),
                        height=int(cfg_cam.get("height", 720)))
                frame = cam.read(timeout=FRAME_BUDGET, screen=0)
                if frame is None:
                    self._results.put(("noimg", row, None))
                else:
                    self._results.put(("ok", row, frame))
            except Exception as err:
                self._results.put(("error", row, type(err).__name__))
            finally:
                if cam is not None:
                    try:
                        cam.release()
                    except Exception:
                        pass
        try:
            with cf.ThreadPoolExecutor(
                    max_workers=min(8, max(1, len(rows)))) as ex:
                for row in rows:                   # submit order =
                    ex.submit(one, row)            # display order
        except Exception:
            log.exception("setup worker died mid-sweep")

    # --------------------------------------------------------------- pump --
    def _pump(self):
        if self._dying:
            return
        try:
            while True:
                try:
                    kind, row, payload = self._results.get_nowait()
                except queue.Empty:
                    break
                self._add_card(row,
                               None if kind == "ok" else payload,
                               payload if kind == "ok" else None)
                self._done += 1
                if self._done < self._total:
                    self.veil.configure(
                        text="testing cameras... (%d of %d)"
                             % (self._done, self._total))
                else:
                    self.veil.configure(text="done")
                    self.ok_button.pack(side="left")
                    self.rerun_note.pack(side="right")
        except Exception:
            log.exception("setup pump failed; the loop goes on")
        try:
            self.after(60, self._pump)
        except Exception:
            pass

    def _add_card(self, row, error, frame):
        spec = card_spec(row, frame is None)
        card = ctk.CTkFrame(self._host, **self.skin.panel_style())
        card.pack(fill="x", pady=(0, theme.S_ROW))
        head = spec["header"]
        if frame is None:
            head += "  ·  no frame"          # the honest reason the
        if error:                            # photo box holds a
            head += "  ·  %s" % error        # sentence instead
        ctk.CTkLabel(card, text=head, font=self.skin.font(12, "bold"),
                     **self.skin.text_style()).pack(
            anchor="w", padx=theme.S_FIELD, pady=(theme.S_FIELD, 0))
        shot = ctk.CTkLabel(card, text="")
        if frame is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            scale = min(SNAP_W / img.width, SNAP_H / img.height, 1.0)
            img = img.resize((max(int(img.width * scale), 16),
                              max(int(img.height * scale), 16)))
            shot._ctkimg = ctk.CTkImage(light_image=img, dark_image=img,
                                        size=img.size)
            shot.configure(image=shot._ctkimg)
        else:
            shot.configure(text="request timed out - non-responsive",
                           font=self.skin.font(11),
                           **self.skin.text_style("sub"))
        shot.pack(anchor="w", padx=theme.S_FIELD, pady=theme.S_FIELD // 2)
        line = ctk.CTkFrame(card, fg_color="transparent")
        line.pack(fill="x", padx=theme.S_FIELD, pady=(0, theme.S_FIELD))
        entry = ctk.CTkEntry(line, font=self.skin.font(12))
        entry.insert(0, spec["prefill"])
        entry.pack(side="left", fill="x", expand=True)
        var = ctk.BooleanVar(value=spec["checked"])
        ctk.CTkCheckBox(line, text="hide this camera", variable=var,
                        font=self.skin.font(11), checkbox_width=14,
                        checkbox_height=14, fg_color=self.skin.accent,
                        hover_color=self.skin.accent_hover,
                        border_color=self.skin.border_raised,
                        text_color=self.skin.text,
                        text_color_disabled=self.skin.txt3).pack(
            side="right", padx=(theme.S_FIELD, 0))
        self._cards.append({"key": spec["key"], "prefill": spec["prefill"],
                            "entry": entry, "var": var,
                            "started": spec["checked"]})

    # ---------------------------------------------------------- buttons --
    def _ok(self):
        states = [(c["key"], c["prefill"], str(c["entry"].get()),
                   bool(c["var"].get()), c["started"])
                  for c in self._cards]
        for action, payload in ok_verbs(states):
            self.app.monitor.events.put((action, payload))
        # setup completed IS consent: the enable rides the same loop-
        # owned queue (the ui never writes the toml); the pane refresh
        # gives the picker its captions the moment the veil lifts
        self.app.monitor.events.put(("camera_enabled", True))
        self._close()
        try:
            self.app._scan_cameras()
        except Exception:
            pass

    def _close(self):
        # the destroy law from birth (the wave's own crash lesson):
        # the X and OK both land here, ONCE (the guard: an X + button
        # burst can double), withdraw now / destroy on the loop's
        # clean stack
        if self._dying:
            return
        self._dying = True
        self.withdraw()
        try:
            self.after(0, self.destroy)
        except Exception:
            pass

    def _claim_focus(self):
        try:
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
