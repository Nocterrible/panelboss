"""The identity lanes: bind_profile's ids match, the geometry recovery
(tails moved, stamp re-lands), the none verdicts, the auto opt-in's
store and pass legs, the static ban. Fake rows shaped like
wm.monitors() output; the real desk is never touched."""
import logging
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panelboss import profiles

# the log is a CLAIM here, so it is evidence (the awaymode school)
_recs = []


class _Cap(logging.Filter):
    def filter(self, r):
        _recs.append((r.levelno, r.getMessage()))
        return True


lg = logging.getLogger("profiles")
lg.addFilter(_Cap())
lg.setLevel(logging.DEBUG)
clear = lambda: _recs.clear()
infos = lambda: [m for lv, m in _recs if lv == logging.INFO]
debugs = lambda: [m for lv, m in _recs if lv <= logging.DEBUG]


def live(tail, x, w=3840, h=2160, y=0):
    return {"id": "MONITOR\\REMOTE_Monitor\\%s" % tail,
            "short": "REMOTE_Monitor", "gdi": r"\\.\DISPLAY%d" % x,
            "x": x, "y": y, "w": w, "h": h, "rate": 60, "bits": 32,
            "primary": x == 0}


def saved(tail, x, geom=True, w=3840, h=2160, y=0):
    d = dict(live(tail, x, w, h, y), on=True)
    if geom:
        d["geom"] = "%dx%d@%d,%d" % (w, h, x, y)
    return d
# (a) exact ids: binding answers, NOTHING restamps, no log line.
rows = [saved("0005", 0), saved("0011", 3840)]
clear()
b, lane = profiles.bind_profile(rows, [live("0005", 0),
                                       live("0011", 3840)], "desk")
assert lane == "ids" and sorted(b) == sorted(d["id"] for d in rows)
assert rows[0]["id"].endswith("0005") and not _recs, (rows[0], _recs)
# (b) tails moved (the measured RDP class): the geometry lane binds,
# rows re-stamp to the live tails, the INFO word lands ONCE.
rows = [saved("0005", 0), saved("0011", 3840)]
mons = [live("0011", 0), live("0013", 3840)]
clear()
b, lane = profiles.bind_profile(rows, mons, "desk")
assert lane == "geometry", lane
assert [d["id"] for d in rows] == [mons[0]["id"], mons[1]["id"]], rows
assert sorted(b) == ["MONITOR\\REMOTE_Monitor\\0005",
                     "MONITOR\\REMOTE_Monitor\\0011"], b
assert sum("rebound by geometry" in m for m in infos()) == 1, infos()
assert not any("positional" in m for m in infos()), infos()
# (c) the half-restored desk (2 of 3 live): none, no action, no
# spam - one debug names the miss. (d) same count, different layout
# (rewired AND rearranged): none too - ids moved, else the ids lane
# would answer.
clear()
b, lane = profiles.bind_profile(
    [saved("0005", 0), saved("0011", 3840),
     saved("0013", 7680, w=1920, h=1080)],
    [live("0005", 0), live("0011", 3840)], "desk")
assert b is None and lane == "none" and not infos() and len(debugs()) == 1
clear()
b, lane = profiles.bind_profile(
    [saved("0005", 0), saved("0011", 3840, w=1920, h=1080)],
    [live("0007", 0), live("0009", 3840, w=2560, h=1440)], "desk")
assert b is None and lane == "none" and not infos() and len(debugs()) == 1
# (e) an old profile (no geom stamp): ids lane only - it binds when
# the ids answer, and at the miss one debug word, never a raise.
rows = [saved("0005", 0, geom=False)]
clear()
assert profiles.bind_profile(rows, [live("0005", 0)], "desk")[0] is not None
assert not _recs
clear()
b, lane = profiles.bind_profile(rows, [live("0009", 0)], "desk")
assert b is None and lane == "none" and not infos() and len(debugs()) == 1
# (f) twins (identical signatures - same size AND place): the pairing
# is POSITIONAL, first-occurrence of the lists, and says so.
clear()
b, lane = profiles.bind_profile([saved("0005", 0), saved("0011", 0)],
                                [live("0009", 0), live("0007", 0)], "desk")
assert lane == "geometry"
assert b["MONITOR\\REMOTE_Monitor\\0005"]["id"] == \
    "MONITOR\\REMOTE_Monitor\\0009", b
assert sum("positional" in m for m in infos()) == 1, infos()

# (g) the auto flag round-trips through the EXISTING save path, and
# one auto_pass drive covers the delta-3 leg: tails moved -> the
# geometry lane re-stamps and PERSISTS (id and fp on disk follow),
# the window leg runs, the announcement names lane and count.
tmp = tempfile.mkdtemp()
data = {"last": {}, "profiles": {"desk": {
    "fp": "F", "match": "process", "hdr": "leave alone", "auto": True,
    "displays": [saved("0005", 0)],
    "wins": [{"proc": "opera.exe", "title": "A",
              "rect": [10, 10, 100, 100], "zoomed": False,
              "match": "process"}]}}}
assert profiles.save(data, tmp) and \
    profiles.load(tmp)["profiles"]["desk"]["auto"] is True
placed, pressed = [], []
profiles.wm = types.SimpleNamespace(
    monitors=lambda: [live("0009", 0)],          # the tail MOVED
    list_windows=lambda include_minimized=False: [
        {"proc": "opera.exe", "title": "A", "hwnd": 2,
         "rect": [0, 0, 5, 5], "zoomed": False, "iconic": False}],
    true_rect=lambda hwnd: (0, 0, 5, 5),
    place=lambda hwnd, rect, zoomed=False: (
        placed.append((hwnd, rect, bool(zoomed))), "ok")[1],
    press_keys=lambda combo: pressed.append(combo) or "",
    rescue_lost=lambda: [])
clear()
lines = profiles.auto_pass(profiles.load(tmp), profiles.wm.monitors(),
                           dir=tmp)
assert any("applied by geometry: 1 windows moved" in ln
           for ln in lines), lines
assert placed == [(2, (10, 10, 100, 100), False)] and pressed == []
disk = profiles.load(tmp)["profiles"]["desk"]
assert disk["displays"][0]["id"] == "MONITOR\\REMOTE_Monitor\\0009", disk
assert disk["fp"] == profiles.target_fp(disk["displays"]), \
    "the re-stamp persisted with a stale fingerprint"

# (h) static ban (the awaymode_test window idiom): the auto hook's
# source owns no monitor-setting VERB, and windows-only is the scope
# it calls - the row's UI promise, pinned in source.
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
body = open(os.path.join(root, "panelboss", "profiles.py"),
            encoding="utf8").read()
body = body[body.index("def auto_pass"):]
assert 'scope="windows"' in body
ev = open(os.path.join(root, "panelboss", "state", "_events.py"),
          encoding="utf8").read()
arm = ev[ev.index("def _auto_profiles"):]
arm = arm[:arm.index("\n    def ")]
for window in (body, arm):
    for verb in ("hdr_set(", "hdr_states(", "apply_layout(", "press_keys(",
                 "hdr_", "CDS_", "ChangeDisplaySettings"):
        assert verb not in window, verb
assert ev.count("self._auto_profiles()") == 2, \
    "both arms (displaychange, session_unlock) ride the one hook"
print("IDENTITYLANE lanes OK (ids exact, geometry re-stamp, partial "
      "and mismatch to none, old profiles ids-only, twins positional)")
print("IDENTITYLANE auto OK (flag round-trip, pass drive, windows and "
      "NOTHING else - static ban)")
print("IDENTITYLANE TESTS OK")
