"""The veil budget belongs to the owner, not the process (Oct 12,
owner: "first open is not hiding my monitor switching any more"): the
day's kill-and-relaunch rituals booted instances that mapped the
window UNASKED at startup, and yesterday's one-map-ever rule let that
unasked map spend the single ceremony the first REAL open was owed.
The veil now rides every map up to the first MANUAL open - an unasked
boot map may veil (the sweep is worth hiding from any glance), but
only a tray-open consumes the budget. Asserts both halves and that
later opens stay pixel-instant (the DWM-surface reopen, owner-chosen).
The window runs against a fake monitor; cameras are stubbed out. The
switch half of this file was re-cut the same day to layer-raise law
(owner: "tabbing just reveals them"): pages ride the body as mapped
layers and the checks assert the stack, not a cover. The Oct-29 tail
adds the doorway's BOOT LAW (the boot-resurrection cure): the row that
predates this boot reads dead, with one confession per minute."""
import logging
import os
import queue
import sys
import tempfile
import time
import tkinter as tk

os.environ.setdefault("PANELBOSS_CONFIG_DIR", os.path.join(
    os.environ.get("TEMP", "/tmp"), "panelboss-veil-test"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panelboss import config                        # noqa: E402
from panelboss import videoeye                      # noqa: E402
from panelboss.ui.window import _shell              # noqa: E402
from panelboss.ui.window import _runtime            # noqa: E402
from panelboss.ui.window import _scroll             # noqa: E402
from panelboss.ui.window._constants import TABS     # noqa: E402

fails = []


def check(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


class NoBlockQueue(queue.Queue):
    # _tick_inner does a bare framebox.get(): the real monitor keeps
    # one always fed, so the blocking read is sound in production.
    # The fake must answer None instead of lying about the cadence.
    def get(self, *a, **k):
        try:
            return queue.Queue.get(self, block=False)   # not
        except queue.Empty:                             # get_nowait:
            return None                                 # that re-enters


class FakeMonitor:
    def __init__(self):
        self.framebox = NoBlockQueue()    # stays empty: no mosaic draw
        self.events = NoBlockQueue()
        self.state = "away"
        self.paused = False
        self.mode = "poll"


class ProbeWindow(_shell.SettingsWindow):
    # the veil story needs no cameras; the boot scan would open real
    # doors (and fight a running app for them) for seconds on end.
    # The signature tracks the ui-1c force kwarg: the rescan button
    # posts force=True, and a stub that cannot take it would lie
    # about the pane's one click that matters here.
    def _scan_cameras(self, force=False):
        pass


cfg = config.get_config()
events = queue.Queue()
app = ProbeWindow(cfg, FakeMonitor(), events)

# an UNASKED map (the boot flavor) veils but does not consume.
# drain init's own veil+lift FIRST (under gauntlet load the 300 ms
# lift can mature between construction and the first explicit map -
# a stale timer firing inside _veil's forced paint ate the check
# once, mid-suite, observed 15:2x ALL GREEN:False)
time.sleep(0.45)
app.update()
if app.state() != "withdrawn":
    app._hide()
    time.sleep(0.2)
app._show_first()                             # manual=False
check(app._veil_lbl is not None, "boot map veils (sweep stays hidden)")
time.sleep(0.4)
app.update()                                  # pump the 300 ms after()
check(app._veil_lbl is None, "boot veil lifts")
check(app._manual_open_done is False,
      "boot map does not spend the owner's ceremony")

# the first TRAY open (the one "open" event the tray ever sends)
events.put(("open", None))
app._drain_ui_events()
check(app._veil_lbl is not None, "first manual open veiled")
check(app._manual_open_done is True, "manual open consumes the budget")

# (Oct 12, owner: "items drawing above the veil") tk law, measured
# with a pixel probe this session: a child created AFTER the veil
# paints OVER it (fresh children stack top). The probe also settled
# the query direction: winfo_children lists BOTTOM-FIRST - before
# any raise the veil is listed first while painting UNDER; after
# tkraise it is listed first painting OVER. So HIGH index = top of
# the pile. The boot sweep is exactly when late widgets are born;
# the veil must re-take the top, and both law and repair assert here.
late = tk.Label(app, text="lateborn")
late.pack()
kids = app.winfo_children()
check(kids.index(late) > kids.index(app._veil_lbl),
      "late-born child stacks over the veil (measured tk law)")
app._tick_inner()
kids = app.winfo_children()
check(kids.index(app._veil_lbl) > kids.index(late),
      "one tick re-buries the late-born under the veil")
late.destroy()

time.sleep(0.4)
app.update()

# The reopen law, corrected by the owner's own UAT (Oct 15).
# MEASURED AT THIS PIN, not assumed: withdraw is a real destroy
# (state() answers "withdrawn"), yet Tk REUSES the HWND number on the
# next map - winfo_id() is stable across the cycle, so the handle
# tells you nothing about whether the surface survived. What the
# owner's eye settled is the question the handle cannot answer: after
# a close, the next open draws the full UI with no cover. The window
# is reborn with a fresh composite regardless of which handle number
# it lands on, so a reopen after a close rides the cover exactly like
# the birth map. The pixel-instant ideal survives ONLY on the
# already-mapped raise path, asserted below.
app._hide()
time.sleep(0.2)
events.put(("open", None))
app._drain_ui_events()
check(app._veil_lbl is not None,
      "a reopen after a close takes the cover (the owner's UAT: the "
      "reopen drew the whole UI; withdraw is a real destroy, and the "
      "reused HWND number hides it)")
check(app.state() == "normal", "and the window is up")
time.sleep(0.4)
app.update()                             # pump the 300 ms lift
check(app._veil_lbl is None, "the reopen veil lifts on its own budget")

# the other half of the same law, and the ONLY pixel-instant path
# left: an open while the window is already mapped takes no cover and
# no resync (the raise is a raise).
events.put(("open", None))
app._drain_ui_events()
check(app._veil_lbl is None,
      "an already-mapped raise stays pixel-instant (no cover, and the "
      "knob resync that used to redraw the button family is skipped)")
check(app.state() == "normal", "and the window is still up")

# (Oct 12 re-cut, owner: "tabbing just reveals them") the switch half
# moved to layer law: no cover is BORN for a switch any more, and the
# contract is the STACK - the switched-to page sits TOP of the body's
# children (bottom-first list, law measured above), still mapped,
# while the page it replaced rides back under.
first, away = list(TABS)[1], list(TABS)[0]
body = app._body
app._show_tab(first)
app.update()
kids = body.winfo_children()
check(app._veil_lbl is None, "a switch takes no cover any more")
check(app.pages[first].winfo_ismapped()
      and kids.index(app.pages[first]) == len(kids) - 1,
      "switch raises the layer to the top of the body (enter)")
check(app.pages[first].winfo_width() == body.winfo_width()
      and app.pages[first].winfo_height() == body.winfo_height(),
      "the placed layer covers the body whole (the hidden pages stay HIDDEN)")
app._show_tab(away)                     # away
app.update()
app._show_tab(first)                    # and BACK: the second entry
kids = body.winfo_children()
check(app._veil_lbl is None
      and app.pages[first].winfo_ismapped()
      and kids.index(app.pages[first]) == len(kids) - 1
      and kids.index(app.pages[away]) < kids.index(app.pages[first]),
      "switch raises the layer to the top of the body (re-enter)")
app.update()

# (Oct 12, owner: "large blank space at the top of the pages") the
# stranded-view law: a region that SHRINKS under an already-scrolled
# view leaves tk parked inside content that no longer exists - blank
# on top. The host must clamp; re-pack used to hide this, the layer
# law made it permanent, so the law is asserted here forever.
p = app.pages["general/keybinds"]    # the SHORT page (the keybinds
                                       # card grew it - the clamp law
                                       # below stands regardless)
c = p._canvas
_calls = {"sync": 0}
_orig_sync = type(p).sync_region
def _spy(self, *a, **k):
    _calls["sync"] += 1
    return _orig_sync(self, *a, **k)
type(p).sync_region = _spy
big = tk.Frame(p.inner, height=3000)
big.pack(fill="x")
app.update()
c.yview_moveto(0.5)
check(c.yview()[0] > 0.0, "the scrolled page really scrolls (setup)")
big.destroy()
settle = time.time() + 0.6           # let the region burst finish
while time.time() < settle:
    app.update()                     # (the re-measure rides the loop
    time.sleep(0.01)                 # turns, as in production)
regs = str(c.cget("scrollregion")).split()
check(len(regs) == 4 and int(regs[3]) <= c.winfo_height()
      and c.yview()[0] == 0.0,
      "a shrunken region clamps the stranded view back to the top"
      + ("" if c.yview()[0] == 0.0 else
         " [dbg region=%s yview=%s syncs=%s]"
         % (c.cget("scrollregion"), c.yview(), _calls["sync"])))
type(p).sync_region = _orig_sync

# (Oct 12, owner: short pages "ghost their card bottoms as if they
# expected to draw a scroll then rubber band") the fitted-page law,
# other half: a page whose region fits its viewport must not take
# the wheel. yview() is no witness here -- a fitted canvas reports
# (0,1) while yview_scroll STILL moves the rendered view (measured:
# canvasy(0) walks -95px per wheel-up, the clamp's own
# yview_moveto(0) snaps it back from the <Configure> the move
# generates; the flashed frame at the offset is the ghost). The
# honest witness is canvasy(0) sampled BEFORE any pump, so the law
# is asserted in canvasy terms - deterministic, in-process, no
# pixels, no timing.
app.geometry("920x1080")                 # the live-app size, whatever
app._size_pair = (920, 1080)             # was recalled (no resize-recall)
app.update()
app._show_tab("general/keybinds")        # raise the fitted page: the
app.update(); time.sleep(0.15)           # wheel must land on ITS layer
app.update()
gs = app.pages["general/keybinds"]       # the fitted page
gcv = gs._canvas
_off = gcv.canvasy(0)
_pt = (gcv.winfo_rootx() + gcv.winfo_width() // 2,
       gcv.winfo_rooty() + 60)
# the event is generated ON THE CANVAS, not via winfo_containing:
# the first cut of this check asked the display stack who owns the
# pixel and once in the gauntlet got None (a sibling test window sat
# on the point - the answer is window-manager state, not our law).
# event_generate on the canvas runs the same bind chain the pointer
# would (_wheel dispatches off event.widget's master walk), so the
# law is tested without the test inheriting the desktop's mood.
_und = gcv
_und.event_generate("<MouseWheel>", x=10, y=10, delta=120)
check(gcv.canvasy(0) == _off,
      "a fitted page does not flash a scroll (canvasy(0) unmoved"
      " straight after the wheel event, before the clamp could)"
      + ("" if gcv.canvasy(0) == _off else
         " [dbg cy0 %s -> %s]" % (_off, gcv.canvasy(0))))
app.update()
check(_scroll._scroll_up(_und, -1) is False,
      "the fitted host refuses the wheel outright (innermost-first"
      " step-aside law; yview_scroll must never be reached)")
check(gcv.canvasy(0) == _off, "and the refusal leaves the view parked")

# (Oct 13, owner amendment 4: "the veil must last exactly as long as
# the work does - a heartbeat, not a stopwatch") the diagnostic veil
# lease law, on the real window with a FAKE clock (no sleeps, no
# stopwatch race): a re-dress renews the lease WITHOUT birthing a
# second veil; the watchdog lifts only on silence past the hold; and
# the post that lands after a lift RE-RAISES the veil fresh (the
# drain's cameras_veil arm takes _veil's fresh branch by itself -
# this asserts the trace, not just the reading of it).
class FakeTime:
    def __init__(self):
        self.t = 1000.0

    def time(self):                       # the veil's code reads the
        self.t += 0.001                   # clock only through these
        return self.t                     # two: the lease stamp and

    def monotonic(self):                  # the watchdog's now
        return self.t


ft = FakeTime()
_real_times = (_shell.time, _runtime.time)
_shell.time = _runtime.time = ft
try:
    events.put(("cameras_veil", "testing cameras, please wait"))
    app._drain_ui_events()
    check(app._veil_lbl is not None and app._veil_hold == 35.0,
          "the diag veil raises armed with the 35 s DEAD-MAN hold")
    v1, since1 = app._veil_lbl, app._veil_since
    ft.t += 10.0
    events.put(("cameras_veil", "testing cameras, please wait (probing 1)"))
    app._drain_ui_events()
    check(app._veil_lbl is v1, "a beat re-dresses the ONE veil (no stack)")
    check(app._veil_since > since1, "the beat renews the lease")
    ft.t += 25.0                          # 25 s since the last beat:
    app._tick_inner()                     # inside one wedged open's
    check(app._veil_lbl is v1,            # honest silence: it lives
          "silence UNDER the dead-man keeps the veil up")
    ft.t += 11.0                          # 36 s: past the engine's
    app._tick_inner()                     # own wedged-open deadline
    check(app._veil_lbl is None,          # + margin - dead, confessed
          "silence PAST the hold lifts (a dead sweep cannot veil)")
    events.put(("cameras_veil", "testing cameras, please wait (1 of 2 done)"))
    app._drain_ui_events()
    check(app._veil_lbl is not None and app._veil_lbl is not v1,
          "a beat after the lift RE-RAISES the veil fresh")
    # (re-issue) the lease must die WITH the veil: _unveil resets
    # _veil_hold to the stock 3 s, and the very next ordinary veil
    # proves it by lifting on its OWN budget (the reviewer's leak:
    # the sweep's tolerance must not become the window's)
    app._unveil()
    check(app._veil_hold == 3.0, "_unveil resets the heartbeat hold")
    app._veil("rebuild", absolute=True)
    ft.t += 4.0                          # 4 s of silence: past 3,
    app._tick_inner()                    # far inside the leaked 35
    check(app._veil_lbl is None,
          "the next ordinary veil lifts on the stock 3 s budget")
finally:
    app._unveil()
    _shell.time, _runtime.time = _real_times

# ------------------------------------------------------------- BOOT LAW
# (Oct 29, the boot-resurrection cure) the doorway's staleness law:
# a row at least as old as the machine's uptime predates THIS BOOT -
# the monotonic now resets at boot, so its computed age went negative,
# the old max(0.0, ...) clamp folded the lie to zero, and the corpse
# read YOUNG after every boot. The row reads dead instead, with ONE
# confession per minute. Every seam is a fake: the door is a temp
# file (the videoeye_test os.utime idiom), the clocks are the ARGS
# _read takes - no real seconds, no app file touched.
_DOOR_DIR = tempfile.mkdtemp(prefix="pb-veil-bootlaw-")
_DOOR = os.path.join(_DOOR_DIR, "rect")
_REAL_DOOR = videoeye.RECT_PATH
videoeye.RECT_PATH = _DOOR
_W = 946000000.0                      # the fake wall epoch the stamps
                                      # ride; age math is exact in
                                      # float64 (integers < 2**53)


def _door_with_age(age):
    with open(_DOOR, "w", encoding="utf-8") as f:
        f.write('{"rect": {"left": 0, "top": 0, "width": 8,'
                ' "height": 8}}\n')
    os.utime(_DOOR, (_W - age, _W - age))


_words = []


class _Confess(logging.Handler):
    def emit(self, record):
        _words.append(record.getMessage())


_cap = _Confess()
videoeye.log.addHandler(_cap)
_saved_level = videoeye.log.level
videoeye.log.setLevel(logging.INFO)
try:
    videoeye._last_expired_log = None

    # (a) the corpse: 1200 s of file age on a 600 s-old machine.
    _door_with_age(1200.0)
    check(videoeye._read(600.0, _W) is None,
          "a row older than the uptime predates this boot: None, "
          "never young (the Oct 29 boot-resurrection cure)")
    check(len(_words) == 1 and "veil expired" in _words[0]
          and "predates this boot" in _words[0],
          "the corpse gets exactly one confession (log.info, one line)")

    # (b) the post-boot row: 5 s of age, returned with honest age.
    _door_with_age(5.0)
    _row = videoeye._read(600.0, _W)
    check(_row is not None and abs(_row["ts"] - (600.0 - 5.0)) < 0.5,
          "a row written after this boot lives: ts = uptime - file age "
          "(the clamp that faked corpses young is gone)")

    # (c) the boundary: age == uptime is STILL dead (>= law).
    _door_with_age(600.0)
    check(videoeye._read(600.0, _W) is None,
          "a row exactly as old as the uptime predates this boot too "
          "(>= boundary: the boot law takes no favors)")

    # (d) the confession is a heartbeat, not a sermon: at most one
    # line per minute, the uptime the driver passes as the clock.
    _words.clear()
    videoeye._last_expired_log = None
    _door_with_age(1200.0)
    videoeye._read(600.0, _W)                   # the first word, at
    videoeye._read(659.0, _W)                   # 60 s of uptime...
    check(len(_words) == 1,
          "two reads inside a minute confess ONCE (no sermon)")
    videoeye._read(661.0, _W)                   # ...past 60 they owe
    check(len(_words) == 2,                     # a fresh minute
          "a minute later the corpse may speak again")
finally:
    videoeye.log.removeHandler(_cap)
    videoeye.log.setLevel(_saved_level)
    videoeye.RECT_PATH = _REAL_DOOR
    videoeye._last_expired_log = None

app.destroy()
print("veil-budget: %d failure(s)" % len(fails))
sys.exit(1 if fails else 0)
