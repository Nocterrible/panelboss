# One-shot patch: awaymode_test.py extensions for the Oct-22 laws.
# Triple-quoted blocks, real newlines (no escape fragility).
import io

P = "scripts/awaymode_test.py"
src = io.open(P, encoding="utf-8").read()


def rep(old, new, n=1):
    global src
    assert src.count(old) == n, (src.count(old), old[:70])
    src = src.replace(old, new)


# (1) default-flip pins: the shipped default word is now offdisc
rep('''        assert c["away"]["mode"] == "off" and c["away"]["monitors"] == {}''',
    '''        # the Oct-22 default flip: the unset-row default word is
        # "offdisc" (the card's selector is dead; the key lives as
        # the row-fallback word)
        assert c["away"]["mode"] == "offdisc" \\
            and c["away"]["monitors"] == {}''')
rep('''        c = config.get_config(dir=tmp3, verbose=False)   # parses at all?
        assert c["away"]["mode"] == "off"''',
    '''        c = config.get_config(dir=tmp3, verbose=False)   # parses at all?
        assert c["away"]["mode"] == "offdisc"''')

# (2) ledger-line prefix (the degraded-count words are pinned unchanged)
rep('''        line = [l for l in rec.lines if l.startswith("away: dim")]
        assert len(line) == 1 and "0 rows blackout-degraded" in line[0], \\''',
    '''        line = [l for l in rec.lines if l.startswith("away: dark")]
        assert len(line) == 1 and "0 rows blackout-degraded" in line[0], \\''')
rep('''        line = [l for l in rec.lines if l.startswith("away: dim")]
        assert len(line) == 1 and "3 VCP-off asked" in line[0] \\''',
    '''        line = [l for l in rec.lines if l.startswith("away: dark")]
        assert len(line) == 1 and "3 VCP-off asked" in line[0] \\''')
rep('''        line = [l for l in rec.lines if l.startswith("away: dim")]
        assert len(line) == 1 and "1 disconnected" in line[0], line''',
    '''        line = [l for l in rec.lines if l.startswith("away: dark")]
        assert len(line) == 1 and "1 disconnected" in line[0], line''')

# (3) the row-menu relabel: dim first, 'off (DDC fast)', blackout last;
#     and the preview label rides its constant (fake-15 swap proves it)
rep('''    from panelboss.ui.window._away import off_choice, DISC_TEXT
    from panelboss.wm import _bright as _b
    aoc = FakeBright({"D1": 75})                # answers 0x10: bus proven
    assert off_choice(aoc, "D1") == ["blackout", "dim", "off", DISC_TEXT]
    dead = FakeBright({}, no_door=["DX"])       # the gray class - D6 only
    assert off_choice(dead, "DX") == ["blackout", "dim", DISC_TEXT]
    assert DISC_TEXT == "off (disconnect)"     # the shipped label
    assert off_choice(_b, "NO-SUCH-DISPLAY99")[-1] == DISC_TEXT  # answers
    #                                          per door for D6, always
    #                                          offers the disconnect
    print("ok - off selectable everywhere the app reached; gray only "
          "for the never-reached; the disconnect is everywhere")''',
    '''    from panelboss.ui.window._away import (
        off_choice, DISC_TEXT, DDC_TEXT, MODE_BY_LABEL, preview_label)
    import panelboss.ui.window._away as _am
    from panelboss.wm import _bright as _b
    aoc = FakeBright({"D1": 75})                # answers 0x10: bus proven
    assert off_choice(aoc, "D1") == ["dim", DDC_TEXT, DISC_TEXT, "blackout"]
    dead = FakeBright({}, no_door=["DX"])       # the gray class - D6 only
    assert off_choice(dead, "DX") == ["dim", DISC_TEXT, "blackout"]
    assert DISC_TEXT == "off (disconnect)"     # the shipped label
    assert DDC_TEXT == "off (DDC fast)"        # the FILE word stays "off"
    assert set(MODE_BY_LABEL) == set(off_choice(aoc, "D1"))
    assert MODE_BY_LABEL[DDC_TEXT] == "off"    # byte-identical word
    assert DISC_TEXT in off_choice(_b, "NO-SUCH-DISPLAY99")  # answers
    #                                          per door for D6, always
    #                                          offers the disconnect
    # THE PREVIEW LABEL CARRIES ITS OWN DURATION (owner law, Oct 22):
    # derived from PREVIEW_SEC - the fake-constant swap proves the
    # seam (a literal "15s" beside a 10 s timer fails this pin).
    assert preview_label() == "preview (%ds)" % _am.PREVIEW_SEC
    _was, _am.PREVIEW_SEC = _am.PREVIEW_SEC, 15
    try:
        assert preview_label() == "preview (15s)"
    finally:
        _am.PREVIEW_SEC = _was
    assert "threading.Timer(PREVIEW_SEC" in open(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
            __file__))), "panelboss", "ui", "window",
        "_away.py"), encoding="utf8").read(), \\
        "the timer left the constant the label rides"
    print("ok - off selectable everywhere the app reached; gray only "
          "for the never-reached; the disconnect is everywhere; the "
          "preview label follows its constant")''')

