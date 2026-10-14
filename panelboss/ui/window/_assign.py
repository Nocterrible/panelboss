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

Amendment 6 (owner's one-screen law) grew the card: beside the rename
entry a second checkbox, "add to selection", seeds CHECKED from the
duty roster (an on-duty feed cannot be dropped by omission) and OK
posts the checked set as the ONE existing ("camera", list) roster
verb, on a set-diff only. The four-feed ceiling lives in the widget:
at four checked every unchecked add-box grays (checked boxes never
do - the exit is to give a seat up), the reason rides the count line.
The state-side first-four truncation at load stays as the net.

SIZE LAW: measured 696 (Oct 13, fix wave A: the dialog watchdog
- row beats, the sum-of-budgets deadline, the dead-draw close -
plus the exit resync) - the split seam is
named: everything
above the class line (rows_from, card_spec, ok_verbs, add_ceilings)
is the pure data contract - importable, testable without a display
(camdiag section 9) - the SetupWindow class is the widget shell. The
watchdog trio (row_label, veil_text, and the budget arithmetic in
_gather) joined the pure side at fix wave A: the deadline is a
number, and numbers get truth-tabled. If
the shell grows dialog-section machinery, it splits by section the
way _camedit did from _preview, not by helper archaeology.
"""

import logging
import queue
import threading
import time

import cv2
import customtkinter as ctk
from PIL import Image

from .. import theme
from . import _identity
from ... import camera

log = logging.getLogger("ui")

FRAME_BUDGET = 15.0        # seconds a feed gets for its FIRST frame
MARGIN_SEC = 5.0           # the named margin of the watchdog
                           # arithmetic (computed where it rides:
                           # _gather's dialog deadline)
SNAP_W, SNAP_H = 220, 140  # the card's photo box: 8 seats at ~400px


# ------------------------------------------------------------- pure core --
def row_label(row):
    """A row's honest one-word name for the veil (defect 2b): the
    index, or the IR group the sentinel stands for."""
    return "ir %s" % row["group"] if row["group"] is not None \
        else str(row["idx"])


def veil_text(done, total, probing=None, waiting=0):
    """The veil's line, pure (defect 2b): a bare "testing cameras..."
    gave the owner no shape to read while a wedged door held the
    line for six minutes. The count truth FIRST (the card spawns on
    the settle, so the k-of-n never lies); while the board is open
    the LONGEST-WAITING un-settled feed is NAMED - the one that
    knocked first and has not been answered - and the rest are
    counted, so silence always has a shape and a number."""
    if done >= total:
        return "done"
    base = "testing cameras... (%d of %d)" % (done, total)
    if probing is None:
        return base + "  ·  starting"
    if waiting:
        return base + "  ·  probing %s, %d waiting" % (probing, waiting)
    return base + "  ·  probing %s" % (probing,)


def rows_from(devs, enumerated, ir_names, cfg_camera):
    """The screen's seat list: one row per enumerated index (opened
    or not - a dead index still earns a timed-out card, the owner
    must SEE the seat that failed), plus one row per bridge group.
    Returns (rows, n): rows are dicts the worker walks; n is the
    progress denominator, and the scan ceiling (0..7) is the same
    bound the probe worker already keeps."""
    cfg_camera = cfg_camera or {}
    labels = cfg_camera.get("labels") or {}
    ids = _identity.identity_map(devs, enumerated,
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


def card_spec(row, timed_out, cfg_camera=None):
    """The pure verdict behind every card (tested offline): key the
    identity verbs ride, the entry prefill (a saved label wins over
    the display name - the diff-only rule then sends only what the
    owner re-typed), the header line, and the hide checkbox SEED -
    the second-run rule (gate finding 2): a rerun must not undo the
    desk it is showing. Priority:

    (a) the key sits in camera.hidden -> CHECKED. A hidden bright
        camera renders checked (and is un-hideable right from the
        card: unchecking posts the show verb, the sticky path);
    (b) a DARK feed the human touched (label, bind, or above all
        camera.shown) -> UNCHECKED. Amending amendment 2 in its
        literal place: a timeout-seeded check that survives the
        owner's SHOW would re-hide the immune camera the moment OK
        rides silence - the trap the second run walked into;
    (c) plain dark/timeout, untouched -> CHECKED (the dark default);
    (d) bright, untouched -> UNCHECKED (silence is not a claim).
    """
    cfg_camera = cfg_camera or {}
    key = row["key"]
    hidden = set(str(k) for k in (cfg_camera.get("hidden") or []))
    touched = (set(cfg_camera.get("labels") or {})
               | set(cfg_camera.get("bindings") or {})
               | set(str(k) for k in (cfg_camera.get("shown") or [])))
    if key in hidden:
        checked = True                          # (a)
    elif timed_out and key in touched:
        checked = False                         # (b)
    elif timed_out:
        checked = True                          # (c)
    else:
        checked = False                         # (d)
    # the ADD seed (amendment 6): a camera already on the duty roster
    # arrives CHECKED - the owner must not lose it by omission, the
    # same seeding law as hide. The seat is the scan index, or the
    # IR sentinel for a bridge row; the roster reads verbatim (an
    # int is the one-camera shape, a list the rotation - the state
    # branch accepts both since forever)
    duty = cfg_camera.get("index", 0)
    duty = set(duty) if isinstance(duty, (list, tuple)) else {duty}
    seat = (camera.HELLO_IR if row.get("group") is not None
            else row["idx"])
    head = "index %s" % row["idx"] if row["idx"] is not None \
        else "hello IR"
    if row["detail"]:
        head += "  ·  %s" % row["detail"]
    elif row["idx"] is not None and not row.get("opened", True):
        head += "  ·  never opened"
    return {"key": key, "prefill": row["name"],
            "checked": checked, "header": head,
            "add": seat in duty, "seat": seat}


CEILING = 4           # the driver-safe live-feed cap (state-side
                      # first-four truncation stays the NET; the
                      # dialog stops producing the overflow)
CEILING_NOTE = "four live feeds is the driver-safe ceiling"


def add_ceilings(add_flags, ceiling=CEILING):
    """The widget law in pure form (amendment 6): one gray flag per
    add box. At the ceiling every UNCHECKED box grays - the checked
    ones never do, the way out of the ceiling is to give a seat up
    first - and an uncheck re-lights through the same function."""
    at = sum(1 for f in add_flags if f) >= ceiling
    return [at and not f for f in add_flags]


def ok_verbs(cards, current_roster=None):
    """The events OK posts, as a pure function over the card states
    [(key, prefill, text, checked, started_checked)] - the diff-only
    law and the hide/show asymmetry, importable and testable. An
    unchanged entry says NOTHING (the d4000b1 finding: a manufactured
    prefill must not poison the bind migration); a re-typed one is a
    label; hide True is a hide, and hide False on a card that STARTED
    checked (a dark feed the owner kept anyway) is the shown verb -
    stickiness per amendment 2. A card that started unchecked and
    stayed so is the owner's silence, which is not a claim.

    Amendment 6 rides the SAME function, same law: when the caller
    passes 7-fields cards (add_checked, seat) AND the current roster,
    the checked set goes out as ONE ("camera", sorted list) roster
    write - the existing state verb, no new channel - but ONLY when
    the SET differs (silence is not a roster claim either). An all-
    unchecked board posts [] (honest no-duty; the load boundary's
    empty-means-stock rule is the engine's own law, not this
    dialog's)."""
    out = []
    seats = None
    for c in cards:
        key, prefill, text, checked, started_checked = c[:5]
        verb = {"instance": key}
        if text != prefill:
            verb["label"] = text
        if checked:
            verb["hide"] = True
        elif started_checked:
            verb["show"] = True
        if len(verb) > 1:
            out.append(("camera_identity", verb))
        if len(c) >= 7:
            add_checked, seat = c[5], c[6]
            if seats is None:
                seats = []
            if add_checked:
                seats.append(seat)
    if current_roster is not None and seats is not None:
        cur = (set(current_roster) if isinstance(current_roster,
                                                (list, tuple))
               else {current_roster})
        if set(seats) != cur:
            out.append(("camera", sorted(seats)))
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
        # the dialog watchdog (defect 2, owner UAT): the deadline is
        # armed the moment the board is counted (and already now,
        # for the enumerate phase, with the scan ceiling standing in
        # for the row count - the same arithmetic _gather re-arms
        # with), and the PUMP owns it: an op that wedges holds the
        # device-tree lock while it hangs, so a worker cannot be
        # trusted to report its own death, and a board cannot be
        # trusted to answer at all. Rows announced, rows settled,
        # rows beaten - the veil reads all three (defect 2b: silence
        # gets a shape and a name).
        self._rows = []
        self._settled = set()
        self._started = []
        self._deadline_at = (time.monotonic() + 8 * (
            float(getattr(camera, "OPEN_LOCK_TIMEOUT", 30.0))
            + FRAME_BUDGET) + MARGIN_SEC)
        self._board_seen = False
        self._board_done = False
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=theme.S_SECTION, pady=(theme.S_ROW, 0))
        ctk.CTkLabel(head, text="camera setup",
                     font=self.skin.font(15, "bold"),
                     **self.skin.text_style()).pack(side="left")
        # the duty-count line (amendment 6): the count the ceiling
        # rule reads against, and the one place the reason can ride
        self._count = ctk.CTkLabel(head, text="",
                                   font=self.skin.font(10),
                                   **self.skin.text_style("sub"))
        self._count.pack(side="right")
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
        amendment-1 doctrine, inherited whole). Defect 2 (owner UAT,
        the 18:33 stall): the read's timeout arg is sampled BETWEEN
        frames by the engine, and a wedged driver blocks INSIDE
        cap.read() - the promise never gets to run. So the op runs
        in its own inner thread and the worker JOINS it with a
        deadline: a timed join CANNOT hang whatever the driver does
        (the packet's named choice - the timeout arg exists but is
        defeatable, the join is the smallest thing that cannot)."""
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
        try:
            ir_names = camera.hello_ir_names()
        except Exception:
            log.exception("setup: the IR bridge never named itself")
            ir_names = []
        rows, n = rows_from(devs, enumerated, ir_names, cfg_cam)
        self._rows = rows
        # the arithmetic, named (defects 2a/2d). ROW deadline: the
        # engine's published lock-wait (OPEN_LOCK_TIMEOUT - the
        # worst a wedged SIBLING open may honestly make it) + the
        # frame budget + margin; the op joins against it, so a single
        # wedged door (which HOLDS the device-tree lock while it
        # hangs, silencing every row queued behind it) is caught at
        # its own deadline, not the board's. BOARD deadline: the SUM
        # of every budget (opens serialize: n rows × one full
        # lock-wait each, the frame budget is the one shared tail -
        # the boot scan's own bound, inherited whole) + margin. Past
        # the board deadline every un-settled row draws dead and the
        # OK button appears regardless of what the driver is still
        # chewing on (defect 2c).
        lock_wait = float(getattr(camera, "OPEN_LOCK_TIMEOUT", 30.0))
        row_deadline = lock_wait + FRAME_BUDGET + MARGIN_SEC
        self._deadline_at = (time.monotonic()
                             + max(1, n) * (lock_wait + FRAME_BUDGET)
                             + MARGIN_SEC)
        self._results.put(("board", None, n))

        def one(row):
            # the both-ends discipline of the wave's probe: the card
            # spawns on the SETTLE, so the k-of-n never lies - and
            # the beat lands BEFORE the op touches a door, so the
            # veil can name the stall while it lives (defect 2b)
            self._results.put(("probing", row, None))
            box = []

            def op():
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
                        box.append(("noimg", None))
                    else:
                        box.append(("ok", frame))
                except Exception as err:
                    box.append(("error", type(err).__name__))
                finally:
                    if cam is not None:
                        try:
                            cam.release()
                        except Exception:
                            pass

            t = threading.Thread(target=op, daemon=True,
                                 name="assign-op-%s" % row["key"])
            t.start()
            t.join(row_deadline)
            if box:
                kind, payload = box[0]
            else:
                # the join outlived the op: drawn dead now (the
                # honest verdict), not counted by the board deadline
                # later - the abandoned daemon keeps its wedged
                # driver handle and dies with the process, the
                # measured cost of pulling a foot off a train
                kind, payload = "error", "stalled"
            self._results.put((kind, row, payload))
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
                if kind == "board":
                    self._total = payload
                    self._board_seen = True
                    if not payload:
                        # the empty board is a SETTLED board (defect
                        # 2c): OK appears now, not when a settle
                        # arrives that will never come
                        self._close_board()
                    continue
                if kind == "probing":
                    self._started.append(row["key"])
                    continue
                if row["key"] in self._settled:
                    continue                       # dead-and-late:
                    # the first verdict owns the card (a row the
                    # watchdog drew dead stays dead - the rescan is
                    # its second chance, not this dialog's problem)
                self._settled.add(row["key"])
                self._add_card(row,
                               None if kind == "ok" else payload,
                               payload if kind == "ok" else None)
                self._done += 1
                if self._done >= self._total:
                    self._close_board()
            if not self._board_done:
                if time.monotonic() >= self._deadline_at:
                    # the dialog-level dead-man (defect 2d): the sum
                    # of all budgets passed and the board is still
                    # open - whatever has not reported is DEAD, and
                    # saying so is the dialog's job, not the driver's
                    log.warning("setup watchdog: %d of %d rows never "
                                "reported - drawing them dead",
                                self._total - self._done, self._total)
                    self._close_board()
                else:
                    if self._board_seen:
                        # before the board event there is no honest
                        # count to paint (a 0-of-0 would read
                        # "done" mid-enumerate): the veil keeps its
                        # build text until the count lands
                        self.veil.configure(text=self._progress())
        except Exception:
            log.exception("setup pump failed; the loop goes on")
        try:
            self.after(60, self._pump)
        except Exception:
            pass

    def _progress(self):
        """The veil's live line (defect 2b): settled count, then the
        row that knocked FIRST and has not been answered - the
        stall's name, read off the beat order - and how many sit
        behind it. Pure veil_text does the dressing."""
        prober = next((r for r in self._rows
                       if r["key"] in self._started
                       and r["key"] not in self._settled), None)
        waiting = max(0, self._total - self._done - (1 if prober else 0))
        return veil_text(self._done, self._total,
                         row_label(prober) if prober else None, waiting)

    def _close_board(self):
        """One board close, every ending (defect 2c): the last settle,
        the dead-man deadline, and the empty board all land here.
        Un-reported rows are drawn DEAD first - the owner must see
        the seat the driver ate, not count cards and wonder - then
        the veil settles and the OK button appears REGARDLESS: a
        hung door may not eat the exit."""
        if self._board_done:
            return
        for row in self._rows:
            if row["key"] not in self._settled:
                self._settled.add(row["key"])
                self._add_card(row, "stalled", None)
                self._done += 1
        self._board_done = True
        self.veil.configure(text="done")
        self.ok_button.pack(side="left")
        self.rerun_note.pack(side="right")

    def _add_card(self, row, error, frame):
        spec = card_spec(row, frame is None, self.app.cfg["camera"])
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
        # the ADD box (amendment 6, the owner's one-screen law):
        # beside the rename entry, seeded from the duty roster (an
        # on-duty feed starts CHECKED - omission must not silently
        # remove it). The trace - not the command - drives the
        # recount, so a programmatic set (the tests, someday a
        # button) re-lights the board just like a click.
        add_var = ctk.BooleanVar(value=spec["add"])
        add_box = ctk.CTkCheckBox(line, text="add to selection",
                                  variable=add_var,
                                  font=self.skin.font(11),
                                  checkbox_width=14, checkbox_height=14,
                                  fg_color=self.skin.accent,
                                  hover_color=self.skin.accent_hover,
                                  border_color=self.skin.border_raised,
                                  text_color=self.skin.text,
                                  text_color_disabled=self.skin.txt3)
        add_box.pack(side="right", padx=(theme.S_FIELD, 0))
        add_var.trace_add("write", self._recount)
        self._cards.append({"key": spec["key"], "prefill": spec["prefill"],
                            "entry": entry, "var": var,
                            "started": spec["checked"],
                            "add": add_var, "add_box": add_box,
                            "add_started": spec["add"],
                            "seat": spec["seat"]})
        self._recount()

    def _recount(self, *_args):
        """The four-feed ceiling enforced where the choices happen:
        at the cap every unchecked add-box grays (the state-side
        first-four truncation stays as the net, but the dialog can
        no longer produce the overflow), and the reason rides the
        count line. Checked boxes never gray - the way out of the
        ceiling is to give a seat up first."""
        try:
            flags = [bool(c["add"].get()) for c in self._cards]
        except Exception:
            return
        for card, gray in zip(self._cards, add_ceilings(flags)):
            try:
                card["add_box"].configure(state="disabled" if gray
                                          else "normal")
            except Exception:
                pass                          # dying window, no podium
        n = sum(flags)
        try:
            self._count.configure(
                text="%d to add%s" % (n, "  ·  " + CEILING_NOTE
                                      if n >= CEILING else ""))
        except Exception:
            pass

    # ---------------------------------------------------------- buttons --
    def _ok(self):
        states = [(c["key"], c["prefill"], str(c["entry"].get()),
                   bool(c["var"].get()), c["started"],
                   bool(c["add"].get()), c["seat"])
                  for c in self._cards]
        for action, payload in ok_verbs(
                states, self.app.cfg["camera"].get("index", 0)):
            self.app.monitor.events.put((action, payload))
        # setup completed IS consent: the enable rides the same loop-
        # owned queue (the ui never writes the toml)
        self.app.monitor.events.put(("camera_enabled", True))
        self._close(refresh=True)

    def _close(self, refresh=False):
        # the destroy law from birth (the wave's own crash lesson):
        # the X and OK both land here, ONCE (the guard: an X + button
        # burst can double), withdraw now / destroy on the loop's
        # clean stack. The pane refresh rides EVERY close (law 4: OK
        # or X, the picker captions must not keep a feed the setup
        # may have just named or killed) - and an X that never
        # enabled leaves the consent gate holding the doors shut,
        # which is the whole point of the gate
        if self._dying:
            return
        self._dying = True
        # EVERY exit re-syncs the detection tab, unconditionally
        # (owner UAT defect 3): X, OK and the skin rebuild all ride
        # this one function, and the tab must never keep wearing the
        # click that opened this window. enabled is the state loop's
        # key (OK posts it, the loop writes it, the (cameras, None)
        # round-trip repaints it) - a close that never completed
        # consent leaves the truth OFF, and the resync paints exactly
        # that: switch back to the key, note up, gray-out re-derived.
        # Inside the guard, so an X+OK burst retires ONCE and resyncs
        # ONCE (the Spy pin); the hasattr is the test seam (the Spy
        # app is a bare stub), not a behavior gate.
        resync = getattr(self.app, "_sync_consent_switch", None)
        if resync is not None:
            resync()
        self.withdraw()
        try:
            self.after(0, self.destroy)
        except Exception:
            pass
        if refresh or self.app.cfg["camera"].get("enabled"):
            try:
                self.app._scan_cameras()
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
