"""Offline checks for the monitor-profile MODE EDITOR in the settings
window: the per-panel resolution + refresh menus, the blank-profile
button, the add-monitor picker, and the per-row remove. No real display
is ever asked for a mode (the desk and the driver's offered lists are
fakes); profile writes go to a scratch store so the live profiles
survive. Run with the tray app CLOSED: its CTk windows poison
CTkToplevel in any other process (the window section then skips
itself, exit 0).
A wedged Tk loop hard-kills the process at rc=3 - the SAME meaning
gaming_ui_test and the run_all.ps1 exit-code table give it."""
import ctypes
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panelboss import config
from panelboss import profiles as PF
from panelboss import wm as WM
from panelboss.wm import _displaycfg as DC    # the fake speaks the
#                                       engine's REAL refusal words (Oct 14)
import pystray                              # the tray pin below walks
                                             # the real menu tree by class

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
# THE PLACEMENT TRIO (owner request, Oct 16): the tray menu carries both
# window verbs as standalone items - rescue FIRST, restore SECOND. The
# boot probe fakes the tray (no pystray pump), so its half of the pin
# lands here, where a real Tray object is cheap to build off-pump.
from panelboss import tray as _TRAY                       # noqa: E402


def _tray_items(menu):
    out = []
    for it in menu.items:
        if isinstance(it, pystray.MenuItem):
            # pystray 0.19.5 stores the label as a wrapped callable
            # (self._text); .text answers the plain string
            out.append(str(it.text))
        elif isinstance(it, pystray.Menu):
            out.extend(_tray_items(it))
    return out


_t = _TRAY.Tray(__import__("queue").Queue(), cfg,
                ui_events=__import__("queue").Queue())
_tray_labels = _tray_items(_t._build_menu())
assert "rescue my windows" in _tray_labels and \
    "restore my windows" in _tray_labels, \
    "the tray menu lost a window verb: %r" % _tray_labels
assert _tray_labels.index("rescue my windows") < \
    _tray_labels.index("restore my windows"), \
    "the tray menu must keep rescue first, restore second"
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

# the optional IR bridge is not this probe's subject, and its
# enumeration is the documented poison-per-process on this vcam-heavy
# desk (watchdog.py:65, camera.hello_ir_names): the boot identity
# fanout calls rows_from on the tk thread, and a stalled IR join parks
# main 20 s - long enough to starve the refusal's 5 s bound when the
# oled tab's companion card (Oct 15) shifts the boot pump into the
# NVIDIA warm-up window. The window_boot_test idiom, inherited whole.
from panelboss import camera as cam                       # noqa: E402
cam.optional_present = lambda pkg: False
cam.hello_ir_names = lambda: []

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
W.ctk.CTkToplevel._deactivate_windows_window_header_manipulation = True
app = W.SettingsWindow(cfg, fm, queue.Queue())
FAILED = []
# check() sets it PAST its last functional assert, BEFORE its own
# app.destroy(): a TclError before that line skipped asserts still
# to run and must NOT be tolerated (Oct 12 audit, the silent partial)
_done = False


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


def _add_desk_profile(name, used):
    """A profile that IS the fake desk by identity (T1+T2) wearing
    modes the desk has NOT landed (saved 200x200@144; live answers
    100x100@60/75, and the fake fingerprint is the constant TESTFP).
    Cappy's disappearing-profile demo, written into the store the
    live pane reads: the strict opener stays blind, identity cannot
    be. (Oct-24 dossier pins 0a/0b.)"""
    d = [{"id": "MONITOR\\T1", "short": "T1", "gdi": r"\\.\DISPLAY1",
          "on": True, "primary": True, "x": 0, "y": 0, "w": 200,
          "h": 200, "rate": 144, "bits": 32, "hdr_cap": None,
          "hdr_state": None},
         {"id": "MONITOR\\T2", "short": "T2", "gdi": r"\\.\DISPLAY2",
          "on": True, "primary": False, "x": 100, "y": 0, "w": 200,
          "h": 200, "rate": 144, "bits": 32, "hdr_cap": None,
          "hdr_state": None}]
    with open(TEST_PROFILES, encoding="utf-8") as f:
        data = json.load(f)
    data["profiles"][name] = {"fp": PF.target_fp(d), "created": 0.0,
                              "used": used, "match": "process",
                              "hdr": "snap", "displays": d, "wins": []}
    with open(TEST_PROFILES, "w", encoding="utf-8") as f:
        json.dump(data, f)


