"""The setup screen's behavior contract (redesign stage 3): the
retire law on the pane that replaced the wizard, the source ban over
the whole UI package, and - where a display exists - a real
SetupWindow on faked doors: cards spawn per settle, the veil counts
truthfully to done, OK posts the identity verbs, the duty-roster
write (amendment 6's add boxes: seeded from the roster, grayed at
the four-feed ceiling, re-lit on uncheck) and the consent enable,
and the close retires by schedule. The pure data contract (rows_from
/ card_spec / ok_verbs / add_ceilings) is truth-tabled in camdiag_test
section 9; this file owns the window's behavior."""
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
        self.app = type("A", (), {})()
        self.app.cfg = {"camera": {"enabled": enabled}}
        self.app._scan_cameras = lambda *a, **k: setattr(
            self, "scans", self.scans + 1)

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
s.scheduled[0][1]()
check(s.destroyed == 1, "the scheduled destroy lands")
s._close()
check(s.destroyed == 1, "retire ONCE (the X + OK burst cannot double)")
ok = Spy(enabled=True)
ok._close(refresh=True)
check(ok.scans == 1, "OK refreshes the picker (captions follow the setup)")
en = Spy(enabled=True)
en._close()
check(en.scans == 1, "an X on an enabled desk still refreshes captions")

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
            self._scan_cameras = lambda *a, **k: self.scans.append(1)

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
    for _ in range(5):                         # the host loop runs
        _h.update()                            # the scheduled destroy
    check(not _w.winfo_exists(),
          "the scheduled destroy lands (no leak, no zombie toplevel)")
    _h.destroy()
    cam_mod.camera_devices = _real_cd
    cam_mod.enumerate_cameras = _real_ec
    cam_mod.Camera = _real_cam
    cam_mod.hello_ir_names = _real_irn
    cam_mod.HelloIrCamera = _real_ir
except Exception as _exc:
    if isinstance(_exc, AssertionError):
        raise
    if type(_exc).__name__ not in ("TclError", "ImportError"):
        raise
    print("window section skipped: %s (no display?)" % type(_exc).__name__)

print("assign-test: %d failure(s)" % len(fails))
sys.exit(1 if fails else 0)
