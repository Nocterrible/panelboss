# Pre-release audit punch list (Oct 12, branch ui-1c-reskin @ 45fcc38)

Two-pass design: V first pass blind, second pass with first-pass context;
penny fallback collated separately. Disposition columns are the release
decision: **FIX-NOW** (fix wave), **BACKLOG** (post-ship, listed in
PROJECT-STATE known issues), **DISMISSED** (adjudicated false).

Methodology verdict (earned tonight, thrice): a finding graduates only when
someone RUNS the line. Static passes blessed the MessageBox slot-order bug
that runtime caught, the deep lane's own szExeFile "adjacent probe" false-
positive got committed and reverted inside ten minutes, and the wm trio's
prescribed HWND_MESSAGE value (0xFFFFFFF0) was itself WRONG - C3a measured
that 0xFFFFFFF0 and 0xFFFFFFFF BOTH fail CreateWindowExW while -3 (= the true
winuser.h ((HWND)-3)) creates. Audits correct their correctors; the runtime
probe is the only final court.

## cli / boot
- FIX-NOW HIGH cli.py:447,452 — `_enroll` NameError (dead imports); dead
  since birth, confirmed 3 channels incl. AST probe. Two-line fix, drop `det`.
- FIX-NOW MED cli.py — `Path.home` uncalled in APPDATA-less else branch.
- FIX-NOW MED boot — section-type + `int()` crashes on junk cfg at boot
  (folds into the config coercion cluster below).
- BACKLOG INFO boot — debug-level confessions.
- FIX-NOW MED boot — deepcopy DEFAULTS at merge: PROMOTED from INFO, the
  _gaming rate-handler writes proved the nested DEFAULTS dicts are live
  mutation targets through shallow-merged cfgs. One deepcopy in merge, done.
- DONE MessageBoxTimeoutW slot order (07e6c7d) — runtime-caught, both static
  passes missed it; szExeFile "adjacent finding" DISMISSED (45fcc38 revert).

## camera core (camera.py)
- FIX-NOW HIGH — positional PnP→OpenCV pairing; key on InstanceId (owner's
  own log shows index drift; indexes ARE identity-unsafe).
- FIX-NOW MED — `_open_lock` has no deadline → whole-subsystem wedge.
- FIX-NOW MED — BaseException strands eye "opening" forever (row reap).
- FIX-NOW MED — release outside the lock.
- BACKLOG INFO — handle rotation per poll floods the log.

