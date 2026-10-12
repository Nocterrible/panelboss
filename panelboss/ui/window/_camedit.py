"""Per-camera policy editor (UI-1e): one row per scanned camera in
the camera card, so enabling a second eye never means editing
config.toml. The rows write the engine's OWN tables -
cfg["camera"]["on"] / ["off"], {index: mode} over CAMERA_MODES -
which is exactly what state/_policy._table_mode resolves (an absent
index inherits that table's global) and exactly what
config.write_config emits as [camera.on] / [camera.off] with string
keys. The widgets are a view; the tables are the truth, so every
rebuild re-reads them, never the old widgets.
"""

from __future__ import annotations

import customtkinter as ctk

from .. import theme
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
NAME_CLIP = 24                    # "cam 0 <name>" must survive the 320
                                  # px zone; the id never clips, only
                                  # the name does


class _CamEditMixin:

    def _build_cam_policy_zone(self, zone):
        """The per-camera list: a plain frame, no ScrollHost - the
        roster caps at four cameras (config says so, loudly), so the
        zone grows a bounded amount and the card's own page already
        scrolls. Rows appear when a scan reports cameras; until then
        the zone carries an honest empty line, not a blank stare."""
        ctk.CTkLabel(zone, text="per camera",
                     font=self.skin.font(12, "bold"),
                     **self.skin.text_style()).pack(
            anchor="w", pady=(theme.S_ROW, 0))
        self._hint(zone, TIPS["cam_policies"], chars=42)
        self._cam_rows_frame = ctk.CTkFrame(zone, fg_color="transparent")
        self._cam_rows_frame.pack(anchor="w", fill="x",
                                  pady=(theme.S_FIELD, 0))
        self._cam_rows = {}

    def _rebuild_cam_rows(self, found):
        """Called from _apply_cameras on every scan report: destroy
        the old row widgets wholesale, then build one row per scanned
        camera. Sentinels (-1/-2) get no row - a single-eyed device
        never takes a table entry (the config guard makes that noise-
        free), so an editor line for it could only lie."""
        for widget in self._cam_rows_frame.winfo_children():
            widget.destroy()
        self._cam_rows = {}
        for entry in found:
            index, name = entry[0], entry[3]
            if isinstance(index, int) and index >= 0:
                self._cam_row(index, name)
        if not self._cam_rows:
            ctk.CTkLabel(self._cam_rows_frame,
                         text="no cameras to list - rescan",
                         font=self.skin.font(11),
                         **self.skin.text_style("sub")).pack(anchor="w")

    def _cam_row(self, index, name):
        """Camera header at tier 1, then the two policy lines at hint
        tier (the card is ~350 px: two combos sharing one line do not
        fit, so each policy owns a line, mirroring the global pair's
        rhythm)."""
        row = ctk.CTkFrame(self._cam_rows_frame, fg_color="transparent")
        row.pack(fill="x", pady=(theme.S_FIELD, 0))
        title = "cam %s" % index
        if name:
            title += " · %s" % str(name)[:NAME_CLIP]
        head = ctk.CTkLabel(row, text=title, font=self.skin.font(12),
                            **self.skin.text_style())
        head.pack(anchor="w")
        menus = {}
        for table, label in (("on", "while on"), ("off", "while off")):
            line = ctk.CTkFrame(row, fg_color="transparent")
            line.pack(fill="x")
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
        # duty truth, recomputed exactly as the engine roster reads
        # it: a policy on an off-roster camera persists and displays,
        # but the camera cannot vote until the picker (or TOML) puts
        # it on - the row says so rather than letting the policy
        # look silently live
        from ... import config as _cfg
        try:
            on_duty = index in _cfg.normalize_index(
                self.cfg["camera"].get("index", 0))
        except Exception:
            on_duty = True
        row["head"].configure(text=row["title"] + (
            "" if on_duty else "  ·  not on duty"))
