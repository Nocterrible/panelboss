"""One-shot splice: the four _oled.py tip dicts under the owner's
tooltip law (Oct 22 sweep). Run from repo root, then die."""
import io

PATH = io.open("panelboss/ui/window/_oled.py", encoding="utf-8").read() \
    if False else "panelboss/ui/window/_oled.py"
src = io.open(PATH, encoding="utf-8").read()
start = src.index("TIP_JO = {")
end = src.index('    "mons": "per-monitor theater', start)
end = src.index("\n}\n", end) + len("\n}\n")
NEW = '''TIP_JO = {
    "on": "micro-jog moves the app covers around a small ring on a "
          "timer, so no edge of glass ages permanently; the wash "
          "briefly lights the whole panel to even out retention that "
          "has already begun. Opted-in covers only - prevention, not "
          "a diagnosis: the app cannot read your panel's wear "
          "counters.",
    "row": "jog covers on THIS monitor only - the opt-in is per panel "
           "because burn-in is the OLED problem.",
    "mode": "micro-jog moves the covers a few pixels every cycle; "
            "pixel wash happens only on the button below - a wash is "
            "a request, never a schedule.",
    "step": "how far the covers travel around the ring, 1..8 pixels; "
            "the ring returns to rest, so travel never accumulates.",
    "cycle": "minutes between ring steps.",
    "wash": "lights this monitor white for ten seconds, once; the "
            "first opted-in cover answers the button, and if none "
            "are opted in the word beside the button says so.",
}

TIP = {
    "on": "a taskbar that never moves eventually prints itself into "
          "OLED glass; this strip paints over the bar and steps "
          "aside for the cursor, so the pixels rest. Nothing changes "
          "until you opt in, and the strip is an ordinary window "
          "that dies with the app.",
    "row": "one strip per bar on THIS monitor; the opt-in is per "
           "panel because a panel that cannot burn in has no reason "
           "to wear the strip.",
    "reveal": "'hovered only' bars the bar you reached for; 'every "
              "bar' bares them all when you reach for any one. "
              "Returns stay per-bar timers either way.",
    "hold": "how long the cursor must stay clear of every bar before "
            "a withdrawn strip covers again; typing holds the count "
            "until the typing stops.",
    "conflict": "Windows' own per-bar auto-hide is on for this desk: "
                "the two hiders may double-hide, but the taskbar "
                "still comes back for the cursor and the strip "
                "follows it.",
}


TIP_DIM = {
    "on": "an idle desk puts a dark click-through veil over every "
          "window you are not using; the window you touch lights "
          "instantly, and a window the mic just heard keeps its "
          "brightness for four seconds. Elevated windows (Task "
          "Manager's class) never wear a veil this app cannot stack "
          "against - running the app elevated reaches them but is "
          "not recommended. Nothing dims until you opt in, per "
          "monitor.",
    "row": "dim veils on THIS monitor only - the opt-in law, shared "
           "with the strip and the refresh.",
    "always": "dims this panel WITHOUT the idle wait: the veils land "
              "when focus leaves the panel and lift when it returns. "
              "The sound exemption and the pause ride here too; only "
              "the countdown is skipped.",
    "idle": "how still the input must be before the veils land.",
    "ramp": "how long the fade takes once input returns - the veils "
            "step down at most three times and are gone; at zero the "
            "drop is immediate.",
    "level": "how dark the veils are, in percent.",
    "row_level": "this panel's OWN veil percent; a panel with a row "
                 "here ignores the global 'veil level'. The slider "
                 "opens at the global and the first move stores this "
                 "panel's number only.",
    "lift_fade": "off (the default) drops the veil the instant you "
                 "touch the desk; on reveals it through the 'fade "
                 "within' ramp. The theater card has its own twin.",
    "apps": "apps that never wear a veil, by exe file name as the "
            "title bar shows it (chrome.exe), one per line.",
    "key": "press a key to bind the pause toggle, esc clears it. No "
           "combo is stolen before you give one; a taken combo keeps "
           "its predecessor and says so. One press pauses, the next "
           "resumes.",
    "pause": "pause the dimmer without touching its settings: the "
             "field fades out within the ramp and returns the tick "
             "the pause lifts.",
}


TIP_COMP = {
    "on": "movie theater mode: a PLAYING video gets a dimmed frame "
          "around its window once the input has been still for the "
          "'veil after' wait; motion lifts the ring, which re-arms "
          "after the same wait, and a film's sound never touches it. "
          "The player window stays exempt from the PLAIN veils with "
          "or without this switch; the app learns the video's place "
          "from the buddy extension's native host.",
    "status": "the consent rail, the buddy extension's last push, and "
              "the geometry-test answer, refreshed on the dimmer's "
              "beat. A missing answer reads as words, never a crash.",
    "veil": "measures the video on the clicked tab right now, one "
            "shot, no idle wait - the calibration gesture; the "
            "feature is the automatic lane (playing AND still).",
    "path": "where the extension's native host writes its reports: "
            "the app's own folder, every browser. The extension id "
            "is the only credential; install the host once (the "
            "one-click install rides this row).",
    "install": "builds panelboss-host.exe (PyInstaller, ~40 s) and "
               "registers it for your user. The entry takes the "
               "browser's 32-char extension id, or derives it from "
               "the extension's path when empty; a bad shape says so "
               "and does not fire the installer.",
    "store": "opens the buddy's Chrome Web Store listing - any "
             "Chromium browser installs it. Add the extension here "
             "first, then 'install the helper' below.",
    "caps": "what the buddy's API can send, read from the host "
            "itself; no host installed reads as honest words and the "
            "install row is the answer. Re-checks when you touch the "
            "veil button or the switch.",
    "delay": "veil after: how long the input must be still before a "
             "PLAYING video gets its ring - the same number re-arms "
             "it after a lift. The clock is the app's input pump (by "
             "the 'keep Windows awake' switch below), so zero-travel "
             "device chatter no longer keeps the ring down; motion "
             "lifts the RING only, never the movie. 0 means instant.",
    "level": "how dark the four theater pieces are, in percent - the "
             "theater's own darkness, not the idle dimmer's number.",
    "fade": "off (the default): when the frame lifts it is gone that "
            "tick. On: it retracts over the dimmer's 'fade within' "
            "ramp, never a blink.",
    "pump": "Ignores fake input from devices like macro pads, KVMs "
            "and jigglers - only real movement and keystrokes count. "
            "Takes effect after a restart. Remote-control software "
            "can still wake the screen.",
    "mons": "per-monitor theater: a checked panel frames its playing "
            "video (or wears the full-field veil while the "
            "conjunction holds); unchecked panels get no theater at "
            "all. The slider is that panel's own veil percent - "
            "until you move it the panel follows the 'veil level' "
            "above, and rows save on first use.",
}
'''
io.open(PATH, "w", encoding="utf-8", newline="").write(
    src[:start] + NEW + src[end:])
print("oled tips spliced")
