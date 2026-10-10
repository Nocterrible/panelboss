"""power plans by the book of powercfg, no admin needed to swap.

The gaming watcher's second pair of hands: a game wants the high
performance plan and nobody wants it babysitting the desk the rest
of the day. This module only reads and swaps plans; remembering what
was active BEFORE the swap is the caller's job (we return the plan
we replaced, so a game ending restores the user's choice, never our
guess of what it was).

Fail open everywhere: no powercfg, weird locale, a plan that
vanished mid-session - reads answer None/[], swaps answer False.
"""
import logging
import re
import subprocess

log = logging.getLogger("power_plan")

# "Power Scheme GUID: 2e1a3068-f423-8055-...-..." - the GUID shape
# is locale-proof, the words around it are not (powercfg speaks the
# user's UI language).
GUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}",
                  re.IGNORECASE)
CREATE_NO_WINDOW = 0x08000000


def _run(args):
    try:
        p = subprocess.run(["powercfg"] + args,
                           capture_output=True, timeout=10,
                           creationflags=CREATE_NO_WINDOW)
        raw = p.stdout or b""
        if raw[:2] in (b"P\x00", b"\xff\xfe"):
            return raw.decode("utf-16", "ignore")
        return raw.decode("oem", "ignore")   # powercfg speaks the
                                             # console's codepage
    except Exception:
        log.debug("powercfg %s failed", args, exc_info=True)
        return ""


def plans():
    """[{guid, name}] as powercfg lists them (name stays in the
    user's language; guid is the only stable handle). Entries come
    as "Power Scheme <guid> (<name>)" in English; localized builds
    lose the words, never the guid - name falls back to the line
    above the guid line, where several locales put it."""
    lines = _run(["/list"]).splitlines()
    found, seen = [], set()
    for i, line in enumerate(lines):
        m = GUID.search(line)
        if not m or m.group(0).lower() in seen:
            continue
        seen.add(m.group(0).lower())
        name = ""
        p, q = line.find("("), line.rfind(")")
        if 0 <= p < q:
            name = line[p + 1:q].strip()
        elif i and lines[i - 1].strip():
            name = lines[i - 1].strip()
        found.append({"guid": m.group(0), "name": name})
    return found


def active():
    """The guid now in force (cased as powercfg prints it), or None."""
    m = GUID.search(_run(["/getactivescheme"]))
    return m.group(0) if m else None


def set_plan(guid):
    """Swap and verify: believe /getactivescheme, not silence. Case
    is the caller's accident, not a difference."""
    if not guid:
        return False
    _run(["/setactive", guid])
    now = active()
    if not now or now.lower() != guid.lower():
        log.info("power plan: asked %s, powercfg says %s", guid, now)
        return False
    return True


def pick(plans_list, want):
    """Resolve a user's wish ("high performance", a fragment, or a
    bare guid) against the enumerated list; '' when nothing fits -
    guessing across localized plan names is how a laptop ends up in
    Battery Saver mid-game."""
    if not want:
        return ""
    raw = want.strip()
    if GUID.fullmatch(raw):           # a bare guid is the answer,
        return raw                    # whatever case it arrived in
    want = raw.lower()
    for p in plans_list:
        if want in p["name"].lower():
            return p["guid"]
    return ""
