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

HDR is a read, then a command: on Windows 11 24H2+ the DisplayConfig
API (wm.hdr_states / wm.hdr_set) answers per monitor what HDR IS and
accepts a direct SET - no hotkey, no guessing. The app reads first,
commands only the monitors that disagree with the profile, then
reads back until the answer arrives. The keypress-with-belief dance
(win+alt+b, stored hdr_now) survives only as the fallback for older
Windows, whose single readable API conflates HDR with wide-gamut
colour and measurably lies: on this desk it answers
"supported+enabled" for a panel that cannot do HDR at all.
"""

import json
import logging
import os
import threading
import time

from . import config, wm

log = logging.getLogger("profiles")

NEW = "create new..."
MATCH_MODES = ("process", "process + title", "title")
HDR_ASKS = ("snap", "leave alone", "on", "off", "toggle")


# ---------------------------------------------------------------- store --
# The file lives in %APPDATA%: the user's own turf, always editable
# by hand, and the app must survive both bad luck (crash mid-write)
# and bad edits. Two rules: writes are atomic (temp file, then
# os.replace - a half-written profiles.json cannot exist), and a
# file that will not parse is MOVED ASIDE (.corrupt, timestamped)
# before the fresh start - because the next save would otherwise
# quietly swallow the wreckage the user may still want to fix.
# Login is a storm: explorer is still wiring itself together, every
# other autostart entry is thrashing the disk, panels are mid-
# renegotiation. A restore fired into that storm gets built-in
# grace: the FIRST login sits out the full calibration below before
# launching anything, and times every app that shows up; later
# logins wait only the slowest observed boot + LOGIN_BUFFER (the
# times are kept per app in profiles.json's "login" record).
# Every "open it" wait at login is EXTENDED by LOGIN_PATIENCE on
# top of the pin's own number (login stretches patience, it never
# shrinks it).
LOGIN_DELAY = 30.0          # the floor: never less, metric or not
LOGIN_CALIBRATION = 120.0   # the first login: two full minutes
LOGIN_BUFFER = 20           # the safety margin on learned times
LOGIN_CAP = 600             # even a nightmare boot cannot stall past 10 min
LOGIN_PATIENCE = 60


def launch_delay(data):
    """How long a login restore sits out before LAUNCHING anything.
    First login: the whole calibration - we do not yet know this
    machine. Afterwards: the slowest boot ever observed + buffer,
    floored and capped. Apparent slowness is timed from OUR launch
    moment, never from the restore start - counting our own wait
    as the app's slowness would make every login grow one buffer
    longer than the last."""
    took = (data.get("login") or {}).get("max")
    try:
        took = float(took)
    except (TypeError, ValueError):
        took = 0.0
    if took <= 0:
        return LOGIN_CALIBRATION
    return max(LOGIN_DELAY, min(LOGIN_CAP, took + LOGIN_BUFFER))


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
            continue
        # hand-edited junk rows die HERE, before layout+HDR are
        # committed (audit: a string row passed load, apply died after
        # the commit, with no rollback note) - drop the row, keep the
        # profile
        for i, d in enumerate(prof["displays"]):
            if not isinstance(d, dict) or not d.get("id"):
                log.warning("profile '%s': dropped junk displays row "
                            "at index %d (needs a dict with 'id')",
                            name, i)
                prof["displays"][i] = None
        prof["displays"] = [d for d in prof["displays"]
                            if d is not None]
        for i, w in enumerate(prof["wins"]):
            if not isinstance(w, dict) or not w.get("proc") or \
                    "title" not in w or not w.get("rect"):
                log.warning("profile '%s': dropped junk wins row "
                            "at index %d (needs a dict with 'proc', "
                            "'title' and 'rect')", name, i)
                prof["wins"][i] = None
        prof["wins"] = [w for w in prof["wins"] if w is not None]
    lg = data.get("login")                  # the "last" validation
    if lg is not None and not isinstance(lg, dict):   # pattern, aimed
        log.warning("dropped rotted 'login' section (not a dict)")   # at the
        del data["login"]                   # login record
    else:
        if isinstance(lg, dict):
            # REAL shapes (writer at apply: took[who] = ...): 'took' is
            # the per-app dict of launch seconds, 'launch_delay' a
            # scalar. The first cut float()ed BOTH, which dropped the
            # legitimate dict on every load - validation may only
            # reject the rotted shape, never the real one (architect
            # fix on the lane's honest deviation flag).
            if "took" in lg and not isinstance(lg["took"], dict):
                log.warning("dropped rotted login 'took' (not a dict): %r",
                            lg["took"])
                del lg["took"]
            if "launch_delay" in lg:
                try:
                    lg["launch_delay"] = float(lg["launch_delay"])
                except (TypeError, ValueError):
                    log.warning("dropped unparsable login 'launch_delay':"
                                " %r", lg["launch_delay"])
                    del lg["launch_delay"]
    return data


# one lock: save() runs from the apply worker thread AND the UI main
# thread writing one file (audit: single-writer the tmp+replace window)
_SAVE_LOCK = threading.Lock()


def save(data, dir=None):
    p = path(dir)
    try:
        with _SAVE_LOCK:
            with open(p + ".tmp", "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=1)
            os.replace(p + ".tmp", p)      # atomic on the same volume
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
    caps, states = {}, {}
    try:
        rows = wm.hdr_states()
        caps = {r["gdi"]: bool(r["supported"]) for r in rows}
        # the state snapshot the "restore the captured state" ask
        # aims back at: only a readable on/off is worth remembering
        # (an unreadable "unknown" would restore a guess)
        states = {r["gdi"]: r["state"] for r in rows
                  if r.get("supported") and r.get("state") in
                  ("on", "off")}
    except Exception:
        pass                           # capability is garnish, never
    displays = []                      # a blocker
    for m in wm.monitors():
        displays.append({"id": m["id"], "short": m["short"],
                         "gdi": m["gdi"], "on": True,
                         "primary": m["primary"], "x": m["x"],
                         "y": m["y"], "w": m["w"], "h": m["h"],
                         "rate": m["rate"], "bits": m["bits"],
                         "hdr_cap": caps.get(m["gdi"]),
                         "hdr_state": states.get(m["gdi"])})
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
                    "exe": w.get("exe") or "",
                    "rect": list(w["rect"]), "zoomed": w["zoomed"],
                    "monitor": mon})
    return out


def create(data, name, hdr="snap", match="process + title", dir=None):
    prof = {"fp": wm.fingerprint(), "created": time.time(),
            "used": time.time(), "match": match, "hdr": hdr,
            "displays": capture(), "wins": []}
    data.setdefault("profiles", {})[name] = prof
    data.setdefault("last", {})[prof["fp"]] = name
    save(data, dir)
    log.info("profile '%s' captured: %d monitor(s)", name,
             len(prof["displays"]))
    return prof


# --------------------------------------------------- manual mode edits ---
# capture() freezes the desk's CURRENT modes; these are how a user
# says "this profile, but 4K@144 here and 1080p@60 there", or builds
# a profile from nothing. Validation leans on the driver's own
# offered list (wm.offered_modes, same law set_mode enforces at
# apply time) when the monitor is connected - and says so out loud
# when it is not.

def live_modes():
    """monitor id -> ["WxH@Hz", ...] offered on the LIVE desk; the
    editor's dropdowns are made of exactly this, so a user cannot
    ask for a mode the panel will not take."""
    out = {}
    try:
        for m in wm.monitors():
            try:
                out[m["id"]] = wm.offered_modes(m["gdi"])
            except Exception:
                pass
    except Exception:
        pass
    return out


def _prof(data, name):
    return (data.get("profiles") or {}).get(name)


def set_display_mode(data, name, monitor_id, w, h, rate, dir=None):
    """Edit one saved monitor's mode inside a profile. rate must be
    a real number: the offered list is spelled WxH@Hz and a mode
    without one is a wish, not a plan. Returns (ok, note)."""
    prof = _prof(data, name)
    if prof is None:
        return False, "no profile '%s'" % name
    row = next((d for d in prof.get("displays") or []
                if d.get("id") == monitor_id), None)
    if row is None:
        return False, "%s is not in '%s'" % (monitor_id, name)
    try:
        w, h, rate = int(w), int(h), int(rate)
    except (TypeError, ValueError):
        return False, "w/h/rate must be numbers"
    if w <= 0 or h <= 0 or rate <= 0:
        return False, "w/h/rate must be positive"
    want = "%dx%d@%d" % (w, h, rate)
    note = ""
    offered = None
    try:
        live = {m["id"]: m["gdi"] for m in wm.monitors()}
        if monitor_id in live:
            offered = wm.offered_modes(live[monitor_id])
    except Exception:
        log.debug("mode check blind for %s", monitor_id, exc_info=True)
        offered = None
    if offered is not None:
        if want not in offered:
            return False, "%s is not on the offered list for %s" % (
                want, row.get("short") or monitor_id)
    else:
        # offline panel OR a driver that will not answer: either way
        # we cannot verify, and a raise here would break the (ok,
        # note) contract the UI is built on
        note = "%s unreachable: %s saved UNVERIFIED" % (
            row.get("short") or monitor_id, want)
    row["w"], row["h"], row["rate"] = w, h, rate
    save(data, dir)
    log.info("profile '%s': %s -> %s%s", name,
             row.get("short") or monitor_id, want,
             " (" + note + ")" if note else "")
    return True, note


def blank(data, name, dir=None):
    """A profile that starts with nothing; add_display pulls live
    monitors in one at a time. apply_layout refuses "no monitor
    would stay on", so a truly blank one saves but does not
    apply - the editor says so."""
    profs = data.setdefault("profiles", {})
    if name in profs:
        return False, "'%s' already exists" % name
    profs[name] = {"fp": "manual:" + name, "created": time.time(),
                   "used": time.time(), "match": "process",
                   "hdr": "snap", "displays": [], "wins": []}
    save(data, dir)
    return True, ""


def add_display(data, name, monitor_id, dir=None):
    """Add a LIVE monitor to a profile, seeded with its current
    mode and a seat stacked right of the last row (first row owns
    primacy); set_display_mode fixes the details."""
    prof = _prof(data, name)
    if prof is None:
        return False, "no profile '%s'" % name
    if any(d.get("id") == monitor_id
           for d in prof.get("displays") or []):
        return False, "%s is already in '%s'" % (monitor_id, name)
    row = next((d for d in capture() if d["id"] == monitor_id), None)
    if row is None:
        return False, "%s is not on the live desk" % monitor_id
    mons = prof.setdefault("displays", [])
    row["x"] = sum(int(d.get("w") or 0) for d in mons)
    row["y"] = 0
    row["primary"] = not mons
    mons.append(row)
    save(data, dir)
    return True, ""


def drop_display(data, name, monitor_id, dir=None):
    """Forget one monitor of a profile (the desk it describes can
    still come back; the row is re-addable)."""
    prof = _prof(data, name)
    if prof is None:
        return False, "no profile '%s'" % name
    before = prof.get("displays") or []
    prof["displays"] = [d for d in before
                        if d.get("id") != monitor_id]
    if len(prof["displays"]) == len(before):
        return False, "%s is not in '%s'" % (monitor_id, name)
    # promote a successor ONLY when the row we dropped owned primacy:
    # a profile that never had one must not silently grow one (the
    # user's data is the user's).
    if any(d.get("primary") for d in before
           if d.get("id") == monitor_id) \
            and prof["displays"] \
            and not any(d.get("primary") for d in prof["displays"]):
        prof["displays"][0]["primary"] = True
    save(data, dir)
    return True, ""


# --------------------------------------------------------------- pins ---
# A pin is per APP, not per window: the identity is the process, the
# title is only a hint for matching and for the human reading the
# list. The choice of how strictly a saved seat recognises its
# window lives on the pin, because only the user knows which of
# their apps rename themselves a hundred times a day (a browser
# window pinned by title died the moment a tab was clicked).
def pin(data, name, win, match="process + title", open_if_missing=False,
        exe=None, wait=None, dir=None):
    """Pin it: the window's placement RIGHT NOW becomes the
    profile's truth for that app. `open_if_missing` is the wish to
    re-run the exe when no window answers - naive by design (a bare
    shell-execute; store apps and stub launchers start nothing this
    way), so the UI says so before saving it, and offers `exe` to
    outsmart that: the user can point the pin at a launcher or the
    right binary when the auto-captured one starts nothing. `wait`
    is how long to trust the wish before calling it a miss. The exe
    path is captured while the window is alive, because afterwards
    nobody knows where it was installed. Returns (ok, note) like the
    other profile primitives: a dead selection (create-new, or a name
    the store no longer holds) is confessed, never a silent KeyError
    the event loop would swallow behind a button click."""
    prof = (data.get("profiles") or {}).get(name)
    if prof is None:
        return False, "no profile '%s'" % name
    prof["wins"] = [w for w in prof["wins"]
                    if (w["proc"], w["title"]) != (win["proc"],
                                                   win["title"])]
    try:
        seconds = int(wait or 30)
    except (TypeError, ValueError):
        seconds = 30
    prof["wins"].append({"proc": win["proc"], "title": win["title"],
                         "rect": list(win["rect"]),
                         "zoomed": bool(win.get("zoomed")),
                         "monitor": win.get("monitor") or "",
                         "exe": (exe if exe is not None
                                 else win.get("exe")) or "",
                         "match": match,
                         "open": bool(open_if_missing),
                         "wait": max(5, min(600, seconds))})
    save(data, dir)
    return True, ""


def unpin(data, name, proc, title, dir=None):
    """Forget a seat. Returns (ok, note) like pin: a dead selection
    confesses instead of KeyError-ing out of the button's callback."""
    prof = (data.get("profiles") or {}).get(name)
    if prof is None:
        return False, "no profile '%s'" % name
    prof["wins"] = [w for w in prof["wins"]
                    if (w["proc"], w["title"]) != (proc, title)]
    save(data, dir)
    return True, ""


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


