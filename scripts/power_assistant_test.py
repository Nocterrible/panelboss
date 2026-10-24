"""Offline checks for the power assistant: parser, fail-open paths,
state gating, UI wiring. No real UAC: install/uninstall are faked.
THE DESK LAW (the wave-E red): this suite never reads the owner's
live toml - PANELBOSS_CONFIG_DIR moves the whole config world into a
fresh temp dir before panelboss.config is imported (the camdiag/
virgin_boot idiom), so every scenario seeds from the STOCK defaults
(the default-off law is what the window section asserts - the LAW,
not whatever toggles the owner left on the real desk today).
Run with the tray app CLOSED: its CTk windows poison CTkToplevel in
any other process (the window section then skips itself, exit 0).
A wedged Tk loop hard-kills the process at rc=3 - the SAME meaning
gaming_ui_test and the run_all.ps1 exit-code table give it."""
import os
import sys
import tempfile
import threading
import tkinter as tk
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# BEFORE the config import: CONFIG_DIR is read once at module import
# (config.py:41), so the env redirect must come first - late is never
SCRATCH = tempfile.mkdtemp(prefix="panelboss_power_")
os.environ["PANELBOSS_CONFIG_DIR"] = SCRATCH

from panelboss import config, power
from panelboss.state import PresenceMonitor

# 0) silent children: EVERY external helper the windowed app spawns
#    must ride the one no-window door (panelboss/_spawn.py: the
#    CREATE_NO_WINDOW + STARTUPINFO/SW_HIDE belt pair). A windowless
#    parent (pythonw) gets a fresh, VISIBLE console for every
#    console-app child; the user counted the flashes (powershell for
#    camera names, nvidia-smi for the gpu probe - and Oct 13 night's
#    strobe report is why the door replaced per-site flags: a call
#    site cannot forget what it never gets to type). A source-level
#    pin: cheap, and it fails the moment a probe grows without the
#    door; the bare-call ban itself lives in startup_test/gaming_test.
import io as _io
for _f in ("camera.py", "inference.py", "power.py", "power_plan.py",
           "config.py"):
    _src = _io.open(os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "..", "panelboss", _f),
        encoding="utf8").read()
    assert "_spawn.run(" in _src, _f + " spawns outside the no-window door"
print("silent children OK (probes ride the no-window door)")

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
from panelboss.ui import overrides as OV
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
cfg["power"]["skip_camera_when_blocked"] = True   # the feature under
                                                  # test; wave B made the
                                                  # stock False, so the
                                                  # test opts in by hand
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
_real_ti = power.task_installed
try:
    os.remove(os.path.join(os.environ.get("TEMP", "."),
                           "panelboss_test_config.toml"))
except OSError:             # consume fresh, never stale (Oct 12 audit)
    pass
config.write_config = lambda c, path=None: _saved_wc(
    c, os.path.join(os.environ.get("TEMP", "."), "panelboss_test_config.toml"))
power.task_installed = lambda: True         # the belt's oracle, faked
try:
    mon.events.put(("power_assistant", True))
    mon._drain_tray()
    assert cfg["power"]["assistant_task"] is True
    mon.events.put(("power_assistant", False))
    mon._drain_tray()
    assert cfg["power"]["assistant_task"] is False
    # the wave-B belt: a True with no task behind it is a rumor, and
    # rumors do not get written to disk (the adoption breach class)
    power.task_installed = lambda: False
    mon.events.put(("power_assistant", True))
    mon._drain_tray()
    assert cfg["power"]["assistant_task"] is False, "the belt let a rumor through"
finally:
    config.write_config = _saved_wc
    power.task_installed = _real_ti
print("event persistence OK (round trips, and the belt refuses an"
      " unsubstantiated True)")

# 6) window: blockers text renders; switch round-trips through fakes
from panelboss.state import FrameBox
from panelboss.ui import window as W
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
# the UAC after_install leg runs FAKED ELEVATION: no consent dialog can
# be clicked headless, so install/uninstall answer from stubs AND the
# worker's requests() read is canned - the scenario seeds its own truth
# instead of asking a live task store (whose dump mtime would make the
# verdict environment-dependent, the same desk-law class as the toml).
# The marker line says so out loud; the truth-event chain itself still
# runs end to end.
power.requests = lambda ignore=(), assistant=False: {
    "error": None, "display": [], "other": [], "overridden": [],
    "requests": [], "override_entries": []}
print("UAC LEG FAKED: after_install runs on stub install/uninstall and a"
      " canned report (no elevation round trip taken headless)")
# the window also spawns a truth thread that asks the real task store
# for this app's own task name; on a box where that (newly named) task
# is absent the answer is False and _assistant_truth stomps the faked
# install's flag. Same subsystem, same treatment: the store says the
# task is there
power.task_installed = lambda: True
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
                                              "Global\\PanelBoss")
    if not _held:      # the transition belt: an OLD build still
        _held = ctypes.windll.kernel32.OpenMutexW(   # running under
            0x00100001, False, "PanelBoss")           # the bare name
