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
import json
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
from panelboss import nmhost                           # noqa: E402

# the OWNER's real helper install is not this probe's truth: redirect
# the doorway-neighbor so the built card answers from the probe's own
# (absent) world - the exact-label pins below must not depend on
# whether this box has a host installed (the app-up compatibility law
# includes the owner's %APPDATA%).
nmhost.HOST_JSON = os.path.join(SCRATCH, "no-host.json")

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
        _desk0 = WM.monitors
        WM.monitors = lambda: []           # THE OWNER SCENARIO (Oct 17):
        #                             the app opened with NO monitors
        #                             attached - every card must still
        #                             build, and the desk ear must be
        #                             able to fill it when the desk
        #                             returns
        try:
            app = W.SettingsWindow(cfg, fm, queue.Queue())
        finally:
            WM.monitors = _desk0
        assert app.state() == "withdrawn"
        assert getattr(app, "kofi_button", None) is not None, \
            "the window died at the kofi cup again"
        # THE APP ICON (Oct 19): the owner art must ride the titlebar
        # and the taskbar. The MARKER + file are the claim; the wm
        # query below is diagnostic only (a bare query answers '' for
        # the app-default on this Tcl - measured - so it proves
        # nothing either way). THE VETO (gate round, same day): ctk
        # 6.0.0 re-mints its feather on every CTkToplevel at +200 ms
        # unless iconbitmap was called first - _brand_toplevels makes
        # EVERY toplevel call it at birth. Pinned synchronously: a
        # fresh toplevel's flag must already be True (the +200 pass
        # cannot have fired yet; only our patch could have set it).
        ic = app.tk.call("wm", "iconbitmap", app._w)
        marker = getattr(app, "_app_icon_path", "")
        assert str(marker).endswith("assets" + os.sep + "panelboss.ico") \
            and os.path.isfile(marker), \
            "no owner art on the window: marker %r, wm query %r" % (
                marker, ic)
        import customtkinter as _ctk
        tl = _ctk.CTkToplevel(app)
        try:
            assert tl._iconbitmap_method_called is True, \
                "the feather veto did not reach a fresh toplevel"
        finally:
            tl.destroy()
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
        # (i) the desk-less boot drew the static world: NO monitor
        # rows, but every desk-INDEPENDENT control exists (the deep-
        # sleep slider is not a monitor; it survived without them)
        assert app._away_rows == {}, app._away_rows
        assert app._oled_rows == {} and app._jog_rows == {} and \
            app._dim_rows == {} and app._comp_mon_rows == {}, \
            "the oled tab froze rows onto an empty desk"
        assert app.gaming_menus == {}, \
            "the gaming card grew rows out of nothing"
        assert getattr(app, "away_refresh_btn", None) is not None
        # (ii) the desk returns: the fanout (what the 2 s fingerprint
        # poll calls; the test drives the seam directly because its
        # fingerprint fake is a constant by design - the source pin
        # below is what proves the poll is wired to it)
        app.refresh_monitor_rows()
        app.update_idletasks()
        assert list(app._away_rows) == ["T"], app._away_rows
        assert list(app._oled_rows) == ["T"] and \
            list(app._jog_rows) == ["T"] and \
            list(app._dim_rows) == ["T"] and \
            list(app._comp_mon_rows) == ["T"], \
            "one desk panel, one row per card"
        assert list(app.gaming_menus) == ["T"], app.gaming_menus
        # (iii) idempotent: a second refresh swaps rows, never stacks
        n0 = len(app._away_row_frame.winfo_children())
        app.refresh_monitor_rows()
        app.update_idletasks()
        assert len(app._away_row_frame.winfo_children()) == n0, \
            "the refresh stacks instead of swapping"
        # the ear is on the pump (the suite's static-ban idiom): the
        # tick reads the fingerprint and calls the fanout on a change
        _rt = open(os.path.join(os.path.dirname(os.path.dirname(
                       os.path.abspath(__file__))),
                       "panelboss", "ui", "window", "_runtime.py"),
                   encoding="utf-8").read()
        assert "_desk_check()" in _rt and "fingerprint" in _rt, \
            "the desk ear is not wired to the pump"
        # THE CONSENT DOOR (owner correction, Oct 19): 'No' to the
        # setup ask must let the user IN - the switch stays, the
        # engine gets the word, no wizard toll. (The complaint:
        # toggling detection off and on again "won't stay enabled
        # unless you go through first time setup again".)
        app.cfg["camera"]["enabled"] = False
        app.consent_switch.select()              # the user's flip -
        import panelboss.ui.window._detection as _det
        _real_ask = _det.messagebox.askyesno
        _det.messagebox.askyesno = lambda *a, **k: False   # the No
        try:
            app._consent_flipped()
            _evt = None
            try:
                _evt = fm.events.get_nowait()
            except queue.Empty:
                pass
            assert _evt == ("camera_enabled", True), \
                "a No at the gate must ENABLE, not re-flip: %r" % (_evt,)
            # the drain's answer (state owns the key; the resync is
            # what lights the switch - simulate the applied truth):
            app.cfg["camera"]["enabled"] = True
            app._sync_consent_switch()
            assert bool(app.consent_switch.get()), \
                "the switch must STAY on through the refused wizard"
            app._consent_flipped()               # switch already on,
            try:                                 # cfg now on: pure
                _evt = fm.events.get_nowait()    # echo, no post
                raise AssertionError("the echo guard leaked: %r" % (_evt,))
            except queue.Empty:
                pass
        finally:
            _det.messagebox.askyesno = _real_ask
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
        # THE OCT-16 WAVE RENDERS ON AN EMPTY CONFIG (the migration
        # law's UI half): the boot ran with a virgin file - no fade,
        # no levels, no monitors anywhere - and every new widget row
        # still drew: the plain lift-fade switch on the dim card, the
        # fake panel's per-panel veil-% row, the per-monitor theater
        # row (box checked by default, slider at the global). Exact
        # labels, no substring games.
        for want in ("lift fade", "T veil %", "theater on T"):
            assert want in _t, "the Oct-16 wave lost %r on the card" % want
        # THE AWAY CARD LIVES ON THE DETECTION TAB (salvage correction,
        # Oct 17 - scanning the oled tab for it pins a ghost): the
        # stage-two row and the lock box must render there on an
        # EMPTY config, or the feature has no door.
        _t2 = []

        def _titles2(w):
            for c in w.winfo_children():
                try:
                    x = c.cget("text")
                except Exception:
                    x = None
                if isinstance(x, str) and x:
                    _t2.append(x)
                _titles2(c)
        _titles2(app.pages["detection"].inner)
        # THE AWAY CARD AFTER THE OWNER'S OCT-22 WAVE (this session's
        # laws): the global mode selector is DEAD - the retired widget
        # id is pinned out of the builder source itself - the trio of
        # away decisions (hold-off, lock, restore) lives here now, the
        # offdisc default is what a virgin row paints, the per-row
        # picker answers with the honest labels, the DDC law text is
        # data, and the preview label states its duration. The gray
        # is PAINTED AT BUILD: no event has fired on this fresh card,
        # and a row the chain answers 'off (disconnect)' must already
        # show its brightness slider disabled and unmapped (the
        # first-boot lie the pump/hold wave's lesson came to kill).
        # The grace pair moves the OTHER way: it negotiates the plan's
        # wake timers, so it pins into the power plan tab below.
        _usrc = open(os.path.join(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))),
            "panelboss", "ui", "window", "_away.py"),
            encoding="utf8").read()
        assert "away_mode_button" not in _usrc, \
            "the global mode selector row came back"
        for want in ("lock when away starts",
                     "hold off while a fullscreen app owns "
                     "the display",
                     "put window positions back after wake",
                     "refresh monitors"):
            assert want in _t2, \
                "the detection tab lost the away card's %r" % want
        for gone in ("monitors off", "re-off grace", "leave-on grace"):
            assert gone not in _t2, "the away card grew back %r" % gone
        from panelboss.ui.window import _away as _am
        _r = app._away_rows["T"]
        assert set(_r["seg"]._buttons_dict) == set(_r["vals"]), _r["vals"]
        assert _am.DISC_TEXT in _r["vals"]      # offered on EVERY row
        assert set(_r["vals"]) <= {"dim", _am.DDC_TEXT, _am.DISC_TEXT,
                                   "blackout"}, _r["vals"]
        assert _am.TIP["ddc"] == (
            "the quick software power-down - some panels refuse the "
            "DDC/CI write (KVM chains especially); a refused row falls "
            "back to blackout")                 # the tip, as data
        assert _r["preview"].cget("text") == _am.preview_label()
        assert _am.preview_label() == "preview (%ds)" % _am.PREVIEW_SEC
        # an off-mode row's sub-controls must NOT be live at build:
        # CTkSlider has no state option (a bare CTkSlider.configure
        # (state=...) dies - verified in customtkinter 6), so the
        # disabled half is carried by the row gate / the unmapped
        # grid slot - and the slider may only become live again when
        # its row answers dim (which an event alone can do)
        assert _r["slider"].winfo_manager() == "", \
            "the off-mode slider was not unmapped at build"
        if not app.cfg["camera"].get("enabled"):
            # no consent yet: the row's own picker says disabled
            # (the _state seam the power card's gray law reads)
            assert _r["seg"]._buttons_dict[_am.DISC_TEXT]._state == \
                "disabled", \
                "row controls were live at build on a consentless card"
        # the trio paints from cfg at build (the virgin file's truth:
        # guards.fullscreen True by default, restore True, lock False)
        assert _am and bool(app.away_lock_box.get()) is False
        _t3 = []

        def _titles3(w):
            for c in w.winfo_children():
                try:
                    x = c.cget("text")
                except Exception:
                    x = None
                if isinstance(x, str) and x:
                    _t3.append(x)
                _titles3(c)
        _titles3(app.pages["power plan"].inner)
        for want in ("unexpected wake", "auto re-off",
                     "re-off grace", "leave-on grace"):
            assert want in _t3, \
                "the wake card lost %r (the grace pair negotiates ITS " \
                "timers)" % want
        for gone in ("hold off while a fullscreen app owns "
                     "the display",
                     "put window positions back after wake"):
            assert gone not in _t3, \
                "%r did not leave the power plan tab" % gone
        # THE HELPER-INSTALL VERB (Oct 16): the doorway row's button
        # EXISTS on the built window - exact label, no substring
        # checks (the placement-trio lesson) - with its id-override
        # entry beside it on the same row. The label reads the honest
        # state: install while no host is registered, reinstall once
        # one is (the flip below walks the seam the card's own beat
        # walks).
        assert "install the helper" in _t, \
            "the doorway row lost the helper-install button"
        _hb = []

        def _find_btn(w):
            for c in w.winfo_children():
                if c.__class__.__name__ == "CTkButton" and \
                        c.cget("text") == "install the helper":
                    _hb.append(c)          # the OUTER button only:
                    continue               # CTkButton mirrors its text
                _find_btn(c)               # onto an inner canvas child
        _find_btn(app.pages["oled"].inner)
        assert len(_hb) == 1, \
            "the built window must carry exactly one helper-install " \
            "button, got %d" % len(_hb)
        _ent = [c for c in _hb[0].master.winfo_children()
                if getattr(c, "_placeholder_text", None) == "id override"]
        assert len(_ent) == 1, \
            "the install button lost its id-override entry sibling"
        _hjp = os.path.join(SCRATCH, "host.json")
        with open(_hjp, "w", encoding="utf-8") as _f:
            json.dump({"path": sys.executable}, _f)
        nmhost.HOST_JSON = _hjp
        app._helper_install_words()
        assert _hb[0].cget("text") == "reinstall", \
            "an installed host must read 'reinstall' on the button: %r" \
            % (_hb[0].cget("text"),)
        nmhost.HOST_JSON = os.path.join(SCRATCH, "no-host.json")
        app._helper_install_words()
        assert _hb[0].cget("text") == "install the helper", \
            "the absent host must fall back to the install label"
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
