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
   by the time it reaches us;
6. a vrr-declared panel (game_hz = "vrr") is never flipped: the
   user enabled g-sync on it, its scanout belongs to the driver's
   variable rate, so outside games it is only re-pinned to its max
   offered rate (the top of that range, where it idles anyway).

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
    panel offers; game_hz "vrr" rides that same path (the max IS
    the top of the panel's range, and set_mode refuses a no-op, so
    an accidental set cannot flash); desktop_hz unset means 60, the
    user's default."""
    want = (gcfg.get(key) or {}).get(m["short"])
    if want is None and key == "game_hz":
        want = "auto"
    if want is None:
        return 60
    if want == "auto" or str(want).strip().lower() == "vrr":
        best = 0
        for name in offered or ():
            try:
                best = max(best, int(name.rsplit("@", 1)[1]))
            except (IndexError, ValueError):
                continue
        return best or m["rate"]
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
    rate. 'already ...' from set_mode is a normal, boring answer.
    Session (RDP) displays are exempt (measured Oct 11): the virtual
    driver reports a fictional 32 Hz and "offers" modes it rewrites
    at will - negotiating against it loses to the fiction."""
    if "remote_monitor" in (m.get("id") or "").lower():
        log.info("gaming hz: %s is a session display (rates are RDP "
                 "fiction); left alone", m["short"])
        return
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
    booked monitor its desktop rate back (default 60 - a panel WE
    clocked up must not stay clocked up with us gone; panels we
    never touched were never ours to release), then wash hands.
    vrr panels are exempt: we leave them at max, which is exactly
    where their g-sync range tops out."""
    for short in list(ledger):
        m = next((m for m in mons if m["short"] == short), None)
        if m and _vrr_rule((gcfg.get("game_hz") or {}).get(short)):
            # vrr outranks even the hand-back: the panel stays at max,
            # where g-sync lives; 60 is the worst seat in the house
            log.info("gaming hz: %s stays pinned - vrr owns it", short)
        elif m:
            _set_hz(ledger, m, wanted_hz(gcfg, "desktop_hz", m, ()),
                    "switched off")
        ledger.pop(short, None)


def _vrr_rule(rule):
    """True when a per-monitor game rule declares vrr: the user
    enabled g-sync on that panel themselves, so the only thing we
    may do with it is stop flipping it (and re-pin its max)."""
    return str(rule or "").strip().lower() == "vrr"


def _vrr_max(offered):
    """The top rate a 'WxH@R' list offers, 0 when the list is empty
    or nothing in it parses (the same reading 'auto' uses)."""
    best = 0
    for name in offered or ():
        try:
            best = max(best, int(name.rsplit("@", 1)[1]))
        except (AttributeError, IndexError, TypeError, ValueError):
            continue
    return best


def _hold_vrr(ledger, m):
    """The vrr pin: outside games a declared-vrr panel sits at its
    max offered rate - the top of the variable range, where the
    panel idles anyway. Silent when it already sits there; parked
    quietly when the max cannot land at this resolution right now
    (the same storm guard the explicit path uses); nothing at all
    when the driver offers no list."""
    try:
        offered = wm.offered_modes(m["gdi"])
    except Exception:
        offered = ()
    want = _vrr_max(offered)
    if not want:
        return                     # no list: say nothing, do nothing
    live = _live(m["gdi"])
    if live is None or live[2] == want:
        return                     # already at the max: zero calls
    mode = "%dx%d@%d" % (live[0], live[1], want)
    if mode not in (offered or ()):
        # the max cannot land at THIS resolution right now (a cable
        # swap or a driver update rewrote the mode list): set_mode
        # would refuse before touching the screen, the book would
        # keep the foreign truth, and next tick we'd be here again -
        # a 2 s retry storm of scans and log lines for a mode that
        # cannot land. Park quietly until the list changes.
        return
    _set_hz(ledger, m, want, "vrr max", None, "not gaming")