def name_for_desk(data, mons):
    """The login picker's answer for "the one this desk last used",
    judged by PANEL IDENTITY (desk_mismatch - the same view an apply
    takes), not by the exact fingerprint: a cold boot may not have
    reached the profile's modes yet, and the fingerprint would then
    hide the profile that fits."""
    hits = [n for n, p in data["profiles"].items()
            if p.get("displays") and not desk_mismatch(p, mons)]
    hits.sort(key=lambda n: data["profiles"][n].get("used", 0))
    return hits[-1] if hits else None


# ----------------------------------------------------------- matching ---
def pin_hits(row, live, taken, fallback="process"):
    """Pure decision (testable): which open windows answer to one
    saved seat. A 'process' pin moves EVERY window of that app -
    the UI warns before saving such a pin, because it is a choice,
    not an accident. 'title' is the gentle version and misses the
    browser tab that renamed itself; 'process + title' matches
    exactly the one window it was pinned from. Earlier pins answer
    first (save order): `taken` holds the hwnds already claimed, so
    no window is shoved twice, and windows no pin speaks to are
    left exactly where they are."""
    mode = (row.get("match") or fallback or "process").lower()
    proc = (row.get("proc") or "").lower()
    title = row.get("title") or ""
    out = []
    for l in live:
        if l["hwnd"] in taken:
            continue
        lp = (l.get("proc") or "").lower()
        lt = l.get("title") or ""
        if mode == "process + title":
            hit = bool(proc) and lp == proc and lt == title
        elif mode == "title":
            hit = bool(title) and lt == title
        else:                                    # "process"
            hit = bool(proc) and lp == proc
        if hit:
            out.append(l)
    if mode == "process":
        # splash theft (audit): a process pin first-launches into the
        # app's splash, which then parks AT the main seat while the
        # real window sits unplaced - no_shows comes up empty and the
        # loss is never reported. Prefer a window that is not splash
        # sized (< 200x150) whenever one exists for this pin; when
        # only small windows exist, the old behavior stands.
        if out and any(len(l.get("rect") or []) >= 2 and
                       l["rect"][2] < 200 and l["rect"][3] < 150
                       for l in out):
            big = [l for l in out
                   if not (len(l.get("rect") or []) >= 2
                           and l["rect"][2] < 200 and
                           l["rect"][3] < 150)]
            if big:
                out = big
    return out