def check():
    global _done
    try:
        # 0a) THE PICKER SELF-HEALS WHEN MODES LAND (Oct-24 dossier,
        #     the frozen instant thawed): the pane opened on create-
        #     new (nothing in the seed wears this desk's identity);
        #     a fitting profile lands in the store and the desk
        #     ear's OWN seam (a bare _profiles_render - exactly what
        #     MONITOR_ROW_REBUILDERS calls on a fingerprint change)
        #     moves the UNTOUCHED opener onto it, values list and
        #     all. The disappearing profile returns the moment the
        #     desk settles, without a reopen.
        assert app._prof_sel == PF.NEW, app._prof_sel
        _add_desk_profile("r", 1.0)
        app._profiles_render()
        assert app._prof_sel == "r", app._prof_sel
        assert app.profile_menu.get() == "r", app.profile_menu.get()
        assert "r" in app.profile_menu.cget("values"), \
            app.profile_menu.cget("values")
        print("[PASS] the untouched picker self-heals onto the desk's "
              "profile at the desk-ear seam (identity, not the frozen fp)")

        # 0b) NEVER STOMP A DELIBERATE PICK: one manual pick arms the
        #     touched flag, and the same seam with a NEWER fitting
        #     profile in the store (the fingerprint-change route)
        #     must not move the opener. The owner's word outranks the
        #     desk's opinion.
        app._profile_picked("offline")
        assert app._prof_sel_touched is True
        _add_desk_profile("r2", 9.0)
        app._profiles_render()
        assert app._prof_sel == "offline", \
            "the desk ear stomped a deliberate pick"
        print("[PASS] picked-then-desk-change never moves the opener")

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
        _lab = [k for k, v in app._mode_add_map.items()
                if v == "MONITOR\\T2"][0]
        # (the label rides the identity seam - since the Oct-22 wave
        # it may carry the gdi tail and a descriptor, so the test
        # resolves it from the map instead of a literal "T2")
        app._mode_add.set(_lab)
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

        # 8b) THE CREATE-NOW BUTTON (defect 1): on the create-new pane
        #     (empty name -> the entry + "capture this desktop"), a
        #     click must CREATE one default-filled card, land it in the
        #     store, and switch the picker to it - the whole
        #     button -> create -> store -> card-list chain, through the
        #     real handler (the silent-death guard now reports any raise
        #     instead of vanishing). Drive it via the picker's NEW row.
        app._profile_picked(PF.NEW)
        app.update_idletasks()
        # 8b-RAISE (the gate finding): force create() to raise and prove
        #     the failure lands on _status_lbl (the create pane's OWN
        #     label), NOT the silent vanish. _mode_fail routes to
        #     _mode_status, which the create pane never builds - so the
        #     old guard died into its own except-pass on exactly the
        #     fresh-store launch the owner hit. Read the label back.
        _real_create = PF.create
        def _boom(*a, **k):
            raise RuntimeError("driver said no")
        PF.create = _boom
        try:
            app._prof_name.delete(0, "end")
            app._prof_name.insert(0, "willfail")
            app._profile_create()          # must NOT raise, must report
            # THE PUMP LAW (check_8c's, applied to capture since Oct-16
            # worker-ization): done() arrives on a cross-thread after,
            # so an instant read sees only "capturing...". Park here -
            # the fake must stay swapped until done() lands, or the
            # worker reads the RESTORED PF.create and really stores it.
            _t0p = time.time()
            while time.time() - _t0p < 5.0 and getattr(app, "_applying",
                                                       False):
                app.update()
                time.sleep(0.02)
            assert not getattr(app, "_applying", False), \
                "the capture worker never reported done() (5 s bound)"
            app.update_idletasks()
        finally:
            PF.create = _real_create
        _lbl = str(app._status_lbl.cget("text"))
        assert "create profile:" in _lbl and "driver said no" in _lbl, _lbl
        assert "willfail" not in _store()["profiles"], "the raise must not store"
        print("[PASS] create-now failure reports on the label that EXISTS")
        # 8b) THE CREATE-NOW BUTTON (defect 1): on the create-new pane
        #     (empty name -> the entry + "capture this desktop"), a
        #     click must CREATE one default-filled card, land it in the
        #     store, and switch the picker to it - the whole
        #     button -> create -> store -> card-list chain, through the
        #     real handler (the silent-death guard now reports any raise
        #     instead of vanishing). Drive it via the picker's NEW row.
        app._prof_name.delete(0, "end")
        app._prof_name.insert(0, "captured")
        app._profile_create()
        _t0p = time.time()
        while time.time() - _t0p < 5.0 and getattr(app, "_applying",
                                                   False):
            app.update()
            time.sleep(0.02)
        app.update_idletasks()
        assert not getattr(app, "_applying", False), \
            "the capture worker never reported done() (5 s bound)"
        store = _store()
        assert "captured" in store["profiles"], list(store["profiles"])
        _cap = store["profiles"]["captured"]
        assert _cap["displays"] and _cap["displays"][0]["id"] == "MONITOR\\T1", \
            _cap["displays"]
        assert app._prof_sel == "captured", app._prof_sel
        assert "captured" in str(app.profile_menu.cget("values")), \
            app.profile_menu.cget("values")
        # leave the window EXACTLY as section 8 found it (selection on
        # profile-1), or the pin test below renders the wrong profile
        # and the create-now step reads as a neighbour-breaker
        app._profile_picked("profile-1")
        app.update_idletasks()
        print("[PASS] create-now yields one loadable default-filled card")

        # 8c) THE LOUD LAYOUT REFUSAL (the loud-voice wave's visible-
        #     voice pin, scaffolded on 8b-RAISE: swap the fake, drive
        #     the REAL handler, restore after the outcome). The chain
        #     lives in check_8c below - THE PUMP LAW it obeys (why an
        #     update()-poll cannot watch a worker's marshaled done())
        #     is documented there.
        app.after(0, check_8c)
    except tk.TclError as why:
        if not _done:
            # Oct 12 audit, the silent partial: RDP artifact OR a
            # real mid-chain window failure - until every functional
            # assert has run, a TclError is a FAILED, not a teardown
            # story.
            FAILED.append("check (TclError before the asserts "
                          "finished: %s)" % str(why)[:60])
            __import__("traceback").print_exc()
        else:
            # RDP artifact (measured Oct 11): CTk's destroy chain runs
            # a winfo for its title-bar bookkeeping AFTER the
            # interpreter died, and composition latency under remote
            # desktop lets it lose the race; production never
            # re-enters this path.
            print("[teardown TclError tolerated: %s]" % str(why)[:60])
    except Exception:
        _fail("check")


