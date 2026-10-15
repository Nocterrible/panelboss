# PanelBoss changelog

## 0.4.0 (in development)

- Panel refresh (OLED tab, second card): micro-jog steps the app's
  covers around a zero-drift ring every 5-180 minutes (1-8 px), and a
  manual 'run wash now' button lights one opted-in monitor white for
  ten seconds. Per-monitor opt-in, default off; wash is a request,
  never a schedule; the app states plainly that it cannot read panel
  wear counters (this desk's registers were caught lying).
- Background dimmer (OLED tab, third card): an idle desk lowers a
  dark click-through veil over every background window on opted-in
  monitors - the window you touch lifts instantly, and so does
  anything the WASAPI sound sensor HEARS (a just-silent app keeps
  its brightness four more seconds; the hysteresis is ours, not the
  API's). The veil geometry reads the DWM frame bounds - the GDI
  rect lies by eight pixels around every rounded window (measured).
  When input returns the whole field fades in at most three alpha
  steps within the ramp (3-60 s): a dimmer that blinks is a
  screensaver. Exclusions edit in the card; the pause toggle binds
  press-to-key (owner law: UNBOUND by default, no stolen chords
  before consent - the app registers the hotkey only while the
  window's pump lives, binding while headless answers with a dated
  word and retries once a pump exists, and a taken combo keeps its
  predecessor and says so). The config writer learned to omit None:
  TOML has no null, and the first None default would otherwise have
  made the next launch call the whole file corrupt and reset every
  setting.
- Fixed: a stuck morning blackout on the way to this release - the
  cursor jail's Win32 verbs rode the shared user32 handle UNPINNED,
  correct only while some other module pinned them first, and an
  import-order shift made `GetCursorPos` read the stack as garbage.
  The raise fired between overlay-paint and the lift arms, so the
  black never lifted. The verbs are now self-pinned and the jail
  degrades to a bool instead of raising into the spell. The hider's
  bar census got the same soft-fail. If a spell ever sticks again:
  Win-key exposes the tray, right-click quits, the strips are
  ordinary windows and die with the process.

- Boot fix (owner UAT, Oct 15 night): the settings window died at
  birth on every launch since the hiders boot hooks - the hiders
  painter Tk raced the windows for tkinters process-global default
  root and won it, and customtkinter binds every image to that
  default, so the kofi cup landed in the painters interpreter and
  the window raised `image `pyimage1` doesnt exist`. The boot
  containment then destroyed the OTHER threads root - the
  cross-thread Tcl deadlock that also ate the traceback (the log line
  now runs before the destroy, and the destroy refuses roots it does
  not own). The painter waits for the windows root instead (a
  headless boot waits 10 s and claims). The second instance answers
  the click now too: the loser pokes the winners window open through
  the trays own seam and falls back to the balloon only after two
  seconds of silence.

- Taskbar hider (new `oled` tab): a painted black strip over each
  opted-in monitor's taskbar - the OLED burn-in defense. Hover bares
  the bar you reached for (or every bar, your choice); it returns
  after a settled pause, held indefinitely while a caret sits in the
  search box. Per-monitor opt-in, default all-off. Windows' own
  auto-hide WRITE (ABM_SETSTATE) is a no-op on 24H2+ - measured, not
  folklore - which is why the app paints its own strip: it lands
  instantly, dies with the process, and cannot strand a taskbar.
  Known limit, said plainly on the card: apps that queried the work
  area do not learn the bar is covered, so a fullscreen may slip
  behind the strip.


## 0.3.0 - 2026-10-14 (rc-2026-10-14b, UAT build ec02a76)

- Away modes: blackout, DIM (HDR off + brightness dip, honest
  readback, preview), and OFF in two flavors. D6 off sends the
  panel's own power code 0xD6 through the retrying brightness door;
  "off (unverified)" is its universal word - a witness-tested panel
  goes DPMS-dark on a write its own register refuses to confirm
  (trust, and its preview counts the seconds on the settings window,
  the dark panel cannot carry a digit). DISCONNECT off ("off
  (disconnect)") retracts the path at the ADAPTER via
  SetDisplayConfig - works regardless of firmware (the panel loses
  its signal, never hears a code), comes back as a replug, and its
  dark is the one this app can PROVE: the display store is re-queried
  and the intended target is seen gone ("off (disconnected)"). The
  retracted state lives in Windows' own display store and SURVIVES
  THE APP - an uninstall leaves the desk as stored; Settings ->
  Display is always the recovery door, and the boot belt answers from
  inside: any row this app configured offdisc is re-raised at the
  next start (Windows itself refuses to disconnect the last active
  display; that guard degrades the row to blackout with the dated
  word, like every refusal). A boot belt also re-lights any D6-off
  row left dark by a crash or quit. Lock-on-away ([away] lock, default off, a checkbox
  on the away card): a real dim engage that darked at least one row
  also runs LockWorkStation - Windows locks when nobody moves, this
  locks when nobody is HERE. A preview never locks. Behind the lock
  the spell lifts on the camera's presence eye (the stream is ours
  and runs through the lock) and on the watcher's WTS session-unlock
  ear, not on the mouse (raw input is per-desktop and deaf behind
  Winlogon); a returning face gets the lock screen, never somebody
  else's desktop.
- Loud-voice profiles, the profile apply refusals that speak at
  the gaze, and a chain-teardown fix (full app-down gauntlet
  green).
- Freeze fix (hdrwake class) and the INPUT ORGAN SWAP: LL hooks
  replaced by RAWINPUT with verified INPUTSINK - the mouse lag
  class is gone (0.02-0.06 idle cores).
- Cadence: first-dark re-poll and the two degraded-eye re-read
  gates as sliders; dark always-on floor at 1 s - a hand-edited
  [camera] value outranks the slider until moved.
- Known behavior (owner-visible): unchecking every camera leaves
  camera 0 on the next restart.

## 2026-10-13 - 0.2.0 (audit fix waves 1-3)

- Config hardening: junk settings fail open loudly instead of
  wedging the app, and saves are single-writer - a setting that gets
  mutated mid-save now retries instead of writing a torn file.
- Presence-state re-arm: snooze and pause never freeze the camera
  loop, and released eyes cast no verdicts while a state is held.
- Camera engine: mono and zero-size frames abstain instead of
  crashing, a wrong .onnx model confesses at build, dead open-lock
  deadlines are enforced, and one handle gets exactly one release.
- Profiles: only one apply runs at a time, and corrupt rows die at
  load - real shapes never do.
- Every daemon confesses: a tray icon death is fatal-loud, a dead
  watcher closes the loop, and worker failures box or log - never
  silence.
- Display/WM: per-monitor apply truth, a handle-trap sweep,
  localized powercfg decoding, and the power plan comes home after
  a crash.

Known deferrals: see AUDIT-PUNCHLIST.md BACKLOG
