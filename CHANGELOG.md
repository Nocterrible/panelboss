# PanelBoss changelog

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