_S8 = {}                 # the 8c chain's ledger: swap ledger + balloons


def _refusing_layout(entries):
    """8c's fake, speaking the REAL refusal shape (the loud-voice
    wave): the driver killed T1 (rc -1) and took T2 - the refusal line
    addresses the dead panel by its profile SHORT with RC_WHY's human
    word (gate finding 1: the applied half answers by SHORTS too now,
    built from the entries, never a row re-parse), exactly what
    _displaycfg emits, and the (False, lines) answer is what
    profiles.py's sentence builder must parse. The 1.5 s sleep is the
    cold-driver stand-in (same tax class hdrwake_test walks): it
    holds BOTH acts' walks deterministically in flight - act 1's pump
    proves the loud pane survives a slow driver, act 2's mid-apply
    switch (the gate's finding 2) gets its race-free window."""
    time.sleep(1.5)
    lines, dead = [], []
    for e in entries:
        rc = -1 if e["gdi"] == r"\\.\DISPLAY1" else 0
        lines.append("enable %s %dx%d@%d -> %d" % (
            e["gdi"], e.get("w") or 0, e.get("h") or 0,
            e.get("rate") or 0, rc))
        if rc:
            dead.append(e)
    lines.append("commit -> 0")
    for e in dead:
        # rc -1: the fake driver failed the switch on T1
        lines.append("refused %s: %s (desk left partial)" % (
            e.get("short") or e["gdi"], DC.RC_WHY[-1]))
    return not dead, lines


