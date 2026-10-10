"""Offline checks for the monitor-profile MODE EDITOR in the settings
window: the per-panel resolution + refresh menus, the blank-profile
button, the add-monitor picker, and the per-row remove. No real display
is ever asked for a mode (the desk and the driver's offered lists are
fakes); profile writes go to a scratch store so the live profiles
survive. Run with the tray app CLOSED: its CTk windows poison
CTkToplevel in any other process (the window section then skips
itself, exit 0)."""
import ctypes
import json
import os
import queue
import sys

sys.path.insert(0, r"F:\Projects\ICU-PresenceDetector")

from panelboss import config
from panelboss import profiles as PF
from panelboss import wm as WM

cfg = config.get_config(verbose=False)

# config writes go to a scratch file: the window's _save() would
# otherwise rewrite the LIVE config on every widget change
TEST_CFG = os.path.join(os.environ.get("TEMP", "."),
                        "panelboss_test_config.toml")
_saved_wc = config.write_config
config.write_config = lambda c, path=None: _saved_wc(c, TEST_CFG)
try:
    os.remove(TEST_CFG)
except OSError:
    pass

# the monitor-profiles store goes to a scratch file; the desk it sees
# is a fake one (T1/T2 with deterministic offered mode lists). MONITOR\
# OFF is deliberately NOT on the desk, so the editor renders it offline
# (saved values only, 'panel not live', UNVERIFIED on edit).
PF.path = lambda dir=None: os.path.join(os.environ.get("TEMP", "."),
                                        "panelboss_test_profiles.json")
TEST_PROFILES = PF.path()
for _f in (TEST_PROFILES, TEST_PROFILES + ".tmp"):
    try:
        os.remove(_f)
    except OSError:
        pass
_FAKE_DESK = [{"id": "MONITOR\\T1", "short": "T1",
                "gdi": r"\\.\DISPLAY1", "x": 0, "y": 0, "w": 100,
                "h": 100, "rate": 60, "bits": 32, "primary": True},
               {"id": "MONITOR\\T2", "short": "T2",
                "gdi": r"\\.\DISPLAY2", "x": 100, "y": 0, "w": 100,
                "h": 100, "rate": 75, "bits": 32, "primary": False}]
WM.monitors = lambda: [dict(m) for m in _FAKE_DESK]
WM.fingerprint = lambda: "TESTFP"
WM.list_windows = lambda: []
WM.launch = lambda exe: ""
WM.rescue_lost = lambda: []
WM.place = lambda h, r, z=False: "ok"
WM.hdr_states = lambda: [{"gdi": r"\\.\DISPLAY1", "model": "T1",
                          "supported": False, "state": "off",
                          "mode": 0, "precise": True},
                         {"gdi": r"\\.\DISPLAY2", "model": "T2",
                          "supported": False, "state": "off",
                          "mode": 0, "precise": True}]
# two resolutions per panel so the resolution menu has a real choice
# to change (the res-change check needs more than one offered WxH)
WM.offered_modes = lambda gdi, limit=400: (
    ["100x100@60", "100x100@144", "200x200@60", "200x200@144"]
    if gdi == r"\\.\DISPLAY1" else
    ["100x100@75", "100x100@120", "200x200@75", "200x200@120"])
WM.foreground = lambda: None

# pre-seed the store: an 'offline' profile holding only MONITOR\OFF, a
# panel that is NOT on the live desk - the editor renders it offline
_SEED = {"profiles": {
    "offline": {"fp": "manual:offline", "created": 0, "used": 0,
                 "match": "process", "hdr": "snap",
                 "displays": [{"id": "MONITOR\\OFF", "short": "OFF",
                               "gdi": r"\\.\DISPLAY9", "on": True,
                               "primary": True, "x": 0, "y": 0,
                               "w": 640, "h": 480, "rate": 50,
                               "bits": 32, "hdr_cap": None,
                               "hdr_state": None}],
                 "wins": []}}}
with open(TEST_PROFILES, "w", encoding="utf-8") as f:
    json.dump(_SEED, f)

# the window section needs a quiet desktop: with the live app running,
# its CTk windows poison any CTkToplevel a second process opens. The
# tray binary takes the named mutex from cli.py; refuse loudly instead
# of failing red.
_held = None
try:
    ctypes.windll.kernel32.OpenMutexW.restype = ctypes.c_void_p
    _held = ctypes.windll.kernel32.OpenMutexW(0x00100001, False,
                                              "PanelBoss")
except Exception:
    pass
if _held:
    print("SKIP window section: the presence app is running (its CTk")
    print("windows poison CTkToplevel in this process) - close the")
    print("tray app and rerun for the full suite")
    sys.exit(0)

from panelboss.state import FrameBox
from panelboss.ui import window as W

fm = type("FM", (), {})()
fm.state = "counting"
fm.paused = False
fm.re_off_paused = False
fm.events = queue.Queue()
fm.framebox = FrameBox()
fm.blockers = {"error": None, "display": [], "other": []}
W.ctk.CTkToplevel._deactivate_windows_window_header_manipulation = True
app = W.SettingsWindow(cfg, fm, queue.Queue())
FAILED = []


def _fail(where):
    """A raised assert inside an after() callback would otherwise leave
    mainloop running forever; record it, print it, let the chain wind
    down and exit nonzero."""
    FAILED.append(where)
    __import__("traceback").print_exc()


def _store():
    with open(TEST_PROFILES, "rb") as f:
        return json.load(f)


