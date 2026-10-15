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
  (skin, autostart, logs) is meta - it goes in General
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
        self._unveil_job = None          # the tracked after(300) that lifts
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
        """Every map up to the first MANUAL open is veiled; later maps
        are plain deiconifies: DWM still holds the drawn surface,
        Electron's actual trick, available free. The veil rides each
        of those maps, not just one: the budget belongs to the owner,
        not the process. A launch that shows its window at boot
        mapped (and swept) without being asked; the ceremony the
        owner sees is THEIR first tray-open, and yesterday's
        one-map-evers rule let the unasked boot map eat it (owner:
        "both skip the veil" - they opened a window that had already
        been shown at boot by someone else's relaunch ritual). deiconify
        marks the window for mapping; the veil is placed before the
        first update() so the first COMPOSITE carries the veil, not
        the half-drawn UI. The real widgets paint behind it
        clipped-cheap; the timed lift (300 ms) lands after the burst -
        tk cannot pre-paint a withdrawn window (documented trap), so
        the veil covers the burst itself instead. The veil watchdog
        in _tick_inner caps any stuck veil at 3 s. The veil lands on
        the UNMAPPED window (audit INFO: the old deiconify-then-veil
        left a raise window open between the map and the cover - an
        un-veiled half-paint frame): _veil reads no map state, so the
        swap is safe."""
        if not self._manual_open_done:
            self._veil("PanelBoss", full=True)
            self._unveil_job = self.after(300, self._unveil)
            if manual:
                self._manual_open_done = True
            self.deiconify()
        else:
            # the veil rides EVERY manual open, not just the first
            # (owner UAT, Oct 15): after a close, the next tray-open
            # drew the full UI with no cover, so the reveal looked
            # like a redraw and the tray's own raise looked like a
            # rebuild. DWM keeps the surface painted only while the
            # window stays alive; a close destroys it and the next
            # map is a fresh paint burst that wants the veil as much
            # as the birth map did. The raise for an ALREADY-mapped
            # window takes the plain path - the burst there is the
            # widget repaint below, not a first composite.
            was_mapped = self.state() != "withdrawn"
            if manual and not was_mapped:
                self._veil("PanelBoss", full=True)
                self._unveil_job = self.after(300, self._unveil)
            self.deiconify()
            self.lift()
        # knob-lie belt (second corpse, the owner's bar-was-on catch):
        # every switch painted during this window's hidden birth drew
        # its knob at zero geometry - the deferred resync re-arms the
        # same truth paint once the map and its <Configure> have
        # landed (see _repaint_switches; the probe pins the ordering).
        self.after(0, self._repaint_switches)


    # -------------------------------------------------- switch repaint --
    # One dispatch table per PANE (the owner's law: the next switch
    # added to the house joins for free by riding its pane's sync
    # entry, never by remembering call sites). Values are method
    # names; every entry paints BOTH branches from its truth source -
    # cfg, the registry, the editor dict - and fires no commands.
    SWITCH_SYNC = {
        "detection": ("_sync_consent_switch",),
        "monitor profiles": ("_sync_restore_switches",
                             "_sync_editor_switches"),
        "power plan": ("_sync_power_switches", "_sync_gaming_switches"),
        "general": ("_sync_general_switches",),
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
        self._build_profiles(self.pages["monitor profiles"].inner)
        self._build_power(self.pages["power plan"].inner)
        self._build_general(self.pages["general"].inner)
        self._build_oled(self.pages["oled"].inner)
        # The layer law (owner, Oct 12: "tabbing just reveals them
        # instead of fully redrawing them each time"): every page is
        # placed ONCE into the body and stays mapped and painted for
        # the life of the build - the overlap is the point, and
        # relwidth/relheight track body resizes for free.
        for p in self.pages.values():
            p.place(in_=self._body, x=0, y=0, relwidth=1, relheight=1)
        start = self._tab
        self._tab = None               # fresh layers, undressed buttons:
        self._show_tab(start)          # the first call must run past
                                       # the guard (rebuild_for_skin
                                       # lands here too)


    def _show_tab(self, key):
        """The layer law (re-cut Oct 12, owner: "can we draw all
        screens and just layer them behind each other so tabbing just
        reveals them instead of fully redrawing them each time?"):
        the pages were ALWAYS all built at boot; the crawl lived in
        the pack_forget/pack remap - every CTk canvas re-renders on
        re-map (issue #40 class). They now ride the body as
        permanently mapped layers and a switch is ONE tkraise: no
        unmap, no burst, so the switch veil, its forced update() and
        its 120 ms lift die with the remap that needed them. The
        boot/skin veils STAY: _show_first and rebuild_for_skin sweep
        with real widget births, which no layering can hide."""
        page = self.pages[key]
        if key == self._tab and page.winfo_manager() == "place":
            return                     # already the revealed layer: a
            # click on the lit tab must not re-dress anything (build_all
            # nulls _tab first, so a fresh build never trips this)
        self.tips.kill()                 # a tooltip anchored to a row
        self._tab = key                  # would float over the new page
        page.tkraise()                   # THE WHOLE SWITCH
        page.sync_region()               # belt for the wheel: geometry
        # did not move under a raise, but this is exactly the seam
        # _page_region's law says a re-measure belongs (one loop late)
        for k, b in self.tab_buttons.items():
            b.configure(**(self.skin.primary() if k == key
                          else self.skin.secondary()))
        # knob-lie belt, pane arm: the reveal re-paints this pane's
        # truth switches (their build paint may have happened hidden;
        # a switch's geometry cannot lie twice under the eye that
        # reads it - the same table as the show path, scoped here)
        self._repaint_switches(pane=key)


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
        self._unveil_job = self.after(300, self._unveil)  # the rebuild's
        # own veil lifts from its OWN fresh after on the tracked slot -
        # the same one _show_first arms, so a re-veil can cancel it,
        # never a bare untracked after; the 300 ms also covers the
        # post-rebuild paint burst the cover-frame exists for. A raise
        # inside build_all leaves the veil to the 3 s watchdog, same
        # failure path as the old bare _unveil() tail.


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
