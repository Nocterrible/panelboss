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
OFF by default: off means no file reads, nothing. Fail-open is the root
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

import json
import logging
import os
import time

log = logging.getLogger("videoeye")


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
    companion. Feature OFF is a return at the root: no file read. The
    doorway file rides every tick (one stat); a stale row ages out in
    video_rect's grace."""
    vd = cfg.get("videodim") or {}
    if not vd.get("on"):
        return
    row = _read(now, time.time())
    if row is None:
        return
    fam = row.get("family") if row.get("family") in ("chrome", "edge",
                                                     "opera_gx") \
        else "chrome"
    st = _STATE.setdefault(fam, {"row": None, "ts": 0.0})
    if st["row"] is None or row["ts"] >= st["ts"]:   # freshest wins
        st["row"], st["ts"] = row, row["ts"]


def video_rect(cfg, now=None):
    """The dimmer's door: the live PHYSICAL rect (x, y, w, h) of a
    PLAYING video - not paused, big enough for min_rect_px (the
    ad-banner line of defense). This door knows ONE thing: "is a video
    playing, and where." The INPUT-IDLE conjunction (the theater veil
    requires the desk still) is the DIMMER's law, applied at
    dimmer._live_rect where the idle clock lives - not here; the eye
    must never grow a timer.

    Two lanes, two freshness laws:
      - CLICK (lane "click"): a one-shot snapshot, good for grace_s -
        the owner's demoted test-the-geometry gesture.
      - AUTO (lane "auto"): the extension pushes on play AND pause/end;
        a playing video emits no further events, so a paused:false auto
        row is a durable STATE, not a snapshot. It stays live until a
        paused:true push (pause/end) or the app restarts - no short
        grace ages out a movie mid-roll. A browser that dies mid-play
        without a pause/end leaves the row; the DIMMER's idle gate
        drops the frame the moment the owner touches the desk, so the
        stale row costs nothing.

    Any failure anywhere is None; the dimmer holds it one tick and its
    ramp retracts the veil."""
    now = time.monotonic() if now is None else now
    vd = cfg.get("videodim") or {}
    if not vd.get("on"):
        return None
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
        if best is None or st["ts"] > best[1]:
            best = (rect, st["ts"])
    return best[0] if best else None


def probe():
    """The one-shot truth for tests and the CLI: the doorway's last row
    and its folded rect - no shared state touched. A no-video desk
    answering None is a PASS."""
    now = time.monotonic()
    row = _read(now, time.time())
    return {"row": row, "rect": _rect_px(row) if row else None,
            "paused": bool(row and row.get("paused"))}