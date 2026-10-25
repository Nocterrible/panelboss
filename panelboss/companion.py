"""companion: the video-dim companion's config rail and card words.

The debug-flag route is RETIRED (Oct 15) and now fully REMOVED (Oct 16,
the fixer's v0.3 move): the debug port handed any local process full
CDP, and the launch-with-flag families are a reader for a port that no
longer exists. The replacement is the native-messaging companion
(extension/): the extension measures the video, the local host writes
the app's own doorway file, and the eye (videoeye) reads it. There is
no [videodim].enabled / flag_families rail any more - a stale config
key parses without surprise (the normalizer's own honesty law) but this
module no longer reads those words into a card.

The card (ui/window/_oled.py, the fourth card of the oled tab) uses:
`on` for the switch, `say` for its live words, `veil_now` for the manual
one-shot, and `caps_words` for the capability-discovery line - what the
extension's API CAN send, discovered by nmhost.capabilities() asking the
host directly (the owner's mandate, closed for real Oct 16: the host's
self-description is READ, not assumed).
"""

import os
import time

from . import nmhost, videoeye

# the family keys the extension may stamp - the eye's vocabulary. The
# row's family answer rides the extension's UA tell (OPR/ Edg/ Chrome/),
# and the card reads it the way the eye does: a wall-clock words line,
# never a stored list.
FAMILIES = ("chrome", "edge", "opera_gx")

# the exact words the card's say line answers, each a DISTINCT reason -
# the owner's Oct 16 catch: a stale row shared its words with a
# malformed one, and the absent doorway read like a fault, not an
# installation step. Three reasons, three sentences:
NO_COMPANION = ("the companion's helper is not installed - press install the "
            "helper below (or run extension\\host\\install_host.ps1)")
JUNK_WORDS = "the companion answered junk"


def _no_companion():
    """The absent-doorway sentence is TWO sentences (gate finding 2,
    Oct 16): helper never installed -> point at the BUTTON; helper
    installed but the browser has never spoken -> the id mismatch
    class, point at the OVERRIDE entry (pressing install again would
    just re-pass the same id). The caps line beside these words is
    the reader that distinguishes them, so the card never has to
    guess."""
    if nmhost.host_path() is not None:
        return ("the helper is installed but the browser has never "
                "spoken - if the id on your extensions page differs, "
                "paste it in the id override and press reinstall")
    return NO_COMPANION          # the base sentence itself (the blanket
                             # rewrite had folded THIS one too, and
                             # the function called itself forever -
                             # RecursionError, caught by the suite
                             # before anything else could)
# the staleness horizon: a row older than this reads as "hours old",
# not "live". The eye's grace_s (default 3 s) lifts the veil long
# before; this is the CARD's honest age, sized to the owner's sense of
# "I watched a video yesterday and the card still pretends it is live".
STALE_HORIZON = 3600.0      # s: one hour - past this, "hours old"


def _reason(now):
    """Why the card's say line says what it says, as one of three
    words - absent (no doorway), junk (unreadable), stale (readable but
    older than STALE_HORIZON), fresh (readable and recent). The eye's
    own _read returns None for BOTH absent and junk, so this module
    stats the file itself to tell those apart - a fault must not wear
    an installation story's words."""
    try:
        age = now - os.path.getmtime(videoeye.RECT_PATH)
    except OSError:
        return "absent", None
    row = bridge_state()
    if not isinstance(row, dict):
        return "junk", None
    if age > STALE_HORIZON:
        return "stale", row
    return "fresh", row

# the off words, carrier of the default-off law: off means the eye
# never reads, the click is not honored, and the card says so plainly
OFF_WORDS = "video-dim off - arm it and the click is honored"


def door_dir():
    """The doorway the native host writes (the app's own folder), for
    the card's path line: the fixed %APPDATA%\\PanelBoss\\rect, not a
    browser's download dir. A string, never a surprise - the card
    renders it verbatim."""
    return videoeye.RECT_PATH


def caps_words(force=False):
    """The capability-discovery line, from asking the host directly
    (nmhost.capabilities): what the API CAN send - the ops, the veil
    fields, and whether the companion pushes on its own (the "auto" lane) -
    or the honest not-installed words when host.json is absent. force
    re-asks (the card's explicit re-check). Never raises."""
    caps = nmhost.capabilities(force=force)
    if caps is None:
        return nmhost.NOT_INSTALLED
    return _caps_line(caps)


