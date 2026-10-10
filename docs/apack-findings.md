# A-pack findings: gaming toggles on Windows 11 25H2/26H2 (measured 2026-10-10)

Source: researcher brief, verified against live 25H2 build 26220.2586
(this desk) + local ADMX + primary docs. The Game Bar upheaval moved
the UI, not the plumbing: the capture stack (`bcastdvr`) and its
per-user keys are alive and are what Settings/Xbox-app toggles write.

## What this desk already has (live sweep, read-only)

* `HKCU\System\GameConfigStore`: `GameDVR_Enabled=1`, BOTH spellings
  of the FSE mode value present (British one from some tweak script),
  `HonorUserFSEBehaviorMode=0`, `DXGIHonorFSEWindowsCompatible=0`,
  `EFSEFeatureFlags=0`. None of the folklore names exist.
* `HKCU\Software\Microsoft\GameBar`: `UseNexusForGameBarEnabled=0`
  (Win+G already off here), `ShowStartupPanel=0`.
* `HKCU\...\CurrentVersion\GameDVR`: `HistoricalCaptureEnabled=0`;
  `Debug\ErrorHistory_*` dated this week = bcastdvr ALIVE on build.
* Policy paths absent; `GameDVR.admx` local = policy `AllowGameDVR`
  at `HKLM\SOFTWARE\Policies\Microsoft\Windows\GameDVR`.
* `globalCaptureSettings.json` absent (dead Win10 artifact).
* FSO proof live on this desk: `AppCompatFlags\Layers` has
  `Palworld.exe = "~ DISABLEDXMAXIMIZEDWINDOWEDMODE"` - that STRING
  is what the compat-tab checkbox writes. The 0x00100000/0x00200000
  DWORDs are SDB-internal eCompat bits, NEVER registry values.
* Timer resolution RIGHT NOW: current = 5000 = 0.5 ms already, floor
  15.625 ms, `GlobalTimerResolutionRequests` absent - a running
  process holds 0.5 ms without any registry help.
* ChrisTitus "Ultimate Power Plan" is the active plan.
* No "XboxGk" on modern builds; controller driver is `xboxgip.sys`;
  ViGEmBus present. GameInputSvc running (Manual).

## The pack (decisions)

| id | toggle | apply | elevation | timing | verdict |
|----|--------|-------|-----------|--------|---------|
| T1 | Win+G overlay off | HKCU `GameBar\UseNexusForGameBarEnabled=0` | no | live | include |
| T2 | bg capture + "record what happened" | HKCU `CurrentVersion\GameDVR\` `AppCaptureEnabled=0`, `HistoricalCaptureEnabled=0` | no | live new sessions, sign-out to stop bcastdvr fully | include CORE (same keys Settings writes) |
| T3 | machine-wide DVR off (GPO) | HKLM `Policies\Microsoft\Windows\GameDVR\AllowGameDVR=0` | yes | gpupdate + bcastdvr restart | optional "hard" mode; breaks ICC color mgmt in exclusive FS |
| T4 | session DVR kill | HKCU `GameConfigStore\GameDVR_Enabled=0` | no | sign-out | part of the T2 pack |
| T5 | ms-gamebar* protocol hijack (popup killer) | HKCU Classes redirects to systray.exe + NoOpenWith | no | live | only useful paired with Game Bar uninstall; skip alone |
| T6 | per-app FSO off | HKCU `AppCompatFlags\Layers\<full exe path>` = SZ `~ DISABLEDXMAXIMIZEDWINDOWEDMODE` | no | next launch of that exe | include CORE - the only bulletproof FSO knob |
| T7 | global FSO off best-effort | `GameDVR_FSEBehaviorMode=2` + `EFSEFeatureFlags=0` + `HonorUserFSEBehaviorMode=1` | no | sign-out | include labeled best-effort (community-only, some Win11 games ignore) |
| T8 | timer resolution | registry form `GlobalTimerResolutionRequests=1` is HKLM+admin+reboot AND UNDOCUMENTED; measured: desk already at 0.5 ms without it | - | - | skip registry. Better: `timeBeginPeriod(1)` live from the tray app while a game is up (zero admin, zero reboot) - rides gaming_watch |
| T9 | Game Mode | no registry key exists | - | - | skip: orthogonal to power plan (it suppresses WU/background tasks; the plan swap changes hardware policy; neither subsumes the other) |
| T10 | folklore (AutoGameDvr*, RecordGame, HasGameDvr*, BackgroundRecording*, CursorShow*, AllowFlipRecording, globalCaptureSettings.json, GameBar\AllowGameBar...) | verified absent/no-reader on live 25H2 | - | - | SKIP, do not touch |

## Phantom "Setting up USB device" popups (honest partial)

No single magic key. Launch-time popups = (a) Game Bar protocol
launches on controller-driven game detection (fixed by T1+T2, plus
T5 if the app is removed) and (b) genuine child-device balloons from
xboxgip/ViGEmBus re-attach - WUDF/PnP territory; the levers are the
GameInputSvc start type or silencing PnP notifications, NOT a
registry folklore key. Four phrasings searched; no 2025-26 source
stands behind a single-key fix.

## Caveats to keep honest in the UI

* GameDVR_FSEBehaviorMode: zero MS documentation; spelling variants
  circulate; one 2024 report says some Win11 games ignore it.
* GlobalTimerResolutionRequests: Bruce Dawson himself would not ship
  it; and its effect is build/state sensitive.
* An overlay package update can re-register protocol handlers and
  undo T5-style hijacks.
* All "2026" statements pin to build 26220 + GamingOverlay 7.326.

## Next measurements (if certainty needed)

1. toggle Game Mode in Settings and diff the registry to pin where
   GamingServices stores it (currently assumed registry-free).
2. `Get-PnpDevice`/event log around a game launch to NAME the device
   behind the balloon.
3. write a dummy Layers string for a throwaway exe and time the
   effect (claim: next launch, no sign-out).
4. clean-boot timer-resolution floor with browsers closed.
