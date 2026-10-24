"""videoeye: the dim-around-the-playing-video eye.

Geometry now comes from the companion EXTENSION through the local native
host: the extension measures the playing video in the page (the
ad-blocker class of call), the host writes the row to the app's OWN
doorway file (%APPDATA%\\PanelBoss\\rect, a fixed path - deterministic,
no browser download-dir guessing), and this eye reads it and folds it to
physical pixels. The debug-port lane is RETIRED (owner, Oct 16): it
handed any local process full CDP - the infostealer classic, the
approval dialogs, the automation banner. The extension IS the answer,
and this module now READS what the extension's API can send instead of
proving a port.

The row is the OPEN API's veil payload (extension/README.md): rect (the
first <video>'s viewport box, CSS px), dpr, paused, scroll, view, and
the window's outer bounds the extension measured itself. The feature is
OFF by default: OFF is the FRAME's root law - no theater ring - but
since Oct 20 the eye still reads the doorway every beat (the player
exemption does not wait for the switch). Fail-open is the root
law: a missing file, a junk row, a stale row all read as "no rect this
tick" and the dimmer's ramp retracts the veil (a vanished rect is a
stopped video, not an event worth a dark veil).

THE FOLD (content space -> physical desktop px): the page answers
getBoundingClientRect (viewport CSS px) and devicePixelRatio. Since
v0.4.3 the HOST measures the browser's ACTUAL web viewport - the
Chrome_RenderWidgetHostHWND child - in physical px and stamps it as
`webrect`; the fold anchors on that when the row carries one, because
the page's window.screenX/screenY reports the WINDOW rect, not the
viewport (measured (0,0) on a maximized window whose content starts at
(42,109): the whole toolbar plus the GX sidebar sit between the two).
Rows WITHOUT webrect (host/extension pairs mid-update) fold the older
origin report, then the legacy bounds math - both kept as the compat
lane (DIP scaled by dpr, uniform-desk assumption: every panel on this
box shares the scale; mixed-DPI desks are the future lane's). The size
law is UNCHANGED: round() is the one ruler.

SIZE LAW note (~170): the module is ONE seam - the fold, the read, the
tick. The transport lived in wm/_cdp and died with the port; the fold
stays here because the geometry law owns it. One file, one reader.
"""

import ctypes
import json
import logging
import os
import time

log = logging.getLogger("videoeye")
_u32 = ctypes.windll.user32          # the virtual-desktop query only


def door_path(env=None):
    """The app's own doorway: %APPDATA%\\PanelBoss\\rect, the fixed
    path the native host writes. Exposed so the suite can point it at a
    temp dir without touching the real app file."""
    return os.path.join(env.get("APPDATA", "") if isinstance(env, dict)
                        else os.environ.get("APPDATA", ""),
                        "PanelBoss", "rect")


RECT_PATH = door_path()

DEFAULT_GRACE = 3.0        # s: [videodim].grace_s rules
DEFAULT_MIN = 200000       #   the shipped defaults it normalizes to


def _origin(row):
    """The row's viewport-origin report (screenX/screenY, DIP) in its
    in-memory shape: a two-number list/tuple, or None. A junk origin
    reads as NO origin - the legacy bounds lane keeps the answer (the
    compat law for host/extension pairs mid-update)."""
    o = row.get("origin")
    if (isinstance(o, (list, tuple)) and len(o) == 2
            and all(isinstance(v, (int, float))
                    and not isinstance(v, bool) for v in o)):
        return [float(o[0]), float(o[1])]
    return None


def _four(v):
    """A four-number [left, top, w, h] in-memory shape, or None - the
    webrect parser (the host's measured viewport rect, PHYSICAL px).
    ZERO/NON-POSITIVE SIZE REJECTS (gate, Oct 17): a hidden/minimized
    window's degenerate report must fall through to the origin lane,
    not anchor a zero-offset hole."""
    if (isinstance(v, (list, tuple)) and len(v) == 4
            and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                    for x in v)
            and v[2] > 0 and v[3] > 0):
        return [float(v[0]), float(v[1]), float(v[2]), float(v[3])]
    return None