def _enforce_desktop(ledger, mons, gcfg):
    """OUTSIDE game mode two laws share this pass: the vrr law
    outranks the desktop law - a declared-vrr panel is never flipped
    to its desktop rate, it is re-pinned to its max (_hold_vrr);
    every other configured panel sits at its configured rate,
    always, re-set whenever the driver stopped listening. This is
    the automation: Windows forgets rates after reboots/driver
    updates (measured: whole desk at 60 after the 10-10 restart) and
    the user should never have to notice. Panels WITHOUT an entry in
    either map are nobody's business - profiles, NVCP and the user's
    hands keep full authority over them, adopted untouched by
    _adopt_or_hands_off."""
    want_map = gcfg.get("desktop_hz") or {}
    game_map = gcfg.get("game_hz") or {}
    if not isinstance(game_map, dict):
        game_map = {}
    shorts = list(want_map)
    for short in game_map:
        if _vrr_rule(game_map.get(short)) and short not in shorts:
            shorts.append(short)
    for short in shorts:
        m = next((m for m in mons if m["short"] == short), None)
        if m is None:
            continue                     # unplugged: nothing to hold
        if _vrr_rule(game_map.get(short)):
            _hold_vrr(ledger, m)
            continue
        try:
            want = int(want_map[short])
        except (TypeError, ValueError):
            continue
        live = _live(m["gdi"])
        if live is None or live[2] == want:
            continue                     # driver agrees: zero calls
        mode = "%dx%d@%d" % (live[0], live[1], want)
        try:
            offered = wm.offered_modes(m["gdi"])
        except Exception:
            offered = ()
        if mode not in (offered or ()):
            # the panel cannot comply RIGHT NOW (a cable swap or
            # driver update rewrote its mode list): set_mode would
            # refuse before touching the screen, the book would keep
            # the foreign truth, and next tick we'd be here again -
            # a 2 s retry storm of scans and log lines for a mode
            # that cannot land. Park quietly until the list changes.
            continue
        _set_hz(ledger, m, want, "desktop hold", None, "not gaming")


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
    if gaming is None:
        return st, None                      # engine not merged yet:
        # sleep quietly, exactly like the import comment promises
    gcfg = cfg.get("gaming") or {}
    senses = senses or {}
    if side is None:
        side = {}
    plan = None
    if not gcfg.get("enabled"):
        if ledger:                       # switched off mid-game: the
            mons = senses.get("mons", wm.monitors())
            _release_all(ledger, mons, gcfg)
        _apply_power_plan(side, gcfg, False, cfg)   # and the plan back
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
                               st, gcfg, time.monotonic())
    gaming_now = st.get("mode") == "game"
    if not plan:
        _adopt_or_hands_off(st, ledger, mons)
        if not gaming_now:
            _enforce_desktop(ledger, mons, gcfg)
        _apply_power_plan(side, gcfg, gaming_now, cfg)
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
    _apply_power_plan(side, gcfg, gaming_now, cfg)
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


def _persist_plan_state(cfg):
    """The marker rides cfg["gaming"] - the app's one state store (the
    same dict the seen-plan overrides live in) - and reaches the disk
    through config.write_config: the writer takes the WHOLE cfg (it
    rewrites every section, not one table) and serializes the snapshot
    under its own lock, the shape the UI's debounced save rides. The
    call is lazy (the watcher must not pin the config module at import).
    A cfg with no _path never came off disk (the offline test's fake
    desk), so there is nothing to write back to - skip it fail-open
    rather than invent a location; a real failure to write costs the
    marker for one boot, not the desk."""
    target = cfg.get("_path")           # write back to WHERE THIS cfg
    if not target:                      # was loaded from, not wherever
        return                          # CONFIG_DIR points today - the
    try:                                # offline fake's temp store and
        from . import config            # a test's redirected store
        config.write_config(cfg, target)  # must not touch the owner's
    except Exception:                   # real desk
        log.warning("gaming: the plan marker could not be persisted",
                    exc_info=True)