## state machine (__init__/_boot/_phase/_policy/_cams/_events/_power/_preview)
- FIX-NOW HIGH (2-channel CONFIRMED) — unpause/snooze never re-arms
  `next_poll` (core pass: counting/off; satellites F6: snooze expiring while
  `counting` persists → desk lit all night, `_apply_hold` blocks the plan
  timer's rescue too). Fix: paused→False / snooze-expiry edge sets
  `next_poll = now`.
- FIX-NOW HIGH (CONFIRMED, satellites H1) — stale `_vote_index`: credit armed
  tick N, detector raises, tick N+1 fail-closed consumes it as a genuine
  ABSENT verdict; preview lease pins the credit across the whole lease. Fix:
  clear `_vote_index` in the `_tick` except arm and `_release_camera`.
- FIX-NOW MED (satellites F2) — single-camera lease on a RotatingCamera
  TypeErrors (`read(screen=0)` param); per-tick release+reopen spiral, rotor
  can be re-published via single opener. Route rotors into `_preview_mosaic`.
- FIX-NOW MED (satellites F3) — adopted store handle released TWICE on every
  release path (sweep + `self.camera`), relying on cv2 idempotency one layer
  down. Fix: null the store row on adoption (one owner releases).
- FIX-NOW MED — blind-eye unsatisfiable AND-round (`want` counts never-tallying
  eyes; min_hits degrades to 1-then-infinite-stale). Subtract blind eyes.
- FIX-NOW MED — write_config race: UI mutates shared cfg pre-enqueue, loop
  serializes live dict → `dict changed size` inside TOML writer can ride the
  poison cascade (core pass + satellites F10 agree). Lock + unique tmp +
  deepcopy-at-serialize.
- FIX-NOW LOW (satellites F4/F5, latent) — unguarded positional unpacks in
  both drains; poison event = lost event + aborted drain + tick-guard camera
  release side effect. try/except, log-and-drop unknown actions.
- FIX-NOW LOW (satellites extra) — cli quit path calls `_release_camera` from
  main thread after join timeout while the loop may still own it.
- BACKLOG LOW (satellites F8) — preview lease has no dead-handle eviction
  (corpse re-read until lease end).
- BACKLOG INFO (satellites F7/F9) — fullscreen-guard off-state re-polls at ON
  cadence; `preview_width` odd-type crash.
- BACKLOG BLOCK (F12) — _events.py at the 300-line size-law boundary; split
  on next touch, not a drive-by.

## camera companions (preview/preview_grid/detector/faces/motion/inference — all probed)
- FIX-NOW HIGH detector — `_letterbox` broadcasts-ValueError on 2-D frames
  (grayscale IR/depth); the `ndim==2` guard downstream is DEAD because
  `detect()` crashes first. Fix canvas from repeat/cvtColor per ndim.
- FIX-NOW HIGH detector — ZeroDivisionError on 0-size frame (`max(h,1)`).
- FIX-NOW HIGH detector/inference — onnx head-shape assumption: any *.onnx
  admitted; (1,1000)/(84,8400) crash-per-vote, (1,85,8400) = SILENT garbage
  (class index off-by-one, wrong-class person match). Validate head at
  session build, name the mismatch loudly.
- FIX-NOW HIGH motion — ratio=0 (or all-zero mask) → empty `nonzero` →
  `xs.min()` ValueError. Guard `len(xs)`, treat empty as abstain.
- FIX-NOW MED motion/UI — confidence slider is a dead knob in motion mode
  (MotionDetector ignores `conf`); write `ratio` in motion mode or label it.
- FIX-NOW MED preview_grid — `cvtColor BGR2RGB` crashes mosaic on 2-D frames
  (same mono-driver class as detector H1). Branch on ndim.
- FIX-NOW MED inference/faces — `device_id`/threshold coercion at the config
  boundary (raw ValueError outside the session try; string conf → per-frame
  UFuncTypeError).
- FIX-NOW MED faces — npz save non-atomic (no temp+os.replace) + unlocked
  shared `stored`; corrupt gallery EXITS the app at next boot. (Latent
  cross-thread until a UI enroll path lands — enroll is CLI-only, and it's
  the H4 dead fn.)
- BACKLOG LOWs — silent CPU fallback on unknown `device`; faces[0]-only match;
  NaN sims on zero embedding; `tile_w<=0` unguarded (API-misuse); `_prev_gray`
  2-D alias of caller buffer (copy it); `verbose` accepted-unused; shared
  first-tile aspect in mosaic (documented).
- DISMISSED — npz reserved-keyword names: probed clean on 2.2.6.

## Disposition legend (FINAL, wave 3 - second-gate blocker 1 closure)
Every `- FIX-NOW` line below is CLOSED at this tip; the section heading
maps to the closing commit range: config/cli-boot 9563190/615c1c4/66b631b;
camera-core 1ea8c53 then REDONE 633a5c6 (gate 2 reversal: lock-free
null-first ownership - see RESCOPED note in the camera-core block);
companions c9b6642/e8415e8 + 4399a5d; state 51f8253; satellites guards
51f8253; tray/confessions bf668f4/615c1c4/eff0df7 + warm-menu pump-gate
633a5c6; profiles d7ef04f/cd16772/4399a5d + editor .get 4d26424; data/
feature/UI tabs 1f1320c/37bc169/d6162e2/4d26424; wm pinning f8a74f8/
e8ab8ff + canon alignment 49dc14e; gaming/notice clusters 27856ad +
49dc14e (Ultimate canonical, locale confession, reconcile warning).
EXCEPTIONS demoted out of FIX-NOW here, not silently: (1) motion-mode
confidence row VISIBILITY (does the UI show the row in motion mode?) -
owner UX question parked in RC-PACKAGE honest notes, the write-side
mirror shipped 4d26424 (rescaled 13-03: the first mirror copied a
0.05..0.95 confidence onto a 0.0005..0.02 ratio domain - third-gate
ledger 5, up to 47x the legal top; now a linear domain map); (2) the
_events.py size-law split and overrides queue-marshaling stay the two
documented process defers.
LABEL ARCHAEOLOGY (third-gate ledger 15): the per-section FIX-NOW/BACKLOG
labels below predate waves 2-3; some BACKLOG lines are in fact closed
(HWND_MESSAGE CLOSED by measurement in 1481889 - the audit's prescribed
0xFFFFFFF0 was itself wrong, the real value is -3) and two FIX-NOW lines
were re-scoped by design (camera release: lock-free ownership contract,
see the RESCOPE block; login-gone balloon: symmetric notify shipped in
this ledger's third-gate pass). THIS legend is authoritative over the
section labels; where they disagree, the legend wins.
## /disposition legend

## Third-gate ledger disposition (item -> closure, same night)
1 false-funeral box at shutdown -> cli latches monitor.quit before
   icon.stop (this commit); 2 _MENU_READY modal gate -> the lane's
   docstring analysis holds (swap lands after TrackPopupMenuEx returns;
   re-show tracks the FULL menu deliberately) - ledger DISMISSED with
   the reasoning quoted at the handler; 3 release-lock legend wording ->
   legend LABEL ARCHAEOLOGY clause: the release line is CLOSED BY DESIGN
   CHANGE (single-thread loop ownership contract + null-first swap),
   not "back to pre-audit"; the GIL claim downgraded to "atomic by
   documented single-owner contract, hammer-proven"; 4 _open_timed
   comment honesty -> comment now names the 30 s wait the open side can
   pay (the tick-stall LOW was accepted knowingly: the loop thread never
   calls enumerate on its hot path - tray-thread action only; corrected
   in this pass); 5 ratio mirror scale -> LINEAR DOMAIN MAP
   (0.05..0.95 -> 0.0005..0.02, same direction), comment rewritten;
   6 locale confession -> triggers only on EVIDENCE (non-ASCII header or
   header GUID), residual named: ASCII-lettered localized headers stay
   blind until a real localized dump can be measured; 7 marker chain ->
   w3c_probe section (d): REAL writer, temp store, reconcile, re-read -
   plus write-back now routes to cfg["_path"], not module CONFIG_DIR
   (_persist_plan_state fix; a test's redirected store can no longer
   litter the owner's desk - it already had, once, tonight); 8 stale-
   claim vs deliberate-choice -> accepted BACKLOG (one boot revert,
   documented); 9 rect len guard -> == 4 exact (writer shape (x,y,w,h),
   slots 2/3 ARE w/h - the second-gate's LTRB worry was conditional and
   the condition is false); 10 tray raise-path funeral -> except arm
   queues the real quit (no box: the log line is the confession when
   there is no icon to own one); 11 destroy-mask -> except widened to
   (NameError, tk.TclError), re-raise preserves the original; 12 config
   snapshot belt -> TypeError joins RuntimeError in the retry catch,
   message names the class; 13 login-restore no-profile -> symmetric
   icon.notify added; 14 rationed suspicions: HelloIr None-tolerance
   and Register-argtypes live-degradation are BACKLOG-named;
   worker-is-daemon verified True at construction; 15 label archaeology
   -> legend clause; 16 evidence plumbing -> run_all wires the three
   orphan probes and stamps its own log with tip SHA + timestamp; the
   five-repeat claim lives in the lane receipt it belongs to.
## /third-gate ledger

## EPILOGUE - VERDICT: RELEASE (rc-2026-10-13d @ 93c9cc3, pushed)
Fourth submission returned RELEASE, no blockers. Ledger 7 closed in
court: the morning desk's live blocker (ms-teams.exe - Screen lock
block, named by the boot log itself) was the exact display-held state
that made the stale unknown_state fixture red at 07:21 - the suite
was testing the desk, and the desk filed testimony. The first
hundred milliseconds of the released build ran the night's fixes live:
assistant adoption confessed its mismatch, the flag self-healed to
disk, and the blocker line appeared through the new decoder.
OPEN FOR THE OWNER (no code risk): the motion-mode confidence-row
visibility call (parked in RC-PACKAGE honest notes); the merge word
to master; watch items per the gate's RISK line: camera release +
30 s open deadline on the multi-cam desk at first quit/reboot - late
presence decisions, not crashes, would be the symptom.
## /epilogue

## RESCOPE, camera-core (second gate blocker 2): the deadlined RELEASE
was reverted within the wave - release takes ownership (null-first swap,
lock-free), queue-behind-open deleted along with the stall, the None-
release race, and the destructor-lie skip path. The OPEN keeps its
30 s deadline and abstains. Verified: camcore_probe 3/3 (hammer shape).

## Fix wave status (Oct 13, final-gate BLOCK absorbed and being closed)
LANDED+GATED+PUSHED (45fcc38..91fc722): config 9563190; state 51f8253; camid
f3061c8+13e5465; display 1481889; tray/cli bf668f4; profiles d7ef04f+cd16772;
ui-workers 1f1320c+37bc169; nits d6162e2; wm pinning f8a74f8; gate-2 fixup
e8ab8ff (taskbar RECT poison + profiles_test honest fake). Consolidated
gauntlet rc=0 ALL GREEN (complete), app stopped, window sections real.
FINAL GATE #1 VERDICT: BLOCK, both blockers accepted and CLOSED:
- B1 dead-tray quit bypassed the loop (window+lock would outlive the icon):
  FIXED 615c1c4 (events.put quit; the shutdown-note false-confession path
  closes on the same handler because monitor.quit is now always set before
  tray.stop).
- B2 claim-vs-diff gap -> WAVE 2 LANDED AND GATED:
  W2A companions c9b6642+e8415e8 (letterbox 2-D, 0-size abstain before
  inference, onnx head validated at get_session - sole production path,
  ratio=0 abstain + gray copy, faces atomic+locked save + enroll-write
  lock fix, all-faces match, tile floor, preview finally);
  W2B camera core 1ea8c53 (30 s open-lock deadline with per-tick abstain,
  BaseException row reap, one handle one release, skipped release DROPS
  the handle - 4399a5d closed the orphan twin; rotor leases via mosaic);
  W2C 27856ad (boot containment, merge_seen exact-first, plan-ownership
  marker + boot reconcile, GUID-preferred powercfg decode, insightface
  honest box). Architect-inline: enroll imports + tmp sweep 615c1c4.
  Wave-2 gate: no BLOCK, three dictated micro-fixes -> 4399a5d.
RESCOPED (gate B2 demanded honest dispositions): the "InstanceId pairing"
line's true state - labels/hides ARE InstanceId-keyed (shipped pre-wave),
label-lying-by-position closed by C4 (unique-name attach or withhold);
what REMAINS is the acknowledged v1 limit (owner decision, Oct 12):
non-unique friendly names cannot be mapped to an OpenCV index by name;
the wizard confesses this in-text and the roster stays index-keyed by
design. Recorded here so the re-tagged package says what is true.
Punch-list hygiene: item dispositions below are updated to
FIXED(<sha>) / WAVE2 / BACKLOG as the lines land; the "In flight/queued"
audit-scan section is retired.
## /fix wave status

## tray shell (tray/taskbar/display — deep, VERDICT FAIL, both HIGHs = silent
daemon death with process alive)
- FIX-NOW HIGH tray.py:195 — pystray 0.19.5 `_mainloop` swallows pump
  exceptions then NIM_DELETEs the icon: WndProc/dispatch failure = icon gone
  quietly, process alive, no control surface, no app-log line. Route
  pystray's logger into the app log + state-loop `is_alive()` watch on the
  Tray thread so a dead pump confesses.
- FIX-NOW HIGH display.py:179-190 — no try/except around `_record`; null/late
  lParam raises, kills the watcher daemon (pythonw: excepthook to nowhere),
  `watcher` stays non-None with state frozen = display tracking silently
  dead. Wrap per-message, fail-open like the state loop.
- FIX-NOW MED display.py:360,172-185 — the repo's OWN named trap recurs:
  `GetForegroundWindow` unpinned (c_int truncation → fullscreen guard lies),
  power-sink Register/Unregister double-truncated (works only under 2^31
  handles). Pin restype/argtypes.
- FIX-NOW MED taskbar.py:326,91-160 — same class: `OpenProcess` restype and
  every hwnd-taking user32 call unpinned; a misread costs a false cohabitants
  verdict. Batch with the display.py pinning.
- FIX-NOW MED tray.py:213-234 — `_warm_menu` swaps `icon.menu` from the warm
  worker: HMENU destroy/create off the pump thread; right-click during the
  ~13s warm window destroys an HMENU mid modal loop. Gate the swap on pump
  liveness or retry till the pump confirms.
- BACKLOG LOW display.py:45 — `HWND_MESSAGE` = 0xFFFFFFFF (real 0xFFFFFFF0):
  message-only branch dead since birth, invisible top-level fallback carries
  all; fix constant or delete branch + comment.
- BACKLOG LOW display.py:143-171 — watcher startup failure leaves `state=1.0`
  frozen ("assume on") with one unread log line; set watcher=None / surface.
- BACKLOG LOW display.py:295 — `wake(timeout=)` dead param, always True;
  SMTO 1500ms × windows × 2 rounds bounds the loop-cadence dip per wake.
- INFO — menu callbacks on the pump thread touch shared cfg dict (single-key
  writes = safe today); watcher queue unbounded but fed only by power
  framework, not raw broadcasts → no flapping growth. taskbar is COM-free
  (audit item clean); retry loop exits on stop, no forever-spin.

## support layer (theme/overrides/deps/shield/kofi/helpbtn — deep, PASS;
auditor confessed brief-premise drift and audited the real files; all six
import-safe, offline promise HOLDS (kofi = webbrowser.open spawn, no fetch),
Tips timer discipline verified wired on all exits)
- FIX-NOW MED overrides.py:79-82 — merge_seen folds override rows via
  bidirectional SUBSTRING match on first-token base, first match wins:
  python.exe vs pythonw.exe rows show "not overridden" and _diff would
  stage types for the WRONG object. Exact-match first; substring only on
  unique candidate, else warn.
