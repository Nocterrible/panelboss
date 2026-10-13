"""Per-camera policy editor (UI-1e, corrected by owner review): rows
follow the ROSTER, not the scan - a camera appears here only after
the picker adds it to duty, and the picker (which then disappears
from the menu, killing the old redundancy) is how a second eye
joins at all. The rows write the engine's OWN tables -
cfg["camera"]["on"] / ["off"], {index: mode} over CAMERA_MODES -
which is exactly what state/_policy._table_mode resolves (an absent
index inherits that table's global) and exactly what
config.write_config emits as [camera.on] / [camera.off] with string
keys. A freshly added camera has no entries, so it starts at
follow-global (owner: never a silent "off"); REMOVE drops it from
the roster and wipes its entries, so re-adding is pristine.
The widgets are a view; the tables are the truth, so every
rebuild re-reads them, never the old widgets.
"""

from __future__ import annotations

import customtkinter as ctk

from .. import theme
from . import _camid
from ... import camera
from ._constants import TIPS
from ._widgets import SkewCombo

# the combo contract: the first label is the one that never reaches
# the file (ABSENT key is the inherit), the rest are the engine's own
# spellings, shown the way the card's global pair shows them
POLICY_LABELS = ["(follow global)", "boot per poll", "always on", "off"]
TO_MODE = {"boot per poll": "boot_per_poll", "always on": "always_on",
           "off": "off"}
TO_LABEL = {mode: label for label, mode in TO_MODE.items()}
FOLLOW = POLICY_LABELS[0]
ADD_LABEL = "add a camera..."       # the picker's face and no-op verb


def duty_roster(camera_cfg):
    """The roster VERBATIM, not through config.normalize_index: its
    "empty means the stock default" guard fits loading a file, but an
    empty list the window just wrote (removing the last camera) must
    display as honest empty duty, and the bare-int shape (-2/-1
    sentinels, historic single camera) reads as the one camera."""
    value = camera_cfg.get("index", 0)
    if isinstance(value, (list, tuple)):
        return [int(i) for i in value]
    return [int(value)]
NAME_CLIP = 24                    # "cam 0 <name>" must survive the 320
                                  # px zone; the id never clips, only
                                  # the name does


def ir_row_spec(camera_cfg):
    """(display name, hidden?) for an IR seat ON DUTY, None when the
    HELLO_IR sentinel is not rostered (owner amendment 5: an on-duty
    camera with no card is an unremovable camera, and the cv2 scan
    can never carry -2 into _rebuild_cam_rows - the seat needs its
    own line into the duty editor). The name rides the SAME key the
    wizard's IR rows use ("ir:<group>"), so a label written in the
    wizard surfaces here; the first bridge group names an unlabeled
    seat, and a missing bridge says so honestly (hello_ir_names
    returns [] when whircam is absent, never raises - the same oracle
    the picker's IR lines read)."""
    if camera.HELLO_IR not in duty_roster(camera_cfg):
        return None
    names = camera.hello_ir_names()
    base = names[0] if names else None
    label = ((camera_cfg.get("labels") or {}).get("ir:" + base)
             if base else "")
    hidden = ("ir:" + (base or "")) in (camera_cfg.get("hidden") or [])
    return (label or base or "hello IR (bridge missing)"), hidden


