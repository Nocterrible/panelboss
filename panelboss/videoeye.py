"""videoeye: the dim-around-the-playing-video eye.

Geometry rides the Chrome DevTools Protocol - the debug port that
--remote-debugging-port opens and PanelBoss enables by launching the
browser with the flag (wm/_cdp is the stdlib transport). The feature
is OFF by default: off means no file reads, no sockets, nothing.
Fail-open is the root law: no port, no page, no video, a dead socket
all read as "no rect this tick", and the dimmer's ramp does the rest
(a vanished rect is a stopped video, not an event worth a dark veil).

THE FOLD (content space -> physical desktop px): the page answers
getBoundingClientRect (viewport CSS px), devicePixelRatio, paused and
the scroll pair. The viewport's own origin sits inside the window's
OUTER bounds by (outer - inner*dpr): chrome height down top, border
half-lateral. The outer truth is Browser.getWindowBounds for the
attached target - the packet measured window.screenX lying (0,0) on
occluded windows while this call tells the truth - one call, cached,
refreshed every BOUNDS_REFRESH seconds; when the port is dark the OS
window rect from wm is the fallback anchor and the same subtraction
runs against the inner size the evaluate carries. dpr scales the
content px onto the desk (uniform-desk assumption: every panel on
this box shares the scale; mixed-DPI desks are the future lane's).

The companion extension's manual trigger lands through the bridge
FILE instead (one-line json, the mtime as the stamp; both doorways
are read: %APPDATA%\\PanelBoss\\rect for the future native host,
%USERPROFILE%\\Downloads\\PanelBoss\\rect for the zero-plumbing
chrome.downloads writer of v1): freshest wins, ties go to the
click. The native-messaging host is FUTURE work -
extension/README.md carries the two manifest shapes that died
today and the stdin-EOF law they measured.

SIZE LAW note (~390): the module is ONE seam - the per-family door
object, the two clocks' reconciliation, and the fold. Splitting the
transport out already happened (wm/_cdp); splitting the fold from
the door would separate the bounds-cache discipline from the code
that fills it, and the fold is where the geometry law lives: one
file, one reader.
"""

import json
import logging
import os
import time

from .wm import _cdp

log = logging.getLogger("videoeye")

BROWSERS = ("opera_gx", "chrome", "edge")
EXES = {"opera_gx": "opera_gx.exe", "chrome": "chrome.exe",
        "edge": "msedge.exe"}
PROFILES = {"opera_gx": os.environ.get("APPDATA", "") +
            "\\Opera Software\\Opera GX Stable",
            "chrome": os.environ.get("LOCALAPPDATA", "") +
            "\\Google\\Chrome\\User Data",
            "edge": os.environ.get("LOCALAPPDATA", "") +
            "\\Microsoft\\Edge\\User Data"}
SITES = ("youtube.com", "netflix.com", "twitch.tv", "vimeo.com",
         "disneyplus.com", "primevideo.com")
BRIDGES = (os.environ.get("APPDATA", "") + r"\PanelBoss\rect",
           os.environ.get("USERPROFILE", "") +
           r"\Downloads\PanelBoss\rect")   # the zero-plumbing writer
                                           # is chrome.downloads: the
                                           # extension writes here
                                           # with no native host
# But chrome.downloads resolves its filename against EACH BROWSER's own
# download directory, not the OS Downloads folder (measured Oct 16: this
# desk's Opera GX is configured to C:\FastDLs, and a click there landed
# on a shelf the reader never checked). The candidate list is therefore
# extended at read time from every known browser's Preferences - see
# _download_bridges.
_DL_RE = None                              # compiled lazily; re is rare

_BRIDGE_TTL = 60.0
_bridge_cache = {"until": 0.0, "paths": ()}


def _download_bridges(now):
    """Every Chromium-family browser on this box gets its Preferences
    regex-scanned ONCE A MINUTE (the eye runs per beat; re-reading a
    multi-MB JSON every second would be the tail wagging the eye) for
    download.default_directory, and each answer joins the shelves the
    bridge click is looked for on. A browser-less box, an unreadable
    file, and a config without the key all answer zero extra paths,
    never an error."""
    global _DL_RE
    if _DL_RE is None:
        import re
        _DL_RE = re.compile(r'"default_directory":"((?:[^"\\]|\\.)*)"')
    if now < _bridge_cache["until"]:
        return _bridge_cache["paths"]
    out = list(BRIDGES)
    for root in PROFILES.values():
        for name in ("Preferences", "Secure Preferences"):
            for prof in ("Default", ""):          # the profile lives
                try:                              # under Default on
                    with open(os.path.join(root, prof, name),
                              encoding="utf-8",   # every family here
                              errors="replace") as f:
                        m = _DL_RE.search(f.read())
                except OSError:
                    continue
                if not m:
                    continue
                try:
                    d = json.loads('"' + m.group(1) + '"')  # unescape
                except ValueError:
                    continue
                out.append(os.path.join(d, "PanelBoss", "rect"))
    _bridge_cache["until"] = now + _BRIDGE_TTL
    _bridge_cache["paths"] = tuple(dict.fromkeys(out))   # dedupe, the
    return _bridge_cache["paths"]                        # appdata door
                                                         # stays first