- FIX-NOW MED faces/cli.py:343-354 — insightface-missing story exits the
  app under a misleading "detector would not build" banner (broad except
  in _warm_monitor); Deprompt is wired only for whircam. Route that
  RuntimeError to the Deprompt/notice path.
- FIX-NOW LOW→fold-in cli._drive — the real crash shield is log-ONLY: a
  dead settings window is user-invisible under pythonw. One-shot
  icon.notify balloon on that path (rides the tray-confession packet).
- BACKLOG LOW overrides.py:304,341 — cross-thread self.after from daemon
  workers (not doc-safe); marshal via the existing tick-drained queue.
- BACKLOG LOW helpbtn.py:116,60 — pinned tips die on the tip's own Leave,
  and re-hover silently unpins: "click pins it" holds only while the cursor
  never crosses the tip. Exempt pinned from Leave; skip reset on same-text
  hover.
- BACKLOG LOW theme.py:190 — unknown/stale ui.skin silently re-derives as
  MODERN; log once at fallback.
- INFO — apply_ctk_font's ThemeManager mutation verified LIVE on installed
  CTk 6.0.0 (right node, survives appearance-mode re-set, no stale-cache
  path; renamed node would fail LOUD via KeyError). get_available_providers
  is the onnx probe; cv2 is a hard import so ui.is_available() (tk-only)
  lets a missing cv2 die into the misleading "settings window died" line -
  name cv2 there or probe it.

## TALLY (audit closed Oct 13, 13 batches, all reported - 5 via resurrection
pokes, 2 premise-drift-confessed, 1 false-positive adjudicated by live probe)
- VERDICTS: 0 redesign-class; every batch PASS or PARTIAL at patch scale;
  tray shell's FAIL is 2 HIGHs fixable in one confession patch.
- FIX-NOW: ~17 HIGH + ~25 MED, mapped to SIX commits:
  C1 config normalizer + deepcopy-at-merge (kills the coercion cluster,
     _detection device KeyError, the 6 DEFAULTS-alias sites, malformed
     profile/login rows; ~10 findings)
  C2 state re-arm pair (unpause next_poll; stale _vote_index clear)
  C3 guarded-worker pattern x5 + tray/display death confessions
     (pystray logger bridge, is_alive watch, _record wrap, _drive balloon)
  C4 camera identity InstanceId keying (pairing HIGH + positional-label
     fold-ins + wizard reload-race + main-thread PnP off-thread)
  C5 profiles apply lifecycle (worker wrap + re-entrancy flag + row
     validation + save lock)
  C6 displaycfg rc surfacing + HANDLE pinning batch (display/taskbar/
     _hdr trio) + trailing tab-lifecycle nit packet (veil cancel,
     sync_region coalesce, skin-rebuild dress/switch restores, helpbtn,
     theme fallback log, _events size-law split on touch)
