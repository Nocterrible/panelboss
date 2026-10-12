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
    "min_hits": "consecutive positive frames before the screens wake - "
                "any eye on duty may vote. The rotor never resets the "
                "streak when cameras rotate (two votes may come from "
                "different eyes); an unreadable or BLINDED camera "
                "(another app holds it - a work call through NVIDIA "
                "Broadcast - or the room is dark) abstains: no verdict, "
                "adds nothing, resets nothing.",
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
    "camera": "picks ADD a camera to duty; on-duty cameras show as "
               "policy rows below (and leave this menu). Opening every "
               "index is slow (the virtual camera alone takes 16 s), "
               "so the list fills in after the window opens and "
               "rescans on demand.",
    "cam_on": "the screens-on default for cameras set to follow "
               "global: boot per poll rests the LED, always on streams "
               "through the standby transition.",
    "cam_off": "the screens-off default for cameras set to follow "
                "global: always on is the measured-reliable choice (a "
                "device reopened INSIDE the standby transition never "
                "streams again).",
    "cam_policies": "per-camera overrides of the two defaults above. "
                    "a camera joins this list when the menu adds it, "
                    "starting at follow global; remove takes it off "
                    "duty and wipes its overrides, so re-adding is "
                    "pristine.",
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
    "logs": "every decision and the reason, in %APPDATA%\\PanelBoss\\logs.",
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
                    "enable G-SYNC yourself - PanelBoss never touches "
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
