"""taskbar core probes - READ-ONLY on the live desk.

The docs' rule: NEVER poke a real bar hwnd in a test (the user's taskbar
would flicker). These assert shape and return-type only, and the two
poke tests use a DEAD hwnd (0) so the Post just fails without touching a
real bar.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panelboss import taskbar
from panelboss import wm
from panelboss import config

# 1. bars() finds at least one Shell_TrayWnd on this live desk; every bar
#    either maps to a real monitor short or carries short == "".
barlist = taskbar.bars()
assert isinstance(barlist, list)
assert len(barlist) >= 1, "no Shell_TrayWnd found on the live desk"
shorts = {m["short"] for m in wm.monitors()}
for b in barlist:
    assert isinstance(b["hwnd"], int), b
    assert isinstance(b["short"], str), b
    assert b["short"] == "" or b["short"] in shorts, b
    assert isinstance(b["visible"], bool), b
    assert isinstance(b["rect"], tuple) and len(b["rect"]) == 4, b
    assert b["rect"][0] < b["rect"][2] and b["rect"][1] < b["rect"][3], b
print("ok - bars (live desk, read-only): %d bar(s) -> %s"
      % (len(barlist), [b["short"] or "?" for b in barlist]))

# 2. flag_note() is a non-empty str naming one of autohide/shown/unreadable
note = taskbar.flag_note()
assert isinstance(note, str) and note, note
assert ("autohide" in note) or ("shown" in note) or ("unreadable" in note), note
print("ok - flag_note: %s" % note)

# 3. cohabitants() returns a list (print its value); read-only psapi walk
co = taskbar.cohabitants()
assert isinstance(co, list), co
print("ok - cohabitants: %r" % (co,))

# 4. poke_show(0) / poke_hide(0) on a dead hwnd: the Post just fails -
#    bool returned, nothing raised, no real bar touched.
assert isinstance(taskbar.poke_show(0), bool)
assert isinstance(taskbar.poke_hide(0), bool)
print("ok - poke on dead hwnd (bool, no raise)")

# 5. unlock_focus() returns a bool, no raise - with a DEAD hwnd so the
# "read-only" suite never SetForegroundWindow's the real desktop out
# from under the user's active app.
assert isinstance(taskbar.unlock_focus(0x12345), bool)
print("ok - unlock_focus on a dead hwnd (bool, no focus stolen)")

# 6. cfg gate: DEFAULTS carries the taskbar section, off by default
assert config.DEFAULTS["taskbar"]["enabled"] is False
assert config.DEFAULTS["taskbar"]["retry_ms"] == 150
print("ok - cfg gate (DEFAULTS taskbar.enabled is False)")

print("TASKBAR TESTS OK")
