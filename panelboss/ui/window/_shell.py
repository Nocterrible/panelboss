"""The settings window (CTk, main thread - Tk always owns thread zero).

Rules this file lives by:
* it never touches the camera or the display: commands go through the
  state machine's queue, or into the shared config dicts the worker
  reads every tick (cfg["timers"] IS monitor.timers - writing it is
  applying it, no round trip needed)
* the debug view draws from monitor.framebox: the picture next to the
  camera picker is literally the frame the detector judged
* camera enumeration boots every index (this machine's virtual camera
  takes up to 16 s), so it always runs off the UI thread
* four tabs, one scroll page each: what belongs together is
  detected together (detection + timers + camera), named desktops
  (monitors, modes, HDR, window seats) get their own tab because
  applying one reshapes the whole desk, what guards the desk
  belongs to the power plan (hold overrides, wake behavior, the
  powercfg assistant), and what only configures the app itself
  (skin, autostart, logs) is meta - it goes in general/keybinds
* anything that needs a paragraph carries a "?" (ui.helpbtn); the
  rows themselves stay one line short

Skins come from theme.py; nothing here hardcodes a color.

SIZE LAW: grandfathered, measured 770 (Oct 13, after the per-veil
hold, the heartbeat re-lease, the _unveil leak-reset, the
consent-gated boot scan, and the SWITCH_SYNC repaint seam the
knob-lie family's second corpse cost) -
window lifecycle, size recall, and
the reveal-veil machinery are one story (how the window appears and
remembers itself); the scroll hosts already live in _scroll.py and the
next seam to split out is the size-recall trio if this grows again.
"""


from __future__ import annotations

import logging
import os
import threading
import time
import tkinter as tk

import customtkinter as ctk

from ... import config
from ... import hider
from .. import theme
from ..helpbtn import Tips
from ..kofi import kofi_pil
from ._constants import TABS, TIPS
from ._scroll import ScrollHost
from ._widgets import _SleepPrompt
from ._widgets import _WidgetsMixin
from ._present import clip_siblings
from ._runtime import _RuntimeMixin
from ._detection import _DetectionMixin
from ._away import _AwayMixin
from ._oled import _OledMixin
from ._preview import _CameraMixin
from ._camedit import _CamEditMixin
from ._profiles import _ProfilesMixin
from ._prof_editor import _EditorMixin
from ._prof_apply import _ModeMixin
from ._prof_pins import _PinMixin
from ._icon import _IconMixin
from ._restore import _RestoreMixin
from ._power import _PowerMixin
from ._gaming import _GamingMixin
from ._general import _GeneralMixin

log = logging.getLogger("ui")

