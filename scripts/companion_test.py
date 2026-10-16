"""The companion's config pin (Oct 15, the retired-flag dossier).
The debug-flag route is dead: the debug port hands any local process
full CDP (the infostealer classic), the approval dialogs and the
automation banner make the app look like the cookie thief, and Opera's
own Content/Privacy gate refused the flag. The replacement is the
content-script companion (extension/): no debugger, no port. This pin
proves the default answers that story - enabled False AND the default
flag_families empty - so no boot can silently re-flag a browser again.
Run: .venv\\Scripts\\python.exe scripts\\companion_test.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["PANELBOSS_CONFIG_DIR"] = tempfile.mkdtemp(prefix="panelboss_cmp_")

from panelboss import config   # noqa: E402
from panelboss import companion   # noqa: E402

fails = []
passed = []


def check(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if cond:
        passed.append(name)
    else:
        fails.append(name)


D = config.DEFAULTS["videodim"]
check(D.get("enabled") is False,
      "the companion default is enabled False (the opt-in law)")
check(tuple(D.get("flag_families")) == (),
      "the default flag_families is empty: zero families get the "
      "debug port on a stock boot")

# the load path must not launder those answers away: a stock get_config
# carries them, and the normalizer passes them through
c = config.get_config(verbose=False)
check(c["videodim"]["enabled"] is False,
      "get_config answers enabled False on a virgin file")
check(c["videodim"]["flag_families"] == [],
      "get_config answers empty flag_families (the list the writers use)")

# an on-disk true must win over the default (the rail is the owner's
# word), and a junk value warns to the default, not a crash
path = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"], "config.toml")
with open(path, "w", encoding="utf-8") as f:
    f.write("[videodim]\nenabled = true\nflag_families = ['chrome']\n")
c2 = config.get_config(verbose=False)
check(c2["videodim"]["enabled"] is True
      and c2["videodim"]["flag_families"] == ["chrome"],
      "the file's answers win over the stock defaults")
os.remove(path)
n = config.normalize_videodim({"enabled": "junk", "flag_families": "chrome"})
check(n["enabled"] is False and n["flag_families"] == [],
      "junk enabled/families warn to the defaults, never raise")

# the companion module (Oct 15, the card ship): junk config answers
# the off words and never raises - the card's honesty law. The
# bridge probe reads the real doorways, so the file legs run against
# a temp doorway the desk cannot already own.
from panelboss import videoeye                      # noqa: E402
from panelboss import companion                    # noqa: E402

for junk in (None, {}, {"videodim": "junk"}, {"videodim": 7},
             {"videodim": {"on": "yes", "flag_families": "chrome"}},
             {"videodim": {"flag_families": [3, "opera_gx"]}}):
    try:
        words = companion.say(junk)
    except Exception as e:
        words = "RAISED %s" % e
    check(words == "video-dim off - arm it and the click is honored",
          "junk config %r answers the off words, never an exception"
          % (junk,))
check(companion.enabled({"videodim": {"enabled": True}}) is True
      and companion.enabled({"videodim": {"enabled": "yes"}}) is False,
      "enabled is strict like the normalizer: only True is on")
check(companion.families({"videodim": {"flag_families": [3, "chrome",
                                                         "safari"]}})
      == ["chrome"],
      "families keeps the eye's real names and drops the rest")

# the real keys round-trip: the shape normalize_videodim answers,
# through the module the card reads
real = {"videodim": {"enabled": True, "on": True,
                     "flag_families": ["chrome", "opera_gx"],
                     "sites": [], "min_rect_px": 1, "grace_s": 2}}
check(companion.enabled(real) and companion.families(real)
      == ["chrome", "opera_gx"],
      "the rail's real keys round-trip through enabled/families")
try:
    words = companion.say(real)
except Exception as e:
    words = "RAISED %s" % e
check(words.startswith("debug-flag rail on: chrome, opera_gx | "),
      "the say line quotes the rail back in words (bridge leg next)")

# the no-bridge legs: pin both doorways at a file that cannot exist
_real_bridges = videoeye.BRIDGES
_dark = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"], "no-rect")
videoeye.BRIDGES = (_dark,)
try:
    check(companion.bridge_state() is None,
          "no bridge file answers None, never raises")
    check(companion.say(real) == "debug-flag rail on: chrome, "
                                 "opera_gx | " + companion.NO_BRIDGE,
          "the say line names the missing bridge in the pinned words")
    check(companion.veil_now(real) == companion.NO_BRIDGE,
          "the manual one-shot on a dark desk answers NO_BRIDGE")
finally:
    videoeye.BRIDGES = _real_bridges

# and the one-shot that sees a click: a temp file through the eye's
# own doorway, folded to physical px and fed - the button's contract
_dark2 = _dark + "2"
row = ("{\"rect\": {\"left\": 0, \"top\": 0, \"width\": 800, "
       "\"height\": 450}, \"dpr\": 1.5, \"paused\": false, "
       "\"scroll\": [0, 0], \"view\": [1920, 1080], \"family\": "
       "\"chrome\", \"bounds\": {\"left\": 100, \"top\": 50, "
       "\"width\": 1920, \"height\": 1080}}\n")
with open(_dark2, "w", encoding="utf-8") as f:
    f.write(row)
videoeye.BRIDGES = (_dark2,)
try:
    words = companion.veil_now(real)
    check(words.startswith("bridge rect 1200x675 at 150,75"),
          "the click folds through the same door the tick uses "
          "(dpr-scaled bounds, chrome-folded): %r" % (words,))
    st = videoeye._STATE.get("chrome")
    check(st is not None and st.row is not None
          and st.row["rect"]["width"] == 800,
          "the one-shot feeds the eye's state freshest-wins: the "
          "dimmer's next tick frames it")
    words = companion.veil_now({})
    check(words.startswith("saw the rect"),
          "a click with the eye unarmed says so, no state fed")
finally:
    videoeye.BRIDGES = _real_bridges
    try:
        os.remove(_dark2)
    except OSError:
        pass

print("COMPANION-PIN OK (%d)" % len(passed) if not fails
      else "COMPANION-PIN FAILED: %s" % fails)
sys.exit(1 if fails else 0)
