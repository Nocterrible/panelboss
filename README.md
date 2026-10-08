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
| absence confirmed `absent_confirm_sec` (60 s) | `SC_MONITORPOWER(2)` — same standby as the power plan, worst case 90 s after the last keystroke |
| screens dark | camera held open, polled every `off_poll_sec` (3 s) |
| `min_hits` (2) consecutive positive frames | camera released **before** the screens wake (the device is exclusive) |
| screens wake on their own (mouse jiggle) | `wake_policy = "re_off"` (default) turns them off again after `re_off_grace_sec` unless `min_hits` people show up; `"leave_on"` hands them back for `leave_on_grace_sec` |
| **two** unexpected wakes within `wake_burst_window_sec` (120 s) and nobody ever seen | auto re-off **pauses**: screens stay lit while the desk keeps producing input, a toast says the camera (index N) never saw a person — the slipped-off-the-monitor case; re-arms when a person is confirmed, the policy changes, or `Resume auto re-off` (tray/window) |
| another app already holds the display awake (video wake lock, a game, a presentation) | camera polling **stops** while the block is active (no point defending a screen someone else owns); the window's power assistant shows who holds it, and polling resumes when they let go |
| fullscreen app owns the display | the broadcast is skipped (the message never reaches the swap chain) |

Timers, camera modes (`boot_per_poll` / `always_on`, one choice per
phase) and the wake policy are all editable from the settings window
(or the config file — same values).

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

The Behavior card has a **power assistant** checkbox: `powercfg
/requests` requires administrator privileges, so the app cannot simply
ask. Ticking the box registers a tiny scheduled task (one UAC confirm,
yours to give) that dumps `powercfg /requests` to a file the app reads
silently afterwards — who keeps the display awake is listed under the
box, and camera polling stops while a display-class blocker is alive.
Unticking removes the task. With the box off, the app never elevates
anything and simply keeps polling (fail open).

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
update.bat                              # pull + reinstall + relock
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

Autostart at logon: `powershell -File scripts\autostart.ps1 install`
(Task Scheduler; the tray Quit menu remains the only way to stop it
otherwise).

## Face identities (optional)

`faces.enabled = true` makes only enrolled identities count as presence:

```powershell
.venv\Scripts\python.exe -m pip install insightface
.venv\Scripts\python.exe -m pip uninstall -y onnxruntime
.venv\Scripts\python.exe -m pip install onnxruntime-gpu   # after every
                                                          # pip upgrade
.venv\Scripts\python.exe -m awaywatch enroll --name you
```

## Things this machine taught us

* raw `SC_MONITORPOWER` broadcasts do **not** emit `GUID_MONITOR_ON`
  notifications — display state is tracked from commands, input activity
  and the camera; the power sink still listens for power-plan transitions
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
  HIGHEST-task that the non-elevated app starts with `schtasks /Run`
  (no UAC after the one-time confirm) and reads via a dump file
* message-only windows receive notifications only on the thread that
  created the window, and that thread must have created a message queue
  (`PeekMessage`) first; every handle is `c_void_p` so 64-bit values never
  truncate through `int`
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
