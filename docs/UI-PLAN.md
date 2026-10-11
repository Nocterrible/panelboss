# UI pass plan (settings window) — decisions & triggers

Measures taken on the target rig (RTX 5090 desk, 3x3840x2160,
2026-10-10/11). This is the plan of record for the settings-window
overhaul; PROJECT-STATE.md owns the roadmap order, this file owns the
UI truth.

## Diagnosis (measured, not vibes)

- Startup is innocent: customtkinter imports in 0.11 s; a Tk root
  builds in 0.44 s. The perceived lag is RENDER-SIDE: CTk draws every
  rounded widget as software canvas items and repaints them on state
  change; Tk on Windows is GDI (BitBlt accelerates, drawing does not);
  CTk's `check_dpi_scaling` poller re-applies scaling on a timer; at
  4K the painted pixel count multiplies. The owner's phrase - "slow
  to draw, elements stuck on with tape" - is literally two defects:
  canvas-overdraw lag + a missing design system.
- Harness facts learned the same week: `SettingsWindow` close is a
  withdraw (no destroy path in production); the second-window-in-one-
  process `pyimage` TclError is harness-only; general-tab content
  builds lazily on first select (a blank sub-second frame today).
- Focus blip (owner report, parked): a second window periodically
  flashes and settings reclaims focus. Suspects ranked: CTk DPI
  poller, the layout-rescue timer (its cadence matches "periodically"),
  topmost re-assert, kofi/help Toplevel churn. Instrument: foreground
  change-sampler (Temp\opencode\win_sample.ps1); lesson: activate the
  target first (the OpenCode desktop re-grabs focus on every agent
  dispatch - passive sampling during agent sessions is blind). Run
  during the UI sessions with OpenCode idle.

## Phase 1 - de-CTk the hot paths (stay on tk, +~0.5 MB)

Ordered by impact/effort; lands per-page now that window/ is a package:
1. Form walls -> themed ttk (ttkbootstrap or sv-ttk + pywinstyles dark
   titlebar); CTkScrollableFrame is the single worst offender
   (4-15 s stutter reports upstream).
2. Kill the scaling machinery: deactivate_automatic_dpi_awareness +
   set_widget_scaling(1.0); size in device pixels.
3. Replace the three priciest CTk widgets (slider/dropdown/progress)
   with theme-engine ttk equivalents.
4. Preview lane: worker-thread JPEG decode, ONE canvas item
   (`itemconfig`, never re-create), cap 15-20 fps; measured baseline:
   naive PhotoImage loop does 49 fps at 1280x720 on this box -
   downscaling before convert was SLOWER (resize cost > paint saving),
   so the mosaic rule holds: compose in PIL, push one image.
5. Only then re-skin (below); re-skinning first repaints the lag.
6. Per-camera policy editor (on/off tables + timeouts) in the camera
   card - the tables ship TOML-only.

Honest ceiling: Tk stays single-threaded GDI; resize/large
invalidations repaint synchronously. If the result still fails the
triggers below, Phase 2.

### Progress log (measured, medians of 3 uitime runs)

- UI-1a (d542b44): DPI poller killed, scaling 1.0, ScrollHost for all
  4 CTkScrollableFrame sites, diff-writes. Tick repaint 0.406 s ->
  0.0000 s. Build median 1.530 -> 1.442.
- UI-1b2 (efa4d79): SkewCombo (tk.Menubutton) replaces all 18
  CTkOptionMenus. Build 1.442 -> 1.095; tab-switch flat ~0.5. The
  dropdowns were NOT the dominant cost as forecast - profiler indicts
  CTkTextbox next: the three textboxes (_gaming x2, _power) carry
  CTk-internal CTkScrollbars (~1.06 s cumtime in the after-combo
  profile); ScrollHost itself is already pure tk.Canvas +
  tk.Scrollbar, no CTk left inside it. The <0.6 build target stays
  open.
- Gate lesson (efa4d79 review): state= recursed via Widget.__setitem__
  re-entering the configure override; same-value re-pick fired
  command where CTk fires only on change. Both fixed per gate.
- RDP incident harvest (this branch, rescue-restore-v2): sliver
  rescue landed (lost := <64px grabbable on any monitor),
  placement-repair for iconic windows (fix where they'd land, never
  un-minimize), wake-restore now relocates only off-canvas windows
  (user moves between snapshot and wake are respected), and the
  gaming rate-hold abstains on Remote_Monitor (32 Hz fiction).
  Layout_test blocks 3b/3c/3d + a gaming_watch guard test pin them.

## Design system (kills the tape look; applies to ANY toolkit)

- One spacing scale: 4/8/16/24 (label->value 4, row pitch >=8 at 4K,
  section 16, page 24). Value column anchored to its control, never a
  floating right-edge label.
- Elevation = contrast tiers + 1px borders, not shadows: three
  surfaces (page #17181A / card #202123 / raised #2A2C2F), border one
  step darker on cards, lighter on raised controls (the
  Monitorian/PowerToys recipe).
- ONE accent color (4K-legible, 4.5:1 on card), reserved for
  interactive state; the shipped green+teal mix reads accidental.
- No floating "?" chips: pre-allocated inline hint row per control;
  deep help behind F1/Ctrl+K palette (one pre-built Toplevel,
  Twinkle-Tray-style show-don't-create).
- Genre copyables that need no new renderer: pre-built hidden flyout,
  deferred tab bodies (keep - but paint a "building..." row so lazy
  build never reads as blank), keyboard-first nav, value-while-drag.

## Phase 2 triggers (measure on the post-Phase-1 app, don't argue)

tab build > 300 ms | preview/mosaic < 20 fps sustained | resize or
flyout jank visible in a 120 fps phone recording | >50 controls/pane.

Escape order if triggered: pywebview/WebView2 (0.5 MB, Chromium
compositing, preinstalled runtime; lifecycle proven on this box, RAM
unattributable here - 35 webview procs own the baseline) -> PySide6
(last: 78+ MB, LGPL bookkeeping, heavy imports). Flet RULED OUT: 1.0
fetches a 96.6 MB desktop client at first run (offline portable venv
breaks) and its API churned mid-evaluation. DearPyGui/Kivy ruled out
on open HiDPI/Windows defects.

## Size-law compliance map (what's already possible)

window/ split (14 parts <=~350 lines) makes Phase 1 dispatchable per
page: _detection, _power (+_gaming), _profiles (+_prof_editor/
_prof_apply/_prof_pins/_restore), _general, _preview, _runtime,
_widgets. Each de-CTk step is one background coder packet scoped to
one or two parts; the suites are the contract.
