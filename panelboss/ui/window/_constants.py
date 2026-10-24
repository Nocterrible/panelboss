"""Window vocabularies: tip strings, timer specs, menu
pairs. Pure data, zero logic.
"""

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
    ("timers", "off_poll_sec", "first dark re-poll", 1, 15, 1,
     "how long the presence watch waits before its first re-poll after "
     "the screens go dark (the LED is invisible anyway)"),
    # THE DEGRADED ALWAYS-ON RE-READ GATES (owner ruling, Oct 13 late;
    # the split E1 shipped at 8d30a6c): these two ride the same slider
    # idiom and read as a family with the row above (first re-poll /
    # dark re-read / lit re-read). The FRESH-eye ~5 Hz read in the dark
    # is UNCAPPED - the owner answered E1's ceiling question: "the point
    # of an always on cam is instant recognition, if someone wants 10s
    # polls they can set 10 sec polls and let the camera sleep". So
    # these gates only govern the DEGRADED eye (the one whose wear clock
    # ran out); a held stream still reads as fast as it can. They are
    # [camera] keys: _timer_changed writes the very dict the policy
    # reads live at the branch every tick ("writing is applying"), so
    # these are the only live-in-app-tab rows in the design - no re-arm,
    # no restart needed.
    ("camera", "always_fallback_poll_sec", "always-on re-read, screens off",
     1, 15, 1,
     "always-on: the degraded eye re-reads once per configured second "
     "while the screens are off (the stream stays open; 1 s is the "
     "default and the point - a hand-edited [camera] value outranks "
     "the slider until moved)"),
    ("camera", "always_fallback_poll_on_sec", "always-on re-read, screens on",
     5, 15, 1,
     "the lit-table twin of the dark gate: how often a degraded always-on "
     "eye re-reads while the screens are lit - low keeps the eye live, "
     "high lets the stream rest between reads"),
    ("timers", "present_recheck_sec", "present recheck", 10, 300, 5,
     "how often a confirmed person is re-checked while they sit there"),
]

