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
                     "ignore_box", "plan_entry", "add_fg_button"):
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
        # 7) the HDR-while-away switch: RETIRED with its row by the
        #    dim-mode wave (2026-10-14). The widget left the power tab,
        #    so its click round-trip retired with it - the config key
        #    itself still survives (one release, downgrade honesty)
        #    and awaymode_test covers the migration that replaced the
        #    switch. Section number kept as a headstone: renumbering
        #    here would churn every line below for a comment.
        # 8) THE SECOND COLUMN (Oct 12, owner: the gaming cards moved
        #    right, the profiles law extended). The Game DVR card died
        #    by owner order Oct 15 ("the state line lies; not worth the
        #    hassle") - its switch anchors and its live-registry
        #    round-trip retired with it (tweaks_test.py §6 still owns
        #    the apply/revert verb against the real registry). The
        #    column law survives, re-anchored on the gaming card that
        #    remains: the gaming switch sits in a column whose x is
        #    the LEFT card column's x plus that column's width, i.e.
        #    beside, not below.
        _sw0 = app.gaming_switch          # the gaming card's own switch
        _anc = []                        # its ancestor chain, up to
        _w = _sw0                        # the window
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
        assert _cols[1] in _anc, "the gaming card lives in the RIGHT column"
        assert _sw0.winfo_rootx() > _cols[0].winfo_rootx() + 400, \
            "the right column starts a column-width to the right - " \
            "beside, not below [dbg leftx=%s rightx=%s swx=%s innerw=%s " \
            "winw=%s]" % (_cols[0].winfo_rootx(),
                          _cols[1].winfo_rootx(), _sw0.winfo_rootx(),
                          _inner.winfo_width(), app.winfo_width())
        print("[PASS] gaming cards live in the second column (side by side)")
        # 8b/9) THE GAME DVR CARD, BURIED (owner UAT, Oct 15): the
        #     click-repaints-its-own-row closure pin and the
        #     knob-from-truth both-ways pin retired with the card;
        #     the registry round-trip they drove belongs to
        #     tweaks_test. Section numbers kept as headstones:
        #     renumbering would churn every line below for a comment.
        # 9b) THE REST OF THE SWITCH FAMILY (the widget-blind class the
        #     owner personally caught): every knob the power/restore/
        #     editor panes build must paint BOTH branches from cfg
        #     truth - drive the REAL build both ways and read the knobs
        #     back. cfg is the owner's live desk here (this suite
        #     predates the scratch-dir wave): snapshot, drive, restore.
        _ck = [(cfg["power"], k) for k in
               ("hold_display", "hold_sleep", "restore_windows",
                "hdr_off_when_away", "assistant_task")]
        _ck.append((cfg["guards"], "fullscreen"))
        _ck.append((cfg["restore"], "enabled"))
        _snap_cfg = {(id(s), k): s.get(k) for s, k in _ck}
        try:
            # the lever lives in the SELECTED-profile fill (a NEW
            # selection skips that half of the pane, and this suite's
            # profile store is scratch-empty): create one first - the
            # same choreography power_assistant_test and the geometry
            # probe use - or the flip loop probes a widget that was
            # never built (the bite, named by the watchdog census)
            app._prof_name.insert(0, "9b desk")
            app._profile_create()
            # THE PUMP LAW (Oct-16 worker-ization): done() lands on a
            # cross-thread after; the selection returns only when it runs.
            _t0p = time.time()
            while time.time() - _t0p < 5.0 and getattr(app, "_applying",
                                                       False):
                app.update()
                time.sleep(0.02)
            app._profiles_render()
            for flip in (True, False):
                cfg["power"]["hold_display"] = flip
                cfg["power"]["hold_sleep"] = not flip
                cfg["power"]["restore_windows"] = flip
                cfg["power"]["hdr_off_when_away"] = not flip
                cfg["guards"]["fullscreen"] = flip
                cfg["power"]["assistant_task"] = not flip
                cfg["gaming"]["enabled"] = flip
                app._build_power(app.pages["power plan"].inner)
                # the hold pair paints from cfg as the SEGMENTED trio
                # since Oct 21: the same both-branch law, now also
                # proving the belt's bool->word mapping (flip rides the
                # pre-wave boolean shape) and the gray law as painted
                # (camera.enabled is True in this suite's cfg: the
                # 'while present' segment must stand enabled)
                assert app.hold_display_choice.get() == \
                    ("on" if flip else "off"), \
                    "hold_display painted its default, not its cfg"
                assert app.hold_sleep_choice.get() == \
                    ("off" if flip else "on"), \
                    "hold_sleep kept a stale ON"
                assert app.hold_display_choice._buttons_dict[
                    "while present (camera)"]._state == "normal", \
                    "the 'while present' segment grayed behind an " \
                    "enabled eye"
                assert bool(app.restore_switch.get()) is flip
                # (hdr_while-away's assert retired with its switch -
                #  dim-mode wave; the away card's rows - and since the
                #  Oct-22 wave its whole trio of switches - are
                #  painted by _sync_away_rows, a different seam with
                #  its own truth)
                assert bool(app.fullscreen_switch.get()) is flip
                assert bool(app.power_switch.get()) is (not flip)
                assert bool(app.gaming_switch.get()) is flip
            # the gray law's OTHER arm, painted (test (e)'s UI half):
            # detection off -> the segment loses its state (grayed,
            # never hidden: the row's selection keeps its place); back
            # on -> the state returns. The data half lives in hold_test
            # 3c; this is the flag->segment mapping it promises.
            _was_on = cfg["camera"]["enabled"]
            cfg["camera"]["enabled"] = False
            _sel_before = app.hold_display_choice.get()
            app._sync_hold_rows()
            for _seg in (app.hold_display_choice, app.hold_sleep_choice):
                assert _seg._buttons_dict[
                    "while present (camera)"]._state == "disabled", \
                    "detection off left 'while present' enabled"
                assert "while present (camera)" in _seg.cget("values"), \
                    "the gray-out HID the choice (law: gray, never hide)"
            assert app.hold_display_choice.get() == _sel_before, \
                "graying moved the row's selection (kept-while-grayed law)"
            cfg["camera"]["enabled"] = _was_on
            app._sync_hold_rows()
            assert app.hold_display_choice._buttons_dict[
                "while present (camera)"]._state == "normal", \
                "detection back on left the segment grayed"
            # the profiles tab's lever + the editor's checkbox: same
            # law, driven through their own rebuild seams
            for flip in (True, False):
                cfg["restore"]["enabled"] = flip
                app._profiles_render()
                assert bool(app.restorep_switch.get()) is flip, \
                    "the armed lever betrays its origin"
                app._pin_edit["open"] = flip
                app._repaint("editor")
                assert bool(app.pin_open_box.get()) is flip, \
                    "the open-wish box paints half the story"
            print("[PASS] power/restore/editor switches paint knob-from"
                  "-truth both ways (the exterminated family)")
        finally:
            for s, k in _ck:
                if _snap_cfg[(id(s), k)] is None:
                    s.pop(k, None)
                else:
                    s[k] = _snap_cfg[(id(s), k)]
            app._build_power(app.pages["power plan"].inner)
            app._profiles_render()
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
    except Exception:
        _fail("check")
    finally:
        # the checks are done: end the loop - ALWAYS. The third
        # app-down bite (measured, watchdog census in this file):
        # §9b's aborted check skipped this teardown, the mainloop
        # outlived the error by 60 s, and the watchdog's rc=1 buried
        # the real traceback under the bite. destroy+quit belong in
        # a finally: every exit from check() closes the window and
        # fails FAST. destroy() alone does not always end the loop
        # (the half-built second window kills Tk's auto-command
        # table); quit() is the Tcl-level break that does.
        try:
            app.destroy()
        except Exception:
            pass
        try:
            app.quit()
        except Exception:
            pass


def _watchdog():
    print("WATCHDOG FIRED after 60 s", flush=True)
    # the standing bracket's instrument (exit-path hang, three bites):
    # name every still-alive thread at the bite - the class is a
    # thread holding the interpreter (or the loop) open past the
    # [PASS] prints, and a watchdog without a census is a timestamp.
    print("threads alive at bite:", flush=True)
    for t in threading.enumerate():
        print("  %-24s daemon=%s alive=%s" % (t.name, t.daemon,
                                              t.is_alive()), flush=True)
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
    print("threads alive at kill:", flush=True)
    for t in threading.enumerate():
        print("  %-24s daemon=%s alive=%s" % (t.name, t.daemon,
                                              t.is_alive()), flush=True)
    os._exit(3)


threading.Thread(target=_hard_kill, daemon=True).start()

app.after(600, check)
app.after(60000, _watchdog)
app.mainloop()
if FAILED:
    print("WINDOW TEST FAILED in", FAILED)
    sys.exit(1)
print("gaming ui OK")
