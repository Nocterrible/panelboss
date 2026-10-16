"""The setup screen's behavior contract (redesign stage 3): the
retire law on the pane that replaced the wizard, the source ban over
the whole UI package, and - where a display exists - a real
SetupWindow on faked doors: cards spawn per settle, the veil counts
truthfully to done, OK posts the identity verbs, the duty-roster
write (amendment 6's add boxes: seeded from the roster, grayed at
the four-feed ceiling, re-lit on uncheck) and the consent enable,
and the close retires by schedule. The fix wave (owner UAT, four
defects) pins the ANSWER (the ask is the stdlib box, the phantom
message box is banned), the UNBLIND (every exit resyncs the tab from
cfg truth), the DEADLINE (a faked wedged door: the veil names the
stall, the row draws dead, OK appears regardless), and the WHEEL
(disabled means the wheel does not move - on a MAPPED window, the
measured pin trap). The pure data contract (rows_from / card_spec /
ok_verbs / add_ceilings / veil_text) is truth-tabled here and in
camdiag_test section 9; this file owns the window's behavior."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SCRATCH = tempfile.mkdtemp(prefix="panelboss_assign_")
os.environ.setdefault("PANELBOSS_CONFIG_DIR", SCRATCH)

import numpy as np

from panelboss import camera as cam_mod
from panelboss import config
from panelboss.ui.window import _assign
import panelboss.ui.window._detection as _det
from panelboss.ui.window._assign import CEILING_NOTE as _CEILING_TXT

fails = []


def check(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# 1) the retire law on the NEW pane (the wizard's CloseSpy, retired
#    with its window and re-aimed at the successor): withdraw first,
#    destroy on the loop's next clean turn, ONCE, and the pane
#    refresh obeys consent - a closed WITHOUT enabling must not
#    start the scan the gate just refused.
class Spy:
    _close = _assign.SetupWindow._close

    def __init__(self, enabled=False):
        self._dying = False
        self.withdrawn = 0
        self.scheduled = []
        self.destroyed = 0
        self.scans = 0
        self.syncs = 0
        self.app = type("A", (), {})()
        self.app.cfg = {"camera": {"enabled": enabled}}
        self.app._scan_cameras = lambda *a, **k: setattr(
            self, "scans", self.scans + 1)
        self.app._sync_consent_switch = lambda: setattr(
            self, "syncs", self.syncs + 1)

    def withdraw(self):
        self.withdrawn += 1

    def after(self, delay, hook):
        self.scheduled.append((delay, hook))

    def destroy(self):
        self.destroyed += 1


s = Spy()
s._close()
check(s.withdrawn == 1 and s.destroyed == 0,
      "close withdraws and SCHEDULES the destroy (never its own stack)")
check(s.scheduled and s.scheduled[0][0] == 0,
      "the retire rides the loop's next clean turn")
check(s.scans == 0, "X on a never-enabled boot does not open the doors")
check(s.syncs == 1, "the X re-syncs the tab from cfg truth (defect 3)")
s.scheduled[0][1]()
check(s.destroyed == 1, "the scheduled destroy lands")
s._close()
check(s.destroyed == 1 and s.syncs == 1,
      "retire ONCE, resync ONCE (the X + OK burst cannot double)")
ok = Spy(enabled=True)
ok._close(refresh=True)
check(ok.scans == 1 and ok.syncs == 1,
      "OK refreshes the picker (captions follow the setup)")
en = Spy(enabled=True)
en._close()
check(en.scans == 1 and en.syncs == 1,
      "an X on an enabled desk still refreshes captions")

# 2) the source ban, app-wide this time: no command= may point a
#    button straight at destroy() anywhere in the UI package - the
#    crash law is not one window's property anymore. The lambda form
#    rides the same law (gate finding 4), so the ban takes a regex
#    for it on top of the literal
import pathlib
import re as _re
bad = []
_ui = pathlib.Path(_assign.__file__).parent.parent   # the ui package
for p in sorted(_ui.rglob("*.py")):
    text = p.read_text(encoding="utf8")
    if "command=self.destroy" in text or _re.search(
            r"command\s*=\s*lambda[^)]*\.destroy\(", text):
        bad.append(p.name)
check(not bad, "no UI file destroys its own toplevel from a callback: %s"
      % (bad,))
check("WM_DELETE_WINDOW" in pathlib.Path(_assign.__file__).read_text(
    encoding="utf8"), "the setup's X is routed, not default")

# 2d) the consent ask's grave, and the resync's structure (owner UAT
#     fix wave A, defects 1+3): the venv's customtkinter 6.0 has NO
#     CTkMessagebox (measured AttributeError) and the old except
#     manufactured "Yes" into that hole - the ban keeps the name from
#     ever returning, and the LOUD fallback must ride with it. The
#     unblind law is STRUCTURAL: the resync call site lives inside
#     _close itself (every exit routes through it), not in a callback
#     that a rebuilt tab could forget.
_as_src = pathlib.Path(_assign.__file__).read_text(encoding="utf8")
_de_src = pathlib.Path(pathlib.Path(_assign.__file__).parent
                       / "_detection.py").read_text(encoding="utf8")
check("CTkMessagebox" not in _de_src,
      "the phantom message box stays banned from _detection: the ctk "
      "6.0 venv has no CTkMessagebox, the except made that a silent Yes")
check("askyesno" in _de_src, "the ask is the stdlib message box")
check("log.exception" in _de_src,
      "a consent ask that cannot draw is LOUD (the headless fallback)")
_i = _as_src.index("def _close(self")
_blk = _as_src[_i:]
_nx = _re.search(r"\n    def ", _blk)
check(_nx and "_sync_consent_switch" in _blk[:_nx.start()]
      and "getattr" in _blk[:_nx.start()],
      "every window exit re-syncs the tab from cfg truth (inside _close)")

# 2e) the veil's line, pure (defect 2b): silence gets a shape, a
#     NAME, and a count - truth-tabled, no widgets
_vt = _assign.veil_text
check(_vt(0, 0) == "done", "an empty board is a done board (no veil prison)")
check(_vt(2, 5) == "testing cameras... (2 of 5)  ·  starting",
      "no beat yet says starting, not nothing")
check(_vt(2, 5, "1", 2)
      == "testing cameras... (2 of 5)  ·  probing 1, 2 waiting",
      "the stalling feed is NAMED and its queue counted")
check(_vt(0, 1, "ir Face IR", 0)
      == "testing cameras... (0 of 1)  ·  probing ir Face IR",
      "the IR sentinel is nameable; an empty queue drops the clause")
check(_vt(5, 5, "1") == "done", "done outranks every progress line")
check(_assign.row_label({"idx": 3, "group": None}) == "3"
      and _assign.row_label({"idx": None, "group": "G1"}) == "ir G1",
      "row_label: the index, or the IR group")

# 2b) the card SEED law (gate finding 2 - the second-run trap): a
#     rerun must not undo the desk it is showing. Offline on the
#     core, no widgets - a truth table over the four arms
_row_bright = {"key": "USB\\G", "name": "Glass", "idx": 0, "detail": ""}
_row_dark = {"key": "idx:4", "name": "", "idx": 4, "detail": ""}
spec = _assign.card_spec
check(spec(_row_bright, False)["checked"] is False,
      "(d) bright, untouched -> UNCHECKED (silence is not a claim)")
check(spec(_row_dark, True)["checked"] is True,
      "(c) plain dark, untouched -> CHECKED (the dark default)")
check(spec(_row_bright, False, {"hidden": ["USB\\G"]})["checked"] is True,
      "(a) a hidden bright camera renders CHECKED")
check(_assign.ok_verbs([("USB\\G", "Glass", "Glass", False, True)])
      == [("camera_identity", {"instance": "USB\\G", "show": True})],
      "(a) unchecking it posts the show verb - the card cannot strand "
      "a hidden bright camera")
check(spec(_row_dark, True, {"shown": ["idx:4"]})["checked"] is False,
      "(b) a dark feed the owner SHOWN arrives UNCHECKED (sticky)")
check(spec(_row_dark, True, {"labels": {"idx:4": "N"}})["checked"]
      is False,
      "(b) a dark feed with a saved label arrives UNCHECKED (touched)")
check(_assign.ok_verbs([("idx:4", "", "", False, False)]) == [],
      "(b) OK-on-silence over an untouched desk posts NOTHING - no "
      "re-hide of the immune camera")

# 2c) the empty-pane hint lives at the rebuild cycle's TAIL (gate
#     finding 1: stage 4's insertion had orphaned it below a return,
#     where it could never paint). Offline and source-level: the
#     constant must sit in _rebuild_cam_rows, not in _show_back -
#     an empty roster says so in the row zone, whatever the hidden
#     list below it shows
import panelboss.ui.window._camedit as _ce
_src = pathlib.Path(_ce.__file__).read_text(encoding="utf8")
_block = {}
for _m in _re.finditer(r"^    def (\w+)", _src, _re.M):
    _name = _m.group(1)
    _start = _m.start()
    _next = _re.search(r"^    (?:def |class )", _src[_m.end():], _re.M)
    _block[_name] = _src[_start:_start + _next.end()] if _next \
        else _src[_start:]
check(_ce.EMPTY_HINT == "no cameras on duty - add one above",
      "the dead desk's cue survives as a spec-level constant")
check("EMPTY_HINT" in _block["_rebuild_cam_rows"],
      "the empty hint paints from _rebuild_cam_rows' tail")
check("EMPTY_HINT" not in _block["_show_back"],
      "the empty hint is not orphaned inside _show_back (dead code)")

# 3) the window, for real, on faked doors (headless boxes skip it
#    loud-and-quiet like camid's smoke always did)
try:
    import queue as _q
    import customtkinter as ctk
    from panelboss.ui import theme

    ctk.set_appearance_mode("dark")

    class FakeEye:
        def __init__(self, index=0, group=None, alive=True):
            self.index = index
            self.released = False
            self._alive = alive

        def read(self, timeout=3, screen=None):
            return (np.full((60, 80, 3), 37, np.uint8) if self._alive
                    else None)

        def release(self):
            self.released = True

        def is_open(self):
            return True

    cfg = config.get_config(dir=SCRATCH, verbose=False)
    cfg["camera"]["enabled"] = True
    cfg["camera"]["index"] = [0, 1, -2]          # the duty seed the
                                                 # add boxes must read
                                                 # (amendment 6): two
                                                 # cams + the IR seat

    class Host(ctk.CTk):
        def __init__(self):
            super().__init__()
            self.withdraw()
            self.cfg = cfg
            self.skin = theme.get_skin(cfg["ui"]["skin"])
            self.monitor = type("M", (),
                                {"events": _q.Queue()})()
            self.scans = []
            self.syncs = []
            self._scan_cameras = lambda *a, **k: self.scans.append(1)
            # the defect-3 seam on the REAL window: _close re-syncs
            # the tab through this method (the Spy pins the guard's
            # once-ness; this pins that the live window uses it)
            self._sync_consent_switch = lambda: self.syncs.append(1)

    _real_cd = cam_mod.camera_devices
    _real_ec = cam_mod.enumerate_cameras
    _real_cam = cam_mod.Camera
    _real_irn = cam_mod.hello_ir_names
    _real_ir = cam_mod.HelloIrCamera
    cam_mod.camera_devices = lambda: [
        {"name": "Glass", "instance": "USB\\G", "status": "OK"}]
    cam_mod.enumerate_cameras = lambda *a, **k: [(0, True, 1280.0,
                                                  "Glass"),
                                                 (1, True, 1280.0,
                                                  "Second"),
                                                 (3, False, 0.0, ""),
                                                 (4, False, 0.0, "")]
    cam_mod.hello_ir_names = lambda: ["Face IR"]
    cam_mod.Camera = lambda index=0, **kw: FakeEye(
        index, alive=(index in (0, 1)))
    cam_mod.HelloIrCamera = lambda group=None, **kw: FakeEye(group=group)
    def _retire(host):
        # ctk reschedules its DPI check forever; destroying a host
        # with those afters pending lets a LATER section's event
        # pump consume the corpse (the measured bgerror wall this
        # wave grew). Cancel on the way out: no ghosts for the next
        # window's update() to trip over.
        for _aid in host.tk.call("after", "info"):
            try:
                host.tk.call("after", "cancel", _aid)
            except Exception:
                pass
        host.destroy()

    _h = Host()
    _w = _assign.SetupWindow(_h)
    for _ in range(40):                        # pump the 60 ms drain
        _h.update()
        import time as _t
        _t.sleep(0.03)                         # and the real clock
    cards = {c["key"]: c for c in _w._cards}
    check(set(cards) == {"USB\\G", "idx:1", "idx:3", "idx:4",
                         "ir:Face IR"},
          "cards spawn per settle: named, dead indexes, IR group: %s"
          % sorted(cards))
    check(_w.veil.cget("text") == "done", "the veil settles to done")
    check(cards["idx:4"]["started"] is True and
          cards["USB\\G"]["started"] is False,
          "the dark seat arrives CHECKED, the bright one free")
    # amendment 6, live board: the roster seeds the add boxes (an
    # on-duty feed CANNOT be dropped by omission - the seat rides the
    # sentinel for IR too), the ceiling grays ONLY at four checked and
    # ONLY the unchecked, and the reason rides the count.
    check(cards["USB\\G"]["add_started"] is True
          and cards["ir:Face IR"]["add_started"] is True
          and cards["idx:3"]["add_started"] is False,
          "add boxes seed from the duty roster, sentinel included")
    check(cards["idx:4"]["add_box"].cget("state") != "disabled",
          "under the ceiling every box is live")
    cards["idx:3"]["add"].set(True)            # owner claims a dead seat
    check(cards["idx:4"]["add_box"].cget("state") == "disabled",
          "at four checked the 5th add-box grays (and only it)")
    check(cards["idx:3"]["add_box"].cget("state") != "disabled"
          and cards["USB\\G"]["add_box"].cget("state") != "disabled",
          "checked boxes never gray - the way out is to give one up")
    check(_CEILING_TXT in _w._count.cget("text"),
          "the one-line reason rides the count")
    cards["ir:Face IR"]["add"].set(False)      # give the IR seat up
    check(cards["idx:4"]["add_box"].cget("state") != "disabled",
          "unchecking RE-LIGHTS the board")
    check(_w.ok_button.winfo_manager() == "pack", "OK appears at n of n")
    kept = [c for c in _w._cards if c["key"] == "idx:4"][0]
    kept["var"].set(False)                     # owner KEEPS the dark
                                               # one: silence in the
                                               # entry (no rename -
                                               # the diff-only law
                                               # must stay silent)
    _w._ok()
    verbs = list(_h.monitor.events.queue)
    kinds = [v[0] for v in verbs]
    check(("camera_enabled", True) in verbs,
          "OK completes the enable through the loop's queue")
    check(("camera", [0, 1, 3]) in verbs,
          "the roster write is the EXISTING verb, posted exactly as "
          "checked (sorted set): %s" % [v for v in verbs
                                        if v[0] == "camera"])
    keep = [v for v in verbs
            if v[0] == "camera_identity" and
            v[1].get("instance") == "idx:4"]
    check(keep and keep[0][1].get("show") is True,
          "a kept dark seat posts the STICKY show verb: %s" % keep)
    check(_w._dying, "OK retires: withdrawn and guarded, destroy pending")
    check(len(_h.syncs) == 1,
          "OK's exit re-syncs the tab once (defect 3, real window)")
    for _ in range(5):                         # the host loop runs
        _h.update()                            # the scheduled destroy
    check(not _w.winfo_exists(),
          "the scheduled destroy lands (no leak, no zombie toplevel)")
    _retire(_h)
    cam_mod.camera_devices = _real_cd
    cam_mod.enumerate_cameras = _real_ec
    cam_mod.Camera = _real_cam
    cam_mod.hello_ir_names = _real_irn
    cam_mod.HelloIrCamera = _real_ir

    # ---- defect 2 (owner UAT, the 18:33 stall shape): a door that
    # never returns. The wedged fallback driver cannot be summoned on
    # demand (and the owner's desk was busy), so the faked door
    # reproduces the SHAPE - a read that blocks forever - and the
    # deadline machinery must out-argue it: the veil NAMES the stall
    # while it lives, the row draws dead, and OK appears REGARDLESS
    # (defect 2c) so a wedged door cannot eat the exit. The deadline
    # constants shrink to a coffee-cup scale and return in finally.
    import threading as _thr
    import time as _time
    _stall = _thr.Event()                      # never set: the wedged
    class StalledEye(FakeEye):                 # cap.read() that went
        def read(self, timeout=3, screen=None):
            _stall.wait()                      # inside the driver
            return None

    _saved = (_assign.FRAME_BUDGET, _assign.MARGIN_SEC,
              cam_mod.OPEN_LOCK_TIMEOUT)
    try:
        _assign.FRAME_BUDGET = 0.2
        _assign.MARGIN_SEC = 0.2               # row deadline 0.6 s,
        cam_mod.OPEN_LOCK_TIMEOUT = 0.2        # board the same
        cam_mod.camera_devices = lambda: []
        cam_mod.enumerate_cameras = lambda *a, **k: [
            (9, True, 1280.0, "Wedged")]
        cam_mod.hello_ir_names = lambda: []
        cam_mod.Camera = lambda index=0, **kw: StalledEye(index)
        _h2 = Host()
        _w2 = _assign.SetupWindow(_h2)
        _veils = []
        for _ in range(40):                    # past two board deadlines
            _h2.update()
            _veils.append(_w2.veil.cget("text"))
            _time.sleep(0.03)
        check(any(t.startswith("testing cameras... (0 of 1)")
                  and "probing 9" in t for t in _veils),
              "the veil NAMED the stalling feed while it lived: %r"
              % [t for t in _veils if "probing" in t][:2])
        cards2 = {c["key"]: c for c in _w2._cards}
        check(set(cards2) == {"idx:9"},
              "the stalled row gets exactly ONE dead card: %s"
              % sorted(cards2))
        check(cards2["idx:9"]["started"] is True,
              "drawn dead means drawn HIDDEN, the dark-feed default")
        check(_w2.veil.cget("text") == "done",
              "the stalled board settles to done (defect 2b/2c)")
        check(_w2.ok_button.winfo_manager() == "pack",
              "OK appears when the last row DIES, not only at n of n")
        check(not _h2.syncs, "a live window has not earned the resync")
        _w2._close()                           # the X on a stalled board
        check(len(_h2.syncs) == 1,
              "the exit un-blinds the tab even from a stalled board")
        for _ in range(5):
            _h2.update()
        check(not _w2.winfo_exists(), "the stalled setup retires clean too")
        _retire(_h2)
    finally:
        _assign.FRAME_BUDGET, _assign.MARGIN_SEC = _saved[0], _saved[1]
        cam_mod.OPEN_LOCK_TIMEOUT = _saved[2]
        cam_mod.camera_devices = _real_cd
        cam_mod.enumerate_cameras = _real_ec
        cam_mod.Camera = _real_cam
        cam_mod.hello_ir_names = _real_irn

    # ---- wave D: the gather fence closes around the IR call, the
    # veil counts BEFORE the count, and an empty board speaks.
    # Fake enumerate observes the pump deadline from INSIDE the
    # walk (arm-at-gather-start is otherwise unfalsifiable from the
    # pump side - anything non-zero could be the old construction
    # row math), fake rows beat on_row while the walk lives, and
    # two empty-board windows check the NEW LAW: with an engine
    # warning the veil quotes it, without one it still says the
    # bare honest line. Budget constants shrink to the same
    # coffee-cup scale as the stall section (patchable = live).
    import logging as _logging
    import time as _wt
    _s2 = (_assign.FRAME_BUDGET, _assign.MARGIN_SEC,
           cam_mod.ENUMERATE_DOOR_BUDGET_SEC, cam_mod.IR_BUDGET_SEC,
           cam_mod.OPEN_LOCK_TIMEOUT)
    cam_mod.ENUMERATE_DOOR_BUDGET_SEC = 0.5     # arm = 8*0.5+0.5+0.2
    cam_mod.IR_BUDGET_SEC = 0.5                 #    = 4.7 s (live)
    cam_mod.OPEN_LOCK_TIMEOUT = 0.2             # the row arm re-
    _assign.FRAME_BUDGET = 0.2                  # arms at n*0.4+0.2 -
    _assign.MARGIN_SEC = 0.2                    # SMALLER than the
                                                # live enumerate arm,
                                                # so the min visibly
                                                # SHORTENS
    _arm = {}
    _veils2 = []

    def _slow_enum(*a, **k):
        _rows_ = [(2, True, 1280.0, "Dressed")]
        _wt.sleep(0.05)                     # the ctor's return binds _w4
        _arm["at"] = _w4._deadline_at - _wt.monotonic()
        _wt.sleep(1.0)                      # long enough for pump
        for r_ in _rows_:                   # ticks of enumerating line
            k["on_row"](r_[:3])             # (item 3 beats, item 1 clock)
        _wt.sleep(0.4)                      # let the BEAT line live
                                            # a few ticks before the
                                            # board closes the phase
        return [r_[:3] for r_ in _rows_]

    cam_mod.enumerate_cameras = _slow_enum
    cam_mod.camera_devices = lambda: []
    cam_mod.hello_ir_names = lambda: []
    cam_mod.Camera = lambda index=0, **kw: FakeEye(
        index, alive=(index == 2))          # fake doors only - the
    _h4 = Host()                            # owner's desk owes us no
    _w4 = _assign.SetupWindow(_h4)          # LED flicker
    for _ in range(50):
        _h4.update()
        _veils2.append(_w4.veil.cget("text"))
        _wt.sleep(0.03)
    check(_arm.get("at") is not None and 4.0 < _arm["at"] < 5.0,
          "deadline armed at GATHER START, enumerate-sized (observed "
          "from INSIDE the walk: %.2f s of budget pre-board; the row "
          "re-arm below may only shorten it)" % _arm.get("at", -1))
    check(any(t.startswith("enumerating cameras...") and " s" in t
              for t in _veils2),
          "the pre-board veil names its phase and COUNTS SECONDS "
          "(alive-and-counting is honest pre-count)")
    check(any("last index 2, 1 seen" in t for t in _veils2),
          "the enumerate beats ride the veil (item 3): the walk "
          "resolves, the line knows")
    check(_w4._deadline_at - _wt.monotonic() < 1.0,
          "the at-return re-arm SHORTENED the arm (min): a late "
          "gather cannot extend the dialog's patience")
    _retire(_h4)

    # the NEW LAW, two voices: confessing...
    def _empty_enum_warn(*a, **k):
        _logging.getLogger("camera").warning("no enumerator on this desk")
        return []

    cam_mod.enumerate_cameras = _empty_enum_warn
    _h5 = Host()
    _w5 = _assign.SetupWindow(_h5)
    for _ in range(10):
        _h5.update()
        _wt.sleep(0.03)
    check(_w5.veil.cget("text")
          == "no cameras answered - no enumerator on this desk",
          "the empty board SPEAKS with the engine's first warning "
          "(the log line, where the owner is looking): %r"
          % _w5.veil.cget("text"))
    check(_w5.ok_button.winfo_manager() == "pack",
          "the speaking board still hands out the exit")
    _retire(_h5)
    # ...and bare-honest (no warning ever landed)
    cam_mod.enumerate_cameras = lambda *a, **k: []
    _h6 = Host()
    _w6 = _assign.SetupWindow(_h6)
    for _ in range(10):
        _h6.update()
        _wt.sleep(0.03)
    check(_w6.veil.cget("text") == "no cameras answered",
          "no cards, no warnings: the bare honest line, never silence")
    _retire(_h6)
    _assign.FRAME_BUDGET, _assign.MARGIN_SEC = _s2[0], _s2[1]
    cam_mod.ENUMERATE_DOOR_BUDGET_SEC = _s2[2]
    cam_mod.IR_BUDGET_SEC = _s2[3]
    cam_mod.OPEN_LOCK_TIMEOUT = _s2[4]

    # ---- defect 4 (owner UAT): a grayed slider that still took the
    # wheel was a disabled that lied. THE PIN TRAP (measured twice
    # before believing it): event_generate on an UNMAPPED canvas is a
    # SILENT NO-OP - the handler never runs and the value sits even
    # when the wheel should work - so the window is MAPPED (position
    # parked off the visible desk) and the ENABLED leg is asserted
    # FIRST: if delivery ever dies the pin fails loudly instead of
    # the disabled leg passing by accident.
    _hw = ctk.CTk()
    _hw.geometry("+12000+12000")
    _gate = ctk.CTkFrame(_hw)
    _gate.pack()
    _sl = ctk.CTkSlider(_gate, from_=0.1, to=0.9, number_of_steps=80,
                        width=180)
    _sl.pack()
    _sl.set(0.5)
    _hw.deiconify()
    _hw.update()

    class _Walker(_det._DetectionMixin):
        pass

    _walk = _Walker()
    # the three legs exercise the swap machinery, which is live only
    # with per-slider wheels: the scroll law's default (False) makes
    # the swap unbind both arms - so the machinery runs True, and the
    # law leg gets the restored default.
    theme.SCROLL_SLIDERS = True
    _walk._gate_widgets(_gate, "normal")
    _sl._canvas.event_generate("<MouseWheel>", delta=120)
    _hw.update()
    _v1 = _sl.get()
    check(_v1 != 0.5, "the wheel is REAL on this pin (the mapped-window "
          "trap, measured: an unmapped canvas drops it silently)")
    _walk._gate_widgets(_gate, "disabled")
    _sl._canvas.event_generate("<MouseWheel>", delta=120)
    _hw.update()
    check(_sl.get() == _v1, "the DISABLED slider ignores the wheel")
    _walk._gate_widgets(_gate, "normal")       # the un-gray returns it
    _sl._canvas.event_generate("<MouseWheel>", delta=120)
    _hw.update()
    check(_sl.get() != _v1,
          "the RE-ENABLED slider answers the wheel again (no steal)")
    theme.SCROLL_SLIDERS = False
    _walk._gate_widgets(_gate, "normal")       # the re-enabled slider...
    # the law's own baseline: the wrap's last leg moved the value, so
    # _v1 is re-sampled here - the check below is the law, "the wheel
    # does not move it"
    _v1 = _sl.get()
    _sl._canvas.event_generate("<MouseWheel>", delta=120); _hw.update()
    check(_sl.get() == _v1,
          "...stays wheel-silent under the scroll law (the gate swap "
          "obeys SCROLL_SLIDERS too, the timers-tab lesson)")
    _retire(_hw)
except Exception as _exc:
    if isinstance(_exc, AssertionError):
        raise
    if type(_exc).__name__ not in ("TclError", "ImportError"):
        raise
    print("window section skipped: %s (no display?)" % type(_exc).__name__)

print("assign-test: %d failure(s)" % len(fails))
sys.exit(1 if fails else 0)
