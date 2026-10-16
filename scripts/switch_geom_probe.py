"""THE KNOB-GEOMETRY PIN (the knob-lie family's second corpse, the
owner's bar-was-on catch): a CTkSwitch painted while its window is
WITHDRAWN colors its track from truth but can leave the knob at the
zero-width position - the owner screenshotted the consent switch
green-bared, knob-left on a tray-born app. This suite builds the
REAL SettingsWindow in the owner's real birth order (start_minimized:
the window is built and NEVER mapped during the paint), shows it
through the app's own _show_first seam, and asserts every truth
switch's knob at the position a MAPPED control paints - the belt in
_shell.SWITCH_SYNC/_repaint_switches is what the pin pins, so the
ordering it ships (after(0) at the show seam, update_idletasks-then-
reselect inside) is proven on this display, not assumed.

App-up compatible BY DESIGN: the poison class is CTkToplevel's
title-bar dance (a second process's CTk root maps fine with the
live app - measured when this pin was written); the probe never
opens an overrides/setup/sleep toplevel, so it runs inside the
sweep regardless of the tray app."""
import os
import queue
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# the camdiag/virgin idiom: the config world lives in a temp dir
SCRATCH = tempfile.mkdtemp(prefix="panelboss_geom_")
os.environ["PANELBOSS_CONFIG_DIR"] = SCRATCH

from panelboss import config, power
from panelboss import profiles as PF
from panelboss import wm as WM

cfg = config.get_config(verbose=False)
# THE SCENARIO (seeded, never the desk): consent ON is the widget the
# owner screenshotted; one lit and one dark switch per family arm.
cfg["camera"]["enabled"] = True
cfg["power"].update(hold_display=True, hold_sleep=False,
                    restore_windows=False, hdr_off_when_away=True,
                    assistant_task=True)
cfg["guards"]["fullscreen"] = True
cfg["ui"]["start_minimized"] = True      # the tray app's birth
cfg["restore"]["enabled"] = False
cfg["gaming"]["enabled"] = True

# the sibling suites' fake desk: no real display, camera, or store
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
WM.hdr_states = lambda: [{"gdi": r"\\.\DISPLAY1", "model": "T",
                          "supported": True, "state": "off",
                          "mode": 0, "precise": True}]
WM.offered_modes = lambda gdi, limit=400: ["100x100@60"]
power.task_installed = lambda: True       # the truth thread freezes ON
from panelboss import camera as cam
cam.optional_present = lambda pkg: False
cam.hello_ir_names = lambda: []

from panelboss.state import FrameBox
from panelboss.ui import window as W
W.SettingsWindow._scan_cameras = lambda self: None   # no real cameras
W.ctk.CTkToplevel._deactivate_windows_window_header_manipulation = True

fm = type("FM", (), {})()
fm.state = "counting"
fm.paused = False
fm.re_off_paused = False
fm.events = queue.Queue()
fm.framebox = FrameBox()
fm.blockers = {"error": None, "display": [], "other": []}

app = W.SettingsWindow(cfg, fm, queue.Queue())
assert app.state() == "withdrawn", "start_minimized must build unmapped"
# the profiles pane renders its body (restore lever, editor box) via
# its own seam, not the boot build - drive it once HERE (still
# hidden), so those widgets are born at zero geometry exactly like
# the owner's tray-born consent switch. The lever lives in the
# selected-profile fill (a NEW selection skips that half), so create
# a profile first - the same choreography power_assistant_test uses.
app._prof_name.insert(0, "probe desk")
app._profile_create()
app._profiles_render()


def knob(sw):
    """the slider rectangle's canvas bbox - the pixel the owner reads"""
    return sw._canvas.bbox("slider_parts")


LIT = lambda: {"consent": app.consent_switch,
               "hold_display": app.hold_display_switch,
               "fullscreen": app.fullscreen_switch,
               "power": app.power_switch,
               "gaming": app.gaming_switch,
               "min": app.min_switch}
DARK = lambda: {"hold_sleep": app.hold_sleep_switch,
                "restore": app.restore_switch,
                "restorep": app.restorep_switch}
# the editor's open-wish box is a CTkCheckBox (no slider item to
# measure): its arm of the belt repaints paint-state, pinned here
STATE_ONLY = lambda: {"pin_open": app.pin_open_box}

