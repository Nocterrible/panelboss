"""mode-edit primitives offline suite: fake desk, temp profiles
dir, no screen ever blinks. Run from repo root:
python scripts/mode_edit_test.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
from panelboss import profiles, wm  # noqa: E402

LIVE = [{"id": "MONAAA", "short": "AAA", "gdi": r"\\.\DISPLAY1",
         "x": 0, "y": 0, "w": 100, "h": 100, "rate": 60,
         "bits": 8, "primary": True}]
OFFERED = {r"\\.\DISPLAY1": ["100x100@60", "200x200@120"]}


def run():
    td = tempfile.mkdtemp(prefix="modes")
    real = (wm.monitors, wm.offered_modes, wm.hdr_states)
    wm.monitors = lambda: [dict(m) for m in LIVE]
    wm.offered_modes = lambda gdi, limit=400: list(
        OFFERED.get(gdi, []))
    wm.hdr_states = lambda: []
    try:
        data = {"profiles": {}, "last": {}}

        ok, _ = profiles.blank(data, "p", dir=td)
        assert ok
        ok2, note = profiles.blank(data, "p", dir=td)
        assert not ok2 and "already" in note
        print("ok - blank profile, names are one-shot")

        ok, note = profiles.add_display(data, "p", "MONAAA", dir=td)
        assert ok, note
        row = data["profiles"]["p"]["displays"][0]
        assert row["w"] == 100 and row["rate"] == 60
        ok2, note = profiles.add_display(data, "p", "MONAAA", dir=td)
        assert not ok2 and "already" in note
        ok3, note = profiles.add_display(data, "p", "MONZZZ", dir=td)
        assert not ok3 and "live desk" in note
        print("ok - add_display seeds current mode, no dupes, "
              "offline ids refused")

        ok, note = profiles.set_display_mode(
            data, "p", "MONAAA", 200, 200, 120, dir=td)
        assert ok, note
        row = data["profiles"]["p"]["displays"][0]
        assert row["w"] == 200 and row["rate"] == 120
        back = profiles.load(dir=td)
        assert back["profiles"]["p"]["displays"][0]["w"] == 200
        print("ok - offered mode edits apply AND persist")

        ok, note = profiles.set_display_mode(
            data, "p", "MONAAA", 640, 480, 75, dir=td)
        assert not ok and "offered list" in note
        print("ok - unlisted mode refused by the driver's list")

        data["profiles"]["p"]["displays"].append(
            {"id": "MONOFF", "short": "OFF", "gdi": r"\\.\DISPLAY9",
             "x": 100, "y": 0, "w": 50, "h": 50, "rate": 60,
             "bits": 8, "primary": False})
        ok, note = profiles.set_display_mode(
            data, "p", "MONOFF", 80, 80, 144, dir=td)
        assert ok and "UNVERIFIED" in note
        print("ok - offline monitor saves with an honest warning")

        for bad in ((  "x", 200, 120), (200, 200, 0), (200, 200, -1)):
            ok, _ = profiles.set_display_mode(
                data, "p", "MONAAA", bad[0], bad[1], bad[2], dir=td)
            assert not ok
        print("ok - junk numbers never reach the row")

        ok, _ = profiles.drop_display(data, "p", "MONOFF", dir=td)
        assert ok
        ok2, note = profiles.drop_display(data, "p", "MONOFF", dir=td)
        assert not ok2
        print("ok - drop_display removes once, then says so")

        ok, note = profiles.set_display_mode(
            data, "ghost", "MONAAA", 200, 200, 120, dir=td)
        assert not ok and "ghost" in note
        print("ok - unknown profile named honestly")
        assert profiles.live_modes() == {"MONAAA": [
            "100x100@60", "200x200@120"]}
        print("ok - live_modes mirrors the offered lists per id")

        print("MODE EDIT TESTS OK")
    finally:
        wm.monitors, wm.offered_modes, wm.hdr_states = real


if __name__ == "__main__":
    run()
