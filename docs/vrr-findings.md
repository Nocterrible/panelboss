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

## Oct 10 update - verified dwords + expert brief (no more UNTESTED on names)

Source: NVIDIA/nvapi master NvApiDriverSettings.h fetched directly (raw
githubusercontent), cross-checked against our own DRS GetSetting reads.

- VRR_MODE 0x1194F158 ("Enable G-SYNC globally"): DISABLED=0x0
  FULLSCREEN_ONLY=0x1 FULLSCREEN_AND_WINDOWED=0x2. LIVE READ = 1, so
  the desk is fullscreen-only today; the windowed target is 0x2 -
  the global write is NOT a no-op (corrects the earlier guess).
- VRR_APP_OVERRIDE 0x10A879CF / VRR_APP_OVERRIDE_REQUEST_STATE
  0x10A879AC: ALLOW=0 FORCE_OFF=1 DISALLOW=2 ULMB=3 FIXED_REFRESH=4
  (ULMB is NVIDIA-UI's "Ultra Low Motion Blur" family label; the
  FIXED_REFRESH dword the earlier probe was missing is 4).
- VSYNCVRRCONTROL 0x10A879CE: the "Variable Refresh Rate" switch.
- DRS write path ids (verified against >=2 public mirrors by the
  cloud brief, still UNTESTED on this box): SetSetting 0x577DD202,
  SaveSettings 0xFCBC7E14, DestroySession 0xDAD9CFF8; writes go to
  the CURRENT-GLOBAL profile handle with settingLocation=0.
- Brief verdict: DRS has NO display-scoped profiles (per-display
  "Enable for this model" checkbox lives elsewhere; prime candidate
  Get/SetAdaptiveSyncData 0xB73D1EE9/0x3EEBBA1D, rc=0 would also
  settle per-output capability). All-zero GetVRRInfo while
  VRR_MODE=1 ranks: per-display enable off > GSC under-report.
- Owner product decision (Oct 10, supersedes the Hz-switcher
  priority): VRR-capable panels stay pinned at MAX scanout always
  (desktop draws ~60 frames under VRR, ZERO mode flips, zero flash);
  desktop_hz hold + game_hz switching serve non-VRR panels only.
- Next gate: Stage-A read-only probes (GetErrorMessage on -187,
  GetVRRInfo handle x displayId matrix + bad-version control,
  GetAdaptiveSyncData both conventions, EnumAvailableSettingIds
  census) + the user's NVCP "Set up G-SYNC" per-display checkbox
  screenshot; then Stage-B single risky write with rollback.
  Stopping condition: enabled + reboot + OSD never deviates ->
  ship plain Hz switching, delete VRR code.

## Oct 10 backlog - refresh-to-content-rate alignment

Owner ruling: when a panel runs VRR at pinned max, content-rate
judder is mostly VRR's job (proper players stretch frame intervals,
23.976 on 240 plays smooth, no cadence pattern). The INTEGER-MULTIPLE
rule is for the VRR-OFF world (and VRR-unknown fallback): before
playing video, pick the panel's offered mode that is an integer
multiple of the content fps (23.976 -> 119.88/239.76 if offered,
24 -> 144, 25 -> 100/150, 30 -> 120; else keep current) so frames
repeat in an even cadence instead of 3:2 pulldown judder. Selection
source: wm.offered_modes(gdi) already parses every mode the driver
offers - the engine picks min |mode - k*fps| across offered modes
with exact-tolerance, ties to lower total Hz change (less flash).
Content-fps SOURCE is the still-gated GPU decode telemetry
(scripts/video_probe.py, needs the reboot to un-gate). Interaction
with desktop_hz hold: a video-rate switch is OUR OWN set - the hold
must not stomp it back mid-playback (watcher learns the video rate
as temporary truth, restores the configured rate when playback
ends, same ledger discipline as game mode).

## Oct 10 rerun - the stopping condition is met: per-display VRR is not an API fact (on this driver)

Context: owner GPU-Z screenshot of the GP27 (CMT2704, 144 Hz): its
G-SYNC row reads **Not supported** while the EDID CTA-861 extension
block carries the 48-144 Hz LFC range (FreeSync-capable material),
driver 591.86. Meanwhile the 240 (IOC912B) runs VRR verifiably -
owner-confirmed, visible in its OSD.

Probe rerun (gsync_probe.py, read-only, unprivileged, 0 SET calls):

- `VRR_MODE 0x1194F158` global `dword=2` - FULLSCREEN_AND_WINDOWED.
  The owner moved it from 1 in the NVIDIA App since the first read;
  the 0x2 target from the header study is what a real enabled desk
  shows. The change landed without any recorded reboot - same-day
  visibility, consistent with the DRS live-apply mechanism recorded
  at the top of this file (profile edits apply live, no reboot).
