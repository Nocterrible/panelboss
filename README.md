# ICU Presence Detector

Presence-aware monitor power for Windows: watches a webcam, decides
whether someone is at the desk, and drives the displays into the same
DPMS standby the power-plan timeout uses (`SC_MONITORPOWER` broadcast).
When nobody is there the screens go dark; when somebody comes back they
come up again — with the camera polling faster while the screens are dark
and the LED off between polls while they are lit, so you can always
notice the camera blinking and something malicious watching it.

## How it decides

| situation | what happens |
|---|---|
| typing | nothing; the camera never runs (`idle_gate_sec`) |
| idle > `idle_gate_sec` (30 s default) | camera boots per poll, every `on_poll_sec` (3 s) |
| idle and being watched | the app holds Windows' own display and sleep timers off (`[power] hold_display` + `hold_sleep`, default on, independent) so a plan timeout can never time a still person out; the display hold is released before the app's own off-broadcast, and both are released on pause/snooze |
| absence confirmed `absent_confirm_sec` (60 s) | `SC_MONITORPOWER(2)` — same standby as the power plan, worst case 90 s after the last keystroke |
| screens dark | camera held open, polled every `off_poll_sec` (3 s) |
| `min_hits` (2) consecutive positive frames | camera released **before** the screens wake (the device is exclusive) |
| screens wake on their own (mouse jiggle) | `wake_policy = "re_off"` (default) turns them off again after `re_off_grace_sec` unless `min_hits` people show up; `"leave_on"` hands them back for `leave_on_grace_sec` |
| any wake — the app's own, a jiggle, the power button after a sleep | window placement is put back (`[power] restore_windows`, default on): every window's rect and the monitors' hardware IDs were saved before the panels dimmed; after the wake the app waits for the topology to settle (unchanged for 4 s, up to 60 s) and moves everything back — see *Remembering the desk* |
| **two** unexpected wakes within `wake_burst_window_sec` (120 s) and nobody ever seen | auto re-off **pauses**: screens stay lit while the desk keeps producing input, a toast says the camera (index N) never saw a person — the slipped-off-the-monitor case; re-arms when a person is confirmed, the policy changes, or `Resume auto re-off` (tray/window) |
| another app already holds the display awake (video wake lock, a game, a presentation) | camera polling **stops** while the block is active (no point defending a screen someone else owns); the window's power assistant shows who holds it, and polling resumes when they let go |
| fullscreen app owns the display | the broadcast is skipped (the message never reaches the swap chain) |

Timers, camera modes (`boot_per_poll` / `always_on`, one choice per
phase), the wake policy and the overrides below are all editable from
the settings window — four tabs, one subject each: **detection**
(mode; the model's knobs or the differencer's — they never share the
screen; the timers; the live preview beside the camera picker),
**monitor profiles** (named whole-desktop states: panels, modes,
HDR, window seats, and the restore-at-start lever — see below),
**power plan** (the timer overrides
here, the wake behavior, the powercfg assistant), **General** (the
meta: skin, start minimized, autostart, updater, logs).
Anything with more to say has a "?" beside it: hover for the story,
click to pin it. The config file holds the same values.

**Owning the screens (`[power] hold_display`, `hold_sleep`, default
on — and fully independent).** While the app watches a lit desk it
holds a Windows execution-state request (`SetThreadExecutionState`):
the plan's own timers do not start while a request lives, so the
measured tug of war — plan times a still-reading person out, the
camera sees them, the app powers the screen back on — cannot happen,
and the power plan itself needs no touching at all. Each timer is
held separately: display held, sleep released is the classic
no-screen-timeout setup media players always shipped. The display
hold lets go before the app's own off-broadcast (holding a display is
claiming the screens are wanted); the sleep hold is what keeps the
watcher alive through the dark — with it off the box sleeps on
schedule and presence detection re-arms when the power button is
pressed. Pausing, snoozing, or the process dying (crash included,
fail open by construction) hands everything back. Only the
*automatic* timers are affected: your own Sleep button, the lid and
shutdown are requests no app outvotes.

**Remembering the desk (`[power] restore_windows`, default on).** Some
monitors unplug themselves from Windows when they sleep: every window
on them survives in limbo and lands resized on the wrong screen when
the panel returns. The app owns the off edge — it snapshots every
top-level window's true pixel rect plus the monitor topology
(EDID-derived hardware IDs + positions) *before* its off-broadcast.
After ANY wake (its own, a mouse jiggle the watcher reported, the
power button after a sleep) a helper thread waits for the topology to
settle — unchanged for 4 s, within 60 s — and only moves when the
fingerprint matches the saved one: same panels, same places. A
swapped or permanently-unplugged monitor means the saved positions
belong to a desk that no longer exists, and nothing is moved.
Minimized windows, owned popups, cloaked (other virtual desktop) and
shell windows are left alone; a maximized window is re-maximized on
its own old monitor; windows closed during the dark are simply gone.

**Named desktops (monitor profiles tab).** A profile is the whole
desk spelled out: which physical panels (EDID hardware identity —
never the `\\.\DISPLAYn` slots, which reconnect storms reshuffle)
are on, where they sit, which is primary, each one's resolution and
refresh rate, an HDR ask, and a seat for every pinned app. The
picker opens on the profile last used for the layout it sees;
*create new...* captures what the desk is doing right now. Applying
one is the entire lever, in an order this project stole from
`monitor_control` and its lessons baked in: topology first (already
correct monitors untouched so a self-apply never blinks; the new
primary LAST with `CDS_SET_PRIMARY`, because Windows refuses with
error 87 to give up the display that owns the desktop in the same
call that hands the desktop over), modes asked only from the
driver's own offered list with a `CDS_TEST` first, then the HDR
command (read first, set only what disagrees, verify by reading
again — see below), then a **wait until the monitors answer as the profile
asked** (Windows reports success before the modes have settled —
measured — so the live fingerprint is the proof, quiet for two
seconds), and only then the windows.

