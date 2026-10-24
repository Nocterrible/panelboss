"""Pin editor verbs: select, browse, wait, commit, forget - and
the flow helper the pin lists share.
Oct 12 (owner ruling): single pins and unpins update the pins
section SURGICALLY - one row appended, reconfigured or destroyed -
and the bulk verb (pin-all) alone earns a section swap."""

from __future__ import annotations

import logging

import customtkinter as ctk

from ... import profiles
from .. import theme
from ._widgets import _fresh_pin_edit

log = logging.getLogger("ui")


class _PinMixin:
    def _pin_cols(self, parent, count):
        """The flow both pin lists obey. OWNER ORDER, Oct 15 (UAT):
        the lists are LISTS - one packed row per entry, full width.
        The Oct 12 two-sub-column sketch (rows of two chips, taller
        and narrower) is retired: it read as a grid, not a list. The
        count argument stays for the call sites' shape; the answer
        is always ONE column."""
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(anchor="w", fill="x")
        return [f]


    def _pin_select(self, key):
        """a click in the open-windows list makes it the editor's
        subject; clicking the same one again lets go of it. the pane
        is NOT rebuilt whole - the highlight moves on the existing
        row buttons and only the editor section repaints"""
        if self._pin_edit["pick"] == key and self._pin_edit["key"] \
                is None:
            self._pin_edit["pick"] = None
        else:
            self._pin_edit.update(key=None, pick=key)
        self._restyle_live()
        self._repaint("editor")


    def _pin_load(self, w):
        """the pinned row clicked: the pin pops back up into the
        editor, conditions as saved, ready to change and update.
        The row's captured dict can be stale after an in-place
        update-pin (the row was not rebuilt), so the CURRENT saved
        row is re-resolved from the store by its (proc, title) key;
        the captured dict is the fallback for a row a re-scan just
        removed."""
        prof = (self._prof_data.get("profiles") or {}).get(
            self._prof_sel) or {}
        w = next((r for r in prof.get("wins") or []
                  if (r["proc"], r["title"]) == (w["proc"], w["title"])),
                 w)
        try:
            wait = max(0, min(600, int(w.get("wait") or 0)))
        except (TypeError, ValueError):
            wait = 0
        self._pin_edit.update(key=(w["proc"], w["title"]),
                              pick=(w["proc"], w["title"]),
                              match=w.get("match")
                              or (self._prof_data["profiles"]
                                  .get(self._prof_sel, {})
                                  .get("match"))
                              or "process",
                              open=bool(w.get("open")),
                              wait=wait, exe=w.get("exe") or None)
        self._restyle_live()
        self._repaint("editor")


    def _pin_remove(self, w, row):
        """UNPIN: destroys the clicked row's OWN frame in place (the
        x's lambda handed it over - Oct 12: no _repaint("pins") per
        click), shows the placeholder back when the section emptied,
        and tells the status line through the idempotent fill. Only
        the paths where in-place removal cannot speak the truth (a
        dead selection, or a row whose section was rebuilt under it)
        still repaint the pins section."""
        ok, note = profiles.unpin(self._prof_data, self._prof_sel,
                                  w["proc"], w["title"])
        key = (w["proc"], w["title"])
        if self._pin_edit["key"] == key:
            self._pin_edit = _fresh_pin_edit()
        self._prof_msg = ("forgot: %s" % (w["title"] or w["proc"])[:60]
                          if ok else
                          note or "save or pick a profile first")
        in_place = ok and row is not None and row.winfo_exists()
        if in_place:
            row.destroy()
            self._pin_rows.pop(key, None)
            if not self._pin_rows:              # section emptied:
                e = self._pins_empty            # the placeholder is
                if e is not None and e.winfo_exists():   # honest again
                    e.pack(anchor="w", pady=theme.S_FIELD,
                           padx=theme.S_FIELD)
        self._repaint(*(("editor", "status") if in_place
                        else ("pins", "editor", "status")))


    def _pin_match(self, mode):
        self._pin_edit["match"] = mode
        self._repaint("editor")         # the all-windows warning
                                        # hangs off this choice


    def _pin_open(self):
        self._pin_edit["open"] = bool(self.pin_open_box.get())
        self._repaint("editor")         # the naive-exe warning and
                                        # the advanced rows hang off it


    def _pin_wait(self, text):
        try:
            self._pin_edit["wait"] = int(str(text).split()[0])
        except (TypeError, ValueError):
            pass                      # a menu value we did not
                                      # write: keep the current wait
        self._repaint("editor")         # the fine print quotes it


    def _pin_browse(self):
        """What the app cannot guess, the human can: when the
        captured exe starts nothing (store stubs, wrapper launchers)
        the user points the pin at the door that really opens the
        window. The shell runs it exactly as double-click would, so
        a .lnk shortcut is a legal answer too."""
        try:
            from tkinter import filedialog
            got = filedialog.askopenfilename(
                parent=self, title="what should the profile run?",
                filetypes=[("launchers", "*.exe *.bat *.cmd *.lnk"),
                           ("all files", "*.*")],
                defaultextension=".exe")
        except Exception:
            log.warning("browse failed", exc_info=True)
            got = ""
        if got:
            self._pin_edit["exe"] = got
            self._repaint("editor")


    def _pin_cancel(self):
        self._pin_edit = _fresh_pin_edit()
        self._restyle_live()
        self._repaint("editor")


    def _pin_commit(self):
        ed = self._pin_edit
        key = ed["key"] or ed["pick"]
        if key is None:
            self._prof_msg = "pick one of the open windows first"
            self._repaint("status")
            return
        prof = (self._prof_data.get("profiles") or {}).get(
            self._prof_sel)
        if prof is None:
            # create-new, or a name the store no longer holds: the
            # pin has nowhere to live - confess, never a happy "pinned:"
            self._prof_msg = "save or pick a profile first"
            self._repaint("status")
            return
        live_row = next((w for w in profiles.windows_now()
                         if (w["proc"], w["title"]) == key), None)
        win = live_row               # the window closed since the
        if win is None:              # scan: a pin being edited
            win = next((w for w in
                        prof["wins"]
                        if (w["proc"], w["title"]) == key), None)
        if win is None:
            self._prof_msg = "that window is gone - pin something " \
                             "that exists"
            self._pin_cancel()
            self._repaint("status")
            return
        ok, note = profiles.pin(self._prof_data, self._prof_sel, win,
                                match=ed["match"],
                                open_if_missing=ed["open"],
                                exe=ed["exe"], wait=ed["wait"])
        self._prof_msg = "pinned: %s (seat: where it sits now)" % \
            (key[1] or key[0])[:60] if ok else \
            note or "save or pick a profile first"
        self._pin_edit = _fresh_pin_edit()
        self._restyle_live()
        if ok:
            # Oct 12 (owner ruling): the landed pin touches ONE row
            # of the pins section, in place - no section swap, no
            # cover; the editor repaints (its form changed) and the
            # status fill is now a zero-structure configure.
            # pin() stores a CLONE, not `win`: upsert the literal
            # tail entry or the row loses its [open it]/[via] badges.
            self._pin_row_upsert(prof["wins"][-1], live_row)
            self._repaint("editor", "status")
        else:
            self._repaint("pins", "editor", "status")


    def _pin_row_upsert(self, w, live):
        """Land or refresh exactly ONE row in the on-screen pins
        section (Oct 12). A row already present for this (proc,
        title) identity configures its label in place - the store
        moved the entry to the tail of wins, the visible row keeps
        its slot until the next honest full render. A fresh key
        appends its row into the live ScrollHost inner and hides the
        'nothing pinned yet' placeholder. No live section (a pane
        that has no pins block at all) is a silent no-op: nothing
        visible lies, and the next render shows the pin."""
        key = (w["proc"], w["title"])
        got = getattr(self, "_pin_rows", {}).get(key)
        if got is not None and got[0].winfo_exists():
            got[1].configure(text=self._pin_row_text(w, live))
            return
        inner = getattr(self, "_pins_inner", None)
        if inner is None or not inner.winfo_exists():
            return
        e = getattr(self, "_pins_empty", None)
        if e is not None and e.winfo_exists():
            e.pack_forget()
        # the ONE column _fill_pins laid out: the four-row threshold
        # used to be a layout change (one column -> two) and earned
        # the section swap (gate finding 1); the Oct 15 LIST law
        # retires the second column, so no append crosses a threshold
        # any more - the surgical append always stands, appended at
        # the tail of the single column.
        cols = getattr(self, "_pins_cols", None) or [inner]
        self._pin_row(cols[len(self._pin_rows) % len(cols)], w, live)


    def _prof_pin_all(self):
        # one seat per APP, not per window: a process pin owns every
        # window of its app, so the biggest window of each process
        # gets the seat and its siblings ride along with it
        best = {}
        for w in profiles.windows_now():
            p = (w["proc"] or "").lower()
            if not p:
                continue
            if p not in best or w["rect"][2] * w["rect"][3] > \
                    best[p]["rect"][2] * best[p]["rect"][3]:
                best[p] = w
        if self._prof_data["profiles"].get(self._prof_sel) is None:
            self._prof_msg = "save or pick a profile first"   # dead
            self._repaint("status")                           # selection
            return
        done = sum(1 for w in best.values()
                   if profiles.pin(self._prof_data, self._prof_sel, w,
                                   match="process")[0])
        # the count is what ACTUALLY landed; a live selection with an
        # honest zero says zero, it does not confess a selection lie
        # (gate finding 3: an empty scan is not a dead profile)
        self._prof_msg = "pinned one seat per open app (%d)" % done
        self._repaint("pins", "status")

