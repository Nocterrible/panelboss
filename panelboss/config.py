"""Config handling.

Reads %APPDATA%\\PanelBoss\\config.toml, writing stock defaults
first if it has never been created. Unknown keys are tolerated (forward
compatible); missing keys are backfilled from stock defaults so the state
machine never has to None-check.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    import tomllib  # 3.11+ ships tomllib in the stdlib
except ImportError:
    import tomli as tomllib  # type: ignore

log = logging.getLogger("config")

APP_NAME = "PanelBoss"

# the base directory; the environment variable wins so portable installs
# can redirect it next to the repo
appdata = os.environ.get("APPDATA")
if appdata:
    CONFIG_DIR = Path(appdata) / APP_NAME
else:
    CONFIG_DIR = Path.home() / ".config" / APP_NAME

CONFIG_DIR = os.environ.get("PANELBOSS_CONFIG_DIR") or str(CONFIG_DIR)

LOG_DIR = os.environ.get("PANELBOSS_LOG_DIR") or str(Path(CONFIG_DIR) / "logs")

# stock defaults, in one place so behavior is documented by code
DEFAULTS = {
    "camera": {
        "index": 0,             # an int, or a list of ints: several cameras
                                # rotate (one votes per poll, round-robin);
                                # -2 = Windows Hello IR sensor (the optional
                                # whircam bridge: pip install whircam)
        "name_contains": "",    # substring(s) matched against device names
                                # and merged into the index list at config
                                # load (re-checked at open time); matches
                                # join the rotation, "" = names ignored
                                # (old files may hold a list); a sentinel
                                # index (-1/-2) stays single-eyed
        "width": 1280,
        "height": 720,
        "warmup_frames": 4,     # auto-exposure needs time to settle before inference
        "mode_on": "boot_per_poll",   # "boot_per_poll" | "always_on", while screens are on
        "mode_off": "always_on",      # while screens are off, LED is invisible anyway
        # per-index overrides of the two globals above, per display
        # state: {index: mode} with modes CAMERA_MODES. An index
        # missing from a table inherits that table's global; no tables
        # at all is exactly the old one-mode-everyone behavior
        "on": {},
        "off": {},
        # wear guard: an always_on camera that has streamed without a
        # re-arm (boot, or any wake / dark transition) longer than
        # this falls back to boot_per_poll ("degraded") and votes at
        # the fallback cadence below until the next re-arm
        "always_timeout_sec": 3600,
        "always_fallback_poll_sec": 10,
        # camera identity (v1 wizard): keyed on the PnP InstanceId,
        # NOT the index - indexes drift on replugs (measured Oct 12),
        # the instance path does not. labels maps instance -> the
        # user's name; hidden lists instances the picker and the
        # roster menu lines suppress (the engine still honors a
        # hidden index already on duty - its row wears a badge)
        "labels": {},
        "hidden": [],
    },
    "inference": {
        "model": "yolo11n",
        "device": "auto",       # "auto" | "cuda" | "cpu"
        "device_id": 0,
        "confidence": 0.45,
        "min_hits": 2,          # consecutive positive polls before power is restored
    },
    "detection": {
        "mode": "person",       # "person" = the ONNX model; "motion" =
                                # frame differencing only: no ML, nothing
                                # learned about faces, and it drives IR /
                                # depth sensors exactly like a webcam
        "ratio": 0.003,         # share of the downscaled frame that must
                                # change for one poll to count as motion
        "diff_level": 22,       # per-pixel gray delta that counts as a
                                # change (raise it for noisy depth sensors)
        "hold_sec": 180,        # presence lingers this long after the LAST
                                # motion: stillness is not absence
    },
    "timers": {
        "idle_gate_sec": 30,         # no camera polls until the keyboard has been idle this long
        "absent_confirm_sec": 60,    # screens go dark after absence is confirmed this long
        "on_poll_sec": 3,            # cadence while screens are on and absence is being confirmed
        "present_recheck_sec": 60,   # cadence after a person is confirmed present
        "off_poll_sec": 3,           # cadence while screens are off (LED is already off, cam stays open)
        "re_off_grace_sec": 30,      # budget a monitor gets while it is awake with nobody in front of it
    },
    "recovery": {
        "wake_policy": "re_off",     # "re_off" | "leave_on": what to do when the display is
                                     # back on (key press, mouse jiggle) but nobody is in front of it
        "leave_on_grace_sec": 180,   # ignored unless wake_policy is "leave_on"
        "wake_burst_count": 2,       # this many unexpected wakes within the window below ...
        "wake_burst_window_sec": 120,  # ... pauses auto re-off (the camera probably
                                       # slipped and is looking at a wall)
    },
    "guards": {
        "fullscreen": True,     # do not send the off broadcast while a fullscreen game owns the display,
                                # the message is swallowed by the swapchain
    },
    "power": {
        "hold_display": True,    # while the app watches a lit desk it holds
                                 # the plan's display timeout off - a still
                                 # person reading a page is never timed out
        "hold_sleep": True,      # ...and the sleep timeout. The dark watcher
                                 # needs it too: without it the box sleeps
                                 # and presence detection only re-arms when
                                 # the power button is pressed
        "skip_camera_when_blocked": True,  # if another app already holds the
                                           # display awake, the camera does not
                                           # poll to defend it
        "restore_windows": True,     # monitors that unplug themselves on
                                     # standby make Windows re-lay every
                                     # window when they return: the desk is
                                     # remembered at screens-off and put
                                     # back after any wake (see wm.py)
        "assistant_task": False,   # opt-in: registers an elevated scheduled
                                   # task so powercfg /requests can be read
                                   # without running the app as admin
                                   # (one UAC confirm when ticked)
        "poll_sec": 5,             # how often to re-run powercfg /requests when idle
        "ignore": [],              # substrings; processes powercfg names but that
                                   # are not real blockers on this machine
        "hdr_off_when_away": False,  # turn HDR off when the screens go dark
                                     # and hand it back on return: OLED desks
                                     # that live in HDR get their SDR desktop
                                     # washed without it, and the return lands
                                     # exactly on what the user had per panel
    },
    "gaming": {
        "enabled": False,        # the refresh-rate watcher; off until the
                                 # user asks for it (it only ever trades a
                                 # rate the panel already offers)
        "games": [],             # exe names that enter instantly (a title
                                 # screen renders at 0% GPU and still owns
                                 # the panel); any other fullscreen app can
                                 # still earn in via xinput or sustained GPU
        "ignore": [],            # exe names that must never look like a
                                 # game, even if they fool the list
        "threshold_pct": 5.0,    # per-process rendering load that counts as
                                 # evidence (decode-only never does)
        "seen_secs": 10.0,       # how long evidence must hold before the
                                 # panel switches (a browser spike is not a
                                 # game)
        "grace_secs": 60.0,      # how long a game keeps its rate through
                                 # menus, cutscenes and alt-tabs before the
                                 # desktop rate is handed back
        "game_hz": {},           # monitor short -> "auto" (the panel's
                                 # fastest), "vrr" (the user has
                                 # g-sync on it: never flip it, pin
                                 # its max) or a number; unset means auto
        "desktop_hz": {},        # monitor short -> the rate the panel gets
                                 # back when no game owns it; unset means 60
        "power_plan": "",        # name fragment or guid swapped in when a
                                 # game starts ('' = hands off the plan)
    },
    "tweaks": {
        "fso_apps": [],          # full exe paths that get fullscreen
                                 # optimizations OFF in the registry
                                 # (takes effect next launch of each);
                                 # the Layers key is MIRRORED to this
                                 # list at boot - foreign tokens in
                                 # existing values are preserved
    },
    "taskbar": {
        "enabled": False,       # the taskbar hover/autohide emulator
                                 # (taskbar.py); off until asked. It only
                                 # emulates the show-on-hover /
                                 # hide-on-leave of a bar that is ALREADY
                                 # autohiding, and it hands off entirely
                                 # (does nothing) when a tinkerer's mod
                                 # owns the bar - a Windhawk / EP / 7T /
                                 # tweaker co-tenant intercepts the same
                                 # surfaces and wins the bar.
        "retry_ms": 150,        # cadence to re-post the show poke while
                                 # the cursor sits at the bar's edge and a
                                 # post gets swallowed by a fullscreen
                                 # foreground app
    },
    "faces": {
        "enabled": False,       # only registered identities count as presence (insightface)
    },
    "ui": {
        "enabled": True,        # settings window on start; false = headless
        "start_minimized": False,  # true = boot straight to the tray
                                   # icon (left-click opens the window)
        "skin": "modern",       # "modern" (the unfun one) | "fun" (palette stub for now)
        "window_size": [1200, 820],  # initial size; the window OVERWRITES
                                     # it on resize-recall (750 ms
                                     # debounced, clamped 600x420..workarea)
        "preview_width": 420,   # debug camera panel width in px
        "preview_poll_ms": 200,  # applies ONLY while a preview lease is
                                 # held; clamped 50..2000 at the read
                                 # (state-side clamp already covers
                                 # hand-built cfgs)
    },
    "restore": {
        "enabled": False,       # the pre-armed lever (General tab): a
                                # profile the app re-applies by itself
                                # when it starts
        "profile": "last",      # "last" = the one this desk last used
                                # (panel identity decides, modes may
                                # still differ after a cold boot); or
                                # one profile's exact name
        "scope": "full",        # "full" | "monitors" (modes, positions,
                                # HDR only) | "windows" (pinned apps to
                                # their seats only)
        "when": "autostart",    # "autostart" = only the copy the logon
                                # entry launched - the --autostart stamp
                                # in the Run key is the proof, never an
                                # inference; "always" = every app start
    },
}

# the load boundary: hand-edited junk in a section must fail OPEN with a
# loud warning naming the key and the offending value - never raise, never
# stay silent. The rules are data (section, key, kind, bound); a new
# boundary check is one row in the table.
NORMALIZE_RULES = (
    # must track DEVICE_KEYS (ui/window/_constants.py:29): a UI-added
    # backend (directml someday) the set lacks reverts to auto at boot
    ("inference", "device", "oneof", ("auto", "cuda", "cpu")),
    ("inference", "device_id", "int", None),
    ("inference", "confidence", "float", (0.05, 0.95)),
    ("detection", "ratio", "float", (0.0, 1.0)),
    ("detection", "diff_level", "int", 1),
    ("detection", "hold_sec", "int", 1),
    ("gaming", "game_hz", "hzmap", None),
    ("gaming", "desktop_hz", "hzmap", None),
    ("ui", "preview_width", "int", 160),
    # a rule's floor must not exceed the stock value or stock fails
    # its own rule - the audit's 250 was off by 50 against its own DEFAULTS
    ("ui", "preview_poll_ms", "int", 200),
    ("camera", "labels", "dicttype", {}),
    ("camera", "hidden", "listtype", []),
)


def _coerce(value, rule, stock):
    """One NORMALIZE_RULES row; returns (ok, coerced, reason). A failure
    returns the stock value and the reason the warning prints."""
    section, key, kind, bound = rule
    if kind == "oneof":
        value = value.lower() if isinstance(value, str) else value
        if value in bound:
            return True, value, ""
        return False, bound[0], "expected one of %s" % "/".join(bound)
    if kind == "int":
        if value is None:
            return True, None, ""       # None is legal: it means unset
        try:
            value = int(value)
        except (TypeError, ValueError):
            return False, stock, "not an int"
        if bound is not None and value < bound:
            return False, stock, "below %d" % bound
        return True, value, ""
    if kind == "float":
        try:
            value = float(value)
        except (TypeError, ValueError):
            return False, stock, "not a number"
        if not bound[0] <= value <= bound[1]:
            return False, stock, "outside %s..%s" % bound
        return True, value, ""
    if kind == "hzmap":
        # the per-monitor rate maps: None and {} are legal and mean
        # "unset"; junk (a scalar hand-edit) goes to the stock empty
        # map, never a crash at the reader. A dict's VALUES are
        # checked: each must be an int > 0 or one of the two legal
        # tokens ("auto"/"vrr" - the panel's own words for the rate
        # modes, see DEFAULTS game_hz/desktop_hz) - a bad entry is
        # dropped with a named warning, the survivors stay; a map
        # that empties out is the stock {}
        if value is None:
            return True, value, ""
        if not isinstance(value, dict):
            return False, copy.deepcopy(stock), "not a rate map"
        if not value:
            return True, value, ""     # {} is legal: "unset"
        cleaned = {}
        for monitor, hz in value.items():
            good = hz == "auto" or hz == "vrr"
            if not good:
                try:
                    rate = int(hz)
                except (TypeError, ValueError):
                    rate = None
                good = rate is not None and rate > 0
            if good:
                cleaned[monitor] = hz
            else:
                log.warning("config [%s].%s: dropping rate %r=%r "
                            "(must be an int > 0 or auto/vrr)",
                            section, key, monitor, hz)
        if not cleaned:
            # every entry was bad: one warning for the whole map, and
            # the stock empty map stands in
            log.warning("config [%s].%s: no usable rates left after "
                        "cleaning; using the stock empty map",
                        section, key)
            return True, copy.deepcopy(stock), ""
        return True, cleaned, ""
    if kind in ("dicttype", "listtype"):
        good = isinstance(value, dict) if kind == "dicttype" \
            else isinstance(value, list)
        if good:
            return True, value, ""
        return False, copy.deepcopy(bound), "not a %s" % kind[:-4]
    raise ValueError("unknown normalize kind %r" % kind)


def normalize_sections(merged):
    """Runs the boundary table over the merged config: any unusable
    value is replaced by its stock and logged with the key and the
    offending value named. Never raises - junk fails open."""
    for section, key, kind, _bound in NORMALIZE_RULES:
        section_cfg = merged.get(section)
        if not isinstance(section_cfg, dict):
            continue
        stock = DEFAULTS[section][key]
        try:
            ok, coerced, reason = _coerce(section_cfg.get(key),
                                          (section, key, kind, _bound),
                                          stock)
        except Exception:
            ok, coerced, reason = (False, copy.deepcopy(stock),
                                   "coerce error")
        if not ok:
            # warn only when the FILE brought a value that differs from
            # stock: a stock value that trips its own bound (the poll-ms
            # 200 default vs the 250 floor) would otherwise confess on
            # every clean load
            if section_cfg.get(key) != stock:
                log.warning("config [%s].%s = %r is unusable (%s); "
                            "using %r", section, key, section_cfg.get(key),
                            reason, stock)
        section_cfg[key] = coerced


def normalize_index(value):
    """[camera] index in its in-memory shape: a list of ints. A bare int
    is one camera; a list is the rotation (one camera votes per poll,
    round-robin). An empty list means "the stock default"."""
    if value is None:
        return [0]
    if isinstance(value, (list, tuple)):
        out = [int(i) for i in value]
        return out if out else [0]
    return [int(value)]


def normalize_name_contains(value):
    """[camera] name_contains in its in-memory shape: a list of
    substrings. Both shapes read - the new stock default is a string,
    old files on disk may still hold a list; "" and [] both mean
    "no name matching"."""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    out = []
    for part in value:
        part = str(part).strip()
        if part:
            out.append(part)
    return out


CAMERA_MODES = ("boot_per_poll", "always_on", "off")
# the short words the tray and the preview tiles show for a mode
MODE_LABELS = {"boot_per_poll": "poll", "always_on": "always on",
               "off": "off"}


def normalize_camera_modes(value):
    """A [camera] mode table (the on/off sub-tables) in its in-memory
    shape: {int index: mode}. TOML table keys are strings, so "2" and
    2 both read; an unknown mode string warns and drops its entry (the
    index then inherits the global default); the sentinels -1/-2 never
    take an entry - they are single-eyed devices, the same rule the
    name match obeys - and are dropped quietly; a non-dict value (an
    old or hand-broken file) is the empty table, i.e. the globals."""
    out = {}
    if not isinstance(value, dict):
        return out
    for key, mode in value.items():
        try:
            index = int(str(key))
        except (TypeError, ValueError):
            log.warning("camera mode table: %r is not an index; "
                        "dropped", key)
            continue
        if index in (-1, -2):
            continue
        mode = "" if mode is None else str(mode)
        if mode not in CAMERA_MODES:
            log.warning("camera index %s: unknown mode %r; the index "
                        "keeps the global default", index, mode)
            continue
        out[index] = mode
    return out


def find_config(dir=CONFIG_DIR, config_name="config.toml"):
    """Returns the config path, creating parent directories."""
    if not os.path.exists(dir):
        os.makedirs(dir)
        log.debug(f"created {dir}")
    return os.path.join(dir, config_name)


def get_config(dir=CONFIG_DIR, initialize=True, verbose=True):
    """Loads config; writes defaults on first run so users have something to edit."""
    path = find_config(dir)
    config = {}
    if not os.path.exists(path):
        if initialize:
            write_config(DEFAULTS, path)
            log.info(f"wrote stock defaults to {path}")
        config = DEFAULTS
    else:
        try:
            with open(path, "rb") as f:
                config = tomllib.load(f)
        except Exception as e:  # a broken config should not crash the loop
            log.error(f"{path} does not parse ({e}); using stock defaults")
            config = {}
            # the defaults will be written back at the first save and
            # swallow a hand-edit with a typo in it - move the
            # wreckage aside first so the edit stays fixable
            try:
                bad = "%s.corrupt-%d" % (path, int(time.time()))
                os.replace(path, bad)
                log.error(f"unparsable config kept aside as {bad}")
            except OSError:
                log.exception("could not move %s aside", path)
    merged = {}
    for section, stock in DEFAULTS.items():
        # deepcopy, not dict(): a shallow copy aliases the NESTED
        # defaults, and the mutation sites (gaming rate picks, the
        # camera_identity labels, the preview _events handler) write
        # straight through it into DEFAULTS
        merged[section] = copy.deepcopy(stock)
        sec = config.get(section, {})
        if not isinstance(sec, dict):
            log.warning("config section %s is %r; using stock section "
                        "alone", section, type(sec).__name__)
            sec = {}
        merged[section].update(sec)
    # keep top-level keys too
    for key, value in config.items():
        if key not in merged:
            merged[key] = value
    merged["_path"] = path
    # [power] hold_timers became two switches (screen, sleep): one old
    # answer seeds both new keys, and the fossil is dropped so the writer
    # stops re-persisting it; keys the file already sets always win
    power_merged = merged.get("power", {})
    legacy = power_merged.pop("hold_timers", None)
    if legacy is not None:
        loaded = (config.get("power", {}) if isinstance(config, dict)
                  else {})
        for key in ("hold_display", "hold_sleep"):
            if key not in loaded:
                power_merged[key] = bool(legacy)
    if verbose:
        log.debug(f"using config from {path}")
    # [camera] index and name_contains normalize to one in-memory shape
    # (index a list of ints, names a list of substrings); the on-disk
    # file keeps whatever the user wrote
    camera_merged = merged.get("camera")
    if camera_merged is not None:
        camera_merged["index"] = normalize_index(
            camera_merged.get("index", 0))
        camera_merged["name_contains"] = normalize_name_contains(
            camera_merged.get("name_contains"))
        if camera_merged["name_contains"] and all(
                i >= 0 for i in camera_merged["index"]):
            # name matches resolve INTO the duty roster at load: the
            # rotation decision (state._rotor) counts plain indexes,
            # so a name-only config must already be a list by then.
            # probes are the camera module's cached ones, and any
            # probe failure leaves the explicit indexes standing.
            # a sentinel roster stays single-eyed here too (the same
            # rule open_camera enforces): no second eye next to
            # hello IR or the default device, or the bridge route
            # would silently lose its priority
            try:
                from . import camera
                camera_merged["index"] = camera._extend_by_name(
                    camera_merged["index"],
                    camera_merged["name_contains"])
            except Exception:
                log.exception("camera name match failed; running on "
                              "the explicit indexes alone")
        # the per-index mode tables and the wear-guard knobs normalize
        # here too: in memory the table keys are ints, the fallback
        # cadence has a floor (a 1 s "fallback" would be always_on
        # with extra steps), the timeout never goes negative
        camera_merged["on"] = normalize_camera_modes(
            camera_merged.get("on"))
        camera_merged["off"] = normalize_camera_modes(
            camera_merged.get("off"))
        camera_merged["always_timeout_sec"] = max(
            0, int(camera_merged.get("always_timeout_sec", 3600)))
        camera_merged["always_fallback_poll_sec"] = max(
            5, int(camera_merged.get("always_fallback_poll_sec", 10)))
        indexes = camera_merged["index"]
        if len(indexes) > 4:
            # four open streams is the cap: an always_on index holds
            # its device open at all times, and past four held
            # streams the drivers start to wedge. The duty roster is
            # the FIRST four of the index list; the rest are dropped
            # here and now, loudly
            log.warning("camera roster holds %d indexes but only four "
                        "open streams are supported: the first four "
                        "(%s) are on duty, the rest are dropped",
                        len(indexes), indexes[:4])
            camera_merged["index"] = indexes[:4]
    normalize_sections(merged)
    return merged


def _format_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_format_value(v) for v in value) + "]"
    if isinstance(value, dict):
        # TOML inline table, the ONLY legal dict shape here. The
        # old str(dict) fallback wrote Python single quotes, which
        # tomli rejects: the first save carrying a non-empty dict
        # (e.g. gaming.game_hz after a rate pick) made the NEXT
        # boot declare the whole file corrupt and reset every
        # setting to stock (found by the gaming UI suite,
        # 2026-10-10). Keys go through json too: TOML bare keys
        # are [A-Za-z0-9_-] only, and monitor shorts earn dots
        # and spaces from EDID names often enough.
        return "{" + ", ".join("%s = %s" % (json.dumps(k),
                                            _format_value(v))
                               for k, v in value.items()) + "}"
    return str(value)


def _dumps_key(key):
    """A TOML key: bare when legal, quoted otherwise (json's basic
    string quoting IS TOML's). EDID-derived names earn spaces and
    dots often enough that the quoted form is the normal one."""
    key = str(key)
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return json.dumps(key)


def _dumps(data):
    """Emit TOML for our config shape; there is no writer package to
    buy. A dict value inside a section becomes its own table
    ([section.key]) - the [camera.on] / [camera.off] mode tables are
    the regular case; an EMPTY one is skipped, because a missing
    table and an empty one mean the same thing (the globals)."""
    lines = []
    _emit_table(data, "", lines)
    return "\n".join(lines).rstrip() + "\n"


def _emit_table(table, path, lines):
    """One table's lines in two passes: its own key = value lines
    FIRST, its sub-tables only after - TOML ends a table at its first
    sub-table header, so the passes cannot be intermixed, and every
    key (and dotted-header part) goes through _dumps_key."""
    for key, value in table.items():
        if not isinstance(value, dict):
            lines.append("%s = %s" % (_dumps_key(key),
                                     _format_value(value)))
    for key, value in table.items():
        if not (isinstance(value, dict) and value):
            continue
        header = ".".join(p for p in (path, _dumps_key(key)) if p)
        lines.append("[%s]" % header)
        _emit_table(value, header, lines)
        lines.append("")


# two writers share this path - the UI's debounced save and the
# monitor loop's write_config - so the whole snapshot-and-write holds
# one lock; without it _dumps iterates one writer's live nested dicts
# while the other is mid-mutation
_CFG_LOCK = threading.RLock()


def cfg_lock():
    """Borrow _CFG_LOCK as a context manager: single-writer is the endgame; mutators may adopt this lock; write_config holds it through dump+replace today."""
    return _CFG_LOCK


def write_config(config, path=None):
    """Writes config back to disk (stock comments are not preserved).
    Serialized by _CFG_LOCK: two writers, one desk."""
    path = path or CONFIG_DIR
    if os.path.isdir(path):
        path = os.path.join(path, "config.toml")
    with _CFG_LOCK:
        # snapshot FIRST: _dumps below iterates this copy, never the
        # live nested dicts the writers keep mutating
        try:
            data = copy.deepcopy(
                {k: v for k, v in config.items()
                 if not k.startswith("_")})
        except RuntimeError:
            # a mutator not yet on _CFG_LOCK can still resize a nested
            # dict mid-copy ("dict changed size during iteration"):
            # retry once after a short beat; a second failure raises
            # (the callers already log)
            log.warning("config mutated mid-save; retrying")
            time.sleep(0.05)
            data = copy.deepcopy(
                {k: v for k, v in config.items()
                 if not k.startswith("_")})
        if "camera" in data:
            # in memory the index is ALWAYS a list; on disk a single
            # camera goes back to the bare int (the shape users and the
            # tray have always saved) and several stay a list.
            # name_contains: empty is "" on disk, one match a plain
            # string, several a list. data is the snapshot copy, so
            # these rewrites never reach the live cfg
            cam = data["camera"]
            indexes = normalize_index(cam.get("index", 0))
            cam["index"] = indexes[0] if len(indexes) == 1 else indexes
            names = normalize_name_contains(cam.get("name_contains"))
            cam["name_contains"] = (names[0] if len(names) == 1
                                    else names if names else "")
            # the mode tables: in memory they are {int: mode}; on disk
            # the keys are strings (TOML table keys are) and an EMPTY
            # table is not written at all - a missing table means the
            # same as an empty one (the global applies to every index)
            for table_key in ("on", "off"):
                table = normalize_camera_modes(cam.get(table_key))
                if table:
                    cam[table_key] = {str(k): v for k, v in
                                      table.items()}
                else:
                    cam.pop(table_key, None)
            # data["camera"] is cam itself (snapshot copy): no
            # reassignment needed
        # atomic: the app saves while it runs, and a crash between
        # truncate and finish used to leave a half file (or none). The
        # lock above is what silences the two writers; the pid in the
        # tmp name only keeps crash-litter from colliding across
        # processes (gate note), and the litter gets swept on any
        # failure below
        tmp = path + (".tmp.%d" % os.getpid())
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("# PanelBoss config (rewritten, edit to taste)\n")
                f.write(_dumps(data))
            os.replace(tmp, path)
        except Exception:
            try:
                os.remove(tmp)               # one sweep, every exit
            except OSError:
                pass
            raise
    log.debug(f"config saved to {path}")
    return path


def get_log_level(level=None):
    """Attaches a rotating file handler; the tray app has no console."""
    level = level or os.environ.get("PANELBOSS_LOG_LEVEL", "info")
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    root = logging.getLogger()
    handler = next((h for h in root.handlers
                     if isinstance(h, RotatingFileHandler)
                     and h.baseFilename.endswith("panelboss.log")), None)
    if handler is None:
        handler = RotatingFileHandler(os.path.join(LOG_DIR, "panelboss.log"),
                                      maxBytes=1_000_000, backupCount=3,
                                      encoding="utf-8")
        root.addHandler(handler)
    levels = {"debug": logging.DEBUG, "info": logging.INFO,
              "warning": logging.WARNING}
    root.setLevel(levels.get(level, logging.INFO))
    formatter = logging.Formatter(
        "%(asctime)s %(threadName)-12s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    # pystray's own _mainloop swallows pump exceptions and its logger
    # is the pump's quiet grave - force it into this rotating file.
    # Propagation is on by default; the line is idempotent and says
    # the law out loud.
    for name in ("pystray",):
        logging.getLogger(name).propagate = True
    return root


def migrate_once():
    """One-time pre-rename migration, fail-open and idempotent. The old
    data dir is copied over once (left in place as a backup); the two
    pre-rename scheduled tasks are retired; the legacy Run value is
    replaced by its PanelBoss twin, so the autostart the user chose
    survives the rename. A fresh install (no old dir, no legacy value)
    is a silent no-op."""
    log = logging.getLogger("migrate")
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return
    old_dir = os.path.join(appdata, "ICU-PresenceDetector")
    if os.path.isdir(old_dir):
        new_dir = str(Path(appdata) / APP_NAME)
        if not os.path.exists(os.path.join(new_dir, "config.toml")):
            try:
                shutil.copytree(old_dir, new_dir, copy_function=shutil.copy2,
                                dirs_exist_ok=True)
                log.info("migrate: copied settings from %s (left in place "
                         "as backup)", old_dir)
            except Exception as exc:
                log.warning("migrate: could not copy settings from %s: %s",
                            old_dir, exc)
    # task and Run cleanup run even when the old folder is already
    # gone: orphans outlive folders
    for name in ("ICU-PresenceDetector", "ICU-Presence-PowerRequests"):
        # 0x08000000 = CREATE_NO_WINDOW: no console flash from pythonw.
        # A gone task is a silent no-op; anything else (an access wall:
        # the task is SYSTEM-owned and this process is not elevated)
        # is worth a warning, never a crash - migration never blocks
        # the boot, and an unscheduled hang of schtasks is a crash.
        try:
            proc = subprocess.run(["schtasks", "/Delete", "/F", "/TN", name],
                                  capture_output=True, timeout=30,
                                  creationflags=0x08000000, text=True)
            err = (proc.stderr or "").lower()
            if proc.returncode != 0 and "cannot find" not in err:
                log.warning("migrate: could not delete scheduled task %s: "
                            "%s", name, (proc.stderr or "").strip())
        except Exception as exc:
            log.warning("migrate: could not check scheduled task %s: %s",
                        name, exc)
    try:
        import winreg as reg
        with reg.OpenKey(reg.HKEY_CURRENT_USER,
                         r"Software\Microsoft\Windows\CurrentVersion\Run",
                         access=reg.KEY_READ) as key:
            try:
                stored, _ = reg.QueryValueEx(key, "ICU Presence Detector")
            except OSError:
                stored = None
        if stored is not None:
            # replaced, not deleted: startup.enable() writes the entry
            # for THIS running copy under the new name and retires the
            # legacy twin
            from . import startup
            ok, msg = startup.enable()
            log.info("migrate: Run entry renamed to PanelBoss, %s", msg)
    except Exception as exc:
        log.warning("migrate: could not migrate the legacy Run value: %s",
                    exc)
