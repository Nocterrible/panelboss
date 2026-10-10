# VRR / G-Sync programmatic control — findings (Oct 2026)

Research verdict for the "no monitor flash" question, superseding the
earlier control-code theory (0xF0-F2 / explorer LoadLibraryEx trick:
those codes are NOT in the public NVAPI; the EnableCSGS registry blob
exists neither here nor in NVIDIA Profile Inspector's code — it edits
DRS, not the registry).

## The mechanism

G-Sync/FreeSync already IS the no-flash answer: the panel's scanout
stays pinned at max Hz and VRR stretches frames (driver calls it
"virtual refresh rate"). A flash only happens when the MODE leaves
the VRR window (240 -> 60 desktop). So the ideal end-state is:
VRR enabled globally, per-app overrides, and the Hz-switcher kept
for non-VRR panels and for the one intentional desktop transition.

## NVIDIA (nvapi64.dll — already in System32, headers MIT)

- resolve every call via `NvAPI_QueryInterface(interfaceId)`; a plain
  getattr on the DLL raised AttributeError in a ctypes probe — use
  kernel32.GetProcAddress (CAVIL: unresolved, debug first).
- read: `NvAPI_Disp_GetVRRInfo` (ID 0xdf8fda57, query-only),
  `NvAPI_DISP_GetAdaptiveSyncData` (0xb73d1ee9),
  `GetMonitorCapabilities` (supportVRR / isTrueGsync / isBasicVRR).
- write, per display, no admin documented:
  `NvAPI_DISP_SetAdaptiveSyncData` (0x3eebba1d) bDisableAdaptiveSync
  + maxFrameIntervalNs. (Whether it actually applies without
  elevation is UNTESTED — expect DRS to win.)
- the Control Panel's "Set up G-SYNC" + per-app overrides are DRS
  settings (profile DB), applied live, NO reboot, DRS writes
  ELEVATED: `VRR_MODE 0x1194F158` (off / fullscreen / fullscreen+
  windowed), `VRRREQUESTSTATE 0x1094F1F7`, per-app
  `VRR_APP_OVERRIDE 0x10A879CF` (allow/force-off/disallow/
  FIXED_REFRESH!), `VRRFEATUREINDICATOR 0x1094F157`, `VSYNCVRRCONTROL
  0x10A879CE` — via NvAPI_DRS_CreateSession/LoadSettings/SetSetting/
  SaveSettings/CreateApplication. Elevation pattern we already own:
  the power assistant's registered scheduled task.

## AMD (atiadlxx.dll — present even on this NVIDIA box)

`ADL2_Display_FreeSync_Cap` (range in micro-Hz), `_State_Get/_State_
Set` per adapter/display, no admin; proven ctypes-equivalent by
g-helper's production DllImports. No public per-app store (Adrenalin
profiles are opaque).

## Microsoft layer

`HKCU\Software\Microsoft\DirectX\UserGpuPreferences`
`DirectXUserGlobalSettings` = plain `Key=value;` text; add
`VRROptimizeEnable=1` = the Settings VRR toggle. Third-party
writable, no admin. Live effect CONTESTED (some sources claim
reboot) — must be A/B'd on this machine. Only meaningful for DX11
exclusive-fullscreen titles without native VRR anyway.

## No-flash mode switch

No documented flag suppresses the DP retrain blackout for
out-of-window mode changes. ChangeDisplaySettingsExEx doesn't exist.
MPO folklore is about compositor flicker, not mode changes.

## Plan for this app (post gaming-hz)

1. NVAPI read-only pass (GetProcAddress debug, GetVRRInfo per panel)
2. one ELEVATED experiment: flip VRR_MODE + a per-app override on
   the AGON, confirm zero flash and NVCP agreement
3. A/B the VRROptimizeEnable live effect
4. feature: VRR panels get "stay at max Hz + VRR on during games"
   (zero mode switches, zero flash); non-VRR panels and desktop mode
   keep the Hz switcher with its grace timer. The `FIXED_REFRESH`
   per-app override may even remove games-from-the-equation for
   listed titles entirely — worth probing what it does to scanout.
