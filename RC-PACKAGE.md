# RC package v4: PanelBoss ui-1c-reskin fix waves 1-3 (45fcc38..93c9cc3)
FOURTH-SUBMISSION RESULT: **RELEASE** (no blockers; RISK line: the
lock-free release + 30 s open deadline on the owner's multi-cam NVIDIA
desk at first quit/reboot - late presence decisions, not crashes;
accepted knowingly). Housekeeping notes from that verdict (stale
header below, receipts predating probe section (d), docs-only delta
6ce0a1a..27a6d42) are closed by THIS commit: header refreshed,
probe-receipts-v4 regenerated at the final tip (13 suites incl. the
(d) marker-chain line and the deterministic unknown_state), and the
tag moved to the tested content.

## POST-RELEASE addendum (UAT wave, same day) - re-tag due at 0ffa77e
The owner's UAT battery + one live APPCRASH produced SIX more gated
commits on top of the tagged 93c9cc3; the final gate must re-read THIS
range (93c9cc3..0ffa77e), not the original:
- 282b262 wizard preview freeze (CTkLabel image=None trap; ctkimg_probe
  regression net; gate: SHIP)
- ab90cd2 glass-first roster + virtual-cam namespace classifier +
  session reveal checkbox + relaxed twin preview_map (gate: SHIP,
  two below-threshold notes absorbed)
- 0d3c8df c0000374 heap-corruption repair: W3A's lock-free release
  re-locked the DRIVER TOUCH (null-first swap stays; busy lock defers
  via _deferred_releases - never waits, never drops; _open_timed
  drains). Evidence: two WER buckets today (09:13:20, 09:27:42 - the
  second observed live), pre-W3A survivors of identical log clusters
  as the discriminator, camcore_probe case (d) as the regression net
  (gate: SHIP, findings absorbed)
- df9e8c4 wizard/add-pane parity: every OPEN scanned index gets a step
  (owner law: identify must curate what the add pane can open);
  synthetic idx:N keys; UNKNOWN-is-not-SOFTWARE default rule;
  dshow.py opportunistic ordinal oracle (three probed dead routes on
  this box, documented; answers {} warn-once). Live-desk simulation
  caught the first draft's default-hide sin (gate: SHIP, 3 note-level)
- 0ffa77e three honest attempt states (WARMING/BUSY/NOSTREAM): the
  owner-caught "all say no live view" - contended 18.6 s opens and
  zero-sample MF doors hid behind silence while holding the device;
  12 s first-frame budget with guaranteed handle return; gate-specified
  _busy_note leak fix + worker-local got latch (gate:
  SHIP-WITH-FIXES, all absorbed, FlashCam pins one-frame-then-dark)
Receipts at the new tip: gauntlet-v7.log (FILE: in scratch dir),
probe-receipts regenerated at tag time. The RISK line above is CLOSED
by 0d3c8df: the release now rides the device-tree lock (deferral, not
blocking), which was the gate's named worry.

## Intent
Pre-release audit (13 batches, two-channel + probes): ~42 findings, all
patch-scale. Wave 1 closed the state/config/tray/profiles/UI-lifecycle
clusters; the FIRST final gate BLOCKed (dead-tray quit bypass + claim-vs-
diff gap); wave 2 closed the named camera-engine/notice clusters and the
SECOND final gate BLOCKed again (stale per-line dispositions + a release-
lock design regression). Wave 3 reversed the release-lock design, patched
the six unassigned MEDs the second gate's blocker 1 named, and absorbed
the rest of its ledger. This document's law: every claim has a named proof
file; the disposition map is per-section, not per-summary.

## Second-gate blocker disposition
B1 (per-line dispositions + six MEDs with no hunk) -> the AUDIT-PUNCHLIST
"Disposition legend (FINAL, wave 3)" maps EVERY FIX-NOW line to its closing
commit range, with the two process defers and one owner-question listed as
explicit exceptions, not silence. The six MEDs: grid 2-D tiles (4d26424),
warm-menu pump-gate (633a5c6), motion slider mirror-write (4d26424),
editor raw subscripts (4d26424, census: exactly two sites lacked validation,
both converted, the rest already honest), cli quit cross-thread release
(633a5c6), localized display-gate (49dc14e: GUID invariant live-measured +
ONE log.confession when a locale's headers match nothing - the fixture
honesty fix the gate demanded).
B2 (release-lock stall / None.release race / destructor-lie skip) -> design
REVERSED in 633a5c6: release takes ownership via a GIL-atomic null-first
swap, lock-free; the deadline stays on the OPEN side only; the quit path
never reaches across threads while the loop lives. camcore_probe (a) is
now the two-thread 50-round hammer: exactly ONE cap.release ever, no
AttributeError, five repeats no flake.

