"""THE HDR-WAKE FREEZE PIN (the freeze-fix wave, Oct 14): at wake a
WM_DISPLAYCHANGE rides ui_events as hdr_sync, and the drain arm re-reads
the profiles pane's driver truth - live_modes and hdr_states. Against a
COLD driver that walk measured 16-38 s (the class camera.py:56-58 names
for an OPEN; the owner's window died ~20 s at 07:19, back-solved through
the idle-gate arithmetic) - and the arm walked it SYNCHRONOUSLY ON THE
TK PUMP. The camera side learned this driver's resume tax the WARMING
way (0ffa77e); this pin buries the last pump-side holdout, five arms:
  (i)   after the boot render, the pane's driver walks never name
        MainThread;
  (ii)  the pump stayed RESPONSIVE through the walk - >= 5 app.update()
        cycles RETURNED while the stand-ins slept (the freeze signature
        is a stuck pump, not merely a wrong thread name);
  (iii) the payload rides back through the SAME ui_events queue and the
        pane consumes it: the resolution menu carries the LATEST fake
        answer and no older one;
  (iv)  STORM LAW: posts landing during an in-flight walk coalesce -
        three of them are ONE worker call plus ONE latest-wins re-run,
        never a queue of walks;
  (v)   the static ban: the text _profiles_render( may not sit between
        the hdr_sync arm and the next drain arm (the exit-path wave's
        file-ban idiom) - the pump may never walk the driver there.
App-up compatible BY DESIGN (the switch_geom_probe idiom: temp
PANELBOSS_CONFIG_DIR, fake desk, and no CTkToplevel is ever opened). A
wedged pump hard-kills at 60 s with rc=3 - the run_all table's code."""
import os
import queue
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SCRATCH = tempfile.mkdtemp(prefix="panelboss_hdrwake_")
os.environ["PANELBOSS_CONFIG_DIR"] = SCRATCH

from panelboss import config, power
from panelboss import profiles as PF
from panelboss import wm as WM

cfg = config.get_config(verbose=False)
cfg["camera"]["enabled"] = False
cfg["ui"]["start_minimized"] = True      # the tray app's birth
cfg["restore"]["enabled"] = False

# the cold-driver stand-ins: every walk records the THREAD that walked
# it and sleeps 1.5 s; each answer describes a DIFFERENT desk (mode
# marker moves with the call number) so the pane can only be proven to
# have consumed the LATEST payload by seeing that marker and not the
# previous one.
CALLS = []                               # (kind, thread-name)

def _live_modes():
    CALLS.append(("modes", threading.current_thread().name))
    time.sleep(1.5)
    n = sum(1 for k, _ in CALLS if k == "modes")     # this call's number
    # the desk MOVES under every walk: the pane can only be proven to
    # carry the LATEST answer by seeing this call's marker and not the
    # previous call's
    return {"MONITOR\\T": ["100x100@60", "%d00x%d00@60" % (n + 1, n + 1)]}


def _hdr_states():
    CALLS.append(("hdr", threading.current_thread().name))
    time.sleep(1.5)
    on = sum(1 for k, _ in CALLS if k == "hdr") >= 2
    return [{"gdi": r"\\.\DISPLAY1", "model": "T", "supported": True,
             "state": "on" if on else "off", "mode": 2 if on else 0,
             "precise": True}]


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
WM.hdr_states = _hdr_states
WM.offered_modes = lambda gdi, limit=400: ["100x100@60"]
PF.live_modes = _live_modes
power.task_installed = lambda: True
from panelboss import camera as cam
cam.optional_present = lambda pkg: False
cam.hello_ir_names = lambda: []

from panelboss.state import FrameBox
from panelboss.ui import window as W
W.SettingsWindow._scan_cameras = lambda self: None
W.ctk.CTkToplevel._deactivate_windows_window_header_manipulation = True

