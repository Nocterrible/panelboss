"""Named desktops: the manual lever, where wm.py is the nightly one.

A profile is the whole desk spelled out - which physical monitors
(EDID identity, never a \\.\DISPLAYn slot) are on, where they sit,
which is primary, their mode and rate, the HDR ask, and the windows
that belong on it. Applying one changes all of that and then
verifies it, because the C# project this is stolen from measured
that Windows reports success BEFORE the modes have settled; the
poll until the live fingerprint equals the profile's target is that
lesson written down.

The one honest blocker is physical: the panels the profile names
have to be plugged in. Modes can be asked for, positions can be
asked for, a missing monitor cannot. A mismatch therefore refuses
with a sentence and offers the best-effort route (apply what
exists, then rescue).

HDR is a keypress with a belief: there is no API reachable here
that reads HDR back (the C# project's conclusion, unchanged), so
the app sends win+alt+b (configurable, the hotkey has moved between
Windows versions) only when its stored belief disagrees with the
profile, flips the belief, and never claims to know.
"""

import json
import logging
import os
import time

from . import config, wm

log = logging.getLogger("profiles")

NEW = "create new..."
MATCH_MODES = ("process", "process + title", "title")
HDR_ASKS = ("leave alone", "on", "off", "toggle")


# ---------------------------------------------------------------- store --
# The file lives in %APPDATA%: the user's own turf, always editable
# by hand, and the app must survive both bad luck (crash mid-write)
# and bad edits. Two rules: writes are atomic (temp file, then
# os.replace - a half-written profiles.json cannot exist), and a
# file that will not parse is MOVED ASIDE (.corrupt, timestamped)
# before the fresh start - because the next save would otherwise
# quietly swallow the wreckage the user may still want to fix.
def path(dir=None):
    return config.find_config(dir or config.CONFIG_DIR,
                              "profiles.json")


def _quarantine(p):
    try:
        bad = "%s.corrupt-%d" % (p, time.time())
        os.replace(p, bad)
        log.warning("unparsable %s kept aside as %s", p, bad)
    except OSError:
        log.exception("could not move %s aside", p)


def load(dir=None):
    data = {"hdr_key": "win+alt+b", "hdr_now": "unknown",
            "last": {}, "profiles": {}}
    p = path(dir)
    try:
        with open(p, encoding="utf-8") as fh:
            got = json.load(fh)
    except FileNotFoundError:
        got = None                         # absent is not broken
    except (OSError, ValueError):
        _quarantine(p)
        got = None
    if isinstance(got, dict):
        data.update(got)
    for key in ("last", "profiles"):       # never trust a half file
        if not isinstance(data.get(key), dict):
            data[key] = {}
    if not isinstance(data.get("hdr_key"), str) or \
            not data["hdr_key"].strip():
        data["hdr_key"] = "win+alt+b"
    for name, prof in list(data["profiles"].items()):
        if not isinstance(prof, dict) or \
                not isinstance(prof.get("displays"), list) or \
                not isinstance(prof.get("wins"), list):
            del data["profiles"][name]     # one rotted row does not
            log.warning("dropped rotted profile '%s'", name)
    return data