class SettingsWindow(
    _WidgetsMixin,
    _RuntimeMixin,
    _DetectionMixin,
    _AwayMixin,
    _OledMixin,
    _CameraMixin,
    _CamEditMixin,
    _ProfilesMixin,
    _EditorMixin,
    _ModeMixin,
    _PinMixin,
    _IconMixin,
    _RestoreMixin,
    _PowerMixin,
    _GamingMixin,
    _GeneralMixin,
    ctk.CTk,
):

    IR_INSTALL = "hello IR camera (optional - pick to install whircam)"


    def __init__(self, cfg, monitor, ui_events):
        super().__init__()
        # the birth-order law's other half (owner UAT, Oct 15): this
        # root now owns the process default - release the waiting
        # painter; its interpreter can claim nothing anymore, and the
        # images customtkinter binds to the default land HERE
        hider.window_ready()
        # the CTk root maps at BIRTH, before a single widget exists:
        # withdraw instantly so the empty window never gets a frame on
        # screen - the first pixels a user may ever see come from
        # _show_first (veil included), never from a build sweep
        self.withdraw()
        self._manual_open_done = False
        self.cfg = cfg
        self.monitor = monitor
        self.ui_events = ui_events
        self.skin = theme.get_skin(cfg["ui"]["skin"])
        theme.apply_ctk_font(self.skin)
        self.title("PanelBoss")
        self._set_app_icon()                   # the owner art on the
                                               # titlebar + taskbar
                                               # (Tk hands it to every
                                               # toplevel: the wizard
                                               # rides along); the
                                               # TRAY stays the state
                                               # circle by law
        # size (Oct 12, owner: "open larger, and remember how large I
        # dragged it"): the recalled [w, h], clamped at birth; the
        # minsize is the clamp's floor, so a recalled window is never
        # smaller than what the recall promises
        self._size_job = None
        self._size_pair = self._initial_size()
        self.geometry("%dx%d" % self._size_pair)
        self.minsize(600, 420)
        self.bind("<Configure>", self._on_configure)
        self.protocol("WM_DELETE_WINDOW", self._hide)     # close = to tray
        self._cams = None
        self._shown_ts = None
        self._ctkimg = None
        self._save_job = None
        self._veil_lbl = None
        self._veil_since = 0.0
        self._veil_hold = 3.0              # the watchdog budget of the
                                          # veil currently up; _veil
                                          # restamps it per veil
        self._diag_veiled = False          # the veil currently up is
                                          # the camera diagnostic's:
                                          # the next list report owes
                                          # the unveil (runtime's
                                          # cameras arm collects it)
        self._ph_img = None                # the main pane's reset
                                          # placeholder (see the
                                          # _camid trap law: a CTk
                                          # preview resets to an
                                          # IMAGE, never to None)
        self._unveil_job = None          # the tracked after(0) lift chain that raises
                                         # a boot/skin veil: a re-veil
                                         # mid-flight must cancel it, never
                                         # ride a ghost lift
        self._lease_ticks = 0
        # the second-instance handoff (owner UAT, Oct 15): a poke from
        # a launched-while-running twin opens this window (the tray's
        # own manual-open seam) and reads an ack; the stamp's mtime at
        # birth is the floor, so a logon poke racing the build never
        # replays into a map nobody asked for
        self._poke = os.path.join(config.CONFIG_DIR, "poke")
        self._poke_ack = os.path.join(config.CONFIG_DIR, "poke_ack")
        try:
            self._poke_seen = os.path.getmtime(self._poke)
        except OSError:
            self._poke_seen = 0.0
        self._tab = TABS[0]
        ctk.set_appearance_mode(self.skin.mode)
        self.configure(fg_color=self.skin.bg)
        self.build_all()
        if self.cfg["ui"].get("start_minimized"):
            pass                         # straight to the tray: the
            # window stays withdrawn unmapped; the first tray-open
            # pays the veiled first map, every later one is a pixel
            # instant (the DWM surface already holds the drawn UI)
        else:
            self._show_first()
        if self.cfg["camera"].get("enabled"):
            # consent (redesign law 1): the boot scan OPENS every
            # index (enumerate) and, on a stale record, sweeps them
            # - on a virgin boot that is a camera opening the owner
            # never asked for, and on a hostile desk a first-launch
            # lockout behind a 20+ s veil. The setup dialog (or the
            # rescan button once the switch is on) starts the first
            # real scan; until then the picker's stock "scanning
            # cameras..." face is honest: nothing is.
            self._scan_cameras()
        self.after(90, self._tick_ui)


    def _show_first(self, manual=False):
        """The veil's owner is the USER's first real open, and it is
        the UNMAPPED map that needs the cover - not the first one of
        the session.

        The Oct-12 law (owner: "first open is not hiding my monitor
        switching any more", veil_test.py's header): an unasked boot
        map must not spend the ceremony the first REAL open is owed,
        so only a manual open consumes the budget. The Oct-15 UAT
        (the owner's close-X-and-reopen repro) showed the other half:
        after a close the next tray-open drew the full UI with no
        cover, because the rule had hardened into "manual open #1 is
        veiled, every later open is plain".

        The seam that actually decides is mapping state, not a
        session counter. An UNMAPPED window maps fresh and paints the
        whole UI in one burst - DWM holds a drawn surface only while
        the window stays alive, and a close destroys it - so that
        burst wants the cover whether it is the birth map or the
        ninth. An ALREADY-MAPPED open is the pixel-instant reopen the
        owner chose: it takes the plain deiconify/lift and no veil
        (veil_test's "later opens stay pixel-instant" pins exactly
        this). The first MANUAL open also sets the budget flag, so an
        unasked boot map can never eat the owner's ceremony.

        Mechanics: deiconify only MARKS for mapping, so the veil goes
        up before the first update() and the first COMPOSITE carries
        it; tk cannot pre-paint a withdrawn window (documented trap),
        so the veil covers the burst itself. The timed lift (300 ms)
        lands after the burst; the watchdog in _tick_inner caps any
        stuck veil at 3 s. The veil lands on the UNMAPPED window
        (audit INFO: the old deiconify-then-veil order left a frame
        of un-veiled half-paint between map and cover - _veil reads
        no map state, so the current order is the safe one)."""
        # mapping state BEFORE anything else: deiconify and the
        # deferred resync below both read this verdict
        was_mapped = self.state() != "withdrawn"
        if not self._manual_open_done:
            self._veil("PanelBoss", full=True)
            if manual:
                self._manual_open_done = True
            self.deiconify()
        else:
            if manual and not was_mapped:
                self._veil("PanelBoss", full=True)
            self.deiconify()
            self.lift()
        # knob-lie belt (second corpse, the owner's bar-was-on catch):
        # every switch painted during this window's hidden birth drew
        # its knob at zero geometry - the deferred resync re-arms the
        # same truth paint once the map and its <Configure> have
        # landed (see _repaint_switches; the probe pins the ordering).
        # An already-mapped raise skips it: those knobs settled long
        # ago and the re-select is the visible button redraw the
        # owner reported. The exception is a veil we just armed -
        # behind a cover the same repaint is free, and hide/show is
        # exactly the cycle where the geometry claim is unverified.
        if getattr(self, "_unveil_job", None) is not None:
            try:
                self.after_cancel(self._unveil_job)   # cancel-then-
            except Exception:                         # assign: an
                pass                                  # un-cancelled
            self._unveil_job = None                   # orphan is a
                                                      # ghost lift
                                                      # (Oct-12 law,
                                                      # re-entry by
                                                      # this door)
        if not was_mapped or getattr(self, "_veil_lbl", None) is not None:
            self.after(0, self._repaint_switches)
            self.after(0, self._sync_slider_wheels)
            # event-driven lift (SMOOTH, owner Oct 15): the old timed
            # 300 ms lift raced the first geometry flush - the repaint
            # above calls update_idletasks() which does the deferred
            # profiles/editor render, measured ~950-1000 ms on this
            # host - so the veil dropped mid-sweep and the owner saw
            # the repaint. The lift now chains ONTO the flush's own
            # after(0), in schedule order: repaint, slide sync, then
            # unveil. No clock guesses the flush's cost; the lift
            # fires the moment the work is done. A re-veil mid-flight
            # still cancels this job through the same _unveil_job slot
            # (_veil's cancel arm), and the watchdog keeps the 3 s
            # backstop for a flush that wedges.
            if not self._diag_veiled:               # the sweep's
                #                                   veil owns its
                self._unveil_job = self.after(0, self._unveil)  # report
                #                                   -arm; the chain
                #                                   must not lift it
                #                                   mid-sweep


    # -------------------------------------------------- switch repaint --
    # One dispatch table per PANE (the owner's law: the next switch
    # added to the house joins for free by riding its pane's sync
    # entry, never by remembering call sites). Values are method
    # names; every entry paints BOTH branches from its truth source -
    # cfg, the registry, the editor dict - and fires no commands.
    SWITCH_SYNC = {
        "detection": ("_sync_consent_switch", "_sync_away_rows"),
        "monitor profiles": ("_sync_restore_switches",
                             "_sync_editor_switches"),
        "power plan": ("_sync_power_switches", "_sync_gaming_switches"),
        "general/keybinds": ("_sync_general_switches",),
        # the oled pane's first table entry (Oct 15, the companion
        # card): the next switch in the house joins for free by
        # riding its pane's entry - this is that law applied
        "oled": ("_sync_companion_switches",),
    }

    def _drain_ui_events(self):
        _RuntimeMixin._drain_ui_events(self)
        self._drain_poke()

    def _drain_poke(self):
        """The handoff's winner side (owner UAT, Oct 15): the loser
        of the instance race touches poke; this tick (90 ms cadence,
        the tick runs withdrawn) maps the window through the tray's
        own manual-open path and answers in poke_ack, so the next
        launch skips its balloon. Raises ride the runtime tick's own
        try/except - a dead stamp must never brick the loop."""
        try:
            m = os.path.getmtime(self._poke)
        except OSError:
            return
        if m <= self._poke_seen:
            return
        self._poke_seen = m
        self._show_first(manual=True)       # the map FIRST (gate
        self.focus_force()                  # finding 2): an ack before
                                            # a raise would bless a
                                            # poke that produced no
                                            # window - the ack's whole
                                            # purpose was to name the
                                            # silent case
        with open(self._poke_ack, "a"):
            os.utime(self._poke_ack, None)

    def _repaint_switches(self, pane=None):
        """Re-paint the truth switches at settled geometry. WHY: a
        CTkSwitch drawn while its window is WITHDRAWN colors its track
        honestly but leaves the knob at the zero-width position (the
        owner's screenshot: green bar, knob left); select()/deselect()
        re-runs the widget's own _draw - the geometry-honest order is
        flush the pending layout (update_idletasks), then repaint,
        and the call sites ride the seam that follows the map
        (after(0) at show, the reveal itself at tab-switch) so the
        window's <Configure> has landed first - pinned by
        scripts/switch_geom_probe.py. Idempotent, command-free, and
        missing panes (never built, or mid-swap) are a miss, not an
        error: their truth still lands at build paint."""
        if getattr(self, "_dying", False):
            return
        try:
            self.update_idletasks()
        except tk.TclError:
            return                        # destroyed under the resync
        for key in ((pane,) if pane else tuple(self.SWITCH_SYNC)):
            for name in self.SWITCH_SYNC.get(key, ()):
                fn = getattr(self, name, None)
                if fn is None:
                    continue
                try:
                    fn()
                except Exception:
                    log.debug("switch repaint %s missed (pane %s)",
                              name, key)


    # ------------------------------------------------------------- build --
    def build_all(self):
        self._top = ctk.CTkFrame(self, fg_color="transparent")
        self._top.pack(fill="x", padx=theme.S_PAGE,
                       pady=(theme.S_ROW, theme.S_FIELD))
        self._actions = ctk.CTkFrame(self, fg_color="transparent")
        self._actions.pack(fill="x", padx=theme.S_PAGE)     # rescue/sleep/
        # pause/quit row: the desk commands belong above the tabs, not
        # welded to the title (and the title row keeps room for the
        # one link that is not a command)
        self._tabs_bar = ctk.CTkFrame(self, fg_color="transparent")
        self._tabs_bar.pack(fill="x", padx=theme.S_PAGE,
                            pady=(theme.S_FIELD, 0))
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.pack(fill="both", expand=True, padx=theme.S_PAGE,
                        pady=(theme.S_FIELD, theme.S_ROW))
        self.tips = Tips(self.skin, self)
        self._build_top()
        self._build_actions()
        self.tab_buttons = {}
        for key in TABS:
            b = ctk.CTkButton(self._tabs_bar, text=key, width=120,
                              height=30,
                              command=lambda k=key: self._show_tab(k))
            b.pack(side="left", padx=(0, theme.S_FIELD),
                   pady=(0, theme.S_ROW))
            self.tab_buttons[key] = b
        self.pages = {}
        for key in TABS:
            self.pages[key] = ScrollHost(self._body, bg=self.skin.bg)
        self._build_detection(self.pages["detection"].inner)
        # the build order follows TABS (the button row iterates TABS;
        # the initial layer stack of the placed pages is the build
        # order too, and _show_tab re-raises the winner anyway). The
        # power plan sits beside detection since Oct 21: the 'present'
        # hold state makes that adjacency load-bearing.
        self._build_power(self.pages["power plan"].inner)
        self._build_profiles(self.pages["monitor profiles"].inner)
        self._build_general(self.pages["general/keybinds"].inner)
        self._build_oled(self.pages["oled"].inner)
        # The layer law (owner, Oct 12: "tabbing just reveals them
        # instead of fully redrawing them each time"): every page is
        # placed ONCE into the body and stays mapped and painted for
        # the life of the build - the overlap is the point, and
        # relwidth/relheight track body resizes for free.
        for p in self.pages.values():
            p.place(in_=self._body, x=0, y=0, relwidth=1, relheight=1)
        # the FLAT BACKDROP (see _show_tab's atomic-switch note): a plain
        # page-background frame that always sits directly UNDER the active
        # page, so the incoming page's not-yet-repainted regions show the
        # page's own background - never the outgoing page's text. Plain
        # tk (nothing to theme, nothing to draw): one rectangle fill.
        self._backdrop = tk.Frame(self._body, bg=self.skin.bg)
        self._backdrop.place(in_=self._body, x=0, y=0,
                             relwidth=1, relheight=1)
        # WS_CLIPSIBLINGS on every window in the house: without it the
        # lower tab page's child windows paint OVER the raised page -
        # the coexistence the owner screenshotted (measured; see
        # _present.clip_siblings). One walk per build.
        clip_siblings(self)
        start = self._tab
        self._tab = None               # fresh layers, undressed buttons:
        self._show_tab(start)          # the first call must run past
                                       # the guard (rebuild_for_skin
                                       # lands here too)


    def _show_tab(self, key):
        """The ONE-AT-A-TIME switch (re-cut Oct 16, owner: "tabbing
        causes both sets of objects to coexist briefly... I NEVER want
        to see anything paint live").

        The Oct-12 layer law kept every page mapped and switched by
        `tkraise` alone, on the theory that a raise is free. It is not,
        on this toolkit: a merely-restacked window gets no expose from
        Windows, so the page on top kept the PREVIOUS page's pixels on
        the glass until unrelated app activity happened to dirty the
        region - the owner's screenshot. `raise`, `update` and
        `update_idletasks` all failed to cure it (measured; see
        _present.py's header): none of them queues the work the restack
        never queued.

        The cure is the FLAT BACKDROP below (see the atomic-switch note
        under it) plus one Tk redraw pass at the end of the raise
        (Oct-24 correction: the Oct-16 note here claimed a forced
        present was the cure - the code retired it and left the sweep
        behind; the present is back OUT of this path for good, measured
        at ~5x Tk's own pass, see the raise site below). Pages stay
        BUILT and MAPPED either way (no remap: unmapping loses CTk's
        drawn canvases - measured, the fragments the owner would have
        seen instead)."""
        page = self.pages[key]
        if key == self._tab and page.winfo_manager() == "place":
            return                     # already the revealed layer: a
            # click on the lit tab must not re-dress anything (build_all
            # nulls _tab first, so a fresh build never trips this)
        self.tips.kill()                 # a tooltip anchored to a row
        self._tab = key                  # would float over the new page
        # ---- THE ATOMIC SWITCH (Oct 16, the owner's coexistence shot)
        # Measured on this toolkit (see _present.py's header): a
        # restacked page repaints over ~40 ms and Windows does NOT
        # repaint the raised page's covered region, so the outgoing
        # page's pixels stay on the glass in every gap - the two
        # generations the owner screenshotted. raise+update, reorder,
        # unmap/remap and a forced present all failed to make it one
        # frame (the present even LENGTHENED the visible change to
        # ~130 ms, so there is none here).
        #
        # The cure is a persistent FLAT BACKDROP that always sits
        # directly under the active page: the switch raises the
        # backdrop, then the incoming page over it. Every page that is
        # not active is now below an opaque flat surface, so the
        # not-yet-repainted regions of the incoming page show the
        # page's OWN background colour - never the outgoing page's
        # text. No cover to paint, no present to force, no timer: just
        # a z-order that makes two-generation bleed-through
        # unrepresentable.
        self._backdrop.tkraise()
        try:            # findings 1+2: the whole switch under one finally
            self._repaint_switches(pane=key)  # knob-lie belt (pane arm)
            self._sync_slider_wheels()
            for k, b in self.tab_buttons.items():
                b.configure(**(self.skin.primary() if k == key
                              else self.skin.secondary()))
            # THE FLAT FRAME IS FORCED (measured, Oct 24: removing this
            # flush made the switch into detection measure WORSE - 2015
            # ms inside the call against 1500 ms with it, because the
            # pending paint then drained in the same call one step later
            # anyway. Kept: it buys the flat cover NOW, and the switch
            # pays the same bill either way. What it also does is run
            # every due after() callback in the window (the 2 s desk
            # ear, the away poll, the tick) inside the click - so a
            # switch that lands on a due ear pays that rebuild too; the
            # named phase costs below are how that is told apart.)
            try:
                self._backdrop.update()  # flat fill over the body NOW
            except Exception:
                pass                     # dying window: the switch below
        finally:
            # FINDINGS 1+2 (the gate, Oct 16): an exception between the
            # backdrop raise and the switch used to leave the flat
            # backdrop up FOREVER (blank body - and _tab was already
            # set, so re-clicking the same tab no-oped: the old veil
            # had a tick watchdog, the backdrop had none; this finally
            # IS the watchdog). AND the flush above pumps queued
            # events, so a nested second tab click completed INSIDE
            # the outer switch; the outer's unconditional re-raise then
            # re-dressed the superseded page (visible A, dressed B,
            # B's tab a dead click until A is chosen again). The raise
            # runs only while this switch is still the truth (_tab
            # re-read, not captured): a nested switcher already raised
            # its own page and needs no re-raise.
            if self._tab == key:
                page.tkraise()           # THE SWITCH - restack, instant
                # AND FINISH THE PAINT IN THIS CALL (owner ruling, Oct
                # 24: "the UI appears to draw from bottom right to top
                # left as opposed to appearing fully drawn all at
                # once"). The restack queues no paint, so the revealed
                # page repainted itself on later loop turns, widget by
                # widget, newest-first - the sweep, in reverse creation
                # order (the pane's newest widgets are its bottom-right
                # ones). update_idletasks() drains Tk's own redraw queue
                # to completion HERE, so the switch is over when this
                # callback returns.
                # MEASURED, Oct 24 - and this is why it is Tk's pass and
                # not a forced Win32 present: the RedrawWindow
                # ERASE+UPDATENOW+ALLCHILDREN form at PAGE tier repainted
                # the whole subtree explicitly and cost ~1.4 s, where
                # Tk's own pass costs ~0.2 s. Five times the work for
                # the same pixels; the paint primitive stays scoped to
                # the profiles sections, where it pays.
                try:
                    self.update_idletasks()
                except tk.TclError:
                    pass                 # destroyed mid-switch: the paint
                    #                      goes with the window. NOT a
                    #                      `return` (a bare return in a
                    #                      finally swallows the in-flight
                    #                      exception the switch raised)
                page.sync_region()       # belt for the wheel: geometry
                if key != "detection" and hasattr(self, "preview_label"):
                    # THE OWNER'S LEAVE-RESET (Oct 16): the detection
                    # tab's preview bitmap is the heaviest picture in
                    # the window; leaving parks it on the placeholder
                    # and it does not come back until the NEXT CAPTURE
                    # after the tab does (see _preview_leave).
                    self._preview_leave()


    def _sync_slider_wheels(self):
        """The owner's scroll law (Oct 15): the mouse wheel belongs to
        the window, not to the value under the cursor - CTk sliders
        grab <MouseWheel> on their own canvas and NEVER consult state
        (the measured defect that made 'disabled' a lie, worked
        around by _gate_widgets' swap; the one-way opt-out generalizes
        it). One walk per tab build; idempotent (unbind twice is a
        no-op). SCROLL_SLIDERS True restores per-slider wheels."""
        if getattr(self, "_sliders_seen", None) is None:
            self._sliders_seen = set()

        def walk(w):
            try:
                if isinstance(w, ctk.CTkSlider):
                    key = id(w)
                    if not theme.SCROLL_SLIDERS:
                        cv = getattr(w, "_canvas", None)
                        if cv is not None:
                            cv.unbind("<MouseWheel>")
                    elif key not in self._sliders_seen:
                        cv = getattr(w, "_canvas", None)
                        ev = getattr(w, "_mouse_scroll_event", None)
                        if cv is not None and ev is not None:
                            cv.bind("<MouseWheel>", ev)
                            self._sliders_seen.add(key)
            except Exception:
                pass
            for c in w.winfo_children():
                walk(c)
        for child in self.winfo_children():
            walk(child)


    def rebuild_for_skin(self):
        self.tips.kill()
        self.monitor.events.put(("preview", 0))       # audit LOW: the
        # rebuilt live_switch renders UNSELECTED while the lease would
        # otherwise keep streaming ~2.5 s - release the lease at the
        # START, so the switch's off face matches reality the moment
        # it lands
        if getattr(self, "_unveil_job", None) is not None:
            # audit MED (the <300 ms race): a timed lift still pending
            # from the boot/_show_first veil would fire INSIDE this
            # rebuild's own update() pump and cremate the shared veil
            # mid-sweep. Cancel before the re-veil - _veil carries the
            # same cancel at its top for every other caller; this one
            # names the ordering at the re-dress site the audit cited
            try:
                self.after_cancel(self._unveil_job)
            except Exception:
                pass
            self._unveil_job = None
        self._veil("rebuilding the panel...", absolute=True)  # the one
        # mapped full rebuild we do: without the veil this is exactly
        # the tk widget-by-widget build sweep (CTk #40), half a second
        # of the UI erasing itself in front of the user. The veil is
        # pinned to the WINDOW (absolute): the body it covers is the
        # very thing about to be destroyed.
        for widget in (self._top, self._actions, self._tabs_bar,
                       self._body):
            widget.destroy()
        win = getattr(self, "_setup_win", None)     # the setup screen
        # carries build-time colors (the punch-list's resurrected find,
        # gate finding 3: this slot was named for the dead wizard - the
        # live resident is the setup window, and a stale name let it
        # survive rebuilds dressed in the old skin): rebuild re-dresses
        # it by re-opening, so destroy the real resident and clear the
        # real slot
        if win is not None:
            try:
                win._close()                       # the scheduled
                # retire, not a raw destroy: the window guards its own
                # dying and its pump stops clean
            except Exception:
                try:
                    win.destroy()
                except Exception:
                    pass
            self._setup_win = None
        self.skin = theme.get_skin(self.cfg["ui"]["skin"])
        theme.apply_ctk_font(self.skin)
        ctk.set_appearance_mode(self.skin.mode)
        self.configure(fg_color=self.skin.bg)
        self._shown_ts = None                # repaint the preview fresh
        self.build_all()
        # the rebuild's own veil lifts event-driven (SMOOTH, Oct 15):
        # chained onto the same flush the show path uses - the deferred
        # profiles/editor render lives in the first update_idletasks
        # after build, and a fixed 300 ms guess can drop the cover mid-
        # sweep exactly as it did at boot. _repaint_switches does that
        # flush behind the veil, then the unveil rides the NEXT after(0)
        # in schedule order, still on the tracked _unveil_job slot so a
        # re-veil can cancel it; the 3 s watchdog stays the backstop.
        self.after(0, self._repaint_switches)
        self.after(0, self._sync_slider_wheels)
        self._unveil_job = self.after(0, self._unveil)


    # ------------------------------------------------------------ top bar --
    # ------------------------------------------------------------- veil --
    def _veil(self, note="PanelBoss", absolute=False, full=False,
              hold=3.0):
        """The Electron ready-to-show trick, tkinter edition: an
        OPAQUE frame at the page tier covering the body, painted
        BEFORE whatever rebuild happens, destroyed after. CTk's own
        advice against the known Windows build-sweep (issue #40) and
        the maintainer-endorsed cover-frame recipe; translucent veils
        are dither-lies in tk, so this one is solid. Callers MUST
        call _unveil (even on failure paths): a window that never
        lifts its veil is a bricked UI, which is why _tick_ui carries
        the watchdog below. `absolute` pins the veil to the WINDOW at
        the body's current box: for rebuild_for_skin the body itself
        is about to die, and a child veil would cremate with it
        exactly mid-sweep. The plain RELATIVE form rode the tab
        switch and was retired with it (Oct 12: switching raises a
        pre-painted layer now - no burst to cover); callers today
        pass full or absolute. `hold` is this veil's watchdog budget
        in seconds: the stock 3.0 fits every rebuild veil byte-
        identical, and only a caller whose work is SLOW BY DESIGN
        (the camera diagnostic sweep) passes a longer one - the
        watchdog reads it through _veil_hold."""
        if getattr(self, "_unveil_job", None) is not None:
            # a timed lift is still pending from the PREVIOUS veil (audit
            # MED: rebuilds under 300 ms raced the stale after - the
            # ghost lift erased the fresh veil mid-rebuild, and the
            # second tray-open's own 300 could fire twice). Cancel the
            # pending lift; the caller re-arms it on its own slot.
            try:
                self.after_cancel(self._unveil_job)
            except Exception:
                pass
            self._unveil_job = None
        if getattr(self, "_veil_lbl", None) is not None:
            # already veiled: never stack, but a caller may have just
            # changed the skin - re-dress the color, not the geometry.
            # A changed NOTE rides the same re-dress (diffed, per the
            # no-op-configure law): the diagnostic sweep posts its
            # progress ("(N of M done)") as fresh veil messages and
            # the in-place update is what keeps ONE veil on screen -
            # stacking would fight the never-stack invariant above.
            # And the re-dress RENEWS THE LEASE (owner amendment 4):
            # the watchdog lifts on SILENCE past the hold, not on the
            # age of the first raise - a veil that keeps being told
            # "still here" stays exactly as long as its work does, and
            # a dead sweep is caught one dead-man gap after its LAST
            # beat, not at a fixed budget's end.
            self._veil_since = time.time()
            self._veil_hold = float(hold)
            try:
                self._veil_lbl.configure(bg=self.skin.panel)
                lbl = self._veil_lbl.winfo_children()[0]
                if lbl.cget("text") != note:
                    lbl.configure(text=note)
                lbl.configure(bg=self.skin.panel, fg=self.skin.subtext)
            except Exception:
                pass
            return
        # PLAIN tk widgets: the veil is one solid rectangle plus one
        # label - CTk buys nothing here, and CTkFrame refuses
        # width/height on place() (its own sizing API), which the
        # absolute mode needs. Colors ride the skin (panel tier +
        # subtext ink), so the veil belongs to whichever skin is live.
        self._veil_lbl = tk.Frame(self, bg=self.skin.panel)
        tk.Label(self._veil_lbl, text=note, bg=self.skin.panel,
                 fg=self.skin.subtext,
                 font=("Segoe UI", 13, "bold")).pack(expand=True)
        if absolute:
            self.update_idletasks()   # audit LOW: the box below is read
                                      # from the body; on a never-mapped
                                      # window (start_minimized + early
                                      # rebuild) idle geometry is still
                                      # the stale 1x1 boot rect - flush it
                                      # so the pin lands on the real box
            self._veil_lbl.place(x=self._body.winfo_x(),
                                 y=self._body.winfo_y(),
                                 width=self._body.winfo_width(),
                                 height=self._body.winfo_height())
        elif full:
            # the first map: nothing is drawn yet, so the veil owns
            # the WHOLE client area (tabs and top bar included); the
            # title bar is non-client and already native chrome
            self._veil_lbl.place(x=0, y=0, relwidth=1, relheight=1)
        else:
            self._veil_lbl.place(in_=self._body, relwidth=1, relheight=1)
        self._veil_lbl.tkraise()
        # re-entrant calls (rebuild_for_skin sets a NEW skin while the
        # veil is up) keep the veil dressed in whatever tier is live
        self._veil_lbl.configure(bg=self.skin.panel)
        self._veil_lbl.winfo_children()[0].configure(
            bg=self.skin.panel, fg=self.skin.subtext)
        self._veil_since = time.time()
        self._veil_hold = float(hold)      # the watchdog reads THIS,
                                          # not a literal: the hold is
                                          # per-veil now
        try:
            self.update()                # paint NOW (idle tasks alone
                                         # leave it blank - documented
                                         # tk trap; veil has no handlers
                                         # so the re-entry is safe)
        except Exception:
            pass

    def _unveil(self):
        if self.state() == "withdrawn":
            # gate finding 3 (Oct 15): the after(0) chain can drain
            # before the WM delivers <Map> on the close->reopen path;
            # re-arm once, the first <Configure> re-fires the flush
            # chain, and the 3 s watchdog stays the fuse.
            self._unveil_job = self.after(0, self._unveil)
            return
        self._unveil_job = None         # a fired/forced lift is no
                                        # longer pending: a stale id
                                        # here would make the next
                                        # _veil cancel the ghost
        # the heartbeat lease dies with its veil (owner amendment 4
        # re-issue): 35 s of tolerated silence was the SWEEP'S
        # permission, not the window's - reset to the stock 3 s so a
        # dead heartbeat cannot leak into the next ordinary veil
        # even between veil calls (the reviewer's flagged leak)
        self._veil_hold = 3.0
        v = getattr(self, "_veil_lbl", None)
        self._veil_lbl = None
        if v is not None:
            try:
                v.destroy()
            except Exception:
                pass                     # gone already: the point stands
        # AND FINISH WHAT THE VEIL WAS COVERING, IN THIS CALL (owner
        # ruling, Oct 24: "the boottime veil does not hide all
        # drawing"). A cover only hides the frames that happen UNDER it;
        # destroying it exposes the whole client area at once, and Tk
        # then repainted that area over the next loop turns - widget by
        # widget, which reads as the UI painting itself after the veil
        # is gone. Draining Tk's redraw queue here ends the reveal
        # inside this call: veil -> complete window, no half-drawn
        # middle. Tk's own pass, NOT a forced Win32 present: measured
        # Oct 24, the ERASE+ALLCHILDREN form repaints every widget
        # explicitly (~5x the work) and this is the window's most
        # exposed moment.
        try:
            self.update_idletasks()
        except tk.TclError:
            pass                         # destroyed mid-unveil: the
            #                              window is gone, the point
            #                              stands

    def _build_top(self):
        ctk.CTkLabel(self._top, text="PanelBoss",
                     font=self.skin.font(18, "bold"),
                     **self.skin.text_style()).pack(side="left")
        self.chip = ctk.CTkLabel(self._top, text=self.monitor.state,
                                 width=90, pady=theme.S_FIELD,
                                 corner_radius=10,
                                 font=self.skin.font(12, "bold"),
                                 text_color=self.skin.on_accent,
                                 fg_color=self.skin.chip(
                                     self.monitor.state))
        self.chip.pack(side="left", padx=theme.S_SECTION)
        self.idle_label = ctk.CTkLabel(self._top, text="",
                                       font=self.skin.font(12),
                                       **self.skin.text_style("sub"))
        self.idle_label.pack(side="left")
        # the patron link, top-right: the cup is drawn in code (like
        # the UAC shield), one ink per appearance mode - a near-black
        # cup on the near-black window would be a hole, not an icon
        self._kofi_img = ctk.CTkImage(
            light_image=kofi_pil(36),
            dark_image=kofi_pil(36, ink=(226, 229, 232, 255)),
            size=(18, 18))
        self.kofi_button = ctk.CTkButton(
            self._top, text="buy me a beer", image=self._kofi_img,
            compound="left", height=28,
            fg_color="transparent", hover_color=self.skin.panel,
            text_color=self.skin.subtext, font=self.skin.font(12),
            corner_radius=self.skin.radius, command=self._kofi)
        self.kofi_button.pack(side="right")


    def _build_actions(self):
        """The desk commands get their own row above the tabs: they
        steer the running watch, and welded to the title they read
        like window chrome. The rescue button lives here too - lost
        windows are not a problem that only happens on the profiles
        tab, and a panic button behind a tab click is not a panic
        button. pack stacks from the right edge inwards, so Quit -
        which always owns the last cell - is packed first."""
        # the rescue hint rides UNDER the button (the design system's
        # inline hint row, not a "?" chip): a cell frame gives the hint
        # its own line without pushing the rest of the action row
        cell = ctk.CTkFrame(self._actions, fg_color="transparent")
        cell.pack(side="left")
        self.rescue_button = ctk.CTkButton(
            cell, text="rescue my lost windows", width=170,
            command=self._rescue_now, **self.skin.secondary())
        self.rescue_button.pack(anchor="w")
        # UI-1c reversal: the panic button's story pops on its own
        # hover (the _hint line below is the documented no-op twin)
        self.rescue_button.bind(
            "<Enter>",
            lambda e=None: self.tips._schedule(TIPS["profile_rescue"],
                                               self.rescue_button),
            add="+")
        self.rescue_button.bind(
            "<Leave>", lambda e=None: self.tips._hide_soon(), add="+")
        self._hint(cell, TIPS["profile_rescue"])
        # THE OWNER'S PLACEMENT TRIO (Oct 16): the profiles card's
        # "restore my windows" gets a CLONE on this row, beside the
        # rescue it sits next to. Same route as the card's button -
        # _profile_apply(False, scope="windows") applies the captured
        # layout's windows leg alone and opens what is missing; the
        # lock, say line and refusal balloon are the apply path's own.
        # No new state: the card's live truth source is _prof_sel (set
        # by the picker's command), and _profile_apply reads exactly
        # that, so the clone resolves the same profile with nothing of
        # its own. It joins _apply_btns EXACTLY as the card's does -
        # the tuple is rebuilt every pane render (the card's law), so
        # the clone re-joins there and rides the same lock for its life.
        self.restore_wins_button = ctk.CTkButton(
            self._actions, text="restore my windows", width=150,
            command=lambda: self._profile_apply(False, scope="windows"),
            **self.skin.secondary())
        self.restore_wins_button.pack(side="left", padx=(theme.S_FIELD, 0))
        right = ctk.CTkFrame(self._actions, fg_color="transparent")
        right.pack(side="right")
        self.quit_button = ctk.CTkButton(
            right, text="Quit", width=70, command=self._quit,
            fg_color=self.skin.off,
            hover_color=self.skin.button,
            text_color=self.skin.text,
            corner_radius=self.skin.radius)
        self.quit_button.pack(side="right", padx=theme.S_FIELD)
        self.pause_button = ctk.CTkButton(right, text="Pause", width=90,
                                          command=self._pause_toggle,
                                          **self.skin.secondary())
        self.pause_button.pack(side="right", padx=theme.S_FIELD)
        self.sleep_button = ctk.CTkButton(right, text="sleep", width=90,
                                          command=self._sleep_dialog,
                                          **self.skin.secondary())
        self.sleep_button.pack(side="right", padx=theme.S_FIELD)


    def _sleep_dialog(self):
        """One button instead of three hardcoded snoozes: a slider
        asks how long, and the watch is only put to sleep on OK -
        a dialog that acted on click would be cancelled by reflex."""
        def send(minutes):
            self.monitor.events.put(("snooze", minutes))
        dlg = _SleepPrompt(self, self.skin, send)
        dlg.lift()
        return dlg


    # ------------------------------------------------------------ changes ---
    def _save(self):
        if self._save_job is not None:
            self.after_cancel(self._save_job)
        self._save_job = self.after(400, self._save_now)


    def _save_now(self):
        self._save_job = None
        try:
            config.write_config(self.cfg, self.cfg["_path"])
        except Exception:
            log.exception("config save failed")


    # ------------------------------------------------------ size recall --
    # The owner drags the window once; every later launch opens it that
    # size. Only the PAIR is remembered - never the position (the desk
    # moves windows; a remembered corner is how apps grow onto dead
    # monitors) - and only through the settings card's own save path,
    # behind a 750 ms debounce so a drag writes once, not per pixel.

    SIZE_LO = (600, 420)            # clamp floor; minsize()'s twin above

    def _workarea(self):
        """The primary screen's work area (taskbar excluded - a window
        that opens 48 px too tall loses its buttons under the bar).
        tk only knows the FULL screen, so ask Windows; the fallback is
        honest (full screen) where the call is unavailable."""
        try:
            import ctypes
            from ctypes.wintypes import RECT
            r = RECT()
            ctypes.windll.user32.SystemParametersInfoW(
                0x0030, 0, ctypes.byref(r), 0)      # SPI_GETWORKAREA
            return max(r.right - r.left, 600), max(r.bottom - r.top, 420)
        except Exception:
            return (self.winfo_screenwidth(), self.winfo_screenheight())


    def _initial_size(self):
        """The recalled [ui] window_size, clamped into the usable box.
        The first-line failure path: a garbage pair (0x0, an absurd
        99999, a half-written list) is clamped (or defaults, when it
        does not parse at all) AND confesses in the log - a window the
        user cannot grab is a bug report, a clamped one is a Tuesday."""
        raw = self.cfg["ui"].get("window_size") or []
        d_w, d_h = config.DEFAULTS["ui"]["window_size"]
        try:
            w, h = int(raw[0]), int(raw[1])
        except (TypeError, ValueError, IndexError):
            if raw:
                log.info("window size %r unreadable - stock default", raw)
            w, h = d_w, d_h
        hi_w, hi_h = self._workarea()
        cw, ch = max(self.SIZE_LO[0], min(w, hi_w)), \
            max(self.SIZE_LO[1], min(h, hi_h))
        if (cw, ch) != (w, h):
            log.info("window size %dx%d clamped to %dx%d", w, h, cw, ch)
        return cw, ch


    def _on_configure(self, event):
        """resize-recall: the root's OWN w/h changing (not a move, not
        an iconified/withdrawn reshape) re-arms one 750 ms timer; the
        burst lands as a single write. The dedupe pair is the LAST
        WRITTEN one - cfg["ui"]["window_size"], what _remember_size
        replaces on every save (audit INFO): the old compare against
        the boot recall let a drag back to the original size look like
        a no-op, and the first save never armed."""
        if event.widget is not self or self.state() != "normal":
            return
        raw = self.cfg["ui"].get("window_size") or []
        try:
            if (event.width, event.height) == (int(raw[0]), int(raw[1])):
                return
        except (TypeError, ValueError, IndexError):
            pass
        if self._size_job is not None:
            self.after_cancel(self._size_job)
        self._size_job = self.after(750, self._remember_size)


    def _remember_size(self):
        self._size_job = None
        try:
            if self.state() != "normal":       # trayd/zoomed mid-burst
                return
            w, h = self.winfo_width(), self.winfo_height()
        except tk.TclError:
            return
        self.cfg["ui"]["window_size"] = [w, h]  # REPLACE, never mutate
        self._save()                           # in place: the merge is
                                               # shallow and a fresh cfg
                                               # aliases DEFAULTS here


    def _cancel_size_job(self):
        if getattr(self, "_size_job", None) is not None:
            try:
                self.after_cancel(self._size_job)
            except ValueError:
                pass                           # already fired
            self._size_job = None


    def _pause_toggle(self):
        self.monitor.events.put(("pause", not self.monitor.paused))


    def _quit(self):
        if self._size_job is not None:  # FLUSH the size recall first
            self._remember_size()       # (gate finding 2): a quit
        if self._save_job is not None:  # inside the 750 ms debounce
            self._save_now()            # must not lose the last drag
                                        # (quit lands inside the 400 ms
                                        # window often; the old silent
                                        # drop also left a Tcl note at
                                        # teardown - lander concern 2)
        self.monitor.events.put(("quit", True))  # race teardown


    KO_FI = "https://ko-fi.com/nocterrible"


    def _kofi(self):
        """the patron page in the default browser - stdlib opener, no
        shell window (the app's standing policy on windows it did not
        ask to open)"""
        import webbrowser
        try:
            webbrowser.open(self.KO_FI)
        except Exception:
            log.warning("no browser answered the kofi link")


    # ---------------------------------------------------------------- close --
    def _hide(self):
        self._cancel_size_job()         # pending debounce vs teardown
        self.withdraw()                   # the app keeps running in the
        self.tips.kill()                  # tray; the lease dies
        self.monitor.events.put(("preview", 0))


