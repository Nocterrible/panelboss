"""The identity lanes: bind_profile's ids match, its geometry
recovery (tails moved, stamp re-lands), the none verdicts, and the
auto opt-in's store legs. Offline: fake monitor rows shaped like
wm.monitors() output, a temp dir for the real save path. The real
desk is never touched."""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panelboss import profiles

# the log is a CLAIM here, so it is evidence: every record the lanes
# emit is captured, level and words (the awaymode suite's school)
_recs = []


class _Cap(logging.Handler):
    def emit(self, record):
        _recs.append((record.levelno, record.getMessage()))


_h = _Cap()
_lg = logging.getLogger("profiles")
_lg.addHandler(_h)
_lg.setLevel(logging.DEBUG)


def clear():
    del _recs[:]


def infos():
    return [m for lv, m in _recs if lv == logging.INFO]


def debugs():
    return [m for lv, m in _recs if lv <= logging.DEBUG]


def live(tail, x, w=3840, h=2160, y=0):
    return {"id": "MONITOR\\REMOTE_Monitor\\%s" % tail,
            "short": "REMOTE_Monitor", "gdi": r"\\.\DISPLAY%d" % x,
            "x": x, "y": y, "w": w, "h": h, "rate": 60, "bits": 32,
            "primary": x == 0}


def saved(tail, x, geom=True, w=3840, h=2160, y=0):
    m = live(tail, x, w, h, y)
    d = {"id": m["id"], "short": m["short"], "gdi": m["gdi"],
         "on": True, "primary": m["primary"], "x": x, "y": y,
         "w": w, "h": h, "rate": 60, "bits": 32}
    if geom:
        d["geom"] = "%dx%d@%d,%d" % (w, h, x, y)
    return d


# (a) exact ids: the today-lane. Binding answers, NOTHING restamps,
# and not one log line moves.
rows = [saved("0005", 0), saved("0011", 3840)]
mons = [live("0005", 0), live("0011", 3840)]
clear()
b, lane = profiles.bind_profile(rows, mons, "desk")
assert lane == "ids" and sorted(b) == sorted(d["id"] for d in rows)
assert rows[0]["id"].endswith("0005") and not _recs, (rows[0], _recs)

# (b) tails moved (the measured RDP class: same panels, same places,
# Windows re-minted the instance numbers): the geometry lane binds,
# the rows re-stamp to the live tails, the INFO word lands ONCE.
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
# spam - one debug names the miss and the INFO lane stays silent.
rows = [saved("0005", 0), saved("0011", 3840),
        saved("0013", 7680, w=1920, h=1080)]
mons = [live("0005", 0), live("0011", 3840)]
clear()
b, lane = profiles.bind_profile(rows, mons, "desk")
assert b is None and lane == "none" and not infos() and len(debugs()) == 1

# (d) same count, different layout (the desk was rewired AND
# rearranged): none. Ids moved too, else the ids lane would answer.
rows = [saved("0005", 0), saved("0011", 3840, w=1920, h=1080)]
mons = [live("0007", 0), live("0009", 3840, w=2560, h=1440)]
clear()
b, lane = profiles.bind_profile(rows, mons, "desk")
assert b is None and lane == "none" and not infos() and len(debugs()) == 1

# (e) an old profile (no geom stamp): the ids lane only. It binds
# when the ids answer, and at the miss the geometry lane is one
# debug word - never a raise.
rows = [saved("0005", 0, geom=False)]
clear()
b, lane = profiles.bind_profile(rows, [live("0005", 0)], "desk")
assert lane == "ids" and not _recs
clear()
b, lane = profiles.bind_profile(rows, [live("0009", 0)], "desk")
assert b is None and lane == "none" and not infos() and len(debugs()) == 1

# (f) twin panels whose signatures are IDENTICAL (same size AND
# place - the case geometry alone cannot tell apart): the pairing is
# POSITIONAL, first-occurrence order of the lists, deterministic -
# and says so.
rows = [saved("0005", 0), saved("0011", 0)]
mons = [live("0009", 0), live("0007", 0)]
clear()
b, lane = profiles.bind_profile(rows, mons, "desk")
assert lane == "geometry"
assert rows[0]["id"] == "MONITOR\\REMOTE_Monitor\\0009", rows[0]
assert rows[1]["id"] == "MONITOR\\REMOTE_Monitor\\0007", rows[1]
assert sum("positional" in m for m in infos()) == 1, infos()

print("IDENTITYLANE lanes OK (ids exact, geometry re-stamp, partial "
      "and mismatch to none, old profiles ids-only, twins positional)")
print("IDENTITYLANE TESTS OK")
