"""Offline checks for the power assistant: parser, fail-open paths,
state gating, UI wiring. No real UAC: install/uninstall are faked.
Run with the tray app CLOSED: its CTk windows poison CTkToplevel in
any other process (the window section then skips itself, exit 0)."""
import os
import sys
import time

sys.path.insert(0, r"F:\Projects\ICU-PresenceDetector")

from awaywatch import config, power
from awaywatch.state import PresenceMonitor

SAMPLE = """Power Request Sources:

DISPLAY:
	None.

SYSTEM:
	[PROCESS] AudioSrv.exe
		AUDIO

DISPLAY:
	[PROCESS] msedgewebview2.exe
		Video Wake Lock
	PROCESS 0x9999 explorer.exe presentation
"""

# 1) parser: new uppercase format, [PROCESS] prefix stripped, None
#    skipped, sections bucketed by name
parsed = power._parse(SAMPLE)
assert parsed["error"] is None
assert any("msedgewebview2.exe" in x for x in parsed["display"]), parsed
assert any("explorer.exe" in x for x in parsed["display"]), parsed
assert not any(x.startswith("[PROCESS]") for x in parsed["display"])
assert any("AUDIO" in x for x in parsed["other"]), parsed
print("parser OK:", parsed["display"], "|", parsed["other"])

# 1b) the REAL flat dump off this machine: reason lines pair into the
#     entry above them (one per entry), \Device\ volume noise trimmed,
#     [DRIVER] kept as the who-is-it hint, a marker with no reason
#     (Legacy Kernel Caller) stands alone
LIVE = r"""DISPLAY:
[PROCESS] \Device\HarddiskVolume8\Users\user\AppData\Local\Programs\Opera GX\opera.exe
Video Wake Lock

SYSTEM:
[DRIVER] SteelSeries Sonar Virtual Audio Device (ROOT\MEDIA\0000)
An audio stream is currently in use.
[DRIVER] Legacy Kernel Caller

AWAYMODE:
None.
"""
live = power._parse(LIVE)
assert any(x == "Users\\user\\AppData\\Local\\Programs\\Opera GX"
               "\\opera.exe - Video Wake Lock"
           for x in live["display"]), live["display"]
assert not any("HarddiskVolume" in x
               for x in live["display"] + live["other"]), live
assert any(x == "SYSTEM: [DRIVER] SteelSeries Sonar Virtual Audio "
                "Device (ROOT\\MEDIA\\0000) - An audio stream is "
                "currently in use." for x in live["other"]), live["other"]
assert any(x == "SYSTEM: [DRIVER] Legacy Kernel Caller"
           for x in live["other"]), live["other"]
assert not any("None" in x or "AWAYMODE" in x
               for x in live["display"] + live["other"]), live
print("flat-format parser OK:", live["display"], "|", live["other"])

# 1c) manual powercfg -requestsoverride entries demote their holders:
#     out of the gating buckets, back as grey "*OVERRIDE ..." lines
OVR = ("[PROCESS]\n\nmsedgewebview2.exe DISPLAY\n\n[DRIVER]\n"
       "SteelSeries Sonar Virtual Audio Device SYSTEM\n")
res = power._report(SAMPLE + "\n" + power.OVERRIDE_MARK + "\n" + OVR)
assert any(x.startswith("*OVERRIDE") and "msedgewebview2" in x
           for x in res["overridden"]), res
assert not any("msedgewebview2" in x for x in res["display"]), res
assert any("explorer.exe" in x and not x.startswith("*")
           for x in res["display"]), res
res2 = power._report(LIVE + "\n" + power.OVERRIDE_MARK + "\n" + OVR)
assert any(x.startswith("*OVERRIDE") and "SteelSeries" in x
           for x in res2["overridden"]), res2
assert not any("SteelSeries" in x for x in res2["other"]), res2
assert any("Legacy Kernel Caller" in x for x in res2["other"]), res2
assert any("opera.exe" in x for x in res2["display"]), res2  # untouched
print("override demotion OK:", res["overridden"], "|", res2["overridden"])

