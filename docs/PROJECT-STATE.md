# PanelBoss — project state & roadmap

Living document. State as of 2026-10-11 (master `6affd91`). The
history-shaped truth lives in git and `docs/` (findings docs); this file
says where the project STANDS and what DONE looks like.

## What it is

A Windows tray app that commands the desk's displays: camera presence
decides screen power, per-monitor law decides refresh rates, profiles
decide whole-desktop states. Fail-open by religion, no cloud, no
admin. **MIT licensed** (2026-10-11). Distribution is
**installer-first** (owner decision 2026-10-11): the shipped artifact
will be a per-user installer wrapping the PyInstaller onedir build;
the portable git-clone + venv path stays the developer experience.
PyPI name `panelboss` (0.0.1 placeholder), GitHub
`Nocterrible/panelboss` (private), Ko-fi `ko-fi.com/nocterrible`.
Renamed from "ICU Presence Detector" at 0.1.0.

## Shipped (all live-verified on the dev desk, 22/22 suites green)

- **Presence engine**: person/motion/both detection (ONNX DirectML/CPU,
  optional face identities), two-tier borderline law, idle gate, faster
  polling while dark, `min_hits` confirmation, wake-burst learning
  (two pointless wakes = your phone moved the mouse, stop waking for it),
  pause/snooze, unknown-state boot (power-on first, never gamble).
- **Screen law**: holds display+sleep execution requests while a lit
  desk is watched; releases on dark/quit; another app's wake lock is
  detected, shown and yielded to (`powercfg /srw` truth, PDH-backed
  video-sync watch, reboot-pending).
- **Refresh-rate law**: per-monitor `desktop_hz` held outside games;
  game-time modes via `gaming` watcher (foreground-fullscreen + GPU-load
  evidence, seen_secs debounce); VRR is owner-declared per monitor
  (`VRR (pin max)` — pinned at max, zero mode flips, exempt from
  switch-off hand-back). The app NEVER writes NVIDIA driver settings.
- **Profiles**: named whole-desktop states (modes, HDR, window seats)
  with login restore, topology rescue (windows that fell off the desk
  when a monitor slept), rescue-undo, `reg`/`hdr`/custom, edit UI.
- **Tray + identity**: pystray, GUID-keyed slot (`uuid5("panelboss.tray")`)
  — one stable identity across venv/base/frozen launch paths, pins
  survive updates; icon ready ~1 s (light menu first, warm swap ~15 s);
  refuse-GUID reclaim-before-demote fallback; pystray-version warning.
- **Cameras (0.2 direction now, see below)**: rotation up to 4 eyes,
  round-robin voting, `[camera.on]/[camera.off]` per-index policy tables
  over `boot_per_poll|always_on|off`, wear guard (hour cap + 10 s fallback
  poll, re-arm on the edge into always), preview mosaic (labeled honest
  tiles), dead-lone-eye fail-closed, hello-IR path, name-match roster.
- **Settings UI as a package** (split #1 done): `ui/window/` = facade
  `__init__` + 14 modules (constants, widgets, runtime loop, one per
  tab, profile sub-parts, shell) - AST-proven pure move of the former
  3088-line `window.py`; every file <= ~350 lines, SIZE LAW clean.
- **Shell**: autostart via Run key (verified by re-read),
  `update.bat`/`run.bat`, `build_release.ps1` + `run_exe.py`
  (PyInstaller path staged), config writer (atomic, round-trip tested),
  rotating logs, `--autostart` proof-of-origin flag.
- Requires Python 3.10+ (Windows). The full test suite is
  `scripts/run_all.ps1` (22 suites); the UI suites SKIP their window
  sections while the live app holds the single-instance mutex, so an
  honest full-green claim needs the app stopped.

## In flight

- Split #2 DONE (wm/ = 9 parts + fan-out facade; AST-proven, gate
  PASS 118/118 incl. independent setattr-fanout probe). Next:
  `state.py`, `profiles.py` at their next-touch
  occasions; ~15 further files >300 lines carry no note yet - the law
  grandfathers them until touched, the split series retires them in
  order.
