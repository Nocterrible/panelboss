"""the gaming-hz watcher: the hands that execute what gaming.decide
advises.

THE LAW, in the order the loop obeys it:
1. only a fullscreen-over-a-monitor foreground window starts a
   conversation about game mode (gaming.py judges; we only measure
   "covers" and hand over facts);
2. we never fight a mode we do not own. Every rate we set is booked
   in a ledger; if the live mode disagrees with the ledger while a
   game is up, an exclusive title owns the display and we keep our
   hands off until it leaves. While nothing games, a disagreeing
   mode is simply the new truth and we adopt it (NVIDIA panel,
   profile apply, user hands - all welcome);
3. desktop rates return on a transition, never every tick: the
   engine emits plans on change only, and set_mode itself refuses
   a no-op, so a steady desk sees zero driver calls;
4. resolution is never the watcher's business - every set keeps the
   monitor's current pixels and only trades the rate;
5. fail open. Any exception inside a tick is logged and the loop
   survives; any Win32 layer failure is already None/False/{}/""
   by the time it reaches us.

tick() is pure of threads and sleeps so scripts/gaming_watch_test.py
can drive a week of fake desk in seconds. cli.py runs loop() on a
daemon thread beside the presence monitor; the shared cfg dict means
a UI save takes effect on the next tick without a restart.
"""
import logging
import time

from . import wm
try:                              # the engine is written by a
    from . import gaming          # different hand: its absence
except ImportError:               # must never ground the whole
    gaming = None                 # app - the watcher just sleeps
                                  # until it shows up (fresh
                                  # imports cannot see a file
                                  # created later, so a restart
                                  # after the merge is expected)

log = logging.getLogger("gaming")

TICK_SEC = 2.0            # gpu.usage() blocks ~1.2 s by design; two
                          # seconds of slack keeps its collect pair
                          # honest without stacking calls
COVER_FUDGE = 8           # borderless windows measure a few px past
                          # the edge even after true_rect corrects


def covers(fg, mons):
    """True when fg's rect blankets the whole monitor it sits on."""
    if not fg or not fg.get("monitor") or not fg.get("rect"):
        return False
    m = next((m for m in mons if m["short"] == fg["monitor"]), None)
    if not m:
        return False
    x, y, w, h = fg["rect"]
    return (x <= m["x"] + COVER_FUDGE and y <= m["y"] + COVER_FUDGE and
            x + w >= m["x"] + m["w"] - COVER_FUDGE and
            y + h >= m["y"] + m["h"] - COVER_FUDGE)


def wanted_hz(gcfg, key, m, offered):
    """Resolve game_hz/desktop_hz for one monitor: an int is an
    order; game_hz "auto" (or unset) means the fastest rate the
    panel offers; desktop_hz unset means 60, the user's default."""
    want = (gcfg.get(key) or {}).get(m["short"])
    if want is None and key == "game_hz":
        want = "auto"
    if want == "auto":
        best = 0
        for name in offered or ():
            try:
                best = max(best, int(name.rsplit("@", 1)[1]))
            except (IndexError, ValueError):
                continue
        return best or m["rate"]
    if want is None:
        return 60
    try:
        return int(want)
    except (TypeError, ValueError):
        return m["rate"]


def _live(gdi):
    """(w, h, rate) as the driver answers right now, or None."""
    try:
        cur = wm.current_mode(gdi)
    except Exception:
        return None
    if cur is None:
        return None
    return (int(cur.dmPelsWidth), int(cur.dmPelsHeight),
            int(cur.dmDisplayFrequency))


def _book(ledger, short, gdi):
    """Believe the driver: what it allowed after any set (or any
    foreign change) is what we now own."""
    live = _live(gdi)
    if live:
        ledger[short] = (gdi, live[0], live[1], live[2])


def _set_hz(ledger, m, hz, kind, notify=None, reason=""):
    """The one driver call in this file: current resolution, new
    rate. 'already ...' from set_mode is a normal, boring answer."""
    try:
        cur = wm.current_mode(m["gdi"])
        if cur is None:
            return
        say = wm.set_mode(m["gdi"], int(cur.dmPelsWidth),
                          int(cur.dmPelsHeight), int(hz))
        log.info("gaming hz: %s %s -> %s (%s)", m["short"], kind,
                 say, reason or "-")
        if notify and kind == "game":
            notify("gaming hz: %s %s -> %d Hz"
                   % (reason or "game", m["short"], int(hz))[:180])
    except Exception:
        log.exception("gaming hz: set for %s died", m["short"])
    finally:
        _book(ledger, m["short"], m["gdi"])


def _release_all(ledger, mons, gcfg):
    """Gaming got switched off while a monitor was ours: give every
    booked monitor its desktop rate back, then wash our hands."""
    for short in list(ledger):
        m = next((m for m in mons if m["short"] == short), None)
        if m:
            _set_hz(ledger, m, wanted_hz(gcfg, "desktop_hz", m, ()),
                    "switched off")
        ledger.pop(short, None)


def _adopt_or_hands_off(st, ledger, mons):
    """While a game is up, a mode that disagrees with the ledger is
    a display an exclusive title owns: say so once per monitor,
    hands off. While nothing games, disagreement is the new truth:
    adopt it (profiles, the NVIDIA panel and the user's own hands
    all outrank us outside game mode)."""
    gaming_up = st.get("mode") == "game"
    said = st.setdefault("_foreign", set())
    for short in list(ledger):
        gdi = ledger[short][0]
        live = _live(gdi)
        if live is None or live == ledger[short][1:]:
            continue
        if gaming_up:
            if short not in said:
                said.add(short)
                log.info("gaming hz: %s moved out from under us - "
                         "exclusive game owns it, hands off", short)
        else:
            _book(ledger, short, gdi)
            said.discard(short)


