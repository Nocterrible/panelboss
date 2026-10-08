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
| fullscreen app owns the display | the broadcast is skipped (the message never reaches the swap chain) |

Timers, camera modes (`boot_per_poll` / `always_on`, one choice per
phase) and the wake policy all live in the config file.

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
* message-only windows receive notifications only on the thread that
  created the window, and that thread must have created a message queue
  (`PeekMessage`) first; every handle is `c_void_p` so 64-bit values never
  truncate through `int`
* `GetLastInputInfo` is per-session; a locked workstation counts as idle
* exclusive-fullscreen games swallow the standby broadcast
* NVIDIA Broadcast/VCAMDS drivers spam stdout when any camera opens; the
  noise is the driver, not us (redirect it, it is harmless)
* PnP camera order and OpenCV indexes do not necessarily match; use
  `camera.index` or `camera.name_contains`
* model weights (yolo11n.onnx, 10.7 MB) download once into `models\`;
  mirrors in `awaywatch/inference.py`

## Status

v1 is the state machine + barebones tray. The full UI overhaul (live
status, per-timer tuning, log viewer) is scheduled for v2; the queue is
already long.
