# PanelBoss

Presence-aware display control for Windows. Offline, per-user, tray-resident.

PanelBoss decides whether anyone sits at the desk and dims, darkens, or locks
the displays accordingly. OLED-care features keep still pixels from aging
into the glass. Movie theater mode darkens the desk around a playing video.
Monitor profiles store and restore a whole desk. Presence runs locally from a
camera; nothing leaves the machine except the handshake with the optional
companion browser extension.

## Screenshots

<!-- App art lands before launch. -->

## How to

### Install

Download `PanelBoss-<version>-user.msi` from
https://github.com/Nocterrible/panelboss/releases. Per-user: no admin, no UAC
prompt at install, uninstall, or upgrade. The app lands in
`%LOCALAPPDATA%\Programs\PanelBoss` with a Start Menu entry. Autostart is an
in-app opt-in (General tab), never silent. Uninstall removes the app's
scheduled task, its Run-key entry, and re-lights any display the app left
disconnected. Settings and logs live in `%APPDATA%\PanelBoss` and survive
everything around them. First launch has camera detection off: no eye opens
until you turn it on, and turning it on offers a setup that opens every
camera once and lets you label, hide, or put on duty up to four.

**From source (git):** clone https://github.com/Nocterrible/panelboss, make
a virtualenv on Python 3.10+, install `requirements.txt` - or run
`scripts\setup.ps1`, which also fetches the detection model into `models\`.
Start with `python run.py`. The logon entry carries `--autostart`; the flag
is how the app knows a logon start. Source and MSI share `%APPDATA%\PanelBoss`:
same settings, same logs. One instance runs at a time; a second launch wakes
the running app's window and exits, or shows a brief "already running" box
when nothing answers.

To update an MSI install, use **Update now** on the General tab, or
download and run the newer MSI by hand; settings and logs are untouched
in both cases.

### PanelBoss Buddy

A browser extension that reports the playing-video rectangle to the app.
That is all it does. Store listing (as PanelBoss Companion):
https://chromewebstore.google.com/detail/panelboss-companion/feolhiokchmpphlhllagimnilceldegk
The app installs the Buddy's local native-message host: the "install the
helper" button on the Movie theater card builds it and registers it under
your user account, no admin. Manual route: `extension\host\install_host.ps1`;
`extension\README.md` documents the API and the rest. The Buddy is optional;
Movie theater mode is the only feature that needs it.

### Hello IR

Hello IR puts the Windows Hello infrared sensor - the camera that unlocks the
machine - on presence duty. Hello cameras hide from normal enumeration, so
the app reads them through `whircam`, an optional MIT package. Pick "hello IR
camera (optional - pick to install whircam)" in the Detection tab's camera
menu: the app installs the bridge, relaunches, and the sensor is on duty. It
keeps serving frames while Windows Hello stays armed, and the seat can be
labelled and removed like any other camera.

## Features

Five tabs, one subject each. Above them sit the desk commands: rescue my lost
windows, restore my windows, sleep (pick minutes), Pause, Quit. Tray
left-click opens the window; right-click adds camera and mode pickers, wake
policy, pause, snooze 10/30/60, start with Windows, and Quit.

### Detection

The switch on top is consent: off, the tab grays and the note says cameras
will not open until you enable it. Person (AI) mode runs an ONNX detector
with device (auto/CPU/CUDA), GPU id, confidence (0.10-0.90) and min hits
(1-4 positive frames before the screens wake). Motion (no AI) mode is pure
frame differencing - it drives infrared and depth sensors exactly like a
webcam - and sets frame changes, pixel delta, and motion hold: how long
presence lingers after the last movement, because reading a page is stillness,
not absence.

The away card sets what "away" is, per monitor: every panel row picks its
own dark. Dim keeps panels powered and paints the dark: blackout is an
opaque cover, clicked to wake; dim drops the panel to the shared level, 1-40
percent; off (DDC fast) sends the panel's own DDC/CI power code, so the
panel itself
goes dark as if you pressed its button. On NVIDIA drivers this option starts
disabled - the vendor has a kernel bug here, and the option returns with the
driver patch; AMD and Intel desks get it on day one. off (disconnect) - the default for
rows you never touched - retracts the signal at the adapter, and Windows
refuses to strand the last active display. An unworded row follows the
legacy [away] mode key before the default. Lock when away starts ends
the session too: panels wake to the lock screen. Preview tries a row for
10 seconds and reverts; the second click cancels.
Some panels refuse DDC/CI writes - a KVM often explains it - and the app
reports it, never hushes: an accepted write that never proves itself reads
(unverified) on its row, a refused write falls back to painted blackout, and
the row says which.

The Timers card holds the seconds: idle gate (0-180, no camera while input is
recent), absence confirm (10-300), poll while on and first dark re-poll
(1-15), the always-on re-read gates (1-15, 5-15), present recheck (10-300),
re-off grace (0-120), leave-on grace (10-600). The card prints the result:
dark N seconds after the last keystroke.

The Camera card adds cameras from a picker; an on-duty camera leaves the menu
and gets a policy row. Labels ride the camera's hardware identity, so a
replug cannot lose a name. Rescan re-scans and re-tests; a camera that serves
no frame is marked "(no image during diagnostic)". Duty is set per screen
state - boot per poll opens and closes the camera once per poll, always on
holds the stream open - and each camera overrides: follow-global, poll,
always on, off. Four cameras is the duty limit. Live preview shows the exact
frame the detector judged; hidden cameras get a show button.

### Power plan

Two override rows, screen power off and sleep, each answering off, on, or
while present (camera). The power plan itself changes nothing: its timers are
held from firing while the app watches, and handed back when it pauses,
snoozes, or quits. While present holds only while the camera's last verdict
sees a person; absent or no-verdict hands the timer to the plan on the spot.
The choice is grayed, never hidden, while detection is off - and if the eye
goes quiet mid-watch, one tray notice says it: the camera stopped seeing,
presence-based behavior paused until it sees a person again.

The wake card picks re-off or leave-on for unexpected wakes, can hold off
while a fullscreen app owns the display, waits for a resume after two
unexpected wakes in a row, and can put window positions back after wake. The
powercfg assistant is opt-in: one admin confirm registers a task that reveals
which processes hold the display awake; the card lists them, and while one
holds, the camera stops defending a screen it does not own. Gaming, right
column, is off by default. A fullscreen game takes the panel's picked rate
(auto, an explicit Hz, or VRR pin-max for G-SYNC you enabled yourself);
outside games the desktop rate is law, keep being the no-rule answer;
HDR-precise drivers get a desktop hdr on/off/keep pick. Listed exes enter
the moment they own a monitor, anything else must hold sustained 3D load or a
controller api, and the grace timer keeps alt-tabbing from flickering the
panel. A power plan can swap in per game; the previous one returns after.

### Monitor profiles

One profile is the desk spelled out: which physical panels by hardware
identity, their places, the primary, resolution and refresh per panel, the
HDR ask, and where every pinned window belongs. The picker opens on the
profile matching the layout you see; create new... copies what the desk is
doing now. The mode editor offers each panel resolution and refresh menus
from the driver's own list, its live HDR state, and, where the driver answers
precisely, a hdr on/off/keep selector. The hdr ask per apply: restore as
captured, ignore, or force all capable panels on or off; on Windows 11 24H2+
disagreements are commanded and read back, on older Windows restore skips
itself rather than guess. The desk gate refuses to apply onto panels the
profile does not name; try anyway (best effort) appears only then. Applying
waits until monitors answer, moves windows, and rescues stragglers off-screen.
Pins reserve seats: a process-matched pin moves every window of that app,
process-plus-title is the one-window road, and open it if missing launches
the exe - 5 s to 10 min of patience, browse field for launchers and
shortcuts. Restore-at-start re-applies a profile at launch: any profile or
the last one for this desk; whole desk, monitors only, or windows only; on
logon starts, proved by the Run entry's --autostart, or every start. Restore
my windows moves pins only and asks the drivers nothing.

### OLED

The taskbar hider paints a strip over the bar's fixed pixel row, opted in per
monitor. It steps aside for the cursor and covers again after 1-30 seconds;
reveal is per bar or all bars; the card flags a clash with Windows' own
auto-hide. Panel refresh walks the app's strips and veils around a zero-drift
ring every 5-180 minutes, 1-8 pixels a step; the wash is a request, never a
schedule - run wash now lights opted-in panels white for ten seconds, once.

The dimmer card arms background dimming, opted in per monitor. After dim
after (0 to 60 seconds of stillness) every background window wears a veil
at veil level, 10-90 percent, with per-panel overrides. The foreground and
anything making sound keep their light; menus, tooltips, and transient popups
never dim; administrator windows stay bright unless PanelBoss runs elevated,
which is not recommended. Always dims a panel without the idle wait - that
row yields to the foreground, never to motion. The window playing your video
never wears the dim layer, backgrounded included; pause the video and the
dim layer comes back. Fade
within (0-60 s) shapes the return; lift fade decides whether a plain veil
fades or drops the instant you touch the desk. Apps are excluded by exe name;
a pause hotkey binds on keypress, clears on esc, and is unbound until you
give one.

The pump row asks: does your shit occasionally decide it wants to keep
Windows awake? Some devices (macro pads, KVMs, jigglers) keep telling Windows
someone just typed; the pump makes PanelBoss trust only real movement, and
every idle timer reads it. Switched off, the app uses Windows' own idle clock
verbatim. It takes a relaunch to change; a deaf pump falls back to the system
clock by itself.

Movie theater mode is the Buddy's payoff, consented separately. Once a video
plays and input sits still for the veil-after wait (1-30 s), a ring of
darkness hugs the video itself: the hole is the video's own rect, so the
page and the browser's chrome wear the darkness with the desk. The window
playing your video never dims. Motion lifts the ring, which re-arms after the
same wait; a film's sound never lifts it. When the video covers its panel
that panel has no room to ring - the darkness lands on the other enrolled
panels only. (The calmer window-hole shape - a ring around the whole window,
chrome and page bright - is one config word away: [videodim] hole =
"window".) Theater veil level (10-90 percent)
is the frame's own darkness, independent of the dimmer's, per-panel
overridable. Per-monitor boxes enroll panels: an enrolled panel with no video
wears a full-field veil while the conjunction holds; an unenrolled one dims
like any idle desk. Fade out is the opt-in; the lift is instant by default.
The card carries open store page, install the helper, the doorway file, the
host's capability line, and measure now for a one-shot geometry check.

### General

Skin picks the palette; layout and behavior are identical. Start minimized to
tray applies next launch - closing the window always hides it to the tray
anyway. Start with Windows writes the per-user Run key, the entry Task
Manager's Startup tab lists, and reads the registry back to be sure; if the
entry points at a different copy, the note says so and a flip re-points it.
Check for updates asks GitHub what the latest release is; Update now
applies it - a source install pulls and refreshes dependencies, an MSI
install fetches the newer MSI and hands the switch to Windows Installer.
Open log folder opens the log folder.

MIT. Plans and known gaps: `AUDIT-PUNCHLIST.md`.
