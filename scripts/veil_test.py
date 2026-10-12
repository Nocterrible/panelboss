"""The veil budget belongs to the owner, not the process (Oct 12,
owner: "first open is not hiding my monitor switching any more"): the
day's kill-and-relaunch rituals booted instances that mapped the
window UNASKED at startup, and yesterday's one-map-ever rule let that
unasked map spend the single ceremony the first REAL open was owed.
The veil now rides every map up to the first MANUAL open - an unasked
boot map may veil (the sweep is worth hiding from any glance), but
only a tray-open consumes the budget. Asserts both halves and that
later opens stay pixel-instant (the DWM-surface reopen, owner-chosen).
The window runs against a fake monitor; cameras are stubbed out."""
import os
import queue
import sys
import time

os.environ.setdefault("PANELBOSS_STATE", os.path.join(
    os.environ.get("TEMP", "/tmp"), "panelboss-veil-test"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panelboss import config                        # noqa: E402
from panelboss.ui.window import _shell              # noqa: E402

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
            return self.get_nowait()
        except queue.Empty:
            return None


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
time.sleep(0.4)
app.update()

# every later open is the pixel-instant reopen the owner chose
app._hide()
time.sleep(0.2)
events.put(("open", None))
app._drain_ui_events()
check(app._veil_lbl is None, "later opens stay pixel-instant")
check(app.state() == "normal", "and the window is up")

app.destroy()
print("veil-budget: %d failure(s)" % len(fails))
sys.exit(1 if fails else 0)
