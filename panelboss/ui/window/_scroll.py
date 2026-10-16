"""The scroll host: a plain tk.Canvas + Scrollbar standing in for
ctk.CTkScrollableFrame (UI-PLAN Phase 1 step 1: the CTk version is the
single worst render offender - rounded canvas chrome, a poller-tracked
inner frame, and a full item re-map on every show/hide).

The host is pure tk (one Canvas, one Scrollbar, one Frame): the page's
children are built on ``host.inner`` and pack() lands them in the
scroll region; the tab machinery place()s the host into the body once
and raises it to reveal - never remaps (Oct 12, layer-raise switch;
destroy() is still the host's to take, as any widget's). CTk widgets
accept a plain tk.Frame master (measured; CTkScrollableFrame's own
inner frame takes CTk children the same way).

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
from tkinter import ttk

from .. import theme

_SCROLLBAR_STYLES = set()
                # style names already configured in THIS interpreter,
                # so a rebuild storm does not re-configure the style per bar


def scrollbar_style(master, surface):
    """The ttk style name for a bar over `surface`, configured once per
    interpreter (see themed_scrollbar's header for why ttk and why clam)."""
    style = ttk.Style(master)
    name = "PB_%s.Vertical.TScrollbar" % str(surface).lstrip("#")
    if name not in _SCROLLBAR_STYLES:
        try:
            style.theme_use("clam")
        except Exception:
            pass                       # foreign theme: the configure below
                                       # still lands where it can
        thumb = theme_rule_thumb(surface)
        style.configure(name, troughcolor=surface, background=thumb,
                        bordercolor=surface, arrowcolor=surface,
                        lightcolor=thumb, darkcolor=thumb,
                        relief="flat", borderwidth=0, focuscolor=surface)
        try:
            style.map(name, background=[("active", thumb),
                                        ("pressed", thumb)])
        except Exception:
            pass
        _SCROLLBAR_STYLES.add(name)
    return name


def themed_scrollbar(master, surface, width=10, command=None):
    """A vertical scrollbar that honors the skin.

    WHY NOT tk.Scrollbar (measured, Oct 15, scratch probe against this
    venv's Tk 9.0.0): troughcolor/background/activebackground/
    elementborderwidth/borderwidth/relief are ALL ignored - whatever the
    options, the widget paints the system-light trough, so every bar in
    the app read as a white slash inside a dark card (the power tab's
    blockers box and gaming boxes, the pinned-apps list, the page host).
    ttk's clam theme DOES honor them, so every bar in the house rides one
    configured style instead.

    Two styles, named by the surface the bar sits on (the page tier or
    the raised/popup tier on top of it) - the trough vanishes into
    whatever it is drawn over while the thumb stays a visible rail.

    Side effect, deliberate and named: ttk's theme is switched to clam for
    this interpreter. The app owns ZERO ttk widgets (grepped; ui/__init__
    imports ttkbootstrap as an optional probe only), so nothing else can
    observe the theme change - and it is idempotent per interpreter.
    """
    sb = ttk.Scrollbar(master, orient="vertical",
                       style=scrollbar_style(master, surface),
                       command=command)
    try:
        sb.configure(width=width)
    except Exception:
        pass
    return sb


def theme_rule_thumb(surface):
    """The thumb's rail color for a given trough: the raised-control tier
    when the bar sits on the page, the lighter control border when it
    sits ON a raised surface (a thumb equal to its own trough would be an
    invisible bar - the other half of the defect this module prevents)."""
    return theme.BORDER_RAISED if str(surface).lower() == \
        str(theme.RAISED).lower() else theme.RAISED


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
                reg = w.bbox("all")
                # the region-vs-viewport law (Oct 12, ghost hunt):
                # yview() is a liar on a FITTED canvas - it reports
                # (0,1) for "all visible" while yview_scroll still
                # moves the RENDERED view (measured Tk 8.6/3.10.6:
                # -95px per wheel-up, canvasy(0) walks, yview never
                # budges). The old hi-lo guard read (0,1) as
                # scrollable and took the event; the host's own
                # clamp then snapped the offset back from the
                # <Configure> the move itself generates, and the
                # flashed frame at the offset is the ghosted card
                # bottoms the owner saw. The bbox test mirrors the
                # clamp's law exactly (same quantity, same
                # comparison), so accept and snap can never
                # disagree.
                if reg is not None and len(reg) == 4 \
                        and reg[3] > w.winfo_height():
                    # reg[3] (not reg[3]-reg[1]) mirrors the clamp's
                    # law verbatim - premise: inner is pack-managed
                    # at y=0, no negative content; both arms would
                    # change together if that ever breaks.
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
        self._dead = False              # the <Destroy> binding's opt-out
        self._region_job = None         # the sync_region rungs, tracked:
        self._region_job2 = None        # a pending rung is never re-armed
        self._sb = themed_scrollbar(self, bg, width=10)
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
        # a child DESTROY is the other half of the region story (Oct
        # 12, owner's blank band): shrinking content fires NO
        # <Configure> for the frame left behind (measured: pack/
        # destroy coalesces, and a descendant Destroy does NOT hit a
        # middle frame's binding either - Tk routes it through the
        # DESTROYED widget's bindtags, where the toplevel sits). So
        # the toplevel is the truthful seat: every removal anywhere
        # in the page re-measures here, through the loop turn that
        # lets geometry settle (sync_region). Four hosts share the
        # seat; a re-measure is microseconds. DEAD hosts opt out (gate
        # finding, MEDIUM): profile repaints churn ScrollHosts, and an
        # unbinding-less binding would tax every future destroy with
        # the ghosts of every dead section buffer.)
        self.winfo_toplevel().bind(
            "<Destroy>",
            lambda e: None if getattr(self, "_dead", False)
            else self.sync_region(), add="+")
        self._canvas.bind("<Configure>", self._width, add="+")
        # the FIRST MEASURE from a real height (owner Oct 15, the dead
        # trough that survived the swap): a host born inside a section
        # that is built while its page is still unmapped measures a 1 px
        # canvas, reads "content overflows", packs the bar - and nothing
        # later re-checks, because a fitted region fires no <Configure>.
        # The map is the missing seat: one re-measure when the widget
        # lands on screen (sync_region is already debounced and
        # idempotent, so an eager host pays nothing for this).
        self.bind("<Map>", lambda e: self.sync_region(), add="+")
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
            reg = self._canvas.bbox("all") or ()
            self._canvas.configure(scrollregion=reg)
            # the scrollbar's honesty (owner Oct 15: "no scrollbar when
            # there is nothing to scroll"): the bar is only meaningful
            # while the content overhangs the viewport. A fitted page
            # (bbox height <= canvas) hides the bar entirely - the idle
            # trough was a dead seam that read as "more below" on short
            # tabs. The same bbox test the wheel and the clamp already
            # share decides it, so the three can never disagree (the
            # region-vs-viewport law, _scroll_up's header).
            overflow = len(reg) == 4 and reg[3] > self._canvas.winfo_height()
            if overflow:
                if not self._sb.winfo_manager():
                    self._sb.pack(side="right", fill="y")
            else:
                if self._sb.winfo_manager():
                    self._sb.pack_forget()
            # clamp a stranded view (Oct 12, owner's "blank space at
            # the top"): rows that leave (collapsed tiles, retracting
            # update lines) SHRINK the region, and tk never re-clamps
            # yview when that happens - the view stays parked in
            # content that no longer exists, showing blank above the
            # survivors. Re-pack used to hide this by resetting the
            # view on every tab visit; the layer law keeps pages
            # mapped, so the clamp belongs here where the region
            # changes. Content that does not fill the viewport has
            # exactly ONE sane position: the top.
            if not overflow:
                self._canvas.yview_moveto(0.0)
            # the same law's partial-shrink arm (gate finding, LOW,
            # measured there): a region that shrinks but still
            # overhangs the viewport leaves a parked view's fraction
            # OUT of range (0.9 -> 1.0033) - the band's bigger
            # sibling. Past-the-end views snap back to the edge.
            elif self._canvas.yview()[1] > 1.0:
                self._canvas.yview_moveto(1.0)
        except tk.TclError:      # canvas gone mid-teardown: nothing to
            pass                 # measure, nothing to confess

    def sync_region(self):
        """re-measure after a widget swap: pack/destroy coalesce their
        <Configure> events, so inner resizing back to a size it passed
        through mid-burst fires nothing and the region stays whatever
        bbox saw mid-destroy (0x0 -> scrollregion dead, scroll gone).
        Deferred one loop turn so the pending geometry has settled.
        TWO passes (Oct 12, band hunt): a destroy burst outlives a
        single 1 ms hop - the first re-measure can still catch the
        transient, and Tk sends no follow-up event when the settle
        passes silently. The second lands after the burst has truly
        finished; _region is idempotent and microseconds cheap.
        after() survives _region being gone only until destroy()
        deletes the callit - a swap that raised mid-teardown can fire
        it on a dead canvas: the TclError is exactly the silent hole
        class, guarded (gate finding 4).
        COALESCED (audit LOW, the pile-up): the <Destroy> binding fires
        this for EVERY live host on EVERY widget destroy, so one repaint
        armed hundreds of pending runs. Each rung now owns a tracked
        slot and a pending rung is never re-armed - the same debounce
        shape as _shell._save/_save_now, rung-for-rung."""
        try:
            if self._region_job is None:
                self._region_job = self.after(1, self._region_now)
            if self._region_job2 is None:
                self._region_job2 = self.after(50, self._region_now2)
        except tk.TclError:
            pass

    def _region_now(self):
        self._region_job = None         # the slot clears BEFORE the
        self._region()                  # measure: _shell._save's shape

    def _region_now2(self):
        self._region_job2 = None
        self._region()

    def _width(self, event):
        try:
            self._canvas.itemconfigure(self._win, width=event.width)
        except tk.TclError:      # canvas gone mid-teardown: the sibling
            pass                 # _region already swallows this class
        # the scrollbar hide/show law is a resize law (gate finding 2,
        # Oct 15): a vertical resize changes the canvas height without
        # re-geometrying the inner frame, so the <Configure>-bound
        # region check goes stale in BOTH directions - a dead trough
        # re-appears, or a needed bar never shows. Re-check here;
        # microsecond cheap, TclError-guarded by _region itself.
        self._region()

    def _wheel(self, event):                   # kept for old callers
        self._canvas.yview_scroll(int(-event.delta / 120), "units")

    def destroy(self):
        self._dead = True             # the toplevel <Destroy>
        # binding must not tax future events with this host's
        # funeral (gate finding, MEDIUM)
        try:
            _LIVE.remove(self)
        except ValueError:
            pass                               # gone already
        if not _LIVE:      # gate finding 5's rule kept: the global
            #            binding must not outlive the last host
            tk.Misc.unbind_all(self, "<MouseWheel>")
        super().destroy()
