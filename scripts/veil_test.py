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
layers and the checks assert the stack, not a cover."""
import os
import queue
import sys
import time
import tkinter as tk

os.environ.setdefault("PANELBOSS_STATE", os.path.join(
    os.environ.get("TEMP", "/tmp"), "panelboss-veil-test"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panelboss import config                        # noqa: E402
from panelboss.ui.window import _shell              # noqa: E402
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
    # doors (and fight a running app for them) for seconds on end
    def _scan_cameras(self):
        pass


cfg = config.get_config()
events = queue.Queue()
app = ProbeWindow(cfg, FakeMonitor(), events)

# an UNASKED map (the boot flavor) veils but does not consume
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

# every later open is the pixel-instant reopen the owner chose
app._hide()
time.sleep(0.2)
events.put(("open", None))
app._drain_ui_events()
check(app._veil_lbl is None, "later opens stay pixel-instant")
check(app.state() == "normal", "and the window is up")

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

app.destroy()
print("veil-budget: %d failure(s)" % len(fails))
sys.exit(1 if fails else 0)
