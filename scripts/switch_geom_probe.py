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
WM.list_windows = lambda **k: []
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
# THE PUMP LAW (Oct-16 worker-ization): done() lands on a cross-thread
# after; the selection returns only when it runs.
_t0p = time.time()
while time.time() - _t0p < 5.0 and getattr(app, "_applying", False):
    app.update()
    time.sleep(0.02)
app._profiles_render()


def knob(sw):
    """the slider rectangle's canvas bbox - the pixel the owner reads"""
    return sw._canvas.bbox("slider_parts")


LIT = lambda: {"consent": app.consent_switch,
               "fullscreen": app.fullscreen_switch,
               "power": app.power_switch,
               "gaming": app.gaming_switch,
               "min": app.min_switch}
DARK = lambda: {"restore": app.restore_switch,
                "restorep": app.restorep_switch}
# the hold pair left the knob family with the segmented wave (Oct 21):
# a CTkSegmentedButton has no slider to lie about, so its arm of the
# belt is pinned as a SELECTION below (same law: a paint that cannot
# see the truth keeps it stale; the knob geometry arms below cover the
# switches that remain)
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
        ctl = app.restore_switch              # built DARK at hidden birth
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
        # the hold pair's arm of the same law, segmented form (Oct 21):
        # a truth moved in cfg while hidden, the reveal re-selects from
        # it - the bools of the pre-wave shape prove the belt's
        # hold_state mapping too
        assert app.hold_display_choice.get() == "off", \
            "the reveal kept the stale ON selection"
        assert app.hold_sleep_choice.get() == "on", \
            "the reveal missed the new ON truth"
        print("[PASS] truth switches paint their knob after they know "
              "their size (show seam + tab arm)")
        # the scroll law vs the re-sync arm (the consent walker re-arms
        # the wheel on EVERY cameras post): the law must survive the
        # app's own paint cycle, and a hidden bound slider is a
        # landmine the mode picker re-arms.
        app.ui_events.put(("cameras", []))
        app._drain_ui_events()
        def _law_sliders(w):
            out = [w] if isinstance(w, W.ctk.CTkSlider) and \
                getattr(w, "_canvas", None) is not None and \
                bool(w._canvas.bind("<MouseWheel>")) else []
            for c in w.winfo_children():
                out.extend(_law_sliders(c))
            return out
        live = [s for host in app.pages.values()
                for s in _law_sliders(host.inner)]
        assert not live, \
            "%d slider(s) answer the mouse wheel after a consent re-sync" \
            % len(live)
        print("[PASS] the scroll law: no slider keeps its "
              "<MouseWheel> binding across the app's own re-sync")
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
