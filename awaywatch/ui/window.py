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
import os
import queue
import subprocess
import sys
import textwrap
import threading
import time

import cv2
import customtkinter as ctk
from PIL import Image

from .. import config, profiles, wm
from . import deps, theme
from .helpbtn import Tips
from .kofi import kofi_pil
from .shield import shield_pil

log = logging.getLogger("ui")

TIMER_SPECS = [          # section, key, label, min, max, step, help
    ("timers", "idle_gate_sec", "idle gate", 0, 180, 5,
     "the camera never runs while typing; this is how long recent "
     "input still counts as typing"),
    ("timers", "absent_confirm_sec", "absence confirm", 10, 300, 5,
     "how long absence must be seen before the screens go dark - "
     "one unseen frame is never trusted"),
    ("timers", "on_poll_sec", "poll while on", 1, 15, 1,
     "how often the camera wakes while the screens are on and "
     "absence is being confirmed"),
    ("timers", "off_poll_sec", "poll while off", 1, 15, 1,
     "how often the camera watches for a return while the screens "
     "are dark (the LED is invisible anyway)"),
    ("timers", "present_recheck_sec", "present recheck", 10, 300, 5,
     "how often a confirmed person is re-checked while they sit there"),
    ("timers", "re_off_grace_sec", "re-off grace", 0, 120, 5,
     "after an unexpected wake this is the camera's chance to find "
     "the person before the screens go dark again"),
    ("recovery", "leave_on_grace_sec", "leave-on grace", 10, 600, 10,
     "with the leave-on wake policy: how long the screens are left "
     "alone for whoever woke them before the app starts guarding "
     "them again"),
]

DEVICE_KEYS = [("auto", "auto"), ("cpu", "CPU"), ("cuda", "CUDA GPU")]
DEVICE_BY_LABEL = dict((label, key) for key, label in DEVICE_KEYS)

TABS = ("detection", "monitor profiles", "power plan", "general")

PERSON_ROWS = ("device", "cuda gpu id", "confidence", "min hits")
MOTION_ROWS = ("frame changes", "pixel delta", "motion hold")

TIPS = {
    "mode": "person: the ONNX model judges every frame. motion: pure "
            "frame differencing - no ML, nothing learned about faces, "
            "and it drives infrared and depth sensors exactly like a "
            "webcam. Switching rebuilds the detector immediately; the "
            "model's device and thresholds vanish here.",
    "device": "where the model runs. auto lets onnxruntime choose, "
                "CPU always works, CUDA is faster when a card exists. "
                "Applies immediately - the session is rebuilt.",
    "gpu": "which card, for the record, when device is CUDA. Applies "
            "immediately.",
    "confidence": "how sure a detection must be before a frame counts "
                   "as a person. Applied to the next frame; no restart.",
    "min_hits": "consecutive positive frames before the screens are "
                "re-woken. One lucky frame is never believed.",
    "frame changes": "share of the (downscaled) frame that must move "
                      "before a poll counts as motion. Applies "
                      "immediately.",
    "pixel delta": "how much one pixel must shift to count as a change "
                    "- raise it for noisy depth or infrared sensors. "
                    "Applies immediately.",
    "motion hold": "presence lingers this long after the LAST motion: "
                    "reading a page is stillness, not absence. Applies "
                    "immediately.",
    "wake": "the screens came back on their own (a mouse jiggle, a "
             "wake word). re-off darkens them again after the re-off "
             "grace unless a person is confirmed; leave-on hands the "
             "desk over for its grace period instead. Applies "
             "immediately.",
    "fullscreen": "exclusive-fullscreen games swallow the power-off "
                   "broadcast - the app keeps its hands off while a "
                   "game owns the display.",
    "reoff": "after two unexpected wakes in a row the app stops "
               "believing its own camera and leaves the screens lit "
               "until a person shows up or this is resumed here.",
    "hold_display": "Windows is not allowed to turn the screens off "
                     "while the app watches a lit desk. Nothing in the "
                     "power plan changes - the timer is only held back, "
                     "and only while this app runs: pausing, snoozing "
                     "or quitting hands it back.",
    "hold_sleep": "the plan's sleep timer is held back too. While the "
                   "screens are dark this is what keeps the watcher "
                   "alive to notice the return; with it off the box "
                   "sleeps on schedule and the app re-arms when the "
                   "power button is pressed.",
    "restore_windows": "some monitors unplug themselves from Windows "
                       "when they sleep, and Windows re-lays every window "
                       "on them to the wrong screen when they return. "
                       "Before the screens go dark the app remembers every "
                       "window's pixel rect and the monitors' hardware "
                       "identity; after any wake - its own, a mouse "
                       "jiggle, or the power button - it waits for the "
                       "topology to settle and moves everything back. If a "
                       "monitor was swapped or unplugged for good, the "
                       "saved positions belong to another desk and nothing "
                       "is moved. Minimized windows and popups are left "
                       "alone.",
    "profile_picker": "a profile is the whole desk spelled out: which "
                      "physical monitors (by hardware identity, so "
                      "renumbered slots fool nothing) are on, where "
                      "they sit, which is primary, each one's "
                      "resolution and refresh rate, the HDR ask, and "
                      "where every pinned window belongs. the picker "
                      "opens on the profile last used for the layout it "
                      "sees right now; 'create new...' copies what the "
                      "desk is doing and lets you name it. the one "
                      "thing a profile cannot fix is a monitor that is "
                      "not plugged in - modes can be asked for, a "
                      "missing panel cannot.",
    "profile_rescue": "the panic button: every visible window that no "
                      "screen covers - the classic victim of a "
                      "resolution change made while it sat on the "
                      "monitor that just left - comes back to the "
                      "middle of the primary monitor. minimized "
                      "windows, dialogs and windows living on other "
                      "virtual desktops are left alone.",
    "profile_match": "how a saved seat recognises its live window. "
                     "'process' is the default: a browser or chat "
                     "window renames itself a hundred times a day, so "
                     "a pin that trusts titles was dead the moment you "
                     "clicked another tab. The price is honest and the "
                     "editor says it out loud when it applies: a "
                     "process pin moves EVERY window of that app, not "
                     "just the one you picked. 'process + title' is the "
                     "one-window road (right for apps that never "
                     "retitle); 'title' alone matches by name only.",
    "profile_hdr": "what to do with HDR when the profile applies. "
                   "'restore as captured' puts every panel back the "
                   "on/off state the profile saw at capture - per "
                   "monitor, so two HDR panels can each keep their "
                   "own habits. 'ignore' never asks anything. 'all "
                   "on/off' forces EVERY hdr-capable panel the same "
                   "way - both of yours, if both can; panels without "
                   "hdr are never ordered to do the impossible. on "
                   "windows 11 24h2 and later hdr is a READABLE "
                   "fact: the app asks the driver per monitor (the "
                   "live answer sits next to each monitor above), "
                   "commands only the monitors that disagree, then "
                   "reads back to confirm. on older windows that "
                   "answer cannot be had: 'restore as captured' "
                   "skips itself (restoring a guess is not "
                   "restoring), while all-on/all-off fall back to "
                   "pressing win+alt+b and keeping their own belief. "
                   "profiles captured before this snapshot existed "
                   "have nothing to restore - the apply says so.",
    "profile_apply": "one click reshapes the desk: topology first (new "
                     "primary last - windows refuses to move the "
                     "desktop in the same call that hands it over), "
                     "modes asked only from the driver's own list, hdr "
                     "commanded at exactly the monitors that disagree "
                     "(a hotkey only on ancient windows), then a wait "
                     "until the monitors ANSWER as "
                     "the profile asked (windows reports success "
                     "before the modes have settled - measured), and "
                     "only then the windows. anything the shuffle "
                     "stranded off-screen is rescued on the spot.",
    "profile_pins": "a seat reserved for an app: pick one of the "
                    "open windows, set its terms, pin it - the spot "
                    "it holds RIGHT NOW becomes the seat it must "
                    "return to. 'pin every open app' seeds a seat for "
                    "each running program at once. clicking a pinned "
                    "row lifts it back into the editor (refreshing "
                    "the seat = move the window where you want it, "
                    "then update the pin); x forgets the seat. the "
                    "profile moves what it pinned and never touches "
                    "windows it did not.",
    "profile_pin_open": "'open it if missing' runs the saved exe "
                        "when no window of that app answered the "
                        "profile, waits for a window to appear, and "
                        "moves it the moment it does. naive by honest "
                        "design: a bare exe run - store apps, stub "
                        "launchers and shortcut-only programs may "
                        "start nothing under that name. the advanced "
                        "rows exist for exactly that: tune how long "
                        "to wait, and browse to the launcher or "
                        "binary that really opens the window. the "
                        "first miss asks whether to fix the profile; "
                        "say no and later misses stay quiet.",
    "profile_pin_wait": "how long an 'open it' wait lasts before the "
                        "seat counts as missed (5 s to 10 min, "
                        "default 30). it ends the moment a window "
                        "shows - this only decides how long patience "
                        "survives a slow launcher or a cold disk.",
    "profile_pin_exe": "what 'open it' actually runs. by default the "
                       "exe of the app as captured while it ran - "
                       "often the wrong door (store stubs, updater "
                       "wrappers, relauncher shims that exit "
                       "instantly). browse points the pin at the "
                       "launcher or binary that really shows the "
                       "window; the shell runs it exactly as a "
                       "double-click would, so a .lnk shortcut works "
                       "too. the seat's row says [via launcher.exe] "
                       "when the exe no longer matches the app's own "
                       "file.",
    "restore_on": "a profile the app re-applies by itself when it "
                  "starts: the lever, pre-armed. Knowing the logon "
                  "copy is a fact, not a guess - the Run entry this "
                  "app installs carries --autostart (old flagless "
                  "entries learn it by themselves), so launching "
                  "the app yourself to fix something can stay a "
                  "quiet manual start while the logon copy reshapes "
                  "the desk.",
    "restore_profile": "'the last one for this desk' picks by the "
                       "panels physically present (a cold boot may "
                       "not have reached the profile's modes yet - "
                       "identity decides, same as an apply's gate). "
                       "Or name one profile exactly; if it was "
                       "deleted since, the restore says so on the "
                       "tray and does nothing else.",
    "restore_scope": "monitors only: modes, positions, primary, "
                     "HDR - windows stay exactly where they are. "
                     "windows only: pinned apps take their seats, "
                     "the drivers are never asked anything. the "
                     "desk gate guards every scope: different "
                     "panels means refuse, not improvise.",
    "restore_when": "'only logon starts' trusts the flag the Run "
                    "entry carries - a manual launch never moves "
                    "the desk while you are debugging it. 'every "
                    "app start' applies on any launch. Logon "
                    "copies always get the grace: the FIRST login "
                    "sits out 2 full minutes and times every app "
                    "that shows up; later logins launch only after "
                    "the slowest observed boot + 20 s (never under "
                    "30 s), and every 'open it' is 60 s more "
                    "patient than its own number.",
    "camera": "which camera the frames come from. Opening every index "
               "is slow (the virtual camera alone takes 16 s), so the "
               "list fills in after the window opens and rescans on "
               "demand.",
    "cam_on": "camera life while the screens are on: boot per poll "
               "rests the LED, always on streams through the standby "
               "transition.",
    "cam_off": "camera life while the screens are dark: always on is "
                "the measured-reliable choice (a device reopened "
                "INSIDE the standby transition never streams again).",
    "live": "holds the camera open for this window at ~5 fps so the "
            "picture shows exactly what the detector judged. The hold "
            "is a lease: closing the window releases the device.",
    "assistant": "powercfg /requests needs administrator rights, so a "
                  "scheduled task dumps it silently instead (one "
                  "confirm on tick). While another app holds the "
                  "display - a video wake lock, a presentation - the "
                  "camera stops defending a screen it does not own.",
    "skin": "the palette. The layout and all behavior are identical.",
    "min": "boot puts the tray icon down and nothing else (the "
            "monitor works fully either way); left-click the icon "
            "to open the window. Closing the window always hides it "
            "to the tray anyway - this only skips the first one. "
            "Applies from the next launch.",
    "startup": "the per-user Run key - exactly the entry Task "
                "Manager's startup tab lists. No admin, and the app "
                "verifies it by reading the registry back.",
    "logs": "every decision and the reason, in %APPDATA%\\ICU-"
             "PresenceDetector\\logs.",
    "update": "runs update.bat: pulls the newest copy and refreshes "
               "the dependencies. the app quits first - its own files "
               "are the ones being replaced - and the script reopens "
               "it when it finishes. if it stays closed, the update "
               "window says why; run.bat starts it by hand.",
    "hdr_away": "at screens-off the panels' HDR is turned off and "
                "exactly what was on per panel is handed back on wake; "
                "pre-24H2 Windows cannot tell HDR state, so we abstain "
                "there",
    "gaming": "a fullscreen game is owed its panel's top refresh rate; "
              "the desktop is owed a cooler one. only rates the panel "
              "already lists are ever traded - the watcher asks for no "
              "mode the driver will not take, and the resolution is "
              "never touched. a listed game enters the moment it owns "
              "a monitor; any other app must hold real evidence "
              "(sustained 3D-engine load or a loaded controller api) "
              "for the whole seen time first. leaving game mode rides "
              "a grace timer: an alt-tab to chat does not flicker the "
              "rate - the desktop rate comes back once, quietly, after "
              "the game stops answering.",
    "gaming_rates": "only the rates that panel's driver already offers "
                    "are on the list - the watcher trades from this "
                    "same list, so an unlisted rate is never asked "
                    "for. 'auto' means the panel's fastest. THE "
                    "DESKTOP RATE IS LAW WHILE NOT GAMING: the "
                    "watcher holds the panel at it always and re-heals "
                    "it whenever the driver forgets (reboots, driver "
                    "updates). 'keep' means nobody's business - the "
                    "watcher never starts a rule on that panel (a "
                    "panel IT clocked up for a game still comes back "
                    "to a sane 60 - or your rate - when the game "
                    "ends). VRR panels: tick VRR (pin max) after you "
                    "enable G-SYNC yourself - AwayWatch never touches "
                    "drivers, it just stops flipping that panel's "
                    "mode and keeps it at max; if you never enabled "
                    "VRR, pick an Hz or keep.",
    "gaming_games": "the exe names that enter game mode instantly the "
                    "moment they own a monitor - a title screen "
                    "renders at near-zero GPU and still owns the "
                    "panel. any other fullscreen app can still earn "
                    "in, it just holds its evidence longer. one exe "
                    "per line; 'add what's in front of me' appends the "
                    "window that currently covers the screen.",
    "gaming_ignore": "exe names that must never be treated as games, "
                     "even if they fool every other test. one exe per "
                     "line.",
    "gaming_plan": "swapped in while a game owns a monitor ('' = "
                   "never). the plan that was active BEFORE the game "
                   "comes back when it leaves - never a guessed "
                   "default - and only if nobody else moved it "
                   "meanwhile.",
     "dvr": "suppresses background recording and the Win+G overlay "
            "per docs/apack-findings.md; the registry is the truth - "
            "Windows Settings may rewrite these values at any time.",
}