## Commits (24, 45fcc38..HEAD, 54 files +3752/-341)
Full list with subjects in rc-fixwave-v3.patch; waves: 1 = 9563190..d6162e2,
2 = e8ab8ff..4399a5d, 3 = 633a5c6..HEAD (+ W3B 4d26424, absorb 49dc14e,
banner-drift fix 66b631b, probes/probe-name fix).
Gate verdicts: every themed commit passed the synchronous Infernix reviewer
gate (wave-1 trio SHIP x3, C5 gate 2xSHIP+1 fix-now-shipped, C6 gate
SHIP-WITH-FIXES fixed in e8ab8ff, wave-2 gate SHIP-WITH-FIXES fixed in
4399a5d); the wave-3 diff-gate pass was folded into the architect review
because two lanes died at zero writes and the surviving content was
built-and-verified inline (receipts below) - declared, not hidden.

## Evidence set (named files, no shell)
RECEIPT for the process blocker (wave-3 range lacked an independent
gate): the reviewer gate over 633a5c6^..2ed7645 returned AGGREGATE
SHIP-WITH-FIXES on the deep channel (no fallback ridden): "one low
finding (tray _on_menu_ready's modal-pump assumption; worst case a
one-time cosmetic menu-close in the first ~13 s) ... Everything else
in the range - the camera ownership swap, the quit handoff, the
raised-death arm, the _path marker write-back, the locale-evidence
gate, the TypeError belt, the ratio domain map, the fixture
arithmetic, and the runner stamps - verified against the code, not
the dispositions." Both offered remedies (probe or reword) were
comment-grade and re-review-exempt; the reword shipped as 6ce0a1a
together with the runner's DIRTY-stamp. All 9 interrogation items
answered at the receipt.
1. C:\Users\user\AppData\Local\Temp\opencode\rc-fixwave-v3.patch
   - complete diff incl. every suite and probe, 54 files
2. C:\Users\user\AppData\Local\Temp\opencode\gauntlet-final-tagc.log
   - consolidated run AT THIS TIP: "ALL GREEN (complete)", app stopped,
     window sections real, guard_test double-launch, 32 suites incl.
     the five wired in by 6d3edbd
3. C:\Users\user\AppData\Local\Temp\opencode\probe-receipts-v3.txt
   - 12 standalone probes/suites, every rc=0, header names this tip's
     short SHA and timestamp
4. F:\Projects\panelboss-reskin\AUDIT-PUNCHLIST.md
   - finding-by-finding; disposition legend maps every FIX-NOW line to
     its closing commits; BACKLOG items carry file:line + one-line fix
5. F:\Projects\panelboss-reskin\CHANGELOG.md + version 0.2.0 (6d3edbd)

## POST-RELEASE addendum 2 (owner-UAT waves, same day) - re-tag due at wave-E tip
The addendum-1 range itself grew past UAT: the owner's live battery
produced SIX more gated camera commits (4a48efd addendum, 54533bd
BIND, c21c529 instant-close crash + virtual-flag channel, 05efcd1 the
naming law end-to-end incl. IR rows, d4000b1 typed-label-only save),
then THREE themed waves on top of d4000b1, each independently
V-receipted and reviewer-gated (verdicts all SHIP or
SHIP-WITH-FIXES-absorbed):
- CAMDIAG WAVE (2e4c6e1..7289b14): the camera diagnostic record
  (camera.diag), the THREADED scan-probe (owner law: sequential
  6x15s unacceptable; opens serialized on the device-tree lock, 15 s
  budgets overlap), pre-marks/picker suffixes, sticky per-camera
  show-back, and the HEARTBEAT VEIL (fixed budgets died; veil
  lifetime = sweep liveness, 35 s dead-man derived from the engine's
  own open deadline) + the _veil_hold leak close (e69c22c's IR duty
  card closed the unremovable-sentinel seat).
- REDESIGN ("blow it away", 61d9137..36ba449, push 6fbb3a0): CONSENT
  GATE first (camera.enabled stock-false; no camera opens until the
  user speaks - the tray menu itself was an opener until this wave),
  the setup screen (_assign.py: cards spawn per settle, snapshots,
  rename+hide+ADD per card, timeout cards that say so, IR first-class,
  four-seat ceiling grayed IN the widget), the wizard's funeral
  (_camid.py -> 257-line _identity.py data module), hidden list on the
  camera card, and the DEFAULT-OFF LAW (f06da02: power/wake/restore
  stock-dark, adoption one-directional, release-boundary migration
  with named reset lines). Root-cause interlude: the "virgin boot"
  breach was a SILENT migrate_once resurrection of the pre-rename data
  dir - now retire-on-use + consent decisions announce themselves
  (3c6ef0c) + virgin_boot_test regression (5188a8a).
