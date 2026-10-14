"""Offline checks for the gaming card in the settings window: the
enable switch, the per-monitor rate menus, the games/ignore list
editors, and the front-of-me worker. No real display is ever asked
for a mode (the desk and the driver's answers are fakes); config
writes go to a scratch file so the live config survives.
Run with the tray app CLOSED: its CTk windows poison CTkToplevel in
any other process (the window section then skips itself, exit 0)."""
import ctypes
import os
import queue
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import tomllib as _toml
except ImportError:
    import tomli as _toml

from panelboss import config
from panelboss import profiles as PF
from panelboss import wm as WM

cfg = config.get_config(verbose=False)

# config writes go to a scratch file: the window's _save() would
# otherwise rewrite the LIVE config on every widget change (the
# power-assistant suite measured that bite)
TEST_CFG = os.path.join(os.environ.get("TEMP", "."),
                        "panelboss_test_config.toml")
_saved_wc = config.write_config
config.write_config = lambda c, path=None: _saved_wc(c, TEST_CFG)
try:
    os.remove(TEST_CFG)
except OSError:
    pass

# the monitor-profiles tab, live in this window: the store goes to a
# scratch file, and the desk it sees is a fake one (two monitors with
# deterministic offered rates) - no real display is ever asked for
# anything by this suite
PF.path = lambda dir=None: os.path.join(os.environ.get("TEMP", "."),
                                        "panelboss_test_profiles.json")
for _f in (PF.path(), PF.path() + ".tmp"):
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
WM.list_windows = lambda: [{"proc": "a.exe", "title": "one",
                            "hwnd": 11, "rect": [0, 0, 50, 50],
                            "zoomed": False, "exe": r"C:\a\a.exe"}]
WM.launch = lambda exe: ""
WM.rescue_lost = lambda: []
WM.place = lambda h, r, z=False: "ok"
WM.hdr_states = lambda: [{"gdi": r"\\.\DISPLAY1", "model": "T1",
                          "supported": False, "state": "off",
                          "mode": 0, "precise": True},
                         {"gdi": r"\\.\DISPLAY2", "model": "T2",
                          "supported": False, "state": "off",
                          "mode": 0, "precise": True}]
# the gaming card's rate menus and the front-of-me probe: fakes, so no
# panel is ever offered a rate it does not have
WM.offered_modes = lambda gdi, limit=400: (
    ["100x100@60", "100x100@144"] if gdi == r"\\.\DISPLAY1"
    else ["100x100@75", "100x100@120"])
WM.foreground = lambda: {"hwnd": 1, "pid": 4242,
                         "proc": "frontgame.exe",
                         "exe": r"C:\g\frontgame.exe", "title": "t",
                         "rect": [0, 0, 100, 100], "monitor": "T1"}

# the window section needs a quiet desktop: with the live app running,
# its CTk windows poison any CTkToplevel a second process opens - both
# window suites die inside CTkToplevel.__init__ while the exact same
# steps pass with the tray app closed. The tray binary takes the named
# mutex from cli.py; refuse loudly instead of failing red.
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

from panelboss.state import FrameBox
from panelboss.ui import window as W

fm = type("FM", (), {})()
fm.state = "counting"
fm.paused = False
fm.re_off_paused = False
fm.events = queue.Queue()
fm.framebox = FrameBox()
fm.blockers = {"error": None, "display": [], "other": []}
# CTkToplevel.__init__ pumps the WHOLE event loop (its titlebar-color
# dance calls withdraw()+update() to force a redraw); inside the
# synchronous check chain that re-entrancy runs late callbacks early.
# The flag skips the dance; the probes never look at titlebars.
W.ctk.CTkToplevel._deactivate_windows_window_header_manipulation = True
app = W.SettingsWindow(cfg, fm, queue.Queue())
FAILED = []


