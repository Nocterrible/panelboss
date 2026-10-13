"""Manage powercfg overrides.

Size law (~350, 2026-10): the viewer and its typelist apply share a
live-accumulating row model; the docstring below is the protocol.

One row per object (a process, driver or service that either holds a
power request or owns an override entry), and a CHECKBOX PER REQUEST
TYPE - the per-object typelist is the unit powercfg itself thinks in,
and the set form REPLACES the whole list (measured), so a row shows
every type's box and apply ships each changed object's complete
wanted list, survivors included.

The row list ACCUMULATES while the window is open: requests flicker
(a video wake lock blinks with tab visibility), so any object seen
holding since the window opened stays on the books - the 'held'
flags latch. The checkboxes always mirror the LATEST truth (an entry
that vanished really is gone), and refresh re-reads the assistant
dump and folds in whatever new popped up while the user was reading.

Changes stage locally until the apply button shows up; applying is
the same handoff-elevate-then-verify dance the assistant install uses
(truth comes from a fresh dump, never from the exit code). The data
source is the assistant dump, so this window is only opened while the
powercfg assistant is on.

Worker-thread marshaling note: the two after() calls in _refresh and
_save are guarded TclError-and-log - that is the confession, not the
cure. Full queue-marshaling (the ui_events pattern the main window
uses) stays backlog for this window."""
from . import theme
import logging
import threading
import time
import tkinter as tk
from tkinter import BooleanVar

import customtkinter as ctk

from .. import power

log = logging.getLogger("ui")

TRIO = ("process", "driver", "service")

NAMES = {"DISPLAY": "display", "SYSTEM": "system",
         "AWAYMODE": "awaymode", "EXECUTION": "execution",
         "AWAYMODEIDLERESCHEDULE": "idle-reschedule",
         "PERFBOOST": "perfboost", "CONSOLE": "console"}


def _base(name):
    toks = str(name).replace("/", "\\").split("\\")[-1].lower().split()
    return toks[0] if toks else ""


def _row_for(rows, cat, base):
    """Which live request row an override entry folds into (audit MED:
    the old BIDIRECTIONAL substring match let the earlier row eat the
    later row's override - python.exe vs pythonw.exe collided, first
    match in order won). The law now: EXACT base match first;
    substring only when it resolves to EXACTLY ONE candidate row
    (casefold both sides); an ambiguous substring warns and skips the
    fold - never a guess. Returns None when nothing answers."""
    if not base:
        return None
    base = base.casefold()
    exact = [k for k in rows
             if rows[k]["caller"] == cat and k[1].casefold() == base]
    if exact:
        return rows[exact[0]]           # exact first, always
    sub = [k for k in rows
           if rows[k]["caller"] == cat
           and (base in k[1].casefold() or k[1].casefold() in base)]
    if len(sub) == 1:
        return rows[sub[0]]             # the only candidate that fits
    if sub:
        log.warning("overrides: base %r names %d rows (%s); the "
                    "override is not folded into any of them - "
                    "never guess",
                    base, len(sub),
                    ", ".join(sorted(k[1] for k in sub)))
    return None


def merge_seen(seen, result):
    """Fold one powercfg read into the session's accumulating view.

    'overridden' is always the latest truth - a vanished entry is
    gone, the listing is complete every time; 'active' LATCHES,
    because a holder that flickered out between two reads was really
    here, and the whole point is to not forget the 3 a.m. display
    lock that only blinks into existence. Types the set form cannot
    express (perfboost, console - measured: silently dropped on
    write) land in 'drops': shown, never toggleable by us."""
    fresh, order = {}, []

    def touch(caller, obj, base):
        key = (caller, base)
        if key not in fresh:
            fresh[key] = {"key": key, "caller": caller, "object": obj,
                          "label": obj[:70], "active": set(),
                          "overridden": set(), "drops": set()}
            order.append(key)
        return fresh[key]

    for e in (result or {}).get("requests") or []:
        base = _base(e["object"]) or str(e["object"]).lower()
        g = touch(e["caller"], e["object"], base)
        g["active"].add(e["request"])
        if e.get("overridden"):
            g["overridden"].add(e["request"])
    for o in (result or {}).get("override_entries") or []:
        base = _base(o["name"])
        g = _row_for(fresh, o["cat"], base)
        if g is None:
            g = touch(o["cat"], o["name"], base)
        g["overridden"] |= set(o["types"])
        g["drops"] |= set(o["types"]) - set(power.OVERRIDEABLE)
    for k in order:
        g = fresh[k]
        old = seen.get(k)
        if old is not None:
            g["active"] |= old["active"]     # latch survives refresh
        seen[k] = g
    for k, old in seen.items():
        if k not in fresh:
            old["overridden"] = set()        # truth says: gone
            old["drops"] = set()
            # active stays latched: still on the books while open
    return seen


