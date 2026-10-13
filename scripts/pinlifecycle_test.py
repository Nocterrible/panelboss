"""No-window checks for the profiles pin-lifecycle fixes (Oct 12 audit
follow-up): junk rows die at load(), the login record's times die at
load when unparsable, save() is single-writer across threads, and the
module-level defaults survive a store mutation. PANELBOSS_CONFIG_DIR
points at a fresh temp dir BEFORE importing panelboss.profiles, so the
real store is never read or written. One PASS line per numbered
section; exit 0 is the only green shape (gaming_ui_test's verdict
shape)."""
import json
import logging
import os
import sys
import tempfile
import threading

os.environ["PANELBOSS_CONFIG_DIR"] = tempfile.mkdtemp(
    prefix="panelboss_pinlife_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))

from panelboss import profiles as PF          # noqa: E402

LOGS = []


class _Sink(logging.Handler):
    def emit(self, record):
        LOGS.append(record.getMessage())


_SINK = _Sink()
PF.log.addHandler(_SINK)
PF.log.setLevel(logging.WARNING)

STORE = PF.path()


def _disk():
    with open(STORE, encoding="utf-8") as fh:
        return json.load(fh)


def _wipe_logs():
    del LOGS[:]


def main():
    # 1) junk rows die at load(): a string displays row and a wins
    #    dict missing 'rect' are both dropped with a named warning,
    #    and the returned structures hold only clean dict rows
    data = PF.load(os.environ["PANELBOSS_CONFIG_DIR"])
    data["profiles"]["dirty"] = {
        "displays": [{"id": "MONITOR\\A", "x": 0, "y": 0, "w": 100,
                      "h": 100, "primary": True},
                     "not a row"],
        "wins": [{"proc": "good.exe", "title": "g",
                  "rect": [0, 0, 500, 400]},
                 {"proc": "bad.exe", "title": "b"}]}
    assert PF.save(data, os.environ["PANELBOSS_CONFIG_DIR"])
    _wipe_logs()
    back = PF.load(os.environ["PANELBOSS_CONFIG_DIR"])
    dirty = back["profiles"]["dirty"]
    warns = [m for m in LOGS if "dirty" in m]
    assert len(dirty["displays"]) == 1 and \
        isinstance(dirty["displays"][0], dict) and \
        dirty["displays"][0]["id"] == "MONITOR\\A", dirty["displays"]
    assert len(dirty["wins"]) == 1 and dirty["wins"][0]["proc"] == \
        "good.exe", dirty["wins"]
    assert len(warns) == 2, warns
    print("[PASS] 1: junk displays row and rect-less wins row die at "
          "load, both named, clean rows survive")

    # 2) the login record: unparsable times drop the KEY (not the
    #    section) with a warning; parsable and foreign keys survive
    _wipe_logs()
    data["login"] = {"took": "soon", "launch_delay": 12,
                     "max": 99, "at": 1234.0}
    assert PF.save(data, os.environ["PANELBOSS_CONFIG_DIR"])
    back = PF.load(os.environ["PANELBOSS_CONFIG_DIR"])
    lg = back.get("login")
    assert isinstance(lg, dict) and "took" not in lg, lg
    assert lg.get("launch_delay") == 12.0 and lg.get("max") == 99 and \
        lg.get("at") == 1234.0, lg
    warns = [m for m in LOGS if "login" in m]
    assert len(warns) == 1, warns
    print("[PASS] 2: unparsable login 'took' dropped with a warning, "
          "the section and its other keys survive")

    # 3) save() is single-writer: 16 threads hammer one shared store
    #    through the same locked dump/replace; the file re-parses and
    #    no .tmp litter is left behind
    assert PF.save(data, os.environ["PANELBOSS_CONFIG_DIR"])
    for i in range(16):
        d = dict(data)
        d["marker"] = i
        d["profiles"] = dict(data["profiles"])
        d["profiles"]["t%d" % i] = {"displays": [], "wins": []}
        PF.save(d, os.environ["PANELBOSS_CONFIG_DIR"])
    threads = [threading.Thread(
        target=PF.save, args=(data, os.environ["PANELBOSS_CONFIG_DIR"]))
        for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    reparsed = _disk()
    assert isinstance(reparsed.get("profiles"), dict), reparsed.keys()
    assert PF.save(data, os.environ["PANELBOSS_CONFIG_DIR"])
    litter = [f for f in os.listdir(os.environ["PANELBOSS_CONFIG_DIR"])
              if f.startswith("profiles.json.tmp")]
    assert not litter, litter
    print("[PASS] 3: 16-thread save hammer - the file re-parses, no "
          "profiles.json.tmp litter")

    # 4) a store mutation never reaches the module-level defaults:
    #    load() must hand back a fresh structure every time - the
    #    mutation lands in the loaded store, and the NEXT load (and
    #    the module constants it is built from) stay untouched
    data["login"] = {"took": 1.5}
    data["profiles"]["dirty"]["displays"].append(
        {"id": "MONITOR\\B", "x": 0, "y": 0, "w": 100, "h": 100})
    data["last"] = {"FPX": "dirty"}
    before = (list(PF.MATCH_MODES), PF.LOGIN_DELAY, PF.LOGIN_BUFFER)
    fresh = PF.load(os.environ["PANELBOSS_CONFIG_DIR"])
    assert fresh is not data
    assert fresh.get("login") == {"launch_delay": 12.0, "max": 99,
                                  "at": 1234.0}, fresh.get("login")
    assert len(fresh["profiles"]["dirty"]["displays"]) == 1, \
        fresh["profiles"]["dirty"]["displays"]
    assert fresh.get("last") == {}, fresh.get("last")
    assert (list(PF.MATCH_MODES), PF.LOGIN_DELAY, PF.LOGIN_BUFFER) == \
        before
    data["profiles"]["dirty"]["displays"].clear()
    data["last"].clear()
    data["login"] = "mutated after the load"
    again = PF.load(os.environ["PANELBOSS_CONFIG_DIR"])
    assert again.get("last") == {}, again.get("last")
    assert len(again["profiles"]["dirty"]["displays"]) == 1
    assert again.get("login") == {"launch_delay": 12.0, "max": 99,
                                  "at": 1234.0}, again.get("login")
    print("[PASS] 4: mutating the loaded store leaves the freshly "
          "loaded store (and the module defaults) unchanged")

    print("pinlifecycle OK")


if __name__ == "__main__":
    main()