except Exception:
    pass
if _held:
    print("SKIP window section: the presence app is running (its CTk")
    print("windows poison CTkToplevel in this process) - close the")
    print("tray app and rerun for the full suite")
    sys.exit(0)
# the monitor-profiles tab, live in this window: the store goes to a
# scratch file, and the desk it sees is a fake one (one monitor "T",
# two windows) - deterministic rows, and no real display is ever
# asked for anything by this suite
from panelboss import profiles as PF
from panelboss import wm as WM
PF.path = lambda dir=None: os.path.join(os.environ.get("TEMP", "."),
                                        "panelboss_test_profiles.json")
for _f in (PF.path(), PF.path() + ".tmp"):
    try:
        os.remove(_f)
    except OSError:
        pass
_FAKE_DESK = [{"id": "MONITOR\\T", "short": "T",
               "gdi": r"\\.\DISPLAY1", "x": 0, "y": 0, "w": 100,
               "h": 100, "rate": 60, "bits": 32, "primary": True}]
WM.monitors = lambda: [dict(m) for m in _FAKE_DESK]
WM.fingerprint = lambda: "TESTFP"
_FAKE_WINS = [{"proc": "a.exe", "title": "one", "hwnd": 11,
               "rect": [0, 0, 50, 50], "zoomed": False,
               "exe": r"C:\a\a.exe"}]
WM.list_windows = lambda include_minimized=False: [
    dict(w) for w in _FAKE_WINS]
WM.launch = lambda exe: ""
WM.rescue_lost = lambda: []
WM.place = lambda h, r, z=False: "ok"
WM.hdr_states = lambda: [{"gdi": r"\\.\DISPLAY1", "model": "T",
                          "supported": True, "state": "off",
                          "mode": 0, "precise": True}]
# CTkToplevel.__init__ pumps the WHOLE event loop (its titlebar-color
# dance calls withdraw()+update() to force a redraw). Inside the
# synchronous check() chain that re-entrancy runs after_install - and
# its destroy tail - EARLY, killing the app mid-probe (measured). The
# flag skips the dance; the probes never look at titlebars.
W.ctk.CTkToplevel._deactivate_windows_window_header_manipulation = True
app = W.SettingsWindow(cfg, fm, queue.Queue())
# the mode pin below calls _save(); keep the live config out of reach
config.write_config = lambda c, path=None: _saved_wc(
    c, os.path.join(os.environ.get("TEMP", "."), "panelboss_test_config.toml"))
FAILED = []
# check() sets it PAST its last functional assert: a TclError before
# that line skipped asserts still to run and must NOT be tolerated
# (Oct 12 audit: the silent partial - a mid-chain TclError printed
# PASS over a half-checked window)
_done = False


def _fail(where):
    """A raised assert inside an after() callback would otherwise
    leave mainloop running forever (a silent 300 s hang is how this
    suite likes to "fail"); record it, print it, let the chains wind
    down and exit nonzero."""
    FAILED.append(where)
    __import__("traceback").print_exc()