- BACKLOG: ~20 LOW/INFO, each with its file:line and one-sentence fix.
- DISMISSED with evidence: szExeFile class-descriptor false positive;
  npz reserved names (probed clean); camera tab-split claim (parse is JSON).

## feature tabs (_general/_camedit/_preview/_detection/_hints — deep, PARTIAL;
sweeps CLEAN: no lease orphan on any exit path, editor index drift contained,
autostart registry discipline right, _detection IS the complete coercion
boundary - template for the normalizer)
- FIX-NOW MED _detection.py:50 — bare dict lookup on device label map at
  window BUILD: one hand-edited device string = KeyError in __init__ = cli
  stops the monitor and QUITS the app - the UI is more fragile on config
  than the engine (which fails open). .get(...,"auto") + normalize in merge.
- FIX-NOW MED (the double-writer, now fully named) _shell.py:421-426 ↔
  state/_events.py:208,233,261 — two lock-free write_config callers
  serializing the same live dict: UI size-changing table edits vs monitor
  identity writes = RuntimeError; UI side silently loses the debounced save,
  monitor side dies the tick AND the lease cooloff (next toggle re-pays the
  20-27s driver open). Single-writer persistence: lock (or queue) shared by
  both threads - the punch-list cfg fix, sharpened.
- FIX-NOW MED _general.py:219-223 — autostart toggle's worker: unguarded
  worker after() + no single-flight; destroyed mid-registry = invisible
  TclError (pythonw) and the switch lies until next tray-open; double-flip
  races two workers, last-landing callback can show the OPPOSITE of final
  registry state. try/except + disable for the round-trip.
- BACKLOG LOW _preview.py:281 — `_draw`'s preview_width un-floored (card
  path floors at 360): <=0 or non-numeric = raise per tick, "ui tick failed"
  spam at ~5fps, frozen preview. Clamp at read, mirror the state-side clamp.
- BACKLOG LOW _preview.py:185-191 — scan names attached POSITIONALLY to
  OpenCV indexes (guarded by uniqueness only) - the docstring itself concedes
  order can differ: unique-but-wrong labels on a reordered multi-cam desk
  (policies still right; labels lie). Withhold label when unprovable; folds
  into the InstanceId keying wave. PART-CLOSED by the wizard-parity wave:
  the wizard no longer rides positional names for its identity keys (open
  indexes get idx: rows; claims via maps only) - the ADD PANE's displayed
  names stay positional until the ordinal oracle lands.
- BACKLOG MED dshow.py ordinal oracle — CLSID_SystemDeviceEnum is registered
  NOWHERE on the dev desk (HKLM/HKCU/WOW64 all probed; devenum+qedit
  DllGetClassObject -> CLASS_E_CLASSNOTAVAILABLE; cv2 statically compiles
  the enumerator, hence DSHOW works for it). In-process routes to
  index->instance are blocked on this box; the wizard degrades honestly to
  idx: keys. Next routes (tried-and-failed documented in dshow.py): a
  matching devenum regsvr32 (admin) or MFEnumDeviceSources through a
  reg-free activation context. Until then dshow.py answers {} (warn-once).
  Gate note (optional future): when identity_map claims an index N that a
  hidden "idx:N" key also covers, drop the idx: key - the row now has a
  real instance to ride (stale idx: keys mis-hide the new owner of N
  until the wizard re-run clears them).
 - BACKLOG LOW (gate d4000b1 wave, finding 2 accepted): a ghost "idx:N"
   label lingers in the toml when the bind migration is skipped because
   the instance already carries a label. Harmless (display precedence
   ignores it once a real identity claims the index); an identity pass
   may sweep: pop ghost when labels[inst] non-blank.
 - BACKLOG MED (gate d4000b1 wave, finding 3): an IR seat ON DUTY gets
   no policy card - _rebuild_cam_rows iterates the cv2 scan and the
   HELLO_IR sentinel is never in it, so per-camera modes for the IR eye
   are unreachable from the panel (the global table governs). Fix rides
   next IR pass: append the sentinel row from cfg when roster lists it.
   CLOSED (e69c22c: ir_row_spec appends the sentinel duty card from the
   roster - remove/policy pair reachable; the redesign went further:
   a62d9b9 gives EVERY bridge group its own setup-screen card with a
   snapshot, the seat the wizard never had).
 - SHIPPED (camdiag wave: 2e4c6e1, f689587, 98f4e23, aad8e8e, e69c22c,
   7289b14; owner amendments 1-5 all folded; the wizard-era surfaces of
   this block - in-wizard pre-mark display and the wizard's hidden-row
   SHOW list - were superseded by the redesign the same night, see the
   redesign section at the file's end; the record, the sweep trigger,
   the stickiness law, and the placeholder reset survived verbatim):
   first-launch /
   reindex / manual-rescan diagnostic rides the existing scan under a
   held veil ("testing cameras, please wait" + honest N-of-M progress);
   probes are THREADED (opens serialize on the device-tree lock, the
   15 s first-frame budgets overlap - not n x 15 s); no-image indexes
   pre-mark virtual in the wizard and carry the picker suffix; the
   MANUAL rescan button forces the sweep regardless of the index set
   (the automatic path stays first-launch/reindex); the
   stickiness law: a row the human touched (label, bind, or the new
   shown list) is never re-hidden by the sweep; the wizard lists every
   hidden row with a one-at-a-time SHOW button (unhide-all stays as
   the blunt tool); preview resets to a placeholder IMAGE (never
   None - CTk trap) on every step change and every list change, both
   panes (framebox.clear on the cameras event).
- BACKLOG LOW _camedit.py:77-100 — wizard hide/label saves never re-fire
  _apply_cameras: "(hidden)" badges stale until manual rescan. Push a
  "cameras" ui_event after the identity write. CLOSED (the identity
  handler's resync fanout landed that round trip, and stage 4 (9a54ebd)
  made the hidden list ride the same fanout: every identity write
  rebuilds rows and hides together).
- BACKLOG LOW _shell.py:232 + _preview.py:92 — skin rebuild resets live-
  preview switch to off while frames may land ~2.5s more (UI claims off).
  Restore pre-rebuild selection or enqueue preview 0 at rebuild start.
- INFO (confirmed, feeds the same wave) _events.py:244-253 — the camera_
  identity handler's `labels[inst]=` mutates the DEFAULTS alias when the
  file lacks [camera.labels] (wizard Save triggers): copy the container on
  entry. Sixth site, same one fix (deepcopy at merge).

## widgets/text/constants/camid (deep, PASS - no HIGH; module-state and
import sweeps clean; _constants pure)
SUPERSEDED by the camera-setup redesign (a62d9b9): every _camid.py
finding below was the WIZARD's, and the wizard's funeral is that
commit ("the tab gate, the one rescan path, and the wizard's
funeral"). The ladder lines retired with the ladder (the redesign
refreshes through the resync fanout instead of recheck ladders);
the main-thread PnP query is structurally excluded in the
successor (_assign._gather fetches off-thread from birth); the
stale-dress and post-destroy configure findings retired with their
class. The data functions live on in _identity.py, tested by the
same file's data sections (camid_test keeps them).
- FIX-NOW MED _camid.py:269 — `_unhide_all`'s 250ms deferred reload ASSUMES
  the drain already happened; a tick blocked on a slow open (~16s for a
  virtual cam) drains later → stale `hidden` read, freed device missing from
  `_cands`, wizard stuck "nothing left visible" with no re-trigger. Gate the
  reload on hidden-count actually shrinking (bounded recheck or the
  ui_events round-trip).