def check_8c():
    """the visible-voice pin (the loud-voice wave) and the reason the
    chain exists: the worker marshals done() with a cross-thread
    after(), and the main thread must be PARKED in mainloop for the
    marshal to land (measured Oct 14 on the pre-suite probe: an
    update()-poll races it and loses it to "main thread is not in main
    loop" - the frozen "reshaping..." label the probe caught). Every
    hop re-arms until _prof_err shows or the 5 s bound (the packet's)
    expires; the assertions ride this terminal hop, then ACT 2 (the
    gate's finding 2, the mid-apply switch) hands the former tail to
    check_8e below."""
    global _done
    try:
        if "t0" not in _S8:
            _S8["real"] = WM.apply_layout
            WM.apply_layout = _refusing_layout
            _S8["balloons"] = []
            fm.notifier = _S8["balloons"].append
            app._profile_picked("captured")
            app.update_idletasks()
            app._profile_apply(False)   # the REAL verb, real worker
            _S8["t0"] = time.time()
            app.after(20, check_8c)
            return
        if not getattr(app, "_prof_err", False) and \
                time.time() - _S8["t0"] < 5.0:
            app.after(20, check_8c)     # park; let done() land
            return
        assert getattr(app, "_prof_err", False), \
            "the refusal never armed the pane's voice (5 s bound)"
        app.update()                    # fresh geometry for the asserts
        _lbl = str(app._status_lbl.cget("text"))
        assert "layout refused" in _lbl and "refused T1" in _lbl, _lbl
        assert str(app._status_lbl.cget("text_color")).lower() == \
            app.skin.danger.lower(), app._status_lbl.cget("text_color")
        # THE GAZE GEOMETRY (the packet's regression pin against re-
        # basementing, plus the gate's finding 5 FLOOR): the voice's
        # top edge sits AT the gaze - within one field step under the
        # apply buttons' bottom edge (the literal "root-y ABOVE the
        # button's bottom" cannot hold for a label the create-new
        # precedent packs S_FIELD under; the probe measured gap 4 px),
        # and never at a NEGATIVE gap, which would mean the voice was
        # re-packed onto the buttons' roof. A re-basementing drops it
        # a whole section down; both directions are pinned now.
        _btn = app._apply_btns[0]
        _gap = app._status_lbl.winfo_rooty() - (
            _btn.winfo_rooty() + _btn.winfo_height())
        assert 0 <= _gap <= 50, \
            "the refusal voice sits %d px off the apply buttons' " \
            "bottom edge - moved off the gaze (floor: gate finding 5)" \
            % _gap
        assert len(_S8["balloons"]) == 1, _S8["balloons"]  # exactly one
        assert _S8["balloons"][0].startswith("profile 'captured': "
                                             "layout refused"), \
            _S8["balloons"][0]
        assert "refused T1" in _S8["balloons"][0], _S8["balloons"][0]
        print("[PASS] layout refusal shouts at the gaze (danger label, "
              "gaze geometry with its floor, exactly one addressed "
              "balloon)")

        # ACT 2 (the gate's finding 2): the user moves on MID-APPLY.
        # The shout belongs to the profile that was applied: on a
        # moved-on pane the flag may not ride the next render
        # stale-red, while the balloon still carries the moved-on
        # truth cross-tab. The fake's 1.5 s sleep holds the walk in
        # flight across the switch - the pin has no race. (The fake
        # stays swapped: act 2 drives through it too, check_8e
        # restores.)
        app._profile_picked("captured")
        app.update_idletasks()
        app._profile_apply(False)           # worker busy on the fake
        app._profile_picked("profile-1")    # the user moves on
        _S8["t1"] = time.time()
        app.after(20, check_8e)
    except tk.TclError as why:
        if not _done:
            # Oct 12 audit, the silent partial: RDP artifact OR a
            # real mid-chain window failure - until every functional
            # assert has run, a TclError is a FAILED, not a teardown
            # story.
            FAILED.append("check_8c (TclError before the asserts "
                          "finished: %s)" % str(why)[:60])
            __import__("traceback").print_exc()
        else:
            # RDP artifact (measured Oct 11): CTk's destroy chain runs
            # a winfo for its title-bar bookkeeping AFTER the
            # interpreter died, and composition latency under remote
            # desktop lets it lose the race; production never
            # re-enters this path.
            print("[teardown TclError tolerated: %s]" % str(why)[:60])
    except Exception:
        _fail("check_8c")


