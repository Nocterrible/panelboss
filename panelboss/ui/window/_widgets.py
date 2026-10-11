"""Shared card/row/section widgets, the sleep prompt, the
pin editor's blank slate, and SkewCombo - the tk.Menubutton
drop-in that replaced all 18 CTkOptionMenus (UI-1b2: each CTk
dropdown was ~30 canvas-backed labels built at grid time,
~1 s of the 1.44 s build median; this file earns its 230 lines
by being the whole answer to that measurement).
"""

from __future__ import annotations

import tkinter as tk

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



class SkewCombo(tk.Menubutton):
    """CTkOptionMenu drop-in, drawn by plain Tk.

    The measured hot spot: the panel's eighteen CTkOptionMenus together
    carried ~1 s of the 1.44 s build median (uitime combo1), because
    every CTk dropdown is a hidden frame of ~30 canvas-backed CTkLabels
    built at grid time. The Tk version is one Menubutton plus one native
    Menu - and Tk menus ARE colorable, unlike the ttk.Combobox popup
    (measured: Windows paints that one native white no matter the
    style). Square corners are the accepted trade for the speed.

    Call sites spread **skin.menu_style() unchanged, so every CTk-flavored
    kwarg is swallowed at build AND on configure. The contract the sites
    and the UI suites actually use: set/get, configure(values=...) (order
    preserved), cget("values") answering a real LIST (the suites str()
    it and compare a list repr), cget("text") answering the shown value,
    and the raw _command attribute (profiles_ui_test dispatches
    _command(VALUE) itself - no wrapping allowed)."""

    # menu_style() trio keys + the other CTk menu options; corner_radius
    # is ignored on purpose, the rest would reach Tk as nonsense
    _IGNORED = ("fg_color", "button_color", "button_hover_color",
                "text_color", "corner_radius", "dropdown_fg_color",
                "dropdown_hover_color", "dropdown_text_color",
                "height", "anchor")

    def __init__(self, master, values=(), width=None, command=None,
                 **style):
        self._command = command                    # raw, tests read this
        self._values = list(values)
        self._var = tk.StringVar(master, value="")
        btn = style.get("button_color") or "#4a5568"
        hov = style.get("button_hover_color") or "#354052"
        txt = style.get("text_color") or "#dbe2ee"
        mbg = (style.get("dropdown_fg_color") or style.get("fg_color")
               or "#242833")                       # fg_color is field_bg
        mhov = style.get("dropdown_hover_color") or hov
        kw = dict(textvariable=self._var, bg=btn, fg=txt,
                  activebackground=hov, activeforeground=txt,
                  relief="raised", borderwidth=1, highlightthickness=1,
                  padx=6, pady=3)
        # DO NOT set relief flat + borderwidth 0: the button collapses to
        # a 1px sliver (measured trap). px -> chars at ~10 px/char
        if width:
            kw["width"] = int(width / 10)
        tk.Menubutton.__init__(self, master, **kw)
        self._menu = tk.Menu(self, tearoff=0, bg=mbg, fg=txt,
                             activebackground=mhov, activeforeground=txt)
        self["menu"] = self._menu
        self._rebuild()
        self.set(values[0] if values else "")

    def _rebuild(self):
        m = self._menu
        m.delete(0, "end")
        for v in self._values:
            # no variable= on the radiobutton: a CTk dropdown shows no
            # check either - the pick only relabels the button
            m.add("radiobutton", label=str(v),
                  command=lambda v=v: self._fire(v))

    def _fire(self, value):
        # CTk fires command only on an actual change; re-picking the
        # shown item must not rebuild the whole panel behind _skin_changed
        if self._var.get() == str(value):
            return
        self._var.set(str(value))
        if self._command is not None:
            self._command(value)

    # ------------------------------------------------ CTk menu contract --
    def set(self, value):
        self._var.set(str(value))

    def get(self):
        return self._var.get()

    def configure(self, cnf=None, **kw):
        if isinstance(cnf, dict):
            kw = dict(cnf, **kw)
            cnf = None
        elif cnf is not None:                      # legacy pair-list form
            return tk.Menubutton.configure(self, cnf, **kw)
        if "values" in kw:
            self._values = list(kw.pop("values"))  # order preserved
            self._rebuild()
        state = kw.pop("state", None)
        for key in self._IGNORED:
            kw.pop(key, None)                      # re-style kwargs: the
        # skin switch rebuilds whole windows, so the colors taken at
        # build time stay the truth for this widget's life
        if state is not None:
            # no call site drives state= today; CTk's "readonly" has no
            # Tk twin, so it degrades to disabled - a button that shows
            # but does not post is the same visible outcome. Assign via
            # tk.Menubutton.configure: self["state"]= would re-enter this
            # override through Widget.__setitem__ and recurse forever.
            kw.setdefault("state", "disabled"
                          if state in ("disabled", "readonly") else "normal")
        if kw:
            return tk.Menubutton.configure(self, **kw)
        return None

    config = configure
    __call__ = configure

    def cget(self, key):
        if key == "values":
            return list(self._values)              # suites str() this and
        # compare the list repr ("['640x480']") - a tuple would differ
        if key == "text":
            return self.get()                      # tk would name the var
        return tk.Menubutton.cget(self, key)

    __getitem__ = cget

    def destroy(self):
        try:
            self._menu.destroy()
        except Exception:
            pass                                   # parent already gone
        tk.Menubutton.destroy(self)


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

