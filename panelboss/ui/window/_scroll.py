"""The scroll host: a plain tk.Canvas + Scrollbar standing in for
ctk.CTkScrollableFrame (UI-PLAN Phase 1 step 1: the CTk version is the
single worst render offender - rounded canvas chrome, a poller-tracked
inner frame, and a full item re-map on every show/hide).

The host is pure tk (one Canvas, one Scrollbar, one Frame): the page's
children are built on ``host.inner`` and pack() lands them in the
scroll region; the host itself takes the same pack()/pack_forget()/
destroy() calls the tab machinery already makes. CTk widgets accept a
plain tk.Frame master (measured; CTkScrollableFrame's own inner frame
takes CTk children the same way).
"""

from __future__ import annotations

import tkinter as tk


class ScrollHost(tk.Frame):
    def __init__(self, master, bg=None, width=0, height=0, **ignored):
        # **ignored eats leftover CTk-style kwargs (scrollbar_button_color
        # and friends) so call sites can age out of them one at a time
        super().__init__(master, bg=bg)
        self._sb = tk.Scrollbar(self, width=10, bg=bg, troughcolor=bg,
                                activebackground=bg, highlightthickness=0)
        self._sb.pack(side="right", fill="y")
        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0,
                                 borderwidth=0, width=width, height=height,
                                 yscrollcommand=self._sb.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self._canvas, bg=bg)
        # the CTkScrollableFrame API surface the tests and pages
        # already poke: inner under .inner, and _parent_frame maps to
        # the HOST - the test probe asks who is pack-managed, and the
        # host is the pack-truthful widget (inner lives in the canvas)
        self._parent_frame = self
        self._win = self._canvas.create_window((0, 0), window=self.inner,
                                               anchor="nw")
        self._sb.configure(command=self._canvas.yview)
        # width tracks the viewport; height is the scroll region
        self.inner.bind("<Configure>", self._region, add="+")
        self._canvas.bind("<Configure>", self._width, add="+")
        self._canvas.bind("<Enter>", self._wheel_on, add="+")
        self._canvas.bind("<Leave>", self._wheel_off, add="+")

    # the CTkScrollableFrame callers used configure() for; only bg is real
    def configure(self, cnf=None, **kw):
        kw.pop("fg_color", None)
        kw.pop("scrollbar_button_color", None)
        kw.pop("scrollbar_fg_color", None)
        return super().configure(cnf, **kw)

    def _region(self, _event=None):
        self._canvas.configure(scrollregion=self._canvas.bbox("all") or ())

    def _width(self, event):
        self._canvas.itemconfigure(self._win, width=event.width)

    def _wheel_on(self, _event=None):
        self._canvas.bind_all("<MouseWheel>", self._wheel)

    def _wheel_off(self, _event=None):
        self._canvas.unbind_all("<MouseWheel>")

    def _wheel(self, event):
        self._canvas.yview_scroll(int(-event.delta / 120), "units")

    def destroy(self):
        # gate finding 5: bind_all outlives the host otherwise - a
        # later wheel over any window would TclError into the pump
        self._canvas.unbind_all("<MouseWheel>")
        super().destroy()