def _reconcile_plan(store, active, pick, set_plan):
    """Boot pass (audit W2C MED): if the marker is set, a previous
    session left mid-game - the quit (or crash) skipped the
    switch-back. If the plan NOW is the performance plan, the desk is
    still wearing OUR suit: hand back to the recorded previous,
    falling back to letting Windows balance (no swap, no claim) when
    no previous was ever recorded. If the plan is NOT ours any more,
    somebody else moved it and the claim is simply void. Injected
    callables so the probe drives it with no powercfg; production
    passes power_plan (pick takes the gaming cfg dict)."""
    if not gaming.plan_owned(store):
        return None
    prev = gaming.plan_prev(store)
    cur = (active() or "").lower()
    perf = (pick(store) or "").lower()
    if perf and cur == perf:
        if not prev:
            gaming.clear_plan_owned(store)
            return "no recorded previous: let Windows balance"
        if set_plan(prev):
            gaming.clear_plan_owned(store)
            return "handed back to %s" % prev
        return ("handback FAILED, the marker stands "
                "(next boot retries)")      # never orphan silently
    if not perf:
        # gate LOW: marker set but the performance plan resolves to
        # nothing (cleared from config after a crash mid-game) - the
        # claim must not vanish quietly: the desk may still sit on
        # the game plan until someone switches by hand
        log.warning("reconcile: ownership marker set but no performance "
                    "plan on this box - desk may still be on the game "
                    "plan; claim cleared, switch manually if the desk "
                    "runs hot")
    gaming.clear_plan_owned(store)
    return "not ours any more (moved by someone else): cleared"


def _boot_reconcile(cfg):
    """The loop's startup pass: wire _reconcile_plan to the real
    powercfg layer, persist whatever the reconcile decided."""
    if gaming is None:
        return
    gcfg = cfg.get("gaming") or {}
    if not gaming.plan_owned(gcfg):
        return
    from . import power_plan

    def _pick(g):
        want = (g.get("power_plan") or "").strip()
        return power_plan.pick(power_plan.plans(), want) if want else ""
    outcome = _reconcile_plan(gcfg, power_plan.active, _pick,
                              power_plan.set_plan)
    if outcome:
        log.info("gaming boot: stale plan ownership - %s", outcome)
        _persist_plan_state(cfg)


def _apply_power_plan(side, gcfg, gaming_now, cfg):
    """The plan swap rides the same transition as the Hz swap: a
    game earns the fast plan, leaving gives back the plan that was
    active BEFORE the game (never a guessed 'balanced'). Gated by
    gaming.power_plan (name fragment or guid; '' = never touch it).
    side is long-lived so the saved guid survives the engine
    clearing its own state; the config marker (gaming.mark_plan_owned)
    survives the PROCESS clearing it - the quit-mid-game orphan the
    audit caught, closed by _boot_reconcile."""
    want = (gcfg.get("power_plan") or "").strip()
    state = side.setdefault("power_plan", {"saved": "", "active": ""})
    if not want and not state["active"]:
        return
    from . import power_plan
    if want and gaming_now and not state["active"]:
        cur = power_plan.active()
        target = power_plan.pick(power_plan.plans(), want)
        if cur and target and target.lower() != cur.lower():
            if power_plan.set_plan(target):
                state["saved"], state["active"] = cur, target
                gaming.mark_plan_owned(gcfg, cur)   # claim: the desk
                _persist_plan_state(cfg)            # wears our suit
                log.info("gaming hz: power plan -> %s (was %s)",
                         target, cur)
    elif not gaming_now and state["active"]:
        cur = power_plan.active()
        # hand back only if WE still own it; if the user or a
        # scheduled task moved it mid-game, that is the new truth
        # and the claim is simply void (the boot rule agrees).
        if not cur or cur.lower() != state["active"].lower():
            gaming.clear_plan_owned(gcfg)               # ours no more
            _persist_plan_state(cfg)
            state["saved"] = state["active"] = ""
        else:
            # gate MED (ledger 1): a FAILED set_plan (False return or
            # raise) used to clear the marker anyway - the desk stayed
            # on High-Performance with no retry token. The boot rule
            # (_reconcile_plan) clears ONLY on success; mirror it: keep
            # BOTH keys standing, log the failure, and let the next
            # boot's reconcile retry the handback.
            try:
                back = bool(power_plan.set_plan(state["saved"]))
            except Exception:
                back = False
                log.exception("gaming hz: power plan handback raised")
            if back:
                log.info("gaming hz: power plan back to %s",
                         state["saved"])
                gaming.clear_plan_owned(gcfg)           # ours no more
                _persist_plan_state(cfg)
                state["saved"] = state["active"] = ""
            else:
                log.error("gaming hz: power plan handback FAILED (%s); "
                          "the marker stands so the boot reconcile "
                          "retries", state["saved"])


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
    try:
        _boot_reconcile(cfg)             # the startup pass (audit W2C
    except Exception:                    # MED): a marker from a quit
        log.exception("gaming boot reconcile died")   # -mid-game session
                                       # comes home before this loop
                                       # books any new claim
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