def _read(now, wall):
    """The extension's manual trigger, read as a content-space row. One
    doorway, one stat, one line of json. Missing/broken/empty all read
    None - a manual trigger may not cost the eye a beat. The mtime is
    the click's wall stamp, converted to the monotonic clock (now -
    age) so every row ages on one ruler."""
    try:
        mtime = os.path.getmtime(RECT_PATH)
    except OSError:
        return None
    try:
        with open(RECT_PATH, encoding="utf-8") as f:
            row = json.loads(f.readline())
    except (OSError, ValueError):
        return None
    if not isinstance(row, dict):
        return None
    try:
        r = row["rect"]
        out = {"rect": {"left": float(r["left"]),
                        "top": float(r["top"]),
                        "width": float(r["width"]),
                        "height": float(r["height"])},
               "dpr": float(row.get("dpr") or 1),
               "paused": bool(row.get("paused")),
               "scroll": row.get("scroll") or [0, 0],
               "view": row.get("view"),
               "family": row.get("family"),
               "lane": row.get("lane") or "auto",
               "bounds": row.get("bounds"),
               "origin": _origin(row),
               "webrect": _four(row.get("webrect")),
               "ts": now - max(0.0, wall - mtime), "src": "companion"}
    except (ValueError, KeyError, TypeError):
        return None
    return out


def _fold(row, bounds):
    """Content-space row + the window's OUTER bounds (left, top,
    width, height in PHYSICAL px) -> the video's physical rect
    (x, y, w, h). The viewport sits inside the outer by exactly
    (outer - inner*dpr): the chrome height down top, the border
    half-lateral (max-clamped: an outer smaller than the scaled
    inner is a DPI lie, not a negative chrome). A row without a
    usable video box or inner size is unplaceable -> None (the
    fail-open root)."""
    try:
        dpr = float(row.get("dpr") or 1)
        r = row["rect"]
        rl, rt = float(r["left"]), float(r["top"])
        rw, rh = float(r["width"]), float(r["height"])
        iw, ih = (row.get("view") or [0, 0])[:2]
        iw, ih = float(iw), float(ih)
    except (KeyError, TypeError, ValueError):
        return None
    if rw * rh <= 0 or bounds is None:
        return None
    ox, oy, ow, oh = bounds
    if iw * ih <= 0:
        return None
    vx = ox + max(0.0, ow - iw * dpr) / 2.0
    vy = oy + max(0.0, oh - ih * dpr)
    return (round(vx + rl * dpr), round(vy + rt * dpr),
            round(rw * dpr), round(rh * dpr))


def _rect_px(row):
    """Fold a row to physical px. THE WEBRECT IS THE REPORT (v0.4.3),
    THE ORIGIN WAS A LIE: the host now measures the browser's ACTUAL
    web viewport (the Chrome_RenderWidgetHostHWND child) in PHYSICAL px
    and stamps it as webrect [left, top, w, h]. The page's rect is
    viewport-CSS px, so the fold is webrect.left + rect.left*dpr (the
    viewport origin no longer comes from window.screenX/screenY, which
    Chromium fills with the WINDOW rect - measured (0,0) on a maximized
    window whose content actually starts at (42,109): the whole browser
    toolbar (~109px) and the GX sidebar (~42px) live between the two).
    A row WITHOUT webrect (host/extension pairs mid-update) folds the
    origin report if present, else the legacy bounds math - both kept
    as the compat lane, same rounding (round(), one ruler). None when
    the row is unplaceable."""
    wr = row.get("webrect")
    if (isinstance(wr, (list, tuple)) and len(wr) == 4
            and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    for v in wr)):
        try:
            dpr = float(row.get("dpr") or 1)
            r = row["rect"]
            rl, rt = float(r["left"]), float(r["top"])
            rw, rh = float(r["width"]), float(r["height"])
        except (KeyError, TypeError, ValueError):
            return None
        if rw * rh <= 0:
            return None
        return (round(wr[0] + rl * dpr), round(wr[1] + rt * dpr),
                round(rw * dpr), round(rh * dpr))
    o = row.get("origin")
    if o is not None:
        try:
            dpr = float(row.get("dpr") or 1)
            r = row["rect"]
            rl, rt = float(r["left"]), float(r["top"])
            rw, rh = float(r["width"]), float(r["height"])
        except (KeyError, TypeError, ValueError):
            return None
        if rw * rh <= 0:
            return None
        return (round((o[0] + rl) * dpr), round((o[1] + rt) * dpr),
                round(rw * dpr), round(rh * dpr))
    b = row.get("bounds")
    if isinstance(b, dict) and all(k in b for k in
                                   ("left", "top", "width", "height")):
        dpr = float(row.get("dpr") or 1)
        bounds = tuple(float(b[k]) * dpr for k in
                       ("left", "top", "width", "height"))
        return _fold(row, bounds)
    return None


