"""THE CONSTELLATION PIN (owner UAT, Oct 15: the settings window died
at birth on every launch since the hider's boot hooks). The disease
needed the PRODUCTION constellation: the hider's painter Tk is born
on a worker thread first, wins tkinter's process-global default root,
and customtkinter - whose ImageTk.PhotoImage passes no master - binds
the window's images to THAT default: `TclError: image "pyimage1"
doesn't exist` inside SettingsWindow.__init__ (the kofi cup was the
first image built, so it was the corpse on every desk). An isolated
window build cannot show it (no second interpreter competes); the
owner's console repro stayed green exactly that way. This probe
builds the constellation ON PURPOSE - painter thread first, window
after - and pins the fix: the painter waits for the window's root,
the window owns the default, and a second-instance poke maps the
window through the tray's own seam and answers in poke_ack.

App-up compatible BY DESIGN (the switch_geom_probe lesson): the live
tray app running alongside changes nothing here - no mutex, no tray,
no camera; the config world lives in a temp dir."""
import os
import queue
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SCRATCH = tempfile.mkdtemp(prefix="panelboss_wboot_")
os.environ["PANELBOSS_CONFIG_DIR"] = SCRATCH

from panelboss import config, hider                    # noqa: E402
from panelboss import profiles as PF                   # noqa: E402
from panelboss import wm as WM                         # noqa: E402
from panelboss import power                            # noqa: E402
from panelboss import camera as cam                    # noqa: E402
from panelboss.state import FrameBox                   # noqa: E402

cfg = config.get_config(verbose=False)
cfg["camera"]["enabled"] = False         # no real cameras in the probe
cfg["ui"]["start_minimized"] = True      # the tray app's birth
cfg["restore"]["enabled"] = False
cfg["gaming"]["enabled"] = False

PF.path = lambda dir=None: os.path.join(SCRATCH, "profiles.json")
_FAKE_DESK = [{"id": "MONITOR\\T", "short": "T",
               "gdi": r"\\.\DISPLAY1", "x": 0, "y": 0, "w": 100,
               "h": 100, "rate": 60, "bits": 32, "primary": True}]
WM.monitors = lambda: [dict(m) for m in _FAKE_DESK]
WM.fingerprint = lambda: "TESTFP"
WM.list_windows = lambda: []
WM.launch = lambda exe: ""
WM.rescue_lost = lambda: []
WM.place = lambda h, r, z=False: "ok"
power.task_installed = lambda: True
cam.optional_present = lambda pkg: False
cam.hello_ir_names = lambda: []

from panelboss.ui import window as W                   # noqa: E402
W.ctk.CTkToplevel._deactivate_windows_window_header_manipulation = True

fm = type("FM", (), {})()
fm.state = "counting"
fm.paused = False
fm.re_off_paused = False
fm.events = queue.Queue()
fm.framebox = FrameBox()
fm.blockers = {"error": None, "display": [], "other": []}


def _hard_kill():
    time.sleep(60)
    print("HARD KILL after 60 s (rc=3 contract)", flush=True)
    os._exit(3)


threading.Thread(target=_hard_kill, daemon=True).start()

FAILED = []


def check():
    import tkinter as tk
    try:
        # the constellation, in the monitor's birth order: hider.boot()
        # on a worker thread, BEFORE any window exists
        threading.Thread(target=hider.boot, daemon=True,
                         name="monitor").start()
        time.sleep(0.3)                    # the worker was FIRST
        app = W.SettingsWindow(cfg, fm, queue.Queue())
        assert app.state() == "withdrawn"
        assert getattr(app, "kofi_button", None) is not None, \
            "the window died at the kofi cup again"
        assert tk._default_root is app, \
            "the default root is not the window (the painter raced it)"
        # the released painter: alive; and its root must NOT take the
        # default now that the window's root holds it
        deadline = time.time() + 5
        while time.time() < deadline:
            if any(t.name == "hider-paint" for t in threading.enumerate()):
                break
            time.sleep(0.05)
        else:
            raise AssertionError("no hider-paint thread after window_ready")
        time.sleep(0.4)
        assert tk._default_root is app, \
            "the painter's root stole the default after the birth"
        # the handoff's winner side: the loser's stamp opens THIS
        # window through the tray's own manual seam and reads the ack
        poke = os.path.join(config.CONFIG_DIR, "poke")
        ack = os.path.join(config.CONFIG_DIR, "poke_ack")
        with open(poke, "a") as _f:      # creating it IS the poke
            os.utime(poke, None)
        app._drain_poke()
        assert app.state() != "withdrawn", "the poke did not open the window"
        assert os.path.getmtime(ack) >= os.path.getmtime(poke) - 0.5, \
            "the poke ack did not land"
        app.destroy()
        print("[PASS] the settings window survives its own constellation "
              "(painter waits, default root is the window, poke opens it)")
    except Exception:
        FAILED.append("check")
        __import__("traceback").print_exc()
    finally:
        try:
            hider.teardown()
        except Exception:
            pass


check()
if FAILED:
    print("WINDOW BOOT UNDER CONSTELLATION FAILED")
    sys.exit(1)
print("WINDOW BOOT UNDER CONSTELLATION OK")
