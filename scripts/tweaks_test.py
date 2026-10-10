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

# 6. THE CRITICAL THAT SLIPPED: a real apply/revert round-trip.
#    SetValueEx(key, name, reserved, type, data) is the ONLY shape
#    CPython accepts; the dead provider-era myth (3 args) made every
#    apply() raise TypeError, escaping into the UI. "history" is the
#    low-blast-radius toggle; original value restored in a finally.
tid = "history"
path, name = tweaks.TOGGLES[tid][1], tweaks.TOGGLES[tid][2]
orig = tweaks._get(path, name)
try:
    ok, err = tweaks.apply(tid)
    assert ok, "apply raised: %s" % err
    assert tweaks.is_on(tid) is True
    ok, err = tweaks.revert(tid)
    assert ok, err
    assert tweaks.is_on(tid) is False
finally:
    tweaks._put(path, name, orig)
print("ok - toggle apply/revert round-trip on the live registry")

# 7. token preservation (Law 6) + case-insensitive names. Our token
#    merges INTO a foreign value and strips OUT without deleting the
#    neighbour's flag; a path spelled with different case is ONE
#    registry entry, not two (Windows value names are case-insensitive).
vexe = r"Z:\tweaks_probe\vendor_game.exe"
try:
    tweaks._put_str(tweaks.LAYERS, vexe, "~ RIPVSNGLATE")   # foreign
    assert tweaks.fso_state(vexe) is False
    rows = tweaks.fso_sync([vexe])
    assert ("disable-fso", vexe, True, "") in rows, rows
    val = tweaks._get(tweaks.LAYERS, vexe)
    assert "RIPVSNGLATE" in val and \
        "DISABLEDXMAXIMIZEDWINDOWEDMODE" in val, val
    print("ok - fso token merges in beside a foreign flag")
    # a differently-spelled path is the SAME entry: no second write,
    # and it must not get its (now-present) flag stripped
    rows2 = tweaks.fso_sync([vexe.upper()])
    assert not any(r[1].upper() == vexe.upper()
                   and r[0] == "clear-fso-flag" for r in rows2), rows2
    assert tweaks.fso_state(vexe) is True
    print("ok - case-different path is one entry, not two")
    tweaks.fso_sync([])
    val2 = tweaks._get(tweaks.LAYERS, vexe)
    assert "DISABLEDXMAXIMIZEDWINDOWEDMODE" not in val2
    assert "RIPVSNGLATE" in val2, val2
    print("ok - our token strips out, the neighbour's flag stays")
finally:
    tweaks._put(tweaks.LAYERS, vexe, None)

print("TWEAKS TESTS OK")