FAILED = []


def check():
    try:
        hidden = {k: knob(sw) for k, sw in LIT().items()}
        # show through the app's OWN seam: _show_first schedules the
        # after(0) resync; the update() pump lands map, <Configure>,
        # and the pending repaint in that order
        app.geometry("1200x820")
        app._show_first(manual=True)
        app.update()
        app._unveil()
        mapped = {k: knob(sw) for k, sw in LIT().items()}
        ctl = app.hold_sleep_switch           # built DARK at hidden birth
        off_x = knob(ctl)
        ctl.select()
        app.update_idletasks()
        app.update()
        on_x = knob(ctl)                      # the mapped control's ON truth
        ctl.deselect()
        app.update_idletasks()
        disease = [k for k, bb in hidden.items()
                   if bb is None or abs(bb[0] - on_x[0]) > 1]
        print("[geom] knob x at hidden build: %s" %
              {k: (bb[0] if bb else None) for k, bb in hidden.items()})
        print("[geom] mapped control: off=%d on=%d | knob-lie reproduced "
              "at hidden build on: %s" % (off_x[0], on_x[0],
                                          disease or "no (scale 1.0 canvas)"))
        for k, sw in LIT().items():           # the belt landed every one
            bb = knob(sw)
            assert bb is not None and abs(bb[0] - on_x[0]) <= 1, \
                "knob %s lies after the belt: %s != control %s" % (k, bb, on_x)
        for k, sw in DARK().items():
            bb = knob(sw)
            assert bb is not None and abs(bb[0] - off_x[0]) <= 1, \
                "dark knob %s drifted: %s != %s" % (k, bb, off_x)
        for k, w in STATE_ONLY().items():
            assert not bool(w.get()), "state-only box %s lit without truth" % k
        # the paint fired no commands (select() is command-free; the
        # drained assistant_truth matches the painted flag):
        assert list(fm.events.queue) == [], list(fm.events.queue)
        assert bool(app.power_switch.get()) is True
        # the tab arm: a truth moves while the window is hidden, the
        # reveal re-syncs from cfg through the SWITCH_SYNC table
        app.withdraw()
        cfg["power"]["hold_display"] = False
        cfg["power"]["hold_sleep"] = True
        app.deiconify()
        app.update()
        app._show_tab("power plan")           # the pane arm of the seam
        app.update()
        assert abs(knob(app.hold_display_switch)[0] - off_x[0]) <= 1, \
            "the reveal kept the stale ON knob"
        assert abs(knob(app.hold_sleep_switch)[0] - on_x[0]) <= 1, \
            "the reveal missed the new ON truth"
        print("[PASS] truth switches paint their knob after they know "
              "their size (show seam + tab arm)")
        # the scroll law (owner UAT, Oct 15): the wheel belongs to the
        # window, not to the value under the cursor - every real slider
        # in the tree hands its canvas's <MouseWheel> back. The walk is
        # the probe's own (the belt ran at show and at the tab reveal
        # above); a bound canvas answers with a callback string, an
        # unbound one with "".
        def _wheel_bound(w):
            bad = []
            if isinstance(w, W.ctk.CTkSlider):
                cv = getattr(w, "_canvas", None)
                if cv is not None and bool(cv.bind("<MouseWheel>")):
                    bad.append(w)
            for c in w.winfo_children():
                bad.extend(_wheel_bound(c))
            return bad
        live = [w for w in _wheel_bound(app)
                if w.winfo_exists() and w.winfo_ismapped()]
        assert not live, \
            "%d live slider(s) still answer the mouse wheel" % len(live)
        print("[PASS] the scroll law: no live slider keeps its "
              "<MouseWheel> binding")
    except Exception:
        FAILED.append("check")
        __import__("traceback").print_exc()


def _hard_kill():
    time.sleep(60)
    print("HARD KILL after 60 s (rc=3 contract)", flush=True)
    os._exit(3)


threading.Thread(target=_hard_kill, daemon=True).start()
check()
for w in (getattr(app, "_overrides_win", None), app):
    try:
        w.destroy()
    except Exception:
        pass
if FAILED:
    print("SWITCH GEOMETRY PIN FAILED in", FAILED)
    sys.exit(1)
print("SWITCH GEOMETRY PIN OK")
