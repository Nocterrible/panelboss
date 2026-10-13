# RC package v3: PanelBoss ui-1c-reskin fix waves 1-3 (45fcc38..HEAD)

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
