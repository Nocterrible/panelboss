"""Shared card/row/section widgets, the sleep prompt and
the pin editor's blank slate.
"""

from __future__ import annotations

import customtkinter as ctk

def set_text(widget, text):
    """Write a label/button text only when it actually CHANGED. Every
    CTkLabel/CTkButton is a software canvas: a no-op configure(text=...)
    still redraws the whole rounded widget (the tick loop paid a full
    repaint per unchanged label - profiled). cget() answers plain on
    CTk widgets and on tk ones alike (measured)."""
    try:
        if widget.cget("text") == text:
            return
    except Exception:
        pass                        # exotic widget: write blindly
    widget.configure(text=text)


def _fresh_pin_edit():
    """The pin editor's blank slate, in one place so no reset ever
    forgets a field the editor grew later."""
    return {"key": None, "pick": None, "match": "process",
            "open": False, "wait": 30, "exe": None}


class _SleepPrompt(ctk.CTkToplevel):
    """The one sleep button's chooser: a slider for minutes, ok or
    cancel. Built the Deprompt way (transient, the measured focus
    claim) - and the minutes only become an event on ok: dragging
    past a number must not itself put the watch to sleep."""

    def __init__(self, parent, skin, on_ok):
        super().__init__(parent)
        self._on_ok = on_ok
        self.title("sleep the watch")
        self.resizable(False, False)
        self.configure(fg_color=skin.bg)
        self.transient(parent)           # stays above the settings
        self._lbl = ctk.CTkLabel(self, text="wake again in 30 min",
                                 font=skin.font(15, "bold"),
                                 **skin.text_style())
        self._lbl.pack(padx=20, pady=(14, 0))
        self._sld = ctk.CTkSlider(self, from_=5, to=180,
                                  number_of_steps=35, scroll_step=5,
                                  command=self._show)
        self._sld.set(30)
        self._sld.pack(padx=20, pady=(10, 0))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(14, 14))
        ctk.CTkButton(row, text="ok", command=self._go,
                      **skin.primary()).pack(side="right", padx=(8, 0))
        ctk.CTkButton(row, text="cancel", command=self.destroy,
                      **skin.secondary()).pack(side="right")
        self.update_idletasks()
        # centre on the window it belongs to: a 300-wide dialog at
        # the screen corner reads as somebody else's
        x = parent.winfo_rootx() + (parent.winfo_width() - 320) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - 150) // 3
        self.geometry("+%d+%d" % (max(x, 0), max(y, 0)))
        self.after(30, self._claim_focus)

    def _show(self, value):
        # snap to 5 despite number_of_steps: the callback value is a
        # float, and "wake again in 34.999999 min" is not a label
        self._lbl.configure(text="wake again in %d min"
                                  % (round(float(value) / 5) * 5))

    def _go(self):
        minutes = round(float(self._sld.get()) / 5) * 5
        self.destroy()
        self._on_ok(minutes)

    def _claim_focus(self):
        try:
            self.attributes("-topmost", True)
            self.lift()
            self.focus_force()
            self.after(140, self._drop_topmost)
        except Exception:
            pass                             # closed inside 30 ms

    def _drop_topmost(self):
        try:
            self.attributes("-topmost", False)
        except Exception:
            pass                             # gone by the time we drop



class _WidgetsMixin:
    def _card(self, parent, title, sub=""):
        frame = ctk.CTkFrame(parent, **self.skin.panel_style())
        frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(frame, text=title, font=self.skin.font(15, "bold"),
                     **self.skin.text_style()).pack(anchor="w", padx=14,
                                               pady=(10, 0))
        if sub:
            # wraplength or the label clips: the sub lines are longer
            # than any column, and clipped text reads like a bug in the
            # app, not in the label
            ctk.CTkLabel(frame, text=sub, font=self.skin.font(11),
                         wraplength=480, justify="left", anchor="w",
                         **self.skin.text_style("sub")).pack(
                anchor="w", padx=14)
        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=(6, 12))
        return inner


    def _row(self, parent, label, tip=""):
        """One settings row: label left, widget right. Widgets are
        created ON THE ROW so grid only ever manages children of the
        row, pack only ever manages children of the card. The label
        cell hosts the "?" beside the text."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=2)
        row.grid_columnconfigure(0, weight=1)
        cell = ctk.CTkFrame(row, fg_color="transparent")
        cell.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(cell, text=label, font=self.skin.font(12),
                     **self.skin.text_style()).pack(side="left")
        if tip:
            self.tips.button(cell, tip).pack(side="left", padx=(6, 0))
        return row


    def _section(self, name, pady=(0, 0)):
        """A rebuildable slice of the pane. The first call (during a
        full fill) makes the frame; a later call just empties it, so a
        click repaints ONE section, not all forty widgets."""
        f = self._psec.get(name)
        if f is None:
            f = self._psec[name] = ctk.CTkFrame(self._prof_detail,
                                                fg_color="transparent")
            f.pack(fill="x", pady=pady)
        else:
            for w in f.winfo_children():
                w.destroy()
        return f