def _texts(widget):
    """every control's text under a widget - the row area is where the
    offline hint and the UNVERIFIED note are painted."""
    out = []
    try:
        out.append(str(widget.cget("text")))
    except Exception:
        pass
    for c in widget.winfo_children():
        out.extend(_texts(c))
    return out


def check():
    try:
        # 1) the window builds; the mode editor (a 'monitors' section
        #    with a status line and an add-monitor picker) appears for
        #    a real profile on the profiles tab
        app._show_tab("monitor profiles")
        app._profile_picked("offline")
        app.update_idletasks()
        assert hasattr(app, "_mode_status"), "_mode_status missing"
        assert hasattr(app, "_mode_add"), "_mode_add missing"
        assert "MONITOR\\OFF" in app._mode_menus, app._mode_menus
        print("[PASS] window builds (mode editor on the profiles tab)")

        # 1b) an offline row offers ONLY its saved values (R2) and shows
        #     a gray 'panel not live' hint in the row area
        off_res, off_rate = app._mode_menus["MONITOR\\OFF"]
        assert str(off_res.cget("values")) == "['640x480']", \
            off_res.cget("values")
        assert str(off_rate.cget("values")) == "['50']", \
            off_rate.cget("values")
        assert any("panel not live" in t for t in _texts(app._prof_detail)), \
            _texts(app._prof_detail)
        print("[PASS] offline row offers saved values only + 'panel not live'")

        # 2) blank button: auto-named profile-N, created + persisted,
        #    and the editor switches to it
        app._prof_blank()
        app.update_idletasks()
        store = _store()
        assert "profile-1" in store["profiles"], list(store["profiles"])
        assert store["profiles"]["profile-1"]["displays"] == [], \
            store["profiles"]["profile-1"]
        assert app._prof_sel == "profile-1", app._prof_sel
        print("[PASS] blank button creates+persists profile-1 and switches")

        # 3) add monitor: the picked live panel is seeded with its
        #    CURRENT (desk) mode and lands in the STORED json. Drive it
        #    through the OptionMenu's OWN dispatch (_command(VALUE)) -
        #    the widget always passes the value, so calling the bare
        #    handler would mask a TypeError arity bug on real picks.
        app._mode_add.set("T2")
        _cmd = getattr(app._mode_add, "_command", None)
        if _cmd is not None:
            _cmd(app._mode_add.get())
        else:
            app._prof_add_commit()
        app.update_idletasks()
        store = _store()
        d2 = [d for d in store["profiles"]["profile-1"]["displays"]
              if d["id"] == "MONITOR\\T2"]
        assert d2, "T2 not added: %r" % store["profiles"]["profile-1"]
        assert (d2[0]["w"], d2[0]["h"], d2[0]["rate"]) == (100, 100, 75), \
            d2
        print("[PASS] add monitor seeds T2's live mode into the stored json")

        # 3b) now that T2 is a row, its resolution menu lists the
        #     offered WxH (R1)
        t2_res, t2_rate = app._mode_menus["MONITOR\\T2"]
        assert str(t2_res.cget("values")).replace(" ", "") == \
            "['100x100','200x200']", t2_res.cget("values")
        print("[PASS] resolution menu lists the offered WxH")

        # 5) a resolution-menu change persists the new WxH
        app._mode_res("MONITOR\\T2", "200x200")
        app.update_idletasks()
        store = _store()
        d2 = [d for d in store["profiles"]["profile-1"]["displays"]
              if d["id"] == "MONITOR\\T2"][0]
        assert (d2["w"], d2["h"]) == (200, 200), d2
        print("[PASS] resolution-menu change persists WxH")

        # 6) a rate change persists the new Hz
        app._mode_rate("MONITOR\\T2", "120")
        app.update_idletasks()
        store = _store()
        d2 = [d for d in store["profiles"]["profile-1"]["displays"]
              if d["id"] == "MONITOR\\T2"][0]
        assert d2["rate"] == 120, d2
        print("[PASS] rate change persists Hz")

        # 7) an offline-id edit persists AND leaves the UNVERIFIED note
        #    visible in the row area (R2)
        app._profile_picked("offline")
        app.update_idletasks()
        app._mode_rate("MONITOR\\OFF", "60")
        app.update_idletasks()
        store = _store()
        doff = store["profiles"]["offline"]["displays"][0]
        assert doff["rate"] == 60, doff
        assert any("UNVERIFIED" in t for t in _texts(app._prof_detail)), \
            _texts(app._prof_detail)
        print("[PASS] offline-id edit persists and shows the UNVERIFIED note")

        # 8) remove drops the row (the last row - the profile goes empty)
        app._profile_picked("profile-1")
        app.update_idletasks()
        app._mode_remove("MONITOR\\T2")
        app.update_idletasks()
        store = _store()
        assert store["profiles"]["profile-1"]["displays"] == [], \
            store["profiles"]["profile-1"]
        print("[PASS] remove drops the row (last row, empty profile)")

        app.destroy()          # the checks are done: end the loop
    except Exception:
        _fail("check")


def _watchdog():
    print("WATCHDOG FIRED after 60 s", flush=True)
    FAILED.append("watchdog")
    app.destroy()


app.after(600, check)
app.after(60000, _watchdog)
app.mainloop()
if FAILED:
    print("WINDOW TEST FAILED in", FAILED)
    sys.exit(1)
print("profiles ui OK")