TICK = 0.5                 # s: one port probe per family per this,
                           # backed off on misses (a dark port may
                           # never stall the loop)
BOUNDS_BACKOFF = 10.0      # s: after a refused truth call, stop
                           # asking the same port for the bounds
BOUNDS_REFRESH = 2.0       # s: the Browser.getWindowBounds cache law
DEFAULT_GRACE = 3.0        # s: [videodim].grace_s rules; these are
DEFAULT_MIN = 200000       #   the shipped defaults it normalizes to

# the content-space rect, carried as ONE string the extension ships
# verbatim in its click: the first video element's viewport box, the
# device pixel ratio, the paused flag, the scroll pair (the DRM lane
# of the future reads document space from it), the inner size the
# fold needs
RECT_JS = ("(function(){var v=document.querySelector('video');"
           "return v?JSON.stringify({rect:v.getBoundingClientRect(),"
           "dpr:window.devicePixelRatio,paused:v.paused,"
           "scroll:[window.scrollX,window.scrollY],"
           "view:[window.innerWidth,window.innerHeight]}):'null';})()")


def _site(url, sites=SITES):
    return next((s for s in sites if s in (url or "")), None)


def _bridge(now, wall):
    """The extension's manual trigger, read as a content-space row.
    Both doorways are checked - the appdata file (the future native
    host's absolute path) and the downloads folder (chrome.downloads
    is the ZERO-PLUMBING writer the v1 click rides: no host, no
    manifest, one blob download with conflictAction overwrite). The
    freshest file's mtime is the click's WALL stamp; it is converted
    to the loop's monotonic clock on arrival (now - age) so port
    rows and file rows age on ONE ruler. Missing/broken/empty all
    read None - a manual trigger may not cost the port a beat."""
    path, mtime = None, 0.0
    for p in _download_bridges(wall):
        try:
            m = os.path.getmtime(p)
        except (OSError, ValueError):   # ValueError: a garbage-matched
            continue                    # default_directory with a NUL
                                        # escape reaches getmtime as an
                                        # embedded-null path (gate nit
                                        # 1, Oct 16) - one miss, loud
                                        # nowhere, the eye keeps beats
        if m >= mtime:
            path, mtime = p, m
    if path is None:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            row = json.loads(f.readline())
    except (OSError, ValueError):
        return None
    try:
        r = row["rect"]
        return {"rect": {"left": float(r["left"]), "top": float(r["top"]),
                         "width": float(r["width"]),
                         "height": float(r["height"])},
                "dpr": float(row.get("dpr") or 1),
                "paused": bool(row.get("paused")),
                "scroll": row.get("scroll") or [0, 0],
                "view": row.get("view"), "family": row.get("family"),
                "bounds": row.get("bounds"),
                "ts": now - max(0.0, wall - mtime), "src": "bridge"}
    except (ValueError, KeyError, TypeError):
        return None


def window_bounds(family):
    """The family's MAIN window rect (x, y, w, h) physical px, from
    the OS: the codebase already enumerates windows for the dimmer
    (wm.list_windows - the largest visible row of the family's exe
    IS its main window; no new verb, no new promise). None when the
    browser is not on the desk."""
    from . import wm
    best = None
    for w in wm.list_windows():
        if w["exe"] == EXES[family]:
            r = w["rect"]
            if best is None or r[2] * r[3] > best[2] * best[3]:
                best = (r[0], r[1], r[2], r[3])
    return best


def _fold(row, bounds):
    """Content-space row + the window's OUTER bounds (left, top,
    width, height in PHYSICAL px) -> the video's physical rect
    (x, y, w, h). The viewport sits inside the outer by exactly
    (outer - inner*dpr): the chrome height down top, the border
    half-lateral (max-clamped: an outer smaller than the scaled
    inner is a DPI lie, not a negative chrome). A row without a
    usable video box or inner size is unplaceable -> None (the
    fail-open root; the bridge carries no view pair and folds
    through its own measured bounds instead - see _Family)."""
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