- HDR WAVE (38c1343..0995811): per-monitor type-16 SET wired into
  profile apply (order-pinned: layout first) + gaming desktop-color
  sibling + per-panel AUTO-SWITCH tiers - video-ACTIVITY via public
  unelevated PDH GPU-engine counters (RTX-HDR use case; Auto-HDR
  games cannot false-trip while SDR) and mpv-IPC content tier -
  WM_DISPLAYCHANGE ear keeps state honest vs external togglers;
  hysteresis constants named; live off->on->off round trip on the
  owner's panel with both broadcasts witnessed.
- WATCHDOG WAVES (bb38943, e497815): the owner's wedged-desk UAT
  (DroidCam-class MF door) killed the setup screen three times; the
  debugger pinned the third death ONE CALL PAST THE FENCE
  (hello_ir_names -> find_groups, the last unbounded gather verb).
  camera.py now carries join-watchdogs for enumerate (60 s probe-size,
  derivation at the constant), IR (20 s, no-cache-on-stall), and the
  deferred-release drain; the dialog arms at GATHER START, the veil is
  PHASE-NAMED with an elapsed clock and per-index beats, and the NEW
  LAW: an empty board SPEAKS (first engine WARNING surfaced in the UI,
  the veil IS the confession line). Split paid at a real seam:
  watchdog.py (99 lines). 45 commits total since the tag at tip
  e497815.
- WAVE E/F (9e178e1..5cfb57e, the second UAT round - owner-driven):
  the cadence law (always-on reads 1 s dark, floor moved with the
  counter-argument, lit gate split into its own key so the law
  couldn't smuggle a change; two timer-card sliders + the
  "first dark re-poll" relabel killed the README/UI's stale promise),
  create-now's silent-vanish cured at BOTH layers (missing try/except
  + the reporter now writes the label that EXISTS on the fresh-store
  pane), the Xbox toggle verdict WIDGET-BLIND (consumer round-trips;
  one-sided build paint; both-way paints across _gaming/_general/
  _power), the gaming hz menus restored for silent drivers, autostart
  fossil deleted again + the discipline pin (boot can never register
  fresh; registry is the single truth by design), the switch-family
  geometry cure (SWITCH_SYNC repaint at show + tab-reveal; the
  owner's "toggle showed off but the bar was on" root-caused to
  paint-before-geometry with a permanent thread-census instrument),
  and the no-window spawn door (every child verb silent; ban v2 with
  alias coverage + paren-depth flags check; the owner's cmd-strobe
  attribution settled by their own A/B: Fleet Commander, not the
  app - the door ships anyway as the structural class-kill).
  CEREMONY: full runner app-down at 5cfb57e, RUNNER_RC=0, ALL GREEN
  (complete), 42 suites ZERO skips - the first app-down complete in
  the cluster's history (the gaming_ui 60-s bracket closed at
  3 bites/4 greens, blocker named: test's own aborted teardown).
  TAG MOVED: rc-2026-10-13e @ 5cfb57e.

## Honest notes (things the gates found in the gates' own infrastructure)
- Two implementer lanes died at zero writes on multi-delta packets and
  their content was rebuilt inline (the split/absorb dials of packet law);
  one lane reported commit hashes before committing (race, resolved).
  Zero findings lost; every inline fix carries the probe receipts above.
- UNCHECKED classes stated by every verifier: no physical-camera run
  (all camera tests monkeypatch the door), no display-interactive
  automated runs (window sections are scripted-state, not pixel-state).
- The release-path ownership fix (633a5c6) is the one hot-path change the
  fake-camera bench cannot fully rehearse; the null-first swap is
  GIL-atomic and hammered 2x50 rounds, but the owner's multi-cam NVIDIA
  desk is the real test and the first reboot is its rehearsal.
- ONE OWNER QUESTION stands between this RC and motion-mode polish:
  should the confidence slider ROW be visible in motion mode (it now
  mirrors to the ratio knob when moved during a mode race; the row is
  currently hidden by MOTION_ROWS). UI taste call, no code risk.
- Deferred by decision, itemized: _events.py size-law split, overrides
  queue-marshaling, plus the BACKLOG LOWs each with its one-line fix.

