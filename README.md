# PanelBoss

PanelBoss is a Windows tray app that manages the desk around you. It
watches a webcam, decides whether someone is at the desk, and dims,
blacks out, or locks the monitors when you leave. It drops a dark
veil over the background windows of every monitor you opt in, and
with the companion browser extension it frames a playing video and
dims the desk around it: Movie theater mode. It also automates
gaming refresh rates and HDR, hides the taskbar, jogs pixels against
OLED burn-in, and restores your window placement after the screens
go dark. It runs offline: no telemetry, no phone-home, no listening
port. The only inbound path is the companion's native host, writing
one file into a folder PanelBoss owns.

## Why

The second monitor glows at 1 am because nothing told it you left.
The movie plays while the chat window beside it burns at full
brightness. The desk stays lit when the room is empty. PanelBoss
closes those gaps with rules you set once.

## Install

Windows 11, and Python 3.10+ on PATH (setup tells you if it cannot
find one). Clone, set up, run:

```powershell
git clone <this repo>
cd <the repo directory>
powershell -File scripts\setup.ps1
run.bat
```

`setup.ps1` builds a project-local `.venv` (the base environment is
never touched), installs the pinned dependencies, and downloads the
~10.7 MB person-detection model into `models\`. `run.bat` starts the
windowless interpreter: the console that blinks for a moment is
cmd's own window, gone when the app starts. From then on PanelBoss
lives in the tray, no console. `update.bat` pulls and reinstalls
later; the app's Update button runs it and relaunches. A packaged
installer (MSI) is planned; today the repo flow is the truth.

## First run

A tray icon appears, a "running" toast confirms it; on a fresh
Windows 11 box it hides behind the taskbar overflow chevron until you
drag it out. The icon is a circle; its palette names the states (green
present, yellow camera polling, dark gray screens off, orange paused
or snoozed - the recolor hook is in, the state wiring lands with the
UI pass). Left click opens the settings
window; right click gives the menu (Settings, camera and mode
pickers, wake policy, rescue/restore my windows, Pause, Resume,
Snooze, start with Windows, Quit).

The window has five tabbed cards: detection, monitor profiles, power
plan, oled, general. Everything applies live: controls write the
config the engine reads every tick. And no camera opens until you
say so: the detection tab's switch is consent, not decoration.

## Features

### Away

When you are active, nothing runs; after an idle gate the camera
boots per poll and votes, so its LED blinks and you always know it
is watching. Absence confirmed and the screens go dark, the same
standby the power plan uses. Or set away mode to dim: the panels
stay awake and the app paints the dark instead, per monitor one of
blackout (a black overlay), dim (the panel drops to your level, 1 to
40 percent), or off (the panel's own power code). Set a deep-sleep
timer and the painted dark gets a second stage: after that many
minutes away the panels also take the power-off code, the GPU stops
presenting, and the wake on return takes a beat longer - the trade
for a panel that truly rested. The pointer is parked at the bottom of
the lowest monitor when away engages, and stays there when you return:
nobody remembers where their cursor was after leaving the room.
Optional lock-on-away ends the spell with LockWorkStation: the panels wake to
the lock screen, not to your desktop.

### Window dimming

Opt a monitor in, and when input has been still for a moment every
background window on it gets its own dark veil. Each panel can wear
its own darkness percent. The foreground window is never veiled, an
app that starts making sound lifts its own veil the tick the sensor
learns it, and you can exclude named apps. Menus, tooltips and other
transient popups are never dimmed either - a context menu you are
about to click is foreground by nature, and the veil reads the window
style, not the class name, to know one. The taskbar follows the same
law: permanent chrome does not get dimmed; the taskbar hider paints
it when you want it gone. (A borderless *game* window is not a popup:
it keeps dimming like any background app.) When input returns the
veils are gone the same tick; a fade toggle opts into a soft lift
instead. The pause hotkey is bound from the card (press a key, esc
clears): unbound by default, no chord is stolen before you consent.

### Movie theater

Needs the companion. It measures the playing video and hands the
rectangle to PanelBoss, which dims everything around it: four dark
pieces frame the video. The movie's sound does not lift the veil.
The theater engages when a video is playing and input has been
still for your idle delay (1 to 30 seconds); the darkness level is
yours. Other monitors can wear a full-field veil while the movie
runs. A fade is optional; instant lift is the default. The
companion's API is open, documented in `extension/README.md`.

### Gaming

A fullscreen game takes the rate you picked for its panel; when it
lets go the panel returns to your desktop rate, and the desktop rate
is law while no game owns the desk (after a reboot drops the desk to
60 Hz, the app snaps it back). Evidence decides: sustained 3D-engine
GPU load, a controller API, or a spot on your games list; alt-tabbing
does not flicker the panel. VRR: mark a G-SYNC panel and PanelBoss
pins its highest rate instead of flipping modes. HDR: a desktop
state per panel, plus an automatic tier that turns HDR on while
video plays (decoder counters, or the mpv IPC pipe). A power plan
can be swapped in when a game starts and the previous one handed
back after.

### Hider

A black strip painted over the taskbar, per opted-in monitor, so the
bar's fixed pixel row stops aging an OLED. It retracts the moment
your cursor enters the bar and covers again after a few seconds
away; a caret in the search box holds it back. It is an ordinary
window: it dies with the app and strands nothing.

### Jog

Panel refresh: the app's own strips and veils step around a small
ring of offsets every few minutes (5 to 180), so no pixel line sits
still for hours. A manual wash lays a brief white veil over a monitor
when you ask; it never fires on its own.

### Placement restore

Monitors that unplug themselves on standby make Windows re-lay every
window on the return. PanelBoss snapshots each window's rect and the
monitors' hardware identity before the screens go dark, waits for
the topology to settle after any wake, and moves everything back,
but only while the same panels answer. Off by default: it moves your
windows, so it asks first. The tray's "restore my windows"
re-applies your monitor profile at any time.

### Faces

Optional. With `insightface` installed and identities enrolled
(`panelboss enroll`), only known faces count as presence. Off by
default.

## The companion (browser extension)

The companion measures the playing video on the streaming sites the
manifest ships with and hands the geometry over native messaging:
the browser starts a small local host, the host writes one file. No
port, no debugger banner, no pairing token; the dead alternatives
are listed with their causes in `extension/README.md`. The host
registers under your user account's registry key (no admin), and
Chrome, Edge, and Opera read the same key: one install covers all
three. The install button lives on the Movie theater card. The
extension is on the Chrome Web Store soon; today you load the
`extension/` folder unpacked and press the button.

## Config

`%APPDATA%\PanelBoss\config.toml`, hand-editable: the file is yours.
Bad values clamp to the rails or warn and fall back to the default;
a config that will not parse is renamed aside rather than silently
overwritten, so the app never bricks on a typo. Logs are in
`%APPDATA%\PanelBoss\logs`.

## Privacy

Local only. Camera frames are judged in memory and never written to
disk; the camera diagnostic stores verdicts, not pictures. The app
opens no listening socket, and the companion's native host (one file
write into PanelBoss's own folder) is the only inbound path; the
optional mpv probe only answers a question PanelBoss asked its own
player. The model download at setup is the only network call, and
you can drop the file in yourself and run fully offline.

## Developers

`panelboss/` is the app: state machine, tray, settings window, the
`wm/` display plumbing, the companion reader (`nmhost.py`).
`scripts/` is the test gauntlet: `powershell -File
scripts\run_all.ps1` runs all 51 suites (exit 0 = ALL GREEN; honest
green wants the app stopped; a sweep that skipped window sections
says DEGRADED). `extension/` holds the companion source, `models/`
the yolo11n.onnx weights. Run from source after setup:
`.venv\Scripts\pythonw.exe -m panelboss` (setup.ps1 prints the same
line). `scripts\make_icon.py` builds `assets\panelboss.ico`;
`extension\host\install_host.ps1` builds and registers the host exe
with PyInstaller, and the Movie theater card's button runs that same
script.

## Screenshots

<!-- TODO(owner): tray menu, dimmed desk, theater ring, card grid -->

## License

MIT, see `LICENSE`.
