"""Pin editor verbs: select, browse, wait, commit.
"""

from __future__ import annotations

import logging

from ... import profiles
from ._widgets import _fresh_pin_edit

log = logging.getLogger("ui")


class _PinMixin:
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
        editor, conditions as saved, ready to change and update"""
        try:
            wait = max(5, min(600, int(w.get("wait") or 30)))
        except (TypeError, ValueError):
            wait = 30
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


    def _pin_remove(self, w):
        profiles.unpin(self._prof_data, self._prof_sel, w["proc"],
                       w["title"])
        if self._pin_edit["key"] == (w["proc"], w["title"]):
            self._pin_edit = _fresh_pin_edit()
        self._prof_msg = "forgot: %s" % (w["title"] or w["proc"])[:60]
        self._repaint("pins", "editor", "status")


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
        win = next((w for w in profiles.windows_now()
                    if (w["proc"], w["title"]) == key), None)
        if win is None:                # the window closed since the
            win = next((w for w in     # scan: a pin being edited
                self._prof_data["profiles"][self._prof_sel]["wins"]
                if (w["proc"], w["title"]) == key), None)
        if win is None:
            self._prof_msg = "that window is gone - pin something " \
                             "that exists"
            self._pin_cancel()
            self._repaint("status")
            return
        profiles.pin(self._prof_data, self._prof_sel, win,
                     match=ed["match"], open_if_missing=ed["open"],
                     exe=ed["exe"], wait=ed["wait"])
        self._prof_msg = "pinned: %s (seat: where it sits now)" % \
            (key[1] or key[0])[:60]
        self._pin_edit = _fresh_pin_edit()
        self._restyle_live()
        self._repaint("pins", "editor", "status")


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
        for w in best.values():
            profiles.pin(self._prof_data, self._prof_sel, w,
                         match="process")
        self._prof_msg = "pinned one seat per open app (%d)" % \
            len(best)
        self._repaint("pins", "status")