# the last good row per family, keyed by the extension's family word -
# freshest-wins across families, the dimmer's door reads the newest.
_STATE = {}


def tick(cfg, now):
    """The _boot hook (AFTER dimmer.tick): refresh the view of the
    companion. THE EYE ALWAYS LOOKS (owner, Oct 20): the doorway is
    read every tick even when [videodim] is off - the extension
    pushes regardless of the app's switch, and the PLAYER EXEMPTION
    (a window playing a reported video is never plain-veiled, with
    or without theater mode) needs a fresh view to key on. One stat
    and one short line of json per beat is the whole cost. A stale
    row ages out in the door's grace; nothing here grows a timer."""
    row = _read(now, time.time())
    if row is None:
        return
    fam = row.get("family") if row.get("family") in ("chrome", "edge",
                                                     "opera_gx") \
        else "chrome"
    st = _STATE.setdefault(fam, {"row": None, "ts": 0.0})
    if st["row"] is None or row["ts"] >= st["ts"]:   # freshest wins
        st["row"], st["ts"] = row, row["ts"]


def live_rect(cfg, now=None):
    """THE PLAYER-EXEMPTION DOOR (owner, Oct 20): the live playing
    rect with the SAME liveness law as video_rect - not paused, big
    enough for min_rect_px, on the desk, fresh by lane - but NOT
    gated on [videodim].on. The exemption is a property of the buddy
    reporting a playing video, not of the theater switch: a user who
    turned theater mode off still told the eye where their movie is,
    and 'veil never lands on a video' holds either way."""
    return _best_rect(cfg, now)


def live_pair(cfg, now=None):
    """THE PAIRED DOOR (owner clause 1, Oct 20): (live playing rect,
    reporting window's bounds) from ONE walk - the shape the dimmer
    seams on. Same ungated consent as live_rect. Either half reads
    None on its own law: no live row answers (None, None); a row
    whose bounds the host never reported answers (rect, None) and
    the dimmer keeps the VIDEO rect as the ring's hole - the default
    law since the Oct-24 ruling (the reported window frames the hole
    only when the config word says 'window'). The liveness gates ride the VIDEO rect
    throughout (min_rect_px, paused, visible-picture): a tiny ad in
    a huge window is a tiny video - the min rail is the video's,
    only the hole is the window's."""
    return _best_pair(cfg, now)


def window_rect(cfg, now=None):
    """The REPORTING WINDOW's bounds ALONE (the eye's door the probe
    and the suite speak): the live row's outer bounds folded to
    physical px, None with no live row or no usable bounds."""
    return _best_pair(cfg, now)[1]


def _best_rect(cfg, now):
    return _best_pair(cfg, now)[0]


