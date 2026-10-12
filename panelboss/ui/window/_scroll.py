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

Oct 12 (scroll_probe, owner report "page scroll no longer works"):
the wheel moved from the Enter/Leave bind_all dance to ONE global
dispatcher. The dance died on the double-buffer swap - a nested host
destroyed by a repaint called unbind_all, which kills the binding
whoever else was holding it (the page host), and Tk never re-fires
<Enter> for a mouse that never left: wheel dead until the pointer
crossed a border. The dispatcher resolves the host under the pointer
per event, innermost scrollable first, so nested hosts, swaps and
withdraws all take the hit without re-entry.
"""

from __future__ import annotations

import tkinter as tk

_LIVE = []                     # every mapped ScrollHost, innermost-
               # first resolution order; kept tiny on purpose (five
               # hosts per window: the four pages, two profile lists)


def _scroll_up(under, step):
    """From the widget under the event, walk the master chain OUT and
    let every live host on the path try, innermost first; a host that
    cannot scroll (its region fits its viewport) steps aside for the
    next one out, so parking the mouse on the pinned-apps list never
    dead-ends the page behind it. Returns True if some host took it."""
    live = list(_LIVE)
    w = under
    while w is not None:
        for host in live:
            if host._canvas is w:
                lo, hi = w.yview()
                if hi - lo > 1e-6:
                    w.yview_scroll(step, "units")
                    return True
                break            # this host cannot: keep walking out
        w = w.master
    return False


def _wheel(event):
    """The one <MouseWheel> handler the app installs (bind_all).
    event.widget is the tk widget the pointer routes to (children are
    windowless - Tk resolves it); when the platform hands the event to
    the toplevel instead, x_root/y_root resolve the real target."""
    if _scroll_up(event.widget, int(-event.delta / 120)):
        return "break"
    try:
        under = event.widget.winfo_containing(event.x_root, event.y_root)
    except (KeyError, tk.TclError):
        under = None
    if under is not None and _scroll_up(under, int(-event.delta / 120)):
        return "break"
    return None                  # nothing scrollable: pass on


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
        # the wheel: one dispatcher, installed once, owned by no host.
        # UNCONDITIONAL (gate finding 1): PanelBoss owns <MouseWheel>
        # app-wide - a guarded install would silently skip if any
        # library bound the tag first, and a later unbind_all would
        # yank ours with no error (the exact dead-wheel class this
        # file exists to kill). Re-installing our own func is
        # idempotent.
        tk.Misc.bind_all(self, "<MouseWheel>", _wheel)
        _LIVE.insert(0, self)    # newest under the pointer first

    # the CTkScrollableFrame callers used configure() for; only bg is real
    def configure(self, cnf=None, **kw):
        kw.pop("fg_color", None)
        kw.pop("scrollbar_button_color", None)
        kw.pop("scrollbar_fg_color", None)
        return super().configure(cnf, **kw)

    def _region(self, _event=None):
        try:
            self._canvas.configure(scrollregion=self._canvas.bbox("all") or ())
        except tk.TclError:      # canvas gone mid-teardown: nothing to
            pass                 # measure, nothing to confess

    def sync_region(self):
        """re-measure after a widget swap: pack/destroy coalesce their
        <Configure> events, so inner resizing back to a size it passed
        through mid-burst fires nothing and the region stays whatever
        bbox saw mid-destroy (0x0 -> scrollregion dead, scroll gone).
        Deferred one loop turn so the pending geometry has settled.
        after() survives _region being gone only until destroy()
        deletes the callit - a swap that raised mid-teardown can fire
        it on a dead canvas: the TclError is exactly the silent hole
        class, guarded (gate finding 4)."""
        try:
            self.after(1, self._region)
        except tk.TclError:
            pass

    def _width(self, event):
        self._canvas.itemconfigure(self._win, width=event.width)

    def _wheel(self, event):                   # kept for old callers
        self._canvas.yview_scroll(int(-event.delta / 120), "units")

    def destroy(self):
        try:
            _LIVE.remove(self)
        except ValueError:
            pass                               # gone already
        if not _LIVE:      # gate finding 5's rule kept: the global
            #            binding must not outlive the last host
            tk.Misc.unbind_all(self, "<MouseWheel>")
        super().destroy()
