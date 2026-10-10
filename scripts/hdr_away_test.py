"""hdr away-off helpers, offline: fake wm decides what gets switched
and what the handback list may contain. Run from repo root:
python scripts/hdr_away_test.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from awaywatch import profiles  # noqa: E402


class FakeWm:
    def __init__(self, rows, refuses=()):
        self.rows = rows
        self.refuses = set(refuses)
        self.sets = []

    def hdr_states(self):
        return [dict(r) for r in self.rows]

    def hdr_set(self, gdi, on):
        self.sets.append((gdi, on))
        return "refused" if gdi in self.refuses else ""


def main():
    lit = [{"gdi": "D1", "supported": True, "state": "on",
            "precise": True},
           {"gdi": "D2", "supported": True, "state": "off",
            "precise": True},
           {"gdi": "D3", "supported": True, "state": "unknown",
            "precise": False},          # pre-24H2: the state is a lie
           {"gdi": "D4", "supported": False, "state": "on",
            "precise": True}]           # cannot be lit, but pretend

    profiles.wm = FakeWm(lit)
    snap = profiles.hdr_away_off()
    assert snap == ["D1"], snap
    assert profiles.wm.sets == [("D1", False)]
    print("ok - only a precise, supported, on display is switched")

    profiles.hdr_away_restore(snap)
    assert profiles.wm.sets[-1] == ("D1", True)
    print("ok - the handback asks for exactly what left")

    profiles.wm = FakeWm(lit, refuses={"D1"})
    assert profiles.hdr_away_off() == []
    print("ok - a refusal snapshots nothing (nothing to hand back)")

    profiles.wm = FakeWm([])
    assert profiles.hdr_away_off() == []
    print("ok - a desk with nothing lit does nothing")

    profiles.wm = None               # any blowup: fail-open
    try:
        assert profiles.hdr_away_off() == []
        profiles.hdr_away_restore(["D1"])
    except Exception as exc:          # noqa: BLE001 - the point is
        raise SystemExit("fail-open broken: %s" % exc)
    print("ok - fail-open when wm itself is broken")

    print("HDR AWAY TESTS OK")


if __name__ == "__main__":
    main()