def run(cfg, monitor, ui_events):
    # boot containment (audit W2C MED): the CTk root maps WITHDRAWN at
    # construction, so a build_all/_show_first raise (both run INSIDE
    # __init__) leaves a live, undestroyed root with no mainloop and
    # no tick - a zombie - and the measured second-CTk-root class says
    # an in-process retry would then kill the whole Tcl app. A raise
    # inside the constructor never binds the name, so the root is
    # buried through tkinter's own default-root handle (exactly one
    # root is ever born here, and it is the window). Destroy, confess,
    # RE-RAISE: cli._drive's shield catches, boxes, and the shutdown
    # proceeds.
    try:
        window = SettingsWindow(cfg, monitor, ui_events)
    except Exception:
        # the epitaph BEFORE the burial (owner UAT, Oct 15): a destroy
        # that hangs (cross-thread Tcl lock with the hider/overlay
        # interpreters alive) used to swallow this line - the one line
        # that names the raise. Log first, sweep second; the re-raise
        # below is unchanged (gate ledger 11: the sweep must not mask).
        log.exception("boot: settings window died; the half-dressed "
                      "root is destroyed and the failure re-raised")
        try:
            window.destroy()
        except (NameError, tk.TclError):  # the raise came from inside
            # __init__: the name was never bound, the born root may
            # be this process's default - sweep ONLY a root of THIS
            # thread (owner UAT, Oct 15): the worker painters tag
            # theirs (hider._tk_painter), and destroying another
            # thread's root from here is the cross-thread Tcl
            # deadlock that ate the epitaph all night. An untagged
            # root was born here, on this thread: this window's. A
            # foreign default is left standing and the half-dressed
            # root leaks until exit - ordinary windows die with the
            # process, the hider's own law borrowed here - and a raw
            # destroy raise must still not MASK the boot failure
            # (gate ledger 11).
            root = tk._default_root
            if root is not None and getattr(
                    root, "_owner_thread",
                    threading.get_ident()) == threading.get_ident():
                root.destroy()
            elif root is not None:
                log.error("boot sweep skipped: the default root answers "
                          "to another thread (destroying it here would "
                          "deadlock the boot)")
        raise
    window.mainloop()
    return window
