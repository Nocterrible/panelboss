# One-shot patch: the descriptor seam (law 7, Oct 22) - one helper,
# every monitor-identity row, suppression by variance.
import io

def rd(p):
    return io.open(p, encoding="utf-8").read()

def wr(p, s):
    io.open(p, "w", encoding="utf-8", newline="").write(s)

def rep(src, old, new, n=1, tag=""):
    assert src.count(old) == n, (tag, src.count(old), old[:60])
    return src.replace(old, new)


# ---------- 1. _widgets.py: the seam, right below desk_position
p = "panelboss/ui/window/_widgets.py"
s = rd(p)
s = rep(s, '''class _WidgetsMixin:''',
    '''def monitor_row_label(listed, m):
    """A monitor's identity AS UI text - THE seam (owner law, Oct 22):
    short name, the gdi slot tail for duplicate models, and the edge
    descriptor from desk_position over the CARD'S OWN listed set.
    Every row that renders a monitor identity builds its label here,
    so the suppression law moves once: uniform components vanish, a
    single-row context says nothing, and an unlisted desk (before the
    first capture answered) simply has no rows to label."""
    base = [mm.get("short") or mm.get("id") for mm in listed]
    label = m.get("short") or m.get("id")
    if base.count(label) > 1:
        label = "%s (%s)" % (label, str(m.get("gdi") or "").rsplit(
            "DISPLAY", 1)[-1] or "?")
    return label + desk_position(
        [(mm.get("x", 0), mm.get("y", 0), mm.get("w", 0), mm.get("h", 0))
         for mm in listed],
        m.get("x", 0), m.get("y", 0), m.get("w", 0), m.get("h", 0))


class _WidgetsMixin:''', tag="widgets")
wr(p, s)

# ---------- 2. _away.py: route the away rows through the seam
p = "panelboss/ui/window/_away.py"
s = rd(p)
s = rep(s, "from ._widgets import desk_position, set_text",
        "from ._widgets import monitor_row_label, set_text", tag="away-imp")
s = rep(s, '''        _live = wm.monitors()
        base = [m.get("short") or m.get("id") for m in _live]
        dupes = {b for b in base if base.count(b) > 1}
        for m, short in zip(_live, base):
            label = short
            if short in dupes:
                label = "%s (%s)" % (
                    short, str(m.get("gdi") or "").rsplit("DISPLAY", 1)
                    [-1] or "?")
            label = label + desk_position(
                [(mm.get("x", 0), mm.get("y", 0), mm.get("w", 0),
                  mm.get("h", 0)) for mm in _live],
                m.get("x", 0), m.get("y", 0), m.get("w", 0),
                m.get("h", 0))''',
    '''        _live = wm.monitors()
        # the label (short name, duplicate-model tail, and the edge
        # descriptor WHEN IT CARRIES NEWS - law 7, Oct 22) is built at
        # the one seam every identity row shares
        for m, short in zip(_live, [mm.get("short") or mm.get("id")
                                    for mm in _live]):
            label = monitor_row_label(_live, m)''', tag="away-loop")
wr(p, s)

# ---------- 3. _oled.py: hider, jog, dim, theater rows - four fillers
p = "panelboss/ui/window/_oled.py"
s = rd(p)
s = rep(s, "from ._widgets import desk_position, set_text",
        "from ._widgets import monitor_row_label, set_text", tag="oled-imp")
s = rep(s, '''        for m, short in zip(_live, base):
            label = short
            if short in dupes:
                label = "%s (%s)" % (
                    short, str(m.get("gdi") or "").rsplit("DISPLAY", 1)
                    [-1] or "?")
            label = label + desk_position(
                [(mm.get("x", 0), mm.get("y", 0), mm.get("w", 0),
                  mm.get("h", 0)) for mm in _live],
                m.get("x", 0), m.get("y", 0), m.get("w", 0), m.get("h", 0))
            row = self._row(self._oled_row_frame, label, TIP["row"],''',
    '''        for m, short in zip(_live, base):
            label = monitor_row_label(_live, m)
            row = self._row(self._oled_row_frame, label, TIP["row"],''',
    tag="oled-hider")