def check_8e():
    """act 2's landing (the gate's finding 2): done() delivered while
    another profile is selected - the moved-on pane must show the
    outcome line WITHOUT the stale red (the flag is the applied
    profile's own), and the second balloon proves the moved-on truth
    travelled anyway. The shout's per-outcome calm (finding 2's
    other half: picking another profile still resets) is asserted
    here too, after the delivery. The former tail (sections 9/10)
    rides this terminal hop."""
    global _done
    try:
        if len(_S8["balloons"]) < 2 and \
                time.time() - _S8["t1"] < 5.0:
            app.after(20, check_8e)         # park; let done() land
            return
        WM.apply_layout = _S8["real"]       # BOTH acts delivered -
        #                                    the fake is done with
        app.update()
        assert len(_S8["balloons"]) == 2, _S8["balloons"]  # one per act
        assert _S8["balloons"][1].startswith("profile 'captured': "
                                             "layout refused"), \
            _S8["balloons"][1]
        assert app._prof_err is False, \
            "stale red rode the moved-on pane (gate finding 2)"
        _lbl2 = str(app._status_lbl.cget("text"))
        assert "layout refused" in _lbl2, _lbl2   # truth still shown
        assert str(app._status_lbl.cget("text_color")).lower() == \
            app.skin.subtext.lower(), app._status_lbl.cget("text_color")
        # the shout is per-outcome: picking another profile calms it
        # (the wave's original reset law, re-pinned after the storm)
        assert app._prof_err is False, "the danger outlived its outcome"
        print("[PASS] mid-apply switch: no stale red on the moved-on "
              "pane, outcome shown calm, truth travelled (finding 2)")

        # 9) owner sketch (Oct 12): the tab is TWO columns side by
        #    side - whole-desktop profiles + restore on the left,
        #    the pin half on the right. The check runs from an
        #    after() callback INSIDE mainloop (the 8c chain's hops
        #    park there too), so the window is mapped; one full event
        #    pass makes that certain anyway.
        app.update()
        assert app._prof_left.winfo_manager() == "pack", \
            app._prof_left.winfo_manager()
        assert app._prof_right.winfo_manager() == "pack", \
            app._prof_right.winfo_manager()
        # rootx, not winfo_x: inside canvas-hosted widgets (the page
        # and both pin lists ARE ScrollHosts) Tk reports x relative
        # to the nearest canvas (measured Oct 12: every row read 0
        # while its sub-column read 312) - rootx survives the nesting
        assert app._prof_left.winfo_rootx() != \
            app._prof_right.winfo_rootx(), \
            (app._prof_left.winfo_rootx(), app._prof_right.winfo_rootx())
        print("[PASS] profile columns managed side by side")

        # 10) pin rows (owner sketch, re-cut by the Oct-15 UAT LIST
        #     law): a PROCESS-matched pin reads as the exe basename,
        #     a title-matched pin keeps its title, and the list is a
        #     LIST - six seats ride ONE full-width column (the old
        #     two-sub-column flow, asserted here since Oct 12, is
        #     retired; this pin now guards the LIST law). Pin through
        #     the real PF.pin primitive so the row dicts carry the
        #     real schema.
        for i, proc in enumerate(("chrome.exe", "discord.exe",
                                  "steam.exe", "code.exe",
                                  "explorer.exe")):
            PF.pin(app._prof_data, "profile-1",
                   {"proc": proc, "title": "win%d" % i,
                    "rect": [0, 0, 10, 10], "zoomed": False,
                    "monitor": "T1", "exe": r"C:\apps\%s" % proc},
                   match="process")
        PF.pin(app._prof_data, "profile-1",
               {"proc": "notepad.exe", "title": "Untitled - Notepad",
                "rect": [0, 0, 10, 10], "zoomed": False,
                "monitor": "T1", "exe": r"C:\Windows\notepad.exe"},
               match="title")
        app._profiles_render()
        app.update()
        _row, _btn = app._pin_rows[("chrome.exe", "win0")]
        assert str(_btn.cget("text")).startswith("chrome.exe"), \
            _btn.cget("text")
        _trow, _tbtn = app._pin_rows[("notepad.exe",
                                      "Untitled - Notepad")]
        assert str(_tbtn.cget("text")).startswith("Untitled - Notepad"), \
            _tbtn.cget("text")
        xs = sorted({f.winfo_rootx() for f, _ in app._pin_rows.values()})
        assert len(xs) == 1, xs          # the LIST law: one column,
        assert int(_btn.cget("width")) == 400   # every row full width
        print("[PASS] process pins read as exe basenames; 6 seats ride "
              "ONE full-width column (the LIST law)")
        _done = True                 # teardown noise tolerated ONLY
                                     # past this line, see _done

        try:
            app.after_cancel(wd)         # the desk is done watching
        except Exception:
            pass
        app.destroy()          # the checks are done: end the loop
    except tk.TclError as why:
        if not _done:
            # Oct 12 audit, the silent partial: RDP artifact OR a
            # real mid-chain window failure - until every functional
            # assert has run, a TclError is a FAILED, not a teardown
            # story.
            FAILED.append("check_8e (TclError before the asserts "
                          "finished: %s)" % str(why)[:60])
            __import__("traceback").print_exc()
        else:
            # RDP artifact (measured Oct 11): CTk's destroy chain runs
            # a winfo for its title-bar bookkeeping AFTER the
            # interpreter died, and composition latency under remote
            # desktop lets it lose the race; production never
            # re-enters this path.
            print("[teardown TclError tolerated: %s]" % str(why)[:60])
    except Exception:
        _fail("check_8e")