def _best_pair(cfg, now):
    """ONE walk, both answers: the freshest row that passes every
    liveness law (not paused, big enough for min_rect_px, on the
    desk, fresh by lane) -> (its video rect, its window bounds).
    Any failure anywhere is (None, None); the dimmer holds it one
    tick and its ramp retracts the veil."""
    now = time.monotonic() if now is None else now
    vd = cfg.get("videodim") or {}
    grace = float(vd.get("grace_s", DEFAULT_GRACE))
    mins = float(vd.get("min_rect_px", DEFAULT_MIN))
    best = None
    for fam, st in _STATE.items():
        row = st.get("row")
        if row is None:
            continue
        if row.get("paused"):
            continue                    # pause/end lifts immediately
        if row.get("lane") == "click":
            if now - st["ts"] > grace:
                continue                # a snapshot ages out on grace
        rect = _rect_px(row)
        if rect is None or rect[2] * rect[3] < mins:
            continue
        if not _on_desktop(rect):
            continue                    # THE VISIBLE PICTURE (Oct 19)
        if best is None or st["ts"] > best[1]:
            best = (rect, _window_phys(row), st["ts"])
    return (best[0], best[1]) if best else (None, None)


def _window_phys(row):
    """The row's OUTER WINDOW bounds in physical px: the bounds the
    extension measured itself (DIP), dpr-scaled by the same ruler
    the legacy fold uses. A row without usable bounds (missing,
    junk, zero-size) reads None - fail-open, the compat lane, not
    an error."""
    try:
        b = row.get("bounds")
        dpr = float(row.get("dpr") or 1)
        bounds = tuple(float(b[k]) * dpr for k in
                       ("left", "top", "width", "height"))
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    if bounds[2] <= 0 or bounds[3] <= 0:
        return None
    return tuple(round(v) for v in bounds)


def video_rect(cfg, now=None):
    """The dimmer's theater door: the live PHYSICAL rect (x, y, w, h)
    of a PLAYING video - the shared liveness law of live_rect, plus
    the [videodim].on feature gate. Whether the veil is CREATION-ready
    (a live playing rect - dimmer._live_rect) is the DIMMER's law,
    applied there; the eye must never grow a timer.

    Two lanes, two freshness laws:
      - CLICK (lane "click"): a one-shot snapshot, good for grace_s -
        the owner's demoted test-the-geometry gesture.
      - AUTO (lane "auto"): the extension pushes on play AND pause/end;
        a playing video emits no further events, so a paused:false auto
        row is a durable STATE, not a snapshot. It stays live until a
        paused:true push (pause/end) or the app restarts - no short
        grace ages out a movie mid-roll. A browser that dies mid-play
        without a pause/end leaves the row; under the eye's law its
        window stays plain-veil-exempt until a pause push or an app
        restart - admitted cost: the buddy's report is the fact, and
        the buddy is the first to know when the tab goes.

    Any failure anywhere is None; the dimmer holds it one tick and its
    ramp retracts the veil."""
    if not (cfg.get("videodim") or {}).get("on"):
        return None
    return _best_rect(cfg, now)


def _on_desktop(rect):
    """True when the folded rect intersects the VIRTUAL DESKTOP (all
    monitors' union - one GetSystemMetrics quartet). THE VISIBLE
    PICTURE LAW (owner, Oct 19, the GX ghost): a paused:false row
    whose window lives entirely off the desk - a memory-saver tab
    parked at (-32000,-32000), a minimized player - has no picture
    ANYWHERE to dim around, and theater must not veil a desk for a
    rumor of video. The conjunct is the frame, not the audio: the
    owner's law verbatim - 'I have no videos playing but it's
    applying and tearing down the full screen veil'. A refused query
    answers True: the fail-open root never lets a dead syscall veto
    a real movie."""
    try:
        vx = _u32.GetSystemMetrics(76)          # SM_XVIRTUALSCREEN
        vy = _u32.GetSystemMetrics(77)          # SM_YVIRTUALSCREEN
        vw = _u32.GetSystemMetrics(78)          # SM_CXVIRTUALSCREEN
        vh = _u32.GetSystemMetrics(79)          # SM_CYVIRTUALSCREEN
    except Exception:
        return True
    x, y, w, h = rect
    return x < vx + vw and x + w > vx and y < vy + vh and y + h > vy


def probe():
    """The one-shot truth for tests and the CLI: the doorway's last row
    and its folded rect - no shared state touched. A no-video desk
    answering None is a PASS."""
    now = time.monotonic()
    row = _read(now, time.time())
    return {"row": row, "rect": _rect_px(row) if row else None,
            "paused": bool(row and row.get("paused"))}