class _Family:
    """One browser family's door: the port probe, the page attach,
    the truth call, the last good row. Every failure lands in `say`,
    never in an exception; the loop thread owns this object alone -
    with one documented guest: the Tk-side companion.veil_now may
    also write row/ts as one-shot feed pairs (GIL-atomic stores; a
    torn pair costs at most one grace-window, and the tick's own
    bridge fold re-lands the same row the next beat and heals it)."""

    def __init__(self, name):
        self.name = name
        self.port = None
        self.last_check = 0.0
        self.say = "not checked"
        self.miss = 0
        self.sock = None                 # (ws_url, Socket)
        self.brand = None                # the /json/version word
        self.page_url = ""               # the chosen page, for say
        self.site = None
        self.row = None                  # last good content-space row
        self.ts = 0.0                    #   its monotonic stamp
        self.bounds = None               # last truthful OUTER (DIP px)
        self._bts = 0.0

    def _mine(self, browser_word):
        """Whose port it is: the /json/version Browser word, not the
        port number - two Chromium families happily share the hint
        list, and a chrome port dressed as opera_gx anchors the fold
        on the wrong window. Chrome answers Chrome/, Edge answers
        Edg/ (its word starts with it, and the Chrome token riding
        behind does not), Opera GX answers OPR/."""
        if self.name == "edge":
            return browser_word.startswith("Edg/")
        if self.name == "opera_gx":
            return browser_word.startswith("OPR") or \
                browser_word.startswith("Opera")
        return browser_word.startswith("Chrome/")

    def _probe(self, now, timeout=0.3, sites=SITES):
        port = _cdp.find_port([PROFILES[self.name]], timeout)
        self.port = port
        if port is None:
            self.say = "no debug port answers"
            self.miss += 1
            return
        ver = _cdp.read_json("http://127.0.0.1:%d/json/version" % port,
                             timeout) or {}
        self.brand = ver.get("Browser") or "?"
        if not self._mine(self.brand):
            self.port = None
            self.say = "the port belongs to %s" % self.brand
            self.miss += 1
            return
        self.miss = 0
        d = _cdp.read_json("http://127.0.0.1:%d/json" % port, timeout)
        page = next((t for t in (d or [])
                     if isinstance(t, dict)
                     and t.get("type") == "page"
                     and _site(t.get("url"), sites or SITES)
                     and t.get("webSocketDebuggerUrl")),
                    None) if isinstance(d, list) else None
        if page is None:
            self.say = "no streaming page"
            return
        self._page(page, now, timeout, sites)

    def _call(self, method, params, timeout):
        """One call on the OPEN attach; a socket that died between
        ticks is not an event, it is the browser's Tuesday: drop,
        re-attach ONCE, retry. The second failure clears the attach
        and raises (the tick reports it, the grace holds the rect)."""
        if self.sock is None:
            raise _cdp.CdpError("no attach")
        try:
            return self.sock[1].talk(method, params, timeout=timeout)
        except (_cdp.CdpError, OSError):
            self.detach()
            raise

    def detach(self):
        if self.sock is not None:
            try:
                self.sock[1].close()
            except OSError:
                pass
            self.sock = None

    def _attach(self, page, timeout):
        url = page["webSocketDebuggerUrl"]
        if self.sock is not None and self.sock[0] == url:
            return self.sock[1]
        self.detach()
        self.sock = (url, _cdp.Socket(url, timeout=timeout))
        return self.sock[1]

    def _page(self, page, now, timeout, sites=None):
        self.page_url = page.get("url") or ""
        self.site = _site(self.page_url, sites or SITES)
        try:
            self._attach(page, timeout)
            try:
                res = self._call("Runtime.evaluate",
                                 {"expression": RECT_JS,
                                  "returnByValue": True}, timeout)
            except (_cdp.CdpError, OSError):
                # the one re-attach the dead-socket Tuesday deserves
                self._attach(page, timeout)
                res = self._call("Runtime.evaluate",
                                 {"expression": RECT_JS,
                                  "returnByValue": True}, timeout)
        except (_cdp.CdpError, OSError):
            self.detach()
            self.say = "the page refused the attach"
            return
        v = ((res or {}).get("result") or {}).get("value")
        if not v or v == "null":
            self.say = "no video element"
            return
        try:
            self.row, self.ts = json.loads(v), now
            self.say = "playing on " + (self.site or "?")
        except (ValueError, TypeError):
            self.say = "the page answered junk"
            return
        self._truth(page["id"], now, timeout)

    def _truth(self, target_id, now, timeout):
        """Browser.getWindowBounds for the ATTACHED target through
        the open page attach - the truthful outer bounds, cached
        BOUNDS_REFRESH; a refusal (the windowId the target does not
        own, an old Chrome without the call) is no crime: the fold
        falls back to the OS window rect (window_bounds) and the
        port's bounds door stays shut for BOUNDS_BACKOFF seconds."""
        if now - self._bts < BOUNDS_REFRESH:
            return                       # fresh, refused recently, or
                                         # never asked (0.0 = ask now)
        if self.sock is None:
            return
        try:
            wid = (self._call("Browser.getWindowForTarget",
                              {"targetId": target_id}, timeout)
                   or {}).get("windowId")
            b = (self._call("Browser.getWindowBounds",
                            {"windowId": wid}, timeout)
                 or {}).get("bounds")
        except (_cdp.CdpError, OSError):
            self._bts = now
            return
        if b:
            self.bounds = (b["left"], b["top"], b["width"], b["height"])
            self._bts = now
        else:
            # an empty answer is a refusal too: the door stays shut
            # for BOUNDS_BACKOFF (the arithmetic lands the next try
            # then, and until it the OS rect anchors the fold)
            self._bts = now + BOUNDS_BACKOFF - BOUNDS_REFRESH

    def rect_px(self, now):
        """The family's last good row folded to physical px (the
        grace check is video_rect's law, not mine). Anchor order:
        a row that carries its OWN outer bounds (the bridge click,
        measured by the extension itself) folds against those -
        DIP scaled by dpr, uniform desk; then the truth call's
        bounds (port rows); and the OS window rect (window_bounds)
        anchors a family whose port never answered the bounds
        call. The same subtraction runs everywhere: outer minus
        inner*dpr is the chrome, and the veil paints what is left."""
        if self.row is None:
            return None
        row = self.row
        dpr = float(row.get("dpr") or 1)
        ob = row.get("bounds")
        b = None
        if isinstance(ob, dict) and all(
                k in ob for k in ("left", "top", "width", "height")):
            b = tuple(float(ob[k]) * dpr
                      for k in ("left", "top", "width", "height"))
        elif self.bounds is not None:
            b = tuple(v * dpr for v in self.bounds)
        else:
            b = window_bounds(row.get("family") or self.name)
        return _fold(row, b)


