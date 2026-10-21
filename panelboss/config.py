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
        # CONSENT (redesign law 1): no camera opens until the owner
        # says so - false on a virgin boot keeps a hostile camera
        # world off the whole machine; the load path migrates an
        # ALREADY-SET-UP box to true (labels/bindings/diag record in
        # the file mean the owner configured this app before; the
        # upgrade must not silently stop detection). The duty loop,
        # the tray camera submenu, and the boot scan all read this
        # key; the detection tab's switch owns it (camera_enabled
        # event, state-owned write).
        "enabled": False,
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
        # the degraded fallback cadence, SPLIT by table (owner law,
        # Oct 13 night): while the screens are OFF, an always-on eye
        # is read like you mean it - one second is the default AND
        # the floor. A 1 s cadence is strictly cheaper than the
        # boot-per-poll dance it replaces, because the always_on eye
        # holds the stream open anyway: the read is a read, not an
        # open. The old floor of 5 (a 1 s "fallback" would be
        # always_on with extra steps) is superseded-by-owner: the
        # extra steps ARE the point while the desk is dark.
        "always_fallback_poll_sec": 1,
        # the same gate while the screens are LIT stays where it
        # always was (10 s, floor 5): the owner's law speaks the dark
        # hour; the lit desk's cadence is on_poll_sec's story and
        # the wear guard must not start boot-dancing every second in
        # front of a witness. One constant used to serve both tables
        # - the law splits it honestly rather than redefining a key
        # the dark story named
        "always_fallback_poll_on_sec": 10,
        # camera identity (v1 wizard): keyed on the PnP InstanceId,
        # NOT the index - indexes drift on replugs (measured Oct 12),
        # the instance path does not. labels maps instance -> the
        # user's name; hidden lists instances the picker and the
        # roster menu lines suppress (the engine still honors a
        # hidden index already on duty - its row wears a badge).
        # bindings is the wizard's twin answer: instance -> scan
        # index, a HUMAN assertion that outranks every name guess
        # (identity_map applies it last); a bind to an instance that
        # no longer exists maps nothing, like a hidden one
        "labels": {},
        "hidden": [],
        # instances the owner explicitly brought back at the hidden
        # list's per-device "show" (amendment 2): un-hidden AND
        # sticky - the diagnostic pre-mark never applies to a shown
        # identity, forever, because a sometimes-plugged camera the
        # human chose to see must survive every later sweep. A wipe
        # (unhide all) does not write this; a decision does
        "shown": [],
        "bindings": {},
        # the scan's diagnostic verdict, written by the state loop when
        # a sweep ran (camera_diag event - the UI never writes the toml
        # itself): {"at": epoch, "indices": the openable indexes the
        # sweep measured, "noimg": the subset that served no frame in
        # 15 s}. The scan re-probes when this set CHANGES vs its own;
        # an absent key reads {} like bindings did - no migration
        "diag": {},
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
        "off_poll_sec": 3,           # arms the FIRST re-poll after the
                                     # panels go dark; once that deadline
                                     # is due, _off_phase never re-arms -
                                     # a held stream is then read every
                                     # loop tick (~0.2 s), which is the
                                     # point of paying for the open (LED
                                     # is already off, cam stays open;
                                     # the dark-hour cadence a DEGRADED
                                     # eye obeys is always_fallback_
                                     # poll_sec, default 1 s)
        "re_off_grace_sec": 30,      # budget a monitor gets while it is awake with nobody in front of it
    },
    "recovery": {
        # the law wins the enum's judgment call (wave B): wake_policy
        # is the auto re-off FEATURE in a knob's clothes - re_off lets
        # the app re-darken a screen on its own word, and a virgin box
        # must not re-off what the user never asked it to manage.
        # Stock is therefore the hands-off arm; re_off is a choice,
        # never a default that self-runs.
        "wake_policy": "leave_on",   # "re_off" | "leave_on": what to do when the display is
                                     # back on (key press, mouse jiggle) but nobody is in front of it
        "leave_on_grace_sec": 180,   # ignored unless wake_policy is "leave_on"
        "wake_burst_count": 2,       # this many unexpected wakes within the window below ...
        "wake_burst_window_sec": 120,  # ... pauses auto re-off (the camera probably
                                       # slipped and is looking at a wall)
    },
    "guards": {
        # wave B (the owner's virgin launch): a toggle, so off. It
        # WITHHOLDS the app's core broadcast whenever a fullscreen app
        # owns the display - a feature the desk must ask for, not a
        # default that silently suppresses the darkening.
        "fullscreen": False,    # do not send the off broadcast while a fullscreen game owns the display,
                                # the message is swallowed by the swapchain
    },
    "power": {
        # the default-off law, wave B (the owner's virgin launch): the
        # hold pair renders ON in the screenshot because stock says so
        # - stock is dark now; a fresh box lets Windows own its timers
        # until the owner touches the switches.
        "hold_display": "off",   # 'off' | 'on' | 'present' (the third state,
                                 # Oct 21): while the app watches a lit desk
                                 # it holds the plan's display timeout off -
                                 # a still person reading a page is never
                                 # timed out; 'present' holds ONLY while the
                                 # camera's verdict says a person is here
        "hold_sleep": "off",     # ...and the sleep timeout, same three
                                 # words. The dark watcher wants it once it
                                 # runs at all - but the watcher is
                                 # consent-gated (camera.enabled): a box
                                 # that never opted in sleeps when its
                                 # plan says so
        "skip_camera_when_blocked": False,  # if another app already holds the
                                            # display awake, the camera does
                                            # not poll to defend it. Off
                                            # stock: True makes the duty loop
                                            # run powercfg on its own every
                                            # poll_sec - a feature, not a
                                            # shape (the assistant is already
                                            # opt-in; this gate stays off
                                            # beside it and the loop asks
                                            # nobody)
        "restore_windows": False,    # monitors that unplug themselves on
                                     # standby make Windows re-lay every
                                     # window when they return: the desk is
                                     # remembered at screens-off and put
                                     # back after any wake (see wm.py). It
                                     # MOVES the owner's windows - behavior
                                     # to be wanted, never to be stock
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
        # the DESKTOP-COLOR lever (amendment 8, the power-options side):
        # monitor short -> true/false, the HDR state the panel wears
        # when nobody games - applied by the same desktop pass that
        # returns the desktop rate. An ABSENT entry (or "keep" in the
        # menu) is the absence of a rule, never a false: the owner's
        # color state is nobody's business unless they set this
        "hdr": {},
        "power_plan": "",        # name fragment or guid swapped in when a
                                 # game starts ('' = hands off the plan)
    },
    # the auto-switch tiers (amendment 8): per PHYSICAL PANEL, keyed
    # by the same EDID model identity the profiles use (slots shuffle,
    # the model does not). Default empty = every panel "off" - the
    # default-off law: nothing here may surprise a virgin boot. The
    # watcher that acts on these lives in state/_hdrwatch.py
    "hdr": {
        "auto": {},              # model -> "off"|"video"|"content":
                                 # video = PDH video-engine activity
                                 # (a decoder is playing something);
                                 # content = the mpv pipe says the
                                 # playing video IS HDR (bt.2020+PQ)
        "mpv_pipe": r"\\.\pipe\mpv-video",   # the player-ipc probe
                                 # target (the string is pinned equal
                                 # to _videostats.MPV_PIPE_DEFAULT in
                                 # the offline suite - one truth); an
                                 # mpv started --input-ipc-server=
                                 # <this> answers video-params
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
    "away": {
        "mode": "off",          # "off" = the stock SC_MONITORPOWER broadcast
                                # (today's behavior); "dim" = play dead
                                # instead of asleep: the panels stay awake
                                # and the app paints the dark - blackout
                                # rows get a black overlay, dim rows lose
                                # HDR and drop to dim_level (no cold ODM
                                # re-enumeration on wake)
        "monitors": {},         # EDID short -> {"blackout": bool,
                                # "off": bool, "offdisc": bool}
                                # (normalize's shape; the loader also
                                # takes the bare bool and a bare
                                # "blackout"/"dim"/"off"/"offdisc"
                                # string, "off-disc" included). The
                                # off sub-mode is YOUNG: rows without
                                # the key simply answer False (no
                                # migration it must perform). True
                                # "off" = the real power opcode
                                # (VCP 0xD6) through wm/_bright.py's
                                # door - the panel IS the overlay; a
                                # write refused after the budget
                                # degrades that row to blackout with
                                # the confession on its status word
                                # (the PROBE LAW's two honest halves,
                                # AUDIT-PUNCHLIST 60121ed). True
                                # "offdisc" = the DISCONNECT through
                                # wm/_sdc.py - the path retracted at
                                # the adapter, the state lives in
                                # Windows' own display store (one
                                # door deeper than this app:
                                # Settings -> Display is always the
                                # recovery, the boot belt reclaims
                                # rows this app configured). In dim
                                # mode an absent row is a dim row -
                                # the migration promise, and the
                                # honest default for a panel that
                                # joined after the config was written
        "dim_level": 10,        # brightness %% for the dim rows, clamped
                                # 1..40 - measured law (wm/_bright.py):
                                # some panels accept brightness writes
                                # and never obey them; those degrade to
                                # blackout with a confession, never silent
        "lock": False,          # lock-on-away: a REAL dim engage (never
                                # a preview) also runs LockWorkStation
                                # once at least one row went dark -
                                # the panels wake to the LOCK SCREEN,
                                # not to somebody's desktop. False is
                                # the law's floor: a spell that grabs
                                # the session needs asking first
    },
    "hider": {
        "on": False,              # the faux taskbar strip is consent,
                                  # like everything that touches the
                                  # desk: absent section = dark, no
                                  # migration it must perform
        "hold_sec": 3,            # how long the cursor must stay out
                                  # of EVERY bar zone before a withdrawn
                                  # strip returns; clamped 1..30
        "reveal": "hovered",      # "hovered" = only the bar the cursor
                                  # entered; "all" = every enabled bar
                                  # withdraws together (a multi-monitor
                                  # owner switching apps across screens)
        "monitors": {},           # {short: bool} - per-panel opt-in;
                                  # default ALL off (burn-in is the OLED
                                  # problem; even OLED rows are opt-in)
    },
    "jog": {
        "on": False,              # panel refresh is consent, like the
                                   # hider: absent section = dark, nothing
                                   # nudges or washes until opted in
        "monitors": {},           # {short: bool} - per-panel opt-in,
                                   # default ALL off (the same law as the
                                   # hider's rows)
        "step_px": 2,             # micro-jog nudge size in px; clamped 1..8
        "cycle_min": 30,          # minutes between ring steps; clamped 5..180
        "mode": "shuffle",        # "shuffle" | "wash"; a word this app has
                                   # not heard warns and folds to shuffle
                                   # (normalize_hider's honesty, mirrored)
    },
    "dimmer": {
        "on": False,              # background dimming is consent: absent
                                   # section = dark, the desk dims for no one
        "monitors": {},           # {short: bool} - per-panel opt-in, the
                                   # same law as the hider's rows
        "always": {},             # {short: bool} - the SUB-MODE rail
                                   # (owner ruling, Oct 15): an opted row
                                   # that also says always dims without
                                   # the idle wait, bowing to the
                                   # foreground and the audible
                                   # exemptions; false is the plain law
        "idle_sec": 60,           # input stillness before veils may birth;
                                   # clamped 0..60 (silent clamp rails;
                                   # 0 = the rail reaches zero and means
                                   # it, the ramp's law - Oct 15 UAT;
                                   # the ceiling moved 300 -> 60 on the
                                   # owner's timer law, Oct 16)
        "ramp_sec": 8,            # the fade-out after input returns;
                                   # clamped 0..60 (0 = the drop is
                                   # immediate, a ruling not an accident)
        "fade": False,            # the PLAIN veil's lift style (owner,
                                   # Oct 16: "60 s veil lift is dumb"):
                                   # default OFF - input returns, the
                                   # veil is GONE this tick; true opts
                                   # the plain field into the ramp
                                   # family (the theater's own "fade"
                                   # key is the sibling below)
        "level": 20,              # veil darkness in percent; clamped
                                   # 10..90 (Oct-15 OLED ruling: 45 was
                                   # aggressive on a dark desk)
        "levels": {},             # {EDID short: int} - the per-panel
                                   # veil percent (owner, Oct 16, the
                                   # ADDON entry absorbed: panels answer
                                   # differently - 49%% goes DARK on
                                   # DELA283 and is barely a tint on
                                   # IOC912B); a row overrides
                                   # [dimmer].level for ITS panel,
                                   # clamped to the same rails; an
                                   # unlisted panel follows the global
        "apps": {},               # {exe-basename-lower: bool} - the
                                   # exclusion table (bool rows, junk
                                   # warn+drop, unknown kept)
        "bound": None,            # the [mods, vk] pair the card binds;
                                   # None = unbound by DEFAULT (owner
                                   # law: no stolen chord before
                                   # consent); the arm in dimmer.py does
                                   # the RegisterHotKey against the
                                   # display pump's window
        "input_pump": True,       # trust ONLY the app's raw-input
                                # pump for every idle rail (the Oct-20 wave;
                                #   the owner overrode the default-off law for
                                #   THIS key: default-on plus fail-open means
                                #   the worst case equals the old behavior,
                                #   which is what justified the override). false
                                #   is the stock GetLastInputInfo clock verbatim;
                                #   true routes the idle seams through
                                #   inputtruth - zero-travel device liars
                                #   (stuck-macropad firmware, jigglers, KVM
                                #   chatter) re-stamp that clock forever and
                                #   the pump's 3 px dead zone is deaf to
                                #   exactly those. Restart-required like the
                                #   rest of this section: flip it, relaunch.
                                #   The OFF-PHASE WAKE additionally hears
                                #   injection through the exemption when the
                                #   stream is silent (see inputtruth's
                                #   docstring - the away/theater rails never
                                #   take the exemption).
    },
    "videodim": {
        "on": False,               # the dim-around-the-playing-video
                                   # consent, default-off like every
                                   # other rail: off = no file reads,
                                   # nothing. The geometry now comes
                                   # from the companion EXTENSION
                                   # (native messaging): the extension
                                   # measures the video, the local host
                                   # writes the app's doorway file, the
                                   # eye reads it. The debug-flag route
                                   # and its launch-with-flag families
                                   # (enabled / flag_families / sites)
                                   # are RETIRED and removed (Oct 16):
                                   # the debug port handed any local
                                   # process full CDP, and a stale key
                                   # a pre-ruling config carries simply
                                   # parses away (normalize_videodim
                                   # answers the new shape and drops
                                   # the old words, never surprises).
        "min_rect_px": 200000,     # the ad-banner line of defense: a
                                   # "video" smaller than this (in
                                   # PHYSICAL px) is not a video;
                                   # clamped 0..4_000_000 (the silent
                                   # rails, the hider's hold_sec law)
        "grace_s": 3,              # how stale the last good rect may
                                   # ride before the eye calls it gone
                                   # (a vanished rect is a stopped
                                   # video: the dimmer's ramp retracts
                                   # the frame); clamped 0..60
        "idle_sec": 15,            # THE AUTOMATIC LANE'S CONJUNCTION
                                   # (owner, Oct 16: "same as window
                                   # dimming"): the theater veil frames
                                   # the video only when a video is
                                   # PLAYING AND the desk input has
                                   # been still this long - the
                                   # dimmer's idle_sec sibling, one
                                   # knob, pointer/keyboard only (a
                                   # film's SOUND never lifts the
                                   # theater veils - sound is the
                                   # movie's whole context). 15 s is
                                   # the honest default: the mouse
                                   # goes still while the intro runs,
                                   # and a quick scrub doesn't black
                                   # the screen; 1 s is the rail's FLOOR
                                   # (owner, Oct 16: at 0 the veil never
                                   # lifts - rect updates stop re-
                                   # birthing and the ring sticks),
                                   # clamped 1..30 (the owner's timer
                                   # law: the 5 min ceiling was dead
                                   # pixels for a theater veil). The
                                   # click lane (the demoted
                                   # test-the-geometry gesture) never
                                   # waits on this - it measures
                                   # immediately.
        "level": 20,               # the theater pieces' OWN darkness
                                   # (owner, Oct 16): the four dark
                                   # pieces draw at THIS percent, not
                                   # the idle dimmer's [dimmer].level -
                                   # a movie veil can be darker (or
                                   # lighter) than the plain idle veils.
                                   # Sibling of the dimmer's level,
                                   # clamped 10..90 like it.
         "fade": False,             # retract style (owner, Oct 16: "I
                                    # don't like the fade, so I won't use it -
                                    # but having the option is the right
                                    # move): default OFF - input returns,
                                    # the frame is GONE this tick; true
                                    # opts into the ramp family (one-tick
                                    # hold, retract over the dimmer's
                                    # ramp).
        "monitors": {},             # {EDID short: {"on": bool, "level":
                                    # int}} - the per-panel theater rows
                                    # (owner, Oct 16): a row's panel
                                    # wears a FULL-FIELD theater veil
                                    # while the conjunction holds, at
                                    # its own level (absent level =
                                    # follow [videodim].level); on =
                                    # false strips the frame from the
                                    # panel its OWN video sits on (the
                                    # plain veils proceed there). An
                                    # absent row is the legacy shape:
                                    # only the video's panel is framed.
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
    # the release-boundary stamp (wave B): the file's own answer for
    # itself. Its ABSENCE marks a pre-law file to the one-shot load
    # migration below; the first loop-owned save lands it, which makes
    # the migration's shape unreachable - the same disarming as the
    # amendment 2 reset, counted where it can be seen.
    "meta": {
        "defaults": 2,           # 1 = the amendment 2 world, 2 = the default-off law, finished
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
    # the tri-state hold pair (the 'while present' wave, Oct 21): see
    # the 'hold' arm of _coerce - the booleans of the pre-wave files
    # read on/off and stay valid, junk fails to on
    ("power", "hold_display", "hold", ("on", "off", "present")),
    ("power", "hold_sleep", "hold", ("on", "off", "present")),
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
    ("camera", "shown", "listtype", []),
    ("camera", "bindings", "dicttype", {}),
    ("camera", "diag", "dicttype", {}),
    # the amendment 8 maps: per-monitor color state (gaming.hdr: real
    # booleans - TOML has no null, so "keep" is the ABSENCE of a key,
    # never a written false-lie) and the auto tiers (hdr.auto: an
    # absent model reads as the law's default, off; a present value
    # must name one of the tiers, case-insensitive on the way in)
    ("gaming", "hdr", "boolmap", {}),
    ("hdr", "auto", "tiermap", {}),
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
    if kind == "hold":
        # the tri-state hold rows ('while present', owner Oct 21): the
        # booleans of the pre-wave files STAY VALID and mean on/off (the
        # owner's live rows survive the upgrade behavior-identical); the
        # words are the file's own enum texture (wake_policy taught it);
        # junk fails to 'on' - the one hold answer that cannot lose a
        # watching desk to a plan timeout - and the warning names it.
        if value is True:
            return True, "on", ""
        if value is False:
            return True, "off", ""
        v = value.strip().lower() if isinstance(value, str) else value
        if v in bound:
            return True, v, ""
        return False, bound[0], "expected on/off/present"
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
    if kind in ("boolmap", "tiermap"):
        # the amendment 8 per-monitor maps, same cleaning law as
        # hzmap: a junk map goes to stock with a warning, a bad
        # ENTRY is dropped by name and the survivors stay. boolmap
        # values are real booleans only (a written "true"/"yes"
        # string is a hand-edit someone must mean loudly - dropped);
        # tiermap values are the three tier words.
        if value is None:
            return True, None, ""
        if not isinstance(value, dict):
            return False, copy.deepcopy(stock), "not a monitor map"
        if not value:
            return True, value, ""     # {} is legal: nothing claimed
        cleaned = {}
        for monitor, got in value.items():
            if kind == "boolmap":
                good = isinstance(got, bool)
            else:
                good = isinstance(got, str) \
                    and got.strip().lower() in ("off", "video", "content")
                if good:
                    got = got.strip().lower()
            if good:
                cleaned[monitor] = got
            else:
                log.warning("config [%s].%s: dropping %s=%r (%s)",
                            section, key, monitor, got,
                            "must be true or false" if kind == "boolmap"
                            else "must be off/video/content")
        if not cleaned:
            log.warning("config [%s].%s: no usable entries left after "
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
            # every clean load. The line names the COERCED value, not
            # the stock: for every rule but 'hold' the failure fallback
            # IS the stock, but the hold rows fail to 'on' - and an
            # honest warning says what landed (the section's honest word
            # is the point of the line).
            if section_cfg.get(key) != stock:
                log.warning("config [%s].%s = %r is unusable (%s); "
                            "using %r", section, key, section_cfg.get(key),
                            reason, coerced)
        section_cfg[key] = coerced


def hold_state(value):
    """One hold row's value in its canonical word ('the migration table'
    as a function): the pre-wave booleans read on/off and stay valid,
    the tri-state words ride through (case/edge tolerant), anything
    else - a value that never saw the load boundary, a live dict a
    harness scribbled on - is off's neighbor. The state machine and the
    UI both read THIS, so the table lives once."""
    if value is True:
        return "on"
    if value is False:
        return "off"
    v = value.strip().lower() if isinstance(value, str) else value
    return v if v in ("on", "off", "present") else "off"


def hold_present_available(camera_cfg):
    """THE GRAY-OUT LAW AS DATA (owner Oct 21): the 'while present'
    choice is offered only while camera detection stands consented and
    on - [camera].enabled is the consent door's key, and never
    consented reads false, the same key the detection tab's switch
    owns. The UI grays the segment from this (gray, never hidden);
    the suite tests the flag without a widget."""
    return bool((camera_cfg or {}).get("enabled"))


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


AWAY_MODES = ("off", "dim")
AWAY_ROW_MODES = ("blackout", "dim", "off", "offdisc")   # the per-row
#    sub-modes; offdisc = the DISCONNECT flavor (wm/_sdc.py: retracts
#    at the adapter, comes back as a replug, works regardless of
#    firmware) - the pair shape grows a third bool, young like "off"
#    was: absent answers False, no migration it must perform
DIM_LEVEL_FLOOR = 1                 # the dim sub-mode never means black
DIM_LEVEL_CEIL = 40                 # past this the fake-off is a rumor


def _fold_row_mode(v):
    """A row's mode-word in its triple shape; the off-disc alias
    folds here (the hyphen is a spelling, not a sub-mode) so both
    the string branch and the dict branch take it identically."""
    v = str(v or "").strip().lower().replace("-", "")
    return {"blackout": v == "blackout", "off": v == "off",
            "offdisc": v == "offdisc"}


def normalize_away(value):
    """[away] in its in-memory shape: {mode, monitors, dim_level, lock}.
    A mode the engine has never heard of warns and falls back to the
    stock "off" (the file's other answers still stand); dim_level
    clamps to 1..40 (a 0%% "dim" is a blackout that lied about itself,
    a 90%% one is nobody dimming anything); lock is a bool with the
    mode key's honesty (a bad value warns naming short and value, and
    folds to False - the default-off law: a spell that locks the
    session is consent, not a rumor); monitor rows accept the
    bare-bool shorthand (A = true means {"blackout": true}) and drop
    malformed rows with a warning naming them; a RETIRED
    off_after_min key (the stage-two experiment, Oct 17-19: the OS
    screen-off timer owns the disconnect now, with the driver
    holding the device lifetime) warns naming itself and is
    dropped."""
    value = value if isinstance(value, dict) else {}
    mode = value.get("mode", "off")
    if mode not in AWAY_MODES:
        log.warning("away mode %r is unknown; the screens go off as "
                    "they always did", mode)
        mode = "off"
    lock = value.get("lock", False)
    if not isinstance(lock, bool):
        log.warning("away lock %r is not a bool; the away spell will "
                    "not lock the workstation", lock)
        lock = False
    try:
        level = int(value.get("dim_level", 10))
    except (TypeError, ValueError):
        level = 10
    level = max(DIM_LEVEL_FLOOR, min(DIM_LEVEL_CEIL, level))
    rows = {}
    raw = value.get("monitors")
    if isinstance(raw, dict):
        for short, row in raw.items():
            short = str(short).strip()
            if not short:
                continue
            if isinstance(row, bool):
                rows[short] = {"blackout": row, "off": False,
                               "offdisc": False}
            elif isinstance(row, str) and \
                    row.strip().lower().replace("-", "") in AWAY_ROW_MODES:
                rows[short] = _fold_row_mode(row)
            elif isinstance(row, dict) and ("blackout" in row or
                                            "off" in row or
                                            "offdisc" in row or
                                            "mode" in row):
                v = str(row.get("mode") or "").strip().lower() \
                    .replace("-", "")
                if "mode" in row and v not in AWAY_ROW_MODES:
                    # the dict branch answers with the SAME honesty the
                    # string branch shows a bad name (gate finding 5a):
                    # warn, fold to dim, name the row
                    log.warning("away monitor %r: mode %r is not a known "
                                "sub-mode; the monitor keeps the dim "
                                "default", short, row.get("mode"))
                    rows[short] = {"blackout": False, "off": False,
                                   "offdisc": False}
                elif v in AWAY_ROW_MODES:
                    rows[short] = _fold_row_mode(v)
                else:
                    rows[short] = {"blackout": bool(row.get("blackout")),
                                   "off": bool(row.get("off")),
                                   "offdisc": bool(row.get("offdisc"))}
            else:
                log.warning("away monitor %r: %r is not an away row; "
                            "the monitor keeps the dim default", short,
                            row)
    if "off_after_min" in value:
        log.warning("away off_after_min is gone (Oct 19): Windows' own "
                    "screen-off timer does the deep disconnect now - "
                    "the key is ignored and leaves the file at the "
                    "next save")
    return {"mode": mode, "monitors": rows, "dim_level": level,
            "lock": lock}


HIDER_REVEALS = ("hovered", "all")   # the strip's reveal scopes
HOLD_SEC_FLOOR = 1                   # below a second nobody reads
HOLD_SEC_CEIL = 30                   # above half a minute it is a rumor
HOLD_SEC_DEFAULT = 3


def normalize_hider(value):
    """[hider] in its in-memory shape: {on, hold_sec, reveal, monitors}.
    The away section's honesty laws, mirrored: a bad on warns and folds
    to False (the default-off law - strips are painted windows until a
    user says otherwise), a bad reveal word warns naming itself and
    folds to hovered (the label-vs-word lesson of the preview seam: a
    word this app has not heard never silently selects a leg), hold_sec
    clamps to the rails, and monitor rows are plain bools - unknown
    shorts warn but KEEP (they name panels that may come back; the
    strip for an absent panel is simply never painted)."""
    value = value if isinstance(value, dict) else {}
    on = value.get("on", False)
    if not isinstance(on, bool):
        log.warning("hider on %r is not a bool; the taskbar stays as "
                    "Windows left it", on)
        on = False
    reveal = value.get("reveal", "hovered")
    if reveal not in HIDER_REVEALS:
        log.warning("hider reveal %r is not one of %s; the strip will "
                    "only withdraw under the cursor's own bar",
                    reveal, ", ".join(HIDER_REVEALS))
        reveal = "hovered"
    try:
        hold = int(value.get("hold_sec", HOLD_SEC_DEFAULT))
    except (TypeError, ValueError):
        hold = HOLD_SEC_DEFAULT
    hold = max(HOLD_SEC_FLOOR, min(HOLD_SEC_CEIL, hold))
    rows = {}
    raw = value.get("monitors")
    if isinstance(raw, dict):
        try:
            live = set(_live_shorts())
        except Exception:            # a desk that cannot enumerate keeps
            live = None              # every saved row silently
        for short, row in raw.items():
            short = str(short).strip()
            if not short:
                continue
            if isinstance(row, bool):
                if live is not None and short not in live:
                    log.info("hider monitor %r names no panel on this "
                             "desk; the row is kept for when it returns",
                             short)
                rows[short] = row
            else:
                log.warning("hider monitor %r: %r is not a bool; the "
                            "row is dropped", short, row)
    return {"on": on, "hold_sec": hold, "reveal": reveal,
            "monitors": rows}


JOG_MODES = ("shuffle", "wash")     # the refresh's two legs
JOG_STEP_FLOOR = 1                  # one pixel is the smallest honest nudge
JOG_STEP_CEIL = 8                   # past eight it is a window manager, not a jog
JOG_STEP_DEFAULT = 2
JOG_CYCLE_FLOOR = 5                 # below five minutes a shift is a flicker
JOG_CYCLE_CEIL = 180                # past three hours the edge has already aged
JOG_CYCLE_DEFAULT = 30


def normalize_jog(value):
    """[jog] in its in-memory shape: {on, monitors, step_px, cycle_min,
    mode}. normalize_hider's honesty laws, mirrored exactly: a bad on
    warns and folds to False (the default-off law - nothing moves until a
    user says otherwise), a bad mode word warns naming itself and folds to
    shuffle (the label-vs-word lesson: a word this app has not heard never
    silently selects a leg), step_px and cycle_min clamp to the rails, and
    monitor rows are plain bools - unknown shorts warn but KEEP (they name
    panels that may come back; the jog for an absent panel is simply never
    applied).

    One documented divergence from normalize_hider, on purpose: the
    non-bool row warning names its OWN section ("jog monitor"), never
    hider's sentence - the belt must say which feature dropped the row.
    """
    value = value if isinstance(value, dict) else {}
    on = value.get("on", False)
    if not isinstance(on, bool):
        log.warning("jog on %r is not a bool; the panels keep their "  
                    "pixels exactly where Windows left them", on)
        on = False
    mode = value.get("mode", "shuffle")
    if mode not in JOG_MODES:
        log.warning("jog mode %r is not one of %s; the refresh will "
                    "micro-jog instead", mode, ", ".join(JOG_MODES))
        mode = "shuffle"
    try:
        step = int(value.get("step_px", JOG_STEP_DEFAULT))
    except (TypeError, ValueError):
        step = JOG_STEP_DEFAULT
    step = max(JOG_STEP_FLOOR, min(JOG_STEP_CEIL, step))
    try:
        cyc = int(value.get("cycle_min", JOG_CYCLE_DEFAULT))
    except (TypeError, ValueError):
        cyc = JOG_CYCLE_DEFAULT
    cyc = max(JOG_CYCLE_FLOOR, min(JOG_CYCLE_CEIL, cyc))
    rows = {}
    raw = value.get("monitors")
    if isinstance(raw, dict):
        try:
            live = set(_live_shorts())
        except Exception:            # a desk that cannot enumerate keeps
            live = None              # every saved row silently
        for short, row in raw.items():
            short = str(short).strip()
            if not short:
                continue
            if isinstance(row, bool):
                if live is not None and short not in live:
                    log.info("jog monitor %r names no panel on this "
                             "desk; the row is kept for when it returns",
                             short)
                rows[short] = row
            else:
                log.warning("jog monitor %r: %r is not a bool; the "
                            "row is dropped", short, row)
    return {"on": on, "monitors": rows, "step_px": step,
            "cycle_min": cyc, "mode": mode}


DIMMER_IDLE_FLOOR = 0            # the rail reaches zero and MEANS it (the
                                 # ramp's law, extended by the Oct-15 UAT:
                                 # "dim right away" is a choice, not an
                                 # accident - at 0 the veil births on the
                                 # first beat, the foreground and audible
                                 # exemptions still bow to it)
DIMMER_IDLE_CEIL = 60            # 60 s, owner timer law (Oct 16: the
                              # 5 min the Oct-15 ruling left was still
                              # dead pixels for an idle veil - the
                              # slider's 5 min max became 60 s): past
                              # a minute of stillness the veil is a
                              # done deal; a hand-set larger value
                              # clamps honest at the ceiling
DIMMER_IDLE_DEFAULT = 60
DIMMER_RAMP_FLOOR = 0            # the rail reaches zero and MEANS it: at
                                 # 0 the drop is immediate (owner ruling,
                                 # Oct 15 - the Veils fade guards this
                                 # case by name, no /ramp surprise)
DIMMER_RAMP_CEIL = 60            # past a minute the return is an apology
DIMMER_RAMP_DEFAULT = 8
DIMMER_LEVEL_FLOOR = 10          # thinner than this the veil is a rumor
DIMMER_LEVEL_CEIL = 90           # darker than this the desk is the screen
DIMMER_LEVEL_DEFAULT = 20        # the Oct-15 OLED ruling: 45 was
                                 # aggressive; the rails did not move


def normalize_dimmer(value):
    """[dimmer] in its in-memory shape: {on, monitors, always,
    idle_sec, ramp_sec, level, fade, levels, apps, bound}. normalize_jog's
    honesty, mirrored:
    a bad on warns and folds to False (the default-off law), the rails
    clamp in silence (the hider's hold_sec law - a slider that clamps
    must not confess at load), and the row tables fail open: a
    non-bool row warns naming itself and is dropped, unknown keys are
    kept (a panel or an app that may come back). 'bound' is the
    [mods, vk] pair the card bound - a two-sequence with
    int-coercible members round-trips to [int, int] (the UI's ACTUAL
    write shape; a hand-edited "2" earns the same courtesy); any other
    junk warns and folds to None (unbound is the only state besides a
    stored pair the card can promise honestly)."""
    value = value if isinstance(value, dict) else {}
    on = value.get("on", False)
    if not isinstance(on, bool):
        log.warning("dimmer on %r is not a bool; the desk dims for no "
                    "one", on)
        on = False
    try:
        idle = int(value.get("idle_sec", DIMMER_IDLE_DEFAULT))
    except (TypeError, ValueError):
        idle = DIMMER_IDLE_DEFAULT
    idle = max(DIMMER_IDLE_FLOOR, min(DIMMER_IDLE_CEIL, idle))
    try:
        ramp = int(value.get("ramp_sec", DIMMER_RAMP_DEFAULT))
    except (TypeError, ValueError):
        ramp = DIMMER_RAMP_DEFAULT
    ramp = max(DIMMER_RAMP_FLOOR, min(DIMMER_RAMP_CEIL, ramp))
    try:
        level = int(value.get("level", DIMMER_LEVEL_DEFAULT))
    except (TypeError, ValueError):
        level = DIMMER_LEVEL_DEFAULT
    level = max(DIMMER_LEVEL_FLOOR, min(DIMMER_LEVEL_CEIL, level))
    # fade: the PLAIN veil's lift style (owner, Oct 16: "60 s veil lift
    # is dumb"). STRICT bool, absent/junk = False = the veil is GONE the
    # tick input returns; true opts the plain field into the ramp
    # family. Junk warns like `on` does - it is a behavior switch, not
    # a rail. The videodim fade block below is the twin, word for word
    # in tone: two owners' words, two keys, one shape.
    fade = value.get("fade", False)
    if not isinstance(fade, bool):
        log.warning("dimmer fade %r is not a bool; the veil drops "
                    "without a fade", fade)
        fade = False
    # input_pump: the Oct-20 clock choice (the owner's default-on
    # override of the default-off law - fail-open is the insurance
    # that justified it, so junk folds to the DEFAULT, not to off).
    # STRICT bool like fade; the restart law covers the flip.
    pump = value.get("input_pump", True)
    if not isinstance(pump, bool):
        log.warning("dimmer input_pump %r is not a bool; the pump "
                    "stays on (fail-open is the whole desk)", pump)
        pump = True
    rows = {}
    raw = value.get("monitors")
    try:
        live = set(_live_shorts())
    except Exception:                # a desk that cannot enumerate keeps
        live = None                  # every saved row silently
    if isinstance(raw, dict):
        for short, row in raw.items():
            short = str(short).strip()
            if not short:
                continue
            if isinstance(row, bool):
                if live is not None and short not in live:
                    log.info("dimmer monitor %r names no panel on this "
                             "desk; the row is kept for when it returns",
                             short)
                rows[short] = row
            else:
                log.warning("dimmer monitor %r: %r is not a bool; the "
                            "row is dropped", short, row)
    # [dimmer.always] normalizes under the EXACT same law as the
    # monitors table (Oct-15 sub-mode): bool rows only, junk warns and
    # drops, a panel that is off the desk now is kept for its return
    always = {}
    raw = value.get("always")
    if isinstance(raw, dict):
        for short, row in raw.items():
            short = str(short).strip()
            if not short:
                continue
            if isinstance(row, bool):
                if live is not None and short not in live:
                    log.info("dimmer always %r names no panel on this "
                             "desk; the row is kept for when it returns",
                             short)
                always[short] = row
            else:
                log.warning("dimmer always %r: %r is not a bool; the "
                            "row is dropped", short, row)
    apps = {}
    raw = value.get("apps")
    if isinstance(raw, dict):
        for name, row in raw.items():
            name = str(name).strip().lower()
            if not name:
                continue
            if isinstance(row, bool):
                apps[name] = row
            else:
                log.warning("dimmer app %r: %r is not a bool; the "
                            "row is dropped", name, row)
    # [dimmer.levels]: the per-panel veil percent (owner, Oct 16, the
    # ADDON absorbed - panels answer differently). {short: int} clamped
    # to the level rails; a junk ENTRY is dropped in silence (the rail
    # law - a clamp must not confess at load), a non-dict TABLE warns
    # once naming itself. An unlisted panel follows [dimmer].level:
    # absent is EXACTLY today's behavior.
    levels = {}
    raw = value.get("levels")
    if raw is not None:
        if not isinstance(raw, dict):
            log.warning("dimmer levels %r is not a table; every panel "
                        "keeps the global veil", raw)
        else:
            for short, row in raw.items():
                short = str(short).strip()
                if not short:
                    continue
                try:
                    lv = int(row)
                except (TypeError, ValueError):
                    continue
                levels[short] = max(DIMMER_LEVEL_FLOOR,
                                    min(DIMMER_LEVEL_CEIL, lv))
    bound = value.get("bound")
    if isinstance(bound, (list, tuple)) and len(bound) == 2:
        try:
            bound = [int(bound[0]), int(bound[1])]
        except (TypeError, ValueError):
            log.warning("dimmer bound %r holds no two ints; the "
                        "hotkey is unbound", bound)
            bound = None
    elif bound is not None:
        log.warning("dimmer bound %r is not a [mods, vk] pair; the "
                    "hotkey is unbound", bound)
        bound = None
    return {"on": on, "monitors": rows, "always": always,
            "idle_sec": idle, "ramp_sec": ramp, "level": level,
            "fade": fade, "levels": levels,
            "apps": apps, "bound": bound, "input_pump": pump}


VIDEODIM_MIN_FLOOR = 0             # a zero min means "trust every
VIDEODIM_MIN_CEIL = 4_000_000      #   rect" - legal, not a mistake
VIDEODIM_GRACE_FLOOR = 0
VIDEODIM_GRACE_CEIL = 60
VIDEODIM_IDLE_FLOOR = 1            # the "veil after stillness" rail (the
                                    #   dimmer's idle_sec sibling): the
                                    #   owner's 1 s FLOOR (Oct 16: at 0
                                    #   the veil NEVER lifts, so rect
                                    #   updates stop re-birthing and the
                                    #   ring sticks at its first geometry
                                    #   - the sticky-veil class; 1 s is
                                    #   the honest land time, not a delay)
VIDEODIM_IDLE_CEIL = 30            #   30 s (owner timer law, Oct 16:
                                    #   the slider's 5 min max was dead
                                    #   pixels for a theater veil)
VIDEODIM_IDLE_DEFAULT = 15
VIDEODIM_LEVEL_FLOOR = 10          # the "veil level" rail (sibling of the
VIDEODIM_LEVEL_CEIL = 90           #   dimmer's veil level, same honesty:
VIDEODIM_LEVEL_DEFAULT = 20        #   10..90, 20 is the Oct-15 OLED
                                   #   ruling mirrored). The theater pieces
                                   #   draw at THIS darkness, NOT the idle
                                   #   dimmer's [dimmer].level number.


def normalize_videodim(value):
    """[videodim] in its in-memory shape: {on, min_rect_px, grace_s,
    idle_sec, level, fade, monitors}. The same honesty law as
    normalize_dimmer, mirrored:
    a bad on warns and folds to False (the default-off root - the feature
    sleeps until the owner wakes it), the rails clamp in silence. The
    retired keys (enabled / flag_families / sites, the debug-flag rail)
    are dropped here: a config written before the Oct-16 retirement
    still loads, but the words no longer shape anything - the
    companion's geometry is the extension's API, not a flagged browser.
    """
    value = value if isinstance(value, dict) else {}
    on = value.get("on", False)
    if not isinstance(on, bool):
        log.warning("videodim on %r is not a bool; the eye stays shut",
                    on)
        on = False
    try:
        mins = int(value.get("min_rect_px",
                             DEFAULTS["videodim"]["min_rect_px"]))
    except (TypeError, ValueError):
        mins = DEFAULTS["videodim"]["min_rect_px"]
    mins = max(VIDEODIM_MIN_FLOOR, min(VIDEODIM_MIN_CEIL, mins))
    try:
        grace = int(value.get("grace_s", DEFAULTS["videodim"]["grace_s"]))
    except (TypeError, ValueError):
        grace = DEFAULTS["videodim"]["grace_s"]
    grace = max(VIDEODIM_GRACE_FLOOR, min(VIDEODIM_GRACE_CEIL, grace))
    try:
        idle = int(value.get("idle_sec",
                             DEFAULTS["videodim"]["idle_sec"]))
    except (TypeError, ValueError):
        idle = DEFAULTS["videodim"]["idle_sec"]
    idle = max(VIDEODIM_IDLE_FLOOR, min(VIDEODIM_IDLE_CEIL, idle))
    try:
        level = int(value.get("level", DEFAULTS["videodim"]["level"]))
    except (TypeError, ValueError):
        level = DEFAULTS["videodim"]["level"]
    level = max(VIDEODIM_LEVEL_FLOOR, min(VIDEODIM_LEVEL_CEIL, level))
    # fade: the theater retract style (owner, Oct 16). STRICT bool,
    # absent/junk = False = frame vanishes the tick input returns;
    # true opts into the ramp family. Junk warns like `on` does -
    # it is a behavior switch, not a rail.
    fade = value.get("fade", False)
    if not isinstance(fade, bool):
        log.warning("videodim fade %r is not a bool; the frame drops "
                    "without a fade", fade)
        fade = False
    # monitors: the per-panel theater rows (owner, Oct 16). A row is
    # the EDID short -> {"on": bool, "level": int|None}. on absent is
    # True: a row EXISTS to opt out too, so the stock word is consent.
    # Junk on warns and defaults True (the panel keeps its theater - an
    # untrusted row may not silently strip the frame). level clamps to
    # the theater rails; absent, None, or junk means follow
    # [videodim].level. A bare bool row is the away table's shorthand.
    # Absent/empty/non-dict is {} - the legacy shape: only the video's
    # panel is framed, every pre-wave config behaves exactly as today.
    mons = {}
    raw = value.get("monitors")
    if isinstance(raw, dict):
        for short, row in raw.items():
            short = str(short).strip()
            if not short:
                continue
            if isinstance(row, bool):
                row = {"on": row}
            if not isinstance(row, dict):
                continue
            on = row.get("on", True)
            if not isinstance(on, bool):
                log.warning("videodim monitor %r: on %r is not a bool; "
                            "the panel keeps its theater", short, on)
                on = True
            level = row.get("level")
            if level is not None:
                try:
                    level = max(VIDEODIM_LEVEL_FLOOR,
                                min(VIDEODIM_LEVEL_CEIL, int(level)))
                except (TypeError, ValueError):
                    level = None      # the silent clamp family: junk
                                      # follows the global veil
            mons[short] = {"on": on, "level": level}
    return {"on": on, "min_rect_px": mins, "grace_s": grace,
            "idle_sec": idle, "level": level, "fade": fade,
            "monitors": mons}


def _live_shorts():
    """The desk's panel shorts, for the migration's rows. A seam on
    purpose: the suite patches this instead of the Win32 enum, and a
    desk we cannot read simply gets no rows (the absent-row default is
    the same dim sub-mode the migration promises anyway)."""
    from . import wm
    return [m["short"] for m in wm.monitors()]


def _migrate_away(merged):
    """The retired hdr-while-away toggle (the GLOBAL
    [power] hdr_off_when_away bool - this codebase never shipped the
    per-monitor table the feature packet first described) becomes the
    away.dim sub-mode it already promised: the live desk's monitors
    appear as blackout-false rows, the mode becomes "dim", and the
    fossil key STAYS in the file readable for one release (downgrade
    honesty: an older build finding it finds its switch untouched).
    E-day law: consent-silent files only - a file whose [power]
    section never said true is nobody's consent, and a file that
    already carries an [away] section is stamped and hands off. One
    named INFO line per migrated row. Persists right away, the way
    the first-run defaults do, so the truth is told exactly once."""
    try:
        power_raw = merged.get("_raw_power")
        if power_raw is None or power_raw.get("hdr_off_when_away") \
                is not True:
            return False
        away = merged.setdefault("away", {})
        # copy, never mutate: the shallow default-merge shares this
        # dict with DEFAULTS, and a row written into the stock section
        # would poison every later get_config in the process
        rows = dict(away.get("monitors") or {})
        away["monitors"] = rows
        away["mode"] = "dim"
        for short in _live_shorts():
            if short not in rows:
                rows[short] = {"blackout": False}
            log.info("away migration: %s inherits the hdr-while-away "
                     "consent as the Dim sub-mode", short)
        log.info("away migration: the retired hdr_off_when_away toggle "
                 "is now away.mode=dim (the key stays readable one "
                 "release); the away card on the detection tab is its "
                 "headstone")
        return True
    except Exception as exc:              # migration never blocks a boot
        log.warning("away migration failed; the desk stays on the "
                    "old path: %s", exc)
        return False


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
            # wreckage aside first so the edit stays fixable. KEEP THE
            # ORIGINAL IN PLACE TOO (owner lesson, Oct 15): the first
            # save after the reset rewrites path, and an
            # os.replace-style quarantine leaves no second copy - the
            # user's last good state rides on one renamed file with a
            # timestamp no human can read. Two dated, hand-named
            # copies cost 2 KB and buy the restore story.
            try:
                stamp = time.strftime("%Y%m%d-%H%M%S")
                bad = "%s.corrupt-%d" % (path, int(time.time()))
                os.replace(path, bad)
                log.error(f"unparsable config kept aside as {bad}")
                with open(bad, "rb") as f:
                    raw = f.read()
                keep = "%s.saved-%s.bak" % (path, stamp)
                with open(keep, "wb") as f:
                    f.write(raw)
                log.error(f"a readable-dated copy rests at {keep}")
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
    # the away migration (retired hdr-while-away toggle -> dim sub-mode
    # rows) reads the FILE's own answers, never the default-merged
    # dict: a stock false is not consent, and a file already holding an
    # [away] section is stamped and hands off (idempotent by
    # construction - the migrated file wakes up stamped). The raw power
    # view rides in on an underscore key (the writer skips those) and
    # is dropped again before the dict ships.
    merged["_raw_power"] = config.get("power") if isinstance(config, dict) \
        else None
    if "away" not in config and _migrate_away(merged):
        try:
            write_config(merged, path)
            log.info("away migration: the file learned its [away] "
                     "section in place")
        except Exception:
            log.exception("away migration: the rows computed but the "
                          "write failed; recomputed next boot")
    merged.pop("_raw_power", None)
    merged["away"] = normalize_away(merged.get("away"))
    merged["hider"] = normalize_hider(merged.get("hider"))
    merged["jog"] = normalize_jog(merged.get("jog"))
    merged["dimmer"] = normalize_dimmer(merged.get("dimmer"))
    merged["videodim"] = normalize_videodim(merged.get("videodim"))
    # THE BOOT TRUTH, one INFO line (Oct 19, the "theater turns itself
    # back on" hunt: the claim contradicts a persisted on=false and a
    # strict-True knob; every code path checked clean, so the next
    # boot must show its answer instead of the owner's archaeology).
    # AFTER normalize (gate round): the normalized table is the
    # answer - and its monitors-is-dict guarantee is what makes
    # .keys() crash-proof against a hand-edited list (a truth-line
    # that can die is worse than no truth-line: the gate caught this
    # exact class shipped in the first draft).
    vd = merged["videodim"]
    log.info("videodim boot: on=%r rows=%r", vd.get("on"),
             sorted(vd.get("monitors", {}).keys()))
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
        # here too: in memory the table keys are ints, the timeouts
        # never go negative. THE DARK CADENCE FLOOR MOVED (owner law,
        # Oct 13 night): the old max(5, ...) kept 1 s illegal because
        # "a 1 s 'fallback' would be always_on with extra steps" -
        # superseded: the always_on eye ALREADY holds the stream open
        # in the dark, so a 1 s read is strictly cheaper than the
        # boot-per-poll dance it replaces (the old rationale, quoted
        # where it lived). The LIT cadence keeps the old floor: the
        # law speaks the dark hour, and an eye degraded while the
        # panels are lit should still rest in minutes, not seconds
        camera_merged["on"] = normalize_camera_modes(
            camera_merged.get("on"))
        camera_merged["off"] = normalize_camera_modes(
            camera_merged.get("off"))
        camera_merged["always_timeout_sec"] = max(
            0, int(camera_merged.get("always_timeout_sec", 3600)))
        camera_merged["always_fallback_poll_sec"] = max(
            1, int(camera_merged.get("always_fallback_poll_sec", 1)))
        camera_merged["always_fallback_poll_on_sec"] = max(
            5, int(camera_merged.get("always_fallback_poll_on_sec",
                                     10)))
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
        # the consent migration (redesign law 1): the key absent is
        # not ignorance, it is a question the file can answer - a
        # camera section carrying labels, bindings, hides, shows or
        # a diagnostic record, or pointing at a NON-STOCK index, was
        # SET UP by a human (gate finding 2: a roster-only or
        # hidden-only upgrade must not silently flip consent off -
        # the screens would wake on an occupied desk with no word
        # said), and an upgrade must keep detection running
        # untouched. Absent and virgin - the stock write, stock
        # index 0, no tables - boots dark: no camera opens until the
        # owner touches the switch. An explicit value (either way)
        # always wins: this block touches only files that do not
        # speak.
        sec_cam = config.get("camera")
        if not isinstance(sec_cam, dict):
            sec_cam = {}
        if "enabled" not in sec_cam:
            # SPEAK WHEN IT FIRES (amendment 7): the 15:19 breach was
            # not the consent - it was the silence. A state change the
            # file decides must name its evidence in the log that made
            # it, or the next mystery re-litigates a whole afternoon.
            hits = [n for n, v in (
                ("labels", sec_cam.get("labels")),
                ("bindings", sec_cam.get("bindings")),
                ("hides", sec_cam.get("hidden")),
                ("shows", sec_cam.get("shown")),
                ("diag", sec_cam.get("diag")),
                ("non-stock index",
                 sec_cam.get("index") not in (None, 0, [0]))) if v]
            camera_merged["enabled"] = bool(hits)
            if hits:
                log.info("[camera] enabled absent and section reads "
                         "configured (%s) - consent honored from file",
                         ", ".join(hits))
            # the DEFAULT-OFF law (amendment 2, owner): every feature
            # that can surprise on a boot defaults off and never
            # self-enables. The same absent key that lets camera
            # CONSENT be honored (a human set this app up - keep the
            # names, the roster, the whole identity world) does NOT
            # vouch for the power-side flags: gaming/restore/taskbar
            # were the OLD app's doing, or a resurrected file's (the
            # debugger's collateral: no code auto-enabler ever
            # existed; the file was the writer). They reset to stock
            # false on this load and stay behind their switches. One-
            # shot by construction like the consent: the key lands in
            # the file on the first loop-owned save (every toggle
            # writes the WHOLE merged cfg), after which this block
            # cannot fire and the owner's flips stick.
            for _sec in ("gaming", "restore", "taskbar"):
                _fsec = config.get(_sec)
                if isinstance(_fsec, dict) and _fsec.get("enabled"):
                    merged[_sec]["enabled"] = False
                    log.info("[%s] enabled arrived with a pre-consent "
                             "file; the default-off law resets it (the "
                             "switch owns it from now on)", _sec)
    # the boundary migration (wave B, exactly this release edge): the
    # flips in DEFAULTS are stock changes, and a stock change does not
    # touch a file that already speaks - the boot that just ran wrote
    # the OLD stock trues to disk verbatim. The predicate is widened
    # from amendment 2's key-absent shape, and the widening is the
    # credited catch: the violation-era stock write lands EVERY key,
    # camera.enabled included, so the absent-key gate alone would miss
    # the one file this migration exists for. The gate is therefore
    # "this file never opted in": camera.enabled absent OR explicitly
    # false (a setup file whose consent the migration honored reads
    # true and answers for itself; a stamped file is post-boundary by
    # construction). Only keys sitting at their OLD stock values are
    # reset - a hand-typed true is the owner's word and stands.
    # assistant_task is on the list from the other direction: its
    # stock was already False, so a true riding a never-opted-in file
    # can only be the adoption's boot-time write (the breach the
    # screenshot caught) - the boundary clears the artifact, the
    # switch re-creates the task on the owner's click.
    _meta = config.get("meta")
    _cam_f = config.get("camera")
    _cam_f = _cam_f if isinstance(_cam_f, dict) else {}
    if (not isinstance(_meta, dict) or "defaults" not in _meta) \
            and _cam_f.get("enabled", False) is False:
        for _sec, _key, _old in (
                ("power", "hold_display", True),
                ("power", "hold_sleep", True),
                ("power", "skip_camera_when_blocked", True),
                ("power", "restore_windows", True),
                ("power", "assistant_task", True),
                ("guards", "fullscreen", True),
                ("recovery", "wake_policy", "re_off"),
        ):
            _fsec = config.get(_sec)
            if isinstance(_fsec, dict) and _fsec.get(_key) == _old:
                merged[_sec][_key] = DEFAULTS[_sec][_key]
                log.info("[%s] %s arrived with a pre-law stock value; "
                         "the default-off law resets it (the switch "
                         "owns it from now on)", _sec, _key)
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
        if value is None:
            continue        # TOML has no null: the ABSENCE of a key is
                            # this file's UNSET (the away-table law at
                            # the rules comment, now writer-wide - a
                            # None default like [dimmer].bound through
                            # str() would write `bound = None`, and the
                            # reload would call the WHOLE file corrupt
                            # and reset every setting: the Oct-10 trap)
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
        except (RuntimeError, TypeError) as exc:
            # a mutator not yet on _CFG_LOCK can still resize a nested
            # dict mid-copy ("dict changed size during iteration"),
            # and an un-deep-copyable value raises TypeError (gate
            # ledger 12): both get the same one retry after a short
            # beat; a second failure raises as today - callers log
            log.warning("config snapshot failed (%s: %s); retrying",
                        type(exc).__name__, exc)
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
    """One-time pre-rename migration, fail-open and one-shot BY
    CONSTRUCTION: the old data dir is copied over and the source is
    retired under a renamed twin the moment the copy lands (a backup
    left in place resurrected a 3-day-old config at the 15:19 launch -
    see the retire-on-use note below). The two pre-rename scheduled
    tasks are retired; the legacy Run value is replaced by its
    PanelBoss twin, so the autostart the user chose survives the
    rename. A fresh install (no old dir, no legacy value) is a silent
    no-op."""
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
                # RETIRE-ON-USE (amendment 7): a copy whose source stays
                # in place is a resurrection that can fire twice, and
                # twice is the silent breach the 15:19 launch proved -
                # the Oct-10 ICU dir (fingerprints: index = 2,
                # device_id = 1, gaming and restore on) copytree'd over
                # a file-less destination and the consent migration
                # then HONORED the stranger's file. Moving the source
                # out of reach the moment the copy lands makes the
                # migration one-shot by construction. A failed rename
                # keeps the copy (the destination file now answers the
                # next boot anyway), but says so.
                retired = (old_dir + "-retired-"
                           + time.strftime("%Y%m%d-%H%M%S"))
                try:
                    os.rename(old_dir, retired)
                    log.info("migrate: copied settings from %s; source "
                             "retired to %s (can never re-resurrect)",
                             old_dir, retired)
                except OSError as exc:
                    log.warning("migrate: copied settings from %s; the "
                                "source could not be retired (%s) - the "
                                "destination file now answers the boot",
                                old_dir, exc)
            except Exception as exc:
                log.warning("migrate: could not copy settings from %s: %s",
                            old_dir, exc)
    # task and Run cleanup run even when the old folder is already
    # gone: orphans outlive folders
    for name in ("ICU-PresenceDetector", "ICU-Presence-PowerRequests"):
        # through the no-window door (_spawn.py): no console flash
        # from pythonw. A gone task is a silent no-op; anything else
        # (an access wall: the task is SYSTEM-owned and this process
        # is not elevated)
        # is worth a warning, never a crash - migration never blocks
        # the boot, and an unscheduled hang of schtasks is a crash.
        try:
            from . import _spawn
            proc = _spawn.run(["schtasks", "/Delete", "/F", "/TN", name],
                              capture_output=True, timeout=30, text=True)
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