def relaunch(row, taken, fallback, extra=0):
    """The naive re-open: run the exe the pin saved, then wait for
    a window that answers the pin - as long as the pin's own `wait`
    says (the slider the user set, default 30 s; slow machines and
    patient people get to choose) - and move on as soon as it
    shows. `extra` is login's contribution: apps boot slower when
    everything boots at once. Re-lists every tick, because the
    whole point is that the window does not exist yet. Returns
    (hits, trouble); trouble is what to say when even the wish
    failed."""
    try:
        budget = max(5, min(600, int(row.get("wait") or 30)
                            + int(extra or 0)))
    except (TypeError, ValueError):
        budget = 30
    trouble = wm.launch(row.get("exe") or "")
    if trouble:
        return [], trouble
    end = time.monotonic() + budget
    while time.monotonic() < end:
        time.sleep(1.0)
        hits = pin_hits(row, wm.list_windows(), taken, fallback)
        if hits:
            return hits, ""
    return [], "no window of %s showed up within %d s" % (
        (row.get("proc") or row.get("exe") or "?").split("\\")[-1],
        budget)


# -------------------------------------------------------------- HDR ----
def hdr_action(want, believed):
    """LEGACY (pre-24H2 Windows, where HDR cannot be read): the pure
    belief dance - press or don't, and what the belief becomes after
    the press. 'unknown' presses and adopts the wanted answer loudly;
    a press always FLIPS the belief - the app sends a toggle, not a
    command. On a readable OS apply never comes here."""
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


