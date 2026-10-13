# RC package v2: PanelBoss ui-1c-reskin fix wave (45fcc38..4399a5d)

## Intent
Pre-release audit (13 batches, two-channel + probes) produced ~42 findings,
all patch-scale. Wave 1 (9 themed commits) closed the state/config/tray/
profiles/UI-lifecycle clusters. The FIRST FINAL GATE returned BLOCK with
two accepted blockers; wave 2 (5 commits) closes the remaining camera-engine
and notice/plan clusters named by that blocker, plus the wave-2 gate's three
dictated micro-fixes. This document's rule: every claim has a named file
below that proves it.

## Blocker disposition (final-gate #1 -> wave 2)
- B1 dead-tray quit bypassed the loop -> FIXED 615c1c4 (quit event routed
  through the real handler: window closes, lock releases; patch proves it,
  tray.py hunk).
- B2 "every HIGH/MED closed" was false -> every item now FIXED or explicitly
  RE-SCOPED in AUDIT-PUNCHLIST.md's disposition lines. Camera-engine HIGHs:
  c9b6642 (letterbox ndim, 0-size abstain, onnx head validated at build -
  inside get_session, the sole production construction path, gate-verified;
  motion empty-mask + ratio floor; atomic+locked faces save; all-faces
  match; tile floor; preview finally). Camera-core MEDs: 1ea8c53 (30 s
  open-lock deadline with per-tick abstain, BaseException row reap, one
  handle one release, rotor leases via mosaic). Notices/plans MEDs:
  27856ad (boot containment, exact-first override match, plan-ownership
  marker + boot reconcile that KEEPS the marker on failed handback,
  GUID-based localized powercfg decode - corrected by live probe,
  insightface-missing routed to its own honest box). enroll imports:
  615c1c4. Gate micro-fixes: 4399a5d (gallery lock covers the enroll write;
  0-size abstain before inference; skipped release drops its handle instead
  of orphaning it).
- RE-SCOPED (not silently dropped): "InstanceId pairing" - the instance-keyed
  data layer and unique-name label attach shipped earlier (wizard + C4);
  what remains is the owner-acknowledged v1 limit (non-unique friendly
  names cannot map to an OpenCV index by name; wizard confesses it in-text;
  roster stays index-keyed BY DESIGN). See AUDIT-PUNCHLIST.md RESCOPED block.

## Commits (chronological)
9563190 config boundary | 51f8253 state re-arm pair | f3061c8+13e5465 camid
wizard | 1481889 display confession | bf668f4 tray+cli | d7ef04f+cd16772
profiles | 1f1320c+37bc169 UI workers | d6162e2 twelve gate nits |
f8a74f8 wm pinning+apply_layout truth | e8ab8ff gate-2 fixup | 3198042+91fc722
docs | 615c1c4 final-gate-1 follow-through | c9b6642+e8415e8 companions |
1ea8c53 camera core | 27856ad shell/notices/plans | 4399a5d wave-2 micro-fixes

## Evidence set (named files, no shell needed)
1. C:\Users\user\AppData\Local\Temp\opencode\rc-fixwave-v2.patch
   - complete diff 45fcc38..4399a5d, every suite included in-diff
2. C:\Users\user\AppData\Local\Temp\opencode\gauntlet-final-2358.log
   - consolidated run at THIS tip: per-suite rc lines + final verdict
   (rc 0 = "ALL GREEN (complete)": 27+ suites, window sections real,
   app stopped for the run, guard_test double-launch included)
3. C:\Users\user\AppData\Local\Temp\opencode\probe-receipts-v2.txt
   - standalone probe PASS lines: config_norm_test tail, pinlifecycle
   sections, companions_test, camcore_probe 3/3, daemon_confess_probe,
   w2c_probe, displaycfg refusal probe output
4. F:\Projects\panelboss-reskin\AUDIT-PUNCHLIST.md
   - every finding with disposition (FIXED-sha / WAVE2-FIXED / BACKLOG with
   one-line fix / RESCOPED with owner-decision cite) + lane-tax ledger
5. Verbatim reviewer verdicts: section VERDICTS below

## VERDICTS (reviewer gate, Infernix seat, commit-object reviews)
- Wave-1 trio gate (9563190/1481889+bf668f4/f3061c8): "SHIP / SHIP / SHIP -
  all three commits clear their named checks against the diff; nothing here
  blocks."
- C5 gate (d7ef04f/cd16772/1f1320c): "SHIP / SHIP / SHIP-WITH-FIXES - one
  dead-worker path leaves the autostart switch disabled forever" -> fixed
  37bc169, re-gated SHIP.
- C6 gate (f8a74f8/d6162e2/37bc169): "SHIP-WITH-FIXES - one real pin trap:
  taskbar GetWindowRect POINTER(wm.RECT) re-poisons the shared u32 (the
  measured _winapi class); layout_test missed it by not importing taskbar"
  -> fixed e8ab8ff with the gate's exact failure-order probe.
- C2 gate (51f8253): "SHIP - no minimal fixes owed", with the math.inf
  enumeration proving re-arm universality and the release-vs-tally
  single-thread ordering traced.
- Wave-2 gate (c9b6642+e8415e8/1ea8c53/27856ad): "SHIP-WITH-FIXES - no
  BLOCK, no logic that misses the stated requirement; three small fixes"
  -> all three fixed 4399a5d (faces enroll lock, r==0 abstain, skipped-
  release handle drop + the false comment corrected). Interrogation answers:
  validate_head covers every production build path; _load boot race dead on
  arrival (init-before-publish); marker round-trip refuted-by-update(),
  normalizer is key-scoped; reconcile runs pre-loop (boot-only double burst
  acceptable); user32 box is thread-safe; _default_root sweep covers the
  unbound-name class.
- Every implementer lane delivered a VERIFIER child receipt (session IDs in
  lane reports; the sole UNCHECKED classes are stated there: no physical
  camera on the bench, no display-interactive runs).

## Honest notes
- The audit itself produced one false positive (szExeFile, reverted), one
  wrong prescription (HWND_MESSAGE 0xFFFFFFF0; measured -3), and one
  docstring-trust miss the live probe corrected (Display subgroup GUID).
- Single-user offline app: no network surface (ko-fi = webbrowser.open
  spawn), HKCU-only registry, no shell interpolation of user data
  (ShellExecuteW with pinned argtypes is the launch verb).
- Deferred backlog is itemized in the punch list, each with file:line and a
  one-line fix; the two process defers are the _events.py 300-line split
  and overrides queue-marshaling (confession shipped in its place).
- Infra reality for calibration, not doubt: 10 lane-death events tonight
  (emit-boundary thinking-channel truncation, now auto-recovered at the
  bridge); zero lost writes; every verdict on this page was delivered whole.
