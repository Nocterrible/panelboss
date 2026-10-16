"""companion: the video-dim companion's config rail and card words.

The debug-flag route is RETIRED (Oct 15) and now fully REMOVED (Oct 16,
the fixer's v0.3 move): the debug port handed any local process full
CDP, and the launch-with-flag families are a reader for a port that no
longer exists. The replacement is the native-messaging companion
(extension/): the extension measures the video, the local host writes
the app's own doorway file, and the eye (videoeye) reads it. There is
no [videodim].enabled / flag_families rail any more - a stale config
key parses without surprise (the normalizer's own honesty law) but this
module no longer reads those words into a card. The card's live words
now answer from what the extension's API CAN send (capability
discovery), not what a flagged browser used to mean.

The card (ui/window/_oled.py, the fourth card of the oled tab) uses:
`on` for the switch, `say` for its live words, and `veil_now` for the
manual one-shot. No watchdog, no relaunch logic - the rail is the
owner's word, and the loop thread answers it.
"""

import time

from . import videoeye

# the family keys the extension may stamp - the eye's vocabulary. The
# row's family answer rides the extension's UA tell (OPR/ Edg/ Chrome/),
# and the card reads it the way the eye does: a wall-clock words line,
# never a stored list.
FAMILIES = ("chrome", "edge", "opera_gx")

# the exact no-bridge words (the button's and the say line's): pinned
# by scripts/companion_test.py so they never drift under the card
NO_BRIDGE = ("no companion click yet - the buddy's icon writes it "
             "on click")

# the off words, carrier of the default-off law: off means the eye
# never reads, the click is not honored, and the card says so plainly
OFF_WORDS = "video-dim off - arm it and the click is honored"


def door_dir():
    """The doorway the native host writes (the app's own folder), for
    the card's path line: the fixed %APPDATA%\\PanelBoss\\rect, not a
    browser's download dir. A string, never a surprise - the card
    renders it verbatim."""
    return videoeye.RECT_PATH


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


def on(cfg):
    """The feature's consent key: [videodim] on. Strict like the
    normalizer: only True is on, junk is off."""
    return _vd(cfg).get("on") is True


def bridge_state():
    """Thin wrapper over the eye's doorway probe (videoeye._read - the
    app's own rect file). Returns the content-space row or None; never
    raises: the file is the extension's word, and its junk is not the
    app's crime."""
    try:
        return videoeye._read(time.monotonic(), time.time())
    except Exception:
        return None


def _fmt(v):
    return str(int(v)) if isinstance(v, (int, float)) else "?"


def _bridge_words(row):
    """A row (or None) as honest words; every key read with a default,
    so a row written by a future extension build raises neither the
    card nor the poll."""
    if not isinstance(row, dict):
        return NO_BRIDGE
    r = row.get("rect") if isinstance(row.get("rect"), dict) else {}
    return "companion: %sx%s at %s,%s%s" % (
        _fmt(r.get("width")), _fmt(r.get("height")),
        _fmt(r.get("left")), _fmt(r.get("top")),
        " (paused)" if row.get("paused") else "")


def say(cfg):
    """One line of words for the card's say line, from the rail alone.
    Junk config reads as the off words, never an exception; off answers
    before any file is touched - the default-off root binds the card
    too: no reads, nothing."""
    if not on(cfg):
        return OFF_WORDS
    return _bridge_words(bridge_state())


def veil_now(cfg):
    """The card's manual one-shot through the companion channel ONLY:
    no flag, no CDP, no daemon watching. An explicit click is the
    user's own opt-in for the read, so it stands even while the rail
    sleeps. Reads the file, folds it through the eye's own door (the
    row carries the bounds the extension measured), and feeds the eye's
    state freshest-wins so the dimmer's NEXT tick frames it: the
    on-gate and the liveness law stay the engine's to apply, re-checked
    by nobody here. Answers the words the card's say line shows: a
    rect, or NO_BRIDGE."""
    row = bridge_state()
    if not isinstance(row, dict):
        return NO_BRIDGE
    fam = row.get("family") if row.get("family") in FAMILIES \
        else FAMILIES[0]
    rect = videoeye._rect_px(row)
    if rect is None:
        return "the companion answered junk - no rect to veil"
    geo = "rect %sx%s at %s,%s" % (rect[2], rect[3], rect[0], rect[1])
    if not on(cfg):
        return "saw the " + geo + " - the eye is unarmed, no frame " \
                                 "until the switch"
    st = videoeye._STATE.setdefault(fam, {"row": None, "ts": 0.0})
    ts = row.get("ts") or time.monotonic()
    if st["row"] is None or ts >= st["ts"]:     # freshest wins, the
        st["row"], st["ts"] = row, ts           # tick's own law
    return "companion " + geo + (" (paused - the eye waits for play)"
                                  if row.get("paused")
                                  else " - the frame lands next tick")