s = rep(s, '''        for m, short in zip(wm.monitors(), base):
            label = short
            if short in dupes:
                label = "%s (%s)" % (
                    short, str(m.get("gdi") or "").rsplit("DISPLAY", 1)
                    [-1] or "?")
            row = self._row(self._jog_row_frame, label, TIP_JO["row"],''',
    '''        for m, short in zip(_live, base):
            label = monitor_row_label(_live, m)
            row = self._row(self._jog_row_frame, label, TIP_JO["row"],''',
    tag="oled-jog")
s = rep(s, '''        base = [m.get("short") or m.get("id") for m in wm.monitors()]
        dupes = {b for b in base if base.count(b) > 1}
        for m, short in zip(wm.monitors(), base):''',
    '''        _live = wm.monitors()
        base = [m.get("short") or m.get("id") for m in _live]
        dupes = {b for b in base if base.count(b) > 1}
        for m, short in zip(_live, base):''', tag="oled-dim-live")
s = rep(s, '''        for m, short in zip(_live, base):
            label = short
            if short in dupes:
                label = "%s (%s)" % (
                    short, str(m.get("gdi") or "").rsplit("DISPLAY", 1)
                    [-1] or "?")
            row = self._row(self._dim_row_frame, label, TIP_DIM["row"],''',
    '''        for m, short in zip(_live, base):
            label = monitor_row_label(_live, m)
            row = self._row(self._dim_row_frame, label, TIP_DIM["row"],''',
    tag="oled-dim")
s = rep(s, '''        base_c = [m.get("short") or m.get("id") for m in wm.monitors()]
        dupes_c = {b for b in base_c if base_c.count(b) > 1}
        for m, short in zip(wm.monitors(), base_c):
            label = short
            if short in dupes_c:
                label = "%s (%s)" % (
                    short, str(m.get("gdi") or "").rsplit("DISPLAY", 1)
                    [-1] or "?")''',
    '''        _live_c = wm.monitors()
        base_c = [m.get("short") or m.get("id") for m in _live_c]
        for m, short in zip(_live_c, base_c):
            label = monitor_row_label(_live_c, m)''',
    tag="oled-theater")
wr(p, s)

# the jog filler's own base/dupes lines (its _live binding was absent -
# its replace above introduced _live; give it the one it needs)
p = "panelboss/ui/window/_oled.py"
s = rd(p)
s = rep(s, '''        jog_cfg = self.cfg.setdefault("jog", {})
        base = [m.get("short") or m.get("id") for m in wm.monitors()]
        dupes = {b for b in base if base.count(b) > 1}''',
    '''        jog_cfg = self.cfg.setdefault("jog", {})
        _live = wm.monitors()
        base = [m.get("short") or m.get("id") for m in _live]
        dupes = {b for b in base if base.count(b) > 1}''', tag="oled-jog-live")
wr(p, s)

# ---------- 4. _gaming.py: the two rate labels
p = "panelboss/ui/window/_gaming.py"
s = rd(p)
anchor = "from ._widgets import SkewCombo" if \
    "from ._widgets import SkewCombo" in s else None
if anchor:
    s = rep(s, anchor,
            "from ._widgets import SkewCombo, monitor_row_label",
            tag="gaming-imp")
else:
    lines = s.splitlines(True)
    for i, ln in enumerate(lines):
        if ln.startswith("from .."):
            lines.insert(i + 1, "from ._widgets import monitor_row_label\n")
            break
    s = "".join(lines)
s = rep(s, '''        caps = wm.hdr_caps()
        for m in wm.monitors():''',
    '''        caps = wm.hdr_caps()
        _live = wm.monitors()
        for m in _live:''', tag="gaming-loop")
s = rep(s, '                            "%s - game rate" % m["short"],',
        '                            "%s - game rate"\n'
        '                            % monitor_row_label(_live, m),',
        tag="gaming-game")
