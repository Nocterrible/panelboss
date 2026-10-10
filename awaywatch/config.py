"""Config handling.

Reads %APPDATA%\\ICU-PresenceDetector\\config.toml, writing stock defaults
first if it has never been created. Unknown keys are tolerated (forward
compatible); missing keys are backfilled from stock defaults so the state
machine never has to None-check.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    import tomllib  # 3.11+ ships tomllib in the stdlib
except ImportError:
    import tomli as tomllib  # type: ignore

log = logging.getLogger("config")

APP_NAME = "ICU-PresenceDetector"

# the base directory; the environment variable wins so portable installs
# can redirect it next to the repo
appdata = os.environ.get("APPDATA")
if appdata:
    CONFIG_DIR = Path(appdata) / APP_NAME
else:
    CONFIG_DIR = Path.home / ".config" / APP_NAME

CONFIG_DIR = os.environ.get("ICU_PRESENCE_CONFIG_DIR") or str(CONFIG_DIR)

LOG_DIR = os.environ.get("ICU_PRESENCE_LOG_DIR") or str(Path(CONFIG_DIR) / "logs")

# stock defaults, in one place so behavior is documented by code
DEFAULTS = {
    "camera": {
        "index": 0,             # -1 to auto-pick the first camera that opens;
                                # -2 = Windows Hello IR sensor (the optional
                                # whircam bridge: pip install whircam)
        "name_contains": [],    # substring match against device names, wins over index
        "width": 1280,
        "height": 720,
        "warmup_frames": 4,     # auto-exposure needs time to settle before inference
        "mode_on": "boot_per_poll",   # "boot_per_poll" | "always_on", while screens are on
        "mode_off": "always_on",      # while screens are off, LED is invisible anyway
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
                                 # fastest) or a number; unset means auto
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
        "preview_width": 420,   # debug camera panel width in px
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
        merged[section] = dict(stock)
        merged[section].update(config.get(section, {}))
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


def _dumps(data):
    """Emit TOML for our config shape; there is no writer package to buy."""
    lines, tables = [], []
    for key, value in data.items():
        if isinstance(value, dict):
            tables.append("[%s]" % key)
            tables.extend("%s = %s" % (k, _format_value(v))
                          for k, v in value.items())
            tables.append("")
        else:
            lines.append("%s = %s" % (key, _format_value(value)))
    return "\n".join(lines + tables).rstrip() + "\n"


def write_config(config, path=None):
    """Writes config back to disk (stock comments are not preserved)."""
    path = path or CONFIG_DIR
    if os.path.isdir(path):
        path = os.path.join(path, "config.toml")
    data = {k: v for k, v in config.items() if not k.startswith("_")}
    # atomic: the app saves while it runs, and a crash between
    # truncate and finish used to leave a half file (or none)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write("# ICU Presence Detector config (rewritten, edit to taste)\n")
        f.write(_dumps(data))
    os.replace(path + ".tmp", path)
    log.debug(f"config saved to {path}")
    return path


def get_log_level(level=None):
    """Attaches a rotating file handler; the tray app has no console."""
    level = level or os.environ.get("ICU_PRESENCE_LOG_LEVEL", "info")
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    root = logging.getLogger()
    handler = next((h for h in root.handlers
                     if isinstance(h, RotatingFileHandler)
                     and h.baseFilename.endswith("awaywatch.log")), None)
    if handler is None:
        handler = RotatingFileHandler(os.path.join(LOG_DIR, "awaywatch.log"),
                                      maxBytes=1_000_000, backupCount=3,
                                      encoding="utf-8")
        root.addHandler(handler)
    levels = {"debug": logging.DEBUG, "info": logging.INFO,
              "warning": logging.WARNING}
    root.setLevel(levels.get(level, logging.INFO))
    formatter = logging.Formatter(
        "%(asctime)s %(threadName)-12s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    return root
