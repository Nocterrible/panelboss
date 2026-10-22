"""One-shot splice: replace the TIPS dict in _constants.py with the
owner-sweep-law version (Oct 22 batch). Run from repo root, then die."""
import io
import os

PATH = os.path.join("panelboss", "ui", "window", "_constants.py")
NEW = '''TIPS = {
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
                "An eye that cannot see never votes and never resets "
                "the streak.",
    "frame changes": "share of the frame that must move before a poll "
                     "counts as motion. Applies immediately.",
    "pixel delta": "how much one pixel must shift to count as a "
                   "change; raise it for noisy depth or infrared "
                   "sensors. Applies immediately.",
    "motion hold": "how long presence lingers after the LAST motion - "
                   "reading a page is stillness, not absence. Applies "
                   "immediately.",
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
    "logs": "every decision and the reason, in %APPDATA%\\\\PanelBoss\\\\logs.",
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
'''
src = io.open(PATH, encoding="utf-8").read()
start = src.index("TIPS = {")
end = src.index("\n}\n", start) + len("\n}\n")
io.open(PATH, "w", encoding="utf-8", newline="").write(
    src[:start] + NEW + src[end:])
print("spliced:", len(src), "->", start + len(NEW) + len(src) - end)
