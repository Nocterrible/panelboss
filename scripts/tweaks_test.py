import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from awaywatch import tweaks

# 1. timer boost round-trip
assert tweaks.timer_boost(True) is True
assert tweaks.timer_boost(False) is True
print("ok - timer_boost")

# 2. FSO round-trip on a fake path
exe = r"Z:\tweaks_probe\fake_game.exe"
try:
    ok, err = tweaks.fso_set(exe, True)
    assert ok
    assert tweaks.fso_state(exe) is True
    assert tweaks.fso_state(r"Z:\tweaks_probe\never_set.exe") is False
    ok, err = tweaks.fso_set(exe, False)
    assert ok
    assert tweaks.fso_state(exe) is False
    print("ok - fso round-trip")
finally:
    tweaks.fso_set(exe, False)

# 3. fso_sync list-mirror
a = r"Z:\tweaks_probe\sync_a.exe"
try:
    rows = tweaks.fso_sync([a])
    assert ("disable-fso", a, True, "") in rows
    assert tweaks.fso_state(a) is True
    rows2 = tweaks.fso_sync([a])
    assert not any(r[1] == a and r[0] == "disable-fso" for r in rows2)
    rows3 = tweaks.fso_sync([])
    assert any(r[0] == "clear-fso-flag" and r[1] == a and r[2] for r in rows3)
    assert tweaks.fso_state(a) is False
    print("ok - fso_sync")
finally:
    tweaks.fso_set(a, False)
    tweaks.fso_set(exe, False)

# 4. read-only
for tid in tweaks.TOGGLES:
    assert isinstance(tweaks.is_on(tid), bool)
print("ok - is_on read-only")

# 5. policy
ok, msg = tweaks.apply_policy()
assert isinstance(ok, bool) and isinstance(msg, str)
print("ok - apply_policy (elevated)" if ok
      else "ok - apply_policy (not elevated)")

print("TWEAKS TESTS OK")