- FIX-NOW MED _camid.py:208-212 — the "silent no-op" comment guards only the
  SCHEDULING; the after(0) BUSY callback itself raises TclError from
  preview.configure post-destroy, on the main event path. Wrap the lambda
  body, or publish BUSY through the _pump like frames.
- FIX-NOW MED _camid.py:75-108 vs _shell rebuild — IdentifyWindow survives
  skin rebuild with build-time-spread palette: stale dress until reopen.
  Destroy (or re-dress) app._camid_win in rebuild_for_skin.
- FIX-NOW MED _camid.py:272 — reload falls back to camera_devices() (a
  10s-timeout powershell PnP query) ON THE MAIN TK THREAD when _devs is
  empty: ~10s UI freeze worst case. Worker + after() marshal, like _gather.
- BACKLOG LOW _camid.py:209 — the file's ONE naked off-main Tcl call
  (worker-thread self.after); survives on GIL, route via _pump flag.
- BACKLOG LOW _widgets.py:163 — SkewCombo generator footgun (list() at 137,
  values[0] on the ORIGINAL arg at 163); use self._values.
- BACKLOG LOW _widgets.py:21 — set_text's cget diff-guard is label/button-
  class only; a text-class call site would die in configure. Document or
  guard.
- BACKLOG INFO _camid.py:172 — `_cands` ignores PnP `status`: dead devices
  get a step and a wasted open. Flag/skip.

## data tabs (_prof_apply/_prof_pins/_prof_editor/_profiles/_restore/_power/_gaming
— deep, PARTIAL; bare-thread sweep: 4 workers, 3 unguarded, gaming's foreground
probe is the verified model: try/except + guarded after)
- FIX-NOW HIGH _prof_apply.py:245-258 — (sibling-confirmed) no try/except,
  done() only on return path, naked after raises TclError on mid-apply
  destroy: any raise = stuck "reshaping the desktop..." forever, log-only.
  Wrap work(), always marshal one done(ok, text) through a guarded after.
- FIX-NOW HIGH _prof_apply.py:237-258 — NO RE-ENTRANCY: buttons live during
  run, `data` is the shared `_prof_data` the UI keeps mutating mid-apply:
  double-click = double desk reshuffle + concurrent lock-free saves (can
  corrupt profiles.json into quarantine - only "create new..." survives);
  stale done() repaints the pane the user left, shows A's result under B.
  One _applying flag + disabled buttons + refuse edits in flight.
- FIX-NOW MED _prof_editor.py:111,279,342 + _prof_pins.py:64,176 — pin rows
  subscripted raw; one bad store row raises inside the render chain whose
  finally DESTROYS the old body → half-dead pane, invisible under pythonw.
  .get()/per-row try + gray note. (UI side of the profiles load() HIGH -
  same pair.)
- FIX-NOW MED _restore.py:81,95,121 — picker reads DISK via fresh load()
  instead of in-memory _prof_data: corrupt store = ghost armed name not in
  its own list; login "last" restore is silent-log-only while the note
  promises the wait; named-gone gets a balloon, "last"-gone gets nothing;
  400ms debounce hides a just-created profile from the first render. Build
  from _prof_data, flag ghost armed, symmetrical balloons.
- FIX-NOW MED _power.py:337-371 — assistant switch: no busy state, unguarded
  work(), and cfg["power"]["assistant_task"] written FROM THE WORKER THREAD
  (new cross-thread write site): fast double-click races two workers against
  one task store (last user click can lose); install/uninstall raise = switch
  shows ON with no task for the session. Disable until first assistant_ui,
  wrap work().
- FIX-NOW MED (promotion) _gaming.py:185-207 — rate handlers bare-subscript
  cfg["gaming"]["game_hz"]: explicit null in file survives shallow merge →
  TypeError in the Tk callback, silent evaporating pick under pythonw; AND
  on fresh cfg the nested dict IS DEFAULTS → UI writes mutate process-global
  DEFAULTS. Confirms the core-boot deepcopy INFO as a live corruption path -
  the config-boundary normalizer must deepcopy DEFAULTS sections at merge.
- FIX-NOW LOW _power.py:159-176 — boot truth() thread unguarded: one raise =
  switch drifts from the task store silently until next skin rebuild.
- INFO — per-row hover carriers are row-owned (no leak; tooltip lingering on
  in-place unpin mid-hover = kill tip when _pin_remove destroys a hovered
  row); rescue_lost() runs sync on UI thread (freeze class apply was moved
  off-thread for - accept or worker it). STALE-SELECTION SWEEP CLEAN: all
  pickers string-keyed, in-place paths winfo_exists-guarded, upsert threshold
  cross falls back to full repaint correctly.

## UI layout core (window/__init__, _shell, _runtime, _scroll — deep, PASS,
2 MED; probe-verified: _dead/_LIVE integrity, bind idempotency, wheel-guard
complementarity — the clamp/guard same-expression law CONFIRMED from outside)
- FIX-NOW MED _shell.py:149,234-249 — `_show_first`'s after(300,_unveil) is
  never cancelled; rebuild_for_skin reuses the veil slot synchronously →
  stale timer lifts the REBUILD veil up to 300ms early, exposing the CTk
  erase sweep (same race: two tray-opens <300ms apart). Track `_unveil_job`,
  after_cancel in _veil/rebuild; lift rebuild's veil from its own after.
- FIX-NOW MED _shell.py:116,551-554 — boot has no failure containment:
  build_all/_show_first raise = withdrawn root, no mainloop, no tick; an
  in-process retry then hits the measured second-root-kills-Tcl class.
  run() wraps construction, destroys root, re-raises.
- FIX-NOW LOW _scroll.py:174-193 — sync_region re-arms 2 afters per call with
  no dedup, and the TOPLEVEL <Destroy> binding fires it for EVERY live host
  on EVERY widget destroy: a repaint = ~400 pending _region runs (each
  bbox("all")). Coalesce per host with the existing _save/_on_configure
  debounce pattern.
- BACKLOG LOW _scroll.py:126-129 — per-host <Destroy> lambda add="+" never
  unbound; no-op via _dead (verified) but bindtag closures accumulate
  unboundedly across rebuilds/repaints. unbind(func) in ScrollHost.destroy.
- BACKLOG LOW _scroll.py:195 — `_width`'s itemconfigure unguarded while
  sibling `_region` swallows TclError (asymmetric teardown safety).
- BACKLOG LOW _shell.py:290 — veil pinned to body box read pre-map:
  start_minimized + early rebuild pins to the stale 1x1 default. Read after
  update_idletasks, or pin relwidth/relheight to self.
