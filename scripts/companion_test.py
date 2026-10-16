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

fails = []


def check(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
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

print("COMPANION-PIN OK" if not fails else "COMPANION-PIN FAILED: %s" % fails)
sys.exit(1 if fails else 0)