def hdr_plan(want, states):
    """Pure decision (testable): given what the driver ANSWERS about
    each monitor ({id: "on"/"off"/"na"/"unknown"}), which monitors to
    command and to what. Panels that cannot do HDR ("na") or will not
    say ("unknown") are left alone - a command they would only refuse
    is not a service; 'toggle' flips exactly what it can see. An
    empty list means the desk already obeys."""
    if want in ("leave alone", "skip"):
        return []
    if want == "toggle":
        return [(i, "off" if s == "on" else "on")
                for i, s in states.items() if s in ("on", "off")]
    return [(i, want) for i, s in states.items() if s in ("on", "off")
            and s != want]


def hdr_snap_plan(displays, states):
    """Pure decision for the honest ask (testable): put every panel
    back the way the profile SAW it at capture. Panels whose capture
    holds no readable state (old profiles, unreadable drivers) are
    left exactly as they are - restoring a guess is not restoring;
    panels that cannot do HDR or will not say now are never
    commanded (same law as hdr_plan); an empty list means the desk
    already wears its captured face."""
    out = []
    for d in displays:
        want = d.get("hdr_state")
        if want not in ("on", "off"):
            continue
        now = states.get(d["id"])
        if now in ("on", "off") and now != want:
            out.append((d["id"], want))
    return out


