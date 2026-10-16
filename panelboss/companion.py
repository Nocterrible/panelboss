"""companion: the video-dim companion's config rail and card words.

The debug-flag route is RETIRED (Oct 15, the retired-flag dossier): the
debug port hands any local process full CDP, the approval dialogs make
the app read as the cookie thief, and Opera's own Content/Privacy gate
refused the flag. The replacement is the content-script companion
(extension/): no debugger, no port, the bridge file the eye already
reads. The rail the dossier left lives in panelboss/config.py under
[videodim] (there is no 'companion' section): `enabled` is the
companion's opt-in rail (config.py:433), `on` the feature's own
consent, and `flag_families` carries the launch-with-the-flag
families (config.py:450) - this module reads THOSE keys and invents no
schema of its own.

The card (ui/window/_oled.py, the fourth card of the oled tab) uses:
`enabled`/`families` for the switches, `say` for its live words, and
`veil_now` for the manual one-shot. No watchdog, no relaunch logic -
the rail is the owner's word, and the loop thread answers it.
"""

import os
import time

from . import videoeye

# the family keys the card offers and the config may carry - the
# eye's own vocabulary (videoeye.BROWSERS; the extension stamps the
# same words onto its click). The card's row order: chrome, edge,
# opera gx (the packet's; the eye's BROWSERS order is its probe's).
FAMILIES = ("chrome", "edge", "opera_gx")

# the bundled extension folder, resolved from the app's own tree -
# the _general.py:153 root idiom (the module's dir, twice up)
EXT_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "extension")

# the exact no-bridge words (the button's and the say line's): pinned
# by scripts/companion_test.py so they never drift under the card
NO_BRIDGE = ("no bridge file yet - the buddy's icon writes it "
             "on click")


def _vd(cfg):
    """[videodim] as a dict; junk config answers {} instead of
    raising: the section may be missing, a bare string, or a list,
    and the card's honesty law is that junk reads as off, never an
    exception."""
    try:
        vd = (cfg or {}).get("videodim")
    except Exception:
        return {}
    return vd if isinstance(vd, dict) else {}


def enabled(cfg):
    """The companion's opt-in rail: [videodim] enabled (the real key;
    the card's master switch moves it WITH the consent key - the pair
    companion_retire_cleanup.py writes as one gesture). Strict like
    the normalizer: only True is on, junk is off."""
    return _vd(cfg).get("enabled") is True


def families(cfg):
    """The launch-with-flag families: [videodim] flag_families (the
    real key) as the eye's family names. A non-list or junk rows read
    as [] - the normalizer's own shape, narrowed to families the eye
    can actually knock on."""
    fams = _vd(cfg).get("flag_families")
    if not isinstance(fams, (list, tuple)):
        return []
    return [f for f in fams if isinstance(f, str) and f in FAMILIES]


def bridge_state():
    """Thin wrapper over the eye's bridge-file probe (videoeye._bridge
    - the freshest of the two doorways; missing/broken/empty all read
    None, so a manual trigger may not cost the port a beat). Returns
    the content-space row or None; never raises: the file is the
    extension's word, and its junk is not the app's crime."""
    try:
        return videoeye._bridge(time.monotonic(), time.time())
    except Exception:
        return None


def _fmt(v):
    return str(int(v)) if isinstance(v, (int, float)) else "?"


def _bridge_words(row):
    """A bridge row (or None) as honest words; every key read with a
    default, so a row written by a future extension build raises
    neither the card nor the poll."""
    if not isinstance(row, dict):
        return NO_BRIDGE
    r = row.get("rect") if isinstance(row.get("rect"), dict) else {}
    return "bridge: %sx%s at %s,%s%s" % (
        _fmt(r.get("width")), _fmt(r.get("height")),
        _fmt(r.get("left")), _fmt(r.get("top")),
        " (paused)" if row.get("paused") else "")


def say(cfg):
    """One line of words for the card's say line, from the rail alone
    (the eye's live port words ride videoeye.probe in the card's
    render). Junk config reads as the off words, never an exception;
    off answers before any file is touched - the default-off root
    binds the card too: no reads, nothing."""
    if _vd(cfg).get("on") is not True:
        return "video-dim off - arm it and the click is honored"
    fams = families(cfg)
    tail = ("debug-flag rail on: " + ", ".join(fams)) if fams else \
        "no browser flagged - the bridge click is the only channel"
    return tail + " | " + _bridge_words(bridge_state())


def veil_now(cfg):
    """The card's manual one-shot through the bridge channel ONLY: no
    flag, no CDP, no daemon watching. An explicit click is the user's
    own opt-in for the read, so it stands even while the rail sleeps.
    Reads the file, folds it through the eye's own door (the row
    carries the bounds the extension measured - the anchor order the
    tick's bridge fold uses), and feeds the eye's state freshest-wins
    so the dimmer's NEXT tick frames it: the on-gate and the liveness
    law stay the engine's to apply, re-checked by nobody here.
    Answers the words the card's say line shows: a rect, or
    NO_BRIDGE."""
    row = bridge_state()
    if not isinstance(row, dict):
        return NO_BRIDGE
    fam = row.get("family") if row.get("family") in FAMILIES \
        else FAMILIES[0]
    try:
        door = videoeye._Family(fam)
        door.row = row
        rect = door.rect_px(time.monotonic())
    except Exception:
        return "the bridge file answered junk - no rect to veil"
    if rect is None:
        return "no bridge: the click row carries no placeable rect"
    geo = "rect %sx%s at %s,%s" % (rect[2], rect[3], rect[0], rect[1])
    if _vd(cfg).get("on") is not True:
        return "saw the " + geo + " - the eye is unarmed, no frame " \
                                 "until the switch"
    st = videoeye._STATE.setdefault(fam, videoeye._Family(fam))
    ts = row.get("ts") or time.monotonic()
    if st.row is None or ts >= st.ts:         # freshest wins, the
        st.row, st.ts = row, ts               # tick's own law
    return "bridge " + geo + (" (paused - the eye waits for play)"
                              if row.get("paused")
                              else " - the frame lands next tick")
