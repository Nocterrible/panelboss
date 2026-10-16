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
        # the reskin pin (UI-1c, owner Oct 15): the built oled tab
        # carries its four card titles verbatim - the rename is
        # proven by the suite, not by eyes on an RDP bitmap. Exact
        # label texts only (the status line legitimately carries
        # "video-dim off" words from the module's own say()).
        _t = []

        def _titles(w):
            for c in w.winfo_children():
                try:
                    x = c.cget("text")
                except Exception:
                    x = None
                if isinstance(x, str) and x:
                    _t.append(x)
                _titles(c)
        _titles(app.pages["oled"].inner)
        for want in ("taskbar hider", "panel refresh",
                     "background dimmer", "Movie theater mode"):
            assert want in _t, "the oled tab lost the %r card" % want
        assert "video-dim" not in _t and "Video-dim" not in _t, \
            "the renamed card still answers an old title label"
        # THE PLACEMENT TRIO (owner request, Oct 16): the top bar's
        # actions row carries BOTH window verbs as standalone buttons,
        # rescue FIRST and restore SECOND - exact labels only (the
        # owner's status-line lesson: no substring checks), and the
        # order is pinned by the children list, not by a set. The tray
        # menu is faked here (no pystray pump in this probe), so its
        # half of the pin lands in profiles_ui_test instead.
        _kids = app._actions.winfo_children()
        _labels = []
        for _c in _kids:
            try:
                _x = _c.cget("text")
            except Exception:
                _x = None
            if isinstance(_x, str) and _x:
                _labels.append(_x)
            for _g in _c.winfo_children():
                try:
                    _y = _g.cget("text")
                except Exception:
                    _y = None
                if isinstance(_y, str) and _y:
                    _labels.append(_y)
        assert "rescue my lost windows" in _labels and \
            "restore my windows" in _labels, \
            "the actions row lost a window verb: %r" % _labels
        _ri = _labels.index("rescue my lost windows")
        _oi = _labels.index("restore my windows")
        assert _ri < _oi, \
            "the actions row must keep rescue first, restore second"
        # --- the capture-freeze doses, pinned (Oct-16, py-spy proven).
        #     (a) dose 1, the timeout route: a Tk toplevel IS an own-
        #     process window, so win_title takes the SendMessage branch
        #     for real - a wrong ctypes shape raises or lies; and a
        #     deaf answer must fall to the honest empty. (b) dose 3:
        #     skin.font holds a STRONG ref (a main-interpreter Font
        #     finalized on a worker thread is the frame that froze
        #     hider-paint). The window here is the Tk root for both.
        #     (c) dose 2's visible lock: capture shares the apply
        #     button list, or the worker-ized verb runs un-locked.
        from panelboss.ui import theme
        from panelboss.wm import _inspect as _I
        import ctypes as _ct
        _top = tk.Toplevel(app)
        _top.title("freeze-canary")
        _top.update()
        _hwnd = _ct.windll.user32.GetAncestor(_top.winfo_id(), 2)  # GA_ROOT
        _got = _I.win_title(_hwnd)
        assert _got == "freeze-canary", \
            "win_title lost a real own-process title (timeout route " \
            "broken): got %r" % _got
        class _Deaf:
            def __init__(self, real):
                self._real = real
            def __getattr__(self, n):
                return getattr(self._real, n)
            def SendMessageTimeoutW(self, *a):
                return 0
        _real_u32, _I.u32 = _I.u32, _Deaf(_I.u32)
        try:
            assert _I.win_title(_hwnd) == "", \
                "a deaf thread must answer the honest empty, not hang"
        finally:
            _I.u32 = _real_u32
        _top.destroy()
        _f0 = len(theme.MODERN._fonts)
        theme.MODERN.font(size=11)                   # may be the cached one
        assert len(theme.MODERN._fonts) == _f0 or \
            len(theme.MODERN._fonts) == _f0 + 1, \
            "font cache grew by more than one"
        _f = theme.MODERN.font(size=11)
        assert theme.MODERN._fonts.get(
            (theme.MODERN.font_family, 11, "normal")) is _f, \
            "skin.font returned an UNREMEMBERED font (the GC edge is alive)"
        import gc as _gc
        del _f
        _gc.collect()                                # and only the dict
        assert theme.MODERN._fonts.get(              # keeps it alive
            (theme.MODERN.font_family, 11, "normal")) is not None
        app._profile_picked(PF.NEW)            # the create-now pane (the
        #                                      only one that builds the
        #                                      capture button)
        assert getattr(app, "_prof_create_btn", None) is not None and \
            app._prof_create_btn in app._apply_btns, \
            "capture button not in _apply_btns: the worker-ized capture " \
            "verb would run un-locked"
        # THE LEAVE-RESET (owner fix, Oct 16): the detection preview
        # must not be the bitmap the tab switch carries. Full cycle:
        # draw one, leave (the CURRENT slot's ts is CONSUMED), a new
        # capture while hidden may NOT rebuild the picture (the tick
        # gates on the tab), and the return draws the newest frame on
        # its next tick.
        import numpy as _np
        _fr = _np.zeros((8, 8, 3), dtype=_np.uint8)
        fm.framebox.put(_fr, [], [])
        app._tab = "detection"
        app._draw(fm.framebox.get())
        assert app._ctkimg is not None, "the draw path itself is broken"
        _ts1 = app._shown_ts
        app._preview_leave()
        assert app._ctkimg is None and app._shown_ts == _ts1, \
            "leave left the bitmap or the ts unconsumed"
        _fr2 = _np.zeros((8, 8, 3), dtype=_np.uint8)
        _fr2[0, 0] = 255
        from panelboss.state import _preview as _pstate
        _real_t = _pstate.time
        _pstate.time = type("T", (), {"monotonic": lambda: _ts1 + 1.0})
        fm.framebox.put(_fr2, [], [])                   # a capture that
        _pstate.time = _real_t                          # happened AFTER
        # (monotonic is coarse on this box: two puts microseconds apart
        # can share a stamp, and an EQUAL stamp is not "newer" - the
        # state module's time is faked for the put alone)
        app._tab = "general"
        app._tick_inner()
        assert app._ctkimg is None, \
            "a hidden poll smuggled a fresh bitmap in before the return"
        app._tab = "detection"
        app._tick_inner()
        assert app._ctkimg is not None, \
            "the return did not draw the newest frame on its first tick"
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
