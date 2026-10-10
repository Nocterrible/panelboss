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

- resolve every call via `nvapi_QueryInterface(method_id) -> fnptr`
  (export ord 2). CONFIRMED (Oct 10, gsync_probe.py): Release 590's
  `nvapi64.dll` is a SAL PROXY exporting ONLY `nvapi_QueryInterface` +
  `nvapi_Direct_GetMethod` — every named `NvAPI_*` export is GONE, so
  GetProcAddress-by-name / getattr cannot work. method_ids come from
  NVIDIA/nvapi `nvapi_interface.h` (NVAPI_INTERFACE_TABLE).
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

## Measured: gsync_probe.py (Oct 10 2026, unprivileged, read-only)

Headline: **DRS READS work unprivileged.** Each of the 3 VRR settings read
with `NvAPI_DRS_GetSetting` returned `0 NVAPI_OK` with NO elevation
(shell not elevated). The doc above only recorded DRS *writes* (elevated);
reads are open. Per setting, both the current-global handle and the base
profile handle read clean:
- `VRR_MODE 0x1194F158` (name "Enable G-SYNC globally") → `dword=1`
- `VRR_REQUEST_STATE 0x1094F1F7` (name "VRR requested state") → `dword=1`
- `VRR_APP_OVERRIDE 0x10A879CF` (name "G-SYNC", settingLocation=3) → `dword=0`

Mechanics that were wrong / not yet known and are now confirmed:
- The modern DRS `GetSetting` is the 4-arg
  `NvAPI_DRS_GetSetting(hSession, hProfile, sid, NVDRS_SETTING*)`. The
  `GLOBAL_PROFILE_HANDLE` sentinel (0xFFFFFFFFFFFFFFFF) must NOT be passed
  as `hProfile` — the driver dereferences it as a pointer and AVs. Use the
  real handle from `GetCurrentGlobalProfile` / `GetBaseProfile` (both return
  0 OK on this box).
- `NvAPI_Disp_GetVRRInfo(displayId, ...)` wants the "combined physical
  display + GPU id" from `NvAPI_GPU_GetConnectedDisplayIds` (per
  `NvAPI_EnumPhysicalGPUs`), NOT the low-32 of `NvDisplayHandle` — that
  yields `-187 NVAPI_INVALID_DISPLAY_ID`. Confirmed: 2 GPUs → 3 displayIds
  (0x82061083/0x80/0x86) → `GetVRRInfo` returns `0 OK` unprivileged.
- Data finding: all three outputs report every VRR bit 0
  (`bIsVRREnabled/bIsVRRPossible/bIsVRRRequested/bIsVRRIndicatorEnabled/
  bIsDisplayInVRRMode = 0`) even though DRS global `VRR_MODE=1`.
  Interpretation pending (likely per-output VRR off / not possible in the
  current mode); raw values are the report, not a bug.
- Method IDs resolved (via nvapi_QueryInterface): Initialize 0x0150E828,
  EnumNvidiaDisplayHandle 0x9ABDD40D, Disp_GetVRRInfo 0xDF8FDA57,
  DRS_CreateSession 0x0694D52E, DRS_LoadSettings 0x375DBD6B,
  DRS_GetCurrentGlobalProfile 0x617BFF9F, DRS_GetBaseProfile 0xDA8466A0,
  DRS_GetSetting 0x73BF8338, DRS_GetSettingNameFromId 0xD61CBE6E,
  EnumPhysicalGPUs 0xE5AC921F, GPU_GetConnectedDisplayIds 0x0078DBA2.

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