- BACKLOG INFO — size-save skips first drag-back-to-recalled-size (compare
  last-WRITTEN pair); deiconify-before-veil leaves an un-veiled half-paint if
  _veil raises (veil first, then map); dead assignment `build_all = ...` :248.

## profiles.py (deep; store design SOUND - atomic save, EDID keys, zero shell
in the call graph, all 26 entries import-clean. Weak flank = user-editable rows)
- FIX-NOW MED+ profiles.py:114-126 — `load()` validates lists, not ROWS: a
  hand-edited string row passes, `apply` dies mid-restore (layout+HDR already
  committed) at `s.get`/`d["id"]`; no save, no rollback note. Probed:
  `desk_mismatch` TypeError. Fix: drop non-dict/missing-key rows in `load()`
  with the rotted-profile warning. (HIGH as a class only because the UI
  worker below has no try/except — the pair is the bug.)
- FIX-NOW MED profiles.py:132-134 — `save()` lock-free; apply worker AND UI
  main thread dump the same `profiles.json.tmp`; collision commits
  interleaved garbage, next load quarantines it (setups survive only in
  `.corrupt`). One module lock around dump+replace.
- FIX-NOW MED profiles.py:907-913 — `login` never coerced in `load()` (unlike
  `last`): string `took` or list `login` crashes AFTER restore completes →
  final `save` skipped, `used`/`last` lost, worker hangs (see HIGH). Validate
  like `last`.
- FIX-NOW MED profiles.py:199,351 — `create()`/`pin()` default match="process"
  = the colliding mode: a process pin moves EVERY live window of the app, so
  profile A relocates profile B's pinned seats; same-proc double pins =
  permanent silent no-show. Default new pins to "process + title".
- FIX-NOW MED profiles.py:851-888 — launch-then-position race: relaunch
  returns on FIRST window answering a process pin (splash!) → splash parked
  at the main seat, real window unplaced, `no_shows` empty = unreported.
  Size-threshold or one re-verify after the pin's wait window.
- BACKLOG LOW profiles.py:702-708 — pins restore by ABSOLUTE rect (monitor
  label informational); missing panel → placed off-desktop, rescued to
  primary post-hoc, seat lost. Note in the best-effort dialog wording.
- BACKLOG LOW profiles.py:136 — `save()` bool ignored by ALL callers; disk
  failure = silent memory/disk divergence, picker shows pre-edit state.
- INFO (confirmed, belongs to UI batch) _prof_apply.py:245-257 — `work()` on
  a bare thread, no try/except, `done()` only on return: any raise = stuck
  tab. Wrap + schedule done with error text. (Profiles' HIGH is only user-
  visible-because-of-this.)

## wm structs (_winapi/_displaycfg/_hdr — resurrected-session report, structs
byte-probed against the live OS; HANDLE-trap sweep clean)
- FIX-NOW MED _displaycfg — `apply_layout` discards per-device staged rcs;
  refused enable + successful commit = "applied" is a lie. Surface per-device
  failure.
- FIX-NOW MED _displaycfg — empty-`DEVMODEW` fallback base is the exact shape
  measured to answer -2; refuse with a named line or CDS_TEST first.
- BACKLOG LOWs — no ERROR_INSUFFICIENT_BUFFER re-size loop; count iteration;
  re-read after commit.
- _winapi: probe table CLEAR.

## gaming / system integration
- FIX-NOW MED — toml coercion cluster (gaming + `*_hz`): silently freezes the
  engine at debug level; ONE normalizer at the config boundary, shared with
  the boot/int crashes above.
- FIX-NOW MED — quit-mid-game orphans the High-Performance plan (loop-local
  `side`); persist plan ownership + boot reconcile.
- FIX-NOW MED — English-only powercfg/DISPLAY_WORDS parsing kills the
  display-gate on localized Windows.
- CLEAN — HKCU-only, no shell interpolation, query-verified plan switch,
  monotonic clocks throughout.

## guard / tests (already shipped this branch)
- Global\ mutex guard + belt + loud UNGUARDED (8c1b85d); run_all DEGRADED
  rc=4 + guard_test (888857c); TclError flags, NIM_ADD anti-vacuous, scratch
  hygiene; PANELBOSS_CONFIG_DIR corrected.

## Wave C ledger lines (gate SHIP @ bb38943, Oct 13 night)
- find_camera's stall RuntimeError text says "check privacy settings" -
  a wedged driver would confess as a privacy LIE; append "; or a wedged
  door - see door-join warnings" (one-liner, next camera.py touch).
- _probe's load-time leg (get_config -> _extend_by_name) is NOT
  externally bounded - opt-in name_contains + wedged MF door can hang
  BOOT; join the cycle or narrow the exemption comment (LOW, next touch).
- camera.py 1283 vs ~1000 grandfather: next wave that grows it pays
  the named Rotor/AsyncOpener seam FIRST (gate's standing rule).
- Enum watchdog live-proof pending: the owner's wedged desk (DroidCam
  index-1 class) is the real harness; bare "testing cameras..." forever
  must be DEAD behavior at this tip.

