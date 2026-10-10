"""gaming_watch offline suite: a fake desk (monitors, foreground,
gpu map, driver) driven through gaming_watch.tick() at frozen time,
asserting exactly which driver calls happen when. The ENGINE's own
judgment is gaming_test.py's job; here we verify the hands: covers
measurement, ledger discipline, exclusive-game hands-off, desktop
return, release-on-disable, and the iron rule that a steady desk
sees zero driver calls.

Run: python scripts/gaming_watch_test.py   (from repo root)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not os.path.exists(os.path.join(ROOT, "awaywatch", "gaming.py")):
    # engine still typing elsewhere: shim the EXACT contract so the
    # worker plumbing can be tested today. gaming_test.py is the
    # engine's judge, not this file.
    import types

    def evaluate(facts, st, cfg, now):
        if not cfg.get("enabled"):
            st.clear()
            return st, None
        fg = facts.get("fg")
        proc = (fg or {}).get("proc", "").lower()
        want = (fg and fg.get("covers") and
                (proc in [g.lower() for g in cfg.get("games", [])]
                 or facts.get("gpu", {}).get(fg["pid"], 0.0) >=
                 cfg.get("threshold_pct", 5.0)
                 or facts.get("xinput")))
        if st.get("mode") == "game":
            if want and fg["monitor"] == st["monitor"] and \
                    proc == st["proc"]:
                st["grace_start"] = None
                return st, None
            if want and fg["monitor"] != st["monitor"]:
                old = st["monitor"]
                st.update(mode="game", monitor=fg["monitor"],
                          proc=proc, pid=fg["pid"])
                return st, {"game": {"monitor": fg["monitor"],
                                     "pid": fg["pid"], "proc": proc,
                                     "reason": "moved"},
                            "desktop": [old]}
            if st.get("grace_start") is None:
                st["grace_start"] = now
            if now - st["grace_start"] < cfg.get("grace_secs", 60.0):
                return st, None
            old = st["monitor"]
            st.clear()
            return st, {"game": None, "desktop": [old],
                        "reason": "grace expired"}
        if want:
            st.update(mode="game", monitor=fg["monitor"], proc=proc,
                      pid=fg["pid"], grace_start=None)
            return st, {"game": {"monitor": fg["monitor"],
                                 "pid": fg["pid"], "proc": proc,
                                 "reason": "trusted"}, "desktop": []}
        return st, None
    mod = types.ModuleType("awaywatch.gaming")
    mod.evaluate = evaluate
    sys.modules["awaywatch.gaming"] = mod

from awaywatch import gaming_watch as gw        # noqa: E402

CALLS = []


class Mode:
    def __init__(self, w, h, r):
        self.dmPelsWidth, self.dmPelsHeight = w, h
        self.dmDisplayFrequency = r


class FakeWm:
    MONS = [{"id": "M1", "short": "M1", "gdi": "D1",
             "x": 0, "y": 0, "w": 2560, "h": 1440, "rate": 144,
             "bits": 32, "primary": True},
            {"id": "M2", "short": "M2", "gdi": "D2",
             "x": 2560, "y": 0, "w": 1920, "h": 1080, "rate": 60,
             "bits": 32, "primary": False}]
    OFFER = {"D1": ["2560x1440@60", "2560x1440@144",
                                 "2560x1440@240"],
             "D2": ["1920x1080@60", "1920x1080@165"]}

    def __init__(self):
        self.live = {"D1": (2560, 1440, 144),
                     "D2": (1920, 1080, 60)}
        self.fg = None

    def monitors(self):
        return [dict(m) for m in self.FakeWm_mons()]

    def FakeWm_mons(self):
        return self.MONS

    def foreground(self):
        return dict(self.fg) if self.fg else None

    def has_xinput(self, pid):
        return False

    def current_mode(self, gdi):
        w, h, r = self.live[gdi]
        return Mode(w, h, r)

    def offered_modes(self, gdi):
        return list(self.OFFER[gdi])

    def set_mode(self, gdi, w, h, rate):
        CALLS.append((gdi, w, h, rate))
        if "%dx%d@%d" % (w, h, rate) in self.OFFER[gdi]:
            self.live[gdi] = (w, h, rate)
        return "asked %dx%d@%d" % (w, h, rate)


class Clock:
    t = 1000.0

    def time(self):
        return self.t

    def monotonic(self):
        return self.t          # the engine's now: one frozen lever


def fg_on(mon, proc, full=True):
    m = next(m for m in FakeWm.MONS if m["short"] == mon)
    if full:
        rect = [m["x"] - 2, m["y"] - 2, m["w"] + 4, m["h"] + 4]
    else:
        rect = [m["x"], m["y"], m["w"] // 2, m["h"]]
    return {"hwnd": 1, "pid": 777, "proc": proc, "exe": "",
            "title": "", "monitor": mon, "rect": rect}


CFG = {"gaming": {"enabled": True, "threshold_pct": 5.0,
                  "seen_secs": 10.0, "grace_secs": 60.0,
                  "games": ["test.exe"], "ignore": [],
                  "desktop_hz": {},   # UNSET here: the classic
                  # narrative (idle silence, adoption, return-to-60
                  # via the plan default) all belong to UNCONFIGURED
                  # panels. The configured-panel HOLD law gets its
                  # own block at the end - configured means HELD,
                  # always, no adoption, no fighting.
                  "game_hz": {"M1": 240}}}


def main():
    wm = FakeWm()
    clock = Clock()
    gw.wm = wm
    gw.time = clock
    st, ledger = {}, {}
    side = {}                          # the watcher's own memory,
                                       # as loop() would hand it

    def tick(fg=None, gpu=None, enabled=True):
        wm.fg = fg
        CFG["gaming"]["enabled"] = enabled
        n0 = len(CALLS)
        senses = {"mons": FakeWm.MONS, "fg": fg,
                  "gpu": gpu or {}, "xinput": False}
        r_st, plan = gw.tick(st, ledger, CFG, senses=senses,
                             side=side)
        return len(CALLS) - n0, plan

    def ok(name):
        print("ok - %s" % name)

    n, plan = tick()
    assert n == 0 and plan is None and not ledger
    ok("idle desk: zero driver calls")

    n, plan = tick(fg_on("M1", "test.exe"))
    assert n == 1 and CALLS[-1] == ("D1", 2560, 1440, 240)
    assert ledger.get("M1") == ("D1", 2560, 1440, 240)
    ok("trusted fullscreen -> exactly one set, to 240, current res")

    n, plan = tick(fg_on("M1", "test.exe"))
    assert n == 0 and plan is None
    ok("steady game: zero calls (emission discipline)")

    wm.live["D1"] = (2560, 1440, 120)   # exclusive
    n, plan = tick(fg_on("M1", "test.exe"))
    assert n == 0
    ok("exclusive override mid-game: hands off, no fight")

    n, plan = tick()                                   # alt-tab
    assert n == 0 and st.get("mode") == "game"
    clock.t += 30
    n, plan = tick()
    assert n == 0
    ok("alt-tab inside grace: no flicker calls")

    clock.t += 61
    n, plan = tick()
    assert n == 1 and CALLS[-1] == ("D1", 2560, 1440, 60)
    assert not st.get("mode")
    ok("grace expired -> back at the 60 desktop DEFAULT (unset "
       "entry), resolution preserved")

    n, plan = tick()
    assert n == 0
    ok("post-game steady: silent")

    wm.live["D1"] = (2560, 1440, 100)    # user's hand
    n, plan = tick()
    assert n == 0 and ledger["M1"][3] == 100
    ok("manual change while nothing games: adopted, not fought")

    n, plan = tick(fg_on("M1", "video.exe"))          # unlisted,
    n2, plan2 = tick(fg_on("M1", "video.exe"),
                     gpu={777: 1.0})                  # low gpu
    assert n == 0 and n2 == 0 and plan2 is None
    ok("fullscreen video player never looks like a game")

    n, plan = tick(fg_on("M1", "test.exe", full=False))
    assert n == 0
    ok("windowed trusted app: no game mode (covers gate)")

    st.clear()
    n, plan = tick(fg_on("M1", "test.exe"))
    assert n == 1 and ledger.get("M1")
    n, plan = tick(fg_on("M1", "test.exe"), enabled=False)
    assert n == 1 and CALLS[-1] == ("D1", 2560, 1440, 60)
    assert not ledger and not st
    ok("switched off mid-game: booked panel handed back at the "
       "60 desktop default")

    # power plan effector: the game earns the fast plan, leaving
    # gives back the plan that was active BEFORE it
    import awaywatch.power_plan as ppl
    real = (ppl.plans, ppl.active, ppl.set_plan)
    FAST = "a" * 8 + "-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    BAL = "b" * 8 + "-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    cur, PPS = [BAL], []
    ppl.plans = lambda: [{"guid": FAST, "name": "High performance"},
                         {"guid": BAL, "name": "Balanced"}]
    ppl.active = lambda: cur[0]

    def _sp(g):
        PPS.append(g)
        cur[0] = g
        return True
    ppl.set_plan = _sp
    CFG["gaming"]["power_plan"] = "high"
    st.clear()
    ledger.clear()
    side.clear()
    n, plan = tick(fg_on("M1", "test.exe"))
    assert PPS == [FAST], PPS
    clock.t += 10
    n, plan = tick()                        # absence seen, grace runs
    clock.t += 90
    n, plan = tick()                        # grace expired -> out
    assert PPS[-1] == BAL, PPS
    CFG["gaming"]["power_plan"] = ""
    ppl.plans, ppl.active, ppl.set_plan = real
    ok("power plan: game earns the fast plan, leaving gives back "
       "the one that was there first")

    hz = gw.wanted_hz({"game_hz": {}}, "game_hz",
                      {"short": "M2", "rate": 60},
                      ["1920x1080@60", "1920x1080@165"])
    assert hz == 165
    assert gw.wanted_hz({}, "desktop_hz", {"short": "M1", "rate":
                                           144}, ()) == 60
    ok("auto game hz = panel's fastest; desktop unset = 60")

    # the DESKTOP HOLD (the automation the user asked for): with no
    # game up, a CONFIGURED panel sits at its configured rate always,
    # self-healing the Windows-forgets-rates bug (measured: the whole
    # desk answered 60 after the 10-10 reboot). Unconfigured panels
    # stay nobody's business; the hold never fights a live game.
    CFG["gaming"]["desktop_hz"] = {"M2": 165}
    wm.live["D2"] = (1920, 1080, 60)         # the forgotten rate
    n, plan = tick()
    assert n == 1 and CALLS[-1] == ("D2", 1920, 1080, 165), CALLS[-3:]
    assert ledger.get("M2") == ("D2", 1920, 1080, 165)
    n, plan = tick()
    assert n == 0
    ok("not gaming: configured panel held to its rate, then silent")

    # the storm guard: a configured rate the panel's mode list does
    # NOT currently offer (cable swap, driver update) must be parked
    # silently - set_mode would refuse, book the foreign truth, and
    # next tick we'd retry: forever, every 2 s, log line and all.
    CFG["gaming"]["desktop_hz"] = {"M2": 100}   # 100 offered nowhere
    n, plan = tick()
    assert n == 0 and ledger["M2"] == ("D2", 1920, 1080, 165)
    ok("unofferable rate: parked quietly, zero retry storm")
    CFG["gaming"]["desktop_hz"] = {"M2": 165}

    n, plan = tick(fg_on("M1", "test.exe"))
    assert n == 1 and CALLS[-1] == ("D1", 2560, 1440, 240)
    n, plan = tick(fg_on("M1", "test.exe"))
    assert n == 0
    ok("hold stands down while the game owns the desk")
    CFG["gaming"]["desktop_hz"] = {}

    print("GAMING WATCH TESTS OK"
          if os.path.exists(os.path.join(ROOT, "awaywatch",
                                         "gaming.py"))
          else "GAMING WATCH TESTS OK (against CONTRACT SHIM - "
               "engine pending)")


if __name__ == "__main__":
    main()