def _hdr_now():
    """Driver truth joined to monitor ids: ({id: state}, precise,
    {id: gdi}) - the gdi map rides along because after a topology
    apply the old slot names are stale and hdr_set wants fresh
    ones. Fail-open: ({}, False, {}) on any trouble - the caller
    then falls back to the belief path, which is how it behaved
    all along."""
    states, precise, gdis = {}, False, {}
    try:
        rows = wm.hdr_states()
        by_gdi = {m["gdi"]: m["id"] for m in wm.monitors()}
        for s in rows:
            mid = by_gdi.get(s["gdi"])
            if mid is None:
                continue
            gdis[mid] = s["gdi"]
            states[mid] = "na" if not s.get("supported") \
                else s.get("state", "unknown")
            precise = precise or bool(s.get("precise"))
    except Exception:
        log.debug("hdr read failed", exc_info=True)
        return {}, False, {}
    return states, precise, gdis


def hdr_away_off():
    """Presence policy helper: kill every HDR-lit display when the
    desk goes dark, returning the panels we switched so the return can
    hand back exactly what the user had per panel. Empty list =
    nothing to hand back. On pre-24H2 the read state is a lie
    (HDR and wide-gamut merged), so precise=False abstains: no
    cleverness built on sand. Fail-open always.

    Each entry carries the panel MODEL, not just the gdi slot:
    standby can fully disconnect a panel and Windows reshuffles the
    \\.\DISPLAYn slots on return (the same reason _remember_layout
    exists), so the return re-resolves by the model identity that
    does not move."""
    off = []
    try:
        for r in wm.hdr_states():
            if r.get("precise") and r.get("supported") and \
                    r.get("state") == "on":
                say = wm.hdr_set(r["gdi"], False)
                if say == "":
                    off.append({"gdi": r["gdi"],
                                "model": r.get("model") or ""})
                else:
                    log.info("hdr away: %s refused: %s", r["gdi"], say)
    except Exception:
        log.debug("hdr away-off failed", exc_info=True)
    return off