# 1d) manager model: powercfg needs structured caller/object/request,
#     the pair consolidates into ONE row, and the elevated script
#     quotes like the entries powercfg itself lists
e_ms = [e for e in res["requests"] if "msedgewebview2" in e["text"]][0]
assert e_ms["caller"] == "process" and e_ms["object"] == "msedgewebview2.exe"
assert e_ms["request"] == "DISPLAY" and e_ms["overridden"] is True
e_dr = [e for e in res2["requests"] if "SteelSeries" in e["text"]][0]
assert e_dr["caller"] == "driver" and e_dr["request"] == "SYSTEM"
assert e_dr["object"] == "SteelSeries Sonar Virtual Audio Device"
assert e_dr["overridden"] is True
assert any(o["name"] == "steelseries sonar virtual audio device"
           and "SYSTEM" in o["types"] and o["cat"] == "driver"
           for o in res2["override_entries"]), res2["override_entries"]
script = power.apply_script([
    {"caller": "process", "object": "opera.exe", "types": ["DISPLAY"]},
    {"caller": "driver", "object": "Legacy Kernel Caller", "types": []},
    {"caller": "process", "object": "dual.exe",
     "types": ["DISPLAY", "SYSTEM"]}])
lines = script.splitlines()
# one set per object carrying the COMPLETE wanted typelist (survivors
# re-listed, because the set form REPLACES); empty = clear (measured:
# the documented DELETE keyword does not exist, and the empty set
# form deletes the registry value outright)
assert ('& powercfg.exe /requestsoverride PROCESS "opera.exe" DISPLAY'
        in lines), script
assert ('& powercfg.exe /requestsoverride DRIVER "Legacy Kernel Caller"'
        in lines), script
assert ('& powercfg.exe /requestsoverride PROCESS "dual.exe" DISPLAY SYSTEM'
        in lines), script
from awaywatch.ui import overrides as OV
seen = OV.merge_seen({}, res2)
steel = next(g for g in seen.values() if "SteelSeries" in g["label"])
assert steel["overridden"] == {"SYSTEM"}, seen   # one row saying both
assert steel["active"] == {"SYSTEM"}, seen
opera = next(g for g in seen.values() if "opera.exe" in g["label"])
assert opera["overridden"] == set() and opera["active"] == {"DISPLAY"}, seen
web = next(g for g in seen.values() if g["object"] == "msedgewebview2.exe")
assert web["overridden"] == {"DISPLAY"} and web["active"] == set(), seen
lkc = next(g for g in seen.values() if "Legacy Kernel" in g["label"])
assert lkc["overridden"] == set() and lkc["active"] == {"SYSTEM"}, seen
# accumulation: a later read where an object VANISHED keeps its row
# (active latches) but the override truth is gone - the listing is
# complete every time
seen = OV.merge_seen(seen, {"requests": [], "override_entries": []})
assert len(seen) == 4, seen
assert steel["active"] == {"SYSTEM"} and steel["overridden"] == set(), seen
# and a brand-NEW holder in a later read folds in on refresh
seen = OV.merge_seen(seen, {"requests": [
    {"caller": "process", "object": "newbie.exe", "request": "DISPLAY",
     "text": "newbie.exe", "overridden": False}],
    "override_entries": []})
assert any("newbie.exe" in g["label"] for g in seen.values()), seen
# multi-type entries and a drop type: perfboost shows but the set
# form cannot express it (measured: DISPLAY PERFBOOST stored 0x1)
seen2 = OV.merge_seen({}, {"requests": [], "override_entries": [
    {"cat": "process", "name": "dual.exe",
     "types": {"DISPLAY", "SYSTEM", "PERFBOOST"}}]})
d = next(iter(seen2.values()))
assert d["overridden"] == {"DISPLAY", "SYSTEM", "PERFBOOST"}, d
assert d["drops"] == {"PERFBOOST"}, d
print("override manager model OK (%d objects seen)" % len(seen))

# 2) live machine, unelevated, no assistant: explicit admin message
r = power.requests()
assert r["error"] and "administrator privileges" in r["error"], r
assert r["display"] == [] and r["other"] == []
print("unelevated fail-open OK:", r["error"])

# 3) assistant on but task never registered: honest "not reported"
#    (point the dump path at nowhere - a machine WITH the assistant
#    installed has a real, current file there)
_real_rp = power.result_path
power.result_path = lambda: os.path.join(os.environ.get("TEMP", "."),
                                         "absent", "power_requests.txt")
try:
    r = power.requests(assistant=True)
finally:
    power.result_path = _real_rp
assert r["error"] and "not reported yet" in r["error"], r
print("assistant-uninstalled path OK:", r["error"][:60], "...")

# 4) state gate: display holders pause polling and wipe the running
#    absence count; clearing them resumes it
cfg = config.get_config(verbose=False)
cfg["power"]["assistant_task"] = False
calls = {"poll": 0, "requests": 0}


