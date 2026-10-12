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
"""


from __future__ import annotations

import logging
import time
import tkinter as tk

import customtkinter as ctk

from ... import config
from .. import theme
from ..helpbtn import Tips
from ..kofi import kofi_pil
from ._constants import TABS, TIPS
from ._scroll import ScrollHost
from ._widgets import _SleepPrompt
from ._widgets import _WidgetsMixin
from ._runtime import _RuntimeMixin
from ._detection import _DetectionMixin
from ._preview import _CameraMixin
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
    _CameraMixin,
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
        # the CTk root maps at BIRTH, before a single widget exists:
        # withdraw instantly so the empty window never gets a frame on
        # screen - the first pixels a user may ever see come from
        # _show_first (veil included), never from a build sweep
        self.withdraw()
        self._ever_mapped = False
        self.cfg = cfg
        self.monitor = monitor
        self.ui_events = ui_events
        self.skin = theme.get_skin(cfg["ui"]["skin"])
        self.title("PanelBoss")
        self.geometry("920x640")
        self.minsize(760, 520)
        self.protocol("WM_DELETE_WINDOW", self._hide)     # close = to tray
        self._cams = None
        self._shown_ts = None
        self._ctkimg = None
        self._save_job = None
        self._veil_lbl = None
        self._veil_since = 0.0
        self._lease_ticks = 0
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
        self._scan_cameras()
        self.after(90, self._tick_ui)


    def _show_first(self):
        """The ONE first map, veiled. deiconify marks the window for
        mapping; the veil is placed before the first update() so the
        first COMPOSITE carries the veil, not the half-drawn UI. The
        real widgets paint behind it clipped-cheap; the timed lift
        (300 ms) lands after the burst - tk cannot pre-paint a
        withdrawn window (documented trap), so the veil covers the
        burst itself instead. After this, every reopen is a plain
        deiconify: DWM still holds the drawn surface, Electron's
        actual trick, available free."""
        self.deiconify()
        if not self._ever_mapped:
            self._ever_mapped = True
            self._veil("PanelBoss", full=True)
            self.after(300, self._unveil)
        else:
            self.lift()


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
        self._show_tab(self._tab)


    def _show_tab(self, key):
        page = self.pages[key]
        if key == self._tab and page.winfo_manager():
            return                     # the page is already up: a tab
            # button on the visible tab must not unmap-and-remap the
            # whole widget tree (repaint profile: the remap IS the cost)
        self.tips.kill()                 # a tooltip anchored to a row
        self._tab = key                  # would float over the new page
        for other in self.pages.values():
            other.pack_forget()
        page.pack(fill="both", expand=True)
        for k, b in self.tab_buttons.items():
            b.configure(**(self.skin.primary() if k == key
                          else self.skin.secondary()))


    def rebuild_for_skin(self):
        self.tips.kill()
        self._veil("rebuilding the panel...", absolute=True)  # the one
        # mapped full rebuild we do: without the veil this is exactly
        # the tk widget-by-widget build sweep (CTk #40), half a second
        # of the UI erasing itself in front of the user. The veil is
        # pinned to the WINDOW (absolute): the body it covers is the
        # very thing about to be destroyed.
        for widget in (self._top, self._actions, self._tabs_bar,
                       self._body):
            widget.destroy()
        self.skin = theme.get_skin(self.cfg["ui"]["skin"])
        ctk.set_appearance_mode(self.skin.mode)
        self.configure(fg_color=self.skin.bg)
        self._shown_ts = None                # repaint the preview fresh
        build_all = self.build_all()
        self._unveil()


    # ------------------------------------------------------------ top bar --
    # ------------------------------------------------------------- veil --
    def _veil(self, note="PanelBoss", absolute=False, full=False):
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
        exactly mid-sweep. Normal callers want the plain relative
        veil, which tracks the body's resizes for free."""
        if getattr(self, "_veil_lbl", None) is not None:
            # already veiled: never stack, but a caller may have just
            # changed the skin - re-dress the color, not the geometry
            try:
                self._veil_lbl.configure(bg=self.skin.panel)
                self._veil_lbl.winfo_children()[0].configure(
                    bg=self.skin.panel, fg=self.skin.subtext)
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
        try:
            self.update()                # paint NOW (idle tasks alone
                                         # leave it blank - documented
                                         # tk trap; veil has no handlers
                                         # so the re-entry is safe)
        except Exception:
            pass

    def _unveil(self):
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


    def _pause_toggle(self):
        self.monitor.events.put(("pause", not self.monitor.paused))


    def _quit(self):
        self.monitor.events.put(("quit", True))


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
        self.withdraw()                   # the app keeps running in the
        self.tips.kill()                  # tray; the lease dies
        self.monitor.events.put(("preview", 0))


def run(cfg, monitor, ui_events):
    window = SettingsWindow(cfg, monitor, ui_events)
    window.mainloop()
    return window