def tick(st, ledger, cfg, notify=None, senses=None, side=None):
    """One honest observation plus the mode moves it asks for.
    `senses` injects the outside facts (fg/mon/gpu) for the offline
    test; production leaves it None. `side` is the watcher's OWN
    long-lived state (module snapshots can block, so we cache; the
    power-plan handback memory) - kept apart from the engine's st
    because evaluate is free to clear st on every transition.
    Returns (st, plan)."""
    gcfg = cfg.get("gaming") or {}
    senses = senses or {}
    if side is None:
        side = {}
    plan = None
    if not gcfg.get("enabled"):
        if ledger:                       # switched off mid-game: the
            mons = senses.get("mons", wm.monitors())
            _release_all(ledger, mons, gcfg)
        _apply_power_plan(side, gcfg, False)   # and the plan back
        _timer_boost(side, False)              # and the timer hand
        st.clear()
        return st, None
    mons = senses.get("mons") if "mons" in senses else wm.monitors()
    if not mons:
        return st, None                  # a re-plug storm: nothing is
                                         # knowable, wait it out
    fg = senses.get("fg", None) if "fg" in senses else wm.foreground()
    if fg and "covers" not in fg:
        fg = dict(fg, covers=covers(fg, mons))
    if "xinput" in senses:
        x = senses["xinput"]
    else:
        x = False                        # anti-cheat snapshots can
        if fg:                           # block seconds: only ever
            if side.get("fg_pid") != fg["pid"]:
                side["fg_pid"] = fg["pid"]
                side["fg_x"] = bool(wm.has_xinput(fg["pid"]))
            x = bool(side.get("fg_x"))
    gpu_map = senses.get("gpu") if "gpu" in senses else _gpu_usage()
    st, plan = gaming.evaluate(dict(fg=fg, gpu=gpu_map, xinput=x),
                               st, gcfg, time.time())
    gaming_now = st.get("mode") == "game"
    if not plan:
        _adopt_or_hands_off(st, ledger, mons)
        _apply_power_plan(side, gcfg, gaming_now)
        _timer_boost(side, gaming_now)
        return st, plan
    for short in plan.get("desktop") or []:
        m = next((m for m in mons if m["short"] == short), None)
        if m:
            _set_hz(ledger, m, wanted_hz(gcfg, "desktop_hz", m, ()),
                    "desktop")
    g = plan.get("game")
    if g:
        m = next((m for m in mons if m["short"] == g["monitor"]), None)
        if m:
            _set_hz(ledger, m,
                    wanted_hz(gcfg, "game_hz", m,
                              wm.offered_modes(m["gdi"])),
                    "game", notify, g.get("proc", ""))
    _apply_power_plan(side, gcfg, gaming_now)
    _timer_boost(side, gaming_now)
    return st, plan


def _timer_boost(side, gaming_now):
    """Hold 1 ms timer resolution ONLY while a game owns the desk
    (docs/apack-findings.md T8: the documented winmm API, not the
    undocumented registry knob; zero admin, zero reboot, works even
    with the GPU counters dead). side remembers OUR holding so the
    pairing is exact: timeEndPeriod only ever answers a
    timeBeginPeriod we made."""
    held = bool(side.get("timer"))
    if held == bool(gaming_now):
        return
    try:
        from . import tweaks
        ok = tweaks.timer_boost(bool(gaming_now))
    except Exception:
        ok = False
    if ok:
        side["timer"] = bool(gaming_now)
        log.debug("timer resolution %s for gaming",
                  "held at 1 ms" if gaming_now else "released")


def _apply_power_plan(side, gcfg, gaming_now):
    """The plan swap rides the same transition as the Hz swap: a
    game earns the fast plan, leaving gives back the plan that was
    active BEFORE the game (never a guessed 'balanced'). Gated by
    gaming.power_plan (name fragment or guid; '' = never touch it).
    side is long-lived so the saved guid survives the engine
    clearing its own state."""
    want = (gcfg.get("power_plan") or "").strip()
    if not want:
        return
    from . import power_plan
    state = side.setdefault("power_plan", {"saved": "", "active": ""})
    if gaming_now and not state["active"]:
        cur = power_plan.active()
        target = power_plan.pick(power_plan.plans(), want)
        if cur and target and target.lower() != cur.lower():
            if power_plan.set_plan(target):
                state["saved"], state["active"] = cur, target
                log.info("gaming hz: power plan -> %s (was %s)",
                         target, cur)
    elif not gaming_now and state["active"]:
        cur = power_plan.active()
        # hand back only if WE still own it; if the user or a
        # scheduled task moved it mid-game, that is the new truth.
        if cur and cur.lower() == state["active"].lower():
            if power_plan.set_plan(state["saved"]):
                log.info("gaming hz: power plan back to %s",
                         state["saved"])
        state["saved"] = state["active"] = ""


def _gpu_usage():
    """gpu.usage() behind a name so the lazy import (pdh.dll) only
    ever happens with gaming enabled."""
    from . import gpu
    return gpu.usage()


def loop(cfg, stop):
    """cli.py's daemon body. Reads cfg every tick (a UI save takes
    effect live); dies quietly when stop is set."""
    log.info("gaming watcher alive (enabled=%s)",
             bool((cfg.get("gaming") or {}).get("enabled")))
    st, ledger, side = {}, {}, {}
    while not stop.is_set():
        try:
            tick(st, ledger, cfg, side=side)
        except Exception:
            log.exception("gaming tick died; desk left as it is")
        stop.wait(TICK_SEC)
    if (cfg.get("gaming") or {}).get("enabled") and ledger:
        pass                             # quitting mid-game leaves
                                         # the rate we set: honest -
                                         # we did not steal it back
                                         # on a suicide
