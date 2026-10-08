"""Manage powercfg overrides.

Lists every live power request and every override on the machine, one
row each with a toggle; a holder that is also overridden (the usual
state after a lifetime of powercfg tinkering) consolidates into ONE
row saying both. Toggling queues the matching powercfg
/requestsoverride add/remove; the Save button only appears while a
change waits, and applying it is the same handoff-elevate-then-verify
dance the assistant install uses (truth comes from a fresh dump, never
from the exit code). The data source is the assistant dump, so this
window is only opened while the powercfg assistant is on."""
import logging
import threading

import customtkinter as ctk

from .. import power

log = logging.getLogger("ui")

TRIO = ("process", "driver", "service")


def _base(name):
    return (str(name).replace("/", "\\").split("\\")[-1].lower().split()
            or [""])[0] if str(name).split() else ""


def rows_from(result):
    """Pure model: one row per (request | override-per-type). A
    request already overridden claims its override entry, so the pair
    never shows twice."""
    rows = []
    claimed = set()
    for e in (result or {}).get("requests") or []:
        caller, obj, req = e["caller"], e["object"], e["request"]
        rows.append({"key": (caller, obj, req),
                     "label": e["text"][:70],
                     "caller": caller, "object": obj, "request": req,
                     "active": True,
                     "overridden": bool(e.get("overridden")),
                     "overridable": caller in TRIO
                                    and req in power.OVERRIDEABLE})
        if e.get("overridden"):
            b = _base(obj) or obj.lower()
            for o in (result.get("override_entries") or []):
                if b and (b in o["name"] or o["name"] in b):
                    claimed.add(id(o))
    for o in (result or {}).get("override_entries") or []:
        if id(o) in claimed:
            continue
        for t in sorted(o["types"]):
            rows.append({"key": ("override", o["cat"], o["name"], t),
                         "label": o["name"][:70],
                         "caller": o["cat"], "object": o["name"],
                         "request": t, "active": False, "overridden": True,
                         "overridable": o["cat"] in TRIO
                                        and t in power.OVERRIDEABLE})
    return rows


class OverridesWindow(ctk.CTkToplevel):
    def __init__(self, cfg, monitor, skin, parent=None):
        super().__init__(master=parent, fg_color=skin.panel)
        self.title("manage powercfg overrides")
        self.geometry("580x540")
        self.cfg, self.monitor, self.skin = cfg, monitor, skin
        self.desired = {}                       # key -> wanted override
        self._busy = False
        ctk.CTkLabel(self, text="manage powercfg overrides",
                     font=skin.font(15, "bold"),
                     **skin.text_style()).pack(anchor="w", padx=14,
                                               pady=(10, 0))
        ctk.CTkLabel(
            self, text="toggles mark what should be overridden; the "
            "apply button elevates once and the result is verified "
            "from a fresh powercfg read",
            font=skin.font(10), wraplength=520, justify="left",
            **skin.text_style("sub")).pack(anchor="w", padx=14, pady=(2, 6))
        self.listing = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=skin.button,
            scrollbar_fg_color=skin.panel)
        self.listing.pack(fill="both", expand=True, padx=14)
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=14, pady=(6, 10))
        self.status = ctk.CTkLabel(bar, text="", font=skin.font(11),
                                   **skin.text_style("sub"))
        self.status.pack(side="left")
        self.save_button = ctk.CTkButton(bar, text="apply overrides",
                                         width=150, command=self._save,
                                         **skin.primary())
        self._refresh()

    # ------------------------------------------------------------- rows ---
    def _refresh(self, src=None):
        for w in self.listing.winfo_children():
            w.destroy()
        self.desired.clear()
        rows = rows_from(src if src is not None else self.monitor.blockers)
        self.rows = rows
        if not rows:
            ctk.CTkLabel(self.listing,
                         text="no power data yet - the powercfg "
                              "assistant must be ticking",
                         font=self.skin.font(11),
                         **self.skin.text_style("sub")).pack(anchor="w",
                                                             pady=8)
        for r in rows:
            row = ctk.CTkFrame(self.listing, fg_color="transparent")
            row.pack(fill="x", pady=2)
            txt = ctk.CTkFrame(row, fg_color="transparent")
            txt.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(
                txt, anchor="w", justify="left",
                text=("*OVERRIDE " if r["overridden"] else "")
                     + r["label"],
                font=self.skin.font(11),
                text_color=(self.skin.danger if r["active"]
                            and r["request"] == "DISPLAY" else
                            self.skin.paused if r["overridden"]
                            else self.skin.text)).pack(anchor="w")
            state = "holding the display now" if (r["active"]
                                                  and r["request"] ==
                                                  "DISPLAY") else \
                ("holding now" if r["active"] else "not holding now")
            ctk.CTkLabel(txt, anchor="w", justify="left",
                         text="%s %s · %s%s" % (
                             r["caller"], r["request"].title(), state,
                             "" if r["overridable"]
                             else " · not overridable"),
                         font=self.skin.font(10),
                         **self.skin.text_style("sub")).pack(anchor="w")
            if r["overridable"]:
                sw = ctk.CTkSwitch(row, text="", width=36,
                                   progress_color=self.skin.accent,
                                   border_color=self.skin.border)
                sw.pack(side="right", padx=(6, 0))
                sw.select() if r["overridden"] else sw.deselect()
                sw.configure(command=lambda k=r["key"], s=sw:
                             self._toggled(k, bool(s.get())))
        self._sync()

    # ------------------------------------------------------------ diff ----
    def _toggled(self, key, want):
        self.desired[key] = want
        self._sync()

    def _diff(self):
        ops = []
        for r in getattr(self, "rows", []):
            want = self.desired.get(r["key"])
            if want is not None and bool(want) != r["overridden"]:
                ops.append({"add": bool(want), "caller": r["caller"],
                            "object": r["object"],
                            "request": r["request"]})
        return ops

    def _sync(self):
        n = len(self._diff())
        if n and not self._busy:
            self.save_button.configure(
                text="apply overrides (%d)" % n)
            if not self.save_button.winfo_manager():
                self.save_button.pack(side="right")
            self.status.configure(
                text="changes pending - apply elevates once",
                text_color=self.skin.subtext)
        else:
            self.save_button.pack_forget()

    # ------------------------------------------------------------- apply --
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
                self.after(0, lambda: self._applied(ok, msg, fresh))
            except Exception:
                log.exception("overrides apply crashed")
        threading.Thread(target=work, daemon=True).start()

    def _applied(self, ok, msg, fresh):
        self._busy = False
        self.status.configure(text=msg,
                              text_color=self.skin.ok if ok
                              else self.skin.paused)
        self._refresh(fresh or None)
