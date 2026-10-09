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
| **two** unexpected wakes within `wake_burst_window_sec` (120 s) and nobody ever seen | auto re-off **pauses**: screens stay lit while the desk keeps producing input, a toast says the camera (index N) never saw a person — the slipped-off-the-monitor case; re-arms when a person is confirmed, the policy changes, or `Resume auto re-off` (tray/window) |
| another app already holds the display awake (video wake lock, a game, a presentation) | camera polling **stops** while the block is active (no point defending a screen someone else owns); the window's power assistant shows who holds it, and polling resumes when they let go |
| fullscreen app owns the display | the broadcast is skipped (the message never reaches the swap chain) |

Timers, camera modes (`boot_per_poll` / `always_on`, one choice per
phase), the wake policy and the overrides below are all editable from
the settings window — three tabs, one subject each: **detection**
(mode; the model's knobs or the differencer's — they never share the
screen; the timers; the live preview beside the camera picker),
**power plan** (the timer overrides here, the wake behavior, the
powercfg assistant), **General** (the meta: skin, autostart, updater,
logs).
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