WAIT_CHOICES = (5, 10, 15, 30, 45, 60, 90, 120, 180, 300, 600)

# the restore-at-start lever's vocabularies: (stored value, shown
# label) - the cfg file stays English-stable, the menus stay human
RESTORE_LAST = ("last", "the last one for this desk")
# the hdr ask in human words: the STORED values are the engine's
# (snap / leave alone / on / off; "toggle" survives only in old
# profiles and is no longer offered), the menu says what each one
# really does - per-monitor restore is not the same command as
# forcing every capable panel
HDR_ASK_LABELS = {"snap": "restore as captured (per monitor)",
                  "leave alone": "ignore HDR (leave as found)",
                  "on": "all hdr-capable panels on",
                  "off": "all hdr-capable panels off",
                  "toggle": "flip it (legacy)"}
HDR_MENU_ORDER = ("snap", "leave alone", "on", "off")
HDR_BY_LABEL = {label: ask for ask, label in HDR_ASK_LABELS.items()}
RESTORE_SCOPES = (("full", "the whole desk"),
                  ("monitors", "monitors only (modes + HDR)"),
                  ("windows", "windows only (pinned apps)"))
RESTORE_WHENS = (("autostart", "only logon/autostart starts"),
                 ("always", "every app start"))


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


class SettingsWindow(ctk.CTk):

    IR_INSTALL = "hello IR camera (optional - pick to install whircam)"

    def __init__(self, cfg, monitor, ui_events):
        super().__init__()
        self.cfg = cfg
        self.monitor = monitor
        self.ui_events = ui_events
        self.skin = theme.get_skin(cfg["ui"]["skin"])
        self.title("ICU Presence Detector")
        self.geometry("920x640")
        self.minsize(760, 520)
        self.protocol("WM_DELETE_WINDOW", self._hide)     # close = to tray
        self._cams = None
        self._shown_ts = None
        self._ctkimg = None
        self._save_job = None
        self._lease_ticks = 0
        self._tab = TABS[0]
        ctk.set_appearance_mode(self.skin.mode)
        self.configure(fg_color=self.skin.bg)
        self.build_all()
        if self.cfg["ui"].get("start_minimized"):
            self.withdraw()                # straight to the tray: this
            # happens before mainloop maps anything, so there is no
            # show-then-hide blink; the tray's left click opens home
        self._scan_cameras()
        self.after(90, self._tick_ui)

    # ------------------------------------------------------------- build --
    def build_all(self):
        self._top = ctk.CTkFrame(self, fg_color="transparent")
        self._top.pack(fill="x", padx=14, pady=(12, 2))
        self._actions = ctk.CTkFrame(self, fg_color="transparent")
        self._actions.pack(fill="x", padx=14)     # rescue/sleep/pause/
        # quit row: the desk commands belong above the tabs, not
        # welded to the title (and the title row keeps room for the
        # one link that is not a command)
        self._tabs_bar = ctk.CTkFrame(self, fg_color="transparent")
        self._tabs_bar.pack(fill="x", padx=14, pady=(6, 0))
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.pack(fill="both", expand=True, padx=14, pady=(6, 12))
        self.tips = Tips(self.skin, self)
        self._build_top()
        self._build_actions()
        self.tab_buttons = {}
        for key in TABS:
            b = ctk.CTkButton(self._tabs_bar, text=key, width=120,
                              height=30,
                              command=lambda k=key: self._show_tab(k))
            b.pack(side="left", padx=(0, 6), pady=(0, 8))
            self.tab_buttons[key] = b
        self.pages = {}
        for key in TABS:
            self.pages[key] = ctk.CTkScrollableFrame(
                self._body, fg_color="transparent",
                scrollbar_button_color=self.skin.button,
                scrollbar_fg_color=self.skin.panel)
        self._build_detection(self.pages["detection"])
        self._build_profiles(self.pages["monitor profiles"])
        self._build_power(self.pages["power plan"])
        self._build_general(self.pages["general"])
        self._show_tab(self._tab)

    def _show_tab(self, key):
        self.tips.kill()                 # a tooltip anchored to a row
        self._tab = key                  # would float over the new page
        for page in self.pages.values():
            page.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        for k, b in self.tab_buttons.items():
            b.configure(**(self.skin.primary() if k == key
                          else self.skin.secondary()))

    def rebuild_for_skin(self):
        self.tips.kill()
        for widget in (self._top, self._actions, self._tabs_bar,
                       self._body):
            widget.destroy()
        self.skin = theme.get_skin(self.cfg["ui"]["skin"])
        ctk.set_appearance_mode(self.skin.mode)
        self.configure(fg_color=self.skin.bg)
        self._shown_ts = None                # repaint the preview fresh
        build_all = self.build_all()

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

    # ------------------------------------------------------------ top bar --
    def _build_top(self):
        ctk.CTkLabel(self._top, text="ICU Presence Detector",
                     font=self.skin.font(18, "bold"),
                     **self.skin.text_style()).pack(side="left")
        self.chip = ctk.CTkLabel(self._top, text=self.monitor.state,
                                 width=90, pady=3, corner_radius=10,
                                 font=self.skin.font(12, "bold"),
                                 text_color="#10131a",
                                 fg_color=self.skin.chip(
                                     self.monitor.state))
        self.chip.pack(side="left", padx=14)
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
        self.rescue_button = ctk.CTkButton(
            self._actions, text="rescue my lost windows", width=170,
            command=self._rescue_now, **self.skin.secondary())
        self.rescue_button.pack(side="left")
        self.tips.button(self._actions, TIPS["profile_rescue"]).pack(
            side="left", padx=(4, 0))
        right = ctk.CTkFrame(self._actions, fg_color="transparent")
        right.pack(side="right")
        self.quit_button = ctk.CTkButton(
            right, text="Quit", width=70, command=self._quit,
            fg_color=self.skin.off,
            hover_color=self.skin.button,
            text_color=self.skin.text,
            corner_radius=self.skin.radius)
        self.quit_button.pack(side="right", padx=3)
        self.pause_button = ctk.CTkButton(right, text="Pause", width=90,
                                          command=self._pause_toggle,
                                          **self.skin.secondary())
        self.pause_button.pack(side="right", padx=3)
        self.sleep_button = ctk.CTkButton(right, text="sleep", width=90,
                                          command=self._sleep_dialog,
                                          **self.skin.secondary())
        self.sleep_button.pack(side="right", padx=3)

    def _sleep_dialog(self):
        """One button instead of three hardcoded snoozes: a slider
        asks how long, and the watch is only put to sleep on OK -
        a dialog that acted on click would be cancelled by reflex."""
        def send(minutes):
            self.monitor.events.put(("snooze", minutes))
        dlg = _SleepPrompt(self, self.skin, send)
        dlg.lift()
        return dlg

    # ---------------------------------------------------------- detection --
    def _build_detection(self, page):
        # ONE band anchored top-left: the camera card mounts beside
        # the settings column, never against the window edge -
        # stretching the window opens spare room to the RIGHT of the
        # pair, not in a canyon between its halves
        band = ctk.CTkFrame(page, fg_color="transparent")
        band.pack(anchor="nw")
        left = ctk.CTkFrame(band, width=380, fg_color="transparent")
        left.pack(side="left", fill="y")
        self._build_detect_card(left)
        self._build_timers(left)
        self._build_camera_card(band)

    def _build_detect_card(self, left):
        box = self._card(left, "Detection")
        # the mode row leads the card: motion mode has no model at all,
        # so the model's device and thresholds below it are mere trivia
        row = self._row(box, "mode", TIPS["mode"])
        self.mode_button = ctk.CTkSegmentedButton(
            row, values=["person (AI)", "motion (no AI)"], height=26,
            width=230, command=self._detect_mode_changed,
            **self.skin.segmented_style())
        self.mode_button.set(self._detect_mode_label(self.cfg))
        self.mode_button.grid(row=0, column=1, sticky="e")
        rows = [("mode", row)]

        row = self._row(box, "device", TIPS["device"])
        menu = ctk.CTkOptionMenu(row, values=[label for _, label in
                                              DEVICE_KEYS], width=160,
                                 command=self._device_changed,
                                 **self.skin.menu_style())
        menu.grid(row=0, column=1, sticky="e")
        menu.set(dict(DEVICE_KEYS)[self.cfg["inference"]["device"]])
        rows.append(("device", row))

        from .. import inference
        self.gpu_ids = inference.cuda_gpus()
        if not self.gpu_ids:
            self.gpu_ids = [(n, "") for n in range(4)]
        labels = ["%s %s" % (gid, name[:32]) for gid, name in self.gpu_ids]
        row = self._row(box, "cuda gpu id", TIPS["gpu"])
        gpu_menu = ctk.CTkOptionMenu(
            row, values=labels, width=200, command=self._gpu_changed,
            **self.skin.menu_style())
        gpu_menu.grid(row=0, column=1, sticky="e")
        for gid, name in self.gpu_ids:
            if gid == self.cfg["inference"]["device_id"]:
                self._set_menu(gpu_menu, "%s %s" % (gid, name[:32]))
                break
        rows.append(("cuda gpu id", row))

        row = self._row(box, "confidence", TIPS["confidence"])
        self.conf_label = ctk.CTkLabel(row, font=self.skin.font(12),
                                       **self.skin.text_style("sub"))
        self.conf_label.grid(row=0, column=2, sticky="e", padx=(6, 0))
        slider = ctk.CTkSlider(row, from_=0.1, to=0.9,
                               number_of_steps=80, width=180,
                               command=self._confidence_changed,
                               **self.skin.slider_style())
        slider.set(self.cfg["inference"]["confidence"])
        slider.grid(row=0, column=1, sticky="e")
        self.conf_label.configure(
            text="%.2f" % self.cfg["inference"]["confidence"])
        rows.append(("confidence", row))

        row = self._row(box, "min hits", TIPS["min_hits"])
        hits = ctk.CTkSegmentedButton(
            row, values=["1", "2", "3", "4"], height=26, width=170,
            command=self._min_hits_changed, **self.skin.segmented_style())
        hits.set(str(self.cfg["inference"]["min_hits"]))
        hits.grid(row=0, column=1, sticky="e")
        rows.append(("min hits", row))

        # motion's own knobs, hidden in person mode exactly as the
        # model's knobs are hidden here: each mode shows its controls
        row = self._row(box, "frame changes", TIPS["frame changes"])
        self.motion_labels = {}
        slider = ctk.CTkSlider(row, from_=0.0005, to=0.02,
                               number_of_steps=39, width=180,
                               command=lambda v, k="ratio":
                               self._motion_changed(k, v),
                               **self.skin.slider_style())
        slider.set(self.cfg["detection"]["ratio"])
        slider.grid(row=0, column=1, sticky="e")
        shown = ctk.CTkLabel(row, font=self.skin.font(12),
                             **self.skin.text_style("sub"))
        shown.grid(row=0, column=2, sticky="e", padx=(6, 0))
        shown.configure(text="%.4f" % self.cfg["detection"]["ratio"])
        self.motion_labels["ratio"] = shown
        rows.append(("frame changes", row))

        row = self._row(box, "pixel delta", TIPS["pixel delta"])
        slider = ctk.CTkSlider(row, from_=1, to=128, number_of_steps=127,
                               width=180,
                               command=lambda v, k="diff_level":
                               self._motion_changed(k, v),
                               **self.skin.slider_style())
        slider.set(self.cfg["detection"]["diff_level"])
        slider.grid(row=0, column=1, sticky="e")
        shown = ctk.CTkLabel(row, font=self.skin.font(12),
                             **self.skin.text_style("sub"))
        shown.grid(row=0, column=2, sticky="e", padx=(6, 0))
        shown.configure(text="%d" % self.cfg["detection"]["diff_level"])
        self.motion_labels["diff_level"] = shown
        rows.append(("pixel delta", row))

        row = self._row(box, "motion hold", TIPS["motion hold"])
        slider = ctk.CTkSlider(row, from_=10, to=600, number_of_steps=59,
                               width=180,
                               command=lambda v, k="hold_sec":
                               self._motion_changed(k, v),
                               **self.skin.slider_style())
        slider.set(self.cfg["detection"]["hold_sec"])
        slider.grid(row=0, column=1, sticky="e")
        shown = ctk.CTkLabel(row, font=self.skin.font(12),
                             **self.skin.text_style("sub"))
        shown.grid(row=0, column=2, sticky="e", padx=(6, 0))
        shown.configure(text="%ss" % self.cfg["detection"]["hold_sec"])
        self.motion_labels["hold_sec"] = shown
        rows.append(("motion hold", row))

        self._det_rows = rows               # build order is display order
        self.detect_note = ctk.CTkLabel(box, font=self.skin.font(10),
                                       wraplength=350, justify="left",
                                       anchor="w",
                                       **self.skin.text_style("sub"))
        self._show_mode_rows()

    def _show_mode_rows(self):
        """One truth: the model's knobs and the differencer's knobs
        never share the screen; whichever the mode does not use hides
        itself (a slider that changes nothing is a liar)."""
        mode = (self.cfg.get("detection") or {}).get("mode", "person")
        keep = MOTION_ROWS if mode == "motion" else PERSON_ROWS
        for key, widget in self._det_rows:
            widget.pack_forget()
        for key, widget in self._det_rows:
            if key == "mode" or key in keep:
                widget.pack(fill="x", pady=2)
        self.detect_note.pack_forget()
        self.detect_note.configure(
            text=("no model: the differencer is rebuilt the moment a "
                  "slider moves" if mode == "motion" else
                  "device applies immediately; the model file itself "
                  "needs a restart"))
        self.detect_note.pack(anchor="w", pady=(6, 0))

    def _build_timers(self, left):
        box = self._card(left, "Timers",
                         "written to config.toml, applied while the "
                         "loop runs")
        self.timer_labels = {}
        for section, key, label, lo, hi, step, tip in TIMER_SPECS:
            row = self._row(box, label, tip)
            value_label = ctk.CTkLabel(row, font=self.skin.font(12),
                                       **self.skin.text_style("sub"))
            value_label.grid(row=0, column=2, sticky="e", padx=(6, 0))
            slider = ctk.CTkSlider(row, from_=lo, to=hi,
                                   number_of_steps=int((hi - lo) / step),
                                   width=180,
                                   command=lambda v, s=section, k=key:
                                   self._timer_changed(s, k, v),
                                   **self.skin.slider_style())
            slider.set(self.cfg[section][key])
            slider.grid(row=0, column=1, sticky="e")
            value_label.configure(text="%ss" % self.cfg[section][key])
            self.timer_labels[key] = value_label
        self.worst_label = ctk.CTkLabel(box, font=self.skin.font(11),
                                         wraplength=350, justify="left",
                                         anchor="w",
                                         **self.skin.text_style("sub"))
        self.worst_label.pack(anchor="w", pady=(6, 0))
        self._update_worst()

    # ----------------------------------------------------- camera + preview --
    def _build_camera_card(self, band):
        # beside the settings column (see _build_detection): the
        # window cannot promise the preview height fits, so the page
        # scrolls (unscrollable, the switch was simply born below the
        # clip edge - seen live)
        card = ctk.CTkFrame(band, width=int(self.cfg["ui"]["preview_width"])
                            + 30, **self.skin.panel_style())
        card.pack(anchor="nw", padx=(12, 0))
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(anchor="w", padx=14, pady=(10, 0))
        ctk.CTkLabel(head, text="Camera", font=self.skin.font(15, "bold"),
                     **self.skin.text_style()).pack(side="left")
        self.tips.button(head, TIPS["camera"]).pack(side="left",
                                                    padx=(6, 0))
        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.pack(fill="x", padx=14, pady=(6, 2))
        self.camera_menu = ctk.CTkOptionMenu(
            controls, values=["scanning cameras..."], width=300,
            command=self._camera_changed, **self.skin.menu_style())
        self.camera_menu.pack(side="left")
        ctk.CTkButton(controls, text="rescan", width=80,
                      command=self._scan_cameras,
                      **self.skin.secondary()).pack(side="left", padx=6)
        # the label zone is a 320 px form, not the card's full width:
        # full width flings labels to one edge and menus to the other
        # and the eye has to cross a canyon to read the pair (the
        # screenshot's complaint); 320 keeps every control's right
        # edge on one line, close enough to its label to belong to it
        zone = ctk.CTkFrame(card, width=320, fg_color="transparent")
        zone.pack(anchor="w", padx=14)
        for key, label, tip in (("mode_on", "while screens are on",
                                 TIPS["cam_on"]),
                                ("mode_off", "while screens are off",
                                 TIPS["cam_off"])):
            row = self._row(zone, label, tip)
            menu = ctk.CTkOptionMenu(row, values=["boot per poll",
                                                  "always on"], width=150,
                                     command=self._mode_changed(key),
                                     **self.skin.menu_style())
            menu.grid(row=0, column=1, sticky="e")
            menu.set(self._mode_label(self.cfg["camera"][key]))
        row = self._row(zone, "live preview", TIPS["live"])
        self.live_switch = ctk.CTkSwitch(row, text="", font=self.skin.font(12),
                                         command=self._live_changed,
                                         progress_color=self.skin.accent,
                                         border_color=self.skin.border)
        self.live_switch.grid(row=0, column=1, sticky="e", padx=(0, 4))
        self.power_msg = ""                      # install/uninstall result
        self.power_msg_ts = 0.0
        self.preview_frame = ctk.CTkFrame(card, fg_color=self.skin.field_bg,
                                          corner_radius=self.skin.radius)
        self.preview_frame.pack(anchor="w", pady=(4, 4), padx=14)
        self.preview_label = ctk.CTkLabel(self.preview_frame,
                                          text="no frames yet - flip on "
                                          "live preview",
                                          font=self.skin.font(12),
                                          **self.skin.text_style("sub"))
        self.preview_label.pack()
        self.preview_info = ctk.CTkLabel(card, text="",
                                         font=self.skin.font(10),
                                         wraplength=400, justify="left",
                                         anchor="w",
                                         **self.skin.text_style("sub"))
        self.preview_info.pack(anchor="w", padx=14, pady=(0, 10))

    # ---------------------------------------------------- monitor profiles --
    def _build_profiles(self, page):
        col = ctk.CTkFrame(page, width=640, fg_color="transparent")
        col.pack(side="left", fill="y")
        box = self._card(col, "whole-desktop profiles",
                         "one profile is the desk spelled out: the "
                         "panels by hardware identity, their places, "
                         "modes and rates, HDR, and the windows that "
                         "belong on it. applying re-shapes everything, "
                         "waits until the monitors ANSWER as asked, "
                         "and only then moves the windows")
        row = self._row(box, "profile", TIPS["profile_picker"])
        self._prof_data = profiles.load()
        self._prof_msg = ""
        self._prof_live = {}                    # last live_modes() pass
        self._mode_notes = {}                   # per-row last note (R2)
        self._mode_menus = {}                   # per-row res/rate menus
        self._mode_add_map = {}                 # picker label -> panel id
        self._mode_add = None
        self._pin_edit = _fresh_pin_edit()
        names = [profiles.NEW] + sorted(self._prof_data["profiles"])
        start = profiles.default_name(self._prof_data,
                                      wm.fingerprint()) or profiles.NEW
        self.profile_menu = ctk.CTkOptionMenu(
            row, values=names, width=220, command=self._profile_picked,
            **self.skin.menu_style())
        self.profile_menu.set(start)
        self.profile_menu.grid(row=0, column=1, sticky="e")
        # (rescue lives on the actions bar now - always in reach)
        self._prof_sel = start
        # the anchor is packed ONCE; every render swaps a fresh body
        # into it (see _profiles_render) - the anchor itself is never
        # touched, so the swap cannot disturb anything around the pane
        self._prof_anchor = ctk.CTkFrame(box, fg_color="transparent")
        self._prof_anchor.pack(fill="x", pady=(4, 0))
        self._prof_body = None
        self._profiles_render()

    def _profiles_render(self):
        """Swap a whole freshly built pane in, then callers may repain
        individual sections cheaply (see _section). Rebuilt whole on a
        profile switch because the lists of open windows and live
        monitor states are snapshots - a half-updated mix of old and
        new lines is worse. And the rebuild is DOUBLE BUFFERED: CTk
        constructors call update_idletasks(), so building the pane in
        place painted every half-built stage (the whole-window redraw
        storm on every click, user-reported). Built UNPACKED, those
        intermediate paints hit an invisible frame; the destroy-old
        pack-new swap is one redraw."""
        old = self._prof_body
        self._prof_body = ctk.CTkFrame(self._prof_anchor,
                                       fg_color="transparent")
        self._prof_detail = self._prof_body
        self._psec = {}
        try:
            self._profiles_fill()
        finally:
            if old is not None:
                old.destroy()
            self._prof_body.pack(fill="x")

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

    def _repaint(self, *names):
        """Re-run just the named sections' builders after a handler
        changed only that part of the world."""
        for name in names:
            getattr(self, "_fill_%s" % name)()

    def _profiles_fill(self):
        """The pane's content, built into the (still unpacked) fresh
        body; every self._prof_detail below is that body."""
        prof = self._prof_data["profiles"].get(self._prof_sel)
        if prof is None:                          # the create-new pane
            line = ctk.CTkFrame(self._prof_detail, fg_color="transparent")
            line.pack(fill="x")
            self._prof_name = ctk.CTkEntry(
                line, width=240, font=self.skin.font(12),
                placeholder_text="new profile name",
                fg_color=self.skin.field_bg, border_width=1,
                border_color=self.skin.border,
                corner_radius=self.skin.radius)
            self._prof_name.pack(side="left")
            ctk.CTkButton(line, text="capture this desktop", width=150,
                          command=self._profile_create,
                          **self.skin.secondary()).pack(side="left",
                                                        padx=(6, 0))
            self._prof_status = ctk.CTkLabel(
                self._prof_detail, text=self._prof_msg,
                font=self.skin.font(11), wraplength=560, justify="left",
                anchor="w", **self.skin.text_style("sub"))
            self._prof_status.pack(anchor="w", pady=(6, 0))
            return

        mons = wm.monitors()
        gate = profiles.desk_mismatch(prof, mons)
        # the mode editor: one row per saved panel (resolution +
        # refresh menus), a blank-profile button, and an add-monitor
        # picker (R1-R5). live_modes() is read once inside and handed
        # to every row (R6); every mutation goes through a profiles
        # primitive and repaints the whole pane (R7).
        self._fill_monitors(mons)
        warn = ctk.CTkLabel(
            self._prof_detail,
            text=(gate + " - applying anyway is a gamble, best "
                  "effort below") if gate
            else "this desk matches the profile",
            font=self.skin.font(11), wraplength=560, justify="left",
            anchor="w", **self.skin.text_style("sub"))
        warn.pack(anchor="w", pady=(4, 0))

        opts = ctk.CTkFrame(self._prof_detail, fg_color="transparent")
        opts.pack(fill="x", pady=(2, 0))
        row = self._row(opts, "hdr", TIPS["profile_hdr"])
        self.hdr_menu = ctk.CTkOptionMenu(
            row, values=[HDR_ASK_LABELS[k] for k in HDR_MENU_ORDER],
            width=230, command=self._prof_hdr,
            **self.skin.menu_style())
        self._set_menu(self.hdr_menu,
                       HDR_ASK_LABELS.get(prof.get("hdr", "snap"),
                                          HDR_ASK_LABELS["snap"]))
        self.hdr_menu.grid(row=0, column=1, sticky="e")
        btns = ctk.CTkFrame(self._prof_detail, fg_color="transparent")
        btns.pack(anchor="w", pady=(6, 0))
        ctk.CTkButton(btns, text="apply profile", width=130,
                      command=lambda: self._profile_apply(False),
                      **self.skin.primary()).pack(side="left")
        if gate:
            ctk.CTkButton(btns, text="try anyway (best effort)",
                          width=180,
                          command=lambda: self._profile_apply(True),
                          **self.skin.secondary()).pack(side="left",
                                                        padx=(6, 0))

        # ---- pin an app: pick a window, set conditions, pin it ---------
        # the editor sits directly under the list it edits, and the
        # pinned seats come AFTER it: clicking a seat then loads the
        # editor just above the row clicked. with the seat list on
        # top, an edited pin loaded its editor below the fold, off
        # the bottom of the window (user-reported trap). each block is
        # a SECTION (_fill_live/_fill_editor/_fill_pins/...): the
        # handlers repaint only what their click changed - rebuilding
        # all forty widgets per click was the lag the user felt
        self._fill_live()
        self._fill_editor()
        self._fill_pins()
        self._restore_section(self._prof_detail)
        self._fill_status()

    def _fill_monitors(self, mons):
        """The mode editor (R1-R5): one row per saved panel, each with a
        resolution menu and a refresh menu built from what the LIVE panel
        offers (the saved value is kept when the driver no longer lists
        it, so an offline desk still edits - R1/R2). A blank-profile
        button and an add-monitor picker ride the same bar (R3/R4); every
        row carries its own remove (R5). live_modes() is read EXACTLY ONCE
        here and handed to every row (R6); a mutation goes through a
        profiles primitive and repaints the whole pane (R7); a failure is a
        gray status line, never a dialog (R8). Each row also carries the
        panel's LIVE hdr state note (on/off/no hdr/?) straight from the
        driver - silent {} on ancient Windows means no note, which is
        honest, and the power assistant's UI test watches for it."""
        sec = self._section("monitors", pady=(10, 0))
        prof = self._prof_data["profiles"].get(self._prof_sel)
        if prof is None:                            # the create-new pane
            return
        self._mode_menus = {}        # last render's menus died with
        #                            its old body: start from clean
        live = profiles.live_modes()                # R6: once per pass
        self._prof_live = live
        hdr = {}
        try:
            hdr = {r["gdi"]: ("no hdr" if not r.get("supported")
                              else "hdr on"
                              if r.get("state") == "on"
                              else "hdr off"
                              if r.get("state") == "off"
                              else "hdr ?")
                   for r in wm.hdr_states()}
        except Exception:
            pass
        g_of = {m["id"]: m["gdi"] for m in mons}
        head = ctk.CTkFrame(sec, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text="edit panel modes",
                     font=self.skin.font(13, "bold"),
                     **self.skin.text_style()).pack(side="left")
        for d in prof.get("displays") or []:
            self._mode_row(sec, d, live,
                           hdr.get(g_of.get(d.get("id"), ""), ""))
        if not (prof.get("displays") or []):
            ctk.CTkLabel(sec, text="no panels yet - add one below",
                         font=self.skin.font(11),
                         **self.skin.text_style("sub")).pack(
                             anchor="w", pady=(2, 0))
        bar = ctk.CTkFrame(sec, fg_color="transparent")
        bar.pack(fill="x", pady=(6, 0))
        ctk.CTkButton(bar, text="blank profile", width=130,
                      command=self._prof_blank,
                      **self.skin.secondary()).pack(side="left")
        in_prof = {d.get("id") for d in prof.get("displays") or []}
        avail = [m for m in mons if m.get("id") not in in_prof]
        base = [(m.get("short") or m.get("id")) for m in avail]
        dupes = {b for b in base if base.count(b) > 1}
        add_vals, self._mode_add_map = [], {}
        for m, b in zip(avail, base):
            label = b
            if b in dupes:
                # two panels of one model share a short: append the
                # gdi slot tail so the menu can tell them apart
                label = "%s (%s)" % (
                    b, str(m.get("gdi") or "").rsplit("DISPLAY", 1)
                    [-1] or "?")
            add_vals.append(label)
            self._mode_add_map[label] = m["id"]
        self._mode_add = ctk.CTkOptionMenu(
            bar, values=add_vals or ["(none)"], width=190,
            # CTkOptionMenu fires command(VALUE) - proven from the
            # widget source (ctk_optionmenu:383) - so the bound
            # command MUST accept the arg or a dropdown pick dies
            # TypeError inside the widget, past every try here
            command=lambda v=None: self._prof_add_commit(),
            **self.skin.menu_style())
        self._set_menu(self._mode_add, add_vals[0] if add_vals else "(none)")
        self._mode_add.pack(side="left", padx=(6, 0))
        ctk.CTkButton(bar, text="add", width=48,
                      command=self._prof_add_commit,
                      **self.skin.secondary()).pack(side="left", padx=(4, 0))
        # the R8 status line: a small gray label under the rows that
        # every handler's failure lands in (no dialogs, ever)
        self._mode_status = ctk.CTkLabel(
            sec, text="", font=self.skin.font(11), wraplength=560,
            justify="left", anchor="w", **self.skin.text_style("sub"))
        self._mode_status.pack(anchor="w", pady=(4, 0))

    def _mode_row(self, parent, d, live, hdr_note=""):
        """One editable panel row: short name (plus its LIVE hdr state,
        the driver's truth, silent when unknowable), a resolution menu, a
        refresh menu, a remove. A panel not on the live desk offers only
        its saved values and a gray 'panel not live' hint; a UNVERIFIED
        note from the last edit is painted gray under the row (R2)."""
        mon_id = d.get("id")
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=1)
        ctk.CTkLabel(
            row, anchor="w",
            text="%s%s%s" % (d.get("short") or mon_id,
                             " (primary)" if d.get("primary") else "",
                             "   " + hdr_note if hdr_note else ""),
            font=self.skin.font(11),
            **self.skin.text_style()).pack(side="left")
        try:
            saved_w = int(d.get("w") or 0)
            saved_h = int(d.get("h") or 0)
            saved_rate = int(d.get("rate") or 0)
        except (TypeError, ValueError):
            saved_w = saved_h = saved_rate = 0
        saved_res = "%dx%d" % (saved_w, saved_h)
        live_list = live.get(mon_id) or []
        if live_list:
            res_set = set(m.split("@")[0] for m in live_list)
            res_set.add(saved_res)
            resolutions = sorted(res_set)
            offline = False
        else:                                        # R2: saved only
            resolutions = ([saved_res]
                           if saved_res and saved_res != "0x0"
                           else ["?"])
            offline = True
        res_menu = ctk.CTkOptionMenu(
            row, values=resolutions, width=150,
            command=lambda v, m=mon_id: self._mode_res(m, v),
            **self.skin.menu_style())
        self._set_menu(res_menu, saved_res)
        res_menu.pack(side="left", padx=(6, 0))
        rates = self._rates_for(live_list, saved_res, saved_rate, offline)
        rate_menu = ctk.CTkOptionMenu(
            row, values=[str(r) for r in rates] or ["?"], width=80,
            command=lambda v, m=mon_id: self._mode_rate(m, v),
            **self.skin.menu_style())
        self._set_menu(rate_menu, str(saved_rate) if saved_rate else "?")
        rate_menu.pack(side="left", padx=(4, 0))
        self._mode_menus[mon_id] = (res_menu, rate_menu)
        ctk.CTkButton(row, text="remove", width=66,
                      command=lambda m=mon_id: self._mode_remove(m),
                      **self.skin.secondary()).pack(side="left", padx=(4, 0))
        if offline:
            ctk.CTkLabel(parent, text="panel not live",
                         font=self.skin.font(10),
                         **self.skin.text_style("sub")).pack(
                             anchor="w", padx=92)
        note = self._mode_notes.get(mon_id, "")
        if "UNVERIFIED" in note:
            ctk.CTkLabel(parent, text=note, font=self.skin.font(10),
                         **self.skin.text_style("sub")).pack(
                             anchor="w", padx=92)

    @staticmethod
    def _rates_for(live_list, res_text, saved_rate, offline):
        """The refresh values a panel offers at the chosen resolution,
        plus the saved rate when the driver no longer lists it. An
        offline panel offers only its saved rate (R2)."""
        if offline:
            return [saved_rate] if saved_rate else []
        rset = set()
        for m in live_list:
            if m.split("@")[0] == res_text:
                try:
                    rset.add(int(m.split("@")[1]))
                except (ValueError, IndexError):
                    pass
        if saved_rate:
            rset.add(saved_rate)
        return sorted(rset)

    def _fill_live(self):
        """The pick-list section: every open window, the chosen one
        highlighted. The row buttons are remembered, so selecting a
        window can re-highlight WITHOUT rebuilding the list at all."""
        sec = self._section("live", pady=(10, 0))
        ed = self._pin_edit
        head = ctk.CTkFrame(sec, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text="pin an app - click a window, it "
                                "lands in the editor below",
                     font=self.skin.font(13, "bold"),
                     **self.skin.text_style()).pack(side="left")
        self.tips.button(head, TIPS["profile_match"]).pack(
            side="left", padx=(6, 0))
        lif = ctk.CTkScrollableFrame(sec, width=590,
                                     height=132, fg_color="transparent",
                                     scrollbar_button_color=self.skin.border,
                                     scrollbar_button_hover_color=self.skin.accent)
        lif.pack(fill="x")
        self._live_rows = {}
        live = profiles.windows_now()
        for l in live:
            key = (l["proc"], l["title"])
            picked = ed["pick"] == key
            b = ctk.CTkButton(
                lif, width=540, anchor="w",
                text="%s   %s %dx%d at %d,%d on %s" % (
                    (l["title"] or "(untitled)")[:40],
                    l["proc"][:14], l["rect"][2], l["rect"][3],
                    l["rect"][0], l["rect"][1],
                    l["monitor"] or "?"),
                font=self.skin.font(11),
                command=lambda k=key: self._pin_select(k),
                fg_color=self.skin.accent if picked
                else self.skin.field_bg,
                hover_color=self.skin.accent_hover,
                text_color="#10131a" if picked else self.skin.text,
                corner_radius=self.skin.radius)
            b.pack(anchor="w", pady=1)
            self._live_rows[key] = b
        if not live:
            ctk.CTkLabel(lif, text="no open windows to pick",
                         font=self.skin.font(11),
                         **self.skin.text_style("sub")).pack(
                anchor="w", pady=4, padx=4)

    def _restyle_live(self):
        """the highlight move, without a rebuild: paint exactly the
        rows whose picked-state changed"""
        pick = self._pin_edit["pick"]
        for key, b in getattr(self, "_live_rows", {}).items():
            on = key == pick
            try:
                b.configure(fg_color=self.skin.accent if on
                            else self.skin.field_bg,
                            text_color="#10131a" if on
                            else self.skin.text)
            except Exception:
                pass                    # a destroyed row: harmless

    def _fill_editor(self):
        """The conditions + fine print for the editor's subject, live
        or remembered. The section carries its own 'editing:' title -
        it is what changes when a seat is clicked, and the title is
        the proof the click landed."""
        sec = self._section("editor", pady=(4, 0))
        prof = self._prof_data["profiles"].get(self._prof_sel) \
            or {"wins": []}
        ed = self._pin_edit
        ctk.CTkLabel(sec,
                     text=("editing: %s" % (ed["key"][1] or ed["key"][0])
                           if ed["key"] else "the editor"),
                     font=self.skin.font(13, "bold"),
                     **self.skin.text_style()).pack(anchor="w")
        live = profiles.windows_now()
        picked = next((w for w in live
                       if (w["proc"], w["title"]) == ed["pick"]), None)
        saved_row = next((w for w in prof["wins"]
                          if (w["proc"], w["title"]) == ed["key"]),
                         None) if ed["key"] else None
        row = self._row(sec, "window matching", TIPS["profile_match"])
        self.match_menu = ctk.CTkOptionMenu(
            row, values=list(profiles.MATCH_MODES), width=150,
            command=self._pin_match, **self.skin.menu_style())
        self.match_menu.set(ed["match"])
        self.match_menu.grid(row=0, column=1, sticky="e")
        row = self._row(sec, "open it if missing",
                        TIPS["profile_pin_open"])
        self.pin_open_box = ctk.CTkCheckBox(row, text="",
                                            font=self.skin.font(12),
                                            command=self._pin_open,
                                            checkbox_width=18,
                                            checkbox_height=18,
                                            border_color=self.skin.border,
                                            fg_color=self.skin.accent,
                                            hover_color=self.skin.accent)
        self.pin_open_box.grid(row=0, column=1, sticky="e")
        if ed["open"]:
            self.pin_open_box.select()

        if ed["open"]:
            # the wish's advanced half: how long patience lasts,
            # and WHERE the wish knocks. the captured exe is often
            # the wrong door (store stubs, updater wrappers) and
            # only the human knows which launcher opens the window
            row = self._row(sec, "wait up to",
                            TIPS["profile_pin_wait"])
            self.pin_wait_menu = ctk.CTkOptionMenu(
                row, values=["%d s" % s for s in WAIT_CHOICES],
                width=110, command=self._pin_wait,
                **self.skin.menu_style())
            self.pin_wait_menu.set("%d s" % ed["wait"])
            self.pin_wait_menu.grid(row=0, column=1, sticky="e")
            row = self._row(sec, "launches", TIPS["profile_pin_exe"])
            exf = ctk.CTkFrame(row, fg_color="transparent")
            show = (ed["exe"]
                    or (picked or saved_row or {}).get("exe")
                    or "(no exe captured yet - browse picks one)")
            ctk.CTkLabel(exf,
                         text=show if len(show) <= 44
                         else "..." + show[-41:],
                         font=self.skin.font(10),
                         **self.skin.text_style("sub")).pack(
                side="left")
            ctk.CTkButton(exf, text="browse...", width=80,
                          command=self._pin_browse,
                          **self.skin.secondary()).pack(side="left",
                                                        padx=(6, 0))
            exf.grid(row=0, column=1, sticky="e")

        # the honest fine print, only ever saying something true:
        # which rect the pin saves, that a process pin drags every
        # window of that app, and what "open it" really is
        notes = []
        if picked:
            notes.append("will save: %s %dx%d at %d,%d on %s" % (
                picked["proc"][:14], picked["rect"][2],
                picked["rect"][3], picked["rect"][0],
                picked["rect"][1], picked["monitor"] or "?"))
        elif saved_row:
            notes.append("saved seat: %dx%d at %d,%d on %s (the "
                         "window is closed; move the window and hit "
                         "update pin while it is open to move the "
                         "seat)" % (saved_row["rect"][2],
                                    saved_row["rect"][3],
                                    saved_row["rect"][0],
                                    saved_row["rect"][1],
                                    saved_row.get("monitor") or "?"))
        else:
            notes.append("pick one of the open windows above")
        if (picked or saved_row) and ed["match"] == "process":
            who = (picked or saved_row)["proc"].lower()
            n = sum(1 for l in live if l["proc"].lower() == who)
            if n > 1:
                notes.append("WARNING: %d windows of %s are open - "
                             "this pin moves ALL of them, not just "
                             "the one you picked" % (n, who))
        if (picked or saved_row) and ed["open"]:
            exe = ((ed["exe"] or (picked or {}).get("exe")
                    or (saved_row or {}).get("exe") or "?")
                   ).split("\\")[-1]
            notes.append("will run %s to wake it - a naive exe run; "
                         "store apps and stub launchers may start "
                         "nothing, then it waits %d s and reports"
                         % (exe, ed["wait"]))
        for t in notes:
            ctk.CTkLabel(sec, text=t,
                         font=self.skin.font(10), wraplength=580,
                         justify="left", anchor="w",
                         **self.skin.text_style("sub")).pack(
                anchor="w", pady=(2, 0))
        cbtns = ctk.CTkFrame(sec, fg_color="transparent")
        cbtns.pack(anchor="w", pady=(4, 0))
        ctk.CTkButton(cbtns,
                      text="update pin" if ed["key"] else "pin it",
                      width=130, command=self._pin_commit,
                      **self.skin.primary()).pack(side="left")
        if ed["key"] or ed["pick"]:
            ctk.CTkButton(cbtns, text="cancel", width=80,
                          command=self._pin_cancel,
                          **self.skin.secondary()).pack(side="left",
                                                        padx=(6, 0))

    def _fill_pins(self):
        """The seats this profile owns - below the editor on purpose
        (see the reorder note in _profiles_fill)."""
        sec = self._section("pins", pady=(10, 0))
        prof = self._prof_data["profiles"].get(self._prof_sel) \
            or {"wins": []}
        ctk.CTkLabel(sec, text="pinned apps",
                     font=self.skin.font(13, "bold"),
                     **self.skin.text_style()).pack(side="left")
        self.tips.button(sec, TIPS["profile_pins"]).pack(
            side="left", padx=(6, 0))
        ctk.CTkButton(sec, text="pin every open app", width=150,
                      command=self._prof_pin_all,
                      **self.skin.secondary()).pack(side="left",
                                                    padx=(8, 0))
        ctk.CTkButton(sec, text="re-scan", width=80,
                      command=self._prof_rescan,
                      **self.skin.secondary()).pack(side="left",
                                                    padx=(6, 0))
        pinf = ctk.CTkScrollableFrame(sec, width=590,
                                      height=112, fg_color="transparent",
                                      scrollbar_button_color=self.skin.border,
                                      scrollbar_button_hover_color=self.skin.accent)
        pinf.pack(fill="x")
        live_key = {(w["proc"], w["title"]): w
                    for w in profiles.windows_now()}
        for w in prof["wins"]:
            self._pin_row(pinf, w, live_key.get((w["proc"], w["title"])))
        if not prof["wins"]:
            ctk.CTkLabel(pinf, text="nothing pinned yet - seat an app above",
                         font=self.skin.font(11),
                         **self.skin.text_style("sub")).pack(
                anchor="w", pady=4, padx=4)

    def _fill_status(self):
        sec = self._section("status")
        self._prof_status = ctk.CTkLabel(
            sec, text=self._prof_msg,
            font=self.skin.font(11), wraplength=560, justify="left",
            anchor="w", **self.skin.text_style("sub"))
        self._prof_status.pack(anchor="w", pady=(6, 0))

    def _pin_row(self, parent, w, live):
        """One pinned seat. The row itself is the button that lifts
        the pin back into the editor ('click it and it pops back
        up'), the pencil says the same out loud, the x forgets the
        seat. Badges tell the truth the plain text cannot: closed,
        'open it', a non-default match."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(anchor="w", fill="x", pady=1)
        badges = ""
        if w.get("open"):
            try:
                wt = int(w.get("wait") or 30)
            except (TypeError, ValueError):
                wt = 30
            badges += "  [open it%s]" % (
                "" if wt == 30 else " in %ds" % wt)
            ex = (w.get("exe") or "").split("\\")[-1].lower()
            if ex and ex != (w.get("proc") or "").lower():
                badges += "  [via %s]" % ex[:18]
        if (w.get("match") or "process") != "process":
            badges += "  [%s]" % w.get("match")
        ctk.CTkButton(
            row, width=470, anchor="w",
            text="%s  %s  %dx%d at %d,%d on %s%s%s" % (
                (w["title"] or w["proc"])[:36], w["proc"][:14],
                w["rect"][2], w["rect"][3], w["rect"][0],
                w["rect"][1], w.get("monitor") or "?",
                "" if live else "  (closed)", badges),
            font=self.skin.font(11),
            command=lambda r=w: self._pin_load(r),
            fg_color="transparent", hover_color=self.skin.panel,
            text_color=self.skin.text,
            corner_radius=self.skin.radius).pack(side="left")
        ctk.CTkButton(row, text="edit", width=48,
                      command=lambda r=w: self._pin_load(r),
                      **self.skin.secondary()).pack(side="left",
                                                    padx=(4, 0))
        ctk.CTkButton(row, text="x", width=30,
                      command=lambda r=w: self._pin_remove(r),
                      **self.skin.secondary()).pack(side="left",
                                                    padx=(4, 0))

    # ---- profiles: handlers ---------------------------------------------
    def _profile_picked(self, name):
        self._prof_sel = name
        self._prof_msg = ""
        self._mode_notes = {}                   # stale per-row notes
        self._pin_edit = _fresh_pin_edit()
        self._profiles_render()

    def _profile_create(self):
        name = (self._prof_name.get() or "").strip()
        if not name:
            self._prof_msg = "give it a name first"
            self._prof_status.configure(text=self._prof_msg)
            return
        profiles.create(self._prof_data, name)
        self.profile_menu.configure(values=[profiles.NEW] + sorted(
            self._prof_data["profiles"]))
        self.profile_menu.set(name)
        self._profile_picked(name)

    def _prof_blank(self):
        """R3: a profile that starts empty, auto-named profile-N (the
        next unused). The editor switches to it; nothing is ever asked
        - no dialogs."""
        try:
            taken = set(self._prof_data["profiles"])
            n = 1
            while ("profile-%d" % n) in taken:
                n += 1
            name = "profile-%d" % n
            ok, note = profiles.blank(self._prof_data, name)
            if not ok:
                self._mode_fail(note or "could not create a blank profile")
                return
            self.profile_menu.configure(values=[profiles.NEW] + sorted(
                self._prof_data["profiles"]))
            self._set_menu(self.profile_menu, name)
            self._profile_picked(name)
        except Exception as e:
            self._mode_fail("blank profile: %s" % e)

    def _prof_add_commit(self):
        """R4: pull the picked LIVE panel into the profile; the
        primitive seeds it with the panel's current mode. Resolution is
        by the label->id map _fill_monitors built THIS render, so two
        same-model panels never collide (finding: name scan picked the
        first)."""
        try:
            sel = self._mode_add.get()
            if not sel or sel == "(none)":
                self._mode_fail("pick a panel to add")
                return
            mon_id = (self._mode_add_map or {}).get(sel)
            if mon_id is None:
                self._mode_fail("no such panel on the desk")
                return
            ok, note = profiles.add_display(
                self._prof_data, self._prof_sel, mon_id)
            if not ok:
                self._mode_fail(note or "could not add the panel")
                return
            self._profiles_render()
        except Exception as e:
            self._mode_fail("add panel: %s" % e)

    def _mode_res(self, mon_id, res_text):
        """R1: the resolution changed; keep the saved rate when the new
        panel still offers it there, else the first rate it offers."""
        try:
            w, h = (int(x) for x in res_text.split("x"))
            prof = self._prof_data["profiles"].get(self._prof_sel) or {}
            row = next((d for d in prof.get("displays") or []
                        if d.get("id") == mon_id), None)
            if row is None:
                return
            live_list = (self._prof_live or {}).get(mon_id) or []
            rset = set()
            for m in live_list:
                if m.split("@")[0] == res_text:
                    try:
                        rset.add(int(m.split("@")[1]))
                    except (ValueError, IndexError):
                        pass
            cur = int(row.get("rate") or 0)
            rate = cur if cur in rset else (min(rset) if rset else cur)
            ok, note = profiles.set_display_mode(
                self._prof_data, self._prof_sel, mon_id, w, h, rate)
            self._apply_mode_note(mon_id, note, ok)
            self._profiles_render()
        except Exception as e:
            self._mode_fail("change resolution: %s" % e)

    def _mode_rate(self, mon_id, rate_text):
        """R1: the refresh changed; the resolution is the row's saved
        one. An offline panel saves any rate as UNVERIFIED (no driver
        to check it) - which is exactly what the gray note reports."""
        try:
            rate = int(rate_text)
            prof = self._prof_data["profiles"].get(self._prof_sel) or {}
            row = next((d for d in prof.get("displays") or []
                        if d.get("id") == mon_id), None)
            if row is None:
                return
            ok, note = profiles.set_display_mode(
                self._prof_data, self._prof_sel, mon_id,
                int(row.get("w") or 0), int(row.get("h") or 0), rate)
            self._apply_mode_note(mon_id, note, ok)
            self._profiles_render()
        except Exception as e:
            self._mode_fail("change rate: %s" % e)

    def _mode_remove(self, mon_id):
        """R5: drop one panel; the last row is removable too."""
        try:
            ok, note = profiles.drop_display(
                self._prof_data, self._prof_sel, mon_id)
            if not ok:
                self._mode_fail(note or "could not remove the panel")
                return
            self._mode_notes.pop(mon_id, None)
            self._profiles_render()
        except Exception as e:
            self._mode_fail("remove panel: %s" % e)

    def _apply_mode_note(self, mon_id, note, ok):
        """Remember the last note per row so a UNVERIFIED one is painted
        gray under it on the next repaint (R2); a clean edit clears it,
        and a refusal also lands in the gray status line (R8)."""
        self._mode_notes[mon_id] = note or ""
        if not ok:
            self._mode_fail(note or "the panel refused the mode")

    def _mode_fail(self, msg):
        """R8: a failure is a gray status line, never a dialog, and
        nothing raises into the mainloop."""
        try:
            self._mode_status.configure(text=msg)
        except Exception:
            pass

    def _profile_apply(self, force=False):
        # the reshuffle takes seconds (modes, settle-poll, windows
        # and maybe a 30 s wait for a pinned app to wake), and Tk
        # must not sit frozen through any of it
        name, data = self._prof_sel, self._prof_data
        self._prof_msg = "reshaping the desktop..."
        self._prof_status.configure(text=self._prof_msg)

        def work():
            ok, text, info = profiles.apply(data, name,
                                            best_effort=force)
            log.info("profile '%s' %s: %s", name,
                     "applied" if ok else "refused", text)

            def done():
                self._prof_msg = text
                self._profiles_render()
                misses = (info or {}).get("no_shows") or []
                if misses:
                    self._noshows_ask(misses)
            self.after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def _noshows_ask(self, misses):
        """Loud, but only once: pinned apps that never turned up.
        'I'll fix it' leaves them loud and opens the editor for
        them; 'let it be' marks them quiet and the same failure is
        silent from now on - until one answers a profile again,
        which lifts the quiet automatically."""
        names = "\n".join("  %s" % (m["title"] or m["proc"])[:60]
                          for m in misses)
        dlg = ctk.CTkToplevel(self)
        self.noshows_dialog = dlg
        dlg.title("pinned apps that stayed away")
        dlg.resizable(False, False)
        dlg.configure(fg_color=self.skin.bg)
        dlg.transient(self)
        ctk.CTkLabel(
            dlg, text="these pinned apps did not turn up:\n%s\n\n"
                      "Fix the profile? 'let it be' keeps them "
                      "quiet about future failures." % names,
            font=self.skin.font(12), justify="left",
            **self.skin.text_style()).pack(padx=20, pady=(14, 8))
        line = ctk.CTkFrame(dlg, fg_color="transparent")
        line.pack(pady=(0, 14))

        def fix():
            if len(misses) == 1:
                self._pin_load({"proc": misses[0]["proc"],
                                "title": misses[0]["title"],
                                "rect": [0, 0, 0, 0]})
            dlg.destroy()

        def quiet():
            prof = self._prof_data["profiles"].get(self._prof_sel)
            if prof:
                for m in misses:
                    for w in prof["wins"]:
                        if (w["proc"], w["title"]) == (m["proc"],
                                                       m["title"]):
                            w["quiet"] = True
                profiles.save(self._prof_data)
            dlg.destroy()
        ctk.CTkButton(line, text="I'll fix it", width=110,
                      command=fix, **self.skin.primary()).pack(
            side="left", padx=(0, 6))
        ctk.CTkButton(line, text="let it be", width=110,
                      command=quiet, **self.skin.secondary()).pack(
            side="left")
        dlg.after(30, dlg.focus_force)       # the measured claim:
                                             # Windows steals focus
                                             # back without this

    def _rescue_now(self):
        brought = wm.rescue_lost()
        self._prof_msg = ("brought back: %s" % ", ".join(brought)
                          if brought else "nothing was off screen")
        self._profiles_render()

    def _prof_hdr(self, ask):
        # the menu hands labels; unknown strings pass through raw
        # (a hand-edited profile or a test speaks the engine's
        # tongue directly)
        ask = HDR_BY_LABEL.get(ask, ask)
        self._prof_data["profiles"][self._prof_sel]["hdr"] = ask
        profiles.save(self._prof_data)

    def _prof_rescan(self):
        self._prof_msg = ""
        self._profiles_render()

    def _pin_select(self, key):
        """a click in the open-windows list makes it the editor's
        subject; clicking the same one again lets go of it. the pane
        is NOT rebuilt whole - the highlight moves on the existing
        row buttons and only the editor section repaints"""
        if self._pin_edit["pick"] == key and self._pin_edit["key"] \
                is None:
            self._pin_edit["pick"] = None
        else:
            self._pin_edit.update(key=None, pick=key)
        self._restyle_live()
        self._repaint("editor")

    def _pin_load(self, w):
        """the pinned row clicked: the pin pops back up into the
        editor, conditions as saved, ready to change and update"""
        try:
            wait = max(5, min(600, int(w.get("wait") or 30)))
        except (TypeError, ValueError):
            wait = 30
        self._pin_edit.update(key=(w["proc"], w["title"]),
                              pick=(w["proc"], w["title"]),
                              match=w.get("match")
                              or (self._prof_data["profiles"]
                                  .get(self._prof_sel, {})
                                  .get("match"))
                              or "process",
                              open=bool(w.get("open")),
                              wait=wait, exe=w.get("exe") or None)
        self._restyle_live()
        self._repaint("editor")

    def _pin_remove(self, w):
        profiles.unpin(self._prof_data, self._prof_sel, w["proc"],
                       w["title"])
        if self._pin_edit["key"] == (w["proc"], w["title"]):
            self._pin_edit = _fresh_pin_edit()
        self._prof_msg = "forgot: %s" % (w["title"] or w["proc"])[:60]
        self._repaint("pins", "editor", "status")

    def _pin_match(self, mode):
        self._pin_edit["match"] = mode
        self._repaint("editor")         # the all-windows warning
                                        # hangs off this choice

    def _pin_open(self):
        self._pin_edit["open"] = bool(self.pin_open_box.get())
        self._repaint("editor")         # the naive-exe warning and
                                        # the advanced rows hang off it

    def _pin_wait(self, text):
        try:
            self._pin_edit["wait"] = int(str(text).split()[0])
        except (TypeError, ValueError):
            pass                      # a menu value we did not
                                      # write: keep the current wait
        self._repaint("editor")         # the fine print quotes it

    def _pin_browse(self):
        """What the app cannot guess, the human can: when the
        captured exe starts nothing (store stubs, wrapper launchers)
        the user points the pin at the door that really opens the
        window. The shell runs it exactly as double-click would, so
        a .lnk shortcut is a legal answer too."""
        try:
            from tkinter import filedialog
            got = filedialog.askopenfilename(
                parent=self, title="what should the profile run?",
                filetypes=[("launchers", "*.exe *.bat *.cmd *.lnk"),
                           ("all files", "*.*")],
                defaultextension=".exe")
        except Exception:
            log.warning("browse failed", exc_info=True)
            got = ""
        if got:
            self._pin_edit["exe"] = got
            self._repaint("editor")

    def _pin_cancel(self):
        self._pin_edit = _fresh_pin_edit()
        self._restyle_live()
        self._repaint("editor")

    def _pin_commit(self):
        ed = self._pin_edit
        key = ed["key"] or ed["pick"]
        if key is None:
            self._prof_msg = "pick one of the open windows first"
            self._repaint("status")
            return
        win = next((w for w in profiles.windows_now()
                    if (w["proc"], w["title"]) == key), None)
        if win is None:                # the window closed since the
            win = next((w for w in     # scan: a pin being edited
                self._prof_data["profiles"][self._prof_sel]["wins"]
                if (w["proc"], w["title"]) == key), None)
        if win is None:
            self._prof_msg = "that window is gone - pin something " \
                             "that exists"
            self._pin_cancel()
            self._repaint("status")
            return
        profiles.pin(self._prof_data, self._prof_sel, win,
                     match=ed["match"], open_if_missing=ed["open"],
                     exe=ed["exe"], wait=ed["wait"])
        self._prof_msg = "pinned: %s (seat: where it sits now)" % \
            (key[1] or key[0])[:60]
        self._pin_edit = _fresh_pin_edit()
        self._restyle_live()
        self._repaint("pins", "editor", "status")

    def _prof_pin_all(self):
        # one seat per APP, not per window: a process pin owns every
        # window of its app, so the biggest window of each process
        # gets the seat and its siblings ride along with it
        best = {}
        for w in profiles.windows_now():
            p = (w["proc"] or "").lower()
            if not p:
                continue
            if p not in best or w["rect"][2] * w["rect"][3] > \
                    best[p]["rect"][2] * best[p]["rect"][3]:
                best[p] = w
        for w in best.values():
            profiles.pin(self._prof_data, self._prof_sel, w,
                         match="process")
        self._prof_msg = "pinned one seat per open app (%d)" % \
            len(best)
        self._repaint("pins", "status")

    # --------------------------------------------------------- power plan --
    def _build_power(self, page):
        col = ctk.CTkFrame(page, width=560, fg_color="transparent")
        col.pack(side="left", fill="y")
        box = self._card(col, "override Windows' own timers",
                         "nothing in the power plan changes: the "
                         "timers are only held from firing while the app "
                         "is watching, and they are handed back the "
                         "moment it pauses, snoozes or quits")
        row = self._row(box, "screen power off", TIPS["hold_display"])
        self.hold_display_switch = ctk.CTkSwitch(row, text="",
                                                 font=self.skin.font(12),
                                                 command=self._hold_changed,
                                                 progress_color=self.skin.accent,
                                                 border_color=self.skin.border)
        self.hold_display_switch.grid(row=0, column=1, sticky="e")
        if self.cfg["power"].get("hold_display"):
            self.hold_display_switch.select()
        row = self._row(box, "sleep", TIPS["hold_sleep"])
        self.hold_sleep_switch = ctk.CTkSwitch(row, text="",
                                               font=self.skin.font(12),
                                               command=self._hold_changed,
                                               progress_color=self.skin.accent,
                                               border_color=self.skin.border)
        self.hold_sleep_switch.grid(row=0, column=1, sticky="e")
        if self.cfg["power"].get("hold_sleep"):
            self.hold_sleep_switch.select()

        box = self._card(col, "when the screens wake on their own")
        row = self._row(box, "unexpected wake", TIPS["wake"])
        self.policy_menu = ctk.CTkOptionMenu(
            row, values=["re-off after wake", "leave on after wake"],
            width=180, command=self._policy_changed,
            **self.skin.menu_style())
        self.policy_menu.grid(row=0, column=1, sticky="e")
        self.policy_menu.set(
            "re-off after wake"
            if self.cfg["recovery"]["wake_policy"] == "re_off"
            else "leave on after wake")
        row = self._row(box, "hold off while a fullscreen app owns "
                        "the display", TIPS["fullscreen"])
        self.fullscreen_switch = ctk.CTkSwitch(row, text="",
                                               font=self.skin.font(12),
                                               command=self._fullscreen_changed,
                                               progress_color=self.skin.accent,
                                               border_color=self.skin.border)
        self.fullscreen_switch.grid(row=0, column=1, sticky="e")
        if self.cfg["guards"]["fullscreen"]:
            self.fullscreen_switch.select()
        row = self._row(box, "auto re-off", TIPS["reoff"])
        self.reoff_label = ctk.CTkLabel(row, text="on",
                                        font=self.skin.font(12),
                                        **self.skin.text_style("sub"))
        self.reoff_label.grid(row=0, column=1, sticky="e")
        self.reoff_button = ctk.CTkButton(
            row, text="resume now", width=110,
            command=lambda: self.monitor.events.put(("reoff", False)),
            **self.skin.secondary())
        self.reoff_button.grid(row=0, column=2, sticky="e", padx=(6, 0))
        row = self._row(box, "put window positions back after wake",
                        TIPS["restore_windows"])
        self.restore_switch = ctk.CTkSwitch(row, text="",
                                            font=self.skin.font(12),
                                            command=self._restore_changed,
                                            progress_color=self.skin.accent,
                                            border_color=self.skin.border)
        self.restore_switch.grid(row=0, column=1, sticky="e")
        if self.cfg["power"].get("restore_windows"):
            self.restore_switch.select()

        # the UAC shield before the assistant label is the honest hint
        # that ticking it means one admin confirm (drawn to match the
        # system icon: quartered blue/amber, silver cross, ui.shield)
        box = self._card(col, "powercfg assistant")
        prow = ctk.CTkFrame(box, fg_color="transparent")
        prow.pack(anchor="w")
        self._shield_img = ctk.CTkImage(
            light_image=shield_pil(16), dark_image=shield_pil(16),
            size=(16, 16))
        ctk.CTkLabel(prow, text="", image=self._shield_img,
                     fg_color="transparent", width=22).pack(side="left")
        self.power_switch = ctk.CTkSwitch(
            prow, text="wait out other display locks",
            font=self.skin.font(12), command=self._power_assistant_changed,
            progress_color=self.skin.accent,
            border_color=self.skin.border)
        self.power_switch.pack(side="left")
        self.tips.button(prow, TIPS["assistant"]).pack(side="left",
                                                        padx=(6, 0))
        if self.cfg["power"]["assistant_task"]:
            self.power_switch.select()
        # the blockers report: the red lines are the apps that actually
        # hold the display (they pause the camera); everything else is
        # news. Scrollable: a crowded report never overflows the card.
        self.blockers_box = ctk.CTkTextbox(
            box, height=132, width=500, font=self.skin.font(10),
            fg_color=self.skin.field_bg, border_color=self.skin.border,
            border_width=1, corner_radius=self.skin.radius, wrap="word")
        self.blockers_box.pack(anchor="w", pady=(6, 0))
        # NOT state="disabled": that repaints every tag the same flat
        # color (measured - the red vanished). It stays enabled so the
        # tag colors live, and reads as a report by swallowing edits
        for seq in ("<Key>", "<<Paste>>", "<<Cut>>", "<<Undo>>",
                    "<Control-v>", "<Control-V>", "<Control-x>",
                    "<Control-X>", "<Control-z>", "<Control-Z>"):
            self.blockers_box.bind(seq, lambda event: "break")
        # the truth check: the switch must show REALITY (the task
        # store), not the config rumor - the task can outlive or
        # predate the flag, and /Query costs ~2 s here, so it asks in
        # the background; the answer may land while an install is mid-
        # flight (delete then create), so a first "gone" is doubted and
        # re-asked before believed
        def truth():
            from .. import power
            real = power.task_installed()
            for _ in range(3):
                if real:
                    break
                time.sleep(2)
                real = power.task_installed()
            log.info("assistant truth: task store says %s", real)
            # NOT self.after(0, ...): this thread can beat app.mainloop
            # (measured: schtasks answered while the constructor still
            # ran) and tkinter then raises "main thread is not in main
            # loop" - pythonw ate the traceback, the answer evaporated,
            # and the switch drifted from reality forever. The queue is
            # thread-safe whenever; _tick_ui drains it on the main
            # thread once the loop exists.
            self.ui_events.put(("assistant_truth", real))
        threading.Thread(target=truth, daemon=True).start()
        # the overrides manager exists only while the assistant does:
        # its entire data source is the assistant's dump, so the button
        # joins and leaves with the switch, never lies about data
        self.assistant_box = box
        self.overrides_button = ctk.CTkButton(
            box, text="manage powercfg overrides", width=250,
            command=self._show_overrides, **self.skin.secondary())
        self._assistant_ui(bool(self.cfg["power"]["assistant_task"]))
        row = self._row(col, "turn HDR off while away (OLED panels)",
                        TIPS["hdr_away"])
        self.hdr_away_switch = ctk.CTkSwitch(row, text="",
                                             font=self.skin.font(12),
                                             command=self._hdr_away_changed,
                                             progress_color=self.skin.accent,
                                             border_color=self.skin.border)
        self.hdr_away_switch.grid(row=0, column=1, sticky="e")
        if bool(self.cfg["power"].get("hdr_off_when_away")):
            self.hdr_away_switch.select()
        self._gaming_section(col)
        self._dvr_section(col)

    def _gaming_section(self, col):
        """The refresh-rate watcher's face: it joins the power-plan
        tab (a fifth tab was refused on measured repaint cost) and
        reads its facts off the same cfg the watcher re-reads every
        tick, so writing cfg["gaming"] IS applying it. The rate menus
        offer only what the panel's driver already lists
        (wm.offered_modes - the same list wanted_hz trades from), so
        the UI can never ask for a mode the panel will not take."""
        g = self.cfg.get("gaming") or {}
        box = self._card(col, "gaming refresh rates",
                         "a fullscreen game takes its panel's top "
                         "rate; the desktop gets its own back when "
                         "the game leaves. only the rate is traded - "
                         "the resolution is never touched")
        row = self._row(box, "watch games and trade rates",
                        TIPS["gaming"])
        self.gaming_switch = ctk.CTkSwitch(row, text="",
                                           font=self.skin.font(12),
                                           command=self._gaming_changed,
                                           progress_color=self.skin.accent,
                                           border_color=self.skin.border)
        self.gaming_switch.grid(row=0, column=1, sticky="e")
        if g.get("enabled"):
            self.gaming_switch.select()
        # one row per live panel: the game rate first, the rate the
        # desktop gets back second - both only among the rates that
        # panel's driver offers
        self.gaming_menus = {}
        for m in wm.monitors():
            hz = self._offered_hz(m)
            if not hz:
                continue          # the driver said nothing: nothing
                                  # to offer this panel
            row = self._row(box, "%s - game rate" % m["short"],
                            TIPS["gaming_rates"])
            # 'VRR (pin max)' is not a rate: it declares the panel's
            # scanout belongs to the driver's variable rate, so the
            # watcher never flips it (and pins it at its max outside
            # games). The card's first entry stays 'auto' - the game
            # menu has no 'keep' (that is the desktop menu's word)
            game_vals = ["auto", "VRR (pin max)"] + [str(v) for v in hz]
            game_menu = ctk.CTkOptionMenu(
                row, values=game_vals, width=120,
                command=lambda v, s=m["short"]:
                self._gaming_game_hz(s, v),
                **self.skin.menu_style())
            stored = (g.get("game_hz") or {}).get(m["short"])
            # a stored 'vrr' shows as its menu label; anything else
            # shows its own string, falling back to the default the
            # same way the desktop menu does
            shown = ("VRR (pin max)"
                     if str(stored).strip().lower() == "vrr"
                     else str(stored))
            game_menu.set(shown if stored is not None
                          and shown in game_vals[1:] else "auto")
            game_menu.grid(row=0, column=1, sticky="e")
            row = self._row(box, "%s - desktop rate" % m["short"],
                            TIPS["gaming_rates"])
            # 'keep' is not a rate, it is the ABSENCE of a rule - the
            # menu must show that truth, not a fake '60' that config
            # never agreed to (this exact lie is why the feature
            # looked broken: menus showed 60, cfg said {}, nothing was
            # configured, the watcher correctly held nothing)
            desk_vals = ["keep"] + [str(v) for v in hz]
            desk_menu = ctk.CTkOptionMenu(
                row, values=desk_vals, width=100,
                command=lambda v, s=m["short"]:
                self._gaming_desk_hz(s, v),
                **self.skin.menu_style())
            stored = (g.get("desktop_hz") or {}).get(m["short"])
            desk_menu.set(str(stored) if stored is not None
                          and str(stored) in desk_vals[1:] else "keep")
            desk_menu.grid(row=0, column=1, sticky="e")
            self.gaming_menus[m["short"]] = (game_menu, desk_menu)
        # the two exe lists: one name per line, and the lines ARE the
        # list - the commit on focus-out is the save
        row = self._row(box, "games (one exe per line)",
                        TIPS["gaming_games"])
        self.games_box = ctk.CTkTextbox(
            row, height=84, width=230, font=self.skin.font(11),
            fg_color=self.skin.field_bg, border_color=self.skin.border,
            border_width=1, corner_radius=self.skin.radius, wrap="word")
        self.games_box.grid(row=0, column=1, sticky="e")
        self.games_box.insert("1.0", "\n".join(g.get("games") or []))
        self.games_box.bind("<<FocusOut>>", self._gaming_games_commit)
        # foreground() can block for seconds (anti-cheat pids), so the
        # button only starts the probe: the answer comes back on the
        # main thread, and a miss just leaves the list alone
        self.add_fg_button = ctk.CTkButton(
            row, text="add what's in front of me", width=170,
            command=self._gaming_add_foreground, **self.skin.secondary())
        self.add_fg_button.grid(row=0, column=2, sticky="e", padx=(6, 0))
        row = self._row(box, "never games (one exe per line)",
                        TIPS["gaming_ignore"])
        self.ignore_box = ctk.CTkTextbox(
            row, height=60, width=230, font=self.skin.font(11),
            fg_color=self.skin.field_bg, border_color=self.skin.border,
            border_width=1, corner_radius=self.skin.radius, wrap="word")
        self.ignore_box.grid(row=0, column=1, sticky="e")
        self.ignore_box.insert("1.0", "\n".join(g.get("ignore") or []))
        self.ignore_box.bind("<<FocusOut>>", self._gaming_ignore_commit)
        # the plan a game earns: a name fragment or a guid; '' leaves
        # the plan alone entirely
        row = self._row(box, "power plan while gaming",
                        TIPS["gaming_plan"])
        self.plan_entry = ctk.CTkEntry(
            row, width=180, font=self.skin.font(12),
            placeholder_text="fragment or guid ('' = never)",
            fg_color=self.skin.field_bg, border_width=1,
            border_color=self.skin.border,
            corner_radius=self.skin.radius)
        self.plan_entry.insert(0, g.get("power_plan") or "")
        self.plan_entry.grid(row=0, column=1, sticky="e")
        self.plan_entry.bind("<<FocusOut>>", self._gaming_plan_commit)

    def _dvr_section(self, col):
        """The Game DVR card: one switch per registry tweak the
        gaming pack can promise (docs/apack-findings.md). The
        registry is the truth - a Settings page may rewrite the
        values at any time - so the switches read their state
        from the registry at render and hand it back after
        every click, and a failed write is reported in the
        status line instead of a dialog."""
        from .. import tweaks
        box = self._card(col, "Game DVR", TIPS["dvr"])
        self.dvr_switches = {}
        for tid, (label, _path, _name, _data, _timing) in tweaks.TOGGLES.items():
            row = self._row(box, label)
            sw = ctk.CTkSwitch(row, text="",
                               font=self.skin.font(12),
                               progress_color=self.skin.accent,
                               border_color=self.skin.border)
            # bind BOTH via defaults, after sw exists: binding
            # only tid left every lambda painting the LAST switch
            # from registry truth (the classic late-binding trap -
            # the clicked switch kept its raw state, repaint lied)
            sw.configure(command=lambda t=tid, s=sw:
                         self._dvr_toggle(t, s))
            sw.grid(row=0, column=1, sticky="e")
            if tweaks.is_on(tid):
                sw.select()
            self.dvr_switches[tid] = sw
        self.dvr_status = ctk.CTkLabel(
            box, text="", font=self.skin.font(11),
            **self.skin.text_style("sub"))
        self.dvr_status.pack(anchor="w")

    def _dvr_toggle(self, tid, sw):
        """The registry decides, not the click: apply when off,
        revert when on, then repaint the switch from the
        registry again (the user's click may have lost to a
        Settings page) and surface the error in the status
        line - no dialogs."""
        from .. import tweaks
        if tweaks.is_on(tid):
            ok, err = tweaks.revert(tid)
        else:
            ok, err = tweaks.apply(tid)
        if tweaks.is_on(tid):
            sw.select()
        else:
            sw.deselect()
        self.dvr_status.configure(text="" if ok else err)

    @staticmethod
    def _offered_hz(m):
        """A panel's rates as ascending ints, parsed from the driver's
        'WxH@Hz' list (the very list the watcher trades from); empty
        when the driver answers nothing."""
        out = set()
        for name in wm.offered_modes(m["gdi"]):
            try:
                out.add(int(name.rsplit("@", 1)[1]))
            except (IndexError, ValueError):
                continue
        return sorted(out)

    # -------------------------------------------------------------- general --
    def _build_general(self, page):
        from .. import startup
        col = ctk.CTkFrame(page, width=460, fg_color="transparent")
        col.pack(side="left", fill="y")
        box = self._card(col, "General")
        row = self._row(box, "skin", TIPS["skin"])
        self.skin_menu = ctk.CTkOptionMenu(
            row, values=[s.label for s in theme.SKINS.values()],
            width=140, command=self._skin_changed,
            **self.skin.menu_style())
        self.skin_menu.grid(row=0, column=1, sticky="e")
        self.skin_menu.set(self.skin.label)
        row = self._row(box, "start minimized to tray", TIPS["min"])
        self.min_switch = ctk.CTkSwitch(row, text="",
                                        font=self.skin.font(12),
                                        command=self._start_min_changed,
                                        progress_color=self.skin.accent,
                                        border_color=self.skin.border)
        self.min_switch.grid(row=0, column=1, sticky="e")
        if self.cfg["ui"].get("start_minimized"):
            self.min_switch.select()
        # the updater lives here because it is meta: it replaces the
        # app, not anything the app watches. the frozen exe has no
        # repo to pull, so the row hides itself there.
        row = self._row(box, "check for updates", TIPS["update"])
        self.update_row = row
        self.update_button = ctk.CTkButton(
            row, text="update now", width=110, command=self._update_now,
            **self.skin.secondary())
        self.update_button.grid(row=0, column=1, sticky="e")
        if getattr(sys, "frozen", False):
            row.pack_forget()
        row = self._row(box, "open log folder", TIPS["logs"])
        ctk.CTkButton(row, text="open", width=110, command=self._open_log,
                      **self.skin.secondary()).grid(row=0, column=1,
                                                    sticky="e")
        # the switch mirrors the HKCU Run key, not a config rumor: a
        # stale entry from a deleted folder lights it up honest, and
        # the note spells out where the entry actually points (move the
        # app folder and the old entry keeps firing at logon; one flip
        # off and on re-points it here)
        row = self._row(box, "start with Windows", TIPS["startup"])
        self.startup_switch = ctk.CTkSwitch(row, text="",
                                            font=self.skin.font(12),
                                            command=self._startup_changed,
                                            progress_color=self.skin.accent,
                                            border_color=self.skin.border)
        self.startup_switch.grid(row=0, column=1, sticky="e")
        self.startup_note = ctk.CTkLabel(box, text="",
                                         font=self.skin.font(11),
                                         wraplength=420, justify="left",
                                         anchor="w",
                                         **self.skin.text_style("sub"))
        self.startup_note.pack(anchor="w")
        self._startup_sync(startup.enabled())

    # ------------------------------------------------------------- helpers --
    @staticmethod
    def _set_menu(menu, value):
        try:
            menu.set(value)
        except Exception:
            pass                            # values not populated yet

    @staticmethod
    def _mode_label(stored):
        return "boot per poll" if stored == "boot_per_poll" else "always on"

    @staticmethod
    def _mode_value(shown):
        return "boot_per_poll" if shown == "boot per poll" else "always_on"

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

    def _device_changed(self, label):
        name = DEVICE_BY_LABEL[label]
        self.cfg["inference"]["device"] = name
        self.monitor.events.put(("device", name))
        self._save()

    def _gpu_changed(self, label):
        gid = int(str(label).split(" ")[0])
        self.cfg["inference"]["device_id"] = gid
        self.monitor.events.put(("device_id", gid))
        self._save()

    def _confidence_changed(self, value):
        self.cfg["inference"]["confidence"] = round(float(value), 2)
        self.conf_label.configure(text="%.2f" % value)
        self.monitor.events.put(("confidence", round(float(value), 2)))
        self._save()

    def _motion_changed(self, key, value):
        value = float(value)
        self.cfg["detection"][key] = (int(value) if key == "diff_level"
                                       else value)
        fmt = {"ratio": "%.4f", "diff_level": "%d", "hold_sec": "%.0f s"}
        self.motion_labels[key].configure(text=fmt[key] % value)
        # the differencer reads its numbers once, at build; refiring
        # the mode event rebuilds it around whatever the sliders hold
        # now (no model to load in this mode, so it stays cheap)
        self.monitor.events.put(("detection_mode", "motion"))
        self._save()

    def _min_hits_changed(self, value):
        if value:
            self.cfg["inference"]["min_hits"] = int(value)
            self._save()

    @staticmethod
    def _detect_mode_label(cfg):
        return ("motion (no AI)"
                if (cfg.get("detection") or {}).get("mode") == "motion"
                else "person (AI)")

    def _detect_mode_changed(self, label):
        mode = "motion" if str(label).startswith("motion") else "person"
        # the tray and the monitor read THIS dict; the event rebuilds
        # the detector through the factory (motion: no onnx touched)
        self.cfg["detection"]["mode"] = mode
        self.monitor.events.put(("detection_mode", mode))
        self._show_mode_rows()
        self._save()

    def _timer_changed(self, section, key, value):
        self.cfg[section][key] = int(round(value))
        # monitor.timers / monitor.recovery are these very dicts:
        # writing is applying
        self.timer_labels[key].configure(text="%ss" % round(value))
        self._update_worst()
        self._save()

    def _update_worst(self):
        timers = self.cfg["timers"]
        worst = timers["idle_gate_sec"] + timers["absent_confirm_sec"]
        self.worst_label.configure(
            text="worst case: dark %.0f s after the last keystroke" % worst)

    def _policy_changed(self, label):
        name = "re_off" if label.startswith("re-off") else "leave_on"
        self.cfg["recovery"]["wake_policy"] = name
        self.monitor.events.put(("wake_policy", name))
        self._save()

    def _fullscreen_changed(self):
        self.cfg["guards"]["fullscreen"] = bool(self.fullscreen_switch.get())
        self._save()

    def _hold_changed(self):
        # cfg["power"] IS monitor.power_cfg, and the loop re-asserts
        # the execution state every tick: both switches are live within
        # 0.2 s, each on its own
        self.cfg["power"]["hold_display"] = bool(
            self.hold_display_switch.get())
        self.cfg["power"]["hold_sleep"] = bool(
            self.hold_sleep_switch.get())
        self._save()

    def _restore_changed(self):
        # cfg["power"] IS monitor.power_cfg: the snapshot/restore hooks
        # read restore_windows fresh at every off/wake edge
        self.cfg["power"]["restore_windows"] = bool(
            self.restore_switch.get())
        self._save()

    def _hdr_away_changed(self):
        self.cfg["power"]["hdr_off_when_away"] = bool(
            self.hdr_away_switch.get())
        self._save()

    # ------------------------------------------------------------ gaming ---
    def _gaming_changed(self):
        # cfg["gaming"] IS the watcher's gcfg: the loop re-reads it
        # every tick, so writing is applying
        self.cfg["gaming"]["enabled"] = bool(self.gaming_switch.get())
        self._save()

    def _gaming_game_hz(self, short, label):
        if label == "VRR (pin max)":
            self.cfg["gaming"]["game_hz"][short] = "vrr"
        elif label == "auto" and (
                self.cfg["gaming"]["game_hz"].get(short) == "vrr"):
            # back to the default = the vrr rule comes off: pop the
            # rule, the same pattern the desktop keep uses ('auto'
            # and an unset entry answer the same, the panel's
            # fastest)
            self.cfg["gaming"]["game_hz"].pop(short, None)
        else:
            self.cfg["gaming"]["game_hz"][short] = (
                "auto" if label == "auto" else int(label))
        self._save()

    def _gaming_desk_hz(self, short, label):
        # 'keep' = delete the rule, not store a string: the watcher
        # must treat this panel as nobody's business again. int('keep')
        # would raise INSIDE the widget callback - silently, in
        # pythonw - and the pick would evaporate before _save().
        if label == "keep":
            self.cfg["gaming"]["desktop_hz"].pop(short, None)
        else:
            self.cfg["gaming"]["desktop_hz"][short] = int(label)
        self._save()

    def _gaming_games_commit(self, event=None):
        self._gaming_list_commit("games", self.games_box)

    def _gaming_ignore_commit(self, event=None):
        self._gaming_list_commit("ignore", self.ignore_box)

    def _gaming_list_commit(self, key, box):
        """Focus left a list box: the lines (blanks dropped) are the
        list now."""
        lines = [line.strip() for line in box.get("1.0", "end")
                 .splitlines()]
        self.cfg["gaming"][key] = [line for line in lines if line]
        self._save()

    def _gaming_fill_list(self, key):
        box = self.games_box if key == "games" else self.ignore_box
        box.delete("1.0", "end")
        box.insert("1.0", "\n".join(self.cfg["gaming"].get(key) or []))

    def _gaming_plan_commit(self, event=None):
        self.cfg["gaming"]["power_plan"] = (self.plan_entry.get()
                                            or "").strip()
        self._save()

    def _gaming_add_foreground(self):
        """wm.foreground() can block for seconds (anti-cheat pids), so
        it runs on a daemon thread and hands the answer back through
        the main thread. Fail open: a miss just leaves the list
        alone - the desk is never told what it cannot know."""
        def work():
            try:
                fg = wm.foreground()
            except Exception:
                log.exception("gaming: the foreground probe died")
                return
            if not fg or not fg.get("proc"):
                return

            def done():
                proc = fg["proc"]
                games = self.cfg["gaming"].setdefault("games", [])
                if proc in games:
                    return
                games.append(proc)
                self._gaming_fill_list("games")
                self._save()
            try:
                self.after(0, done)
            except Exception:
                pass            # the window closed while the probe ran

        threading.Thread(target=work, daemon=True).start()

    def _skin_changed(self, label):
        for skin in theme.SKINS.values():
            if skin.label == label:
                self.cfg["ui"]["skin"] = skin.key
                break
        self._save()
        self.rebuild_for_skin()

    def _start_min_changed(self):
        # read once at boot (the tip says so): no live effect possible
        # on a window that is, at this moment, open
        self.cfg["ui"]["start_minimized"] = bool(self.min_switch.get())
        self._save()

    def _mode_changed(self, key):
        def command(label):
            self.cfg["camera"][key] = self._mode_value(label)
            self._save()
        return command

    def _camera_changed(self, shown):
        from .. import camera
        if shown == self.IR_INSTALL:
            self._apply_cameras(self._cams)   # undo the menu choice -
            self._dep_prompt(switch=True)     # picking the invitation
            return                            # is not picking a camera
        for entry in (self._cams or []):
            if shown.startswith("index %s " % entry[0]):
                self.cfg["camera"]["index"] = entry[0]
                self.monitor.events.put(("camera", entry[0]))
                self._save()
                return
        if shown.startswith("index %s" % camera.HELLO_IR):
            # "index -2 hello IR <group>": the bridge lives, the wish
            # is recorded, the state machine swaps the camera
            self.cfg["camera"]["index"] = camera.HELLO_IR
            self.monitor.events.put(("camera", camera.HELLO_IR))
            self._save()

    def _live_changed(self):
        on = bool(self.live_switch.get())
        self.monitor.events.put(("preview", 1.5 if on else 0))

    def _pause_toggle(self):
        self.monitor.events.put(("pause", not self.monitor.paused))

    def _quit(self):
        self.monitor.events.put(("quit", True))

    def _open_log(self):
        try:
            os.startfile(config.LOG_DIR)
        except Exception:
            os.system('start "" "%s"' % config.LOG_DIR)

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

    @staticmethod
    def update_script():
        """update.bat, beside the package - or None. The frozen exe
        carries no repo and no script, so it has nothing to run."""
        if getattr(sys, "frozen", False):
            return None
        root = os.path.dirname(os.path.dirname(
            os.path.abspath(config.__file__)))
        script = os.path.join(root, "update.bat")
        return script if os.path.exists(script) else None

    def _update_now(self, extra=()):
        """The update replaces the very files THIS app runs from, so
        the courtesies are in order: hand the job (plus the relaunch
        promise) to cmd, quit, let the script work on quiet files.
        cmd.exe must be the one to run the .bat - CreateProcess
        cannot exec a batch file directly; the app has no console of
        its own, so the script's console opens fresh, visible, and
        outlives us (it must, it carries the relaunch). extra carries
        the updater's other flags - ("deps",) when a feature is
        waiting on an optional package."""
        script = self.update_script()
        if not script:
            return
        self._save_now()                     # the debounced save may
                                             # never fire again - the
                                             # script reads the FILE
        try:
            subprocess.Popen(["cmd.exe", "/c", script] + list(extra)
                             + ["relaunch"], cwd=os.path.dirname(script))
        except Exception:
            log.exception("update refused to start; the app stays up")
            return
        self.monitor.events.put(("quit", True))

    def _dep_prompt(self, switch):
        """One prompt per missing package on screen at a time (a
        re-open just lifts the old one). switch=True when the user was
        picking the hello IR entry - installing then also SELECTS the
        camera, because that is what the click meant."""
        win = getattr(self, "_dep_win", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win._claim_focus()
                    return win
            except Exception:
                pass
        self._dep_win = deps.Deprompt(
            self, self.skin, "hello IR", "whircam",
            "The infrared-camera bridge is an optional package (MIT, "
            "a few hundred kB). The updater installs it and reopens "
            "the app a moment later; the desk is unsupervised only "
            "for that moment, and nothing in the timers or the power "
            "plan changes.",
            lambda: self._dep_install(switch))
        return self._dep_win

    def _dep_install(self, switch):
        from .. import camera
        if switch:
            self.cfg["camera"]["index"] = camera.HELLO_IR
            # no camera event: this process is about to quit, and the
            # one the updater reopens boots straight into hello IR
        self._update_now(extra=("deps",))

    # -------------------------------------------------------- power assistant --
    def _assistant_truth(self, real):
        """Adopt the task store's answer as the switch state and tell
        the monitor, so config, UI and reality cannot disagree."""
        try:
            was = bool(self.power_switch.get())
            log.info("assistant adoption: switch says %s, store says %s",
                     was, real)
            if was != real:
                self.power_switch.set(real)          # set() is click-free
                self.cfg["power"]["assistant_task"] = real
                self.monitor.events.put(("power_assistant", real))
                self._save()                         # the file learned the
                # truth too, or a test that scribbled assistant_task=false
                # over it keeps whispering lies to every future instance
                # until some unrelated widget change happens to save it
        except Exception:
            log.exception("assistant adoption crashed")  # pythonw has no
            # stderr: without this the whole thread's answer evaporated
            # silently, which is exactly how "does not persist" was born
        self._assistant_ui(real)

    def _assistant_ui(self, on):
        """Everything that lives and dies with the assistant switch."""
        try:
            if on:
                if not self.overrides_button.winfo_manager():
                    self.overrides_button.pack(anchor="w", pady=(6, 0))
            else:
                self.overrides_button.pack_forget()
        except Exception:
            pass                        # still building, or already gone

    def _show_overrides(self):
        """One manager window; opening it again just lifts the old one."""
        win = getattr(self, "_overrides_win", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win._claim_focus()          # the trick that works,
                    return win                    # not a bare lift
            except Exception:
                pass
        from . import overrides
        self._overrides_win = overrides.OverridesWindow(
            self.cfg, self.monitor, self.skin, parent=self)
        return self._overrides_win

    def _power_assistant_changed(self):
        """Tick ON registers the task (one UAC confirm, which can flash
        up behind this borderless window); tick OFF deletes it. Both
        paid on a worker thread so the window stays alive."""
        want = bool(self.power_switch.get())
        self.power_msg = ("waiting for the admin confirm - check the "
                          "taskbar if no prompt is visible"
                          if want else "removing the scheduled task...")
        self.power_msg_ts = time.time()

        def work():
            from .. import power
            ok, msg = power.install() if want else power.uninstall()
            self.cfg["power"]["assistant_task"] = bool(ok and want)
            self.monitor.events.put(("power_assistant", bool(ok and want)))
            self.ui_events.put(("assistant_ui", bool(ok and want)))
            if not ok:
                self.power_msg = msg
                self.power_msg_ts = time.time()
                self.after(0, lambda: self.power_switch.set(not want))
            else:
                # the waiting line must die on success too, or the user
                # never learns the truth until its expiry timer ends it
                self.power_msg = ""
                self.power_msg_ts = 0.0
                try:    # read through the assistant just created (or
                        # honestly say admin after deleting), instead of
                        # letting last week's error string linger
                    self.monitor.blockers = power.requests(
                        self.cfg["power"]["ignore"],
                        assistant=bool(ok and want))
                except Exception:
                    pass
                self.after(0, self._update_blockers)
        threading.Thread(target=work, daemon=True).start()

    # -------------------------------------------------------------- startup --
    def _startup_sync(self, stored):
        """Checkbox + note from the registry's answer (None | string)."""
        from .. import startup
        self.startup_switch.select() if stored else \
            self.startup_switch.deselect()
        if not stored:
            text = ""
        elif stored == startup.command():
            text = ("registered for this copy (see Task Manager's "
                    "startup apps)")
        else:
            text = ("entry points elsewhere: %s - flip off and on to "
                    "re-point here" % textwrap.shorten(stored, width=46))
        self.startup_note.configure(text=text)

    def _startup_changed(self):
        """The write verifies itself by re-read; the switch always ends
        on what the registry says, never on hope. Registry I/O is fast,
        but a locked-down hive can block on policy - the worker keeps
        even that worst case off the UI thread."""
        from .. import startup
        want = bool(self.startup_switch.get())

        def work():
            ok, msg = (startup.enable() if want else startup.disable())
            stored = startup.enabled()
            self.after(0, lambda: self._startup_done(ok, msg, stored))
        threading.Thread(target=work, daemon=True).start()

    def _startup_done(self, ok, msg, stored):
        if not ok:
            self.startup_note.configure(text=msg)     # the failure needs
            self.startup_switch.set(1 if stored else 0)   # to introduce
            return                                      # itself
        self._startup_sync(stored)

    # ------------------------------------------------- restore at start --
    @staticmethod
    def _pair_label(pairs, value):
        return dict(pairs).get(value, pairs[0][1])

    def _restore_section(self, parent):
        """The pre-armed lever, living ON the profiles tab with the
        profiles it arms (it hid under General; the user hunted for it
        here). Rebuilt with the pane, so the picker always knows about
        profiles captured since the window opened. Which COPY is the
        logon one is not inferred (the shell gives no clue) - the Run
        entry installed by the startup row stamps --autostart on
        itself, and cli reads that stamp as proof."""
        rst = self.cfg.setdefault("restore", {})
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(head, text="restore a profile at start",
                     font=self.skin.font(13, "bold"),
                     **self.skin.text_style()).pack(side="left")
        self.tips.button(head, TIPS["restore_on"]).pack(
            side="left", padx=(6, 0))
        row = self._row(parent, "armed", TIPS["restore_on"])
        self.restorep_switch = ctk.CTkSwitch(row, text="",
                                             font=self.skin.font(12),
                                             command=self._restorep_changed,
                                             progress_color=self.skin.accent,
                                             border_color=self.skin.border)
        self.restorep_switch.grid(row=0, column=1, sticky="e")
        if rst.get("enabled"):
            self.restorep_switch.select()
        row = self._row(parent, "which profile", TIPS["restore_profile"])
        self.restorep_menu = ctk.CTkOptionMenu(
            row, values=self._restorep_names(), width=240,
            command=self._restorep_pick, **self.skin.menu_style())
        self._set_menu(self.restorep_menu,
                       self._restorep_label(rst.get("profile") or "last"))
        self.restorep_menu.grid(row=0, column=1, sticky="e")
        row = self._row(parent, "what to restore", TIPS["restore_scope"])
        self.restorep_scope_menu = ctk.CTkOptionMenu(
            row, values=[lbl for _, lbl in RESTORE_SCOPES], width=240,
            command=self._restorep_scope, **self.skin.menu_style())
        self._set_menu(self.restorep_scope_menu,
                       self._pair_label(RESTORE_SCOPES,
                                        rst.get("scope") or "full"))
        self.restorep_scope_menu.grid(row=0, column=1, sticky="e")
        row = self._row(parent, "applies to", TIPS["restore_when"])
        self.restorep_when_menu = ctk.CTkOptionMenu(
            row, values=[lbl for _, lbl in RESTORE_WHENS], width=240,
            command=self._restorep_when, **self.skin.menu_style())
        self._set_menu(self.restorep_when_menu,
                       self._pair_label(RESTORE_WHENS,
                                        rst.get("when") or "autostart"))
        self.restorep_when_menu.grid(row=0, column=1, sticky="e")
        self.restorep_warn = None
        self.restorep_note = ctk.CTkLabel(
            parent, text=self._restorep_note(), font=self.skin.font(11),
            wraplength=560, justify="left", anchor="w",
            **self.skin.text_style("sub"))
        self.restorep_note.pack(anchor="w")

    def _restorep_names(self):
        """'last' first, then every profile by name - the picker on
        the profiles tab and this one read the same truth."""
        return [RESTORE_LAST[1]] + sorted(profiles.load()["profiles"])

    def _restorep_label(self, value):
        return RESTORE_LAST[1] if value == "last" else value

    def _restorep_value(self, label):
        return "last" if label == RESTORE_LAST[1] else label

    def _restorep_note(self):
        """fine print that tells the truth about how long login will
        wait - the calibration promise, or the learned number"""
        data = profiles.load()
        lg = data.get("login") or {}
        head = ("login gets the grace a storm needs, and results "
                "arrive as tray balloons - no dialog holds a "
                "half-woken desktop hostage. ")
        try:
            mx = float(lg.get("max") or 0)
        except (TypeError, ValueError):
            mx = 0.0
        if mx > 0:
            return head + ("learned from your logins: the slowest "
                           "app took %d s to show after launch, so "
                           "launches now wait %d s."
                           % (int(mx), int(profiles.launch_delay(
                               data))))
        return head + ("the FIRST login waits 2 full minutes "
                       "before launching anything and times every "
                       "app that shows up; after that, launches "
                       "wait only the slowest boot + 20 s (never "
                       "under 30 s, never over 10 min).")

    def _restorep_warn(self):
        """the first-login promise, spoken when the lever is armed -
        and only then: once a metric exists there is nothing new to
        warn about"""
        if (profiles.load().get("login") or {}).get("max"):
            return
        dlg = ctk.CTkToplevel(self)
        self.restorep_warn = dlg
        dlg.title("first login restore")
        dlg.resizable(False, False)
        dlg.configure(fg_color=self.skin.bg)
        dlg.transient(self)
        ctk.CTkLabel(
            dlg, text="the FIRST login restore will wait longer: 2 "
                      "full minutes before launching anything, "
                      "because it is timing how long this machine "
                      "needs. every login after that waits only "
                      "the slowest boot it measured + 20 s (never "
                      "under 30 s, never over 10 min).",
            font=self.skin.font(12), justify="left", wraplength=340,
            **self.skin.text_style()).pack(padx=20, pady=(14, 8))

        def close():
            dlg.destroy()
            if self.restorep_warn is dlg:
                self.restorep_warn = None

        ctk.CTkButton(dlg, text="got it", width=110, command=close,
                      **self.skin.primary()).pack(pady=(0, 14))
        dlg.after(30, dlg.focus_force)       # Windows steals focus
                                             # back without this

    def _restorep_changed(self):
        on = bool(self.restorep_switch.get())
        self.cfg.setdefault("restore", {})["enabled"] = on
        self._save()
        if on:
            self._restorep_warn()

    def _restorep_pick(self, label):
        self.cfg.setdefault("restore", {})["profile"] = \
            self._restorep_value(label)
        self._save()

    def _restorep_scope(self, label):
        for value, lbl in RESTORE_SCOPES:
            if lbl == label:
                self.cfg.setdefault("restore", {})["scope"] = value
                break
        self._save()

    def _restorep_when(self, label):
        for value, lbl in RESTORE_WHENS:
            if lbl == label:
                self.cfg.setdefault("restore", {})["when"] = value
                break
        self._save()

    # --------------------------------------------------------------- cameras --
    def _scan_cameras(self):
        """Opening every index is slow (the virtual camera alone takes
        up to 16 s), so enumerate on a helper thread and hand the
        answer back through after()."""
        def worker():
            from .. import camera
            try:
                names = camera.camera_names()
                found = [(index, opened, width,
                          names[index] if index < len(names) else "")
                         for index, opened, width
                         in camera.enumerate_cameras() if opened]
            except Exception:
                log.exception("camera scan failed")
                found = []
            try:
                self.ui_events.put(("cameras", found))
            except Exception:
                pass                    # the window closed mid-scan
        threading.Thread(target=worker, daemon=True, name="ui-scan").start()

    def _apply_cameras(self, found):
        from .. import camera
        self._cams = found
        labels = []
        for index, opened, width, name in found:
            label = "index %s (%s px)" % (index, int(width))
            if name:
                label += " %s" % name
            labels.append(label)
        if not labels:
            labels = ["no camera opens"]
        # the hello IR entry rides on the end either way: the real
        # groups when the whircam bridge lives, an invitation when it
        # does not - the feature must be reachable without ever
        # opening config.toml
        if camera.optional_present("whircam"):
            for name in camera.hello_ir_names():
                labels.append("index %s hello IR %s"
                              % (camera.HELLO_IR, name))
        else:
            labels.append(self.IR_INSTALL)
        self.camera_menu.configure(values=labels)
        # the roster may be a list (multi-camera); the picker is a
        # one-choice widget, so it shows the rotation's first post
        # and picking any single entry collapses the roster onto it
        current = config.normalize_index(self.cfg["camera"]["index"])[0]
        want = self.IR_INSTALL if current == camera.HELLO_IR else None
        for label in labels:
            if label == want or \
                    label.startswith("index %s " % current) or \
                    label == "index %s" % current:
                self._set_menu(self.camera_menu, label)
                break
        # config already points at hello IR but the bridge is missing
        # (a hand-edited config, or a venv rebuilt without -Optional):
        # the camera would only fail into the log - ask instead, once
        if (current == camera.HELLO_IR
                and not camera.optional_present("whircam")
                and not getattr(self, "_dep_asked", False)):
            self._dep_asked = True
            self._dep_prompt(switch=False)

    # ----------------------------------------------------------------- tick --
    def destroy(self):
        """destroy() tears children down first while Tk still processes
        the queue - a pending tick then reschedules itself on the
        half-dead interpreter forever (measured: an endless "ui tick
        failed" loop whose mainloop never returned). Flag the dying
        state and the chain just quits."""
        self._dying = True
        try:
            self.tips.kill()
        except Exception:
            pass
        super().destroy()

    def _tick_ui(self):
        if getattr(self, "_dying", False):
            return
        try:
            self._tick_inner()
        except Exception:
            log.exception("ui tick failed; the loop goes on")
        try:
            self.after(90, self._tick_ui)
        except Exception:
            pass                        # the window was destroyed

    def _tick_inner(self):
        now = time.monotonic()
        self._drain_ui_events()
        slot = self.monitor.framebox.get()
        if slot is not None and slot[3] != self._shown_ts:
            self._draw(slot)
        self._update_status(now, slot)
        if bool(self.live_switch.get()) and self.state() == "normal":
            self._lease_ticks += 1
            if self._lease_ticks % 6 == 0:      # ~0.5 s heartbeats for
                self.monitor.events.put(("preview", 1.5))    # a 1.5 s
                                                    # lease

    def _drain_ui_events(self):
        while True:
            try:
                message, _value = self.ui_events.get_nowait()
            except queue.Empty:
                break
            if message == "quit":
                self.destroy()
                return
            if message == "open":
                self.deiconify()
                self.lift()
                self.focus_force()
            if message == "assistant_truth":
                self._assistant_truth(_value)
            if message == "assistant_ui":
                self._assistant_ui(_value)
            if message == "startup":
                from .. import startup
                self._startup_sync(startup.enabled())
            if message == "cameras":
                self._apply_cameras(_value)

    def _update_status(self, now, slot):
        state = self.monitor.state
        if self.monitor.paused:
            state = "paused"
        self.chip.configure(text=state, fg_color=self.skin.chip(state))
        idle = self._idle()
        age = "never" if slot is None else "%.1f s" % (now - slot[3])
        self.idle_label.configure(
            text="idle %.0f s · frame %s old · %d seen"
            % (idle, age, len(slot[1]) if slot else 0))
        self.pause_button.configure(
            text="Resume" if self.monitor.paused else "Pause")
        paused_re = getattr(self.monitor, "re_off_paused", False)
        self.reoff_label.configure(
            text="PAUSED (camera slipped?)" if paused_re else "on")
        self.reoff_button.configure(
            state="normal" if paused_re else "disabled")
        self._update_blockers()
        want = self._detect_mode_label(self.cfg)   # a tray flip lands here
        if self.mode_button.get() != want:      # through the shared cfg
            self.mode_button.set(want)          # dict; set() fires no command
            self._show_mode_rows()               # and the rows follow suit

    def _update_blockers(self):
        b = getattr(self.monitor, "blockers", None) or {}
        err = b.get("error")
        held = b.get("display") or []
        others = b.get("other") or []
        over = b.get("overridden") or []     # "*OVERRIDE ..." already
        rows = []                            # (text, mood) - moods are
        if self.power_msg and time.time() - self.power_msg_ts < 25:
            rows.append((self.power_msg, "warn"))
        if err:                              # palette keys, nothing more
            rows.append((err, "warn"))
        if held:
            rows.append(("holding the display - the camera waits:",
                         "danger"))
            rows += [("  " + x[:80], "danger") for x in held[:6]]
        if over:
            rows.append(("user-overridden in powercfg - camera does "
                         "not wait for these:", "sub"))
            rows += [(x[:88], "sub") for x in over[:6]]
        if others:
            rows.append(("sleep only (fine): "
                         + "; ".join(x[:48] for x in others[:3]), "sub"))
        if not bool(self.power_switch.get()) and not (err or held):
            rows.append(("off: powercfg needs admin, so nothing is "
                         "checked and polling never pauses; tick to "
                         "register a scheduled task (one admin confirm)",
                         "sub"))
        if not rows:
            rows.append(("nothing pins the display; the camera guards it",
                         "ok"))
        colors = {"danger": self.skin.danger, "warn": self.skin.paused,
                  "sub": self.skin.subtext, "ok": self.skin.ok}
        sig = tuple(rows)
        if getattr(self, "_blockers_sig", None) == sig:
            return                    # identical text: never touch the
                                      # box - delete+insert snaps the
                                      # view to the top, and this runs
                                      # every tick, so the pane was
                                      # un-scrollable (user-confirmed)
        self._blockers_sig = sig
        box = self.blockers_box
        # customtkinter 6 turns tags= into a bare tag NAME and leaves
        # foreground empty (measured: tags on char 1.0 = ('#ff5d5d',)
        # with fg "") - the color goes on the inner tk.Text, per mood
        inner = getattr(box, "_textbox", box)
        for mood, color in colors.items():
            try:
                inner.tag_configure(mood, foreground=color)
            except Exception:
                pass
        try:                          # survive a real content change
            was = float(inner.yview()[0])      # where the user was
        except Exception:
            was = 0.0
        box.delete("1.0", "end")
        for text, mood in rows:
            box.insert("end", text + "\n", tags=mood)
        if was > 0.0:
            try:
                inner.yview_moveto(0, was)     # fraction of content:
            except Exception:                  # the honest best we can
                pass                           # do for changed text

    @staticmethod
    def _idle():
        from .. import display
        try:
            return display.get_idle_time()
        except Exception:
            return float("inf")

    def _draw(self, slot):
        frame, boxes, scores, ts = slot
        self._shown_ts = ts
        img = frame.copy()
        for box, score in zip(boxes, scores):
            cv2.rectangle(img, box[:2].astype(int), box[2:].astype(int),
                          color=self.skin.box_bgr, thickness=2)
            cv2.putText(img, "%.2f" % float(score),
                        (int(box[0]), max(int(box[1]) - 6, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.skin.box_bgr, 2)
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        width = int(self.cfg["ui"]["preview_width"])
        height = int(width * img.shape[0] / max(img.shape[1], 1))
        image = Image.fromarray(rgb).resize((width, height))
        self._ctkimg = ctk.CTkImage(light_image=image, dark_image=image,
                                    size=(width, height))
        self.preview_label.configure(image=self._ctkimg, text="")
        self.preview_info.configure(
            text="%dx%d · %d box%s · the exact frame the detector judged"
            % (img.shape[1], img.shape[0], len(boxes),
               "" if len(boxes) == 1 else "es"))

    # ---------------------------------------------------------------- close --
    def _hide(self):
        self.withdraw()                   # the app keeps running in the
        self.tips.kill()                  # tray; the lease dies
        self.monitor.events.put(("preview", 0))


def run(cfg, monitor, ui_events):
    window = SettingsWindow(cfg, monitor, ui_events)
    window.mainloop()
    return window