# THE GRACE PAIR (owner ruling, Oct 22): the same spec rows the Timers
# card built for the sliders' whole life, byte-identical ranges and
# steps, edited from the power plan's wake card from today - they
# negotiate the wake policy above them, not the detection clock. The
# [timers] and [recovery] config sections are UNCHANGED; _timer_row /
# _timer_changed serve both lists, so the write paths and the live
# apply ("monitor.timers / monitor.recovery are these very dicts")
# did not move an inch.
WAKE_SPECS = [
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

TABS = ("detection", "power plan", "monitor profiles", "oled",
        "general")      # general last (owner UAT, Oct 15); detection
                        # first stays the landing tab (TABS[0]). The
                        # power plan moved up to sit immediately AFTER
                        # detection (owner Oct 21): the hold's 'present'
                        # third state and the dark-camera notice make
                        # the dependency real - the two cards belong
                        # adjacent; monitor profiles drops one slot
                        # (less related to detection than the timers
                        # it now shares the row with)

PERSON_ROWS = ("device", "cuda gpu id", "confidence", "min hits")
MOTION_ROWS = ("frame changes", "pixel delta", "motion hold")

TIPS = {
    # THE TOOLTIP LAW (owner sweep, Oct 22): what the control does,
    # one sentence; a second for the why when the label cannot carry
    # it; load-bearing facts (restart-required, fallbacks, ranges)
    # stay as short clauses; no history, no narrative.
    "mode": "person judges faces with the model; motion judges frame "
            "changes with no ML. Switching rebuilds the detector "
            "immediately.",
    "device": "where the model runs. CUDA needs a capable card. "
              "Applies immediately.",
    "gpu": "which card, for the record, when device is CUDA. Applies "
           "immediately.",
    "confidence": "how sure a detection must be before a frame counts "
                  "as a person. Applies to the next frame.",
    "min_hits": "consecutive positive frames before the screens wake. "
                "With several eyes, any eye that sees votes present; absent "
                "needs every eye to deny. An eye that cannot see never votes "
                "and never resets the streak.",
    "frame changes": "share of the frame that must move before a poll "
                     "counts as motion. Applies immediately.",
    "pixel delta": "how much one pixel must shift to count as a "
                   "change; raise it for noisy depth or infrared "
                   "sensors. Applies immediately.",
    "motion hold": "how long presence lingers after the LAST motion - "
                   "reading a page is stillness, not absence. Applies "
                   "immediately.",
    "pump": "Ignores fake input from devices like macro pads, KVMs "
            "and jigglers - only real movement and keystrokes count. "
            "Takes effect after a restart. Off, the app uses Windows' "
            "own idle clock, and a deaf pump falls back to it by "
            "itself. Remote-control software can still wake the "
            "screen.",
    "wake": "what happens when the screens came back without the app. "
            "re-off darkens them again after the re-off grace unless "
            "a person is confirmed; leave-on hands the desk over for "
            "its grace period. Applies immediately.",
    "reoff": "after two unexpected wakes in a row the app leaves the "
             "screens lit; 'resume now' restarts the watch.",
    "hold_display": "Windows cannot turn the screens off while the app "
                    "watches a lit desk. 'while present' holds only "
                    "while the camera sees a person - absent or no "
                    "verdict hands the timer back the same instant, "
                    "and pausing, snoozing or quitting always hand it "
                    "back.",
    "hold_sleep": "the plan's sleep timer is held back too; 'while "
                  "present' follows the camera verdict the same way. "
                  "While the screens are dark this is what keeps the "
                  "watcher alive to notice the return.",
    "profile_picker": "a profile stores the monitors (by hardware "
                      "identity), their places, modes, the HDR ask "
                      "and the pinned windows. The picker opens on "
                      "the profile last used for the desk it sees; "
                      "'create new...' copies the live desk. A "
                      "profile cannot fix a monitor that is not "
                      "plugged in.",
    "profile_rescue": "brings back every visible window no screen "
                      "covers, centered on the primary monitor. "
                      "Minimized windows, dialogs and other-desktop "
                      "windows stay put.",
    "profile_match": "how a saved seat recognizes its live window. "
                     "'process' survives app renames but moves EVERY "
                     "window of that app; 'process + title' pins one "
                     "window; 'title' matches by name only.",
    "profile_hdr": "what to do with HDR when the profile applies. "
                   "'restore as captured' returns each panel to its "
                   "captured state, 'ignore' asks nothing, and 'all "
                   "on/off' commands every HDR-capable panel. On "
                   "older Windows, which cannot report the state, "
                   "'restore as captured' skips itself rather than "
                   "restore a guess.",
    "profile_apply": "one click reshapes the desk: topology first, "
                     "modes asked only from the driver's own list, "
                     "HDR at exactly the monitors that disagree, "
                     "then the windows once the monitors answer. "
                     "Anything the shuffle stranded off-screen is "
                     "rescued on the spot.",
    "profile_pins": "a seat reserved for an app: the spot it holds "
                    "now becomes where the profile puts it back. "
                    "Click a pinned row to edit it, x to forget it. "
                    "The profile moves only what you pinned.",
    "profile_pin_open": "'open it if missing' runs the saved exe when "
                        "no window of that app answered the profile, "
                        "and moves the first window that appears. "
                        "Store apps and shortcut-only launchers may "
                        "need the exe line pointed at the real door.",
    "profile_pin_wait": "how long an 'open it' wait lasts before the "
                        "seat counts as missed (5 s to 10 min, "
                        "default 30). It ends the moment a window "
                        "shows.",
    "profile_pin_exe": "what 'open it' actually runs. By default the "
                       "exe of the window as captured; browse points "
                       "the pin at the launcher or binary that really "
                       "shows the window (a .lnk shortcut works too).",
    "restore_on": "re-applies a profile when the app starts. The "
                  "logon copy is identified by its --autostart flag, "
                  "so a manual launch while debugging never moves the "
                  "desk unless you say every start.",
    "restore_profile": "'the last one for this desk' matches by the "
                       "panels physically present; naming a deleted "
                       "profile says so on the tray and does nothing "
                       "else.",
    "restore_scope": "monitors only leaves the windows alone; windows "
                     "only never asks the drivers anything. Different "
                     "panels refuse the apply outright - every scope.",
    "restore_when": "'only logon starts' moves the desk on autostart "
                    "launches; 'every app start' moves it on any. The "
                    "first login waits out two full minutes, later "
                    "ones the slowest observed boot plus 20 s.",
    "camera": "adds a camera to duty; on-duty cameras show as policy "
              "rows below (and leave this menu). Opening every index "
              "is slow (the virtual camera alone takes 16 s), so the "
              "list fills in after the window opens.",
    "cam_on": "the screens-on default for cameras set to follow "
              "global: boot per poll rests the LED, always on streams "
              "through the standby transition.",
    "cam_off": "the screens-off default for cameras set to follow "
               "global. always on is the reliable choice: a device "
               "reopened inside the standby transition never streams "
               "again.",
    "cam_policies": "per-camera overrides of the two defaults above. "
                    "A camera joins the list when the menu adds it, "
                    "starting at follow global; removing it takes it "
                    "off duty and wipes its overrides.",
    "live": "holds the camera open for this window at ~5 fps so the "
            "picture shows exactly what the detector judged. The hold "
            "is a lease: closing the window releases the device.",
    "assistant": "powercfg /requests needs administrator rights, so a "
                 "scheduled task dumps it silently instead (one "
                 "confirm on tick).",
    "skin": "the palette. The layout and all behavior are identical.",
    "min": "boot starts hidden in the tray; left-click the icon to "
           "open the window. Applies from the next launch. Closing "
           "the window always hides it to the tray anyway.",
    "startup": "the per-user Run key - exactly the entry Task "
               "Manager's startup tab lists. No admin, and the app "
               "verifies it by reading the registry back.",
    "logs": "every decision and the reason, in %APPDATA%\\PanelBoss\\logs.",
    "update": "check now asks GitHub for the newest release; update "
              "now installs it and this copy quits - the update "
              "console says why if it stays closed. run.bat (or the "
              "shortcut) starts it again by hand.",
    "gaming": "a game gets its panel's top refresh rate; the desktop "
              "gets a cooler one. Only rates the panel already lists "
              "are traded; the resolution is never touched. A listed "
              "exe enters game mode the moment it owns a monitor; "
              "any other app must hold real evidence first. Leaving "
              "rides a grace timer: an alt-tab does not flicker the "
              "rate.",
    "gaming_rates": "only rates the panel's driver offers are listed; "
                    "'auto' is the panel's fastest. The desktop rate "
                    "is law while not gaming - the watcher re-heals "
                    "it whenever the driver forgets. 'keep' means "
                    "hands off. For VRR, tick the box after enabling "
                    "G-SYNC yourself: the app stops flipping that "
                    "panel's mode and keeps it at max.",
    "gaming_games": "exe names that enter game mode the moment they "
                    "own a monitor, one per line. 'add what's in "
                    "front of me' appends the window that currently "
                    "covers the screen.",
    "gaming_ignore": "exe names that must never count as games, even "
                     "if they fool every other test. One exe per "
                     "line.",
    "gaming_plan": "the power plan swapped in while a game owns a "
                   "monitor ('' = never). The plan active before the "
                   "game comes back when it leaves - only if nobody "
                   "else moved it.",
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
# the per-PANEL color selector (amendment 8): the stored value is the
# boolean, and "keep" is the ABSENCE of the key - never a written
# false-lie (the desktop-rate menu's lesson, inherited). Rendered
# only where a PRECISE driver read says the panel can do HDR;
# everywhere else the selector is absent, not gray-lied
HDR_SET_LABELS = (("keep", None), ("hdr on", True), ("hdr off", False))
RESTORE_SCOPES = (("full", "the whole desk"),
                  ("monitors", "monitors only (modes + HDR)"),
                  ("windows", "windows only (pinned apps)"))
RESTORE_WHENS = (("autostart", "only logon/autostart starts"),
                 ("always", "every app start"))