## Fix-wave findings accepted on the ledger (Oct 13, gate SHIP @ 36ba449)
- EMPTY-ROSTER SPLIT (MED, engine): an all-unchecked setup board posts
  index []; config.normalize_index maps empty -> [0], so the NEXT
  restart puts index 0 on duty while the panes read [] as honest empty
  - three readers, two meanings of one key (same split as
  _cam_remove's last camera). Engine fix when touched: normalize_index
  ([])->[] + fallback arms in _preview and the single-vote path.
  Release note sentence owed to users: "unchecking every camera leaves
  camera 0 on the next restart".
- NO-CARD ROSTER SEATS (LOW): a rostered index with no card (>=8 or
  -2 with no bridge) is dropped by OK's set-diff (omission removes).
  Fix: union no-card seats into the posted roster verb.
- ONE-SIDED CONSENT INFO (LOW): the evidence INFO speaks only when it
  fires; the virgin branch lands enabled=False in silence - add the
  else-line "section reads virgin - booting dark".
- gaming_ui 60 s watchdog: 2 fail / 2 green today, pre-wave suite,
  assertions all pass before the hang; third app-down failure ->
  instrument the teardown position.

## Approved scope, tagged-candidate (owner, Oct 13 evening): HDR wave
Per-monitor HDR joins the profile/power-option controls (per-display
"hdr": null|true|false applied through wm/_hdr.py's proven type-16
SET after mode changes, dropdown rendered only on hdr_states()-
supported panels) + AUTO-SWITCH tiers, opt-in default-off: video-
ACTIVITY auto-on (PDH GPU-Engine VideoDecode/Processing counters -
public, unelevated; the RTX-HDR use case: any video stream flips
HDR on so NVIDIA's SDR->HDR transmute has a canvas; Auto HDR games
cannot false-trip it while SDR, per MS docs) with hysteresis +
idle-timeout, and an mpv JSON-IPC HDR-content tier (primaries/
gamma; loose match per mpv's own warning). WM_DISPLAYCHANGE listener
syncs state when anyone toggles externally. Verdict research + the
manifest-verification that killed the ETW-color-space myth: this
section's commit history; full design: redesign-packet.md amendment
8 (scratch). Feature wave AFTER tag #2.

## Redesign (owner law, Oct 13 afternoon): "blow it away"
The curation UX collapses into ONE flow: the detection tab is gated
behind a big consent switch (OFF on first boot - no camera opens until
the user says so, and a broken camera world can never lock the app out);
toggling or the rescan button opens the setup screen - progress veil at
the bottom, camera CARDS spawning as each reports (index + device
detail header, snapshot, optional rename, hide checkbox; timed-out
cameras get a card that says so; IR cameras included); the Identify
window and its button are DELETED; the hidden list lives at the bottom
of the camera card. Packet: redesign-packet.md (scratch dir).
STATUS: stage 0 (crash re-land, 61d9137) + stage 1 (consent gate,
980d55a) committed; gate SHIP-WITH-FIXES, owed accepts folded into
stage 2: five unguarded dialog X's (same crash law - the gate's worse-
sibling), migration predicate extended to hidden/shown/non-stock index,
live-preview switch honors consent (verified by hand:
enumerate_cameras opens every index 0..7 - the TRAY MENU was lighting
the LED on a right-click; now an info row when off), _close re-
entrancy, camera_enabled resync post. Stages 2-5 in flight.
Push awaits the full-runner receipt at the final tip (app down, ALL
GREEN complete) - the s1b log vanished with the swept wave; no
honor-system pushes.
LAW (learned the lost-work way): STAGE every in-progress edit at each
red->green milestone; unstaged changes are a rumor - one worktree sweep
during review ate an entire crash-fix wave between two porcelain checks
and it was re-landed from the commit message alone.

## In flight / queued
RETIRED (Oct 13): audit queue drained; fix waves 1-3 landed; second-gate
dispositions closed in wave 3 + this ledger's third-gate fixes. Loop
state: third submission returned BLOCK-ON-PROCESS (wave-3 range carried
no independent gate) - the reviewer pass is dispatched as part of this
resubmission cycle; on RELEASE: merge word to master.

## CAMERA-SETUP REDESIGN - CLOSING STATUS (complements the architect's
## Redesign section above - intent is theirs, this is the per-stage
## ledger; the duplicate-heading look is two authors one night, not
## two plans)
## (owner: "blow it away") - CODE-COMPLETE, first
## launch pending owner's witness (Oct 13)
- CONSENT (laws 1+2): [camera] enabled=false stock; the load migration
  reads the file (labels/bindings/hidden/shown/diag record or a
  non-stock index = a human set this box up -> true; virgin -> false;
  an explicit value always wins). Duty gate at the _poll head (a
  mid-duty disable drains there, roster survives); the preview lease
  gates the same way (gate finding 5); the tray camera submenu answers
  a right-click with an info row INSTEAD of enumerate_cameras (the
  menu itself used to open every index); the boot scan is gated; the
  detection tab grays behind ONE big switch - ON asks (setup IS the
  enable), OFF needs no ceremony. (980d55a, 1d19fc4, a62d9b9)
- ONE SETUP SCREEN (laws 3+4): _assign.py - every enumerated index
  (dead seats earn timed-out cards) and every bridge group gets a
  card, snapshot per feed (black frames are an answer), diff-only
  renames, hide checkbox (dark cards start CHECKED, keeping one
  posts the STICKY show verb), queue+pump marshaling (no worker ever
  touches a widget), scheduled retire from birth on both X and OK,
  OK posting the EXISTING identity verbs plus camera_enabled. The
  wizard and its button are deleted; the data functions survive in
  _identity.py (git mv). (a62d9b9)
- HIDDEN LIST (law 5): bottom of the camera card, per-row SHOW riding
  the same sticky verb and the identity resync fanout. (9a54ebd)
- CRASH LAW APP-WIDE: five dialog Xs + every command button retire by
  withdraw+after(0,destroy); an app-wide source ban asserts it in
  assign_test. (1d19fc4, a62d9b9)
- COVERAGE RECORD, honest: the diagnostic suffix's "record covers
  THIS scan" display gate is widget-side (the _apply_cameras /
  _rebuild_cam_rows consumers); the offline suites pin the membership
  finder and the truth tables, the gate line itself is smoke-only.
- KNOWN BLEMISH: the stage-3 commit subject carries one stray CJK
  glyph ("keeps the谱" - lineage was the word). No-amend law kept it;
  noted here so the final-gate package reads it as a typo, not a
  concealment.
- FOLLOW-UPS (owner's call, none owed): tray menu can show a stale
  roster after a switch flip (update_menu timing); consent-off grays
  the hidden list's SHOW buttons with the whole tab (law 2 as
  written; lifting the scope is two lines); the stale-idx: keys note
  above now clears itself - a setup re-run re-derives the maps.
- DEPLOY SHAPE: the HKCU Run key fires THIS worktree's venv directly
  (run.py --autostart), so there is no separate installed tree: the
  tip IS the deployment, the kill leg is the process, and the copy
  leg is a no-op. First launch happens on the owner's word.

## HDR WAVE (amendment 8, Oct 13 evening) - CLOSED, four commits

- DATA LAYER: [hdr] auto={} (model -> off|video|content) + mpv_pipe,
  [gaming].hdr={} (short -> bool, ABSENCE = hands off: TOML has no
  null, "keep" deletes the key); boolmap/tiermap normalize kinds
  (bad entry dies by name, survivors stay). profiles.load guards the
  per-display hdr tri-state. (38c1343)
- THE PROBE (wm/_videostats.py): PDH GPU Engine \Utilization
  Percentage over the video-family instances ONLY - VideoDecode(2)+
  VideoProcessing(4) per the manifest docs (URL in the header);
  encode excluded (recording is not watching), jpeg/vendor-codec
  catch-alls excluded. Instance matcher validated against BOTH
  spellings measured on this box (NVIDIA engtype_VideoDecode, iGPU
  "video decode 1" with spaces). Mechanics mirror gpu.py's measured
  law (fresh query per call, collect pair, per-instance adds); the
  English door is PdhAddEnglishCounterW - the packet's
  "…CounterPath" name does not exist (measured AttributeError; the
  fixup rode commit e7616d9). The mpv matcher is pure
  (bt.2020+pq/hlg, loose spellings); the pipe probe waits bounded.
  (38c1343, e7616d9)
- THE WATCHER (state/_hdrwatch.py): pure hysteresis -
  ENGAGE_SEC=2.0 unbroken busy to light, RELEASE_SEC=30.0 quiet to
  hand back, both re-anchoring on emit (a held edge commands ONCE);
  own thread (cli arm, unconditional, zero sense reads while the
  tier map is empty - the virgin default costs one dict read per
  tick). NEVER rides the duty _poll. (2cf3b50)
