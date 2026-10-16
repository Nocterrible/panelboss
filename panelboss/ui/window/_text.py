"""SkewText: the CTkTextbox drop-in, drawn by plain Tk (UI-1b3).

The measured hot spot: CTkTextbox's INTERNAL CTkScrollbars carry
~1.06 s cumtime in the build profile - two always-built scrollbar
canvases plus a 200 ms poller (``_check_if_scrollbars_needed``) per
box. This twin is one tk.Text and one tk.Scrollbar; no canvas
chrome, no poller. Split from _widgets.py (230 lines, SIZE LAW).

Shape: SUBCLASS, not the CTkTextbox-style wrapper. The call sites
grid()/pack()/bind()/insert()/get()/delete() the returned object
directly, and _runtime._update_blockers plus the power suites reach
for ``box._textbox`` to touch the real Tk text widget - so
``self._textbox = self`` closes that mirror (getattr(box, "_textbox",
box) lands here too) without a forwarding layer. A wrapper would
re-grow the ~30 delegating methods CTkTextbox has; a tk.Text already
IS all of them.

Pixel kwargs: CTkTextbox takes width/height in PIXELS (widget scaling
is pinned to 1.0 in window/__init__.py); tk.Text counts chars/lines.
Pixels are converted through the widget's own font metrics at build.
The y-scrollbar is a placed child overlaying the right edge (CTk
grids it side-by-side and auto-hides it; this one is always shown,
the ScrollHost pattern from _scroll.py:24), so the width conversion
reserves its 10 px and text never hides under the thumb.

Divergences from CTk, all deliberate: no rounded border (flat relief,
bd=0, highlightthickness=0 - border_color/border_width/corner_radius
are accepted and ignored, the same trade SkewCombo made); the
scrollbar never auto-hides; x-scrolling is not offered (wrap="word"
is what every call site asks for, and CTk's x bar was hidden anyway).
Kwargs policy, spelled out: the documented skin keys are swallowed
like SkewCombo's _IGNORED list, fg_color/text_color MAP to bg/fg -
but any key not on either list raises TypeError, because this widget
only ever meets menu_style()-shaped kwargs and an unknown one is a
typo, not a style. get("1.0", "end") keeps tk's trailing-newline
truth - CTk merely delegated here, so the call sites' splitlines()
sees no change.
"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

from .. import theme
from ._scroll import themed_scrollbar, scrollbar_style

# fallbacks ARE the design tiers; call sites pass both explicitly,
# these answer hand-built uses
_BG, _FG = theme.RAISED, theme.TXT_1
_SB_W = 10                      # the ScrollHost width, _scroll.py:24

# menu_style()-shaped keys + CTkTextbox's own options: absorbed on
# construct AND on configure, so call sites age out one at a time
_IGNORED = ("corner_radius", "border_color", "border_width",
            "border_spacing", "scrollbar_button_color",
            "scrollbar_button_hover_color", "activate_scrollbars",
            "label_text", "label_font", "label_anchor",
            "label_forward", "dropdown_fg_color",
            "dropdown_hover_color", "dropdown_text_color",
            "button_color", "button_hover_color", "anchor")


class SkewText(tk.Text):
    def __init__(self, master=None, cnf=None, width=None, height=None,
                 fg_color=None, text_color=None, font=None, wrap="word",
                 **ignored):
        for key in _IGNORED:     # CTk-flavored kwargs never reach Tk
            ignored.pop(key, None)
        if ignored:
            raise TypeError("SkewText: unexpected kwargs %s"
                            % sorted(ignored))       # loud, not silent
        bg = fg_color or _BG
        fg = text_color or _FG
        # no width/height yet: the px->unit math needs THIS widget's
        # font metrics, so pass them right after the Tk widget exists
        tk.Text.__init__(self, master, cnf, bg=bg, fg=fg,
                         insertbackground=fg, wrap=wrap, font=font,
                         relief="flat", borderwidth=0,
                         highlightthickness=0, padx=4, pady=4)
        self._textbox = self     # the CTkTextbox mirror (see docstring)
        # the bar rides the house's themed one (the themed_scrollbar
        # header has the measurement: a plain tk.Scrollbar cannot be
        # colored on this Tk, so it painted the system-light trough
        # inside our dark field - the white slashes the owner saw)
        self._sb = themed_scrollbar(self, bg, width=_SB_W,
                                    command=self.yview)
        # placed child, pinned to the right edge (Text children take
        # place/grid, not pack slots); relheight keeps it full-height
        self._sb.place(rely=0.0, relx=1.0, anchor="ne", width=_SB_W,
                       relheight=1.0)
        self.configure(yscrollcommand=self._sb.set)
        if height is not None:
            self.configure(height=self._lines(height))
        if width is not None:   # minus the thumb: text stays readable
            # floor at 1 char: a small pixel width must not go negative
            # (negative tk widths silently mean PIXELS again)
            self.configure(width=max(1, self._chars(width) - _SB_W))

    # ------------------------------------------------------------ sizing --
    def _font(self):
        """This widget's font as a Font object. Tk 9 dropped Text's
        fontmetrics/measure subcommands, so metrics go through the
        named font; CTkFont answers as its registered font name."""
        try:
            return tkfont.Font(font=self.cget("font"))
        except tk.TclError:
            return tkfont.nametofont("TkDefaultFont")

    def _lines(self, px):
        """Pixel height -> whole text lines, at this widget's font."""
        return max(1, int(round(
            (px - 8) / self._font().metrics()["linespace"])))

    def _chars(self, px):
        """Pixel width -> average chars, at this widget's font."""
        return max(4, int(round(px / max(1, self._font().measure("0")))))

    # ------------------------------------------------ CTk kwarg contract --
    def insert(self, index, chars, *tag_args, tags=None):
        """CTkTextbox.insert(index, text, tags=None) twin: the keyword
        form joins the native *args tag list (tkinter would otherwise
        reject tags=, and _runtime._update_blockers calls it that way).
        Without the keyword this is native tk.Text.insert exactly."""
        if tags is not None:
            tag_args = tag_args + (tags,)
        return tk.Text.insert(self, index, chars, *tag_args)

    def configure(self, cnf=None, **kw):
        if isinstance(cnf, dict):
            kw = dict(cnf, **kw)
            cnf = None
        elif cnf is not None:                      # legacy pair-list form
            return tk.Text.configure(self, cnf, **kw)
        if "fg_color" in kw:
            kw["bg"] = kw.pop("fg_color")
            kw.setdefault("troughcolor", kw["bg"])
            try:                            # re-dress the bar with the new
                self._sb.configure(         # field: the ttk style IS the
                    style=scrollbar_style(self, kw["bg"]))  # bar's look
            except Exception:
                pass                        # dying widget: no re-dress
        if "text_color" in kw:
            kw["fg"] = kw["insertbackground"] = kw.pop("text_color")
        for key in _IGNORED:
            kw.pop(key, None)
        if kw:
            return tk.Text.configure(self, **kw)
        return None

    config = configure
    __call__ = configure

    def cget(self, key):
        if key == "fg_color":                      # CTk answers, not tk
            return tk.Text.cget(self, "bg")
        if key == "text_color":
            return tk.Text.cget(self, "fg")
        return tk.Text.cget(self, key)

    __getitem__ = cget