_STATE = {}


def tick(cfg, now):
    """The _boot hook (AFTER dimmer.tick): refresh every family's
    view of the desk. Feature OFF is a return at the root: no file
    read, no socket. The bridge file rides every tick (one stat);
    the port rides the TICK clock, backed off to 8 s on misses -
    a dark port may never stall the loop."""
    vd = cfg.get("videodim") or {}
    if not vd.get("on"):
        return
    sites = vd.get("sites") or SITES
    for name in BROWSERS:
        f = _STATE.setdefault(name, _Family(name))
        gap = min(8.0, TICK * (2 ** min(f.miss, 4)))
        if now - f.last_check >= gap:
            f.last_check = now
            try:
                f._probe(now, sites=sites)
            except Exception as e:            # a dead browser is not
                f.say = "probe died: %s" % e  # a dead FEATURE
        b = _bridge(now, time.time())
        if b is not None and (f.row is None or b["ts"] >= f.ts):
            f.row, f.ts = b, b["ts"]      # freshest wins, ties the
                                          # file's (a click IS intent)


def video_rect(cfg, now=None):
    """The dimmer's door: the live PHYSICAL rect (x, y, w, h) of a
    playing video - not paused, big enough for min_rect_px (the
    ad-banner line of defense), fresh within grace_s. Any failure
    anywhere is None; the dimmer holds it one tick and its ramp
    retracts the veil (the vanished rect is a stopped video)."""
    now = time.monotonic() if now is None else now
    vd = cfg.get("videodim") or {}
    if not vd.get("on"):
        return None
    grace = float(vd.get("grace_s", DEFAULT_GRACE))
    mins = float(vd.get("min_rect_px", DEFAULT_MIN))
    best = None
    for name in BROWSERS:
        f = _STATE.get(name)
        if f is None or f.row is None or now - f.ts > grace:
            continue
        if f.row.get("paused"):
            continue
        rect = f.rect_px(now)
        if rect is None or rect[2] * rect[3] < mins:
            continue
        if best is None or f.ts > best[1]:
            best = (rect, f.ts)
    return best[0] if best else None


def probe():
    """The one-shot truth for tests and the CLI: every family's
    port, chosen page, content row, folded rect - no shared state
    touched. The LIVE leg of the delivery runs this and reports the
    dict verbatim; a no-video desk answering None is a PASS."""
    now = time.monotonic()
    out = {}
    for name in BROWSERS:
        f = _Family(name)
        try:
            f._probe(now, timeout=1.0)
        except Exception as e:
            f.say = "probe died: %s" % e
        out[name] = {"port": f.port, "say": f.say,
                     "page": f.page_url or None,
                     "rect": f.rect_px(now),
                     "paused": bool(f.row and f.row.get("paused")),
                     "row": f.row, "bounds": f.bounds,
                     "bridge": _bridge(now, time.time())}
        f.detach()
    return out