# (4) the stock path is now the fallback chain
rep('''def test_stock_path():
    tmp = tempfile.mkdtemp(prefix="pb_away_o")
    m = make_monitor(tmp, {"mode": "off"})
    try:
        m._screens_off(1.0)
        calls = m._fake["calls"]
        assert ("turn_off",) in calls, "stock mode powers off"
        assert not m.away_status
        assert ("arm", True) not in calls
        m._away_lift()                        # no-op by law
        assert ("hide_all",) not in m._fake["overlay"].calls
        print("ok - stock mode is the old path, untouched")
    finally:
        m._ledger.undo()''',
    '''def test_legacy_global_off_fallback():
    """The owner ruling, Oct 22: the global key is a fallback WORD,
    not a switch - a legacy file saying mode="off" feeds the row word
    "off" (the VCP door, byte-identical behavior of that word) to
    every unset row. The SC_MONITORPOWER broadcast survives only for
    the empty desk (and the fossil there stays honored)."""
    tmp = tempfile.mkdtemp(prefix="pb_away_o")
    m = make_monitor(tmp, {"mode": "off"})
    try:
        m._screens_off(1.0)
        calls = m._fake["calls"]
        assert ("turn_off",) not in calls, \\
            "the away engine owns the dark on a desk with rows"
        for gdi in ("D1", "D2", "D3"):
            assert ("vcp", gdi, 0xD6, 4, _bright.VCP_TRIES) in calls, \\
                "the legacy word still means the VCP door, byte-for-byte"
        assert set(m.away_status.values()) == {"off (unverified)"}
        assert ("arm", True) in calls
        m._away_lift()
        print('ok - legacy global mode="off": the rows speak, the '
              "broadcast stands down")
        # the empty desk keeps the old path verbatim (fossil honored)
        m._ledger.keep(wm, "monitors", lambda: [])
        m._screens_off(9.0)
        assert ("turn_off",) in m._fake["calls"], \\
            "a desk with no rows still takes the stock broadcast"
        print("ok - the empty desk answers the broadcast")
    finally:
        m._ledger.undo()''')

# (5) hook-lifecycle first section: the away engine never stands down,
#     so the default desk wears ears - registered ONCE, churned never.
rep('''        assert m._away_engage() == {}         # stock mode, the default law
        assert d._pump_pause() == disp.IDLE_PAUSE_SEC, "deaf and noteless"
        d._service_ears()
        d._service_ears()
        assert fake.registers == [], fake.registers
        assert fake.hook_calls == [], "the LL chain is gone for good"
        print("ok - mode off NEVER registers the ears (no tax, ever)")''',
    '''        led.keep(wm, "_sdc", FakeSDC())       # the suite owns the CCD
        #                              door: the default desk retracts
        eng = m._away_engage()                # fresh default: unset rows
        assert eng and all(s.startswith("offdisc refused")  # fall to the
                           for s in eng.values()), eng      # disconnect,
        #                              refused here (no path answers) ->
        #                              confessed blackout; the ears ride
        #                              every spell from Oct 22
        assert d._pump_pause() == disp.ARMED_PAUSE_SEC
        d._service_ears()
        d._service_ears()
        assert fake.registers == [2], fake.registers
        assert fake.hook_calls == [], "the LL chain is gone for good"
        m._away_lift()
        d._service_ears()
        assert fake.unregisters == [2]
        fake.registers.clear()
        fake.unregisters.clear()      # section 2 pins the dim spell
        #                              with a fresh recorder
        print("ok - the away engine never stands down: ears ride the "
              "spell, registered once, and the LL trio stays dead")''')

