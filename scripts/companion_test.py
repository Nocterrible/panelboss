"""The companion's config pin (Oct 16, the native-messaging v0.3 move).
The debug-flag route is dead AND now removed: the debug port handed any
local process full CDP (the infostealer classic), and the companion is
the native-messaging extension - the extension measures the video, the
local host writes the app's own doorway file, the eye reads it. This pin
proves the one-consent shape: [videodim].on is the only rail, the
retired enabled/flag_families/sites keys parse away without surprise,
and the module (companion.on/say/veil_now) answers the off words on junk
and the live words on a click. The doorway is redirected to a temp dir
so the owner's real rect file never touches the suite.
Run: .venv\\Scripts\\python.exe scripts\\companion_test.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["PANELBOSS_CONFIG_DIR"] = tempfile.mkdtemp(prefix="panelboss_cmp_")

from panelboss import config   # noqa: E402
from panelboss import companion   # noqa: E402
from panelboss import videoeye   # noqa: E402

fails = []
passed = []


def check(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    (passed if cond else fails).append(name)


D = config.DEFAULTS["videodim"]
check("on" in D and "enabled" not in D and "flag_families" not in D
      and "sites" not in D,
      "the default is the one-consent shape: on present, enabled/"
      "flag_families/sites absent")
check(D.get("on") is False,
      "the companion default is on False (the default-off law)")

# a stock get_config carries only on, and the normalizer passes it
# through while DROPPING the retired keys a pre-ruling file may carry
c = config.get_config(verbose=False)
check(c["videodim"].get("on") is False and "enabled" not in c["videodim"],
      "get_config answers on False and carries no enabled on a virgin "
      "file")

# a pre-ruling config with the retired keys still loads - the retired
# words are dropped, the single consent survives
path = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"], "config.toml")
with open(path, "w", encoding="utf-8") as f:
    f.write("[videodim]\non = true\nenabled = false\n"
            "flag_families = ['chrome']\nsites = ['netflix.com']\n")
c2 = config.get_config(verbose=False)
check(c2["videodim"].get("on") is True and "enabled" not in c2["videodim"]
      and "flag_families" not in c2["videodim"]
      and "sites" not in c2["videodim"],
      "a pre-ruling file on=true loads; the retired enabled/"
      "flag_families/sites words are gone")

n = config.normalize_videodim({"on": "junk", "enabled": True,
                               "flag_families": ["chrome"],
                               "sites": ["youtube.com"]})
check(n == {"on": False, "min_rect_px": 200000, "grace_s": 3},
      "junk on folds to False and the retired keys never survive the "
      "normalizer")

# the companion module: junk answers the off words, never raises
for junk in (None, {}, {"videodim": "junk"}, {"videodim": 7},
             {"videodim": {"on": "yes"}}):
    try:
        words = companion.say(junk)
    except Exception as e:      # noqa: BLE001
        words = "RAISED %s" % e
    check(words == "video-dim off - arm it and the click is honored",
          "junk config %r answers the off words, never an exception"
          % (junk,))
check(companion.on({"videodim": {"on": True}}) is True
      and companion.on({"videodim": {"on": "yes"}}) is False,
      "on is strict like the normalizer: only True is on")

# redirect the doorway to a temp file the desk cannot own
_real_rect = videoeye.RECT_PATH
_dark = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"], "no-rect")
videoeye.RECT_PATH = _dark
try:
    check(companion.bridge_state() is None,
          "no doorway file answers None, never raises")
    check(companion.say({"videodim": {"on": True}}) == companion.NO_BRIDGE,
          "the say line names the missing click in the pinned words")
    check(companion.veil_now({"videodim": {"on": True}})
          == companion.NO_BRIDGE,
          "the manual one-shot on a dark desk answers NO_BRIDGE")

    # a click: a temp file through the eye's own doorway, folded to
    # physical px and fed - the button's contract
    body = {"rect": {"left": 0, "top": 0, "width": 800, "height": 450},
            "dpr": 1.5, "paused": False, "scroll": [0, 0],
            "view": [1920, 1080], "family": "chrome",
            "bounds": {"left": 100, "top": 50, "width": 1920,
                       "height": 1080}}
    with open(_dark, "w", encoding="utf-8") as f:
        f.write(json.dumps(body) + "\n")
    words = companion.veil_now({"videodim": {"on": True,
                                             "min_rect_px": 1}})
    check(words.startswith("companion rect 1200x675 at 150,75"),
          "the click folds through the eye's own door: %r" % (words,))
    st = videoeye._STATE.get("chrome")
    check(st is not None and st["row"] is not None
          and st["row"]["rect"]["width"] == 800,
          "the one-shot feeds the eye's state fresh-wins: the dimmer's "
          "next tick frames it")
    words = companion.veil_now({})
    check(words.startswith("saw the rect"),
          "a click with the eye unarmed says so, no state fed")
    check(isinstance(companion.door_dir(), str)
          and companion.door_dir() == _dark,
          "door_dir() answers the redirected doorway path")
finally:
    videoeye.RECT_PATH = _real_rect

print("COMPANION-PIN OK (%d)" % len(passed) if not fails
      else "COMPANION-PIN FAILED: %s" % fails)
sys.exit(1 if fails else 0)