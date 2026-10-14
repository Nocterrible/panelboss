# PanelBoss changelog

## Unreleased - 2026-10-14 waves (rc-2026-10-14b)

- Away modes: blackout, DIM (HDR off + brightness dip, honest
  readback, preview), and OFF (the panel's own power code 0xD6
  through the retrying brightness door; "off (unverified)" is the
  universal word - a witness-tested panel goes DPMS-dark on a
  write its own register refuses to confirm; its preview counts
  the seconds on the settings window, the dark panel cannot carry
  a digit). A display sent OFF is retracted at the adapter level and
  the state survives the app - Windows Settings -> Display brings it
  back, and Windows itself refuses to disconnect the last active
  display. A boot belt re-lights any off-row left dark by a
  crash or quit.
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
