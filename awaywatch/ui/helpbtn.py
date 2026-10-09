"""Hover help: a round "?" beside any setting, the detailed story in
the tooltip, so the rows themselves stay short and honest.

One tip at a time, and the pointer may travel FROM the button ONTO
the tip - a tooltip that dies the moment you move toward it is a
teaser, not documentation. Appears after a short hover (a sweep of
the mouse across the window must not strobe the whole page), leaves
when both the button and the tip are abandoned, and a click PINS it
for the hands-free readers. The window is takefocus=() + topmost:
showing a tooltip must never steal the keyboard (measured the hard
way in every toolkit that forgot it).
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

SHOW_MS = 350
HIDE_MS = 150
WIDTH = 360


class Tips:
    def __init__(self, skin, root):
        self.skin = skin
        self.root = root
        self.tip = None
        self.pinned = False
        self.text = ""
        self.job = None

    def button(self, parent, text):
        """Build the "?" widget; the caller places it (pack/grid)."""
        b = ctk.CTkButton(parent, text="?", width=22, height=22,
                          corner_radius=11, border_width=0,
                          font=self.skin.font(11, "bold"),
                          fg_color=self.skin.field_bg,
                          hover_color=self.skin.button_hover,
                          text_color=self.skin.subtext)
        b.bind("<Enter>", lambda e=None: self._schedule(text, b))
        b.bind("<Leave>", lambda e=None: self._hide_soon())
        b.bind("<Button-1>", lambda e=None: self.toggle(text, b))
        return b

    # ------------------------------------------------------------ timing --
    def _cancel(self):
        if self.job is not None:
            try:
                self.root.after_cancel(self.job)
            except Exception:
                pass
            self.job = None

    def _schedule(self, text, b):
        self._cancel()
        self.pinned = False             # a new hover always takes over
        try:
            self.job = self.root.after(SHOW_MS,
                                       lambda: self._show(text, b))
        except Exception:               # half-dead window
            self.tip = None

    def _hide_soon(self):
        self._cancel()
        if self.pinned:
            return
        try:
            self.job = self.root.after(HIDE_MS, self.kill)
        except Exception:
            self.tip = None

    def toggle(self, text, b):
        self._cancel()
        if self.pinned and self.tip is not None and self.text == text:
            self.kill()                          # click again = unpin
            return
        self._show(text, b)
        self.pinned = True                       # survives the leave

    # ------------------------------------------------------------ window --
    def _show(self, text, b):
        self.text = text
        self._kill_tip()
        try:
            x = b.winfo_rootx() + b.winfo_width() + 8
            y = b.winfo_rooty() + b.winfo_height() + 6
        except Exception:
            return                             # button vanished mid-hover
        if not text:
            return
        tip = tk.Toplevel(self.root, takefocus=())
        tip.withdraw()
        tip.transient(self.root)               # dies with the window
        frame = tk.Frame(tip, bg=self.skin.border, padx=1, pady=1)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=text, bg=self.skin.panel, fg=self.skin.text,
                 font=("Segoe UI", 10), justify="left", anchor="nw",
                 wraplength=WIDTH - 24, padx=10, pady=8).pack(anchor="nw")
        tip.update_idletasks()
        w, h = tip.winfo_width(), tip.winfo_height()
        x = max(min(x, self.root.winfo_rootx() + self.root.winfo_width()
                   - w - 8), 0)
        y = max(y, 0)
        tip.geometry("+%d+%d" % (x, y))
        tip.attributes("-topmost", True)        # above borderless windows
        tip.deiconify()
        for widget in (tip, frame) + tuple(frame.winfo_children()):
            widget.bind("<Enter>", lambda e=None: self._cancel())
            widget.bind("<Leave>", lambda e=None: self.kill())
        self.tip = tip

    def _kill_tip(self):
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None
        self.pinned = False

    def kill(self):
        """Now: every tab change, every skin rebuild, every close."""
        self._cancel()
        self._kill_tip()