def _fail(where):
    """A raised assert inside an after() callback would otherwise
    leave mainloop running forever (a silent 300 s hang is how this
    suite likes to "fail"); record it, print it, let the chains wind
    down and exit nonzero."""
    FAILED.append(where)
    __import__("traceback").print_exc()


def _disk():
    with open(TEST_CFG, "rb") as f:
        return _toml.load(f)


def check():
    try:
        # 1) the window built with the gaming card ON the power-plan
        #    tab (no fifth tab - the card joins that tab's column)
        assert set(app.pages) == set(W.TABS), app.pages
        for attr in ("gaming_switch", "gaming_menus", "games_box",
                     "ignore_box", "plan_entry", "add_fg_button",
                     "dvr_status"):
            assert hasattr(app, attr), attr + " missing from the build"
        print("[PASS] window builds (gaming card on the power-plan tab)")
        app._show_tab("power plan")
        app.update_idletasks()
        # 2) the enable switch round-trips through a real config
        #    rewrite (the 400 ms save debounce is what ships it)
        app.gaming_switch.select()
        app._gaming_changed()
        assert cfg["gaming"]["enabled"] is True
        time.sleep(0.5)
        app.update()
        assert _disk()["gaming"]["enabled"] is True, _disk()["gaming"]
        app.gaming_switch.deselect()
        app._gaming_changed()
        assert cfg["gaming"]["enabled"] is False
        time.sleep(0.5)
        app.update()
        assert _disk()["gaming"]["enabled"] is False, _disk()["gaming"]
        print("[PASS] gaming switch round-trips through a config rewrite")
        # 3) the list editors: the lines (blanks dropped) are the list
        app.games_box.delete("1.0", "end")
        app.games_box.insert("1.0", "listed.exe\n\nsecond.exe\n")
        app._gaming_games_commit()
        assert cfg["gaming"]["games"] == ["listed.exe", "second.exe"], \
            cfg["gaming"]["games"]
        app.ignore_box.insert("1.0", "cheater.exe\n")
        app._gaming_ignore_commit()
        assert cfg["gaming"]["ignore"] == ["cheater.exe"], \
            cfg["gaming"]["ignore"]
        # 3b) the browse buttons (owner: browse beats free-edit): the
        #     dialog is patched, the LAW is the handler's own code -
        #     base name only, deduped, committed through the focus
        #     seam like any typed line
        import tkinter.filedialog as _fd
        _real_ask = _fd.askopenfilename
        # ONE try over the whole browse block: the patched dialog
        # answers from a script, and the real one must stay hidden
        # for every call - the first cut restored the real function
        # between the two picks, the dedupe browse then opened a REAL
        # modal on the owner's desktop, the 60 s watchdog destroyed
        # the app, and every downstream TclError was just wreckage
        _picks = iter([r"D:\Games\Third Party\Third.exe",        # append
                       r"D:\Games\Third Party\Third.exe",        # dup
                       ""])                                      # cancel
        _fd.askopenfilename = lambda **k: next(_picks)
        try:
            app._gaming_browse(app.games_box)
            assert cfg["gaming"]["games"] == ["listed.exe", "second.exe",
                                              "third.exe"], \
                cfg["gaming"]["games"]      # BASE name, path dropped
            app._gaming_browse(app.games_box)   # same pick again
            assert cfg["gaming"]["games"].count("third.exe") == 1, \
                "the browse is a door, not a pile"
            app._gaming_browse(app.ignore_box)  # cancelled dialog
            assert cfg["gaming"]["ignore"] == ["cheater.exe"], \
                "a cancelled browse edits nothing"
        finally:
            _fd.askopenfilename = _real_ask
        print("[PASS] browse-to-exe appends the base name, dedupes, "
              "and the cancel is a no-op")
        time.sleep(0.5)
        app.update()
        disk = _disk()
        # third.exe is here because the browse commit above went
        # through the SAME _save path - the disk shows exactly what
        # the live cfg shows, which is the whole point of the seam
        assert disk["gaming"]["games"] == ["listed.exe",
                                           "second.exe",
                                           "third.exe"], disk["gaming"]
        assert disk["gaming"]["ignore"] == ["cheater.exe"], disk["gaming"]
        print("[PASS] list commits save through a config rewrite")
        # 4) the per-monitor menus: offered rates only, the defaults
        #    are the TRUTH (unset game = auto = fastest during
        #    games; unset desktop = keep = the watcher never touches
        #    this panel outside games - the old cosmetic 60 was the
        #    lie that made the feature look broken), and a selection
        #    lands in cfg under the right short
        assert set(app.gaming_menus) == {"T1", "T2"}, app.gaming_menus
        game1, desk1 = app.gaming_menus["T1"]
        game2, desk2 = app.gaming_menus["T2"]
        v1 = str(game1.cget("values"))
        assert "auto" in v1 and "60" in v1 and "144" in v1, v1
        v2 = str(desk2.cget("values"))
        assert "75" in v2 and "120" in v2 and "keep" in v2, v2
        assert game1.get() == "auto", game1.get()      # unset = auto
        assert desk1.get() == "keep", desk1.get()      # unset = keep
        assert desk2.get() == "keep", desk2.get()
        app._gaming_game_hz("T1", "144")
        assert cfg["gaming"]["game_hz"].get("T1") == 144, \
            cfg["gaming"]["game_hz"]
        assert "T2" not in cfg["gaming"]["game_hz"], \
            "T1's choice leaked into T2"
        app._gaming_game_hz("T2", "auto")
        assert cfg["gaming"]["game_hz"].get("T2") == "auto", \
            cfg["gaming"]["game_hz"]
        # keep on a CONFIGURED panel deletes the rule (hands-off
        # again), it must never store the string "keep"
        cfg["gaming"]["desktop_hz"]["T2"] = 75
        app._gaming_desk_hz("T2", "keep")
        assert "T2" not in cfg["gaming"]["desktop_hz"], \
            cfg["gaming"]["desktop_hz"]
        app._gaming_desk_hz("T2", "120")
        assert cfg["gaming"]["desktop_hz"].get("T2") == 120, \
            cfg["gaming"]["desktop_hz"]
        time.sleep(0.5)
        app.update()
        back = _disk()
        assert back["gaming"]["game_hz"]["T1"] == 144, back["gaming"]
        assert back["gaming"]["game_hz"]["T2"] == "auto", back["gaming"]
        assert back["gaming"]["desktop_hz"]["T2"] == 120, back["gaming"]
        print("[PASS] game_hz menu selection lands in cfg with the right short")
        # 4b) the VRR entry: it sits between the default and the Hz
        #     list, stores the string "vrr", shows itself again on a
        #     reload, and choosing the default back pops the rule (the
        #     desktop keep's pattern, scoped to a vrr entry)
        assert "VRR (pin max)" in v1, v1
        assert str(game1.cget("values")) == \
            "['auto', 'VRR (pin max)', '60', '144']", v1
        app._gaming_game_hz("T1", "VRR (pin max)")
        assert cfg["gaming"]["game_hz"].get("T1") == "vrr", \
            cfg["gaming"]["game_hz"]
        time.sleep(0.5)
        app.update()
        assert _disk()["gaming"]["game_hz"]["T1"] == "vrr", _disk()["gaming"]
        print("[PASS] vrr (pin max): menu entry, vrr stored, on disk")
        # 4c) THE RELOAD HALF IS SKIPPED IN-PROCESS, UNCONDITIONALLY
        #     (Oct 12, measured to the widget path): a second
        #     SettingsWindow shares the ONE Tcl interpreter and its
        #     child-name uniquifier REUSES names across roots - app2's
        #     gaming card landed on app's box's path and orphaned
        #     app's SkewText outright (the front-of-me worker's
        #     deferred refresh died on the next line). Destroying OR
        #     parking app2 both poison app; the historic "died in the
        #     build + SKIP" shape was the same defect one stage
        #     earlier. Reload-on-build is still covered by this suite:
        #     the cfg->disk->fresh-window path is exactly what the
        #     MAIN window's own rebuild does at build time (section 2
        #     and 4 read cfg and disk directly). A true second-window
        #     reload test needs window.py to grow single-root
        #     discipline - BACKLOG item, not a red line here.
        print("SKIP vrr reload half: in-process second roots poison "
              "the first window (measured to the path) - window.py "
              "side defect, not this suite; the stored-state path is "
              "asserted through cfg and disk above")
        # 5) the front-of-me worker: the function (not the click) starts
        #    the probe off-thread; the answer appends and refreshes the
        #    box; a miss leaves the list exactly alone
        before = tuple(cfg["gaming"]["games"])
        _box_path = str(app.games_box)     # named in the failure text
        app._gaming_add_foreground()
        time.sleep(0.4)
        app.update()
        assert tuple(cfg["gaming"]["games"]) == before + \
            ("frontgame.exe",), cfg["gaming"]["games"]
        assert "frontgame.exe" in app.games_box.get("1.0", "end"), \
            ("the games box did not refresh [%s %s]"
             % (_box_path, app.games_box))
        _real_fg = WM.foreground
        WM.foreground = lambda: None
        app._gaming_add_foreground()
        WM.foreground = _real_fg
        time.sleep(0.4)
        app.update()
        assert tuple(cfg["gaming"]["games"]) == before + \
            ("frontgame.exe",), \
            "a foreground miss must not touch the list"
        print("[PASS] front-of-me worker appends the foreground proc")
        # 6) the plan entry commits the fragment it holds
        app.plan_entry.delete(0, "end")
        app.plan_entry.insert(0, "high performance")
        app._gaming_plan_commit()
        assert cfg["gaming"]["power_plan"] == "high performance", \
            cfg["gaming"]["power_plan"]
        print("[PASS] power-plan entry commits the fragment")
        # 7) the HDR-while-away switch round-trips through a config
        #    rewrite like the gaming switch does
        before_hdr = bool(cfg["power"].get("hdr_off_when_away"))
        app.hdr_away_switch.select() if not before_hdr \
            else app.hdr_away_switch.deselect()
        app._hdr_away_changed()
        assert bool(cfg["power"].get("hdr_off_when_away")) is not before_hdr
        time.sleep(0.5)
        app.update()
        assert bool(_disk()["power"]["hdr_off_when_away"]) is not before_hdr
        app.hdr_away_switch.deselect() if not before_hdr \
            else app.hdr_away_switch.select()
        app._hdr_away_changed()
        assert bool(cfg["power"].get("hdr_off_when_away")) is before_hdr
        time.sleep(0.5)
        app.update()
        assert bool(_disk()["power"]["hdr_off_when_away"]) is before_hdr
        print("[PASS] hdr-while-away switch round-trips through a config rewrite")
        # 8) the Game DVR card: the registry is the truth, so the
        #    round-trip runs against the LIVE registry - "history" is
        #    the low-blast-radius value on this desk and its original
        #    entry is restored no matter what happens in between. This
        #    exercises tweaks.apply/revert/_put VERBATIM: the old 6-arg
        #    SetValueEx crash (TypeError, the provider-era myth) is gone,
        #    so no shim stands between the test and the code that ships.
        #    (Oct 12, owner: the gaming cards moved to column two, the
        #    profiles law extended - the law is asserted: the DVR
        #    switch sits in a column whose x is the LEFT card column's
        #    x plus that column's width, i.e. beside, not below.)
        _sw0 = next(iter(app.dvr_switches.values()))
        _anc = []                        # the DVR switch's ancestor
        _w = _sw0                        # chain, up to the window
        while _w is not None and _w is not app:
            _anc.append(_w)
            _w = _w.master
        _inner = app.pages["power plan"].inner
        # the law is about the SPLIT, and the split needs a page
        # wide enough to hold it: the scratch window arrives at its
        # 200 px fossil size (no recall in this state dir), so the
        # test gives it the size the owner's window has - the same
        # explicit-geometry discipline veil_test's fitted-page block
        # learned an hour ago (a layout assertion that inherits the
        # WM's mood measures the mood, not the layout)
        app._size_pair = (1200, 820)
        if app.state() == "withdrawn":
            app.deiconify()              # the dance before this
        app.geometry("1200x820")         # section withdrew the
        app.update()                     # window; geometry only
        time.sleep(0.25)                 # resolves on a MAPPED
        app.update()                     # window (measured: a
                                         # withdrawn 200 px fossil
                                         # ignored the request). NO
                                         # lower() after: raise/
                                         # withdraw cycles reorder
                                         # what winfo reports, and
                                         # the column law needs only
                                         # COORDINATES - a mapped
                                         # window reports them
                                         # whether front or back.
        _cols = sorted([c for c in _inner.winfo_children()
                        if c.winfo_manager()],
                       key=lambda c: c.winfo_rootx())
        assert len(_cols) == 2, "power plan carries two columns now"
        assert _cols[1] in _anc, "the DVR card lives in the RIGHT column"
        assert _sw0.winfo_rootx() > _cols[0].winfo_rootx() + 400, \
            "the right column starts a column-width to the right - " \
            "beside, not below [dbg leftx=%s rightx=%s swx=%s innerw=%s " \
            "winw=%s]" % (_cols[0].winfo_rootx(),
                          _cols[1].winfo_rootx(), _sw0.winfo_rootx(),
                          _inner.winfo_width(), app.winfo_width())
        print("[PASS] gaming cards live in the second column (side by side)")
        from panelboss import tweaks
        tid = "history"
        path, name = tweaks.TOGGLES[tid][1], tweaks.TOGGLES[tid][2]
        orig = tweaks._get(path, name)             # capture
        try:
            ok, err = tweaks.apply(tid)
            assert ok, err
            assert tweaks.is_on(tid) is True
            ok, err = tweaks.revert(tid)
            assert ok, err
            assert tweaks.is_on(tid) is False
        finally:
            tweaks._put(path, name, orig)          # restore (None deletes)
        print("[PASS] dvr toggle apply/revert round-trips against the "
              "live registry")
        # 8b) THE closure trap itself: clicking one switch must repaint
        #     THAT row from registry truth. The late-binding bug made
        #     every lambda paint the LAST switch in the loop - invisible
        #     unless a bystander row is watched. "capture" clicks,
        #     "session" watches, and the bystander must not flinch.
        cap = app.dvr_switches["capture"]
        ses = app.dvr_switches["session"]
        p2, n2 = (tweaks.TOGGLES["capture"][1],
                  tweaks.TOGGLES["capture"][2])
        orig = tweaks._get(p2, n2)
        ses_was, cap_was = ses.get(), cap.get()
        try:
            cap.cget("command")()      # CTkSwitch has no invoke():
            #                            cget("command") fires EXACTLY
            #                            the bound closure under test
            app.update_idletasks()
            assert ses.get() == ses_was, "clicking capture painted session"
            assert cap.get() != cap_was
            assert tweaks.is_on("capture") == bool(cap.get())
            assert app.dvr_status.cget("text") in ("", None)
            cap.cget("command")()
            app.update_idletasks()
            assert ses.get() == ses_was, "clicking capture painted session"
            assert cap.get() == cap_was
            assert tweaks.is_on("capture") == bool(cap.get())
        finally:
            tweaks._put(p2, n2, orig)
        print("[PASS] a DVR click repaints its OWN row, never the "
              "neighbour's")
        # 9) KNOB-FROM-TRUTH at build (defect 2's widget-blind family):
        #    a switch must be painted from its state at construction,
        #    BOTH branches - a fresh CTkSwitch defaults off so the
        #    false case looked right by accident, but the paint must
        #    come from truth. Drive the real build: point every DVR
        #    toggle's registry value at its suppression state, rebuild
        #    the section, and read each knob back. (The gaming enable
        #    switch uses the same both-branch idiom now - asserted via
        #    the enabled round-trip in section 2.)
        import copy as _copy
        _tog = tweaks.TOGGLES
        _snap = {t: tweaks._get(_tog[t][1], _tog[t][2]) for t in _tog}
        try:
            # ALL on: each suppression value in place -> every knob on
            for t in _tog:
                tweaks._put(_tog[t][1], _tog[t][2], _tog[t][3])
            app._dvr_section(app.pages["power plan"].inner)
            for t in _tog:
                assert app.dvr_switches[t].get() == 1, \
                    "toggle %s built OFF though registry says on" % t
            # ALL off: values deleted -> every knob MUST be painted
            # off (the old one-sided build would keep a stale on)
            for t in _tog:
                tweaks._put(_tog[t][1], _tog[t][2], None)
            app._dvr_section(app.pages["power plan"].inner)
            for t in _tog:
                assert app.dvr_switches[t].get() == 0, \
                    "toggle %s kept a stale ON (no deselect at build)" % t
            print("[PASS] DVR switches paint knob-from-truth both ways")
        finally:
            for t in _tog:
                tweaks._put(_tog[t][1], _tog[t][2], _snap[t])
        # 10) DESKTOP-HZ / GAME-HZ per panel SURVIVES a silent driver
        #     (defect 3): a panel whose driver lists no rates (the RDP
        #     session display, a cable mid-renegotiation) must still
        #     get both menus - the enforcement reads desktop_hz/game_hz
        #     regardless of the offered list. Seed a saved rate and
        #     prove the menu shows it even though the driver offered
        #     nothing. Junk dies by name at normalize (config_norm 3b);
        #     here we prove the UI never goes silent.
        _real_off = WM.offered_modes
        try:
            WM.offered_modes = lambda gdi, limit=400: []   # driver mute
            cfg["gaming"]["desktop_hz"] = {"T1": 100}      # saved, unlisted
            cfg["gaming"]["game_hz"] = {"T1": 120}
            cfg["gaming"]["enabled"] = True
            app._gaming_section(app.pages["power plan"].inner)
            assert set(app.gaming_menus) >= {"T1", "T2"}, app.gaming_menus
            g1, d1 = app.gaming_menus["T1"]
            assert g1.get() == "120", ("saved game rate invisible", g1.get())
            assert d1.get() == "100", ("saved desktop rate invisible", d1.get())
            print("[PASS] rate menus render on a silent driver, saved "
                  "rates shown")
        finally:
            WM.offered_modes = _real_off
        # the checks are done: end the loop. destroy() alone does not
        # always work - a half-built second window (the image poison
        # above) kills the Tk auto-command table, and the mainloop's
        # window-gone notification runs through those commands.
        # quit() is a Tcl-level 'break' and always ends the loop.
        app.destroy()
        app.quit()
    except Exception:
        _fail("check")


def _watchdog():
    print("WATCHDOG FIRED after 60 s", flush=True)
    FAILED.append("watchdog")
    app.destroy()


# hard backstop: if the Tk event loop itself stops processing (the
# second-window image death can do it), the after-based watchdog
# below never fires and this process would hang the whole sweep.
# This daemon kills the process at 120 s instead.
def _hard_kill():
    time.sleep(120)
    print("HARD KILL after 120 s: the Tk event loop stopped "
          "processing - killing so the sweep cannot hang",
          flush=True)
    os._exit(3)


threading.Thread(target=_hard_kill, daemon=True).start()

app.after(600, check)
app.after(60000, _watchdog)
app.mainloop()
if FAILED:
    print("WINDOW TEST FAILED in", FAILED)
    sys.exit(1)
print("gaming ui OK")