def save(data, dir=None):
    p = path(dir)
    try:
        with open(p + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
        os.replace(p + ".tmp", p)          # atomic on the same volume
        return True
    except OSError:
        log.exception("profiles could not be written")
        return False


# ------------------------------------------------------------ capture ---
def target_fp(displays):
    """The fingerprint the desk SHOULD answer with once the profile
    is applied - the verification target (and what create records)."""
    on = [d for d in displays if d.get("on", True)]
    return "|".join(sorted(
        "%s@%d,%d %dx%d%s" % (d["id"], d["x"], d["y"], d["w"], d["h"],
                              "P" if d.get("primary") else "")
        for d in on))


def capture():
    """Everything the desk is right now, in profile words."""
    displays = []
    for m in wm.monitors():
        displays.append({"id": m["id"], "short": m["short"],
                         "gdi": m["gdi"], "on": True,
                         "primary": m["primary"], "x": m["x"],
                         "y": m["y"], "w": m["w"], "h": m["h"],
                         "rate": m["rate"], "bits": m["bits"]})
    return displays


def windows_now():
    """The open windows a profile may pin, tagged with the monitor
    each one sits on."""
    mons = wm.monitors()
    out = []
    for w in wm.list_windows():
        mon = ""
        cx = w["rect"][0] + w["rect"][2] // 2
        cy = w["rect"][1] + w["rect"][3] // 2
        for m in mons:
            if (m["x"] <= cx < m["x"] + m["w"]
                    and m["y"] <= cy < m["y"] + m["h"]):
                mon = m["short"]
                break
        out.append({"proc": w["proc"], "title": w["title"],
                    "rect": list(w["rect"]), "zoomed": w["zoomed"],
                    "monitor": mon})
    return out


def create(data, name, hdr="leave alone", match="process + title",
           dir=None):
    prof = {"fp": wm.fingerprint(), "created": time.time(),
            "used": time.time(), "match": match, "hdr": hdr,
            "displays": capture(), "wins": []}
    data.setdefault("profiles", {})[name] = prof
    data.setdefault("last", {})[prof["fp"]] = name
    save(data, dir)
    log.info("profile '%s' captured: %d monitor(s)", name,
             len(prof["displays"]))
    return prof


# --------------------------------------------------------------- pins ---
def pin(data, name, win, dir=None):
    """Tick the box: the window's placement RIGHT NOW becomes the
    profile's truth for that process + title."""
    prof = data["profiles"][name]
    prof["wins"] = [w for w in prof["wins"]
                    if (w["proc"], w["title"]) != (win["proc"],
                                                   win["title"])]
    prof["wins"].append({k: win[k] for k in
                         ("proc", "title", "rect", "zoomed",
                          "monitor")})
    save(data, dir)


def unpin(data, name, proc, title, dir=None):
    prof = data["profiles"][name]
    prof["wins"] = [w for w in prof["wins"]
                    if (w["proc"], w["title"]) != (proc, title)]
    save(data, dir)


# ------------------------------------------------------------- picker ---
def default_name(data, fp):
    """The picker's opening answer: the profile last used for THIS
    exact desk, else create-new."""
    hit = [n for n, p in data["profiles"].items()
           if p.get("fp") == fp]
    if not hit:
        return None
    hit.sort(key=lambda n: data["profiles"][n].get("used", 0))
    return hit[-1]


# ----------------------------------------------------------- matching ---
def pair(saved, live, mode):
    """Pure decision (testable): which open window answers to which
    saved placement. The mode is the user's choice because both
    answers have a failure mode: process-only may drag an unrelated
    new window into an old one's place, title-only misses the
    browser window that renamed itself - and 'process + title'
    misses exactly THAT, which is why the menu exists. Within a
    mode, exact agreement wins first, then order; open windows that
    answer no pin are left exactly where they are (the profile
    never shoves a window it never pinned)."""
    mode = (mode or "").lower()
    same_proc = lambda s, l: (s["proc"] or "").lower() == \
        (l["proc"] or "").lower()
    same_title = lambda s, l: (s["title"] or "") == (l["title"] or "")
    pairs, used = [], set()

    def take(pred):
        for s in saved:
            if any(s is ps for ps, _ in pairs):
                continue
            for i, l in enumerate(live):
                if i not in used and pred(s, l):
                    used.add(i)
                    pairs.append((s, l))
                    break

    if mode == "title":
        take(same_title)
    elif mode == "process":
        take(lambda s, l: same_proc(s, l) and same_title(s, l))
        take(same_proc)                      # the renamed tab still
    else:                                    # belongs in its seat
        take(lambda s, l: same_proc(s, l) and same_title(s, l))
    return pairs


# -------------------------------------------------------------- HDR ----
def hdr_action(want, believed):
    """Pure belief dance (testable): press or don't, and what the
    belief becomes after the press. 'unknown' presses and adopts
    the wanted answer loudly; a press always FLIPS the belief -
    the app sends a toggle, not a command."""
    if want == "leave alone" or want == "skip":
        return None, believed
    if want == "toggle":
        return "press", ("on" if believed != "on" else "off")
    on = want == "on"
    believed_on = believed in ("on", "true")
    if believed == "unknown":
        return "press", ("on" if on else "off")
    if believed_on != on:
        return "press", ("on" if on else "off")
    return None, believed


# ------------------------------------------------------------- apply ---
def desk_mismatch(prof, mons):
    """The blocker, and nothing else: the physical panels. Returns
    the honest sentence, or '' when the identity sets agree."""
    want = {d["id"] for d in prof["displays"]}
    have = {m["id"] for m in mons}
    missing = want - have
    extra = have - want
    short = {d["id"]: d.get("short", "?") for d in prof["displays"]}
    names = lambda ids: ", ".join(
        short.get(i, i[:24]) for i in sorted(ids))
    if not missing and not extra:
        return ""
    bits = []
    if missing:
        bits.append("not plugged in: %s" % names(missing))
    if extra:
        bits.append("not in the profile: %s" % names(extra))
    return "; ".join(bits)


def apply(data, name, best_effort=False, dir=None):
    """The whole lever. Order and paranoia stolen from
    monitor_control (enable pass, primary last, disable pass, one
    commit, skip-what-is-right so a self-apply never blinks;
    verify-by-fingerprint after, because success is reported before
    the modes land; rescue at the end for whatever the shuffle
    stranded). Returns (ok, sentence)."""
    prof = data["profiles"].get(name)
    if prof is None:
        return False, "no such profile"
    mons = wm.monitors()
    say = []
    gate = desk_mismatch(prof, mons)
    if gate and not best_effort:
        return False, "different desk right now (%s)" % gate
    if gate:
        say.append("best effort over: %s" % gate)

    # 1+2. topology and modes in one DEVMODE pass (entries already
    # carry mode/position; the modes ride the same call the switcher
    # proved on this machine)
    entries = []
    by_id = {m["id"]: m for m in mons}
    for d in prof["displays"]:
        cur = by_id.get(d["id"])
        if cur is None:
            continue                       # the missing panel: asked
        e = dict(d)                        # of nothing, said once
        e["gdi"] = cur["gdi"]              # (slot names may have
        entries.append(e)                  # shuffled since capture)
    if entries:
        ok, lines = wm.apply_layout(entries)
        for t in lines:
            log.info("apply '%s': %s", name, t)
        if not ok:
            return False, ("layout refused: " + "; ".join(lines[-1:]))

    # 3. the belief dance
    want, believed = hdr_action(prof.get("hdr", "leave alone"),
                                data.get("hdr_now", "unknown"))
    if want == "press":
        trouble = wm.press_keys(data.get("hdr_key", "win+alt+b"))
        data["hdr_now"] = believed
        say.append(trouble or ("pressed %s for hdr (now believed %s)"
                               % (data.get("hdr_key"), believed)))
        save(data, dir)

    # 4. verify: poll until the desk answers with the profile's
    # fingerprint, quiet-for-2s so the relay storm has passed. A
    # best-effort apply onto a smaller desk can NEVER equal the
    # target - there it settles on any stable fingerprint and moves
    # windows anyway, because "placed on what exists" is the deal
    # the user bought with the try-anyway button.
    target = prof["fp"]
    matched = best_done = False
    last = quiet = None
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        fp = wm.fingerprint()
        now = time.monotonic()
        if fp != last:
            last, quiet = fp, now
        elif now - quiet >= 2:
            matched = fp == target
            best_done = best_effort and fp != target
            break
        time.sleep(0.5)
    if best_done:
        say.append("the desk never matched the profile (it answers "
                   "%s) - windows placed on what is here" % last)
    elif not matched:
        say.append("the desk never answered as the profile asked "
                   "(still: %s)" % (last or "nothing settled"))

    # 5. windows, only against a settled desk they were pinned for
    if matched or best_done:
        live = wm.list_windows()
        pairs = pair(prof["wins"], live, prof.get("match"))
        moved = sum(1 for s, l in pairs
                    if wm.place(l["hwnd"], tuple(s["rect"]),
                                s.get("zoomed")) == "ok")
        say.append("windows: %d placed, %d not open or refused"
                   % (moved, len(prof["wins"]) - moved))
        rescued = wm.rescue_lost()
        if rescued:
            say.append("rescued: %s" % ", ".join(rescued)[:120])
    else:
        say.append("windows untouched")

    prof["used"] = time.time()
    data["last"][target] = name
    save(data, dir)
    return matched or best_done, " ; ".join(say) if say else \
        "applied: %s" % (" + ".join(d["short"] for d in
                                prof["displays"] if d.get("on", True)))