- THE BROADCAST EAR, measured twice: WM_DISPLAYCHANGE is SENT to
  the window proc (it never rides the queue - the pump's
  PeekMessage is structurally blind) and the broadcast enumerator
  SKIPS hidden windows - the old message-only shape caught nothing
  while a real hdr_set round trip flew. The watcher's window is
  now WS_VISIBLE|WS_EX_TOOLWINDOW at -32000 (on screen nowhere,
  out of Alt+Tab), the queue put lives in _def_window, routed
  through _ACTIVE (the ear goes deaf when the window dies).
  displaychange -> _drain_display posts ("hdr_sync", None) and
  never feeds _notice_screens (a color flip says nothing about the
  lamps). Live proof printed:
  "queue: [(displaychange,0.0,ts),(displaychange,0.0,ts)] …
  ROUND TRIP OK" - one event per real flip, Go2HDR's claim verified
  here. (2cf3b50)
- APPLY ORDER: profiles step 3 weaves hdr_display_plan - an
  explicit per-panel true/false OUTRANKS snap and the wide ask (an
  instruction beats a memory), the wide ask keeps the unclaimed
  panels, a leave-alone profile now applies its explicit rows; the
  plan lands AFTER apply_layout and re-reads to confirm (kept
  ordering law). Pinned in profiles_test (order via the recorded
  call list; the fresh-rows lesson: the fake driver keeps the last
  scenario's memory). (e7616d9)
- DESKTOP COLOR: gaming_watch._enforce_desktop's color sibling -
  outside games, a configured panel wears its hdr state, one
  command per disagreement; vrr panels NOT exempt (rate and color
  are different questions). (e7616d9)
- UI, both homes per the owner's words: the profiles row grew the
  trinary selector between rate and remove (precise-capable only -
  ABSENT, never gray-lied), the gaming card the same on the
  desktop-rate row. (e7616d9)
- RELEASE-NOTE SENTENCE (first-time reader): if you set a monitor's
  auto-switch to "video", the app watches the GPU's video decoders
  (Task Manager's own counters) and turns that monitor's HDR on
  when something starts playing, turning it off again about thirty
  seconds after playback stops; if you set it to "player", HDR
  comes on only when an mpv (started with its pipe enabled)
  reports that the playing video itself is HDR (BT.2020 colour
  with PQ or HLG transfer). A plain SDR game cannot false-trip
  the video tier while HDR is off, because Windows' Auto HDR only
  engages on a monitor that is already HDR-on - the light must be
  on before the effect can run, so the watcher turns it on and
  Auto HDR follows on top; and games render through 3D engines,
  which the decoder-only watch deliberately does not count anyway.
- TESTS: scripts/hdrwatch_test.py (43 offline pins: path strings,
  the matcher's exclusions, the mpv truth table, fake-clocked
  hysteresis incl. the flinch case, the arm over faked senses, the
  type-16 canary constant+call-site); config_norm 3c rows; the
  profiles_test weave. scripts/hdr_live_probe.py is COMMITTED as
  the by-hand live tool and deliberately NOT in run_all (it
  flickers the owner's desk; the gauntlet never does).
- FOLLOW-UPS (none owed): MPC-HC's command channel is the named
  second player tier (probe shape differs); the mpv tier assumes
  one pipe per desk (multiple players = first answerer wins);
  hdr_sync repaints the profiles pane only - the gaming card
  refreshes when its tab next paints (a full-tab rebuild for an
  out-of-view card was not worth the repaint cost); a video tier
  can be tripped by any decoder user (a browser playing a 4K AV1
  trailer lights the panel too - honest reading of "something is
  playing", the owner can move that monitor to the player tier).

## DEFAULT-OFF LAW - FINISHED (wave B, Oct 13, the owner's virgin-launch screenshot)
The screenshot said the general/power tabs lit features by default on a TRUE
virgin boot. Every defect closed, measured, and pinned:
- POWER STOCK DARK: hold_display/hold_sleep (the card's pair) flipped True ->
  False; skip_camera_when_blocked flipped with them (a self-running powercfg
  poll - enabler by the law's own definition); restore_windows and the
  fullscreen guard flipped (they move windows / withhold the broadcast -
  behaviors to be wanted). wake_policy judged: the law wins the enum call -
  re_off is the auto re-off FEATURE in a knob's clothes, stock is leave_on
  (a virgin box must not re-off what the user never asked it to manage).
  ui.enabled stays TRUE (named judgment): the settings window is the opt-in
  ceremony itself, not a background feature.
- ADOPTION OBEYS THE FLAG (_power.py): the boot's truth thread met a stray
  task (pre-wipe life) and re-wrote assistant_task=True behind the owner's
  OFF switch - the consent breach the log confessed ("switch says False,
  store says True" -> "flag written to disk: True"). Adoption is now
  one-directional: a gone task un-lights a lying switch (honest), a present
  task NEVER lights an off flag - "assistant off: adoption silent" logs it
  and the task rides inert (requests(assistant=False) never consults it;
  the switch's own click path owns it from there). A state-side belt in
  _events.py refuses an unsubstantiated True at the last gate before disk.
- RUN KEY AUDIT (defect 4): no boot path REGISTERS on a fresh profile.
  migrate_once re-points only an EXISTING legacy value (measured: the
  "ICU Presence Detector" value is gone - the re-point already spent its
  one-shot); startup.selfheal re-stamps only an entry that exists and
  differs from ours by exactly the missing --autostart flag. The stale
  PanelBoss value on this box predates the wipe and the UI reflected it
  honestly. Deleted as delivery (reg delete HKCU Run /v PanelBoss /f);
  the opt-in switch re-creates it instantly when the owner ticks the box.
- RELEASE-BOUNDARY MIGRATION (the credited catch): the packet's
  enabled-absent gate would have missed the ONE file this migration
  exists for - the violation boot's stock write lands camera.enabled =
  false PRESENT (write_config writes the whole merged cfg). Widened per
  ruling: consent silent (absent OR explicitly false) AND the key sitting
  at its OLD stock value -> reset to new stock, every line named in the
  log. One-shot BY CONSTRUCTION: the new [meta] defaults=2 stamp rides the
  stock table and lands with the first save, after which the shape is
  unreachable and the owner's own re-toggles (which re-create the value
  shape but not the absent stamp) stand forever. assistant_task is on the
  reset list from the other direction: its stock was already False, so a
  true on a never-consented file can only be the adoption's artifact.
- TRUTH ROWS MOVED WHERE THE LAW MOVED: config_norm (stock-shaped power),
  camdiag section 8 (written-false consent resets; typed values and
  re-armed gaming stand; the stamp disarms), virgin_boot (dark stock, the
  stamp, the stranger's power flags stripped WITH every reset naming its
  line), power_assistant (silent adoption + the belt's rumor refusal + the
  switch round trips from dark), hold (fossil fixtures stamped - the test
  pins the fossil, not the boundary), layout (restore's promise inverted).
RESIDUAL (honest): the owner's on-disk file still carries the old trues -
the reset fires in memory at the app's NEXT load (no kill/relaunch was in
this wave's mandate), and the PanelBoss-PowerRequests scheduled task is
left installed-but-inert (removing it costs a UAC prompt; the switch's
off-path deletes it whenever the owner next visits the card). README still
says "default on" in two places and calls re_off the default - docs lane,
follow-up.