Windows are pinned per APP, in the tab's **pin an app** editor:
pick one of the open windows, set its conditions, *pin it* — the
spot it holds right now becomes the seat the app must return to.
Matching defaults to `process`, because a browser or chat window
renames itself constantly and a pin that trusted titles was dead
the moment you clicked another tab; the editor warns out loud when
a process pin would move EVERY window of that app, not just the
picked one. `process + title` (the automatic wake-restore's method,
where it stays) matches exactly the one window it was pinned from;
`title` is the gentle version. The honest extras: *open it if
missing* runs the exe saved at pin time when no window answered,
waits for it to wake (default 30 s, adjustable per pin from 5 s to
10 min) and moves it the moment it shows — a naive exe run, so
store apps and stub launchers may start nothing; *browse* then
lets you point the pin at the launcher or binary that really opens
the window (the shell runs it exactly like a double-click, so a
`.lnk` shortcut works too). The pinned seats list sits **below**
the editor on purpose: clicking a row loads the editor directly
above the row clicked, always on screen (with the seat list on
top, the editor of an edited pin often fell below the bottom of
the window). Clicking a pinned row lifts the pin
back into the editor to change or refresh it, `x` forgets the
seat, and *pin every open app* seats one window per running
program at once. At apply each pin moves the windows that answer
to it (earlier pins answer first, windows no pin speaks to are
never touched); a pin whose app stayed away is complained about
**once** — the dialog offers to fix the profile, and "let it be"
keeps that pin silent about the same failure until the app
actually shows up again. Anything the shuffle stranded off-screen
is rescued on the spot. The one thing a profile cannot fix is a
panel that is not plugged in — modes can be asked for, a missing
monitor cannot — so applying onto the wrong monitors refuses with
the honest sentence and a *try anyway (best effort)* button that
converts what exists and places windows on whatever desk answered.

**The lever can pull itself (restore at start).** The profiles tab
holds a pre-armed apply (it arms profiles, so it lives with them
— General keeps only the autostart entry that proves which copy is
the logon one): tick *armed*, pick
which profile ("the last one for this desk" chooses by panel
IDENTITY — a cold boot may not have reached the profile's modes
yet, and the exact fingerprint would then hide the profile that
fits), what to restore (the whole desk, monitors only, or windows
only — the desk gate guards every scope), and when (autostart
launches only, or every app start). Which copy the logon fired is
never guessed — the shell gives no clue; the Run entry this app
installs stamps `--autostart` on itself and the app reads its own
arguments as proof (flagless old entries learn the stamp at the
next start, and only entries differing by exactly that stamp are
touched). Login is treated as the storm it is, and the lever says
so when you arm it: the **first** login sits out 2 full minutes
before launching anything — calibration, timing every app it
launches until a window shows — and keeps the worst time per app.
Every login after that launches only after the slowest observed
boot + 20 s (never under 30 s, never over 10 min), the note under
the lever states the learned number, and the tray balloon reports
what the next login will wait. The timing is measured from OUR
launch, never from login start — counting our own wait as the
app's slowness would make every login grow one buffer longer than
the last. Every "open it" at login carries its own wait + 60 s;
results arrive as tray balloons (still-missing apps named), never
a dialog holding a half-woken desktop hostage. If a manual launch
at the exact moment of logon wins the single-instance race, the
restore runs in whichever copy survived.
The profile's HDR dropdown asks in human words and every choice
means what it says. **restore as captured** (the default for new
profiles) puts every panel back
in the on/off state the profile saw at capture — per monitor, so
two HDR panels each keep their own habits. **ignore HDR** never
asks anything. **all hdr-capable panels on/off** forces every
capable panel the same way — both of yours, if both can. (The old
global **toggle** survives only in hand-edited profiles, where the
engine still obeys it.) Nothing is ever guessed: panels without
HDR are never ordered to do the impossible, and a profile captured
before the snapshot existed says it has nothing to restore. The
mechanics: HDR is a read, then a command: on Windows 11 24H2 and later the
DisplayConfig API answers per monitor what colour mode it is
actually in (`GET_ADVANCED_COLOR_INFO_2` — the call the Settings
toggle itself is built on) and accepts a direct SET, so the app
reads first, commands only the monitors that disagree with the
profile's ask, then reads back until the answer arrives. No
hotkey, no guessing. win+alt+b (configurable) survives only as the
fallback for older Windows, where the one readable answer conflates
HDR with wide-gamut colour and measurably lies — on this desk it
reports "supported + enabled" for a panel that cannot do HDR at
all. The stored belief (`hdr_now` in `profiles.json`) is kept
calibrated from the reads and matters only on that ancient path —
and on it, *restore as captured* abstains rather than flip a coin
(the belief dance knows exactly one global switch).
The **rescue my lost windows** button (on the command bar beside
sleep/pause/Quit, always visible — useful far
beyond profiles) walks every visible, non-minimized, grabbable
window no screen covers and brings it back to the middle of the
primary monitor. Store: `%APPDATA%\ICU-PresenceDetector\
profiles.json`; the automatic off/wake desk-memory above stays the
nightly path — profiles are the manual lever.

## Detection modes (`[detection] mode`)