- Live-walk (Oct 11, architect, headless+MCP): **close->reopen PASS**
  (hide semantics: `WM_DELETE -> _hide -> withdraw`; the window is
  never destroyed in production, so the harness-only `pyimage` poison
  has no production path - `rebuild_for_skin` ×3 + clean destroy
  verified headlessly). General tab builds lazily on first select
  (blank frame <1 s - exactly the snappiness target for Phase 1).
  Tray protocol captured for scripts: message `0x40B`, lParam
   `0x202` = activate, `0x205` = menu. The tray menu itself
   WALKED: 18 items enumerated via the #32768 probe, Pause->Resume
   drove the real modal loop (menu actions are log-silent by design -
   state changes, not events). REMAINING walk items: profiles apply
   round-trip, camera picker rescan, per-camera policy TOML edit +
   second camera when the hardware arrives. Desk note: AOC2790
   unplugged - restore correctly declined the stale topology
   ("different desk right now").

## Planned end state — v1.0, in order

1. **UI Phase 1 (de-CTk + design system)** — full plan of record:
   `docs/UI-PLAN.md` (measurements, phase order, trigger table, design
   rules). The lag is render-side
   (measured: import is innocent; CTk canvas redraws on 3×4K are not).
   Per researched plan: ttk.Treeview/grid forms under ttkbootstrap or
   sv-ttk + pywinstyles dark titlebar, DPI poller off, preview lane
   (worker decode, one canvas item), ONE accent, 3 contrast tiers,
   4/8/16/24 spacing, no floating `?` chips (inline hint slot + Ctrl+K).
   Includes: **per-camera policy editor** (the tables are TOML-only
   today) and the parked focus-blip investigation (instrument ready).
   Phase-2 migration (pywebview/WebView2 first, Qt last) triggers ONLY
   on measured failure: tab build >300 ms, mosaic <20 fps, visible jank.
2. **Installer track** (license settled MIT - PyInstaller's runtime
   exception is happy): `PanelBoss.exe` keeps its version resource
   (kills the "Python" label in Windows Settings' tray page; one
   stable exe path = the tray pin and Run-key identity outlive
   updates), wrapped by an **Inno Setup** per-user installer (no
   admin, `%LOCALAPPDATA%\Programs` default, Start Menu entry,
   uninstall cleans the Run value it owns). `build_release.ps1`'s
   onedir output becomes the installer payload; `update.bat` graduates
   from git-pull to "fetch + run the new setup". Stretch: winget
   manifest once the first signed release ships.
    ICON ART DECISION (owner, Oct 11): a proper icon will be generated
    with ComfyUI on the 5090 - deferred because that evicts Infernix
    (review gate runs same-family on lane 1 while ComfyUI is up;
    re-seat START-infernix-27b-2seq.bat afterwards). The green-circle
    tray art is the placeholder; all other installer work is
    icon-agnostic and proceeds.
3. **Real PyPI 0.1.x/0.2.x**: `pip install panelboss && python -m
   panelboss` as the script path alongside the installer; needs a
   `pyproject.toml` (none exists yet - packaging is created, not
   configured); repo folder rename (venv rebuild rides with it);
   README quickstart = installer first, PyPI second. The PyPI
   placeholder 0.0.1 (name claim only) gets superseded by the first
   real release.
4. **Gaming field-pass**: live matrix (mark pin-max cams, set real
   desktop_hz on the gaming card, trust-list, hot-plug) — the code is
   shipped but this desk has never played a game through it.
5. **Second-camera reality**: door-cam wiring (policy tables are built
   for it), real multi-cam preview, real exclusive-driver behavior of
   the degrade path (probes used fakes).
6. **Housekeeping**: `_enroll` NameError (pre-existing), PDH video
   counters after next reboot, OldBeast engine notes refresh.

## Not in v1.0 (parked with receipts)

VRR ghost-window experiments (banked, docs/vrr-findings.md), hotkey
layer, profile import/export, telemetry, multi-user service, Galahad
KV offload (owner: wrong-session research, ignored here).

## Definition of done (v1.0)

`pip install panelboss` on a clean Win11 box → tray icon named
PanelBoss appears <2 s, settings window responds instantly (no measured
jank at 4K), one door cam + one desk cam run off policy tables edited
IN THE UI, screens obey the presence law for a week of daily use with
zero false-offs the owner can demonstrate, an update via the new installer keeps the pin and
the Run entry (same exe identity end to end), and every file in the repo is either
≤~300 lines or carries its SIZE LAW note.

## Standing constraints (binding, older than any feature)

Fail-open (a broken optional feature must never eat the core promise),
silent at logon, driver settings belong to the owner, no admin
required for install or operation, review gate before every commit,
lane doctrine per fleet-capacity, design principles per AGENTS.md.
(Portable-first retired 2026-10-11 in favor of installer-first; the
venv dev path survives untouched.)
