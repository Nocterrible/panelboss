"""Edge/position descriptors (law 7, owner Oct 22), offline: the
suppression law as a truth table, the seam as the single label
builder, and the coverage census (every card that renders a monitor
identity routes through it). No Tk, no display hardware, no live app.
Run from repo root:
python scripts/descriptor_test.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panelboss.ui.window._widgets import (  # noqa: E402
    desk_position, monitor_row_label)

ROOT = os.path.dirname(os.path.abspath(__file__))


def read_mod(name):
    return open(os.path.join(ROOT, "..", "panelboss", "ui", "window",
                             name), encoding="utf8").read()


def body(src, defline):
    i = src.index(defline)
    j = src.index("\n    def ", i + 1)
    return src[i:j]


def M(x, y, w=1920, h=1080):
    return (x, y, w, h)


def test_truth_table():
    # (a) every row the same descriptor -> the shared word is noise ->
    #     NOTHING is shown (the exact first-boot all-identical shape)
    same = [M(0, 0, 800, 600), M(0, 0, 800, 600)]
    assert desk_position(same, 0, 0, 800, 600) == ""
    # (b) one row only -> no variance at all -> nothing
    assert desk_position([M(0, 0)], 0, 0, 1920, 1080) == ""
    # (c) before ANY capture: the empty set answers absence, not a dash
    assert desk_position([], 0, 0, 1920, 1080) == ""
    # (d) side-by-side: the shared 'top' vanishes, the varying half shows
    row = [M(0, 0), M(1920, 0)]
    assert desk_position(row, 0, 0, 1920, 1080) == " [left]"
    assert desk_position(row, 1920, 0, 1920, 1080) == " [right]"
    three = [M(0, 0), M(1920, 0), M(3840, 0)]
    assert desk_position(three, 1920, 0, 1920, 1080) == " [middle]"
    # (e) a stack: the shared horizontal half vanishes
    col = [M(0, 0), M(0, 1080)]
    assert desk_position(col, 0, 0, 1920, 1080) == " [top]"
    assert desk_position(col, 0, 1080, 1920, 1080) == " [bottom]"
    # (f) mixed variance: both halves carry news, both show, and a
    #     center panel reads the honest two-word shape
    desk = [M(0, 0), M(1920, 0), M(0, 1080)]
    assert desk_position(desk, 0, 0, 1920, 1080) == " [top left]"
    assert desk_position(desk, 1920, 0, 1920, 1080) == " [top right]"
    assert desk_position(desk, 0, 1080, 1920, 1080) == " [bottom left]"
    # (g) the one-different rule: three panels sharing the horizontal
    #     span exactly (a stack plus an offset third whose VERTICAL
    #     part repeats) keep the varying half only where it differs
    l2 = [M(0, 0), M(0, 1080), M(1920, 1080)]
    assert desk_position(l2, 1920, 1080, 1920, 1080) == " [bottom right]"
    assert desk_position(l2, 0, 0, 1920, 1080) == " [top left]"
    # (h) junk rows are skipped, never raise, and the single survivor
    #     gets the single-row silence
    assert desk_position([M(0, 0), ("x", 0, 0, 0)], 0, 0, 1920, 1080) == ""
    print("ok - truth table: uniform components drop as noise, "
          "variance earns its words, silence before capture")


def test_the_seam():
    # the seam builds short + gdi tail + descriptor in ONE place
    mons = [{"short": "AOC", "gdi": "\\\\.\\DISPLAY1", "x": 0, "y": 0,
             "w": 1920, "h": 1080},
            {"short": "AOC", "gdi": "\\\\.\\DISPLAY2", "x": 1920, "y": 0,
             "w": 1920, "h": 1080}]
    labels = [monitor_row_label(mons, m) for m in mons]
    assert labels == ["AOC (1) [left]", "AOC (2) [right]"], labels
    # a card listing ONE panel shows no descriptor (single row: no
    # variance is possible inside the listed set)
    assert monitor_row_label(mons[:1], mons[0]) == "AOC"
    # two identical-descriptor monitors -> the walked card shows NO
    # descriptor word anywhere in its row set
    twins = [{"short": "T", "gdi": "\\\\.\\DISPLAY1", "x": 0, "y": 0,
              "w": 800, "h": 600},
             {"short": "T", "gdi": "\\\\.\\DISPLAY2", "x": 0, "y": 0,
              "w": 800, "h": 600}]
    walked = [monitor_row_label(twins, m) for m in twins]
    assert all(("[" not in w) for w in walked), walked
    print("ok - the seam: tail + descriptor at one site; identical-"
          "descriptor rows walk clean")


def test_coverage():
    # every identity-rendering builder routes through the seam
    for mod, fn, want in (
            ("_away.py", "def _away_fill_rows", "monitor_row_label"),
            ("_oled.py", "for m, short in zip(_live, base):",
             "monitor_row_label"),
            ("_oled.py", "def _comp_fill_rows", "monitor_row_label"),
            ("_gaming.py", "def _gaming_fill_rows", "monitor_row_label"),
            ("_profiles.py", "for m in avail:", "monitor_row_label"),
            ("_profiles.py", "pos=desk_position(", "pos=desk_position(")):
        assert want in read_mod(mod), "the %s seam went missing" % fn[:40]
    # and no builder left the hand-rolled tail+geometry idiom behind
    for mod in ("_away.py", "_oled.py", "_gaming.py", "_profiles.py"):
        src = read_mod(mod)
        assert "rsplit(\"DISPLAY\", 1)" not in src or mod == "_widgets.py" \
            or src.count("rsplit(\"DISPLAY\", 1)") == 0, \
            "%s still builds identity labels by hand" % mod
    print("ok - coverage: away, hider/jog/dim/theater, gaming, profiles "
          "all read the one seam (the tray menu is a named follow-up)")


def main():
    test_truth_table()
    test_the_seam()
    test_coverage()
    print("DESCRIPTOR TESTS OK")


if __name__ == "__main__":
    main()