class StubDetector:
    conf = 0.45

    def detect(self, frame, conf=None):
        return __import__("numpy").empty((0, 4)), __import__("numpy").empty((0,))


mon = PresenceMonitor(cfg, StubDetector())
mon.state = "counting"
mon.absent_since = 90.0
mon.next_poll = 100.0                     # due the moment the gate opened


def fake_poll():                          # no camera needed
    calls["poll"] += 1
    return False, 0.0


mon._poll = fake_poll
real_requests = power.requests


def counted(result):
    def inner(ignore=(), assistant=False):
        calls["requests"] += 1
        return result
    return inner


blocked = {"error": None, "display": ["msedgewebview2.exe"], "other": []}
power.requests = counted(blocked)
try:
    mon._on_phase(100.0, 45.0)            # gate open, poll due
    assert calls["poll"] == 0, "blocked must not poll"
    assert mon.absent_since is None, "blocked must wipe the absence count"
    assert mon.next_poll == 100.0 + cfg["power"]["poll_sec"]
    mon._on_phase(101.0, 46.0)            # throttle: not requests again
    assert calls["requests"] == 1, calls
    mon._on_phase(110.0, 55.0)            # still blocked: retry, no poll
    assert calls["requests"] == 2, calls
    mon.blockers = {"error": None, "display": [], "other": []}
    mon.next_poll = 110.0
    mon._on_phase(110.0, 55.0)
    assert calls["poll"] == 1, "unblocked must poll again"
finally:
    power.requests = real_requests
print("state gate OK (blocked waits, absence resets, throttle, resume)")

# 5) events: power_assistant opt-in persists into the shared cfg -
#    but _drain_tray calls write_config(cfg) with NO path, so left to
#    itself this test scribbles assistant_task=false over the LIVE
#    config every run (measured: it did, and the next instance booted
#    assistant-off while the task sat Ready, feeding the pane stale
#    admin errors). Redirect every write to a scratch file.
_saved_wc = config.write_config
config.write_config = lambda c, path=None: _saved_wc(
    c, os.path.join(os.environ.get("TEMP", "."), "icu_test_config.toml"))
try:
    mon.events.put(("power_assistant", True))
    mon._drain_tray()
    assert cfg["power"]["assistant_task"] is True
    mon.events.put(("power_assistant", False))
    mon._drain_tray()
    assert cfg["power"]["assistant_task"] is False
finally:
    config.write_config = _saved_wc
print("event persistence OK")

# 6) window: blockers text renders; switch round-trips through fakes
from awaywatch.state import FrameBox
from awaywatch.ui import window as W
import queue

fm = type("FM", (), {})()
fm.state = "counting"
fm.paused = False
fm.re_off_paused = False
fm.events = queue.Queue()
fm.framebox = FrameBox()
fm.blockers = {"error": None, "display": ["msedgewebview2.exe Video Lock"],
               "other": ["System: AudioSrv AUDIO"]}
power.install = lambda: (True, "registered (test)")
power.uninstall = lambda: (True, "assistant removed (test)")
# the window section needs a quiet desktop: with the live app running,
# its CTk windows poison any CTkToplevel a second process opens - both
# window runs today died inside CTkToplevel.__init__ with "can't
# invoke bind command: application has been destroyed" while the exact
# same steps passed with the tray app closed. The tray binary takes
# the named mutex from cli.py; refuse loudly instead of failing red.
import ctypes
_held = None
try:
    ctypes.windll.kernel32.OpenMutexW.restype = ctypes.c_void_p
    _held = ctypes.windll.kernel32.OpenMutexW(0x00100001, False,
                                              "ICU-Presence-Detector")
except Exception:
    pass
if _held:
    print("SKIP window section: the presence app is running (its CTk")
    print("windows poison CTkToplevel in this process) - close the")
    print("tray app and rerun for the full suite")
    sys.exit(0)
app = W.SettingsWindow(cfg, fm, queue.Queue())
FAILED = []


def _fail(where):
    """A raised assert inside an after() callback would otherwise
    leave mainloop running forever (a silent 300 s hang is how this
    suite likes to "fail"); record it, print it, let the chains wind
    down and exit nonzero."""
    FAILED.append(where)
    __import__("traceback").print_exc()