| mode | sees | notes |
|---|---|---|
| `"person"` (default) | the ONNX person model | a chair with a jacket on it is not presence |
| `"motion"` | pixels that changed | no model at all: nothing loaded, nothing learned about faces; presence = one poll saw `ratio` of the (downscaled) frame change, and it lingers `hold_sec` after the LAST motion, because stillness (reading!) is not absence |

Switching is live from two places that mirror each other: the tray's
**Detection mode** submenu and the **mode** segment on the settings
window's Detection card (person (AI) / motion (no AI)). Either flips
the detector on the spot - the differencer is built or the session
re-opened, no restart - and the choice persists to the config; the
other control catches up within a tick over the shared config dict.
Motion mode never touches onnxruntime, so it also works before any
model/provider story applies.

**Depth/IR sensors (Hello bridge included):** motion mode drives any
grayscale stream. Two ways in:

- Plain indexes. Many desktop Hello webcams expose the IR sensor as an
  ordinary second UVC device — it then shows in the tray **Camera**
  menu like any webcam (measured here: one Hello cam presents *two*
  "USB Camera" entries, RGB and IR, both openable by index; the
  ambiguous names are exactly why the second way exists).
- `index = -2` (or the tray's **hello IR:** entry) — the
  `MediaFrameSourceGroup` route. Windows Hello drivers hide the sensor
  from plain enumeration (`SkipCameraEnumeration`), but WinRT reaches
  it in `SharedReadOnly` mode while Hello stays armed. This needs the
  optional bridge `whircam` (MIT, PyPI; pulls ~1 MB of `winrt-*`
  wheels) — and asks instead of failing: the camera picker carries a
  hello IR entry either way, and choosing it (or already having
  `index = -2` without the bridge) opens a prompt that hands the job
  to `update.bat deps` — the same updater, optional dependencies
  included — and reopens the app installed. Absent whircam and
  declined prompt = the real menu entry never appears and everything
  else is unchanged. Measured on this box: the bridge finds
  two IR groups (`USB Camera` infrared-only, `YourCameraGroup` with
  Color+Infrared) that carry the same sensor.

IR frames are near-infrared grayscale at ~15 fps (the driver alternates
lit/ambient) — motion mode does not care and the person model works on
BGR-converted IR too, though it was trained on RGB lighting. IR opens
take ~1–2 s (WinRT pipeline start): with `index = -2`, prefer
`mode_on = "always_on"` in `[camera]` so the pump is not rebuilt per
poll. A crashed WinRT pump reads as a dead handle — the state machine's
existing release-and-reopen path picks it up.

**Tray**: a plain LEFT click opens the settings window (the
`Settings...` item is the pystray default action); the menu itself
remains the right-click affair.

## Gaming refresh rates (`[gaming]`, power-plan tab)

A fullscreen game deserves its panel's top Hz; a desktop does not
need 240 Hz burning watts and OLED heat all day. The watcher
(`gaming_watch.py`, beside the presence loop) applies one law:

1. **only a window covering a whole monitor starts the conversation**
   - a windowed or half-screen app can ask for nothing;
2. **evidence decides**: sustained 3D-engine GPU load (the Windows
   performance counters, read per pid - video decode is a different
   engine, which is why a fullscreen video player never looks like a
   game), or a loaded `xinput*.dll` (controller APIs a game is
   almost alone in using), or simply being on the user's games list.
   An unlisted app must hold evidence for `seen_secs` before anything
   moves; a listed one moves instantly, because menu screens render
   at near zero;
3. **grace, not flicker**: alt-tab to Discord does not drop the
   monitor - the rate returns `grace_secs` (60) after the game stops
   answering, once, quietly;
4. **we never fight a mode we do not own**: every rate set is booked
   in a ledger; when the driver moves the mode under us mid-game
   (native-exclusive titles do exactly that), the watcher takes its
   hands off until the game leaves;
5. **resolution is never touched** - only the rate is traded, and
   back; `game_hz = "auto (fastest)"` asks the panel's own list.

Detection reads `\GPU Engine(*)\Utilization Percentage` per-instance
(`gpu.py`); the wildcard-array API is abandoned on this OS (it
answers, but its items match no documented layout - see the quirk
below). `has_xinput` snapshots a process's modules, which anti-cheat
can make slow, so it runs only when the foreground *pid changes*,
never per tick. Fail open everywhere: no counters, no game mode.

If `power_plan` names a scheme (fragment like `high`, or a guid),
entering game mode also swaps the power plan and - the part that
distinguishes a janitor from a vandal - restores **the plan that
was active before the game**, not a guessed default, and only if
nobody else moved it meanwhile. Off by default (unset).

## HDR while away (`[power] hdr_off_when_away`)

HDR-owning OLEDs punish an unasked HDR desktop: SDR content looks
washed and the panel runs brighter/hotter than the room wants. With
the switch on, the screens-off moment turns HDR **off on every
panel reporting it on**, remembers exactly which ones were lit, and
hands them back on the return (`profiles.hdr_away_off/restore`, the
wake and force-on paths both). Panels that were off, unsupported,
or whose OS cannot answer the question honestly (pre-24H2 merges
HDR with wide-gamut - not a fact worth acting on) are left in
peace. A user's Win+Alt+B toggle in the middle is overridden by the
handback: the promise is "what you had when you left", not "guess
what you want now".

## Registry tweaks (`[tweaks]`, no admin, no reboot)

Small, measured registry wins (research: `docs/apack-findings.md`,
all verified on this 25H2 build - the folklore pile stayed out):

* `fso_apps`: full exe paths whose **fullscreen optimizations get
  turned OFF** (the exact `~ DISABLEDXMAXIMIZEDWINDOWEDMODE` layer
  the compat-tab checkbox writes; takes effect next launch). At
  boot the Layers key is MIRRORED to the list - missing entries are
  added, fallen-off entries lose only OUR token (someone else's
  compat flags in the same value survive).
* while a game owns the desk, the watcher holds **1 ms system
  timer granularity** via the documented `timeBeginPeriod` API -
  the honest half of the "0.5 ms fix" (zero admin, zero reboot,
  gone the moment the game leaves; the registry variant of that
  fix is undocumented and skipped).
* `awaywatch.tweaks` also knows the Game DVR suppressors (overlay,
  background capture, record-what-happened, session detection -
  all HKCU, read live so Settings and us never disagree) and the
  machine-wide policy attempt that honestly reports "admin needed".
  A UI card for these is the next seat in line.

## Settings window & skins

`run.bat` opens a CustomTkinter window (main thread; the monitor loop
and the tray run on workers). Everything applies live — sliders write
the same config dicts the loop reads every tick — and persist to
`config.toml` after a short rest. The **Camera** panel shows a live
debug view next to the index picker: the picture is literally the last
frame the detector judged (via a thread-safe frame slot), so you tune
against exactly what the model sees. "live preview" holds the camera
open at ~5 fps; the hold is a *lease* the window renews while visible,
so closing it (or crashing) releases the device.

The Camera card has a **powercfg assistant** switch (marked with the
UAC shield, drawn to match the system icon, because ticking it means
one admin confirm): `powercfg /requests` requires administrator
privileges, so the app cannot simply ask. Ticking the box registers a
tiny scheduled task (one admin
confirm - silent when UAC is set to never notify) that runs as SYSTEM,
completely invisible, and dumps `powercfg /requests` and
`powercfg -requestsoverride` to a file the app reads silently
afterwards — who keeps the display awake is listed under the box, and
camera polling stops while a display-class blocker is alive. A holder
the user previously silenced with `powercfg -requestsoverride` shows
grey and prefixed `*OVERRIDE`: Windows itself ignores overridden
requests, so the app never pauses the camera for them. While the
switch is on, a **manage powercfg overrides** button appears below it:
a window with one row per object (process, driver or service that
holds a request or owns an override - a holder that is also overridden
is one row saying both), and a **checkbox per request type**: the
per-object typelist is the unit powercfg thinks in, and the set form
replaces the whole list, so apply ships each changed object's complete
wanted list, survivors included. Checked = overridden (live truth);
a `held` flag marks types seen holding since the window opened. The
row list **accumulates while open** - requests flicker, so nothing is
forgotten between reads - and a **refresh** button folds in whatever
new popped up while the user was reading. Types beyond the five the
set form can express (perfboost, console) show as locked boxes marked
*drops on edit* (measured: the set form silently discards them).
Changes stage locally until **apply** shows up - one elevated
batch of `powercfg /requestsoverride` sets, verified against a fresh
dump like everything else here. Removal is the same set form with no
request types (`powercfg /requestsoverride PROCESS chrome.exe`): the
documented `DELETE` keyword does not exist in this build (measured -
Invalid Parameters).
Unticking the switch removes the
task and the button. With the box off, the app never elevates anything
and simply keeps polling (fail open).

Skins are the seam for the two looks. `ui.skin` picks one
(`theme.get_skin`); a `Skin` is only a palette + the style kwargs each
widget asks for, so layout lives in `window.py` and a new look is one
file. `modern` is the unfun default; `fun` is a palette stub awaiting
its real design. Switching is live.

## Setup (portable, never touches the base env)

```powershell
git clone <this repo> ; cd ICU-PresenceDetector
powershell -File scripts\setup.ps1     # .venv + pinned deps + weights
run.bat                                 # or double-click: tray + monitor
update.bat                              # pull + reinstall + relock;
                                        # reopens the app when the app
                                        # itself asked (its button)
```

The console that blinks on `run.bat` is cmd's *own* window, gone the
moment `pythonw` starts; autostart and the updater's relaunch launch
the windowless `pythonw` directly and pop nothing anywhere.

Diagnose first:

```powershell
.venv\Scripts\python.exe -m awaywatch cameras    # find your index
.venv\Scripts\python.exe -m awaywatch preview --off-test   # draw + round trip
```

Config: `%APPDATA%\ICU-PresenceDetector\config.toml` (written on first
run). Logs: same folder, `logs\awaywatch.log`
(`ICU_PRESENCE_LOG_LEVEL=debug` to see every frame decision).

`run.bat` starts the settings window plus the tray icon. The window
is where everything is tuned (see below); closing it with ✕ hides it to
the tray, and tray → `Settings...` brings it back. Windows 11 hides new
icons behind the taskbar chevron — look there first. The icon also pops
a "running" toast, and the log says `tray icon ready`, so a quiet start
is a good start. Launching `run.bat` twice is refused by a mutex; the
notice dialog closes itself after 5 seconds.

Headless (tray only, no window): `ui.enabled = false` in the config or
`python -m awaywatch run --no-ui`.

Start at logon: both the tray menu and the window's **General**
card carry a `start with Windows` switch. It writes one value under
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` (named `ICU
Presence Detector` — the entry Task Manager's Startup tab lists, so
the user can verify it in system UI). No admin. The registry is the
truth: the switch reads the entry back every time, a stale entry from
a moved folder is shown as pointing elsewhere, and one flip off and
on re-points it at the current copy. The command stored is this
install's own: the frozen exe for a packaged release, `pythonw
run.py` for the repo.

`powershell -File scripts\autostart.ps1 install` is the alternative
(Task Scheduler). Pick one — both at once means two launches at
logon, and the mutex answers the second with a notice dialog.

## Face identities (optional)

`faces.enabled = true` makes only enrolled identities count as presence:

```powershell
.venv\Scripts\python.exe -m pip install insightface
.venv\Scripts\python.exe -m awaywatch enroll --name you
```

insightface shares the project's `onnxruntime` wheel, and the
DirectML flavor (requirements.txt) also ships the CPU provider, so
there is no after-every-upgrade swap dance anymore.

## Things this machine taught us

* `\GPU Engine(*)\Utilization Percentage` **wildcard array reads**
  (`PdhGetFormattedCounterArrayW`) answer rc=0 with ~1900 items in a
  self-consistent blob that matches **no documented item layout** on
  this OS (probed across both header shapes; `create_string_buffer(1,
  size)` meanwhile silently heap-corrupted the attempt - the first
  argument is the initial byte, not the size). Read per-instance
  instead: enumerate instance names, add one counter per rendering
  instance (cap 400), collect twice; measured setup 0.1-0.2 s, so
  `gpu.usage()` builds fresh every call - and the fresh build is not
  a preference: **counter instances are born with their process**, so
  a reused query is blind to every game started after it (measured:
  stays blind forever)
* **2026-10-10, the day the GPU went silent**: after an overnight
  restart, EVERY per-instance read fails `PDH_INVALID_ARGUMENT`
  (0xC0000BBD) and .NET `Get-Counter` reports
  `PDH_CSTATUS_INVALID_DATA` with silent 0.0 for all ~1650
  instances - bisected across scale (3 vs 400 counters), collect
  schedules, format-vs-struct pairings and 3-vs-4-arg calls
  (scripts/pdh_min.py). Verdict: the counter DATA PROVIDER (WDDM
  graphics bridge) is dead machine-wide, not our marshaling; both
  GPUs stay `CM_PROB_NONE` and enumeration still works (metadata
  only). Corroborating: all monitors fell 240/144 back to 60 Hz at
  the same restart. Recovery needs a driver-mode change (hot-key
  reset or NVDisplay container restart, admin) - BOTH forbidden
  while the vLLM fleet runs, because the engines live on those exact
  GPUs (a reset kills them). Until the next reboot at the user's
  hours: `gpu.usage()` fail-opens to `{}`, gaming evidence degrades
  to trust-list + xinput, and the video-rate feature stays gated
  (scripts/video_probe.py must see decode move before any engine
  trusts a counter). Honest re-read of the note above: "rc=0 with
  values 0.0" on 10-09 may have been the same dead provider masked
  by silent zeros - treat that success claim as UNVERIFIED
* **config writer, the silent data-killer (2026-10-10)**: a
  non-empty dict was emitted as Python `str(dict)` - single quotes,
  unparseable - so the FIRST save carrying one (a gaming rate pick)
  made the next boot declare the file corrupt and reset every
  setting. Dicts now emit as TOML inline tables (keys through
  `json.dumps`: TOML bare keys are `[A-Za-z0-9_-]` only), and so do
  strings - the old escaper only escaped `"`, so a backslash path
  (`F:\Games\...` in tweaks.fso_apps) was a parse bomb too. Proven
  by scripts/config_writer_test.py, which now rides the sweep
* the venv `python.exe` is a **redirector**: `Popen([sys.executable,
  "-c", ...]).pid` is the shim; the interpreter that really runs the
  code is its child (measured: popened 70424, child's own `getpid()`
  75092). A module-walk probe was blaming `wm.has_xinput` for a day -
  it kept inspecting the shim, which loads nothing. Real games own
  their windows, so `foreground()` never hands out a shim pid, but
  any future test that spawns an interpreter and inspects it must ask
  the child for its own pid
* **`CreateToolhelp32Snapshot` with the module flags answers an
  EMPTY snapshot for every pid from this venv's process family** -
  self, a child that had just loaded `xinput1_3.dll`, even explorer
  itself (measured across child processes: 0 modules where psapi
  reports 21/32/397; no error, just empty). Module enumeration in
  this project is therefore **psapi-only** (`EnumProcessModulesEx` +
  `GetModuleBaseNameW`, `LIST_ALL_MODULES_REQUEST=0x3`):
  `wm.has_xinput` was silently always-False under toolhelp. NOTE:
  process-list snapshots (`Process32First/Next`, flag 0x2, as used
  by `gpu_probe._name`) are a DIFFERENT snapshot kind and were not
  disproved by the bisect - only module snapshots are dead here
* the settings window's tab click-to-quiet cost scales with widget
  count: measured 4.4 s cold / 2.4 s warm on monitor profiles, 2.0 s
  on general - the pack/unpack itself is near-free, the cost is CTk
  repainting every canvas-backed widget the page reveals. That is
  why gaming controls joined the power-plan card list instead of a
  fifth tab (five 120 px buttons would not fit the window either)
* the DEFAULT PyPI `onnxruntime` wheel has **no GPU provider at all**:
  requesting `CUDAExecutionProvider` from it is not an error, just a
  warning on stderr that `pythonw` never shows - the session silently
  ran on CPU forever. `get_session` now asks strictly from
  `get_available_providers()`; `onnxruntime-directml` is the wheel that
  makes this app GPU-capable with zero extra dlls
* yolo11n at 640 px, measured: DirectML ~40 ms/inference vs CPU ~30 ms
  on this box - at nano size the per-call overhead eats the GPU win,
  so the device picker is about CPU load, not wake latency. And DML
  `device_id` follows DXGI adapter order, which need not match the
  nvidia-smi order the tray menu shows

* raw `SC_MONITORPOWER` broadcasts do **not** emit `GUID_MONITOR_ON`
  notifications — display state is tracked from commands, input activity
  and the camera; the power sink still listens for power-plan transitions
* the `SC_MONITORPOWER(-1)` **on**-broadcast is effectless on this box
  (measured: the whole wake path ran — camera released, broadcast sent,
  `ES_DISPLAY_REQUIRED` pulsed — and the panels stayed dark until real
  mouse input; NVIDIA + DisplayPort drops the link and the driver
  ignores the legacy request). The "supported" replacements are dead
  ends here too, all probed: `powrprof.dll` exports **no
  `CallNtPowerRequest`** at all on current Windows, `powercfg`'s
  request table has no video-on keyword, and kernel32
  `PowerCreateRequest` takes a `REASON_CONTEXT` with no video-on type.
  Injected input is the only measured weapon: `wake()` CTRL-taps via
  `SendInput` (a lone modifier presses no buttons), then one broadcast
  round for machines that honor it, `ES_DISPLAY_REQUIRED` for the idle
  timer, and a second tap — real input re-trains a DP link, and
  `SendInput` rides the same stack
* `SendMessageTimeout` with `uTimeout=0` waits forever; some app on the
  system never pumps its queue — every call carries a timeout
* ctypes finds **exports**, not C header macros: `user32.SendMessageTimeout`
  raises `AttributeError` (the dll only exports the A/W variants), which
  silently killed every monitor-off under `pythonw` where the traceback
  could never be seen — every such entry point is called with its real
  `...W` suffix here
* `powercfg /requests` **requires administrator privileges** even to
  *read* (measured on Windows 11 26220; no user-mode API escapes it).
  The power assistant is the classic workaround: a once-registered
  task that the non-elevated app starts with `schtasks /Run` (no UAC
  after the one-time confirm) and reads via a dump file. Getting that
  task registered on this machine needed three measured facts:
  `schtasks /Create` rejects `/SC ONDEMAND` (no such schedule type -
  use a dummy `DAILY /ST 03:07` and drive cadence with `/Run`);
  a task created from the elevated context arrives with security
  descriptor `O:BA`, invisible AND unrunnable to the same user's
  filtered token (`icacls` on the task FILE fixes nothing -
  TaskScheduler checks the task's own SD), so the installing script
  rewrites it via `Schedule.Service` COM:
  `SetSecurityDescriptor("D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGX;;;SID)",
  0)` - the 0-flag and the trustee at SDDL field 6 both matter; and
  elevation should go through `ShellExecuteW("runas", "powershell",
  "-File script.ps1")`, because `Start-Process -Verb RunAs -Wait`
  spawned from a `pythonw` process hung under the "Never notify" UAC
  slider while ShellExecuteW returned instantly. Elevation is a
  handoff, never an answer: every path re-asks the task store
  (`/Query`) for the truth afterwards
* `widget.after()` from a worker thread is NOT a safe "post to UI":
  when the thread answered fast (schtasks replied while the window
  constructor still ran, before `app.mainloop()` existed), tkinter
  raised `RuntimeError: main thread is not in main loop`, pythonw ate
  the traceback, and the answer evaporated - the assistant switch
  drifted from reality and the setting "did not persist". Cross-thread
  replies must ride the event QUEUE the periodic main-thread tick
  drains; a queue is thread-safe whenever, `after` only once the loop
  exists
* a `.bat` written from a python string doubles `%%` expansions **only
  if** the python string itself goes through the `%` operator: a plain
  literal `"%%~dp0"` writes `%%~dp0` into the file, and cmd hands it on
  as *literal text* - the SYSTEM task then "successfully" wrote
  `C:\Windows\System32\%~dp0power_requests.txt` forever while the real
  dump file aged (found via that exact junk file sitting in System32)
* `powercfg /requests` on current Windows prints FLAT: `[PROCESS]
  <path>` / `[DRIVER] <name>` markers at column 0 with the reason alone
  on the next line - no indentation exists to lean on, so reason lines
  pair with the entry above positionally (one per entry) and the
  `\Device\HarddiskVolume8\` prefix is volume noise the parser trims
* the app's own display hold appears in that same dump, under
  `DISPLAY:`, as the app's own `[PROCESS]` line - and the flat layout
  prints **no PID** for execution-state holders (measured): only the
  image path, and of the BASE install the venv launcher re-execed, not
  the venv path itself. The self-filter matches both spellings'
  driveless path tails; without it the app would list itself as a
  display blocker, stop its own camera, and defend itself forever
* `powercfg -requestsoverride` bare (the listing, needs admin, so the
  dump task writes it under a `REQUESTSOVERRIDEMARK` line) shows
  `[CATEGORY]` headers then `<friendly name> <TYPE>` per line. A live
  holder whose name and request type appear there was silenced by the
  user themselves - it leaves the gating bucket and returns as a grey
  `*OVERRIDE ...` line: the whole point of an override is that Windows
  ignores that request, so the app must not pause the camera for it
  either
* `powercfg /requestsoverride DELETE ...` (the documented removal
  form) does **not** exist in this build - `Invalid Parameters` with
  or without types, measured in a hidden elevated run where the error
  was otherwise invisible. Removal is the SET form with no request
  types (`powercfg /requestsoverride PROCESS chrome.exe`), which
  deletes the registry value under
  `HKLM\SYSTEM\CurrentControlSet\Control\Power\PowerRequestOverride\`
  outright; and the set form **replaces** the whole typelist, so
  touching one type of a multi-type entry must re-list the others
* the set form silently **drops types beyond the five** (display,
  system, awaymode, idle-reschedule, execution): asking for
  `DISPLAY PERFBOOST` stored `0x1`, no error, the perfboost bit
  simply never existed - entries carrying such bits lose them on any
  edit through the CLI, so the manager shows them locked as
  "drops on edit"
* customtkinter's checkbox kwargs are `fg_color`/`hover_color`/
  `checkmark_color` in the pinned release - the `checkbox_checked_color`
  names newer docs show raise `ValueError` at construction; and every
  ctk widget prints its CLASS NAME as placeholder text unless `text`
  is given (the "CTkLabel" ghost over the shield icon)
* `destroy()` tears children down while Tk still runs the queue, so
  a self-rescheduling UI tick will reschedule itself on the
  half-dead interpreter forever (endless "ui tick failed" traceback
  loop, mainloop never returns) - a "dying" flag checked before each
  tick is what lets the window actually end
 * `cv2.VideoCapture` opened DURING the display standby transition
  hands back an open-yet-FROZEN handle: `isOpened()` is true, frames
  never flow again (probe: opening after the panels are dark always
  streams fine, ~4-21 s per open). So the held `always_on` stream
  rides through the transition untouched, and any handle whose read
  times out is treated as dead whatever `is_open()` swears - keeping
  the corpse meant forever-silent dark polling and mouse-only wakes
* `CREATE_NO_WINDOW` is a **process creation flag**, not a
  `STARTUPINFO.dwFlags` bit - stuffing it into startupinfo looks
  plausible, compiles, and does nothing. And since 24H2 the *default
  terminal* applies: every console a `pythonw` child forgets to hide
  opens as a **Windows Terminal window that steals focus** (captured
  with an EnumWindows watcher blinking every 2 s - the confirmation
  loop querying schtasks). Console children of a GUI app must get
  `creationflags=CREATE_NO_WINDOW` like a load-bearing wall
* message-only windows receive notifications only on the thread that
  created the window, and that thread must have created a message queue
  (`PeekMessage`) first; every handle is `c_void_p` so 64-bit values never
  truncate through `int`
* `GetMonitorInfoW` fails here with error 87 for **every** struct shape
  (measured: plain and EX, argtypes on and off, inside and outside the
  `EnumDisplayMonitors` callback) — monitor identity comes from
  `EnumDisplayDevicesW` + `EnumDisplaySettingsW` instead (DEVMODE
  position + the panel's EDID-derived `DeviceID`; the `\\.\DISPLAYn`
  slot names get reshuffled by reconnect storms). And
  `SetWindowPos`'s `SWP_NOOWNERZORDER` fails with error 1004 whatever
  the z-order slot holds (measured: `None`, `0`, `-1`) — the restore
  move rides on `NOZORDER|NOACTIVATE|SHOWWINDOW` only
* display-mode changes are a **normal-user right**: the whole profiles
  feature asks `ChangeDisplaySettingsExW` from a medium-integrity
  token (measured: `CDS_TEST` → 0 without elevation) — the app still
  elevates for exactly one thing, the power assistant task
* a DEVMODE freshly copied from the `EnumDisplaySettingsW` mode list
  carries an **empty `dmDeviceName`** and every change requested
  against it answers −2 (the "monitor unplugged itself" illusion);
  changes base on the *current* mode, falling back to
  `ENUM_REGISTRY_SETTINGS` for a display that is currently dark
* asking `ChangeDisplaySettingsExW` to give up the display that owns
  the desktop, in the same call that hands the desktop over, refuses
  with error 87 — hence the two-pass apply: enable pass (new primary
  last, `CDS_SET_PRIMARY`), disable pass, one commit releasing all
  the `CDS_NORESET` holds
* mode switches report success **before they land**: everything here
  believes the read-back, not the return code — profiles poll the
  live fingerprint until it stops moving for two seconds, and the
  window pass waits for that proof
* `SendInput` silently drops events whose `cbSize` is not exactly 40
  (the x64 `INPUT` size): with a naturally-packed 32-byte keyboard
  struct the call "succeeds" having injected nothing — a win+alt+b
  that never happened
* `ctypes.windll.user32` is one cached handle shared by the whole
  process: an `argtypes` declaration applied to it binds **every
  module** that touches it. wm.py's `POINTER(wm.RECT)` on
  `GetWindowRect` screened display.py's structurally identical
  `wintypes.RECT` (ctypes checks class identity, and the error message
  helpfully calls both "RECT") — and it only died on the first real
  absence after the window-restore commit shipped, which is how a bug
  survives a day of live use. Any
  struct-pointer argument on a shared handle is declared `c_void_p`
  now; the layout suite pokes both modules to keep it that way
* the shared-handle trap has an easy variant: power.py already calls
  `ShellExecuteW("runas")` through the cached `windll.shell32`, so
  wm.py's `launch()` argtypes bind on a fresh `ctypes.WinDLL("shell32")`
  handle instead — same lesson, private copy
* a pinned app's re-open is a bare `ShellExecuteW` of the exe the
  pin recorded (exactly what a double-click runs), and that is the
  whole trick — store apps and stub launchers start nothing under
  that name, which is why browse (point the pin at the launcher that
  works) and the pin's own wait timer exist, and why success is
  judged by a window appearing, never by what launch returned
* `CTkToplevel.__init__` pumps the **entire event loop** (its
  Windows titlebar-colour dance does `withdraw(); update()` to force
  a redraw): a dialog created inside an `after()` callback runs every
  due timer right there — the window suite's `after_install`, and its
  destroy tail, ran early inside a probe and killed the app
  mid-assert. Automated suites set
  `_deactivate_windows_window_header_manipulation = True` (CTk's own
  escape hatch); no probe reads titlebars
* customtkinter constructors call `update_idletasks()` — building a
  VISIBLE pane in place paints every half-built stage, so a whole
  pane rebuild looked like the entire window redrawing on every
  click. The profiles pane is double-buffered: each render builds
  its body UNPACKED (intermediate paints land on an invisible
  frame), destroys the old body and packs the new one as a single
  swap; the anchor frame is packed once and never touched. The pane
  is ALSO split into named sections (live list, editor, seats,
  status), so a click rebuilds only the section its handler changed
  — whole-pane rebuilds felt laggy per click however invisible the
  swap was made, and a selection click now just re-highlights the
  existing row buttons without rebuilding anything
* the shell never tells a launched app WHY it launched it:
  `explorer.exe` parents the Run key, the Startup folder and a
  plain double-click alike, and process-parent checks stop there —
  so recognizing one's own logon copy can only be a fact the app
  stamps on its entry (`--autostart`, exactly what Opera and
  Battle.net do; the live HKCU Run key on this machine proves the
  custom) and reads back from its own argv; `startup.selfheal()`
  teaches the stamp to old flagless entries, and to nothing else —
  an entry whose PATH differs is a moved folder, a difference with
  meaning that the switch note explains instead of touching
* **HDR state is readable after all** (monitor_control exhausted the
  wrong candidates and this project ran on *belief* for months):
  `DisplayConfigGetDeviceInfo` answers per target — type 15,
  `GET_ADVANCED_COLOR_INFO_2` (OS build 26100+), carries the honest
  `activeColorMode` (SDR/WCG/HDR) plus the panel's capability bits,
  and type 16 SETs it directly. Proven here end to end, unelevated:
  SET → read back → restore
* the old type 9, `GET_ADVANCED_COLOR_INFO`, is what poisoned the
  well: it conflates HDR with wide-gamut colour and on this desk
  answers "supported + enabled" for the panel that has no HDR at
  all — an answer from it is never an HDR fact, only "cannot tell"
* the display-path *device path* is the join key: the model segment
  of `\\?\DISPLAY#IOC912B#5&...` **is** the EDID identity we store;
  the *friendly* name is a marketing string and a different one
  (this desk's `IOC912B` answers to "GA27W1Q") — joining on it
  loses
* the adapter LUID + id the colour calls want come from the **mode
  entry of the target side**, never the source side (the source
  LUID is the GPU's), and an HDR change re-enumerates the display
  paths: cached mode indices across a SET are stale — wm.py
  re-walks the topology on every call
* config files are the user's own turf (`%APPDATA%`), hand-edited by
  design, and the app must survive it: both `config.toml` and
  `profiles.json` are written atomically (temp file + `os.replace`),
  and one that fails to parse is renamed to `.corrupt-<timestamp>`
  instead of being silently swallowed by the next save — the
  half-typed edit stays recoverable
* **nobody can cheaply ask whether the monitors are lit** - Windows
  only *broadcasts* power transitions; there is no user-mode "display
  on?" call worth its cost. So a fresh instance must never assume on
  (a restart during a dark spell silently loses the wake - measured:
  off at 14:08, restarts after, screens stayed dark on a sleeping
  desk): the machine starts `unknown`, resolves it from the first
  broadcast, or from a one-time **idempotent** `SC_MONITORPOWER ON`
  at the first proof of life (typing or a camera hit - ON onto lit
  screens is a documented no-op), and an external OFF broadcast is
  *adopted* into the off state so a power-plan sleep cannot leave the
  app believing in lit screens it will never wake
* `GetLastInputInfo` is per-session; a locked workstation counts as idle
* exclusive-fullscreen games swallow the standby broadcast
* NVIDIA Broadcast/VCAMDS drivers spam stdout when any camera opens; the
  noise is the driver, not us (redirect it, it is harmless)
* two threads calling `cv2.VideoCapture()` at once (the monitor polling
  while the settings window enumerates indexes) makes the VCAMDS driver
  throw `Interprocess mutex timeout ... owner died without unlocking`
  and OpenCV raise a C++ exception that kills the thread; every open and
  enumerate now goes through one `camera._open_lock`, and the state loop
  survives a failed grab instead of dying with it
* pystray is a trap: the constructor is `Icon(name, icon=, title=,
  menu=)` — the image keyword is `icon=` and a wrong `image=` is
  swallowed by `**kwargs`; the icon starts HIDDEN and the default setup
  callback is what sets `visible = True`, so passing your own `setup=`
  silences NIM_ADD entirely (the Shell never sees the icon; pystray
  logs nothing). `scripts\visible_test.py` spies on `Shell_NotifyIcon`
  and prints every code/result if the icon vanishes again
* PnP camera order and OpenCV indexes do not necessarily match; use
  `camera.index` or `camera.name_contains`
* model weights (yolo11n.onnx, 10.7 MB) download once into `models\`;
  mirrors in `awaywatch/inference.py`

## Status

v1: state machine + tray + settings window (CustomTkinter) with the
embedded debug camera view, live-apply controls and the skin seam
(`modern` today, `fun` is a palette stub awaiting its design). Still
scheduled: fun-skin details, per-event log viewer, face-identity gate
 polish.