def hdr_away_restore(off):
    """Give back what hdr_away_off took. Setting HDR on a display
    that came back on its own (someone's hotkey, a driver whim) is
    a no-op, so the handback is unconditional. A saved slot is
    trusted only while its LIVE row still answers to the saved model
    - a pair the shuffle cannot frame; a slot that changed tenants
    sends the search to the model identity that does not move.
    Plain-string entries (snapshots taken before this fix) still
    ride, trusting the slot. No live match at all: skip, do not
    guess a panel the user never had lit."""
    entries = [{"gdi": e, "model": ""} if isinstance(e, str) else e
               for e in (off or [])]
    try:
        live = wm.hdr_states()
    except Exception:
        log.debug("hdr return: live read failed", exc_info=True)
        live = []
    by_gdi = {r["gdi"]: r for r in live}
    used = set()
    try:
        for e in entries:
            gdi = e.get("gdi") or ""
            model = e.get("model") or ""
            row = by_gdi.get(gdi)
            if not live:
                target = gdi          # cannot see the desk at all:
                #                      blind ride, the old way
            elif row is not None and (not model
                                      or (row.get("model")
                                          or "") == model):
                target = gdi                    # slot still its own
            elif model:
                target = next((r["gdi"] for r in live
                               if (r.get("model") or "") == model
                               and r["gdi"] not in used), None)
            else:
                target = gdi          # nothing to re-find by
            if not target:
                log.info("hdr return: %s (%s) is gone from the desk",
                         gdi or "?", model or "?")
                continue
            used.add(target)
            say = wm.hdr_set(target, True)
            if say:
                log.info("hdr return: %s refused: %s", target, say)
    except Exception:
        log.debug("hdr restore failed", exc_info=True)


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