s = rep(s, '                            "%s - desktop rate" % m["short"],',
        '                            "%s - desktop rate"\n'
        '                            % monitor_row_label(_live, m),',
        tag="gaming-desk")
wr(p, s)

# ---------- 5. _profiles.py: the add menu + the captured-panel rows
p = "panelboss/ui/window/_profiles.py"
s = rd(p)
if "from ._widgets import" in s:
    s = rep(s, "from ._widgets import SkewCombo",
            "from ._widgets import SkewCombo, desk_position, \\\n    "
            "monitor_row_label", tag="prof-imp")
else:
    lines = s.splitlines(True)
    for i, ln in enumerate(lines):
        if ln.startswith("from .."):
            lines.insert(i + 1, "from ._widgets import desk_position, \\\n"
                                "    monitor_row_label\n")
            break
    s = "".join(lines)
s = rep(s, '''        base = [(m.get("short") or m.get("id")) for m in avail]
        dupes = {b for b in base if base.count(b) > 1}
        add_vals, self._mode_add_map = [], {}
        for m, b in zip(avail, base):
            label = b
            if b in dupes:
                # two panels of one model share a short: append the
                # gdi slot tail so the menu can tell them apart
                label = "%s (%s)" % (
                    b, str(m.get("gdi") or "").rsplit("DISPLAY", 1)
                    [-1] or "?")
            add_vals.append(label)
            self._mode_add_map[label] = m["id"]''',
    '''        add_vals, self._mode_add_map = [], {}
        for m in avail:
            # the seam's own tail law covers duplicate models (the
            # comment moved with it, Oct 22); the descriptor is
            # suppressed unless the listed set has variance to show
            label = monitor_row_label(avail, m)
            add_vals.append(label)
            self._mode_add_map[label] = m["id"]''', tag="prof-add")
s = rep(s, '''        for d in prof.get("displays") or []:
            self._mode_row(sec, d, live,
                           hdr.get(g_of.get(d.get("id"), ""), ""),
                           bool(cap.get(g_of.get(d.get("id"), ""))))''',
    '''        _drects = [(d.get("x", 0), d.get("y", 0), d.get("w", 0),
                    d.get("h", 0)) for d in (prof.get("displays") or [])]
        for d in prof.get("displays") or []:
            self._mode_row(sec, d, live,
                           hdr.get(g_of.get(d.get("id"), ""), ""),
                           bool(cap.get(g_of.get(d.get("id"), ""))),
                           pos=desk_position(
                               _drects, d.get("x", 0), d.get("y", 0),
                               d.get("w", 0), d.get("h", 0)))''',
    tag="prof-mode-row")
wr(p, s)

# ---------- 6. _prof_apply.py: the pos parameter on the display row
p = "panelboss/ui/window/_prof_apply.py"
s = rd(p)
s = rep(s, '    def _mode_row(self, parent, d, live, hdr_note="", '
           'hdr_cap=False):',
    '    def _mode_row(self, parent, d, live, hdr_note="", hdr_cap=False,\n'
    '                 pos=""):', tag="apply-sig")
s = rep(s, '''            text="%s%s%s" % (d.get("short") or mon_id,
                             " (primary)" if d.get("primary") else "",
                             "   " + hdr_note if hdr_note else ""),''',
    '''            text="%s%s%s%s" % (d.get("short") or mon_id, pos,
                             " (primary)" if d.get("primary") else "",
                             "   " + hdr_note if hdr_note else ""),''',
    tag="apply-text")
wr(p, s)

# ---------- 7. run_all.ps1: register the new suite
p = "scripts/run_all.ps1"
s = rd(p)
s = rep(s, "'camid_test.py', 'assign_test.py', 'camdiag_test.py',",
        "'camid_test.py', 'assign_test.py', 'camdiag_test.py',\n    "
        "'descriptor_test.py',", tag="runall")
wr(p, s)
print("law-7 patch applied")