fm = type("FM", (), {})()
fm.state = "counting"
fm.paused = False
fm.re_off_paused = False
fm.events = queue.Queue()
fm.framebox = FrameBox()
fm.blockers = {"error": None, "display": [], "other": []}

FAILED = []


def check():
    global FAILED
    app = None
    try:
        app = W.SettingsWindow(cfg, fm, queue.Queue())
        app._prof_name.insert(0, "wake desk")
        app._profile_create()            # boot render walked, MainThread
        app._show_tab("monitor profiles")
        app.update()
        base = len(CALLS)

        def pump(seconds):
            """real drain: the tick chain armed in __init__ drains
            ui_events on every due timer; returns the cycle count"""
            n = 0
            t0 = time.time()
            while time.time() - t0 < seconds:
                app.update()
                n += 1
            return n

        # the ride-up, driven through the REAL arm: one post, and while
        # the walk is in flight three more (the storm)
        app.ui_events.put(("hdr_sync", None))
        cycles = pump(1.0)               # the spawn drains here
        for _ in range(3):
            app.ui_events.put(("hdr_sync", None))
        cycles += pump(8.0)              # BOTH walks' sleep windows
                                         # (3 s each, back to back):
                                         # the pump must stay alive
                                         # clean through them
        walk_names = {n for k, n in CALLS[base:]}
        walks = sum(1 for k, _ in CALLS[base:] if k == "modes")

        # (i) after the boot render, the walks never name MainThread
        assert "MainThread" not in walk_names, \
            "the pane walked the driver ON THE PUMP: %s" % sorted(
                walk_names)
        # (ii) the freeze signature is a stuck pump, not just a name
        assert cycles >= 5, \
            "the pump froze during the walk: %d update cycles returned " \
            "in the sleep window (the freeze, measured)" % cycles
        # (iv) STORM LAW: four posts = one walk + one latest-wins re-run
        assert walks == 2, \
            "storm law broken: %d walks for 4 posts (one + one re-run " \
            "is the law)" % walks
        # (iii) the pane consumed the LATEST payload (marker of walk 2;
        # walk 1's marker gone: latest wins, not first lands)
        app.update()
        res_menu = app._mode_menus["MONITOR\\T"][0]
        vals = str(res_menu.cget("values")).replace(" ", "")
        last_n = sum(1 for k, _ in CALLS if k == "modes")   # total
        assert "%d00x%d00" % (last_n + 1, last_n + 1) in vals, \
            "the pane never consumed the walk's payload: %s" % vals
        assert "%d00x%d00" % (last_n, last_n) not in vals, \
            "a superseded payload still paints (latest must win): %s" \
            % vals
        print("[PASS] hdr wake: pump alive through the walk (%d cycles), "
              "%d walks for 4 posts, latest payload consumed (%s)"
              % (cycles, walks, vals))
    except Exception:
        FAILED.append("check")
        __import__("traceback").print_exc()
    finally:
        try:
            if app is not None:
                app.destroy()
        except Exception:
            pass


def ban():
    """(v) the static arm: the pump-side walk is banned from the
    hdr_sync arm's text (file-ban idiom of the exit-path wave)"""
    src = open(os.path.join(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))),
        "panelboss", "ui", "window", "_runtime.py"),
        encoding="utf-8").read()
    a = src.index('if message == "hdr_sync":')
    b = src.index("if message ==", a + 30)
    seg = src[a:b]
    if "_profiles_render(" in seg:
        FAILED.append("ban")
        print("[FAIL] ban: hdr_sync arm still holds _profiles_render("
              " on the pump")


def _hard_kill():
    time.sleep(60)
    print("HARD KILL after 60 s (rc=3 contract)", flush=True)
    os._exit(3)


threading.Thread(target=_hard_kill, daemon=True).start()
check()
ban()
if FAILED:
    print("HDR WAKE PIN FAILED in", FAILED)
    sys.exit(1)
print("HDR WAKE PIN OK")