# hard backstop (gaming_ui_test.py:449-461 shape): if the Tk event
# loop itself stops processing, the after-based watchdog above never
# fires and this process would hang the whole sweep. This daemon
# kills at 120 s with rc=3 - the run_all table's hard-kill code.
def _hard_kill():
    time.sleep(200)
    print("HARD KILL after 120 s: the Tk event loop stopped "
          "processing - killing so the sweep cannot hang",
          flush=True)
    os._exit(3)


def _watchdog():
    # the 8c chain replaced the linear runner, and with it the module's
    # ONLY reference to this name - first app-down run of the whole
    # file (Oct 14 ceremony) found the scaffold calling a function the
    # chain had never defined. Defined now, with the census instrument
    # so a future bite names itself (gaming_ui's model).
    print("WATCHDOG FIRED after 60 s", flush=True)
    for t in threading.enumerate():
        print("  thread:", t.name, "daemon=", t.daemon,
              "alive=", t.is_alive(), flush=True)
    print("WINDOW TEST FAILED in ['chain', 'watchdog']", flush=True)
    os._exit(1)


threading.Thread(target=_hard_kill, daemon=True).start()

# bracket re-arm (Oct 14, the OLED tab's window-cost teaching): the
# camera enumerate door gets ~60 s to report its own dead verdict
# (watchdog.ENUMERATE_DOOR_BUDGET_SEC, NVIDIA warm-open arithmetic);
# a 60 s watchdog raced that boundary and lost every race the desk
# state could lose. 110 s still kills a true hang in one sweep minute.
wd = app.after(110000, _watchdog)
app.after(600, check)
try:
    app.mainloop()
except tk.TclError:
    pass                     # same artifact class: CTk's title-bar
                             # re-assert can meet a destroyed app the
                             # moment check() returns from destroy
if FAILED:
    print("WINDOW TEST FAILED in", FAILED)
    sys.exit(1)
print("profiles ui OK")