def _caps_line(caps):
    """Render a capabilities dict (junk welcome) as the honest line.
    GATE 2nd-PASS, finding 2: junk members inside a well-shaped list
    ({"ops":[1,2]}) must not TypeError their way out of a function
    whose docstring promises it never raises - keep strings only."""
    opnames = tuple(x for x in nmhost.ops(caps) if isinstance(x, str))
    fields = tuple(x for x in nmhost.veil_fields(caps)
                   if isinstance(x, str))
    line = "companion API: " + ", ".join(opnames) if opnames else \
        "companion API: (no ops)"
    if isinstance(caps.get("auto"), dict):
        line += ", auto on play"    # the v0.4 lane: the companion pushes
                                     # on its own, no click
    if fields:
        line += " - veil sends " + "/".join(fields)
    return line


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


def _bridge_words(reason, row):
    """A reason word + row as the card's honest say line. Each reason
    is its own sentence - a stale row does not wear a malformed one's
    words, and the absent doorway reads as an installation step, not a
    fault."""
    if reason == "absent":
        return _no_companion()
    if reason == "junk":
        return JUNK_WORDS
    if reason == "stale":
        return ("the last geometry is hours old - play a video or "
                "click the companion")
    if not isinstance(row, dict):
        return _no_companion()   # malformed row WITH a doorway: the same
                             # honest fork (installed? override box.
                             # absent? button.) - the junk words would
                             # blame the payload for a missing one
    r = row.get("rect") if isinstance(row.get("rect"), dict) else {}
    lane = " (auto)" if row.get("lane") == "auto" else ""
    return "companion: %sx%s at %s,%s%s%s" % (
        _fmt(r.get("width")), _fmt(r.get("height")),
        _fmt(r.get("left")), _fmt(r.get("top")),
        " (paused)" if row.get("paused") else "", lane)


def say(cfg):
    """One line of words for the card's say line, from the rail alone.
    Junk config reads as the off words, never an exception; off answers
    before any file is touched - the default-off root binds the card
    too: no reads, nothing. On, the line names the reason: not installed
    (an instruction), junk (a fault), stale (self-healing, plays on the
    next push), or the fresh geometry."""
    if not on(cfg):
        return OFF_WORDS
    reason, row = _reason(time.monotonic())
    return _bridge_words(reason, row)


def veil_now(cfg):
    """The card's manual one-shot through the companion channel ONLY:
    no flag, no CDP, no daemon watching. An explicit click is the
    user's own opt-in for the read, so it stands even while the rail
    sleeps. Reads the file, folds it through the eye's own door (the
    row carries the bounds the extension measured), and feeds the eye's
    state freshest-wins so the dimmer's NEXT tick frames it: the
    on-gate and the liveness law stay the engine's to apply, re-checked
    by nobody here. Answers the words the card's say line shows: a
    rect, or the reason (absent/junk/stale)."""
    reason, row = _reason(time.monotonic())
    if reason == "absent":
        return _no_companion()
    if reason == "junk":
        return JUNK_WORDS
    if reason == "stale":
        return ("the last geometry is hours old - play a video or "
                "click the companion")
    if not isinstance(row, dict):
        return _no_companion()   # malformed row WITH a doorway: the same
                             # honest fork (installed? override box.
                             # absent? button.) - the junk words would
                             # blame the payload for a missing one
    fam = row.get("family") if row.get("family") in FAMILIES \
        else FAMILIES[0]
    rect = videoeye._rect_px(row)
    if rect is None:
        return "the companion's row carries no placeable rect"
    geo = "rect %sx%s at %s,%s" % (rect[2], rect[3], rect[0], rect[1])
    if not on(cfg):
        return "saw the " + geo + " - the eye is unarmed, no frame " \
                                 "until the switch"
    st = videoeye._STATE.setdefault(fam, {"row": None, "ts": 0.0})
    ts = row.get("ts") or time.monotonic()
    if st["row"] is None or ts >= st["ts"]:     # freshest wins, the
        st["row"], st["ts"] = row, ts           # tick's own law
    if not row.get("paused") and not videoeye._on_desktop(rect):
        return "companion " + geo + " - but the picture is OFF the " \
               "desk (a hidden or minimized tab); the visible-picture " \
               "law will hold the theater shut"    # the promise is
        #               gated with the gate (Oct 19 gate round): a
        #               click-test on a ghost must confess the ghost,
        #               not promise a frame the eye will veto
    return "companion " + geo + (" (paused - the eye waits for play)"
                                  if row.get("paused")
                                  else " - the frame lands next tick")