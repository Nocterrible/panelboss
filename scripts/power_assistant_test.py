"""Offline checks for the power assistant: parser, fail-open paths,
state gating, UI wiring. No real UAC: install/uninstall are faked."""
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

# 2) live machine, unelevated, no assistant: explicit admin message
r = power.requests()
assert r["error"] and "administrator privileges" in r["error"], r
assert r["display"] == [] and r["other"] == []
print("unelevated fail-open OK:", r["error"])

# 3) assistant on but task never registered: honest "not reported"
r = power.requests(assistant=True)
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

# 5) events: power_assistant opt-in persists into the shared cfg
mon.events.put(("power_assistant", True))
mon._drain_tray()
assert cfg["power"]["assistant_task"] is True
mon.events.put(("power_assistant", False))
mon._drain_tray()
assert cfg["power"]["assistant_task"] is False
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
app = W.SettingsWindow(cfg, fm, queue.Queue())


def check():
    fm.blockers = {"error": None, "display": ["msedgewebview2.exe Lock"],
                   "other": []}
    app._update_blockers()
    text = app.blockers_label.cget("text")
    assert "holding the display" in text and "msedgewebview2" in text, text
    app.power_switch.select()
    app._power_assistant_changed()


def after_install():
    evs = []
    while not fm.events.empty():
        evs.append(fm.events.get())
    assert ("power_assistant", True) in evs, evs
    assert cfg["power"]["assistant_task"] is True
    app.destroy()


app.after(600, check)
app.after(1800, after_install)
app.mainloop()
print("window OK (blockers render, switch installs via fakes)")
print("ALL POWER ASSISTANT TESTS OK")
