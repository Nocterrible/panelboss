"""the gaming decision core: pure judgment over injected facts.

No ctypes, no windows, no clocks of its own - the caller passes
`now` and the three senses (foreground window, gpu map, xinput
verdict), which makes the whole thing testable to the millisecond.
gaming_watch.py is the hands; this is the brain it consults.

THE LAW:
1. only a window covering a whole monitor may ask (covers gate);
2. evidence qualifies: the games list (a menu renders at 0% and
   still deserves the rate), a loaded xinput (games are almost
   alone in using it), or gpu load at/over threshold;
3. the list enters instantly; evidence alone must SUSTAIN for
   seen_secs first (a browser spike must not burn the panel);
4. while a game owns a monitor, losing the evidence (menu,
   cutscene, alt-tab) only starts a grace timer, never a switch;
   the timer clears the moment evidence returns;
5. the rate returns only after grace expires - once, quietly
   (emission discipline: plans are emitted at transitions; a
   steady state answers None and the worker stays silent);
6. ignore beats the list; a game never qualifies twice for the
   same frame; nothing here may raise.

evaluate(facts, st, cfg, now) -> (st, plan|None)
facts = {"fg": {...}|None, "gpu": {pid: pct}, "xinput": bool}
plan  = {"game": {"monitor","pid","proc","reason"}|None,
         "desktop": [short, ...]}
"""
import logging

log = logging.getLogger("gaming")

DEFAULTS = {"threshold_pct": 5.0, "seen_secs": 10.0,
            "grace_secs": 60.0}


def _get(d, key, default=None):
    try:
        v = d.get(key, default)
    except AttributeError:
        return default
    return default if v is None else v


def evaluate(facts, st, cfg, now):
    """Judge one frame of the desk. st is the caller's dict; we
    keep "mode"/"monitor"/"proc"/"pid"/"seen"/"grace_start" in it
    and clear() it on the way out of a game (the worker's ledger,
    not the desk, decides what a handback costs)."""
    try:
        return _evaluate(facts or {}, st if st is not None else {},
                         cfg or {}, now)
    except Exception:
        log.debug("gaming evaluate died", exc_info=True)
        return st, None


def _evaluate(facts, st, cfg, now):
    if not cfg.get("enabled"):
        st.clear()
        return st, None
    thr = _get(cfg, "threshold_pct", DEFAULTS["threshold_pct"])
    seen = _get(cfg, "seen_secs", DEFAULTS["seen_secs"])
    grace = _get(cfg, "grace_secs", DEFAULTS["grace_secs"])
    games = [str(g).lower() for g in _get(cfg, "games", [])]
    ignore = [str(g).lower() for g in _get(cfg, "ignore", [])]

    fg = facts.get("fg") or {}
    proc = str(_get(fg, "proc", "")).lower()
    pid = _get(fg, "pid", 0) or 0
    monitor = str(_get(fg, "monitor", ""))
    covers = bool(_get(fg, "covers", False)) and bool(monitor)
    pct = 0.0
    try:
        pct = float((facts.get("gpu") or {}).get(pid, 0.0))
    except (TypeError, ValueError):
        pass
    qualified = (covers and proc and proc not in ignore
                  and (proc in games or facts.get("xinput")
                       or pct >= thr))
    if qualified and proc in games:
        reason = "trusted"
    elif facts.get("xinput"):
        reason = "xinput"
    elif pct >= thr:
        reason = "gpu %.1f%%" % pct
    else:
        reason = ""

    game = {"monitor": monitor, "pid": pid, "proc": proc,
            "reason": reason}

    if st.get("mode") == "game":
        old = st.get("monitor")
        if qualified and monitor == old:
            st["grace_start"] = None
            if (st.get("proc") == proc and st.get("pid") == pid):
                return st, None          # steady; the watcher owns
                                         # any re-assert, we do not
            st["proc"], st["pid"] = proc, pid   # handoff: new
            game["reason"] = "handoff"          # title bar, same
            return st, {"game": game, "desktop": []}   # panel
        if qualified:                    # another panel earned it
            st.update(mode="game", monitor=monitor, proc=proc,
                      pid=pid, grace_start=None, seen=None)
            game["reason"] = "moved"
            return st, {"game": game, "desktop": [old]}
        if st.get("grace_start") is None:
            st["grace_start"] = now      # the alt-tab window opens
        if now - st["grace_start"] < grace:
            return st, None
        st.clear()
        return st, {"game": None, "desktop": [old]}

    if not qualified:
        st.pop("seen", None)             # evidence broke; the timer
        return st, None                  # restarts from zero
    if proc in games:                    # listed: instant, a menu
        st.update(mode="game", monitor=monitor, proc=proc, pid=pid,
                  seen=None, grace_start=None)
        return st, {"game": game, "desktop": []}
    sp = st.get("seen") or {}
    if not (sp.get("pid") == pid and sp.get("proc") == proc
            and sp.get("monitor") == monitor):
        st["seen"] = {"pid": pid, "proc": proc, "monitor": monitor,
                      "since": now}
        return st, None
    if now - sp.get("since", now) >= seen:
        game["reason"] = "%s sustained %d s" % (
            reason, int(now - sp["since"]))
        st.update(mode="game", monitor=monitor, proc=proc, pid=pid,
                  seen=None, grace_start=None)
        return st, {"game": game, "desktop": []}
    return st, None