class _CamEditMixin:

    def _build_cam_policy_zone(self, zone):
        """The per-camera list: a plain frame, no ScrollHost - the
        roster caps at four cameras (config says so, loudly), so the
        zone grows a bounded amount and the card's own page already
        scrolls. Rows appear when a scan reports cameras; until then
        the zone carries an honest empty line, not a blank stare."""
        head = ctk.CTkLabel(zone, text="per camera",
                            font=self.skin.font(12, "bold"),
                            **self.skin.text_style())
        head.pack(anchor="w", pady=(theme.S_ROW, 0))
        # UI-1c reversal: the per-camera paragraph rides the heading's
        # hover, the exact path the old "?" chip used
        head.bind("<Enter>",
                  lambda e=None: self.tips._schedule(TIPS["cam_policies"],
                                                     head),
                  add="+")
        head.bind("<Leave>", lambda e=None: self.tips._hide_soon(), add="+")
        self._hint(zone, TIPS["cam_policies"], chars=42)
        self._cam_rows_frame = ctk.CTkFrame(zone, fg_color="transparent")
        self._cam_rows_frame.pack(anchor="w", fill="x",
                                  pady=(theme.S_FIELD, 0))
        self._cam_rows = {}

    def _rebuild_cam_rows(self, found):
        """Called from _apply_cameras on every scan report: destroy
        the old row widgets wholesale, then build one row per scanned
        camera. Sentinels (-1/-2) get no row from the scan loop - a
        single-eyed device never takes a table entry (the config guard
        makes that noise-free), so an editor line for it could only
        lie. The IR seat is the honest exception (owner amendment 5):
        rostered duty WITHOUT a cv2 index, invisible to the loop
        above, and duty with no card is duty with no remove button -
        ir_row_spec gives it the line the roster says it earned.
        Cards survive the discard-rebuild like the scanned ones, and
        identity writes resync the pane, so a wizard label or a hide
        reaches the IR card on the same turn it reaches the others."""
        for widget in self._cam_rows_frame.winfo_children():
            widget.destroy()
        self._cam_rows = {}
        roster = set(duty_roster(self.cfg["camera"]))
        hidden = self.cfg["camera"].get("hidden") or []
        hid = _camid.hidden_indices(getattr(self, "_devs", None) or [],
                                    found, hidden,
                                    self.cfg["camera"].get("bindings") or {})
        names = _camid.display_names(getattr(self, "_devs", None) or [],
                                     found, self.cfg["camera"])
        # the sweep's verdict rides the duty card too, under the same
        # coverage gate as the picker line (the record must have
        # measured THIS scan): a duty camera that served no image says
        # so on its own card
        diag = self.cfg["camera"].get("diag") or {}
        covers = bool(diag) and \
            sorted(diag.get("indices") or []) == sorted(e[0] for e in found)
        for entry in found:
            index, name = entry[0], names.get(entry[0], "") or entry[3]
            if isinstance(index, int) and index in roster:
                # a hidden device ON duty keeps its row (the engine
                # still honors the roster) wearing an honest badge
                self._cam_row(index, name, index in hid,
                              (_camid.diag_suffix(self.cfg["camera"],
                                                  entry[0])
                               if covers else ""))
        # the IR seat's card (amendment 5): duty the cv2 loop cannot
        # see gets its line from the roster itself - name, hidden
        # badge, policy pair, and the remove button the owner was
        # missing on the live pane
        ir = ir_row_spec(self.cfg["camera"])
        if ir is not None:
            self._cam_row(camera.HELLO_IR, ir[0], ir[1])
        if not self._cam_rows:
            ctk.CTkLabel(self._cam_rows_frame,
                         text="no cameras on duty - add one above",
                         font=self.skin.font(11),
                         **self.skin.text_style("sub")).pack(anchor="w")

    def _cam_row(self, index, name, hidden=False, verdict=""):
        """Camera header at tier 1, then the two policy lines at hint
        tier (the card is ~350 px: two combos sharing one line do not
        fit, so each policy owns a line, mirroring the global pair's
        rhythm)."""
        row = ctk.CTkFrame(self._cam_rows_frame, fg_color="transparent")
        row.pack(fill="x", pady=(theme.S_FIELD, 0))
        row.grid_columnconfigure(0, weight=1)
        title = "cam %s" % index
        if name:
            title += " · %s" % str(name)[:NAME_CLIP]
        if hidden:
            title += " · (hidden from menus)"
        # the sweep's verdict appended AFTER the clip, like the hidden
        # badge: NAME_CLIP is the NAME's width guard, and a state
        # suffix must not eat the name's budget - nor be eaten by it
        # (a 29-char verdict clipped to 24 would never survive, which
        # is why this rides post-clip rather than the call site: the
        # packet's law, applied to the real clip)
        title += verdict
        head = ctk.CTkLabel(row, text=title, font=self.skin.font(12),
                            **self.skin.text_style())
        head.grid(row=0, column=0, sticky="w")
        # every duty camera owns its exit: removal drops it from the
        # roster AND wipes its table entries, so re-adding starts
        # pristine at follow-global (owner's rule, no silent offs)
        ctk.CTkButton(row, text="remove", width=64,
                      font=self.skin.font(11),
                      command=self._cam_remove(index),
                      **self.skin.secondary()).grid(
            row=0, column=1, sticky="e")
        menus = {}
        for n, (table, label) in enumerate((("on", "while on"),
                                            ("off", "while off"))):
            # the line frames ride the SAME manager as the header (a
            # grid frame may not host pack slaves); full width under
            # both header columns keeps the label-left combo-right
            # rhythm the columnconfigure weight buys
            line = ctk.CTkFrame(row, fg_color="transparent")
            line.grid(row=1 + n, column=0, columnspan=2, sticky="we")
            line.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(line, text=label, font=self.skin.font(11),
                         **self.skin.text_style("sub")).grid(
                row=0, column=0, sticky="w")
            menu = SkewCombo(line, values=POLICY_LABELS, width=160,
                             command=self._cam_policy_changed(index,
                                                              table),
                             **self.skin.menu_style())
            menu.grid(row=0, column=1, sticky="e")
            menu.set(self._cam_policy_label(index, table))
            menus[table] = menu
        self._cam_rows[index] = {"head": head, "menus": menus,
                                 "title": title}
        self._cam_dim(index)

    def _cam_remove(self, index):
        def command():
            roster = [i for i in duty_roster(self.cfg["camera"])
                      if i != index]
            self.cfg["camera"]["index"] = roster
            for table in ("on", "off"):
                entries = self.cfg["camera"].get(table)
                if isinstance(entries, dict):
                    entries.pop(index, None)   # re-add starts pristine
            self.monitor.events.put(("camera", list(roster)))
            self._apply_cameras(self._cams)    # row gone, menu regains
            self._save()
        return command

    def _cam_refresh(self):
        """Re-run every row's dim/duty verdict: any change to the
        GLOBAL pair or the rotation roster can move a row's truth
        underneath it, and the engine recomputes both at every poll -
        the row must not lag the table it mirrors."""
        for index in list(getattr(self, "_cam_rows", {})):
            self._cam_dim(index)

    def _cam_table_mode(self, index, table):
        """The engine's own resolution, recomputed from the cfg dict
        (the window must not lean on the monitor: the UI suites drive
        this with a fake one): table entry wins, the table's global
        fills the gap."""
        cam = self.cfg["camera"]
        entry = (cam.get(table) or {}).get(index)
        if entry in TO_MODE.values():
            return entry
        return cam.get("mode_off" if table == "off" else "mode_on")

    def _cam_policy_label(self, index, table):
        stored = (self.cfg["camera"].get(table) or {}).get(index)
        return FOLLOW if stored is None else TO_LABEL.get(stored, FOLLOW)

    def _cam_policy_changed(self, index, table):
        def command(label):
            entries = self.cfg["camera"].setdefault(table, {})
            if label == FOLLOW:
                entries.pop(index, None)   # absent IS inherit; an
                # emptied table then goes unwritten (config's rule: a
                # missing table means the globals)
            else:
                entries[index] = TO_MODE[label]
            self._cam_dim(index)
            self._save()
        return command

    def _cam_dim(self, index):
        """off in BOTH states is an eye this app will never need - the
        mosaic keeps it as a labeled hole and never opens it (state/
        _preview); the row reads at the disabled tier (skin.txt3).
        Inherited offs count, same test the mosaic applies."""
        row = self._cam_rows.get(index)
        if row is None:
            return
        off = (self._cam_table_mode(index, "on") == "off"
               and self._cam_table_mode(index, "off") == "off")
        row["head"].configure(**self.skin.text_style(
            "disabled" if off else "text"))
        # duty needs no badge here: rows exist ONLY for roster members
        # (owner review); an off-roster camera is not listed at all,
        # and the picker offers it again
