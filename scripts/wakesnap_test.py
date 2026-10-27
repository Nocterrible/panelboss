"""The wake-frames ring, offline: the text log is ALWAYS on (a
disabled switch still writes the who-woke-it row, just no picture),
the enabled ring appends and caps at five (newest first), the input
wake names itself, the jpeg decodes back, and the static bans that
keep a diagnostic a diagnostic (no disk verbs, no try-suppression at
the wake seam, the stock false in the camera defaults). No Tk, no
camera, no live app.
Run from repo root:
python scripts/wakesnap_test.py
"""
import os
import sys
import tempfile

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panelboss import config, wakesnap                         # noqa: E402


def frame(tone):
    """A synthetic BGR frame: numpy square, one flat tone per test."""
    return np.full((120, 120, 3), tone, np.uint8)


def reset():
    wakesnap._ring.clear()
    wakesnap._pending = None


def test_disabled_writes_the_text_row():
    reset()
    wakesnap.set_enabled(False)
    wakesnap.remember(frame(90), 0.83, "desk")
    wakesnap.wake(0.83)                                # camera-driven
    rows = wakesnap.frames()
    assert len(rows) == 1, rows
    assert rows[0]["jpg"] is None, \
        "disabled: the row stands, the picture does not"
    assert abs(rows[0]["score"] - 0.83) < 1e-9 and rows[0]["cam"] == "desk"
    print("ok - disabled: the wake still writes its text row (jpg None)")


def test_enabled_ring_and_cap():
    reset()
    wakesnap.set_enabled(True)
    wakesnap.remember(frame(70), 0.42, "desk")
    wakesnap.wake(0.42)
    rows = wakesnap.frames()
    assert len(rows) == 1 and rows[0]["jpg"], "enabled: the picture rides"
    for i in range(1, 6):                            # six wakes total
        wakesnap.remember(frame(70 + i), 0.1 * i, "cam%d" % i)
        wakesnap.wake(0.1 * i)
    rows = wakesnap.frames()
    assert len(rows) == 5, "the ring capped at five, got %d" % len(rows)
    assert [r["cam"] for r in rows] == ["cam5", "cam4", "cam3", "cam2",
                                        "cam1"], \
        "newest first, the oldest wake is gone: %r" % [r["cam"] for r in rows]
    assert all(r["jpg"] for r in rows), "enabled rows all carry pictures"
    print("ok - enabled: wake appends, six keep the newest five, newest first")


def test_input_wake_names_itself():
    reset()
    wakesnap.set_enabled(True)
    wakesnap.wake(None)                              # the typing branch
    rows = wakesnap.frames()
    assert len(rows) == 1 and rows[0]["cam"] == "input" \
        and rows[0]["score"] is None and rows[0]["jpg"] is None, rows
    # the away_lift / session_unlock shape (score 0.0): falsy too, and
    # a pending frame on hand must NOT make it a camera row
    wakesnap.remember(frame(80), 0.7, "desk")
    wakesnap.wake(0.0)
    rows = wakesnap.frames()
    assert len(rows) == 2 and rows[0]["cam"] == "input", \
        "the stale frame was dropped, the input row stands: %r" % rows
    # a truthy score with no pending (a wake from a frame this module
    # never saw) writes a bare camera row, not an input row
    reset()
    wakesnap.wake(0.6)
    assert wakesnap.frames()[0]["cam"] == "camera", wakesnap.frames()
    print("ok - input wakes (None and the 0.0 the event drains pass) say "
          "'input' and drop the stale frame; a score with no "
          "pending row says 'camera'")


def test_jpg_decodes_back():
    reset()
    wakesnap.set_enabled(True)
    wakesnap.remember(frame(123), 0.9, "desk")
    wakesnap.wake(0.9)
    jpg = wakesnap.frames()[0]["jpg"]
    back = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
    assert back is not None, "the ring's bytes must answer the viewer's decode"
    assert back.shape == (120, 120, 3), back.shape
    print("ok - the stored jpeg decodes back at full size")


def test_writer_carries_the_word():
    tmp = tempfile.mkdtemp(prefix="pb_wake_cfg")
    c = config.get_config(dir=tmp, verbose=False)
    assert c["camera"]["wake_snap"] is False, "the stock answer is no"
    c["camera"]["wake_snap"] = True
    path = config.write_config(c, os.path.join(tmp, "config.toml"))
    disk = open(path, encoding="utf8").read()
    assert "wake_snap = true" in disk, \
        "a true word must ride the writer: %r" % disk
    print("ok - [camera] wake_snap defaults false and a true lands in "
          "the written file")


def test_static_bans():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "panelboss", "wakesnap.py"),
               encoding="utf8").read()
    for banned in ("imwrite", "open(", "save", "tofile", ".dump"):
        assert banned not in src, \
            "wakesnap learned a disk verb (%s) - the promise is memory only" % banned
    power = open(os.path.join(root, "panelboss", "state", "_power.py"),
                 encoding="utf8").read()
    body = power.split("def _wake", 1)[1].split("\n    def ", 1)[0]
    assert "wakesnap.wake(score)" in body, "the wake seam lost its call"
    assert "try" not in body and "except" not in body, \
        "the wake seam grew a try-suppression: the ring either rides " \
        "or the wake confesses"
    cfg = open(os.path.join(root, "panelboss", "config.py"),
               encoding="utf8").read()
    cam = cfg.split('"camera": {', 1)[1].split('"inference"', 1)[0]
    assert '"wake_snap": False' in cam, \
        "the wake-frames switch left the camera defaults (or moved section)"
    print("ok - static bans: no disk verbs in the ring, no try at the "
          "wake seam, the stock false sits in [camera]")


def main():
    test_disabled_writes_the_text_row()
    test_enabled_ring_and_cap()
    test_input_wake_names_itself()
    test_jpg_decodes_back()
    test_writer_carries_the_word()
    test_static_bans()
    print("WAKESNAP TESTS OK")


if __name__ == "__main__":
    main()
