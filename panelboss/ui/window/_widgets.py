"""Shared card/row/section widgets, the sleep prompt, the pin
editor's blank slate, and SkewCombo - the tk.Menubutton drop-in
that replaced all 18 CTkOptionMenus. The UI-1b2 measurement that
earns this file's length is documented on the class.

SIZE LAW: just over 300. _section (the profiles pane's double-buffer
paint seam) stays here with its _repaint counterpart in _profiles.py:
one cohesive mechanism, and a second mixin split costs more MRO and
attention tax than a header note. The optional real split is lifting
SkewCombo + _fresh_pin_edit (~90 lines) into _combo.py."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from .. import theme
from ._hints import HINT_WRAP

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
        self._lbl.pack(padx=theme.S_SECTION, pady=(theme.S_SECTION, 0))
        self._sld = ctk.CTkSlider(self, from_=5, to=180,
                                  number_of_steps=35, scroll_step=5,
                                  command=self._show,
                                  **skin.slider_style())
        self._sld.set(30)
        self._sld.pack(padx=theme.S_SECTION, pady=(theme.S_ROW, 0))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=theme.S_SECTION,
                 pady=(theme.S_SECTION, theme.S_SECTION))
        ctk.CTkButton(row, text="ok", command=self._go,
                      **skin.primary()).pack(side="right",
                                             padx=(theme.S_ROW, 0))
        ctk.CTkButton(row, text="cancel", command=self._retire,
                      **skin.secondary()).pack(side="right")
        self.update_idletasks()
        # centre on the window it belongs to: a 300-wide dialog at
        # the screen corner reads as somebody else's
        x = parent.winfo_rootx() + (parent.winfo_width() - 320) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - 150) // 3
        self.geometry("+%d+%d" % (max(x, 0), max(y, 0)))
        self.after(30, self._claim_focus)
        # the X too (gate finding 1, the wave's own crash law): the
        # title-bar close lands on tk's protocol callback with this
        # toplevel as its target - the direct-destroy ban applies to
        # it exactly as to the buttons; the same scheduled retire
        # takes both (0xc0000374 is double-destroy, not button-specific)
        self.protocol("WM_DELETE_WINDOW", self._retire)

    def _show(self, value):
        # snap to 5 despite number_of_steps: the callback value is a
        # float, and "wake again in 34.999999 min" is not a label
        self._lbl.configure(text="wake again in %d min"
                                  % (round(float(value) / 5) * 5))

    def _retire(self):
        # scheduled destroy (owner crash law): this dialog's buttons
        # reach it from their own command callbacks, and a toplevel
        # destroyed under a live callback is the 0xc0000374 double-
        # destroy shape. Withdraw now, destroy on the loop's stack.
        self.withdraw()
        self.after(0, self.destroy)

    def _go(self):
        minutes = round(float(self._sld.get()) / 5) * 5
        self._retire()
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
                "height", "anchor", "font")

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
                  # tk's default highlight ring is LIGHT GRAY - on the
                  # dark panel it was the one non-design pixel left in
                  # the UI (screenshot-verified); sink it into the
                  # face and let the raised relief carry the edge
                  highlightbackground=mbg, highlightcolor=hov,
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


def desk_position(rows, x, y, w, h):
    """The monitor's RELATIVE slot on the desk (owner law, Oct 15):
    a name disambiguates panels only when the EDID strings differ;
    the geometry disambiguates three identical ones. A pure
    function over the live row list so every card says the same
    word for the same desk. Rows without geometry are skipped -
    no row raises inside a card redraw. A single-row desk gets no
    word: with one panel the position IS the desk and says
    nothing. Parts that cannot vary are omitted, not faked:
    side-by-side rows share their top edge and the vertical half
    of the word is vacuous; a stack shares its x span and the
    horizontal half is."""
    edges = []
    for rx, ry, rw, rh in rows:
        if not all(isinstance(v, (int, float))
                   for v in (rx, ry, rw, rh)):
            continue
        edges.append((rx, ry, rx + rw, ry + rh))
    if len(edges) < 2:
        return ""
    min_x = min(e[0] for e in edges)
    max_r = max(e[2] for e in edges)
    min_y = min(e[1] for e in edges)
    max_b = max(e[3] for e in edges)
    if max_r - min_x <= 0:
        h_part = ""
    elif x == min_x:
        h_part = "left"
    elif x + w == max_r:
        h_part = "right"
    else:
        h_part = "middle"
    if max_b - min_y <= 0:
        v_part = ""
    elif y == min_y:
        v_part = "top"
    elif y + h == max_b:
        v_part = "bottom"
    else:
        v_part = "middle"
    parts = [p for p in (v_part, h_part) if p]
    return (" [%s]" % " ".join(parts)) if parts else ""


class _WidgetsMixin:
    def _fit_wrap(self, container, label, pad=None):
        """Keep a wrapped label inside its container at ANY width (owner
        Oct 15, the NO-CLIPPING word). HINT_WRAP was a fixed 480 and a
        card can be narrower than that on a small desk or a narrow column
        - a wraplength wider than its own box clips, silently. The honest
        wrap is the container's own width minus its padding, recomputed on
        every resize; the diff guard is the loop-breaker (a configure that
        does not change the number must not re-fire the layout)."""
        step = theme.S_SECTION if pad is None else pad
        seen = [None]

        def fit(event):
            want = max(200, int(event.width) - 2 * step)
            if want == seen[0]:
                return
            seen[0] = want
            try:
                label.configure(wraplength=want)
            except Exception:
                pass                     # dying card: nothing to fit
        try:
            container.bind("<Configure>", fit, add="+")
        except Exception:
            pass

    def _two_columns(self, parent, gutter=None):
        """THE ONE COLUMN RHYTHM (owner Oct 15, spatial similarity: "all
        cards should occupy a uniform footprint - same widths, same column
        rhythm, same header band height across every tab"). Two columns of
        equal width filling the page, one gutter token between them, flush
        to both page edges - every tab rides this, so the eye finds the
        grid without hunting.

        Why equal: pack hands every -expand sibling an equal share of the
        LEFTOVER space, so two identical requested widths land identical.
        The width below is a FLOOR (the HINT_WRAP budget: 480 + its two
        section pads), never the final number. Why pack, not grid: the
        pinned-apps suite asserts both profile columns are pack-managed,
        and one rhythm everywhere is the point."""
        g = theme.S_SECTION if gutter is None else gutter
        floor = HINT_WRAP + 2 * theme.S_SECTION
        left = ctk.CTkFrame(parent, width=floor, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True)
        right = ctk.CTkFrame(parent, width=floor, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=(g, 0))
        return left, right

    def _card(self, parent, title, sub=""):
        # the card is INVISIBLE (owner Oct 15: "I don't like the look of
        # cards") - page fill, no border. The section GAP is therefore
        # load-bearing: a whole S_PAGE of air under every card plus the
        # header's own S_SECTION above it is what makes two adjacent
        # blocks read as two blocks at all.
        frame = ctk.CTkFrame(parent, **self.skin.panel_style())
        frame.pack(fill="x", pady=(0, theme.S_PAGE))
        ctk.CTkLabel(frame, text=title, font=self.skin.font(15, "bold"),
                     **self.skin.text_style()).pack(
            anchor="w", padx=theme.S_SECTION, pady=(theme.S_SECTION, 0))
        if sub:
            # wraplength or the label clips: the sub lines are longer
            # than any column. Now FITTED to the card's live width
            # (_fit_wrap) instead of a fixed HINT_WRAP, so a narrow
            # column wraps honestly instead of cutting a sentence off.
            # The sub doubles as the heading's hover bubble (UI-1c
            # reversal: the bubbles are back, on the labels)
            sub_lbl = ctk.CTkLabel(frame, text=sub, font=self.skin.font(11),
                                   wraplength=HINT_WRAP, justify="left",
                                   anchor="w", **self.skin.text_style("sub"))
            sub_lbl.pack(anchor="w", padx=theme.S_SECTION)
            self._fit_wrap(frame, sub_lbl)
            sub_lbl.bind("<Enter>",
                         lambda e=None: self.tips._schedule(sub, sub_lbl),
                         add="+")
            sub_lbl.bind("<Leave>", lambda e=None: self.tips._hide_soon(),
                         add="+")
        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=theme.S_SECTION,
                   pady=(theme.S_FIELD, theme.S_ROW))
        return inner

    def _hint(self, parent, tip, chars=90, **pack):
        """Documented no-op (UI-1c reversal: the hover bubbles are back,
        riding the controls themselves). The signature survives so every
        call site compiles unchanged; no caller chains the return."""
        return None

    def _row(self, parent, label, tip="", hint_chars=90):
        """One settings row: label left, widget right. When the setting
        carries help, the LABEL pops the full tip paragraph on hover
        (the old "?" chip's exact path into the Tips engine); the text
        also lands on row._tip for the probes to read. hint_chars is a
        kept-for-compatibility relic of the inline-hint era - the bubble
        wraps at its own width. Widgets are created ON THE ROW so grid
        only ever manages children of the row, pack only ever manages
        children of the card."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0, theme.S_ROW))
        row.grid_columnconfigure(0, weight=1)
        cell = ctk.CTkFrame(row, fg_color="transparent")
        cell.grid(row=0, column=0, sticky="w")
        lbl = ctk.CTkLabel(cell, text=label, font=self.skin.font(12),
                           **self.skin.text_style())
        lbl.pack(side="left")
        row._tip = tip
        if tip:
            lbl.bind("<Enter>", lambda e=None: self.tips._schedule(tip, lbl),
                     add="+")
            lbl.bind("<Leave>", lambda e=None: self.tips._hide_soon(),
                     add="+")
        return row

    def _section(self, name, pady=(0, 0)):
        """A rebuildable slice of the pane: DOUBLE BUFFERED exactly
        like _profiles_render's body. First call (full fill, body
        unpacked) makes and packs the frame. A later call (a click
        repaint) builds a FRESH unpacked frame - the OLD one stays
        visible and undestroyed until _repaint swaps: emptying the
        visible frame first dirties the region, and every CTk
        constructor's update_idletasks then repaints the WHOLE mapped
        pane (measured: 688 ms for 12 rows; a detached build with the
        old row still shown is the 27 ms the tab switch pays)."""
        f = self._psec.get(name)
        if f is None:
            f = ctk.CTkFrame(self._prof_detail, fg_color="transparent")
            f.pack(fill="x", pady=pady)
        else:
            self._psec_old.setdefault(name, []).append(f)  # outlives the
            f = ctk.CTkFrame(self._prof_detail,            # rebuild only
                             fg_color="transparent")       # until the swap
        self._psec[name] = f
        self._psec_pady[name] = pady
        return f