# (6) the park test's stock comment follows the new law
rep('''        m3 = make_monitor(tmp, {"mode": "off"})      # the stock path:
        try:                                         # pointer rules
            m3._screens_off(1.0)                     # belong to engage
            assert not [c for c in m3._fake["calls"] if c[0] == "park"]
        finally:
            m3._ledger.undo()
        print("ok - park: once, at the lawful point, replacing the "
              "jail on painted modes; the stock path stays pointer-blind")''',
    '''        m3 = make_monitor(tmp, {"mode": "off"})      # the legacy word:
        try:                                         # sleep rows jail,
            m3._screens_off(1.0)                     # they never park
            assert not [c for c in m3._fake["calls"] if c[0] == "park"]
        finally:
            m3._ledger.undo()
        print("ok - park: once, at the lawful point, replacing the "
              "jail on painted modes; sleep rows keep the jail")''')

# (7) the new default-flip test with the three ordered pins
rep('''def main():
    test_migration()
    test_row_shorthands()
''',
    '''def test_default_flip():
    """THE DEFAULT FLIP, at all three tiers (owner, Oct 22): an unset
    row -> offdisc; the legacy 'off' word -> the VCP door byte-
    identical; the chain: row value beats the global key beats the
    default. The normalize line the whole ruling hangs on is pinned
    first, as data."""
    n = config.normalize_away
    assert n({})["mode"] == "offdisc" == config.AWAY_ROW_DEFAULT
    tmp = tempfile.mkdtemp(prefix="pb_away_dflt")
    sdc = FakeSDC(victim={"AAA": "T-A", "BBB": "T-B", "CCC": "T-C"},
                  active={"T-A", "T-B", "T-C"})
    m = make_monitor(tmp, {}, sdc=sdc)          # fresh config shape
    try:
        m._screens_off(1.0)
        assert m.away_status == {"AAA": "off (disconnected)",
                                 "BBB": "off (disconnected)",
                                 "CCC": "off (disconnected)"}, \\
            m.away_status
        assert sorted(sdc.retracts) == ["AAA", "BBB", "CCC"]
        assert not any(c[0] in ("set", "vcp") for c in m._fake["calls"]), \\
            "the default desk spends no brightness and no power code"
        m._away_lift()
        print("ok - unset rows answer the disconnect default (PROVEN "
              "word, adapter door)")
    finally:
        m._ledger.undo()
    # the chain's middle tier: a legacy global key feeds unset rows...
    m2 = make_monitor(tmp, {"mode": "off"})
    try:
        m2._screens_off(1.0)
        assert set(m2.away_status.values()) == {"off (unverified)"}, \\
            m2.away_status
        # ...and an explicit row word always outranks it
        m2.cfg["away"] = config.normalize_away(
            {"mode": "off", "monitors": {"BBB": {"mode": "blackout"}}})
        m2._away_lift()
        m2._screens_off(2.0)
        assert m2.away_status["BBB"] == "blackout", m2.away_status
        assert m2.away_status["AAA"] == "off (unverified)"
        m2._away_lift()
        print("ok - the fallback chain: row beats global key beats "
              "default")
    finally:
        m2._ledger.undo()
    # the card-side mirror: _away_row_mode answers the SAME chain
    from panelboss.ui.window._away import _AwayMixin, DDC_TEXT, DISC_TEXT
    stub = type("S", (), {"cfg": {"away": {"mode": "dim", "monitors": {
        "A": {"blackout": False, "off": True, "offdisc": False}}}}})()
    assert _AwayMixin._away_row_mode(stub, "A") == DDC_TEXT
    assert _AwayMixin._away_row_mode(stub, "Z") == "dim"   # global tier
    stub2 = type("S", (), {"cfg": {"away": {}}})()
    assert _AwayMixin._away_row_mode(stub2, "Z") == DISC_TEXT  # default
    print("ok - the card mirrors the chain; a row with no key paints "
          "the word the engine will act on")


def main():
    test_migration()
    test_row_shorthands()
    test_default_flip()
''')
rep('''    test_stock_path()
''', '''    test_legacy_global_off_fallback()
''')

# (8) the word-seam test's label set follows the relabelled menu
rep('''    assert MODE_BY_LABEL[DISC_TEXT] == "offdisc"
    assert set(MODE_BY_LABEL) == set(off_choice(FakeBright({"D1": 1}),''',
    '''    assert MODE_BY_LABEL[DISC_TEXT] == "offdisc"
    assert MODE_BY_LABEL["dim"] == "dim"
    assert set(MODE_BY_LABEL) == set(off_choice(FakeBright({"D1": 1}),''')

io.open(P, "w", encoding="utf-8", newline="").write(src)
print("awaymode_test patched OK")
