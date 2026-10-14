"""the gaming engine offline suite: fake facts, frozen clock, no
ctypes anywhere. Run from repo root:
python scripts/gaming_test.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panelboss import gaming  # noqa: E402

CFG = {"enabled": True, "threshold_pct": 5.0, "seen_secs": 10.0,
       "grace_secs": 60.0, "games": ["listed.exe"], "ignore": []}


def fg(monitor="A", proc="game.exe", pid=100, covers=True):
    return {"fg": {"monitor": monitor, "proc": proc, "pid": pid,
                   "covers": covers}, "gpu": {}, "xinput": False}


def run():
    st = {}

    def ev(f, cfg=None, now=1000.0):
        c = dict(CFG if cfg is None else cfg)
        return gaming.evaluate(f, st, c, now)

    _, plan = ev({"fg": None, "gpu": {}, "xinput": False},
                 cfg={"enabled": False})
    assert plan is None and not st
    print("ok - disabled is a full stop")

    for t in range(0, 60, 5):          # video player forever
        _, p = ev(fg(proc="mpv.exe", pid=7), now=1000.0 + t)
        assert p is None
    print("ok - fullscreen video never qualifies "
          "(no evidence, no list)")

    f = dict(fg(pid=55), gpu={55: 30.0})
    _, p = ev(f, now=1000.0)             # evidence opens a timer
    assert p is None and st.get("seen")  # from ZERO, always
    _, p = ev(f, now=1005.0)             # mid-timer
    assert p is None
    _, p = ev(f, now=1009.0)             # 9 s: still waiting
    assert p is None
    _, p = ev(f, now=1016.0)             # 16 s: entered
    assert p and p["game"]["monitor"] == "A" \
        and "sustained" in p["game"]["reason"]
    print("ok - unlisted evidence must sustain, then enters")

    st.clear()
    _, p = ev(fg(proc="listed.exe", pid=9), now=2000.0)
    assert p and p["game"]["reason"] == "trusted"
    print("ok - listed enters instantly (menu screens)")

    st.clear()
    f = dict(fg(pid=31), xinput=True)
    _, p = ev(f, now=2500.0)
    assert p is None and st.get("seen")
    _, p = ev(f, now=2512.0)
    assert p and "xinput" in p["game"]["reason"]
    print("ok - xinput alone still needs the sustain window")

    st.clear()                           # fresh entry, then three
    _, p = ev(fg(proc="listed.exe", pid=9), now=2999.0)   # steady
    assert p                             # frames: absolute silence
    for _ in range(3):                   # emission discipline
        _, p = ev(fg(proc="listed.exe", pid=9), now=3000.0 + _)
        assert p is None
    print("ok - steady game emits nothing (worker owns re-asserts)")

    st.clear()
    f = dict(fg(pid=11), gpu={11: 30.0})
    _, p = ev(f, now=4000.0)                   # evidence starts...
    assert p is None
    _, p = ev(f, now=4011.0)                   # ...enters sustained
    assert p and st.get("mode") == "game"
    _, p = ev(fg(pid=11), now=4030.0)          # menu: gpu dies
    assert p is None and st["grace_start"] == 4030.0   # grace opens
    _, p = ev(fg(pid=11), now=4089.0)          # still inside grace
    assert p is None and st.get("mode") == "game"
    _, p = ev(f, now=4091.0)                   # evidence returns:
    assert p is None and st["grace_start"] is None   # timer resets
    st.clear()
    ev(fg(proc="listed.exe", pid=9), now=5000.0)
    for t in (5010, 5040, 5069):        # absent: grace starts at
        _, p = ev({"fg": None, "gpu": {}, "xinput": False}, now=float(t))
        assert p is None and st.get("mode") == "game"   # 5010, runs
    _, p = ev({"fg": None, "gpu": {}, "xinput": False}, now=5071.0)
    assert p == {"game": None, "desktop": ["A"]}   # 5010+60 -> out
    _, p = ev({"fg": None, "gpu": {}, "xinput": False}, now=5080.0)
    assert p is None                     # exactly ONE goodbye
    print("ok - grace expires once, then silence")

    st.clear()
    ev(fg(proc="listed.exe", pid=9), now=6000.0)
    _, p = ev(fg(monitor="B", proc="listed.exe", pid=9),
              now=6010.0)
    assert p["game"]["monitor"] == "B" and p["desktop"] == ["A"]
    print("ok - moving panels drops the old one in the same plan")

    st.clear()
    cfg = dict(CFG, games=["listed.exe", "first.exe",
                         "second.exe"])   # handoff is about the
    ev(fg(monitor="B", proc="first.exe", pid=1), cfg=cfg,  # panel,
       now=7000.0)                       # not the evidence story
    _, p = ev(fg(monitor="B", proc="second.exe", pid=2), cfg=cfg,
              now=7010.0)
    assert p["game"]["proc"] == "second.exe" \
        and p["game"]["reason"] == "handoff" and p["desktop"] == []
    print("ok - handoff on the same panel, no fake desktop plan")

    st.clear()
    cfg = dict(CFG, ignore=["listed.exe"])
    for t in range(0, 30, 10):
        _, p = ev(fg(proc="listed.exe", pid=8), cfg=cfg,
                  now=8000.0 + t)
        assert p is None
    print("ok - ignore outranks the list")

    st.clear()
    for t in range(0, 30, 10):
        _, p = ev(fg(proc="listed.exe", pid=8, covers=False),
                  now=9000.0 + t)
        assert p is None
    print("ok - a windowed list is not a game")

    for junk in ({"fg": {"proc": None}, "gpu": None, "xinput": None},
                 {"fg": {}, "gpu": {"x": "y"}}, {}, None):
        s2 = {}
        s2, p = gaming.evaluate(junk, s2, CFG, 10000.0)
    print("ok - junk facts never raise")

    st.clear()
    cfg = dict(CFG, game_hz={"A": "vrr"})   # a vrr-declared panel
    _, p = ev(fg(proc="listed.exe", pid=9), cfg=cfg, now=11000.0)
    assert p is None and st.get("mode") == "game"
    print("ok - vrr: entering a listed game owes no plan at all")
    _, p = ev(fg(proc="listed.exe", pid=9), cfg=cfg, now=11010.0)
    assert p is None and st.get("mode") == "game"
    print("ok - vrr: a steady game stays planless")
    _, p = ev({"fg": None, "gpu": {}, "xinput": False},
              cfg=cfg, now=11100.0)
    assert p is None and st.get("mode") == "game"
    print("ok - vrr: absence only opens the grace, no plan")
    _, p = ev({"fg": None, "gpu": {}, "xinput": False},
              cfg=cfg, now=11171.0)
    assert p is None and not st
    print("ok - vrr: the 71 s expiry owes the panel nothing (no end "
          "plan, zero flash)")

    st.clear()
    cfg = dict(CFG, game_hz={"A": "vrr"})
    ev(fg(proc="listed.exe", pid=9), cfg=cfg, now=12000.0)
    _, p = ev(fg(monitor="B", proc="listed.exe", pid=9), cfg=cfg,
              now=12010.0)
    assert p["game"]["monitor"] == "B" and p["desktop"] == []
    print("ok - vrr: moving panels keeps the old one out of the plan")
    _, p = ev({"fg": None, "gpu": {}, "xinput": False},
              cfg=cfg, now=12080.0)
    assert p is None and st.get("mode") == "game"
    _, p = ev({"fg": None, "gpu": {}, "xinput": False},
              cfg=cfg, now=12171.0)
    assert p == {"game": None, "desktop": ["B"]}
    print("ok - vrr: the expiry hands the SIBLING back; the vrr panel "
          "never appears")

    # THE BAN (owner's strobe report, Oct 13 night): every console
    # verb in the package rides the _spawn door (or an explicitly
    # creation-flagged declared exception - the updater). Scanned
    # here too, offline, so the gaming side carries the law without
    # waiting for the window suite's app-down half.
    import io as _io, os as _os, re as _re, panelboss as _pb
    _pkg = _os.path.dirname(_os.path.abspath(_pb.__file__))
    _bad = []
    for _root, _dirs, _files in _os.walk(_pkg):
        _dirs[:] = [d for d in _dirs if d != "__pycache__"]
        for _fn in _files:
            if not _fn.endswith(".py") or _fn == "_spawn.py":
                continue
            _src = _io.open(_os.path.join(_root, _fn),
                            encoding="utf8").read()
            for _m in _re.finditer(
                    r"subprocess\.(?:run|Popen|call|check_call|"
                    r"check_output)\s*\(|os\.system\s*\(|os\.popen\s*\(",
                    _src):
                if _m.group(0).startswith("os."):
                    _bad.append("%s: raw %s" % (_fn, _m.group(0)))
                elif "creationflags" not in _src[_m.start():
                                                 _m.start() + 300]:
                    _bad.append("%s: bare %s" % (_fn, _m.group(0)))
    assert not _bad, "console verbs outside the door: %s" % _bad

    print("GAMING TESTS OK")


if __name__ == "__main__":
    run()