def check():
    try:
        fm.blockers = res2                       # structured: the manager
        app._update_blockers()                   # pane reads it too
        text = app.blockers_box.get("1.0", "end")
        assert "holding the display" in text and "opera.exe" in text, text
        assert "*OVERRIDE" in text and "SteelSeries" in text, text
        fg = app.blockers_box._textbox.tag_cget("danger", "foreground")
        assert str(fg).lower().startswith("#"), ("danger tag uncolored", fg)
        # scrollable-ness: identical content must NOT touch the box -
        # delete+insert rewinds the view to the top, and the tick loop
        # re-rendered every ~0.5 s, so the pane was un-scrollable
        # (user-confirmed); a REAL change must still rewrite
        inner = app.blockers_box._textbox
        deletes = []
        _real_delete = inner.delete
        inner.delete = lambda *a, **k: (deletes.append(a),
                                        _real_delete(*a, **k))[1]
        app._update_blockers()                     # same blockers again
        assert deletes == [], "identical text rewrote the box"
        fm.blockers = {"error": None, "display": ["newlock.exe X"],
                       "other": []}
        app._update_blockers()                     # genuine change
        assert deletes, "changed text did not rewrite the box"
        assert "newlock.exe" in app.blockers_box.get("1.0", "end")
        inner.delete = _real_delete
        fm.blockers = res2                         # RESTORE the real
                                                   # dump: the manager
                                                   # window opens below
                                                   # and merges from here
                                                   # (a leaked minimal
                                                   # dict = no SteelSeries
                                                   # = StopIteration, and
                                                   # its teardown cascade)
        # the truth-bridge: a worker thread's answer rides ui_events (its
        # self.after(0) could land BEFORE app.mainloop exists and die with
        # "main thread is not in main loop", pythonw eating the traceback -
        # the measured root cause of "the assistant does not persist")
        app.ui_events.put(("assistant_truth", True))
        app._drain_ui_events()
        assert bool(app.power_switch.get()) is True, "truth did not reach switch"
        assert cfg["power"]["assistant_task"] is True, "truth did not reach cfg"
        # the manager button lives and dies with the assistant
        assert app.overrides_button.winfo_manager() != "", "button lost"
        app._assistant_ui(False)
        assert app.overrides_button.winfo_manager() == "", "button off-screen"
        app._assistant_ui(True)
        w1 = app._show_overrides()
        assert w1 is app._show_overrides(), "second manager window opened"
        app._ov_win = w1
        app.power_switch.select()
        app._power_assistant_changed()
    except Exception:
        _fail("check")


def after_install():
    try:
        evs = []
        while not fm.events.empty():
            evs.append(fm.events.get())
        assert ("power_assistant", True) in evs, evs
        assert cfg["power"]["assistant_task"] is True
        ow = app._ov_win
        steel = next(g for g in ow.seen.values()
                     if "SteelSeries" in g["label"])
        ow._toggled(steel["key"], "DISPLAY", True)   # a second type
        ops = ow._diff()
        assert ops == [{"caller": "driver", "object": steel["object"],
                        "types": ["DISPLAY", "SYSTEM"]}], ops
        # (SYSTEM survives the REPLACE - the whole wanted list ships)
        assert ow.save_button.winfo_manager() != "", "apply button hid"
        ow._toggled(steel["key"], "DISPLAY", False)  # back out
        assert ow._diff() == [], ow._diff()
        assert ow.save_button.winfo_manager() == "", "apply button overstayed"
        ow._toggled(steel["key"], "SYSTEM", False)   # empty the last box
        assert ow._diff()[0]["types"] == [], ow._diff()
        # refresh accumulates without forgetting: a new object folds
        # in, latched 'held' survives, override truth wins
        ow._merged({"requests": [
            {"caller": "process", "object": "newbie.exe",
             "request": "EXECUTION", "text": "newbie.exe",
             "overridden": False}],
            "override_entries": []})
        assert any("newbie.exe" in g["label"] for g in ow.seen.values())
        assert ow.seen[steel["key"]]["active"] == {"SYSTEM"}   # latched
        assert ow.seen[steel["key"]]["overridden"] == set()    # truth
    except Exception:
        _fail("after_install")
    finally:
        for w in (getattr(app, "_ov_win", None), app):
            try:
                w.destroy()
            except Exception:
                pass


app.after(600, check)
app.after(1800, after_install)
app.after(20000, lambda: (FAILED.append("watchdog"), app.destroy()))
app.mainloop()
if FAILED:
    print("WINDOW TEST FAILED in", FAILED)
    sys.exit(1)
print("window OK (blockers render, switch installs via fakes, "
      "manager window behaves)")
print("ALL POWER ASSISTANT TESTS OK")