class OverridesWindow(ctk.CTkToplevel):
    def __init__(self, cfg, monitor, skin, parent=None):
        super().__init__(master=parent, fg_color=skin.panel)
        self._parent = parent
        self.title("manage powercfg overrides")
        self.geometry("620x560")
        self.cfg, self.monitor, self.skin = cfg, monitor, skin
        self.seen = {}                        # (caller, base) -> group
        self.desired = {}                     # (caller, base, type) -> want
        self._busy = False
        self._reading = False
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=theme.S_SECTION, pady=(theme.S_ROW, 0))
        ctk.CTkLabel(head, text="manage powercfg overrides",
                     font=skin.font(15, "bold"),
                     **skin.text_style()).pack(side="left")
        self.refresh_button = ctk.CTkButton(head, text="refresh",
                                            width=86, font=skin.font(11),
                                            command=self._read_in,
                                            **skin.secondary())
        self.refresh_button.pack(side="right")
        ctk.CTkLabel(
            self, text="checked = overridden (live truth); 'held' = seen "
            "holding since this window opened; emptying every box clears "
            "the override. The list accumulates while open - refresh "
            "folds in whatever new popped up.",
            font=skin.font(10), wraplength=560, justify="left",
            **skin.text_style("sub")).pack(anchor="w", padx=theme.S_SECTION, pady=(theme.S_FIELD, theme.S_FIELD))
        from .window._scroll import ScrollHost  # here, not at import
        self.list_host = ScrollHost(self, bg=skin.panel)
        self.list_host.pack(fill="both", expand=True, padx=theme.S_SECTION)
        self.listing = self.list_host.inner
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=theme.S_SECTION, pady=(theme.S_FIELD, theme.S_ROW))
        self.status = ctk.CTkLabel(bar, text="", font=skin.font(11),
                                   **skin.text_style("sub"))
        self.status.pack(side="left")
        self.save_button = ctk.CTkButton(bar, text="apply overrides",
                                         width=160, command=self._save,
                                         **skin.primary())
        merge_seen(self.seen, self.monitor.blockers)
        self.status.configure(text="%d objects from the live dump - "
                                   "refresh folds in new ones"
                              % len(self.seen))
        self._redraw()
        # Windows re-activates the parent right after a toplevel maps
        # (measured: this window appeared on top and the settings
        # window yanked focus straight back). transient() declares
        # the parent/child pair so the child also *stays* above it,
        # and the topmost-blink is the trick that actually wins the
        # activation round (plain lift/focus_force lose it).
        if parent is not None:
            try:
                self.transient(parent)
            except Exception:
                pass
        self.after(30, self._claim_focus)

    def _claim_focus(self):
        try:
            self.attributes("-topmost", True)
            self.lift()
            self.focus_force()
            self.after(140, self._drop_topmost)
        except Exception:
            pass                            # closed inside 30 ms

    def _drop_topmost(self):
        try:                                # the window may be gone by
            self.attributes("-topmost", False)   # now; a raise here is a
        except Exception:                   # traceback pythonw never
            pass                            # lets anybody see

    # ------------------------------------------------------------- rows ---
    def _redraw(self):
        for w in self.listing.winfo_children():
            w.destroy()
        if not self.seen:
            ctk.CTkLabel(self.listing,
                         text="no power data yet - the powercfg "
                              "assistant must be ticking",
                         font=self.skin.font(11),
                         **self.skin.text_style("sub")).pack(anchor="w",
                                                             pady=theme.S_ROW)
        for g in sorted(self.seen.values(), key=lambda x: x["label"]):
            row = ctk.CTkFrame(self.listing, fg_color="transparent")
            row.pack(fill="x", pady=theme.S_FIELD)
            ctk.CTkLabel(
                row, anchor="w", text=g["label"],
                font=self.skin.font(11),
                text_color=(self.skin.danger
                            if "DISPLAY" in g["active"]
                            and "DISPLAY" not in g["overridden"]
                            else self.skin.paused if g["overridden"]
                            else self.skin.text)).pack(anchor="w")
            bits = [g["caller"]]
            if g["overridden"]:
                bits.append("overridden: " + ", ".join(
                    NAMES.get(t, t.lower())
                    for t in sorted(g["overridden"])))
            else:
                bits.append("not overridden")
            ctk.CTkLabel(row, anchor="w", text=" · ".join(bits),
                         font=self.skin.font(10),
                         **self.skin.text_style("sub")).pack(anchor="w")
            boxes = ctk.CTkFrame(row, fg_color="transparent")
            boxes.pack(anchor="w")
            live = g["caller"] in TRIO
            # grid, 3 per row: the scrollable frame scrolls vertically
            # only, one long row of pack(side=left) would clip off-canvas
            # (this ctk's checkbox colors are fg/hover/checkmark - the
            # checkbox_checked_color names of newer releases raise,
            # measured; and text MUST be given or the widget prints
            # its class name)
            for i, t in enumerate(power.OVERRIDEABLE):
                var = BooleanVar(value=bool(self.desired.get(
                    g["key"] + (t,), t in g["overridden"])))
                cb = ctk.CTkCheckBox(
                    boxes, font=self.skin.font(10), width=172,
                    text_color=self.skin.text,
                    text=NAMES.get(t, t.lower())
                         + (" held" if t in g["active"] else ""),
                    variable=var, checkbox_width=14, checkbox_height=14,
                    fg_color=self.skin.accent,
                    hover_color=self.skin.accent_hover,
                    border_color=self.skin.border_raised,
                    text_color_disabled=self.skin.txt3,
                    command=lambda k=g["key"], t=t, v=var:
                    self._toggled(k, t, bool(v.get())))
                if not live:
                    cb.configure(state="disabled")
                cb.grid(row=i // 3, column=i % 3, sticky="w")
            j = len(power.OVERRIDEABLE)
            for t in sorted(g["drops"]):    # perfboost/console class:
                cb = ctk.CTkCheckBox(       # the set form DROPS them
                    boxes, font=self.skin.font(10), width=172,  # (measured) -
                    text_color=self.skin.subtext,               # visible, never
                    text=NAMES.get(t, t.lower())                # ours to touch
                         + " (drops on edit)",
                    variable=BooleanVar(value=True),
                    checkbox_width=14, checkbox_height=14,
                    fg_color=self.skin.button,
                    hover_color=self.skin.button,
                    border_color=self.skin.border_raised,
                    text_color_disabled=self.skin.txt3,
                    state="disabled")
                cb.grid(row=j // 3, column=j % 3, sticky="w")
                j += 1
        self._sync()

    # ------------------------------------------------------------ diff ----
    def _toggled(self, key, t, want):
        self.desired[key + (t,)] = want
        self._sync()

    def _diff(self):
        by = {}
        for (caller, base, t), want in self.desired.items():
            by.setdefault((caller, base), {})[t] = want
        ops = []
        for g in getattr(self, "seen", {}).values():
            ch = by.get(g["key"])
            if not ch:
                continue
            now = set(g["overridden"]) & set(power.OVERRIDEABLE)
            types = set(now)
            for t, want in ch.items():
                if want:
                    types.add(t)
                else:
                    types.discard(t)
            if types == now:
                continue                    # toggled off and back on
            ops.append({"caller": g["caller"], "object": g["object"],
                        "types": sorted(types)})
        return ops

    def _sync(self):
        n = len(self._diff())
        if n and not self._busy:
            self.save_button.configure(text="apply overrides (%d)" % n)
            if not self.save_button.winfo_manager():
                self.save_button.pack(side="right", padx=(0, theme.S_ROW))
            self.status.configure(
                text="%d object(s) staged - apply elevates once" % n,
                text_color=self.skin.subtext)
        else:
            self.save_button.pack_forget()

    # ------------------------------------------------------------- apply --
    def _read_in(self):
        """Fresh dump on a worker (the assistant task needs a few
        seconds to re-run and write it); answers ride after() which
        is safe - this click proves the mainloop is alive."""
        if self._reading:
            return
        self._reading = True
        self.refresh_button.configure(text="reading...")

        def work():
            try:
                rep = power.requests(assistant=bool(
                    self.cfg["power"]["assistant_task"]))
                try:
                    self.after(0, lambda: self._merged(rep))
                except tk.TclError:          # the window closed while
                    log.exception(          # the read ran: confess, do
                        "overrides refresh lost the marshal")  # not evaporate
            except Exception:
                log.exception("overrides refresh crashed")
        threading.Thread(target=work, daemon=True).start()

    def _merged(self, rep):
        try:
            self.refresh_button.configure(text="refresh")
            merge_seen(self.seen, rep)
            if rep.get("error"):
                self.status.configure(text=rep["error"],
                                      text_color=self.skin.paused)
            else:
                self.status.configure(
                    text="%d objects seen since opened - read %s" % (
                        len(self.seen), time.strftime("%H:%M:%S")),
                    text_color=self.skin.subtext)
            self._redraw()
        except Exception:
            log.exception("override merge crashed")

    def _save(self):
        ops = self._diff()
        if not ops or self._busy:
            return
        self._busy = True
        self._sync()
        self.status.configure(
            text="waiting for the admin confirm - check the taskbar "
                 "if no prompt is visible...",
            text_color=self.skin.paused)

        def work():
            try:
                ok, msg, fresh = power.apply_overrides(
                    ops,
                    assistant=bool(self.cfg["power"]["assistant_task"]))
                try:
                    self.after(0, lambda: self._applied(ok, msg, fresh))
                except tk.TclError:          # the window closed while
                    log.exception(          # the apply ran: confess, do
                        "overrides apply lost the marshal")    # not evaporate
            except Exception:
                log.exception("overrides apply crashed")
        threading.Thread(target=work, daemon=True).start()

    def _applied(self, ok, msg, fresh):
        self._busy = False
        self.desired.clear()
        self.status.configure(text=msg,
                              text_color=self.skin.ok if ok
                              else self.skin.paused)
        if fresh and not fresh.get("error"):
            merge_seen(self.seen, fresh)
        self._redraw()