def check():
    global _done
    import time as _clock
    _T0 = _clock.monotonic()
    print("[t] check start", flush=True)
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
        # the measured root cause of "the assistant does not persist").
        # WAVE B rewrote this truth: an OFF flag plus a store True is a
        # SILENT adoption (the flag is consent; the screenshot's breach
        # was the store re-writing True behind it). The honest direction -
        # a lying ON switch meeting a gone task - still self-heals OFF.
        cfg["power"]["assistant_task"] = False
        app.ui_events.put(("assistant_truth", True))
        app._drain_ui_events()
        assert bool(app.power_switch.get()) is False, "silent adoption lit the switch"
        assert cfg["power"]["assistant_task"] is False, "adoption re-wrote True behind the owner"
        assert app.overrides_button.winfo_manager() == "", "silent adoption grew the button"
        cfg["power"]["assistant_task"] = True
        app.power_switch.select()
        app.ui_events.put(("assistant_truth", False))
        app._drain_ui_events()
        assert bool(app.power_switch.get()) is False, "task gone, switch still claims it"
        assert cfg["power"]["assistant_task"] is False, "the truth did not reach cfg"
        assert ("power_assistant", False) in list(fm.events.queue), list(fm.events.queue)
        app._assistant_ui(True)
        assert app.overrides_button.winfo_manager() != "", "button lost"
        app._assistant_ui(False)
        assert app.overrides_button.winfo_manager() == "", "button off-screen"
        app._assistant_ui(True)
        # the detection card's mode segment: window flips -> cfg + event,
        # and a TRAY flip (someone editing the same cfg dict) is mirrored
        # back onto the segment AND the rows by the status tick, without
        # firing command
        rows = dict(app._det_rows)
        assert rows["confidence"].winfo_manager() != "", "person rows"
        assert rows["frame changes"].winfo_manager() == "", \
            "motion knobs hide in person mode"
        app._detect_mode_changed("motion (no AI)")
        assert cfg["detection"]["mode"] == "motion", cfg["detection"]
        assert ("detection_mode", "motion") in list(fm.events.queue), \
            list(fm.events.queue)
        assert rows["device"].winfo_manager() == "", \
            "the model's knobs hide in motion mode"
        assert rows["motion hold"].winfo_manager() != ""
        # a TRAY flip looks like THIS from the window's seat: the cfg
        # dict moved, the segment widget is stale (a direct command
        # call moves neither, and the tray never touches widgets);
        # the status tick must correct segment AND rows together
        cfg["detection"]["mode"] = "person"
        app.mode_button.set("motion (no AI)")
        app._update_status(time.time(), None)
        assert app.mode_button.get() == "person (AI)", app.mode_button.get()
        assert rows["confidence"].winfo_manager() != "", "rows follow"
        # tabs: the layer law (Oct 12 re-cut) - every page is placed
        # for life and exclusivity moved from MANAGER to STACK: the
        # visible tab is the TOP of the body's children (bottom-first
        # list, measured in veil_test). The probe rides
        # _parent_frame.winfo_manager() for shape-agnosticism: the
        # plain-tk host has NO delegation (_parent_frame IS the
        # host), but a probe that asks the placement object through
        # the compat attribute keeps measuring the placed layer even
        # if the host's class ever changes.
        managed = lambda k: app.pages[k]._parent_frame.winfo_manager()
        top = lambda: app._body.winfo_children()[-1]
        app._show_tab("power plan")
        app.update_idletasks()
        assert managed("power plan") == "place"
        assert top() is app.pages["power plan"]
        app._show_tab("detection")
        app.update_idletasks()
        assert managed("detection") == "place"
        assert top() is app.pages["detection"]
        # monitor profiles tab, live in this window (fake desk "T",
        # scratch store): the picker opens on create-new, create
        # captures the desk, pin rows tag the monitor they sit on,
        # ticking saves NOW and unticking forgets, the pickers
        # persist, and the gate reads HARDWARE identity - swap the
        # panel and the profile names its own disappearance.
        print("[t] profiles block +%.1fs" % (
            _clock.monotonic() - _T0), flush=True)
        app._show_tab("monitor profiles")
        app.update_idletasks()
        assert managed("monitor profiles") == "place"
        assert top() is app.pages["monitor profiles"]
        assert app.profile_menu.get() == PF.NEW, app.profile_menu.get()
        assert app.rescue_button.winfo_manager() != ""
        app._prof_name.insert(0, "test desk")
        app._profile_create()
        # THE PUMP LAW (Oct-16 worker-ization): done() lands on a
        # cross-thread after; the selection returns only when it runs.
        _t0p = time.time()
        while time.time() - _t0p < 5.0 and getattr(app, "_applying",
                                                   False):
            app.update()
            time.sleep(0.02)
        app.update_idletasks()
        assert app._prof_sel == "test desk"
        assert "test desk" in app.profile_menu.cget("values")
        prof = app._prof_data["profiles"]["test desk"]
        assert prof["fp"] == "TESTFP"
        assert prof["displays"][0]["short"] == "T"
        assert prof["displays"][0]["hdr_cap"] is True, prof["displays"][0]
        def _ptexts():
            # Oct 12 two-column restructure: the pane's text lives on
            # TWO bodies now - the profile halves on the left, the
            # pin halves (editor fine print included) on the right
            got, stack = [""], [app._prof_detail, app._prof_pins_body]
            while stack:                   # every label/menu text
                w = stack.pop()            # the pane shows
                stack += w.winfo_children()
                try:
                    t = w.cget("text")     # CTkLabel answers cget,
                except Exception:          # OptionMenu answers get
                    try:
                        t = w.get()
                    except Exception:
                        continue
                if isinstance(t, str):
                    got.append(t)
            return got

        app.update_idletasks()
        assert any("hdr off" in t and "T" in t for t in _ptexts()), \
            "live hdr note missing from the monitor row"
        assert app.hdr_menu.get() == "restore as captured (per " \
            "monitor)", app.hdr_menu.get()
        # the label is for humans; the STORED value is the engine's
        app._prof_hdr("all hdr-capable panels off")
        assert prof["hdr"] == "off", prof["hdr"]
        app._prof_hdr("restore as captured (per monitor)")
        assert prof["hdr"] == "snap"
        # the new pin editor: matching defaults to PROCESS (titles
        # lie a hundred times a day), no open wish, no advanced
        # rows until one is asked for
        assert app.match_menu.get() == "process", app.match_menu.get()
        assert app.pin_open_box.get() == 0
        assert not hasattr(app, "pin_wait_menu"), "advanced rows leak"
        # picking the fake window makes it the subject; the editor
        # states the seat it will save
        app._pin_select(("a.exe", "one"))
        app.update_idletasks()
        assert any("will save" in t and "50x50" in t
                   for t in _ptexts()), _ptexts()
        # the wish reveals its advanced half: the wait menu and the
        # browse-to-exe line, plus the honest naive warning
        app.pin_open_box.select()
        app._pin_open()
        app.update_idletasks()
        assert app.pin_wait_menu.get() == "0 s"   # Oct-24: patience
        #                              defaults ZERO - a manual
        #                              restore waits nothing, and
        #                              new rows store the boot
        #                              grace the owner chooses
        assert any("naive" in t for t in _ptexts()), "no fine print"
        # the human who knows better tunes patience and points the
        # pin at the launcher that actually works (browse is faked:
        # the dialog itself is tkinter's own)
        app._pin_wait("90 s")
        assert app._pin_edit["wait"] == 90
        import tkinter.filedialog as _fd
        _real_dialog, _fd.askopenfilename = (
            _fd.askopenfilename, lambda **k: r"C:\stub\launcher.exe")
        app._pin_browse()
        _fd.askopenfilename = _real_dialog
        assert app._pin_edit["exe"] == r"C:\stub\launcher.exe"
        app._pin_commit()
        wins = prof["wins"]
        assert wins and wins[0]["proc"] == "a.exe" and \
            wins[0]["match"] == "process" and wins[0]["open"] is True \
            and wins[0]["wait"] == 90 and \
            wins[0]["exe"] == r"C:\stub\launcher.exe" and \
            wins[0]["rect"] == [0, 0, 50, 50] and \
            wins[0]["monitor"] == "T", wins
        assert os.path.exists(PF.path()), "pin did not reach disk"
        app.update_idletasks()
        got = _ptexts()
        assert any("[open it in 90s]" in t for t in got), got
        assert any("[via launcher.exe]" in t for t in got), got
        # clicking the pinned row pops the pin back into the editor:
        # conditions as saved, and the button now says update
        app._pin_load(wins[0])
        app.update_idletasks()
        assert app._pin_edit["key"] == ("a.exe", "one")
        assert app._pin_edit["wait"] == 90 and \
            app._pin_edit["exe"] == r"C:\stub\launcher.exe"
        assert any("editing: one" in t for t in _ptexts())
        assert any("update pin" in t for t in _ptexts())
        # two windows of the same process open: a process pin must
        # warn it moves ALL of them, not just the picked one
        _FAKE_WINS.append({"proc": "a.exe", "title": "two",
                           "hwnd": 12, "rect": [60, 0, 40, 40],
                           "zoomed": False, "exe": r"C:\a\a.exe"})
        app._pin_select(("a.exe", "two"))
        app.update_idletasks()
        assert any("moves ALL of them" in t for t in _ptexts()), \
            _ptexts()
        app._pin_cancel()
        assert app._pin_edit["pick"] is None and \
            app._pin_edit["key"] is None and app._pin_edit["wait"] == 0
        _FAKE_WINS.pop()                   # the second window closes
        # and x forgets the seat (row=None: the verb takes its
        # full-repaint honest path - Oct 12 made the x's lambda hand
        # the clicked row's frame in for the surgical path)
        app._pin_remove(wins[0], None)
        assert prof["wins"] == []
        app._prof_hdr("on")
        assert prof["hdr"] == "on"
        # loud-once then quiet: _noshows_ask marks declined misses
        # quiet and persists them, so the same failure cannot nag
        # a second time
        app._prof_pin_all()
        assert prof["wins"], "pin-every-app pinned nothing"
        app._noshows_ask([{"proc": "a.exe", "title": "one"}])
        app.update_idletasks()
        kids, stack = [], [app.noshows_dialog]
        while stack:
            w = stack.pop()
            stack += w.winfo_children()
            if w.__class__.__name__ == "CTkButton":
                kids.append(w)
        by = {w.cget("text"): w for w in kids}
        by["let it be"].invoke()
        assert prof["wins"][0].get("quiet") is True, "not marked"
        assert "quiet" in open(PF.path(), encoding="utf-8").read(), \
            "quiet did not reach disk"
        assert PF.default_name(app._prof_data, "TESTFP") == "test desk"
        assert PF.desk_mismatch(prof, WM.monitors()) == ""
        _FAKE_DESK[0]["id"] = "MONITOR\\GONE"
        bad = PF.desk_mismatch(prof, WM.monitors())
        assert "T" in bad and "GONE" in bad, bad
        _FAKE_DESK[0]["id"] = "MONITOR\\T"
        app._rescue_now()
        assert "off screen" in app._prof_msg, app._prof_msg
        print("[t] profiles done +%.1fs" % (
            _clock.monotonic() - _T0), flush=True)
        # the command bar: rescue lives ON the bar now (visible on
        # every tab), Quit owns the far right (pack stacks from the
        # right edge, so the rightmost command is the first child),
        # and sleep is one slider dialog that snoozes only on ok
        # the reskin (UI-1c) wraps the rescue button in a cell frame so
        # its hint line can ride UNDER it; the intent stands: the
        # button lives on the actions bar, one frame deep at most.
        assert app.rescue_button.master.master is app._actions \
            or app.rescue_button.master is app._actions
        kids = app.quit_button.master.winfo_children()
        assert kids[0] is app.quit_button, "Quit is not the far right"
        assert app.sleep_button in kids and app.pause_button in kids
        assert ("snooze", 45) not in list(fm.events.queue)
        dlg = app._sleep_dialog()
        dlg._sld.set(45)
        dlg._go()
        assert ("snooze", 45) in list(fm.events.queue), \
            list(fm.events.queue)
        app._sleep_dialog().destroy()        # cancel just closes
        app._show_tab("detection")
        # tooltips: pin, read, dismiss - the pointer may reach the tip
        app.tips.toggle("hello", app.mode_button)
        app.update_idletasks()
        assert app.tips.tip is not None and app.tips.pinned
        assert app.tips.tip.overrideredirect(), "the note grew a titlebar"
        app.tips.kill()
        assert app.tips.tip is None
        # the hold rows are independent, and wave B darkened both: the
        # default-off law (the owner's screenshot) - stock is off (the
        # tri-state WORD since the Oct 21 wave), the round trip still
        # proves each lives alone, and 'present' rides the same rail
        app._show_tab("power plan")
        assert app.hold_display_choice.get() == "off", \
            "display hold defaults on"
        assert app.hold_sleep_choice.get() == "off", \
            "sleep hold defaults on"
        app._hold_changed("hold_display", "on")
        app._hold_changed("hold_sleep", "on")
        assert cfg["power"]["hold_display"] == "on" and cfg["power"]["hold_sleep"] == "on"
        app._hold_changed("hold_sleep", "off")
        assert cfg["power"]["hold_sleep"] == "off"
        assert cfg["power"]["hold_display"] == "on", "each lives alone"
        app._hold_changed("hold_display", "while present (camera)")
        assert cfg["power"]["hold_display"] == "present", \
            "the third state's label did not land its word"
        app._hold_changed("hold_display", "off")
        assert cfg["power"]["hold_display"] == "off"
        # window restore: wave B darkens it too (it MOVES the owner's
        # windows - a behavior to be wanted), same key, same round trip
        assert not bool(app.restore_switch.get()), "restore defaults on"
        app.restore_switch.deselect()
        app._restore_changed()
        assert cfg["power"]["restore_windows"] is False
        app.restore_switch.select()
        app._restore_changed()
        assert cfg["power"]["restore_windows"] is True
        app._show_tab("detection")
        # update button: the hand-off is cmd + the script + the
        # relaunch promise, then the app quits (its own files are the
        # ones being replaced). the SCRIPT side of the contract is
        # pinned from the file too - the two halves cannot drift.
        script = app.update_script()
        assert script and script.lower().endswith("update.bat"), script
        with open(script, encoding="utf-8") as fh:
            body = fh.read()
        assert 'set "want_relaunch=1"' in body, "relaunch promise gone"
        # the reopening must be WINDOWLESS and identical to run.bat's
        # own launch line - two files, one contract (a test pins them
        # together, so drift between them is a failure, not a surprise)
        launch = ('start "PanelBoss" '
                  '".venv\\Scripts\\pythonw.exe" -m panelboss')
        assert launch in body, "updater relaunch grew a console"
        with open(os.path.join(os.path.dirname(script), "run.bat"),
                  encoding="utf8") as fh:
            assert launch in fh.read(), "run.bat and update.bat drifted"
        popped = []
        real = W.subprocess.Popen
        W.subprocess.Popen = lambda *a, **k: popped.append((a, k))
        try:
            app._update_now()
        finally:
            W.subprocess.Popen = real
        assert popped and popped[0][0][0] == ["cmd.exe", "/c", script,
                                              "relaunch"], popped
        assert ("quit", True) in list(fm.events.queue)
        # optional dependencies: the picker carries hello IR either
        # way - the real groups when whircam lives, an invitation when
        # it does not; choosing the invitation PROMPTS and leaves the
        # camera alone; config pointing at -2 without the bridge asks
        # by itself once; installing = the same updater, deps flag
        from panelboss import camera as cam
        # OWNER MODEL (UI-1e v2): the picker is an ADD widget - the
        # values are ["add a camera...", ...unrostered cams..., IR
        # entries] (on-duty cams own policy rows, not menu lines);
        # picking a cam APPENDS to the roster and the event carries
        # the whole list ("camera", [list]); the bare-int hello-IR
        # sentinel path ("camera", -2) is UNCHANGED. The old pins
        # below retarget from replace-picker to add-picker - no
        # non-camera assertion touched.
        found = [(0, True, 1280, "Integrated Camera"),
                 (1, True, 640, "Logitech Webcam C270")]
        real_present, real_names = cam.optional_present, cam.hello_ir_names
        idx0 = cfg["camera"]["index"]
        cfg["camera"]["index"] = 0
        try:
            cam.optional_present = lambda name: False
            cam.hello_ir_names = lambda: []
            app._apply_cameras(found)
            vals = app.camera_menu.cget("values")
            assert vals[0] == "add a camera...", vals
            assert any(v.startswith("index 1 ") for v in vals), vals
            assert not any(v.startswith("index 0 ") for v in vals), vals
            assert W.SettingsWindow.IR_INSTALL in vals, vals
            app._camera_changed(W.SettingsWindow.IR_INSTALL)
            assert cfg["camera"]["index"] == 0, "invitation is not a camera"
            assert app._dep_win is not None and app._dep_win.winfo_exists()
            app._dep_win.destroy()
            # the add beside the veteran: roster list, list-event,
            # both rows, and the joiner leaves the menu (it is on duty)
            app._camera_changed("index 1 (640 px) Logitech Webcam C270")
            assert cfg["camera"]["index"] == [0, 1], cfg["camera"]["index"]
            assert ("camera", [0, 1]) in list(fm.events.queue), \
                list(fm.events.queue)
            assert set(app._cam_rows) == {0, 1}, sorted(app._cam_rows)
            cam.optional_present = lambda name: True
            cam.hello_ir_names = lambda: ["Windows Hello Contextual Cam"]
            app._apply_cameras(found)
            vals = app.camera_menu.cget("values")
            ir = [v for v in vals if v.startswith("index -2 hello IR")]
            assert ir, vals
            app._camera_changed(ir[0])
            assert cfg["camera"]["index"] == cam.HELLO_IR
            assert ("camera", -2) in list(fm.events.queue)
            cfg["camera"]["index"] = cam.HELLO_IR
            cam.optional_present = lambda name: False
            app._dep_asked = False
            app._apply_cameras(found)
            assert app._dep_win.winfo_exists(), "config said -2, nobody asked"
            popped2 = []
            real = W.subprocess.Popen
            W.subprocess.Popen = lambda *a, **k: popped2.append(a)
            try:
                app._dep_install(switch=False)
            finally:
                W.subprocess.Popen = real
            assert popped2[0][0] == ["cmd.exe", "/c", script, "deps",
                                     "relaunch"], popped2
            assert ("quit", True) in list(fm.events.queue)
            # ---- GHOST LAWS at the picker (the ghost-law build,
            # stage 3). LAW 5: an ADD whose scan row matches exactly
            # one PnP device POPULATES the human-assertion lane (the
            # bind rides the EXISTING camera_identity verb - state
            # owns the toml, re-adoption-by-instance already lives
            # there, the add just signs it at enrol); an ambiguous
            # name binds NOTHING (the deaf badge and the manual bind
            # path own the twins). LAW 4: the duty card reads the
            # monitor's deaf report, and the eye the scan lost gets
            # the card the ROSTER hands it (invisibility was the
            # 00:47 disease). LAW 3 at the dep switch: the about-to-
            # quit write rides the funnel too - no silent in-memory
            # move anywhere the roster lives.
            app._devs = [{"name": "Integrated Camera",
                          "instance": "USB\\VID_INT\\0", "status": "OK"},
                         {"name": "Logitech Webcam C270",
                          "instance": "USB\\VID_LOG\\1", "status": "OK"}]
            cfg["camera"]["index"] = 0
            app._apply_cameras(found)
            before = len(fm.events.queue)
            app._camera_changed("index 1 (640 px) Logitech Webcam C270")
            new = list(fm.events.queue)[before:]
            assert ("camera", [0, 1]) in new, new
            assert cfg["camera"]["index"] == [0, 1], cfg["camera"]["index"]
            assert ("camera_identity",
                    {"instance": "USB\\VID_LOG\\1", "bind": 1}) in new, new
            # the twins: one name, two PnP rows, no honest join, NO claim
            app._devs = [{"name": "Twin Cam", "instance": "USB\\T1",
                          "status": "OK"},
                         {"name": "Twin Cam", "instance": "USB\\T2",
                          "status": "OK"}]
            cfg["camera"]["index"] = 0
            app._cams = [(0, True, 1280, "Twin Cam"),
                         (1, True, 640, "Twin Cam")]
            app._apply_cameras(app._cams)
            before = len(fm.events.queue)
            app._camera_changed("index 1 (640 px) Twin Cam")
            new = list(fm.events.queue)[before:]
            assert ("camera", [0, 1]) in new, new
            assert not [v for v in new if v[0] == "camera_identity"], \
                "the twins got a guessed bind"
            # the badge: a scanned eye wears it on its card...
            app._devs = []
            cfg["camera"]["index"] = [0, 1]
            fm.deaf_indices = lambda: {1: 2}
            app._apply_cameras(found)
            assert "disconnected" in app._cam_rows[1]["title"], \
                app._cam_rows[1]["title"]
            # ...and the eye the scan cannot even answer for gets the
            # whole card from the roster (law 4's own sentence)
            cfg["camera"]["index"] = [0, 1, 2]
            fm.deaf_indices = lambda: {2: 3}
            app._apply_cameras(found)
            assert 2 in app._cam_rows, \
                "the deaf off-scan eye stayed invisible"
            assert "disconnected" in app._cam_rows[2]["title"]
            del fm.deaf_indices                    # the next vote's
            app._apply_cameras(found)              # re-apply clears
            assert "disconnected" not in app._cam_rows[1]["title"], \
                "the badge survived the next vote"
            # the about-to-quit dep switch rides the funnel too
            cfg["camera"]["index"] = 0
            popped3 = []
            real = W.subprocess.Popen
            W.subprocess.Popen = lambda *a, **k: popped3.append(a)
            try:
                app._dep_install(switch=True)
            finally:
                W.subprocess.Popen = real
            assert cfg["camera"]["index"] == cam.HELLO_IR, \
                "the dep switch did not move the roster"
            assert ("camera", -2) in list(fm.events.queue), \
                "the dep switch wrote the dict without a word"
            print("ghost laws OK at the picker (unique add binds, "
                  "twins bind nothing, the deaf card is painted or "
                  "the eye is invisible, the dep switch speaks)")
        finally:
            cam.optional_present, cam.hello_ir_names = real_present, real_names
            cfg["camera"]["index"] = idx0
        # the bat side of the promise: flags in any order, deps wired
        with open(script, encoding="utf8") as fh:
            body = fh.read()
        assert 'set "want_relaunch=1"' in body and 'set "want_deps=1"' in body
        assert "-Optional" in body, "deps flag goes nowhere"
        opt = os.path.join(os.path.dirname(script),
                           "requirements-optional.txt")
        assert os.path.exists(opt), "the deps file the bat installs"
        assert "whircam" in open(opt, encoding="utf8").read()
        # start minimized: the switch mirrors whatever config it was
        # built from - that value is the user's choice, not an
        # invariant (the virgin defaults are pinned offline in
        # layout_test.py). Written for the next boot (the window
        # cannot minimize its own birth)
        app._show_tab("general")
        app.update_idletasks()
        assert bool(app.min_switch.get()) == bool(
            cfg["ui"]["start_minimized"]), "switch betrays its origin"
        app.min_switch.select()
        app._start_min_changed()
        assert cfg["ui"]["start_minimized"] is True
        app.min_switch.deselect()
        app._start_min_changed()
        assert cfg["ui"]["start_minimized"] is False
        # the restore-at-start lever: lives ON THE PROFILES TAB now (it
        # arms profiles, so it lives with them - the user hunted for it
        # there first). rebuilt with the pane, so render fresh here and
        # the probes below face live widgets
        app._profiles_render()
        app.update_idletasks()
        assert bool(app.restorep_switch.get()) == bool(
            cfg["restore"]["enabled"]), "restore lever betrays its origin"
        if cfg["restore"]["enabled"]:        # the live config may
            app.restorep_switch.deselect()   # well have the lever
            app._restorep_changed()          # ARMED (it is a user
            app.update_idletasks()           # setting, not a test
            assert cfg["restore"]["enabled"] is False  # fixture);
        app.restorep_switch.select()                   # normalize
        app._restorep_changed()                        # to OFF
        assert cfg["restore"]["enabled"] is True
        assert app.restorep_warn is not None, \
            "the first-login promise went unspoken at arming"
        stack, kids = [app.restorep_warn], []
        while stack:                       # dismiss it like a human
            w = stack.pop()
            stack += w.winfo_children()
            if w.__class__.__name__ == "CTkButton":
                kids.append(w)
        {w.cget("text"): w for w in kids}["got it"].invoke()
        assert app.restorep_warn is None, "the warning did not go away"
        assert "test desk" in app.restorep_menu.cget("values"), \
            "the login picker cannot see the profiles that exist"
        app._restorep_pick("test desk")
        assert cfg["restore"]["profile"] == "test desk"
        app._restorep_pick("the last one for this desk")
        assert cfg["restore"]["profile"] == "last"
        app._restorep_scope("monitors only (modes + HDR)")
        assert cfg["restore"]["scope"] == "monitors"
        app._restorep_when("every app start")
        assert cfg["restore"]["when"] == "always"
        app.restorep_switch.deselect()
        app._restorep_changed()
        assert cfg["restore"]["enabled"] is False
        cfg["restore"].update(profile="last", scope="full",
                              when="autostart")
        # kofi link: click opens exactly the patron page (opener
        # faked - a test must never really launch a browser), the cup
        # draws itself, and the desk commands now sit on their own row
        # BETWEEN the title and the tabs (geometry proves the order)
        import webbrowser as wb
        opened = []
        orig = wb.open
        wb.open = lambda url: opened.append(url)
        try:
            app._kofi()
        finally:
            wb.open = orig
        assert opened == [W.SettingsWindow.KO_FI], opened
        from panelboss.ui.kofi import kofi_pil
        cup = kofi_pil(20)
        assert cup.mode == "RGBA" and cup.size == (20, 20)
        assert app.kofi_button.winfo_manager() != "", "link not on screen"
        app.update_idletasks()
        assert (app._top.winfo_rooty() <= app._actions.winfo_rooty()
                <= app._tabs_bar.winfo_rooty()), "actions not above tabs"
        assert app.pause_button.winfo_manager() != ""
        w1 = app._show_overrides()
        assert w1 is app._show_overrides(), "second manager window opened"
        app._ov_win = w1
        app.power_switch.select()
        app._power_assistant_changed()
        print("[t] check end +%.1fs" % (
            _clock.monotonic() - _T0), flush=True)
        _done = True                 # teardown noise tolerated ONLY
                                     # past this line, see _done
    except tk.TclError as why:
        if not _done:
            # Oct 12 audit, the silent partial: RDP artifact OR a
            # real window failure - until every functional assert
            # has run, a TclError is a FAILED, not a teardown story.
            FAILED.append("check (TclError before the asserts "
                          "finished: %s)" % str(why)[:60])
            __import__("traceback").print_exc()
        else:
            # RDP artifact (same class as profiles_ui_test, Oct 11):
            # CTk's destroy chain races winfo-vs-interpreter-death
            # under composition latency; every functional check
            # already PASSed and production never re-enters this.
            print("[teardown TclError tolerated: %s]" % str(why)[:60])
    except Exception:
        _fail("check")