- `VRR_REQUEST_STATE 0x1094F1F7` global `dword=2` (read 1 before).
- `VRR_APP_OVERRIDE 0x10A879CF` `dword=0` (ALLOW) at
  settingLocation=3 - the DEFAULT untouched; the probe never
  enumerates CreateApplication profiles, so it claims nothing about
  per-app entries existing or not.
- Three connected displayIds spanning TWO physical GPUs (the probe's
  `2-gpu` line; 0x82061083/80/86, combined display+GPU ids);
  `NvAPI_Disp_GetVRRInfo` rc=0 on all three and **every VRR bit
  still 0** - including the 240 that is enabled and demonstrably
  running VRR right now.

Ruling (the pre-registered stopping condition quoted by name
above): with enabled, working, owner-verified VRR the API never
deviates from zero on this driver. The condition's `reboot` conjunct
is discharged by that same live-apply line - a reboot adds nothing a
live DRS change has not already exposed; and the `OSD never
deviates` conjunct is exactly what the all-zero sweep over a
running-VRR 240 means. The pre-registered consequence ("delete VRR
code") is amended by dc53e32: auto-detection is deleted and stays
dead, but the OWNER-declared `VRR (pin max)` keeps its place,
because a fact the API cannot see, the owner can state.

GPU-Z caveat: its G-SYNC row is not a live-state guarantee either -
"No support" on a panel whose EDID explicitly carries the VRR range
reads as derived heuristics (EDID + driver posture), not GetVRRInfo
truth. The NVIDIA Profile Inspector the owner now has installed
(Nsight Systems Analyze, CUDA-API tracing) is the wrong instrument
entirely for display state: display NVAPI calls never appear in a
CUDA trace. (The similarly named DRS profile inspector from this
file's opening lines is a different tool altogether and stays a
candidate for future DRS writes.) Both tools retired for this
question; gsync_probe.py remains as the evidence harness if a future
driver build deserves a second look.

## Oct 10 - the ghost-window idea, banked not built

Owner proposal: render a tiny hidden window paced at a chosen fps
and let VRR track it - zero mode switches, zero flash, fractional
rates (23.976) for free. Probe: scripts/vrr_ghost.py (popups +
vsync-observer skeleton). On this box the reporting path ran clean
but the EXPERIMENT did not: chain creation stops at the export wall
below, so the ghost never owned a chain, never presented, and the
pacing/observer path is untested here.

Findings before any COM plumbing was even needed:

- The fossil name-lookup design is dead on this machine, but not
  for the reason first written here (corrected after a reviewer
  export census): the creators DO exist - D3D11CreateDeviceAndSwap-
  Chain is exported by d3d11.dll, D3D10CreateDeviceAndSwapChain by
  d3d10.dll; they were only ever missing from dxgi.dll, which never
  hosted them on any build. The surviving wall: the present shims
  the trick was written against (D3D11SwapChainPresent / D3D10Swap-
  ChainPresent) exist in NO dll on this box (census: dxgi, d3d11,
  d3d10, d3d9) - the creator hands back a COM IDXGISwapChain, so
  every call after that is vtable archaeology. And note the fossil
  8-arg call shape the probe uses is not the real 12-arg export
  signature; a COM round 2 rewrites the whole path anyway.
- (inference from documented DWM flip precedence; not exercised on
  this box, the chain never presented) blanking cadence follows
  DWM's FLIPPED window - the topmost opaque unscaled one. A truly
  hidden window gets composited and can never own the clock; a
  window that CAN own it is by definition visible, and while it
  paces at 24 the whole panel (cursor, video, browser) blanks at
  24 - the judder the trick was meant to cure. The observer design
  carries the same inference: its own vsync chain may itself pin
  the cadence to max, so a TRACKED reading there is a lead, not a
  verdict.
- (mechanism expectation, OSD sighting pending) VRR *is* already
  tracking a specified framerate for the frontmost title: a G-SYNC
  game capped at 100 should blank the panel near 100 - observable
  on the 240's OSD, not yet witnessed and recorded here. The only
  genuine gap is windowed-mode players that present badly, and
  there the cadence must come from the front window (the player),
  not a ghost behind it.

Decision (owner): banked, not built. The shipped stance already
covers the space: VRR panels get owner-declared pin-max (zero
flips, the player's own VRR does the rest); non-VRR panels get the
Hz switcher; the video-rate backlog (integer multiples) targets
exactly the VRR-off cases the ghost cannot reach anyway.
vrr_ghost.py stays as the evidence harness: its popup/pacing/
observer skeleton is sound and its failure reporting is honest, and
the comments now mark exactly what a COM round 2 must rewrite (the
12-arg creator, vtable Present, and the observer-domination
question) should a bad player ever make the archaeology worth it.