## POST-TAG addendum 3 (Oct 14 waves) - re-tag due after the off sub-mode
Between rc-2026-10-13e and this entry the owner's day-two UAT drove
five gated/V-receipted waves (loud-voice profiles with the RC_WHY
translation and the fake-wm test-only-truth correction; the wake
freeze fixed via async hdr walk, root-caused by idle-gate back-solve;
dim mode end-to-end - consent-gated [away] config, _bright under the
READBACK-IS-THE-TRUTH law after this desk's own liar panel, own-
interpreter black overlays, the away card between Detection and
Timers with BLACKOUT/DIM rows and the adopt-vs-revert preview, the
hdr-while-away funeral - shipped via a seven-commit CHERRY-PICK
RESCUE from a worktree misplacement, conflict fusions preserving
monitor-first drain order and the DISPLAYCHANGE coexist law; the
INPUT ORGAN SWAP after the owner's mouse lag - LL hooks floor at a
~31 ms round-trip on ANY pump shape, RAWINPUT with verified
INPUTSINK restores 498-1994/s at target and 0.02-0.06 idle cores,
tombstone pin bans the LL trio; and the cadence laws - dark always-
on at 1 s with the old floor rationale superseded-with-argument, its
lit sibling split into its own key, two timers-card sliders and the
first-dark-re-poll relabel, the README's five default-on promises
corrected the same day).
OWNER-CORRECTION PROBE LAW (commit 3ed08ce): scratch-process
hardware verdicts are contaminated by the probing itself (two
processes, one flaky DDC bus, zero retries) - capability is UNKNOWN
until the shipping path asks with its full retry budget;
unanswered-but-sent is UNVERIFIED-TRUST (this desk's AOC proved the
class: dimmed on the app's door, NAK'd on mine); "refused" is a
timestamp about our attempts, not the firmware's soul.
IN FLIGHT at this entry: the OFF sub-mode over the app's proven DDC
door (retry budget, trust mode, blackout-fallback confessed), the
cursor corner-jail (SetCursorPos once at engage; raw motion is the
waker, jail moves generate none), and the settings-window countdown.
Tag moves after they gate green; the final-gate submission covers
the whole 93c9cc3..range in ONE message (verdict, risk, leftover
ledger - no follow-up harvests upstream).

## ADDENDUM 4 (Oct 14 evening) - the OFF sub-mode SHIPS; the panel
## dossier rewrote the day's physics under it
THE OFF RUNG IS REAL, WITNESSED: DDC/CI VCP 0xD6 actuates on the
directly-attached IOC912B - owner's eyes saw the blackout and the
return through the probe's WATCH windows. The panel's power register
read val=1 ("on") THROUGH the witnessed dark, at +1/+2/+3 s re-reads:
the register does not track DPMS state on this class. Consequence,
shipped law (reviewer F4): the universal status word is
"off (unverified)" - bare "off" retired; the engage buys no register
lie at the door (no vcp_read on the send path, pinned).
THE KVM FACT: the AOC2790 sits behind a KVM with partial DDC
pass-through. Every earlier "deaf/refused" verdict was contaminated
twice over - by scratch-process contention (probe law, 3ed08ce) AND
by the switch; the panel's whole rude biography now has a mechanism.
AOC off-capability ships UNKNOWN-selectable; tonight's instrument is
the app's own Preview button, KVM parked on this PC.
DEAD RUNGS, EVIDENCED: (a) monitor devnode disable (pnputil,
elevated, twice + watched retest): kernel marks, CCD desk unmoved,
panel unchanged - mark-only on NVIDIA WDDM 3.2. (b) SetDisplayConfig
path-set (the suspected Settings-Disconnect mechanism, the
no-elevation hope): ERROR_INVALID_PARAMETER 0x57 at ENTRY on every
call shape incl. VALIDATE and no-array verbs, on 26220 - the
"no scriptable API" survey answer, now locally measured. The ladder
ships: blackout (owned) / dim (works, deaf replies) / off (D6, real,
unverifiable-by-register) / physical button.
GATE CHAIN: reviewer pass 1 SHIP-WITH-FIXES (5 findings: boot belt
for the in-memory-ledger stranded-dark class, degraded-count
predicate, countdown chain overlap, bare-off demotion, honesty
one-liners); fixes at 2410e5e applied verbatim; pass 2 SHIP, both
suites re-greened by the gate itself. V PASS on the wave (deep
channel). OWED EVIDENCE at tag time: owner-eye AOC preview, live
armed dim-spell witness, full app-down gauntlet re-witness at this
tip (tray must be down; scheduled after UAT).