def apply(data, name, best_effort=False, scope="full", login=False,
          dir=None):
    """The whole lever. Order and paranoia stolen from
    monitor_control (enable pass, primary last, disable pass, one
    commit, skip-what-is-right so a self-apply never blinks;
    verify-by-fingerprint after, because success is reported before
    the modes land; rescue at the end for whatever the shuffle
    stranded). `scope` narrows the lever - "monitors" skips the
    window phase, "windows" skips every driver call - and the desk
    gate still guards BOTH halves, because a seat saved on one desk
    must never be forced onto another. `login` is the grace flag:
    this apply runs into the logon storm, so the first launch waits
    out LOGIN_DELAY and every "open it" gets LOGIN_PATIENCE on top
    of its own number. Returns (ok, sentence, info) -
    info["no_shows"] names the pins whose app never appeared, so the
    UI can be loud about it exactly as often as the rules allow."""
    prof = data["profiles"].get(name)
    if prof is None:
        return False, "no such profile", {}
    start = time.monotonic()
    layout = scope != "windows"
    wins_scope = scope != "monitors"
    took = {}                 # app -> seconds from OUR launch to window
    waited_for = None         # seconds login made us sit out
    mons = wm.monitors()
    say = []
    gate = desk_mismatch(prof, mons)
    if gate and not best_effort:
        return False, "different desk right now (%s)" % gate, {}
    if gate:
        say.append("best effort over: %s" % gate)

    # 1+2. topology and modes in one DEVMODE pass (entries already
    # carry mode/position; the modes ride the same call the switcher
    # proved on this machine)
    entries = []
    by_id = {m["id"]: m for m in mons}
    if layout:
        for d in prof["displays"]:
            cur = by_id.get(d["id"])
            if cur is None:
                continue                   # the missing panel: asked
            e = dict(d)                    # of nothing, said once
            e["gdi"] = cur["gdi"]          # (slot names may have
            entries.append(e)              # shuffled since capture)
        if entries:
            ok, lines = wm.apply_layout(entries)
            for t in lines:
                log.info("apply '%s': %s", name, t)
            if not ok:
                return False, ("layout refused: " +
                               "; ".join(lines[-1:])), {}

    # 3. HDR: ask the driver first. Where it answers precisely
    # (24H2+), command only the monitors that disagree, then READ
    # BACK until the answer arrives - a set nobody confirmed is a
    # wish, not a fact. The belief dance is what is left for old
    # Windows, whose only readable API conflates HDR with wide
    # gamut and measurably lies.
    ask = prof.get("hdr", "leave alone")
    if layout and ask in ("snap", "on", "off", "toggle"):
        states, precise, gdis = _hdr_now()
        if precise:
            plan = (hdr_snap_plan(prof["displays"], states)
                    if ask == "snap" else hdr_plan(ask, states))
            for mid, goal in plan:
                trouble = wm.hdr_set(gdis[mid], goal == "on")
                if trouble:
                    say.append("hdr %s: %s" % (by_id[mid]["short"],
                                               trouble))
            got = states
            end = time.monotonic() + 10
            while time.monotonic() < end:
                got = _hdr_now()[0]
                if all(got.get(mid) == goal for mid, goal in plan):
                    break
                time.sleep(0.5)
            stuck = [(m, g) for m, g in plan if got.get(m) != g]
            short = lambda m: (by_id[m]["short"] if m in by_id
                               else m[:12])
            if not plan:
                if ask == "snap":
                    say.append(
                        "hdr: already as captured"
                        if any(d.get("hdr_state") in ("on", "off")
                               for d in prof["displays"]) else
                        "hdr: nothing was captured to restore - "
                        "this profile predates the hdr snapshot")
                else:
                    say.append("hdr: nothing readable to flip"
                               if ask == "toggle" else
                               "hdr: every readable monitor already %s"
                               % ask)
            elif stuck:
                say.append("hdr: %s never confirmed" % ", ".join(
                    short(m) for m, _ in stuck))
            else:
                say.append("hdr: %s" % ", ".join(
                    "%s %s (verified)" % (short(m), g)
                    for m, g in plan))
            data["hdr_now"] = "on" if any(v == "on" for v in
                                          got.values()) else "off"
            save(data, dir)
        elif ask == "snap":
            # the belief dance only knows one global switch; per-
            # monitor restore without a readable answer is a coin
            # flip, and coins do not belong in someone's desk
            say.append("hdr: restoring what was captured needs the "
                       "readable driver answer (Win11 24H2+) - "
                       "left as found")
        else:
            action, believed = hdr_action(ask, data.get(
                "hdr_now", "unknown"))
            if action == "press":
                trouble = wm.press_keys(data.get("hdr_key",
                                                 "win+alt+b"))
                data["hdr_now"] = believed
                say.append(trouble or
                           ("pressed %s for hdr (now believed %s)"
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
    if wins_scope and not layout:
        matched = True             # the gate swore this IS the
                                   # profile's desk, and nothing was
                                   # changed: nothing can settle
        say.append("monitors untouched (windows only)")
    else:
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
            say.append("the desk never matched the profile (it "
                       "answers %s) - windows placed on what is "
                       "here" % last)
        elif not matched:
            say.append("the desk never answered as the profile "
                       "asked (still: %s)"
                       % (last or "nothing settled"))

    # 5. windows, only against a settled desk they were pinned for.
    # A pin that finds no window and carries the naive wish re-runs
    # the saved exe and waits; a pin whose app DID show up (just
    # answered an earlier pin of the same process first) is not a
    # failure worth a dialog - only apps that truly stayed away are
    # reported, and only until the user once declined to fix them.
    no_shows = []
    if wins_scope and (matched or best_done):
        live = wm.list_windows()
        taken, placed, silent = set(), 0, 0
        moved_procs, troubles = set(), []
        if login:
            waited_for = launch_delay(data)
        sat_out = waited_for is None
        for s in prof["wins"]:
            fb = prof.get("match") or "process"
            hits = pin_hits(s, live, taken, fb)
            if not hits and s.get("open") and s.get("exe"):
                if not sat_out:
                    # the login special: the first launch sits out
                    # the storm (two unmeasured minutes the first
                    # time; later whatever the slowest app was ever
                    # seen to need, plus buffer)
                    sat_out = True
                    rest = waited_for - (time.monotonic() - start)
                    if rest > 0:
                        log.info("login restore: %d s of storm to "
                                 "sit out before launching",
                                 int(rest) + 1)
                        time.sleep(rest)
                t_launch = time.monotonic()
                hits, trouble = relaunch(
                    s, taken, fb,
                    extra=LOGIN_PATIENCE if login else 0)
                if trouble:
                    troubles.append(trouble)
                if hits:
                    # the lesson, timed from OUR launch: an app
                    # that was already open at boot told us nothing
                    who = ((s.get("proc") or s.get("exe") or "?")
                           ).split("\\")[-1].lower()
                    took[who] = max(time.monotonic() - t_launch, 1.0)
            if not hits:
                if s.get("quiet"):
                    silent += 1
                else:
                    no_shows.append(s)
                continue
            if s.get("quiet"):
                s["quiet"] = False       # it answered again: a new
                                         # failure may be loud again
            for l in hits:
                taken.add(l["hwnd"])
                try:
                    cur = wm.true_rect(l["hwnd"])
                except Exception:
                    cur = None       # a desk this blind proves
                    #                                nothing: place anyway
                if cur == tuple(s["rect"]) and not s.get("zoomed"):
                    placed += 1              # already parked, floating,
                    continue                 # right there: don't move it
                                             # (same-rect skip only; unlike wm.apply, an
                                              # explicit profile apply MOVES
                                              # even a reachable user-moved
                                              # window - that's the point)
                if wm.place(l["hwnd"], tuple(s["rect"]),
                            s.get("zoomed")) == "ok":
                    placed += 1
                    moved_procs.add((s.get("proc") or "").lower())
                else:
                    silent += 1
        still = []
        for s in no_shows:               # the app walked in under
            if (s.get("proc") or "").lower() in moved_procs:
                silent += 1              # another pin - not a loss
            else:
                still.append(s)
        no_shows = still
        say.append("windows: %d placed, %d not open or refused"
                   % (placed, silent))
        if troubles:
            say.append("would not start: %s" % "; ".join(
                troubles)[:160])
        rescued = wm.rescue_lost()
        if rescued:
            say.append("rescued: %s" % ", ".join(rescued)[:120])
        if took:                       # what showed up is the lesson
            lg = data.setdefault("login", {})
            seen = lg.setdefault("took", {})
            for k, v in took.items():
                seen[k] = max(v, seen.get(k, 0))
            lg["max"] = max(seen.values())
            lg["at"] = time.time()
        if waited_for is not None:
            say.append("login: waited %d s before launching"
                       % int(waited_for))
            if took:
                say.append("next login: %d s (learned)"
                           % int(launch_delay(data)))
    else:
        say.append("windows untouched" +
                   (" (monitors only)" if not wins_scope else ""))

    prof["used"] = time.time()
    data["last"][target] = name
    save(data, dir)
    info = {"no_shows": [{"proc": s.get("proc", ""),
                          "title": s.get("title", "")}
                         for s in no_shows]}
    if login:
        info["login"] = {"took": took,
                         "delay_next": launch_delay(data)}
    return matched or best_done, " ; ".join(say) if say else \
        "applied: %s" % (" + ".join(d["short"] for d in
                                prof["displays"] if d.get("on", True))), \
        info