_PA_EVS, _PA_AWAIT = [], {"n": 0}


def after_install():
    # Oct-16 workerization: the capture verb walks the desk on a
    # WORKER, so check's tail (where the power-assistant click posts
    # its event) can land AFTER this timer's +1800 ms birthright -
    # re-entrancy that the synchronous era never had. Wait for the
    # event instead of assuming the pump ordering: every hop drains
    # what exists (events accumulate, none may be lost to a discard),
    # the 5 s bound keeps a real loss loud.
    while not fm.events.empty():
        _PA_EVS.append(fm.events.get())
    if ("power_assistant", True) not in _PA_EVS and _PA_AWAIT["n"] < 150:
        # 150 x 100 ms = a 15 s window: the FIRST version of this wait
        # bounded at 5 s and went red ONLY inside the full gauntlet -
        # under 46-suite load check()'s tail (the click that posts the
        # event) legitimately needs seconds it does not spend alone.
        # A standalone run never sees the difference; the watchdog
        # bound (60 s) keeps the ceiling honest (measured Oct 16, the
        # flake's own dossier entry).
        _PA_AWAIT["n"] += 1
        app.after(100, after_install)
        return
    try:
        evs = _PA_EVS
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


def _watchdog():
    print("WATCHDOG FIRED after 60 s", flush=True)
    FAILED.append("watchdog")
    app.destroy()


# hard backstop (gaming_ui_test.py:449-461 shape): if the Tk event
# loop itself stops processing, the after-based watchdog above never
# fires and this process would hang the whole sweep. This daemon
# kills at 120 s with rc=3 - the run_all table's hard-kill code.
def _hard_kill():
    time.sleep(120)
    print("HARD KILL after 120 s: the Tk event loop stopped "
          "processing - killing so the sweep cannot hang",
          flush=True)
    os._exit(3)


threading.Thread(target=_hard_kill, daemon=True).start()

app.after(600, check)
app.after(1800, after_install)
# the watchdog only turns a hang into a loud failure; the profiles
# editor re-renders scrollable panes per click, so the walk needs
# real headroom - a probe timeout is a harness lie, not a bug
app.after(60000, _watchdog)
try:
    app.mainloop()
except tk.TclError:
    pass                     # CTk title-bar re-assert can meet the
                             # destroyed app; see check() above
if FAILED:
    print("WINDOW TEST FAILED in", FAILED)
    sys.exit(1)
print("window OK (blockers render, switch installs via fakes, "
      "manager window behaves)")
print("ALL POWER ASSISTANT TESTS OK")
