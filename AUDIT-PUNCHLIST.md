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

## PROBE LAW (owner correction, Oct 14): contaminated verdicts are worse
## than no verdict
A scratch-process probe sharing a flaky bus (or mutex, or handle table)
with the LIVE APP measures the COEXISTENCE, not the hardware. Evidence
today: one-shot DDC/CI writes from probe processes "proved" the AOC's
DDC dead and its power opcode firmware-refused - the same panel dims
and restores through the app's own in-process retrying door (owner's
eyes). Standing rules: (1) hardware capability verdicts are admissible
ONLY from the shipping code path with its full retry budget; (2) an
unanswered write after retries = UNVERIFIED-TRUST (reply-deaf panels
are a documented class), never "refused"; (3) "refused" is only ever a
fact about THIS app's attempts, timestamped - not the firmware's soul;
(4) probes that must run against a live app's hardware say so in their
own output and their conclusions are labeled PROVISIONAL.

## AOC PANEL DOSSIER (Oct 14, evening - supersedes all earlier AOC verdicts)
THE PANEL LIVES BEHIND A KVM (owner fact). Everything today's probes saw
- selective reply-deafness, transient 0xC026258B checksum corruption,
the panel "vanishing from the desktop" mid-probe, EDID claims that the
channel cannot deliver - is consistent with DDC lines through a switch
whose EDID/DDC pass-through is partial. Capability claims about this
panel are ONLY valid with the KVM parked on this PC; the owner's UAT
must state the KVM position, or the row label reads "via KVM, partial
pass-through assumed".
EXPERIMENTS RUN (elevated, twice + watched retest):
- MONITOR DEVNODE DISABLE (pnputil /disable-device UID295169): kernel
  says disabled (status=Error), CCD desk unchanged, PANEL UNCHANGED per
  owner's eyes both runs. VERDICT: mark-only on this stack. The devnode
  rung is DEAD for per-monitor off here (literature camp: contested ->
  settled-skeptical on NVIDIA WDDM 3.2 + KVM).
- OPEN RUNGS: (a) DDC/CI VCP 0xD6 - already in flight in the off-submode
  wave, now with the KVM footnote; (b) SetDisplayConfig PATH-SET minus
  the AOC path (no elevation, prior art: SO 57136638 / MartinGC94
  Disable-Display / OSR thread; counterweight: 24H2 regression reports
  - test IN-APP before believing either), the suspected mechanism of
  Settings' Disconnect; (c) if (b) works: topology churn is the price -
  Win11's remember-window-positions is the safety net to verify (the
  survey's observable O3).
- SECURITY EVENTS 6419/6420 did not fire this session (event filter
  found 6416-6420 range only if auditing enabled - uninformative run,
  re-check with auditing if the elevation matrix ever matters).
LADDER (owner's design, current truth): blackout (every panel, owned) ->
dim 0..N via app door (works on the AOC despite the deaf reply channel)
-> off via 0xD6 with retries (UNKNOWN through KVM, in flight) -> off via
path-set (EXPERIMENTAL rung, no-UAC, pending first test) -> the physical
button, undefeated.

DOSSIER UPDATE (Oct 14 pm, off-wave probe - scripts/sdc_off_probe.py,
every rc recorded in its output):
- IDENTITY (owner's word is the only court): the CONTROL panel is the
  IOC912B row on \.\DISPLAY2, DIRECTLY attached (its friendly name
  GA27W1Q is a marketing-string artifact - the profiles doctrine
  applies; the probe joins by gdi SOURCE PATH, never by name). The
  AW2725Q/DEL-stamped row is out of today's record (stamp and name
  disagree). The KVM belongs to the AOC2790 / U2790B on \.\DISPLAY1.
- OFF RUNG WITNESSED (owner's eyes): the IOC "blinked dark" under the
  D6=4 burst (4/5 ACK, one transient 0xC0262582 - the retry law
  measured live) and returned under D6=1 (3/3). The rung is REAL on a
  directly attached panel; the morning's probe-era NO verdict dies
  here - retry discipline was the missing feature, not the wire.
- THE POWER REGISTER LIES: the D6 read answered val=1 (on) through
  the entire dark window (and a clean single write + 1/2/3 s re-reads
  hold 1). The register does not track DPMS state, so the app can
  NEVER verify off from it - "off (unverified)" is the machine-side
  honest word by law, and the preview is the human judge. (Also:
  NULL pVCPFeature answers 0x57 from this OS - part of the morning's
  "reads are deaf" was argument shape, not the panel.)
- RUNG (b) SetDisplayConfig path-set: DEAD AT ENTRY on 26220/NVIDIA.
  Read leg lives (GBS(2)/Query decode 3 paths/6 modes clean; flags
  0x1 and 0x0 answer 0x57 - my first pass's "24H2 regression at the
  READ" was my own wrong flag, corrected in-record), but SetDisplay-
  Config answers 0x57 for EVERY shape: retracted apply, as-is apply,
  VALIDATE|USE_SUPPLIED both ways, even no-array TOPO_MIN/TOPO_ACTIVE.
  The prior-art calls do not survive this stack; closed with evidence.
- AOC D6 rerun under the full retry law, this session: INCONCLUSIVE
  from the scratch process - 20/20 calls gle 0xC0262582, the
  brightness read included, the same door the owner's eyes proved
  alive hours earlier. The probe cannot address this bus beside the
  live app (PROBE LAW rule 1); tonight's UAT - app Preview button,
  off row, KVM parked on this PC - is the instrument.
- LADDER (current truth): blackout (every panel, owned) -> dim via
  app door (proven on the AOC) -> off via 0xD6 WITNESSED on the
  direct panel, register cannot verify, AOC verdict pending the
  app-door UAT -> [devnode: mark-only, twice-witnessed; SDC path-set:
  dead-at-entry - both CLOSED] -> the physical button, undefeated.

DOSSIER UPDATE (Oct 14 night, SDC RUNG (b) RE-TRIAL - the sibling
scripts/sdc_off_probe2.py; every rc/gle/desk-row in its output; the
pm block's "dead at entry" is SUPERSEDED by this one):
- THE DEATH WAS SELF-INFLICTED (MARSHAL-BUG, corrected in dossier
  style): sdc_off_probe.py:52-53 defined SDC_APPLY=0x1 and
  SDC_USE_SUPPLIED=0x2, but those bits are SDC_TOPOLOGY_INTERNAL and
  SDC_TOPOLOGY_CLONE (winuser.h: SDC_APPLY=0x80,
  SDC_USE_SUPPLIED_DISPLAY_CONFIG=0x20). The pm run's flag-argument
  0x3 was therefore a topology ask with NO verb - the illegal-
  combination class that answers 0x57 at entry, driver untouched.
  The pm probe's own GBS(2)/Query(2) leg (3 paths/6 modes) proves
  the structs were innocent all along: the 72/64 layouts were
  right, the verb constants were not. A contaminated-by-illegal-
  shape verdict - rung (b) was EXECUTED-TO-FALSITY, not
  dead-on-merit; the probe law turned fully around and bit its own
  authors' first experiment.
- MEASURED SHAPES (26220/NVIDIA, app live, rc/gle every line):
  AS-IS active (0x80|0x20) rc=0x0 gle=0 - the must-return-0 gate,
  rung credibility RESURRECTED; SANITY SDC_APPLY|SDC_TOPOLOGY_EXTEND
  (NULL arrays, SO 57136638 shape) rc=0x0 - the family verbs answer
  0, no split verdict; the pm's "even no-array TOPO answers 0x57"
  was the same bug.
- SDC_ALLOW_PATH_ORDER_CHANGES (0x2000) is REJECTED 0x57 paired
  with USE_SUPPLIED on this stack, under VALIDATE and under APPLY
  (the lineage combo measured here, falsified as-is); the pairing
  the docs give it (TOPOLOGY_SUPPLIED) measured 0x57 too - and the
  glass-silent `check` mode re-confirmed both at VALIDATE with zero
  applies (sdc2-check.log). The retraction shape that WORKS:
  PATH-MINUS (drop the target's paths from the array, NOT merely
  zero its flags) with
  SDC_APPLY|SDC_USE_SUPPLIED|SDC_SAVE_TO_DATABASE|SDC_ALLOW_CHANGES
  = 0x6A0 - VALIDATE rc=0x0 then APPLY rc=0x0.
- THE pm's second self-inflicted error: ZERO-FLAGS retraction
  (the path kept in the set with flags=0) is ACCEPTED at every
  verb set tried (0xA0, 0x6A0) AND its VALIDATE answers 0x0 -
  validation checks set consistency, NOT which path survives - but
  it disconnects the WRONG panel: DELA283 left the desk and the
  retracted AOC survived, re-slotted to DISPLAY3, twice. The shape
  reads self-inconsistent to the CCD and it re-normalizes by its
  own taste; ALLOW_CHANGES did not save it. PATH-MINUS hit the
  right target.
- RETRACTION MEASURED, authoritative view: mid rows 2 at +0.5 s;
  EnumDisplayDevices showed a plausible-but-LYING
  ('AOC2790','\\.\\DISPLAY3') row, but the CCD's own QDC(2)
  mid-window view answers active = {IOC912B@DISPLAY2,
  DELA283@DISPLAY3} - THE AOC TARGET IS GONE FROM THE ACTIVE PATH
  SET and the surviving pair keeps its true slots; the GDI row is
  the KVM's emulated EDID ghosting a detached slot. The desk
  restored to the original 3 rows/slots (restore = saved arrays
  with the SAME verb set, 0x6A0, SAVE included, so the CCD store is
  written back to the current state, not left saying
  "disconnected"); post-restore CCD: all 3 active, verified True.
- PERSISTENCE (the second door's price, named): SAVE_TO_DATABASE
  writes the disconnect into the HKLM Connectivity store - it
  survives the process, and would survive a REBOOT with the AOC
  dark, if the restore did not carry SAVE (the named footgun).
  Tonight's state is answered WITHOUT another reboot or another
  twitch: the last store writer was the restore's own
  APPLY(full-set, SAVE) at rc=0x0 - the API's contract is that that
  write IS the stored profile, so the store reads connected now by
  attestation. What remains UNVERIFIED is blob-level (some other
  combo's row could have flipped): reg.exe /s on Connectivity
  answers Access-denied at medium integrity (the filtered token is
  Administrators-Deny-Only), and a /rl highest task CANNOT even be
  registered from medium (measured: schtasks create -> access
  denied). Elevation owed for one read; it is a witness, not the
  door itself.
- OWNER STROBE LAW (the complaint, earned): six ladder runs before
  the word arrived = ~30 applies on a live desk, six dark windows.
  The desk is the owner's. The tool now enforces it: VALIDATE gates
  every APPLY (a refused shape costs no glass; its rc is the whole
  evidence), proven shapes run their VALIDATE twin instead of
  re-applying (as-IS applied 0x0 four times, SANITY EXTEND three -
  retired to validate-only), ONE physical retraction cycle per
  session on the AOC, and `check` mode gives the validate-delta
  table with ZERO applies. Attribution for the record: the visible
  toggles were the six retraction windows (target dark + reflow)
  and the SANITY EXTEND applies (topology re-asserts DO flicker);
  the as-IS round-trips on this stack were reported neither way -
  if the owner saw strobing NOT in 6-7 s blocks, the NVIDIA CCD's
  as-is no-op re-validation is the suspect and SDC_NO_OPTIMIZATION
  is its cure, one flag, next touch.
- OWNER EVIDENCE (same day, quoted): Settings' Disconnect on the
  AOC (KVM panel) DOES black the panel - "it doesn't care what's
  downstream of the adapter" - Windows stops driving the output and
  the panel falls to standby on signal loss; and Windows refuses to
  disconnect the LAST active display, so single-screen desks are
  OS-guarded (the app inherits that as the tested refuse->blackout
  path, no new code).
- UAT (owner, same day, quoted): off WITNESSED on both OLEDs via
  the shipping path - admissible; AOC stays lit - firmware-
  attributed since brightness proved the same bus alive.
- VERDICT CLASS: RESURRECTED at the code level (the retraction
  applied clean and the AOC's path is gone from the active CCD
  set); whether the physical panel blinked dark is EYE evidence -
  the mid-window GDI ghost makes row data unable to tell
  dark-but-asserted from lit, so the owner's answer to "did the
  AOC go dark for the 6 s window?" is the missing half. If eyes
  say dark: rung (b) is the off rung's second door, and the good
  one - no firmware cooperation, no elevation, KVM-indifferent (it
  stops the signal at the adapter), persistent by design.
- LADDER (current truth, supersedes the pm line): blackout (all
  panels, owned) -> dim via app door (proven on the AOC) -> off
  via the shipping path WITNESSED on both OLEDs, register cannot
  verify -> off via SDC path-set REOPENED (retraction measured
  clean; AOC-dark pending eyes; elevation owed only for the
  store-blob diff, not the door) -> [devnode: mark-only,
  twice-witnessed; CLOSED] -> the physical button, undefeated.

## Wave E1 (cadence law, SHIP @ 8d30a6c) - gate ledger lines
- OWNER DESK RESIDUE: the violation-era boot wrote stock always_fallback
  _poll_sec=10 into the live toml BEFORE the law existed; the wave-B
  resetter predates these keys, so the dark gate reads 10 s on this
  box until the key is deleted (or hand-set to 1) at next app quit.
  Card label must not promise 1 s to a desk running 10.
- CEILING QUESTION for the owner: law shipped as the FLOOR reading
  (degraded dark eye = 1 s); the FRESH always-on dark eye reads ~5 Hz
  by the loop's nature (that's what a held stream is for; capping =
  one re-arm line in _off_phase, costs ~5x wake latency). Say the
  word if "once per second" was meant as a ceiling too.
- LABEL HONESTY WORSE-SIBLING: _constants.py:15 timers card still
  says "poll while off" for off_poll_sec - the README's just-corrected
  lie lives on the more-read surface. Relabel "first dark re-poll"
  (folded into E2's audit batch).
- E2 RELAY (durable home, unwrapped): "always-on: read once per second
  while the screens are off (the stream stays open; 1 s is the point)"
  - source from THIS block, not the git-message wrap.
- STALE-VALUE CLASS (gate note): a value-gated boundary (_meta < 3 +
  old-stock match) is the structural fix if the "young era" ruling
  ever hardens - wave-B's stamp disarms before camera keys exist.

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

## Lane E1 ledger lines (the always-on law, Oct 13 night)
- always_fallback_poll_sec: default 10 -> 1, floor 5 -> 1 (owner law:
  the paid-open stream earns one-second reads, not ten-second
  glances; the old floor rationale marked superseded at the site).
- The degraded gate was ONE constant shared by both display tables;
  split honestly per the packet: always_fallback_poll_sec is now the
  DARK gate, always_fallback_poll_on_sec (default 10, floor 5) the
  LIT one. _policy._policy names both at the branch.
- MEASURED TRUTH (the owner's question): with a FRESH always_on eye
  and screens off there was no cadence at all - _off_phase never
  re-arms next_poll (_phase.py:113-122, the abstain arm says "the
  off phase re-polls every tick"), off_poll_sec (3) only arms the
  FIRST re-poll (_power.py:138, _events.py:66), and the run loop
  ticks every 0.2 s (_boot.py:121). The README promised "polled
  every off_poll_sec" - corrected, with the fresh/degraded split
  spelled out. The card's "3 s" is the LIT phase's on_poll_sec.
- E2 HANDOFF (the exact card sentence, verbatim):
  "always-on: read once per second while the screens are off (the
  stream stays open; 1 s is the point)"
- No migration: the default flips and stock files pick it up
  (owner's call; the default-off era is young); config_writer_test
  round-trips an explicit 10 unchanged (floor 1 permits it).

## Wave D ledger lines (fence closes around the IR call, Oct 13 night)
Wave-C dispositions first, as ordered:
- find_camera privacy-lie: **FIXED** (wave D) - stall raises "no
  camera opened; check privacy settings - or the door never answered
  its budget (see the warnings above)".
- _probe load-probe exemption: **LEFT** - it is the get_config leg,
  named already in the exemption comment; the boot-hang exposure
  stays LOW (opt-in name_contains only).
- camera.py +40 growth rule: **PAID BY SPLIT** - the join machinery
  and all three budgets moved to watchdog.py (the seam the gate
  named did not apply to a bounds-only fix, so the growth itself
  became the module).
- Enum watchdog live-proof: **RE-MEASURED PENDING** - wave D's live
  expectation is the ENUMERATING veil counting seconds + naming
  resolved indexes on this exact desk (the 19:33 shape now has two
  more fences: IR joined, empty board speaks).
New findings this wave (found by the own pins, not by the owner):
- IDENTITY_MAP 3-TUPLE CRASH (MED, fixed in-wave): identity_map read
  entry[3] unguarded while enumerate's contract row is a 3-tuple -
  the setup's gather thread died at rows_from BEFORE the board post
  on every real desk (the suite fakes hid it with 4-tuples). Guarded
  with the same len-check rows_from uses; the wave-D arm-at-start pin
  is what caught it (fake returned the CONTRACT row shape).
- NEW LAW (owner): the empty board speaks - zero cards drawn means
  the veil reads "no cameras answered" + the camera logger's first
  warning (fallback bare line); the ear is a per-dialog handler,
  removed on close.
- The pre-board veil counts ELAPSED SECONDS (alive-and-counting is
  honest pre-count); enumerate beats name the last resolved index.
- Dialog deadline arms at GATHER START with the enumerate-phase
  arithmetic (gather_budget: 8 indexes x probe budget + IR + margin);
  the at-return re-arm can only SHORTEN (min).
- Deferred releases drain through the join now: a wedged MF teardown
  is a logged abstain (zombie keeps that cap), never a silent death
  of the draining thread holding the whole tree.

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

## TASKBAR DOSSIER (Oct 14, late - for the OLED tab's leg one)
ABM_SETSTATE RETRIAL, CLEAN CONDITIONS (owner closed their third-party
taskbar hider first; contention class cleared): rc=1 ACCEPTED, state
unmoved (GETSTATE stayed 1), StuckRects3 blob unmoved - the morning's
'silently ignored on 26220' survives retrial; it was never the hider
app's fault. But the desk arrived ALREADY auto-hidden with the hider
closed: that app persisted via the STORE (registry), and its effect
outlived its process - the registry route is empirically alive on this
build, proven by forensic residue, no experiment needed.
CAUTION FOR THE PACKET: the folklore 'byte 8' of the Settings blob
showed 0x02 while auto-hide was ON - the old forum values have drifted
across builds; leg one re-derives the offset/semantics from a
before/after diff, not from lore.
LEG-ONE FORK, pre-settled: (a) pen the store + Explorer re-read
(logon/restart to land - hostile UX for a tray toggle), or (b) FAUX
HIDE: the app paints its own edge strip over the taskbar, zero shared
state, vanishes with the process, cannot be broken by any other hider.
For a burn-in tab (purpose: keep pixels from sitting still) (b) is the
front-runner; the hider relocates to the OLED tab as faux-by-default,
with the store route behind a labeled 'make it permanent' affordance
if the owner ever wants it to survive logout. Coexist law either way:
conflict with foreign hider residue CONFESSES on the row, never
last-writer-wins in silence.
FAUX-HIDE BEHAVIOR SPEC (owner, Oct 14 late): strip covers taskbar
edge. Mouse enters taskbar zone -> withdraw. Mouse out of zone for N
user-settled seconds -> return (slider, timer-card idiom, default off
law). EXCEPTION: while a live caret (GetGuitThreadInfo hcaret of the
foreground thread, rect screen-mapped) sits inside the taskbar bounds,
return is HELD - the case the owner named is typing in the search
widget; when the caret dies, the N-second timer restarts normally.
Caret poll rides the strip's existing timer (one call per tick). No
focus-stealing, no click tracking: the strip notices the caret, not
the keyboard.
OFFDISC FOLLOW-UPS \(gate OBS-1/2\) - BOTH CLOSED at 75b1141:
(1) commit prose overclaims 'disagreement LOUD at the belt' - the belt
passes gdi="" so the cross-check cannot disagree there; branch is
harmless defensive, correct the comment or drop the branch.
(2) restore()'s _victim_active is ONE-SHOT while _gone earned 4x0.3s
patience (CCD moves inside a tick, measured) - a 300ms-slow
reactivation would false-warn 'never came back'; give restore the
same VERIFY_TRIES.
FAUX-HIDE SCOPE (owner addendum): one strip per monitor taskbar
(Shell_TrayWnd + Shell_SecondaryTrayWnd rects from the app's own
monitor enumeration). REVEAL SCOPED CHOICE on the tab: 'hovered'
(default) = withdrawing only the strip whose zone the cursor entered;
'all' = entering any zone withdraws every strip (owner case: apps
live on their windows' monitor, hovering one bar wants all bars
visible). Caret-hold is GLOBAL (typing in any bar's search holds all
returns); return timers stay PER STRIP once the hold releases - peek
at everything, restore what is not being touched.
FAUX-HIDE PER-MONITOR ENABLE (owner addendum 2): the hider has a
per-monitor row switch (the away card's row pattern), default ALL off
(owner's rationale: burn-in is the OLED problem - the IPS bar never
needs hiding; even on OLEDs it is opt-in per the law). Only enabled
monitors get a strip painted at all; the reveal-scope choice and
return-timer seconds are GLOBAL (one behavior, per-monitor targets -
not a settings matrix).
PREVIEW-SEAM FIX (436ed4d/75b1141, gate SHIP) - two soft notes for
next touch, neither blocking: (1) the seam pin drives only the
REACHABLE menu shape - strengthen to superset-compare vs off_choice
on a plain fake (a 5th label added only to an unreachable branch
would slip and land as a preview-time KeyError, loud but UI-thread);
(2) restore patience = sleep-before-look, every restore now pays
>=0.3s (<=1.2s serial worst in the lift loop) - same tax _gone
already imposed since the wave, recorded so the number is known
when someone times a lift.
DOSSIER AMENDMENT (taskbar block - the leg-one build caught two of my
own errors, same day): (1) 'ABM_GETTASKBARPOS verb 0x05 rc 1 edge 3' -
that probe ran THROUGH ctypes' SHAppBarMessage, and the repo's own
measured law (docs/taskbar-findings.md, bisected Oct 2026) says the
export ACCESS-VIOLATES from this process family; the successful-looking
answer was luck on that call shape, and the profiles_ui chain watchdog
fired exactly as the AV class predicts once a NEW caller entered the
window-build path. The hider's eyes moved to GetWindowRect +
taskbar.flag_note() (StuckRects3 byte 8, read-only): zero shell API
calls, chain suite green in-sequence again. (2) 'byte 8 semantics
drifted' caution: RESOLVED - taskbar.py already documents them
(2=shown, 3=autohide); the morning's hex window was sliced at the
wrong offset, the folklore was mine, the codebase was right. Lesson
filed once more: bounded-recon packets must include the prior-art
search; the audit trail exists for a reason.

## VEIL / WINDOW-RAISE BUGS (owner UAT, Oct 15 morning - fix later,
## leg-two era; symptom-first, guesses last)
1. The open-from-tray veil works ONLY for the window's first show of
   the session; after a close, the next tray-open draws the full UI on
   screen (no veil cover during the draw) - so the veil is riding
   first-show state somewhere instead of every-show.
2. When the settings window is ALREADY open, a fresh tray-open re-draws
   widgets instead of raising the existing window to focus - and
   BUTTONS redraw visibly the most (the kofi/chip/tabs bar family).
   Suspect seams to read first: _shell.py _show_first's already-mapped
   branch (does it early-return after focus, or fall through to a
   rebuild?), and any _repaint_switches/_draw storm the raise path
   triggers; the poke handoff (_drain_poke) rides the same
   _show_first(manual=True) and may inherit both.
Repro recipe: open window, close it (X), reopen from tray -> observe
no-veil draw; with window open, poke again -> observe full redraw.

## DIMMER WAVE (owner rulings, Oct 15 - packet law for the dispatch)
Stage A: per-monitor background-window dimming - idle-triggered dark
click-through overlays over every non-foreground, non-excluded, non-
audio-active window (WASAPI sensor per the Oct-14 probe: GetState slot
3, GetProcessId slot 14, MTA, >=4 s settle hysteresis); include/
exclude list edited IN the oled tab (one flow); foreground and any
sound-making window un-dim INSTANTLY on touch; ramp + level sliders.
HOTKEY LAW (owner): unbound by DEFAULT - no stolen chord before
consent; assignment lives in the card (press-to-bind affordance), the
binding word is stored, RegisterHotKey exclusivity failure answers
with the dated word (probe: exclusivity incl. Win-combos verified on
this build), and the card shows bound/unbound state honestly. Toggle
semantics (one press pauses, one resumes), not hold.
Stage B (later wave): optimistic around-content dim - DDA motion eye
(ACCESS_LOST re-Duplicate law, PrintWindow PW_RENDERFULLCONTENT
fallback - both measured) dims the window AROUND the detected motion
rect; wrong guesses die on the hotkey or any input.

## MSI WAVE REQUIREMENTS (owner addenda, Oct 15 - the fresh-install
## trial is the RELEASE gate, nothing ships until it passes)
1. Per-user install, no elevation ambush (tray app; the app's own
   task/consent model assumes a normal user).
2. START MENU ITEM (owner aside, Oct 15): a proper app entry (name +
   icon, launches the GUI; the Run-key autostart stays as the app's
   own opt-in - the Start Menu entry is the discoverability half).
3. Uninstall MUST clean: the power-assistant scheduled task, the Run
   key entry, and the CCD stored-disconnect state the boot belt can
   no longer reclaim once the belt is gone (restore-before-kill or
   at minimum a loud dialog naming the disconnected display).
4. The camera/onnx/model/customtkinter data files ride inside the
   package (PyInstaller/Nuitka class problem; measure the bundle).
5. Virgin trial on a fresh Windows user: consent screen -> camera
   consent -> away cards -> hider -> refresh -> dimmer, then
   uninstall and a residue sweep (registry, tasks, AppData).
6. The veil redraw bugs (logged above) close BEFORE the trial; the
   first impression is the trial.

## SILENT APP DEATH (owner UAT, Oct 15 ~11:00 - the hider's 'didn't
## work' was a corpse, not a bug: config persisted, fresh boot applied
## it in one tick - the feature is exonerated by its own wake-up)
EVIDENCE: instance booted 10:56:28 ('tray icon ready', window mapped);
last log line 10:56:39; the next launch at 11:07:06 logged 'instance
guard: WON' (a survivor would have made it a loser with the balloon
line). Fourteen minutes of silence, no Traceback, no 'settings window
died' (epitaph-before-burial ships since 02:00), no quit arm, no hard
kill - pythonw left without a word. Owner-visible symptom chain: tray
icon gone, hider (left ON in config) inactive, everything resurrected
by the next launch.
SUSPECTS (next occurrence must name itself): (a) ui.run() returned -
mainloop ended without the tray's quit arm - and the process exit was
therefore main-thread-normal with only daemons left (silent by
construction); (b) an os._exit path without a marker; (c) console-host
teardown. BELT TO SHIP WITH THE NEXT TOUCH: cli._drive logs the
return of ui.run ('window closed - tray follows' vs 'quitting'), and
_run's tail logs EVERY exit path with its reason - a silent departure
becomes a signed one. Grep for the belt lines names which door the
corpse left by.

## WASH CRASH (owner UAT, Oct 15 11:09) - and the silent-death belt
## answer: the 10:56 corpse was THIS class, caught red-handed the
## first time the exception happened to land in the LOGGED path.
Chain: run wash -> jog painter builds a CTkToplevel -> customtkinter
registers it in the GLOBAL scaling tracker -> tracker's after() fires
on the MAIN thread -> winfo_exists crosses into the jog thread's
interpreter -> RuntimeError in callback -> tkinter's default reporter
PRINTS to stderr -> pythonw's stderr raises OSError(22) -> escapes
through Tk mainloop -> whole app dies. Fix: the veil is plain
tk.Toplevel now (flat color, zero CTk); law recorded: WORKER-THREAD
INTERPRETERS RUN PLAIN TK ONLY. Open question: whether the hider
painter and the blackout overlay share the exposure (both are plain
tk today - safe by idiom, not by policy; a future CTk anywhere on a
worker thread resurrects it). The wash-adjacent app death is now
EXPLAINED; the 10:56 silent death stays unproven but is the prime
same-class suspect (it sat two minutes after a wash-era boot).

## DIMMER OWNER-UAT RULINGS (Oct 15, wave c157f86 - V PASS, gate pending)
- Wallpaper dim was REAL: Progman/WorkerW passed the census and got
  veils; the desktop is now excluded at the CENSUS stratum (a fact
  about the desk, not config). The "random darker box near the focused
  window" was a dead app's veil: the paint raised inside the pump after
  the hwnd died, stranding an immortal unclick-through window - same
  pump-death class the jog veil showed at 11:20. One bad item can no
  longer take the dimmer pump either.
- Owner law, recorded: default dim LEVEL is 20 (45 was aggressive on
  OLED); the fade rail must reach 0 (the clamp's max(3,..) was lying);
  per-monitor ALWAYS ON mode = the autohide shape (dim that panel while
  focus sits elsewhere; exemptions and the hotkey pause still rule).
- Hotkey honesty law: "taken" may ONLY be said on Windows error 1409.
  Every other failure names its code. A word that blames "another app"
  for our own errno is the DISPATCH PURITY disease wearing a UI label.
  Owed from the next real press: the hex line (mods/vk/hwnd/errno) -
  the owner's original Ctrl+Alt+D "taken" may have been a false
  accusation; if so the rebind simply works.
- Overlap law (deliberate boundary, not an oversight): suppression is
  containment-at-birth only; partial overlaps still stack their alpha,
  and an overlapping veil that later dies can strand its suppressed
  window undimmed until the next move. General rect subtraction stays
  a rewrite nobody asked for.

## THE SUITE-REWRITE LESSON (Oct 15, mine, recorded against repetition)
Gate finding 2 (the test helper's level default hid the shipped
default) was a ONE-LINE ask and I spent six commands on it: a regex
`cfg\(([^()]*)\)` ate the helper's own signature (the inserted
`level=20` became a named parameter and the kw-based body went blind),
nested-brace kwargs hid from `[^()]*`, the repair scratch ran with the
wrong cwd, and half the call sites rode `level=` spellings I had not
audited first. For a mechanical sweep across a whole file the verbs
are the balanced-paren scan, THEN an explicit audit of what got
rewritten, THEN a run - not a regex on a guess. (The sweep's real
product was smaller than the doctrine implied: rename the helper, or
keep its default and pin the shipped one bare-dict once - one line,
as the gate said.)

## GATE-FINDING REPAIR, MINE (Oct 15, same session)
Two of the gate's four findings were one-liners; I took them inline and
the honest note is the cost: finding 2 ("the suite helper's level=45
default hides the shipped 20") took SIX commands. A one-line regex on
`cfg(...)` ate its own definition, the nested-brace kwargs were invisible
to `[^()]*`, the fraction ladder I rewrote was the wrong ladder (30/20/10
by thirds, not 30/30/10), and one pin asserted the documented PARTIAL
gap as if it were containment. A whole-file mechanical sweep is exactly
the shape typist-quick exists for - the architect's keyboard is for the
surgical single patch, which the ledger seam below is.

## FLAKY SUITE, CAUGHT IN THE ACT (Oct 15 12:30)
The gauntlet at tip 590441c answered `FAILED: at least one suite rc=1`
and named `hdrwake_test.py rc=1` - the same file printed `HDR WAKE PIN
OK` on my manual run seconds before, and three consecutive manual runs
afterward all exit 0. First recorded flake on this suite; the dimmer
wave touches none of its path (hdr wake pump, no veil code), so the
correlation is with load, not the diff. Owed: give the suite a bounded
retry (a real pump walk needs its window) or pin WHY it can miss once.
Until then the gauntlet's one-word verdicts must be read, never
inferred - the log named the file, so I went and looked.

## VEIL BUG 2, THE HONEST SPLIT (Oct 15)
Bug 1 (veil rode first-show state) is FIXED: _show_first now veils
every UNMAPPED manual open and leaves the already-mapped raise plain.
Bug 2 (the already-mapped raise redraws the button family) is NOT in
the map branch - that branch is three lines (deiconify/lift) and the
commit above proves it. The redraw rides the after(0,
_repaint_switches) every map schedules: it re-selects every switch
through CTk's own _draw, so the switches flash on the raise. It is
load-bearing for a window that was BUILT hidden (its knobs drew at
zero geometry) and pure waste for one already mapped. The fix is to
fire the resync only on the map that actually needed it, and that
touches the ordering the geometry probe pins - so it ships with the
next touch, not as a drive-by. Recorded here so the dossier does not
read as one bug half-fixed twice.

## HDRWAKE: THE LABEL WAS THE BUG (Oct 15, second pass)
The qa lane named the cause as a late counter read; my snapshot patch fixed
that and the suite STILL failed - two ways in five runs: rc=3 (its own 60 s
hard-kill) and rc=1 (the marker assert). Both trace to the same shape, and
neither is the app: the fake driver derives its desk marker from the LIVE
counter (`_live_modes`, hdrwake_test.py:57), so a walk's answer depends on
when its own thread happens to append, and the third walk the pump window
permits paints a marker the test's arithmetic never reserved. The rc=3 run
spent 60 s inside `pump(8.0)` with an 8-second wall and 1.5 s driver sleeps
that need several drains to deliver - the fuse is cut close to the work.
And `check()` swallows its own cause into a label:
`HDR WAKE PIN FAILED in ['check']` when the traceback was already in the
stream; the label was blind by construction, which is why a FLAKE was the
first story we told.
Fix in this commit: the driver's marker is chosen by the CALLER's snapshot
(the desk is described at spawn time, so no thread-timing can move it), the
expected payload is derived from the spawn-time list, and the hard-kill
moves to 90 s so a slow drain cannot be read as a stuck pump. The law this
records: in a suite with live background threads, every expected value must
be frozen at spawn time - a number read from a moving counter is not an
expectation, it is a race with a label.

## VEIL BUG 2 CLOSED, AND THE PIN THAT BLOCKED IT (Oct 15)
The raise-resync packet was going out to a coder lane when veil_test
went red inside the gauntlet: 'later opens stay pixel-instant', an Oct-12
pin. It stopped the dispatch - the right call - because it is not a
regression report, it is a LAW CONFLICT, and the two laws had been
silently incompatible since the Oct-15 fix:
  Oct-12 law: only the first manual open is veiled; later opens are
              pixel-instant (DWM holds the surface).
  Oct-15 UAT: after a close, the next open drew the whole UI uncovered.
Resolution, MEASURED at the pin rather than argued: Tk's withdraw is a
real destroy (state() -> "withdrawn") but the HWND NUMBER IS REUSED on
the next map, so winfo_id() proves nothing either way - which is
exactly how the old law survived an afternoon of being wrong. The
surface does not survive; the number does. A withdrawn window's next
map is a fresh composite and rides the cover; the ONLY pixel-instant
path left is the already-mapped raise, and that raise now skips the
knob resync too - the owner's button-redraw on tray-open. (The resync
still fires behind a freshly armed veil: free under a cover, and
hide/show geometry is precisely where the doubt lives.)
Packet PACKET-RAISE-RESYNC.md died unsent: the seam it dictated turned
out to be the conflict itself, and adjudicating a law conflict is not
typist-class work.

## HOTKEY WAVE, CLOSED (Oct 15) - the audit trail in three lines
- The layering wave (423c9e0/2854492/cb71cbc) carries NO formal gate
  verdict: the reviewer died twice on the thinking-partial trap (the
  Oct-13 class, documented in AGENTS.md, now owner-verified twice on
  the gate's own channel). Treatment stands on its receipts: root cause
  measured (1408 two-thread probe), fix verified live on the owner's
  desk, dimmer 40 + full gauntlet green, and the lane's pixel probe
  caught the debugger's NEXT-vs-PREV error and corrected it in-commit.
  A future gate death class is a channel-sizing fix on the def, not a
  re-roll.
- Gate on the 916d5ea fixup: SHIP. Its one finding, for the record:
  display.py:493 re-initializes _hotkey_req at pump-run time, between
  the hwnd door opening (:459) and the loop; a note posted by the
  monitor thread inside that sliver is wiped and its caller waits the
  5 s bound for (False, 0). Low, bounded, and the SAME shape as
  _ear_req at :492 - a house pattern, not a new disease. Belt when the
  pump gets next touched: assign the run-time birth only when the
  field is None.
- V was dispatched against the wave and died reporting the dimmer
  suite only - awaymode (the suite that actually caught the field
  miss) was never re-run in its session. The architect's own gauntlet
  (rc=0, ALL GREEN, tip 916d5ea, 14:37) covers the gap; the receipt is
  that log, and V's independent re-run stays cheap belt work for the
  MSI wave rather than owed here.

## CONFIG LOSS, MY FAULT, RECORDED PLAIN (Oct 15 ~14:16)
The owner's settings went stock-default because an AGENT edited the
LIVE config file with a one-off regex script while the app was up.
Chain: my script's line-matcher wrote a second `bound` into [dimmer]
(plus clobbering the section layout), the TOML parse refused the
duplicate, the loader's honest recovery quarantined the file and
booted dark-by-law defaults, and the first autosave rewrote the file
from the rebuilt in-memory dict. The corrupt copy survived but carried
only the section my regex had mangled readable - the rest of the
owner's file was gone under the rewrite. The rebuild path itself is
EXONERATED by its own law (loud stop: dated quarantine, log lines,
defaults, no crash-loop); the mistake was mine, twice over: no backup
before scripted surgery, and scripting surgery at all when the UI
owns the file while running. A hand-edit with a typo gets the same
lesson by the loader's own comment - this is that class, agent-sized.
Belts shipped this wave: the quarantine now ALSO leaves a readable
dated .bak copy beside the .corrupt-<epoch> file (2 KB, human
timestamp, restorable by name), and scripts/backup_config.py is the
standing agent-side rule: back up first, edit through the running
app's UI or a restart, never a regex against a live file.

## GAME DVR CARD, BURIED (Oct 15 UAT, owner order)
Killed by owner order: "Game dvr overlay enabled or not still lies and
does not tell the current state or enable/disable. let's kill this
section honestly it's not worth the hassle." The card's state line
could not promise an honest read (a Settings page may rewrite the
values at any time, and the live answer needed the registry
archaeology we were not going to fund), so the card died rather than
kept lying: the section, its switch bookkeeping, its TIPS entry, its
registry-truth repaint row, and the suite's three pins retired with
it. ENGINE SIDE SURVIVES WHOLE: panelboss.tweaks, its registry values,
and tweaks_test's apply/revert round-trip all stand - only the face
is gone. The power tab's column-two law stayed (re-anchored on the
gaming card, the column's remaining tenant).

## VIDEO-DIM RESEARCH: WHAT THE DEAD RESEARCHER LEFT VERIFIED
The deep-research dispatch died on the continuation trap (third death
of the day on that channel family); the mission's load-bearing links
were verified directly instead. Established from Chromium's own docs
(googlesource, retrieved Oct 15):
- Every WebContents (tab) IS a media session; the web platform's
  playbackState is an explicit enum (none|paused|playing), and the
  media session service exposes MediaControllerManager:
  CreateActiveMediaController follows the active session, and the
  exposed is_controllable boolean is documented for exactly the
  question "is there any current media playback" - the playing/
  paused/none transition is EVENT-driven (MediaSessionObserver), no
  sampling. Chromium has a documented Windows SMC design doc
  (content/browser/media/system_media_controls) - the web-video-to-
  SMTC bridge is by design, not folklore (owner screenshot: the
  autohide app's card shows Chrome as provider).
- Chrome's session GROUPING (all browser sessions share one group
  id; concurrent tabs behave as individual sessions) is documented -
  an allow-list by app instance id is needed so a Spotify session
  never arms the video-dim.
OPEN, still to settle before the feature spec:
- HOW the third-party overlay reads SMTC. A live probe found NO
  winrt/winsdk in the venv and NO SMTC code anywhere in PanelBoss's
  tree (the media card the owner pointed at is the owner's autohide
  app - a sibling process; my attribution of its card to PanelBoss
  was folklore, caught by the probe, recorded). Routes left: the
  WinRT projection via pywinrt (new venv dep, no admin), or COM
  direct through the Windows SDK metadata, or the fallback that
  needs no bridge at all: PDH GPU Engine counters split by
  engtype_video_decode per-pid (the owner's own
  h
</think>
 avenue; per-process GPU counters have a known driver-gap
  history - the research question stands), or DDA/WGC motion with
  the WASAPI audible AND-gate (the probe rig on this same desk is
  already measuring the eye's cost).

## INFERNIX (5090) OFFLINE - Oct 15 ~16:0x, owner's call: card took a
## dive mid-shift (owner: "the 5090 decided it had had enough").
EVIDENCE (this workstation is the GPU host): nvidia-smi lists the 5090
at P0/53C (idle-cold), infernix-serve.exe is NOT in the process list,
and :8082 answers SYN-but-nothing (21 s hangs, Test-NetConnection
False on 8082 while 8091 on the beastserv appliance answers True - the
appliance is healthy, the workstation-side engine is what fell).
DOORS IDE GRACEFULLY (the design working): the FC panelboss box stayed
up (health 200 whole time, eventLoop alive); fleet/q27 requests that
would have landed on Infernix now answer 200 in <1 s on the remaining
seats; the four lanes that died did so at START with 'no eligible
target in group q27' - honest refusals, no phantom answers, no
mid-answer corruption. The owner-visible lesson: seat loss = refusals
at dispatch time, which is the loud-stop degradation the design names.
REVIVAL (owner's call on when): re-launch F:\LLM\START-infernix-
27b-4seq.bat once the card is rested; typist-doctor holds the deeper
recipe for the 27B stack.

## VIDEOEYE PACKET (Oct 15, coder lane): three seams absent, the decode
delta measured, OPERA UNVERIFIED
The four-delta packet arrived with three of its targets missing from the
tip: panelboss/videoeye.py, scripts/install_companion.py,
scripts/videoeye_test.py, scripts/companion_test.py exist on NO ref -
worktree, every local branch, every tag, every sibling worktree, and
`git ls-remote` says origin/ui-1c-reskin IS a88491d (the dossier commit),
so the debugger lane's "companion installer + manifest fix" push never
reached this repository. Deltas 1/2/4 (opera in BROWSERS, re-arm
watchdog, the pin) have no seam to edit - the feature must be specced
whole, not patched blind. What IS here (wm/_videostats.py, the counter
vocabulary) made delta 3 (the ship evidence) fully runnable. Measured,
scratch rig, Get-Counter against the already-flagged chrome on :9333,
video dQw4w9WgXcQ (title + paused=false verify playback):
  rest:      196 engtype_VideoDecode instances, 0 nonzero, max 0.00%
  playback:  15 samples / 30 s, every sample answered by ONE pid:
             63744, range 0.33-0.54% (its two videodecode engines)
             - the gpu-process CHILD of main 61728; the main pid and
             the renderers read zero throughout (the child-pid fact,
             live, not folklore)
  tab closed: max back to 0.00%, 3 consecutive samples
THE UNCOMFORTABLE FINDING: the repo's own ctypes PDH route - the
video_probe.py plumbing AND the shipped _videostats.video_busy() it
shares its struct/query laws with - read rc=0xC0000BBD for EVERY
formatted counter, both documented format/struct pairings, at rest and
during verified playback, WHILE Get-Counter returned live values from
the same provider in the same session. On this box today the
production reader fail-opens to 0.0 while the OS has the data: the
counter gate can never arm via ctypes here. The route needs one probe
session (engine-localized machine handle? PdhCollectQueryDataWithTime
interval?) before hdrwatch or any video-dim trust it. Recorded per
README's own Oct-10 law ("dead provider masked by silent zeros").
OPERA GX: UNVERIFIED - the running family is present (31-pid tree, all
five videodecode instances at 0.00 at rest) but carries NO debug port
(no --remote-debugging-port in any argv, no DevToolsActivePort under
the profile) - nothing to drive, so no opera playback delta exists.
The registry fact the packet assumed is also inverted on this box:
HKLM App Paths opera.exe is ABSENT (rc=1); HKCU App Paths opera.exe ->
C:\Users\user\AppData\Local\Programs\Opera GX\opera.exe (the per-user
install). A runtime resolver must probe BOTH hives. Profile
%APPDATA%\Opera Software\Opera GX Stable exists; the running main
process carries no --user-data-dir (default profile confirmed).
scripts/videoeye_probe.py (the DDA/PrintWindow/WGC rig the dossier
cites) joins the repo here so the gauntlet stamp reads clean.

## DECODE GATE, MEASURED - and the ctypes PDH wall (Oct 15, 17:51 runner)
The owner's gate idea is PROVEN on this box: during real playback the
engtype_VideoDecode counter answers on EVERY sample (0.33-0.54%), at
rest and on tab-close it sits at 0.00% across 196 instances - and the
answering pid is the browser's GPU CHILD process, never the main one
(live shape: main 61728 / child 63744). The gate must walk the process
tree and sum the family, or it reads zero forever.

THE WALL (a shipped-module finding, not theory): the ctypes PDH route
in wm/_videostats.py AND the probe rig's copy fails with STATUS
c0000bbd (STATUS_NOT_FOUND - the PdhAddEnglishCounterW export is
missing from the Pdh.dll on this Python/Windows pairing) on EVERY
counter, both call pairings, while Get-Counter reads live in the same
session. The production reader FAIL-OPENS to zero, meaning
video_busy() answers FALSE for a playing video on this machine today.
Consequence: the decode gate cannot ship on the current route; the fix
is the wide-char PdhAddEnglishCounterW call shape (or the Get-Counter
fallback), and a suite pin must assert a NON-zero answer during a
forced query or the fail-open hides the whole gate again. The Oct-13
header claim of a working reader was true then, or was never
verified-live - the dossier does not know which, and the lane's
honesty line says so.

OPERA GX: running on this box (31 pids, decode instances present at
rest) but carries NO debug port (no flag in argv, no DevToolsActivePort
file) and installs per-user (App Paths in HKCU, not HKLM - the
resolver must probe both hives, profile at %APPDATA%\Opera Software\
Opera GX Stable). Opera remains UNVERIFIED for the feature until a
flagged launch is tested; the ship lane does that test, it is not a
claim.

## PANELBOSSBUDDY: OPEN API, OPEN EXTENSION (owner ruling, Oct 15)
The companion is NOT PanelBoss-private. Owner law: the extension ships
open (MIT, in-repo, no obfuscation) and the video-location channel has
NO handshake, NO pairing, NO app allow-list - if the extension can
reach an endpoint, it reports. Any project wanting video rect +
playback state may listen; PanelBoss is just the first consumer.
Consequences written down so the next lane does not re-close the door:
- No shared secret in the manifest or messages. (An origin ACL on the
  native-messaging channel is the browser's own install-boundary
  check, not a pairing: the extension must name a host, and the host
  registration is what 'handshake' ever means here. If a future
  version adds a token, it is a bug against this ruling unless the
  owner says so in writing.)
- The message format ships documented beside the extension (schema in
  the extension's README); version it with a field so a second
  consumer can live beside the first.
- The app remains a *subscriber*: its own absence must never change
  what the extension does (no 'waiting for PanelBoss' state, no
  retry storms keyed to one consumer).

## VIDEO-DIM FOUNDATION - the decisions this batch ships (Oct 15, evening)
THE DATA PATH IS THE DEBUG PORT, not websocket-bidi: --remote-
debugging-port + stdlib HTTP/WS (panelboss/wm/_cdp.py) is the whole
Chromium story; the companion extension is the MANUAL trigger and
the future content-script seat, NOT a requirement of the automatic
veil. Firefox (no CDP port of this shape) is deferred to a content-
add-on future that rides the same bridge-file row shape.
THE .LNK EDIT IS RETIRED: no shortcut rewriting anywhere - the
flag is re-armed at launch (PanelBoss owns the launch when the
feature is on; a browser already running unflagged is simply a
family the eye cannot see, confessed in the per-family say line).
BRIDGE FILE (the manual trigger, %APPDATA%\PanelBoss\rect and the
zero-plumbing Downloads\PanelBoss\rect the v1 click writes via
chrome.downloads): freshest source wins, ties the file's. The
native-messaging host is FUTURE work and today's measurement says
start elsewhere: the .cmd-wrapper manifest shape DIES AT STDIN EOF
(the wrapper exits before the host answers) and the two-token
pythonw manifest form FAILED on this Edge (boots, never hears the
message) - both named in extension/README.md's future section so
the next lane does not re-derive them.
PACKET REALITY, MEASURED AT DISPATCH: "Edge is running with the
port at 9222 (Edg/156)" had aged out - Edge ran WITHOUT any flag
(6 procs, no netstat listener at 9222); the live debug port was
CHROME/155 at 9333 (a prior lane's experiment, user-data-dir
truncated at the space in "User Data" - the argv shows why quoting
matters). The full transport rode that live browser: handshake,
Runtime.evaluate (a real 800x450 paused fixture video), the
Browser.getWindowForTarget/getWindowBounds pair (response shape
{"windowId", "bounds{left,top,width,height}"}, DIP px), fold to
physical (708,551,800,450). By delivery time that browser had
exited and probe() reports no-debug-port for all three families -
the fail-open path, live-verified twice. Opera GX: still no flagged
launch on this box; UNVERIFIED for the feature until one is tested
(the launch-owning lane does that, it is not a claim here).
THE GEOMETRY JUDGMENT the packet left open, decided and pinned:
the straddle frame covers, per intersected monitor, MONITOR minus
the FULL rect - a piece's inner edge is the rect where the rect
crosses the panel border, so the video column across the seam
stays bright and no dark sliver can land on video px (test pins 13
and 14 hold both the single-monitor four and the straddle six).
getBoundingClientRect is VIEWPORT space: the scroll pair rides the
row for the DRM future and does NOT shift the veil (pin 6).
PAUSED IS NOT LIVE: the feature dims playback, not posters (pin 7).

## CARD SHIP DIED SILENTLY (Oct 15, ~18:3x) — the third zero-byte lane
of the day. Capped lanes normally force a text handoff (the two
step-cap lanes today did exactly that); this one COMPLETED with no
text at all and committed NOTHING (tip still ebff8b1, worktree clean,
companion.py absent). The failure mode is the Oct-13 class, one layer
up: a continuation guard kills the session, and the runner reports
'completed' without the report. Countermeasure, immediate: the card
re-issue runs as a FOREGROUND dispatch — a lane that dies in the
foreground dies audibly in my window, where the loss is visible
instead of discovered by the next audit.

## FLAG LAUNCHER GAP (named, not silent, b7bc55c)
The card now records the per-family flag choice and the engine reads
it, but NOTHING yet restarts a browser to actually carry the port -
the checkbox is a decision with no executor. Next lane: the re-arm
launcher (kill-with-restore + flagged launch, the semantics the CDP
probe already measured), or the flag rows gray themselves until it
lands. The zero-plumbing path (icon click -> bridge file -> veil) is
the one PROVEN end-to-end candidate and needs no launcher at all.

## THE BURN-IN PERIOD IS THE PLAN, NOT A CAVEAT (owner, Oct 15)
Tonight's class: a feature that is correct on the desk it was built on
is wrong the moment the desk changes. The dimmer's opt-ins survived
from the physical OLEDs onto the RDP virtual display and blacked the
owner's remote session - the per-monitor law did exactly what it was
told, on a panel the owner never opted in from the remote side, with
the state imported by config rather than chosen. The MSI fresh-install
trial would have caught it; a few days of the final build on the real
life desk (office, remote, sleep, replug) catches its unknown cousins.
Owner ruling recorded: between the trial and the ship sits a burn-in
period of days - FINAL STATE, no more feature traffic - and nothing
goes out before it. The feature freeze is the point, not the delay.

## DOSSIER: the capture freeze (Oct 16) - CLASS LEDGER, third bite
Symptom: click "capture this desktop" -> UI frozen hours; hider stuck ON,
dimmer fine. Debugger caught it live (py-spy x2, byte-identical frames +
native): Tk thread deadlocked in GetWindowTextLengthW -> SendMessageW to
the app's OWN hider-paint thread, which was blocked in Font.__del__ ->
tk.call back to the Tk thread. Closed circle. Raymond Chen's rule explains
the asymmetry (own-process windows SEND, foreign windows read the cache).
CURE (e0de9f4, gauntlet-green): dose 1 own-process titles ride
SendMessageTimeoutW(SMTO_ABORTIFHUNG, 1500 ms, honest empty) - and the
display.py SMTO_NORMAL constant (held 0x0002 = ABORTIFHUNG since first
write) renamed to what it is; dose 2 capture worker-ized like its apply
sibling (done() ghost-tolerant, ui_events ("later") belt for the pre-
mainloop marshal class); dose 3 skin FONTS ARE A CACHE (strong refs -
the GC cross-thread class structurally dead). Five suites grew the
bounded pump (the file's own 8c law). The reviewer's first finding
became the fix's second dose: the strong-ref LIST leaked a CTkFont per
widget per re-render in a tray session - caught before ship.
CLASS: blocking cross-thread Tk calls without deadlines on the pump
thread - bite 3 (wake-freeze, Oct 15 editor destroy, this). Debugger's
verdict PATCH; recurrence of a 4th bite -> REFACTOR class (one inter-
preter + queue-only data) = the owner's UI-process-isolation instinct
expressed inside the app. PROCESS-SPLIT EVIDENCE: one blocking edge was
a cross-PROCESS SendMessage (to a foreign frozen window) - a separate
UI process would have hung on it too; the deadline, not the boundary,
is the cure. Split stays open as design direction, not tonight's fix.
Live repro owed by owner: capture click with hider armed -> instant
"capturing...", profile lands < 2 s (was: dead UI for hours).

## DOCTRINE (owner, Oct 16, mid-flicker-task): the settings-app veil is
## a SERVANT, not sacred. "I don't care about the veil machinery at all
## in the settings app - that's only there to try and hide paints,
## destroy it if it no longer hides paints." Its Oct-15 event-driven-lift
## law was engineering for the veil's own correctness; the owner's frame
## is the goal, not the mechanism: if repaints become atomic by
## construction, the veil machinery (widget, watchdog, hold budgets,
## lift choreography) goes. The DIMMER veils (oled feature, dimmer.py)
## are unrelated - those dim monitors, they do not hide paints. Judge
## survival by what a capture still shows, not by what the code protects.

## DOSSIER: the companion, store-grade (Oct 16, fixer tranche, tip bb6bbd0)
Channel: chrome.runtime.connectNative <-> stdlib-only host exe (one file,
no net, no port), frames native-order length-prefixed JSON (the LE lore
was wrong-law, fixed @I), veil op writes %APPDATA%\PanelBoss\rect,
capabilities op DISCOVERED BY THE APP (nmhost.py: spawn the exe recorded
in %APPDATA%\PanelBoss\host.json, 2 s kill-on-timeout, TTL cache, stat-
not-spawn when absent). The card answers "buddy API: ..." from the
reply - the owner's 'we'll make panelboss read what the api is capable
of' is now literally true, not commit-poetry (gate round 1 caught the
poetry; round 2 caught the PowerShell BOM the producer/consumer pair
hid - utf-8-sig + a real-BOM pin). DEAD SHAPES total: cmd-wrapper host,
pythonw-token host, chrome.debugger click (banner + silent hang, owner
killed on sight), downloads-file bridge (store-hostile, shelf-dependent
- shelf law itself retired), debug port (dormant engine, off the UI).
_cdp.py deleted, config [videodim] = {on, min_rect_px, grace_s}, old
keys parse away. Installer validates the 32-char a-p id shape before
registering (a typo used to read 'nm' forever). STORE TEXT lives in
extension/README.md (scripting/activeTab/nativeMessaging, one-line
justifications; zip WITHOUT host/, the app ships the host).
OWNER UAT PENDING: load unpacked -> id -> install_host.ps1 -ExtensionId
<id> -> reload the card -> video tab -> click -> badge 'veil' -> arm
Movie theater mode -> four dark pieces frame the player; the card's
capability line must light up the moment host.json exists.

## FAILURE CLASS: the credit wall (Oct 16, owner-explained, do not re-diagnose)
Subagent dispatches on cloud lanes can die at START with 'would exceed
available credits given current in-flight requests'. The wording lies:
it is NOT concurrency - it is the OPENROUTER BALANCE. Mechanism
(owner, measured tonight): balance drops under the auto-top-up floor
(old floor \) -> top-up fires with delay -> in the gap, requests
refuse -> the top-up lands -> restart of the SAME dispatch works.
Owner raised the top-up floor; recurrence now means the floor needs
raising AGAIN, not that the fleet is oversubscribed. Fleet insurance
that made this survivable and stays law: commit early (every salvage
was a clean commit, zero work lost to the wall - b118c0e proves it),
and retry-once on any dispatch that dies at START with no output (a
wall-death never wrote anything; a retry after the balance lands is
free). Misreading this class as a fleet bug burns an investigation
pass; this entry is the whole diagnosis.

## ADDON (owner, Oct 16, NOT NOW): per-monitor veil level — ABSORBED
ABSORBED by the Oct-16 per-panel wave (the block below): [dimmer].
levels per EDID token + per-panel card sliders landed for the plain
veils, and the theater question got answered with its own per-panel
rows ([videodim].monitors: selectability + OWN level, full-field on
the opt-in panels - the straddle keeps its per-panel border pieces).
What follows is the entry as parked.
The idle dimmer's veil-level rail is ONE number for every panel - and
panels answer differently (measured on the owner's desk: 49% goes DARK
on DELA283 and is BARELY a tint on IOC912B - per-panel gamma/contrast
laws). Wanted: the veil level per monitor row (the dim card's per-panel
rows already exist as the opt-in seam - the level rail becomes a per-
row value with the card's master as default), config shape [dimmer.
levels] per EDID token (identity law: tokens, not slot numbers), one
calibration story on the card that doesn't beg for an editor (the
'always' row is the precedent for a sub-control riding its parent's
opt-in). Also relevant then: the THEATER veil's percent rail wants the
same question asked (one video frame straddling two panels with
different veil darkness will LOOK wrong - the straddle seam knows both
panels; decide then whether theater uses the brighter of the two, an
average, or its own per-panel row too - do not half-do it).

## UAT WAVE (owner, Oct 16, LANDED): the timer laws, the origin report,
## per-panel veils (commits a0fea3e / 7935de9 / a8cfb6e)
- TIMER LAW, theater: [videodim].idle_sec rails are 1..30 (the slider
  max moved "5 min -> 30 s"). Provenance of the FLOOR (owner law
  "rail MINIMUM 1 s"): at 0 the veil NEVER lifts - rect updates stop
  re-birthing and the ring sticks at its first geometry (the sticky-
  veil class, owner UAT Oct 16). The stock default 15 stands.
- TIMER LAW, dimmer: [dimmer].idle_sec ceiling 300 -> 60 (owner: the
  slider max "5 min -> 60 s"). The stock 120 now clamps honest at the
  ceiling in silence (zero new warnings on an old file).
- LIFT-FADE TOGGLE, default OFF ("60 s veil lift is dumb"): a new
  [dimmer].fade strict bool; OFF = the plain veil drops the INSTANT
  input returns (both retract paths), the "fade within" ramp applies
  only when on; the theater's own [videodim].fade is untouched -
  two keys, two owners' words. The dim card carries the switch.
- PER-MONITOR THEATER LAW: [videodim].monitors rows (EDID shorts)
  make the theater SELECTABLE per monitor with its OWN level slider
  per monitor; a non-video panel with a row wears a FULL-FIELD theater
  veil while the conjunction holds (row level, or the global when
  absent); on=false strips the pieces from the panel its own video
  sits on (plain veils proceed). Absent table = the legacy shape,
  every pre-wave config pin passes unchanged (the regression proof
  lives in videoeye_test).
- PER-MONITOR PLAIN LEVELS: [dimmer.levels] {short: int}, per-panel
  sliders on the dim card, the card's master as default (the ADDON
  above, absorbed).
- GEOMETRY LAW - the border-guess BECAME A REPORT: the fold's even-
  split border correction was a GUESS and the owner's maximized window
  proved it (measured live doorway row: bounds.left=-8 - a maximized
  window's borders hang off-screen, the hole sat a few dozen px off).
  content.js v0.4.2 REPORTS the viewport origin (window.screenX/
  screenY, DIP); the fold uses the report when present
  (x = round((origin0 + rect.left) * dpr) - the same round() as the
  legacy lane, banker's ties included) and the bounds formula survives
  ONLY as the compat lane for host/extension pairs mid-update. The
  owner's bite vector is pinned both ways: report -> 614, guess ->
  634, truth -> 614.
- SCROLL RE-PUSH FIX: the scroll listener moves to {passive: true,
  capture: true} - inner scrollers fire scroll on the ELEMENT and
  scroll does not bubble (capture phase only); a visible veil now
  re-pushes through a page-internal scroll. The 1 s idle floor stays
  the PRIMARY cure; this is the cheap correctness.

## THE ROADMAP (owner, Oct 16, verbatim order - this IS the release plan)
1. Owner verifies Movie theater mode (the UAT above).
2. MAKE THE MSI. Wipe the owner's profile. COMPLETELY FRESH INSTALL from
   the MSI. Run it for DAYS looking for bugs (the burn-in - final state,
   the freeze is the point). Owner makes an app icon during this window.
3. When bug-found stops: integrate the icons where they belong (app icon
   into the exe/shortcuts, tray icon into the tray), update the GitHub
   README, get the extension on the Chrome Web Store (the store text is
   already written in extension/README.md; zip WITHOUT host/, the app
   installs the host).
4. Update the MSI (icons + any burn-in learnings), cut a GitHub RELEASE
   carrying the MSI, set the repo PUBLIC.
5. Owner hits Reddit with the link. Promotion is the owner's channel.
6. HYPER CARE after that (rapid-response phase: fixes ship fast, the
   fleet knows).
Preparation already banked toward step 2: the six MSI laws live above
(this file), the companion installer is now a CARD BUTTON (no console
needed by a fresh user - the fresh-install trial will prove it), the
start-menu entry exists (the MSI replaces it with the registered kind),
the credit-wall and dead-transport dossiers keep the next architect
from re-paying tuition.


## Oct 17 - secondary-veil flicker dossier (census in-line, lane note)

- Owner symptom after a5c95c2 deployed: full-field theater veils flicker on BOTH secondaries (IOC + AOC); video panel perfect.
- captain-debugger lane returned EMPTY TWICE (ses_eb7250a52ffe9C76RRxLO98lZv, no text, no report). Fleet heuristic: a silent cappy completion is a LANE FAULT, not a verdict - do not re-boot a third dispatch on a small probe; the architect's 100-line census settles it cheaper.
- ARCHITECT CENSUS (zchain-0930.py, live desk, app up): monitors DELA(0..3840) / right(3840..7680) / left(-3840..0). Trays: RIGHT secondary top=True z=4, PRIMARY top=True z=9, LEFT secondary top=FALSE z=49 (per-monitor taskbar setting). App pieces: right piece z=3 ABOVE its tray (prev-chain: own hider strips -> ForegroundStaging - never reaches the tray, it is BELOW); left piece topmost=FALSE (sitting in the ORDINARY band - behind the browser).
- ROOT CAUSES (two, both structural): (1) the slide-under reads GetWindow(tray, GW_HWNDPREV) AFTER the raise put the piece ITSELF above the tray -> SetWindowPos(h, h) no-op -> stranded above chrome -> _in_slot's UP-walk can never reach a tray that is BELOW -> False forever -> 5 Hz pair = flicker (right monitor). (2) non-topmost row-tray (left): slide drags the piece into the ordinary band -> buried by the maximized browser -> raise/slide war per beat, veil mostly invisible = 'no proper video veil'.
- FIX DISPATCHED (coder ses_eb7163160ffe, background): slide with the TRAY ITSELF as hwndInsertAfter (position-independent, no self-reference); slide ONLY for topmost trays; two-law _in_slot (under-tray when the row's tray is topmost; band-top otherwise); theater_live under-tray check follows the same law.
- STILL OPEN after the fix: owner visual on both secondaries; then the owed run_all.ps1 at push.

- OPEN (found by docs wave Oct 17): Tray.set_state (state-color hook, tray.py) has ZERO callers - the palette exists, the wiring does not: the icon stays green through away/pause states. Small wave: call it from the state machine transitions (dimmer pause, away enter/exit, theater active?). Also parked: public repo URL placeholder in README (git clone <this repo>) until the repo is made public.


## Oct 17 - MOVIE THEATER MODE: OWNER STAMP (UAT verdict)

Owner, verbatim: 'Movie theater mode is a ship with my own stamp - other systems that I can't personally test aside.' Scope of the stamp: THIS desk (Win11 RDP, GX maximized, 3840x2160 dpr1 + two secondaries with divergent taskbar states), the full chain: extension -> host (webrect) -> fold -> ring/per-monitor veils -> z-law (still at rest) -> idle conjunction 1s floor -> fade default-off. NOT stamped (owner's own exclusion): other systems (dpi-scaled desks, other browsers' render-widget class names, mixed-DPI), and the non-theater systems he never UAT'd in this pass (gaming hz/hdr automation, faces, placement restore internals). Verification spine: dimmer 50 / videoeye 33 / companion 47 pins, gauntlet 51/51 ALL GREEN at 10240f1, guard scripts/theater_live.py remains the live-desk tripwire for the z-law class.

Next on the owner roadmap: MSI wave (six laws in the earlier block), profile-wipe fresh-install burn-in, store submission (zip READY: dist\panelboss-companion-0.4.2.zip - unchanged since the fixer wave, extension files identical), owner icon art -> make_icon.py, README screenshots placeholders -> art, GH release + public repo, Reddit, hyper care.

- STORE STATUS (owner, Oct 19): submitted 0.4.3 (zip dist\panelboss-companion-0.4.3.zip, store shot dist\store-shot-1280x800.jpg, single-purpose + permission text supplied); Chrome warns review may take SEVERAL WEEKS. Launch therefore ships with MANUAL extension install: the app's companion card gains a "manual install files" action (unzip to %LOCALAPPDATA%\PanelBoss\companion + open the folder + jump chrome://extensions; 5 clicks + dev-mode toggle, the whole off-store door Chrome leaves open). The key-pin makes this seamless: manual and store copies share feolhiok..., so store approval replaces the unpacked copy invisibly, host registration untouched. Reddit copy must own it pre-emptively: "needs the free companion extension; Chrome review takes weeks, until it clears it's a 5-click manual install - and the store version replaces it invisibly (same ID)." MSI wave carries the manual-install card work.
- SITE-ACCESS v0.5 DESIGN (owner question, Oct 19): the hard-coded matches list means every new site (incl. the adult web the owner named) is a manifest edit. Answer is NOT a longer list: ship optional_permissions ["<all_urls>"] (store renders as tame "when you add sites"), a "watch this site" button in the popup asks Chrome for the ONE origin and registers content.js there at runtime via chrome.scripting.registerContentScripts - user-curated sites, no re-review per domain, no taxonomy in the README. Pre-bite caveat: the top-frame law (all_frames false, documented in content.js + README) will answer "why not my site" for the iframe-player slice before permissions ever do; all_frames=true is a one-line change that multiplies the script per frame - deliberate call, not a default.


- TRANSIENT-POPUP law trade (gate, Oct 17): while a TASKBAR menu is open the foreground row is the dropped tray row, so always-dim panels dim blind for the menu's lifetime - judged on-principle (a menu is not a panel you are using) but named for the record. Taskbar no longer plain-veils (same law, permanent chrome).


## Oct 17 - TWO-STAGE AWAY + CURSOR PARK (owner feature wave, in flight)

- Owner laws verbatim: stage two after x minutes of away (blackout first ~15 min for the OLEDs, then full monitor power-off - GPU stops presenting, longer wake is 'a fair trade'); blackout 'is still leaving my mouse on screen' -> park the pointer at the bottom-middle of the lowest monitor on away engage; 'no restore, noone remembers where there cursor was after leaving the room.'
- Design locked: [away].off_after_min default 0 = single-stage (byte-identical); clamp 0..240; painted modes only (off/offdisc already sleep); MONOTONIC engage clock stamped in _screens_off (the wall-clock _away_off['tried'] stamps must NEVER mix with it - the salvage caught the class before the code); heartbeat arm _away_beat rides _off_phase (every tick, poll-gate-free); the verb is the EXISTING VCP D6=4; staged GDIs recorded INTO self._away_off so the existing wake lift hands the screens back for free.
- PARK REPLACES JAIL for painted modes: display.jail_cursor already parks at the far corner for blackout-degraded/off rows - two parks would double-fire SetCursorPos; decision: painted modes -> park (bottom-middle, the owner's exact ask), sleep modes -> jail unchanged. Pin proves EXACTLY ONE pointer move per engage through the u32 fake.
- FLEET NOTE: this is the SECOND silent lane death today (cappy x2 earlier, coder here) - both times the continuation prompt extracted real value (this one died at zero writes with a full anchor-correction salvage: six packet lies caught pre-implementation, including the packet's own 'reuse that clock' which named a heartbeat that does not exist). The continuation-ask is the right first response to an empty completion, not a re-dispatch boot.
- OPEN after landing: owner UAT (walk away, return before/after N; check the pointer sliver bottom-middle); MSI note for the installer wave: away defaults change only in the new key, no migration needed (absent = 0 = today).

- LANE NOTE (Oct 17, gauntlet-away wave): layout_test went red on 'fingerprint empty, 0 monitors' - LAWFUL desk state, not a regression: the console had been screen-offed and no relaunch had happened, so the desktop sat on the no-panels answer (the zero-panel class the census already honors). The gauntlet needs the desk lit AND the app up; the runner ritual is now: (re)start app, wait its boot line, THEN run_all. Owner nudge (input) wakes the console; a bare Start-Process did not, this time.


## Oct 17 - MONITOR-ROW REFRESH (desk-ear wave, owner UAT)

- Owner repro: app opened with zero monitors attached (my gauntlet killed the old one mid-away-spell; the relaunch inherited the dark desk) - the detection tab's away rows were born into an empty enumeration and the card never re-read. Engine hot-plug-robust (census every tick); the UI froze. The same staleness waited on four oled-tab sections, the gaming card, and the profiles list - caught by census, all of them.
- The class-cure, one idiom (the _cam_rows discard-and-refill the window already teaches): every monitor-row loop moved into a _fill_rows method feeding a dedicated transparent frame pinned between the desk-independent rows; refresh = destroy children, re-enumerate, rebuild from cfg. The refresh fanout (SettingsWindow.refresh_monitor_rows) walks the four rebuilders per-section-guarded; the pump grows a desk ear: wm.fingerprint() every ~2 s on the Tk thread (one Enum pass), rebuild ONLY on change, seeded at first check so a boot-time desk is truth not delta.
- THE BUTTON is the belt the ear cannot wear: an identical-model panel swapped behind a KVM keeps the fingerprint byte-equal - the poll is lawfully blind there, and only a human knows the glass changed. It rides the away card (where the owner hit the hole); the fanout covers every card.
- Rebuild discipline: the away card cancels live previews through their OWN manual-cancel path before discarding their rows (the applied effect reverts, then the editor dies); _oled_sync/_away_sync re-run after every fill so fresh rows never outrank gray-not-lie.
- FLEET: the coder lane died silent a THIRD time today (this dispatch, zero writes, clean tree - after two earlier ones on the away wave). Inline build per packet law; the lane problem may be the door (prd/q27 coder route) rather than the seat - worth a probe when the fleet is idle: a known-good tiny packet at the door and at the direct OldBeast pin, compare.
- Tests: window_boot_test REWORKED around the owner scenario - the window now BUILDS on an empty desk (static world asserts: no rows, deep-sleep slider and refresh button present), the fake desk returns, refresh_monitor_rows() fills exactly one row per card (the fake's 'T' panel), a second refresh proves swap-not-stack, and a source pin proves the ear is on the pump. Full gauntlet ALL GREEN; the one prior red (layout_test reading zero monitors) is the very desk-state this wave makes self-healing - green on the lit desk too.


## Oct 19 - CRASH INVESTIGATION: stage-two disconnect, and the phantom twin

- Owner A/B (live-seat, highest quality): D6=4 at ENGAGE (panels awake) = fine, all rows, repeatedly. ONLY the second-stage write crashes - pythonw.exe pid 40000 native death Sunday 14:53:22/25 (WER: BEX64 StackHash, 0xc0000005, module unknown), no 'stage two' log line EVER (the beat fires the verb BEFORE its log line - a native death mid-verb leaves the dump and no prose). Hypothesis narrowed toward: cached PHYSICAL_MONITOR handles crossing 30 min of DPMS-dark + the KVM's DDC leg vanishing with the panel + the retry law re-asking the AOC's refused (deaf) row at N. Captain-debugger dispatched background with full evidence (ses_eab74fb30ffesL9esYLWpt8ZcG); repro deliberate, probes read-only first - the live app contends the bus.
- PHANTOM TWIN RESOLVED (mine was wrong first): the second pythonw at every boot is the WINDOWS VENV SHIM - a redirector that re-execs the base interpreter as its CHILD and waits; the stub shows the same run.py command line. Proof: the 6:54 boot banner names ONLY the child (38676: 105 threads, 320 MB); the parent (34520) is one thread, zero CPU ticks. Single-instance mutex honored. The Sunday dump name 'pythonw.exe(1).40000.dmp' = the stub (40000's parent slot) reporting the child's death. Consequence for the crash story: exactly one state machine was ever live; the twin is cosmetic. (Owner's dimmer-weirdness for a few minutes therefore NOT double-writers - it sits inside Sunday's 22:56-23:20 triple crash/respawn window with hid.exe (MonitorProfiles' helper) dying on the same bus minutes apart. MonitorProfiles.exe is a co-resident DDC client worth ONE sentence in the store description's compatibility note.))
- Overnight sequence: crash, crash, crash - autostart respawns at 22:57, 23:11, 23:20 (all 'code from 13:36'), hid.exe APPCRASH at 22:56 and 23:17 in ntdll. The KVM's DDC path and/or the driver stack is the shared victim surface.
- Owner config at crash time: [away] all four rows OFF=true, off_after_min=30, mode dim. With trusted-off rows the beat's ledger law sends ZERO writes at N - yet it died - so the eligible-row class (refused-AOC retry, or a row whose status folded to blackout) is the prime repro target named in the dispatch.

- CORRECTION (same day, hours later): the 'cosmetic venv twin' claim was wrong in the direction that MATTERS - the Run-key's venv pythonw stub does NOT wait; it re-execs the base interpreter and EXITS (or the second pythonw exited cleanly pre-banner both nights). Today's relaunch shows ONE pythonw (38676-style base interp). Sunday's dual dump names (pythonw.exe.40000 + (1)) remain open for the debugger: either two stub-generation dumps of one death, or the twin lived briefly and died in the same storm as its child. The ledger prefers the second: the BEX64 class kills parents that wait.
- STAGE TWO RETIRED (owner decision, Oct 19, first light): 'we may want to ditch this feature in hindsight - I can just unblock the native windows screen turn off and set it to 30 minutes and let windows handle the deep sleep.' The crash dossier made the call easy: monitor power is a DEVICE-LIFETIME problem and the OS monitor power state machine owns the re-plug semantics a cached userland DDC handle cannot promise. Gone: off_after_min (DEFAULTS, parse, return dict), _away_beat + its engage stamp/lift rewind, the _phase call, the UI slider row + handlers + sync gate. KEPT (the wave's better halves): the cursor PARK + park_point (TIP sentence moved to the mode paragraph), the per-row off submode (D6 at engage - owner's own A/B says it works fine), the boot belt. Deprecation honesty (the fossil law, hdr-migration precedent): normalize warns the retired key NAMING ITSELF once per boot and drops it; the next save removes it from the file; test_deep_key_gone pins exactly that. The five stage-two pins die with the feature; awaymode 25 green, full gauntlet ALL GREEN (the one red - profiles_ui at 0x40010006 stack-overrun - is the SAME native family this whole investigation is about, green standalone with the app down; the shared-bus contention note says the gauntlet ritual must keep the app down for its WHOLE run, relaunch after the last suite).


## Oct 19 - THEATER GHOST (visible-picture law) + the captain's door verdict

- Owner UAT break: the veil storm was theater's conjunct fed by a GHOST - GX's memory-saver parks the media tab's page at (-32000,-32000) with paused:false; the extension reported a playing video (correctly!), the fold landed the rect off-desk, and the conjunction (video + 2 s input rail) held through every typing gap - applied and torn down in the owner's keystroke rhythm. LAW ADDED (videoeye.video_rect): a row's folded rect must INTERSECT the virtual desktop (GetSystemMetrics 76-79, one call; refusal = True fail-open). Ghost rows are no video; straddled windows stay movies; the UAT law (visible movie, full-field veils elsewhere) untouched. 3 pins (ghost None, edge-inside fold exact, straddle visible) -> videoeye 36. THE MYSTERY OF THE DOUBLE VEIL: the census showed same-geometry TkTopLevel twins x2; owner reports it tied to the theater conjunct - the fix removes the conjunct's ghost; if twins return with a REAL movie, the veil repaint path owns the next dossier.
- THE BOOT LIE HUNT (owner: 'theater turns itself back on after every boot'): the file persisted on=false, normalize honors it, the switch knob is strict-True from cfg, and NO boot-path writer exists for videodim.on. Rather than patch a rumor: config.get_config now logs ONE INFO line at boot (videodim boot: on=%r rows=%r) - the next boot shows its hand. If it says True over an on=false file, the writer is caught by name; if it says false and theater still veils, the eye is exonerated and the veil painter owns it.
- CAPTAIN VERDICT (ses_eab74fb30ffesL9esYLWpt8ZcG, REFACTOR on _bright.py): root cause is OUR handle discipline - the display-change ear calls DestroyPhysicalMonitors synchronously on the watcher thread while _bright.vcp writes cross-thread, retry-sleeping 0.3 s holding handles the ear may free mid-retry; the driver also PnP-removes the dying leg asynchronously (monitor.sys). The AV executes in the ctypes/libffi trampoline page (0x46730000 page-aligned UNMAPPED, C000041D fatal-user-callback) - matches the Sunday 14:53 dumps EXACTLY. Stage two re-asked the AOC's dead leg by design; the owner's own A/B harness died the same death at 07:32 TODAY (python.exe.12708 - new bucket 25f487ea), the captain's census counted 9 hid.exe deaths of the same class since Sep 28: the bus kills every user-mode DDC client with loose handle rules, ours included. Fix spec (4-6 coder steps, no caller changes): RETIRE-NOT-FREE (invalidate() appends to _retired, never calls DestroyPhysicalMonitors), SETTLE WINDOW (vcp/set/restore return a clean refusal for 5 s after any invalidate or import; reads NOT gated - measured clean all morning incl. the deaf AOC leg), ARR SLACK (allocate count+2 against the ghost-re-attach TOCTOU), BELT STAGGER (1.5 s between row asks + law comment: refused rows never re-asked inside their spell; re-asks re-stamp the dated law).
- FLEET: this is the captain's trial's first FULL success since the Oct 15 revocation talk - evidence-first dispatch (A/B, dumps, logs), no wasted guessing, one live A/B crash caught by his own census mid-session. His CONTINUABLE: install cdb.exe (Windows SDK) - !analyze -v on the pythonw dump would print tid 7356's frame list in one command; none on PATH today.
- OPS for the owner, verbatim from the report: MonitorProfiles.exe is a third DDC client with its own crash history on this muxed bus - disable its autostart or its KVM profiles; the AOC2790 leg is provably dead-at-power-down - blackout-only on that row means zero D6 verbs aimed at it.

- DIMMER DOOR, elevation word (Oct 19, owner's double-veil report on Task Manager): _fact carries 'elevated' (advapi32 token pair - kernel32 on this build resolves OpenProcessToken but NOT GetTokenInformation, measured; label-relative RID = first DWORD; self-RID cached; refusals answer False = veil-anyway, conservative branch per the popup school; per-pid cache like _exe). The door drops elevated rows with the fg escape (the Oct-15 attribution lesson: the focus word must survive every door). Card copy (TIP_DIM.on) + README say the law and the administrator escape WITH the not-recommended why. BUT the witness desk: this desk's Task Manager is NEITHER elevated NOR topmost (ex 0x100, Medium) - the law is class-correct (it follows the token, not the name) and the captain's UIPI doctrine stands, yet the SPECIFIC ride-over the owner screenshotted is not explained by elevation on this box. z re-pin runs every tick (line ~1213, _in_slot idempotent) so a stale ride-over should self-heal in one tick; the screenshot moment had the theater ghost ALSO live (fixed 09 minutes before the shot) - the double veil is one un-reproduced sighting with a contaminated witness. DOSSIER, OPEN: if the dark patch on an app-above-TM appears again, run scripts\dimmer_test.py's live witness while idle (it prints the classification) and screenshot; next suspect order: (1) anchor staleness inside the _zpin synthetic branch under TM's self-reordering, (2) the re-pin's SetWindowPos NOZORDER family flags, (3) TM's own layout pass. The elevated exemption stays regardless - it closes the captain's UIPI class on every desk whose Task Manager DOES run elevated.

- CORRECTION (same day): 'this desk's Task Manager is neither elevated nor topmost' was the BROKEN PARSE talking (offset-0 read the TOKEN_MANDATORY_LABEL header pointer - a constant that compared equal for every token, the dead law the gate predicted). The measured fix (PSID at 0 -> GetSidSubAuthority[0], advapi32 - and the accessors live there, the loader corrected the kernel32 guess the same way it corrected GetTokenInformation): the live witness now prints 'elevated=True -> veil-exempt' on THIS desk's Task Manager. The owner's double-veil sighting was NOT contaminated after all - it was the UIPI class, fully explained, and the exemption earns its keep on the inspiring hardware. The hexdump also showed the label's attrs 0x60 - which a hurried note overread as a LINKED elevation; they are the ubiquitous SE_GROUP_INTEGRITY|_ENABLED enforcement bits (corrected in the dimmer docstring; the LAW is untouched: the current, filtered token is the ruler because UIPI evaluates the current token, and Attributes are never consulted). Gate findings 2 (fake-state hygiene: finally now resets _OURS/_elev_cache before the live witness) and the parse docstring all applied; companion's ghost-branch pins ride the next test pass.
- FLEET: this is the third gate-BLOCK-class save this week where the suite was GREEN - fake agreeing with the author's misread is the oldest trap and the reviewer lane keeps paying it off (Oct 17 class-list blindness, Oct 19 SID offset). The cheap antidote each time: one measurement against the live object before the fake is written.

## Oct 19 - DDC/CI DOOR CLOSED (the captain's fix spec executed, 02c30b2 + fed41f2)

- Verdict ses_eab74fb30ffesL9esYLWpt8ZcG landed as four deltas (no caller changes): (1) RETIRE-NOT-FREE - invalidate() FORGETS, never frees; popped (count, array) pairs ride _retired to process exit, the kernel reclaims, the driver's later calls answer clean refusals not faults (the C000041D trampoline-free class dies with the free). (2) SETTLE WINDOW - vcp/set/restore return clean refusals (vcp the SETTLE word; set (REFUSAL, False); restore the silent return it already had) for SETTLE_SEC=5 after any import or invalidate; reads UNgated (get/vcp_read/reachable - measured clean on dead and live legs, and the engage's honest prior needs answers). (3) ARR SLACK - GetNumberOf/GetPhysical is a TOCTOU on a KVM desk: the array allocates count + _ARR_SLACK(2), the API is told the ORIGINAL count, a ghost re-attach between the two calls overruns into slack, not the heap. (4) BELT STAGGER - _away_boot_belt sleeps _bright.BELT_STAGGER_SEC(1.5) between row ASKS (counted on asked rows, never walked ones) through the _belt_sleep module seam (Ledger-fakeable, no real seconds in CI). The law comment carries the captain's words: a refused 'off' row is NEVER re-asked inside its own spell; any future re-ask rides vcp (settle-gated) and must re-stamp rec['tried'] (the dated law).
- Pins: scripts/bright_door_test.py (rostered): settle gate closes the bus and reopens on the fake monotonic; N invalidates ride _retired with DestroyPhysicalMonitors never called; the count+1 ghost writes the slack slot clean. awaymode_test grows test_belt_stagger (three asks, two 1.5 s spacings) beside test_boot_belt, whose seam is faked too; 26 tests green with the app RUNNING (the door suites are hardware-blind by fake design). The boot belt runs past import+6 s, so the import seed never gates it; the belt's own stagger still spaces its asks.
- FLEET LESSON (the law to keep): a handle cache whose lifetime is owned by an ASYNCHRONOUS driver must never be freed on the event thread - the moment you free memory another thread may hold a receipt for, every later callback is a lottery against the allocator. Forgetting is always safe; freeing is only safe when you own the quiescence, and monitor.sys never asks.

- GATE ROUND 2 (door patch, ses_eab1f75fdffe: SHIP-WITH-FIXES): the BLOCK's remediation judged GENUINE (measured parse, fake hygiene, direction correct). Four takes: (MEDIUM) the wake arms the settle window itself - panels powering up ARE a display change - and the lift's D6=1 (a one-shot, ledger cleared unconditionally after) would be politely refused into a dark-until-next-boot panel: THE HANDBACK WAITS THE WINDOW OUT (settle_left public, lift waits once when ledgers non-empty; the belt waits before each ask - a refused row no longer swallows the rows behind it; seam renamed _belt_sleep -> _bus_sleep, one sleep seam for all bus-waits). (LOW) _retired capped (RETIRE_CAP 64, forget-never-free - the cap drops OUR end; worst in-flight hold is the ~1.4 s retry budget, cap age cannot touch it). (LOW) the attrs 0x60 note overread (SE_GROUP_INTEGRITY|ENABLED, not a linked-elevation marker - corrected in docstring and above; law never consults Attributes). (INFO) 28-byte floor made pointer-size honest (20 on x86, fail-open either way); belt-vs-seed timing claim replaced by the wait (no margin load-bearing). New pins: settle_left counts down / closes to zero; retire cap forgets at 64 with destroy still 0; belt 3.05 then 1.5 sleeps, both rows reach a quiet bus; lift 2.05 wait, hand-back sent, ledger clears. bright_door 4, awaymode 28, dimmer 52, writer, run_all parse 0 errors - all green.

- CONSENT DOOR, the veto removed (owner, Oct 19): off-then-on refused to stay on unless the whole first-time wizard ran again - the ask's No re-flipped the switch (a first-run protection turned returning-user trap; the settings it feared losing provably survive the off-drain, _events' own comment). No now POSTS camera_enabled True and lets the user in (wizard optional, rescan button the standing invitation); echo guard intact; boot-suite pins the door both ways (No enables; repaint moves nothing).

- THEATER IDLE-CLOCK DIAGNOSIS, CORRECTED (Oct 20, supersedes 70eb8fa's stated cause): 70eb8fa retired the theater's pointer-stillness conjunct on an "RDP phantom input" theory - WRONG. The owner is on a PHYSICAL desk (no RDP). Re-measured with a detached sampler (90 s + a 30 s cursor-pinpointed run): GetLastInputInfo stuck at 0.00-0.05 s WHILE hands-off, cursor pixel-frozen (-3140,1542) the whole time -> the desk's user32 idle clock is poisoned by ZERO-TRAVEL HID chatter (KVM/USB chain re-reporting the mouse), not a remote channel. powrprof GetIdleTick (the OS's own device-stack idle timer - the one that makes the owner's 5-min display-off work) is NOT exported on this Win11 26100 (probed False), so no userland API hands us the honest answer. THE OUTCOME STANDS, THE REASON CHANGED: the stillness rail must live on an app-owned input-truth pump (low-level hook + 3px dead-zone: real keys and pointer travel count, zero-travel chatter does not; boot = never-input; fail-open to GetLastInputInfo with a word if the hook can't install). 70eb8fa's OTHER half is kept and correct: the player-window plain-veil exemption (the movie never wears a dim veil) and the per-system levels. The retired conjunct + the "veil after" slider are RESTORED on the pump clock in the Oct-20 input-truth wave (see that commit); the owner's clause "the movie theater is not disappearing on mouse or keyboard input" was him noticing the ring never lifted because the clock it would have lifted on never ages. OWN IT: the wrong theory shipped in a commit body and a card tip; both got corrected in-code, and the sampler in Temp\idlewatch*.py is the receipt. The camera's day-long re-open churn now has a candidate cause too (same poisoned clock gating the camera policy) - census it, do not silently redesign.


- THEATER IDLE CLOCK, CASE CLOSED (Oct 20, evening, supersedes fbe751d's named culprit). The zero-travel-chatter MECHANISM was right; the KVM/USB-chain attribution was WRONG, and the physical desk settled it: three owner-run unplug windows (countdown-synchronized, receipts %TEMP%\opencode\convict2.log, convict3.log, padfree.log) exonerated the KVM (clock pinned THROUGH its full USB removal, OS removal-sound heard) and convicted a $10 CH57x-family macropad (VID_1189&PID_8890, '3 media buttons on a dedicated block', direct-attached): a firmware STUCK STATE re-reporting input ~30 Hz with zero travel. The clock AGES LINEARLY (6.5->50.9 s) the second the pad is unplugged and stays honest after replug - the state resets by physical replug. The owner's own probe caught the epilogue nuance: pinning is EPISODIC on this desk (stuck, un-stuck, re-stick candidates), so the honest sentence is 'the pad FALLS INTO a spam state', not 'this desk never ages' - and the 'display off by system power policy' line quoted twice during the investigation matched ZERO times in the logs and the repo (a contaminated memory citing itself as evidence; retracted). The away engine's history vindicates everything: 45/348/12 engages Oct 18/19/20 whenever the clock was honest, and a ~9.5 h dead zone (12:36 PM -> evening) the moment the pad stuck - the founder's symptom, caught end-to-end in the app's own log (depth ceiling ~34.5 h; older all-nighters unreconstructable, though the wake-lock census names candidates: ms-teams 'Screen lock block' holds to 2293 s, opera Video Wake Lock x17, sunshine x4, zoom x1). THE PUMP SHIPS AS INSURANCE, default ON: raw-input-only ears (display.py's ~31 ms LL-hook dispatch quantum law forbade hooks), cumulative 3px-travel dead zone, boot=never-input, fail-open to GetLastInputInfo with ONE dated warning (worst case = today's behavior - the justification for overriding the default-off law, the owner's ruling), opt-out checkbox carrying his verbatim label. The off-phase wake path keeps an injection exemption (stock clock moved while the pump saw ZERO device packets = software injection, real wake; the pad can never fake it because it IS packets). Founder's-bug class, filed where future readers will use it: a silent hardware liar on the desk can freeze every idle rail in every app that trusts user32, for weeks, with nothing in any log saying which gadget - the app-level answer is an app-owned input truth, and the physical answer is the unplug-countdown experiment.


- FURNITURE NEVER WEARS A VEIL (Oct 21, closes the night's 'double veil on DELA' saga). Census verdict: the two admitted full-panel rows were ONE vendor's two windows - OLED Guard Pro's topmost main + its normal-band companion (the 'nvidia overlay.exe' attribution on the second hwnd was a label error; the pair died together at the owner's tray-exit and the desk went instantly uniform, the owner's own experiment convicting). PanelBoss was veiling another dimmer's veil - inter-dimmer stacking, the fourth incident of the per-window-veil overlap class (wallpaper Oct 15, topmost seam 423c9e0, elevated-Teams ghost 4425e59, furniture tonight) - so d0 ships the style+geometry law (full-panel + tool-bit + not-fg = furniture, no veil; the fg exemption is live-witness mandatory: Win11's Progman answers the census WITH the tool bit, ex 0x200080 measured) and d1 makes the owner's freshness ruling permanent: the theater ring is born only over a live holder-window match - stale by FACT, no clocks, no TTL debates; a killed browser's leftover row can never raise the mask again. Gate: SHIP (six hunt items traced; P3 backlog: name the cloaked-holder edge in-comment; parked: content.js pagehide->paused push as the courtesy complement). VERDICT CLASS for the overlap class itself: REFACTOR OWED - one dim layer per panel with holes cut by SetWindowRgn, post-launch; tonight is the class's final patch, not its first. Non-finding, recorded so nobody re-chases it: the 'four orphan veil pieces' were the live app's own windows read against the STUB pid - the stub/child pair means every window-owner pid check must compare against the CHILD or list none.


- PRESENCE-SCOPED TIMERS (Oct 21, the deep-sleep amnesty comes with a witness): the override rows gain the third state 'while present (camera)' - hold applied while the camera VERDICTS a person, handed to the Windows plan the moment it says absent OR gives no verdict (owner's ruling: presence unknown == absent, the fail-into-Windows branch, no silent holding); the 'while present' segment grays (never hides) when detection is off, re-evaluating live through toggle/wake/reveal; the power plan card moved next to detection in the tab order (the dependency now says so in the layout); EVERY seen-to-dark edge speaks one tray balloon per episode, unconditional (owner: 'the dark-camera notification is good all on its own'). Gate round: the multi-camera abstain flicker (owner's desk runs TWO legs - cam0/cam2 - so the reviewer's single-eye exemption was fiction here) fixed by the roster-shuffle guard (a half-spoken round is shuffling, not darkening; a fully-silent roster IS the dark, consent-off drain forfeits the walk explicitly - caught by the verifier at the call site, amended in); guard window sized by roster arithmetic after the live desk measured 69 s against a 70 s design. Pre-existing caught: the display watcher's RegisterRawInputDevices passed the array, not byref (36e3214-era call shape met dd8591f's import-time rebind; owner's desk died at 08:25 and 11:18; pinned by import-order teeth check at the enumwatch suite). OPEN, dispatched same hour: profiles_ui rc=3 Tk-wedge x3 since ~12:06 with VCAMDS in-process (Oct-11 family precedent, blast radius analysis says the wave cannot execute in that suite, cappy adjudicates the repeat) - burn-in proceeds at 75559c7 meanwhile.


- PROFILES_UI RED, ADJUDICATED ENV (Oct 21, cappy R1/R2/R3): rc=3 Tk-wedge = machine-wide NVIDIA Broadcast (VCAMDS) degradation since the 11:50-12:12 native-death wave (WER Id 1000 python.exe->VCRUNTIME140 x4; the Oct-11 zombie-holder class, poison persists >=75 min - waiting is not the remedy, cycling Broadcast is). PROOF the presence wave is innocent: the gate's own green commit (470b38b, scratch tree) runs RED on today's machine, same fingerprint; the delta's seams never execute in the suite (fake fm). SUITE HARDENING QUEUED (~1 coder step, not a blocker): tray-pin after the mutex skip + stub enumerate_cameras for the pin walk (the suite's own Oct-15 IR idiom, 1b509e3), the '120 s' message vs 200 s sleep honesty, UI-PLAN.md Oct-11 section revalidation append. NEW PRE-EXISTING FLAW with a crime scene (punchlist): fault.log 12:47:38 - ZeroDivisionError in camera.py _open_door (int divide by zero) on the degraded-camera boot path; fail-open (watchdog/door budgets hold), fix Thursday-night triage. BURN-IN RITUAL (revalidated): app-down for honest sweeps; rc=3 + >=2 'Failed to destroy the window' => cycle Broadcast (escalation: NVDisplay Container restart), rerun ONCE, never bisect the tip; after any app native death while streaming, cycle BEFORE the next UI sweep; order app-down UI suites BEFORE the burn-in relaunch (boot-enumerate is a live kill site); app-up SKIPs are safe and their destroy-fail line is chronic noise, not a finding.


## Oct 23 - LAUNCH DAY: the 0x133 family, the vendor gate, and restore-means-RESTORED

- FREEZE DOSSIER, CLOSED (captive at the launch bar, captain-debugger verdict ses_e95902348ffe): five bugcheck dumps Oct 17/18/18/19/23 (0x133 DPC_WATCHDOG_VIOLATION, args 0x1/0x1e00), two witnessed freezes (Oct 21 06:57 hang no-dump, Oct 23 08:17 dump) and a third at 12:07 the owner missed (41, BC=0, PowerButton 12:06:43 - hang). NAMED CULPRIT [inferred, high confidence]: nvlddmkm.sys FV 32.0.16.1742 (2026-09-29, single nv_dispsi package, both adapters) - the decisive arg3->module map is ACL-blocked to non-elevated reads; the fingerprint standing in for it: five dumps' arg3 low-endings ..c53c8/..c63c8 across five KASLR bases (module-relative offsets repeat, random pointers do not) + the Oct 9-12 VIDEO_TDR/DXGKRNL hospital week (pre-D6 era) + the app-absent witness (08:17: the process had NO log lines for 15.5 h, zero writes in flight) + the pre-app witness (Sep 19 13:09 bucket, repo's first commit is Oct 8). The 30-s elevation that converts inferred->verified: run pb_dmps_1220\copy.cmd as admin, then pb_parse_mp_1215.ps1 (prints ARG3-LIVES-IN per dump). Owner ruling at the desk overrode the captain's (b) park-from-menu: VENDOR GATE instead - on NVIDIA display drivers the segment is grayed with the verdict in its own label; AMD/Intel get it day one; fail-closed on a dead scan (this wound KILLS - the gate must not trust a desk it cannot prove innocent); hybrid desks count by dGPU (freeze lives in the driver, not the wiring); KVM branch killed by the owner (not in ddc mode). Feature's RETURN protocol (owner, any day): clean-install the newest driver, direct rows to off (DDC fast), AOC stays blackout, run 12 engage/resume cycles - PASS = 12/12 lifts with zero refusal lines, Minidump count stays 5, no new Kernel_133 bucket, no new 41s; ONE freeze ends the branch. (a)-class belt hardening (engage-side row spacing + lift re-ask after the settle window) is NOT shipped today - the gate removes the exposure at the root, and the re-ask would re-enter the stuck-bus path that ate DISPLAY2's three refused writes minutes before today's hang; revisit with the feature's return.
- THE GATE SHIPPED (13a617c): wm/_monitors.py display_vendor_scan() (tri-state adapter walk of EnumDisplayDevicesW, 'nvidia' on any DeviceString match, throw/no-adapters -> fail) + display_vendor_is_nvidia() bool wrapper (packet-1 contract, truth table pinned); UI-only - the engine never learns the gate exists, a config that says off:True on an NVIDIA desk still runs the VCP trio (escape hatch, owner ruling; the preview on such a row still reaches the door too - recorded, the gray is not a kill switch). The gray segment carries ' - this driver blocks it' IN THE LABEL (the owner photographed the verification run and blessed the art - the public README ships that screenshot), DDC_NVIDIA_TIP rides the segment IN PLACE OF the feature tip, GATE_LOG emits one INFO per card build with the three verdict lines (the gray explains itself in %APPDATA%\PanelBoss without a repro), the suffix is display-only (state key, config word, and MODE_BY_LABEL domain stay DDC_TEXT; map at build/sync/click), and the consent cascade must not re-enable it. The SUITE FAKES THE SCAN at module top - determinism law: the probe box's real GPU must not decide label shapes.
- RESTORE MEANS RESTORED (8200501, owner ruling): the capture's minimize bit (iconic - ALREADY recorded per-window at _inspect.py:125; the amendment's 'if not, add' resolved to present) is the whole contract, decided by the capture ALONE: captured-open + now minimized -> SW_RESTORE THEN position (sequence pinned; a position onto an iconic window restores onto a ghost); captured-minimized -> the user's state honored (live captures screen iconic rows out via wanted() - the skip branch is the belt for hand-made/future records); NO BIT (pre-0.3.6 files, profiles/tray records) -> position-only for windows that sit VISIBLE, UNTOUCHED for minimized (the SetWindowPos SHOWWINDOW flag would de-iconify - a guess in code clothing, gate finding 2).
- GATE ROUND (eaf0003, reviewer ses_e956f28b SHIP-WITH-FIXES - both findings were REAL and the suite was blind to both): (1) the label suffix made DDC_TEXT 'leave' vals at BUILD, so the never-reached confession line fired under EVERY gated row on every NVIDIA desk - the exact gray-not-lie class this gate exists for; fixed: the say-line tests the PRE-SWAP offer, pinned BOTH directions (gated+answered says nothing; never-reached still confesses on any desk). (2) _cap None fell through to the flag's SHOWWINDOW and changed the tray/profile path's behavior on minimized windows - ruled skip. Note #3/#4 recorded (wanted() screens iconic captures; preview-rides-the-gate is law, not hole).
- LAUNCH TRANCHE: run_all 56/56 ALL GREEN at eaf0003 (push receipt, the app-down ritual honored); pushed, tag v0.3.6 at eaf0003, MSI 0.3.6 build in flight (dist\PanelBoss-0.3.6-user.msi); release notes + Reddit copy drafted (Temp\opencode\pb_release_notes_1420.md, pb_reddit_1420.md - extension word LOCKED to 'Companion', the store's own; r/Amd named as second home for the day-one-feature angle). Public flip waits on: README screenshot art (owner's three files into assets/screens/), release creation with the MSI attached, default branch -> ui-1c-reskin (415 commits ahead of master, ff-check first), visibility flip, then the Check-for-updates button goes from 'could not check - offline?' to alive ON THE LIVE INSTALL (the owner's desk IS the test: verify before the Reddit post).
- TRANCHE LANDED (same day): msi = dist\PanelBoss-0.3.6-user.msi (111,518,143 B, sha256 c45425c5..447dad, ICE60 lines are heat's boilerplate - same class as the 0.3.5 build); release https://github.com/Nocterrible/panelboss/releases/tag/v0.3.6 published 21:14Z with the asset; master fast-forwarded 8092320..eaf0003 (ancestry PROVEN by merge-base, default branch now ships the launch code); app relaunched 14:14:20 (stub/child twin, the known pair). OPEN: README screenshot art (owner's three files) -> public flip -> Check-for-updates goes alive (test the button on this desk: up-to-date answer expected) -> Reddit (owner's channel).

- LAUNCH-NIGHT DOSSIERS, CLOSED (captain-debugger ses_e934b8365ffe, three files, owner's own experiments as the repro chain): (A) THE DEAF PUMP - RIDEV_REMOVE is PROCESS-wide (hwndTarget MUST be NULL, MSDN) so display.py's away-lift ear teardown (:799) wiped the inputtruth pump's identical (1,2)/(1,6) registration EVERY away cycle; the pump thread stays alive in GetMessageW so no corpse-detection re-arms it, the input clock freezes at 'stillness', the theater ring forms and can never lift (motion AND keys - both usages wiped together). 0x rides the Oct-20 input-truth wave; 0.3.6 merely the first artifact a stranger could buy it in; the gate round (eaf0003) exonerated by git-show. FIX 4d4fc98: RawEars._register factored idempotent + module re_register() (via inputtruth delegator, deviation named in-commit), fired by _release_ears after the remove (display.py:812-815, one-line law comment); deaf-sibling belt (re-register when pump alive-but-silent and the STOCK clock disagrees) CONSCIOUSLY DEFERRED to post-launch - minimal surface at the ship; the long-term shape (one shared ear multiplexing consumers) noted REFACTOR-not-required-tonight. (B) NO-CODE: maximized video window => hole covers the panel => zero ring on the VIDEO'S OWN panel is the law (dimmer.py:287-295 'a panel-covering rect is none'); plain dimming on DELA proven LIVE (six lawful veils incl. the settings self-veil); always-rows do not lift on motion by law; ship-doc line queued for the README theater paragraph. (C) THE WHITE BOX - our own rescue_lost fetched our own MonitorPowerSink (deliberately visible-offscreen at -32000 per the Oct-13 broadcast law; tool-window + no bg brush => Win11 white + caption band => the 'rounded box with a split') back to EXACT primary-center ((1888,1048) = _rescue math, log 'brought back pythonw.exe' x3). FIX 5d16ea3: _proc_info threads the pid it already queried (failure arms -> foreign, conservative), _facts carries 'pid', rescue skips own-pid rows before BOTH bring-back and placement-repair ('the rescue never touches our own windows - every one is parked where we put it'). Owner-visible law-lesson for the fleet: two owners of one OS slot is a COUPLING miss - the in-repo twin is the Oct-21 cross-module argtypes disease; one process, one registration table.
- PARKED, ONE INCIDENT (21:52:47 fault.log): Windows fatal exception ACCESS VIOLATION in pystray _ready -> serialized_image -> PIL WebPImagePlugin IMPORT at tray init - the old instance's death; the autostart belt respawned at 22:12:18 and the profiles stamp proves the restore thread ran (the belt WORKING, not a new class). Watch item: if it re-appears in the log folder, the pystray icon-image path owns the dossier (candidate: PIL plugin-import race at boot under pythonw).
- LAUNCH POSTURE (owner's call with Cappy's costing): same-night ASSET REFRESH - run_all 56/56 app-down at 5d16ea3, reviewer gate -> push -> retag v0.3.6 at the patched tip (zero downloads on the release = in-place asset swap is honest, sha256 re-ledgered) -> MSI rebuild -> relaunch -> the owner's hero screenshots finally clean (the box is gone WITH the fix, not cropped around). Flip public only after the motion-lift repro passes on the owner's desk (video past the rail, mouse moves, ring DROPS).
- ASSET REFRESH A (00:5x): v0.3.6 retagged at 69ea1fe (0 downloads at swap time - in-place honest), msi rebuilt from the patched tree, sha256 66290ee3..c76ad0 (was c45425c5..00447dad) swapped into the release, same URL, run_all ALL GREEN at the refresh tip before push. App relaunched 00:48:45 on the patched tree; the decisive theater-geometry census (owner challenge: the surround-the-video law vs a wrapped browser, bookmark-bar tell) + lift re-verify + box-death confirmation ride Cappy's continuation at the desk. Flip waits for his word and the owner's.

- THE THEATER LAW, FOUR RESTATINGS (owner, Oct 24, 06:5x-07:5x - the statute converged at the desk, logged so no future lane re-litigates it): the night's mid-verdicts (my 'by design', Cappy's maximized-case exoneration, A2's paused-exemption over-reach) all died against the owner's own re-reads; FINAL LAW = (1) the PLAIN dim layer must not veil the window while its video PLAYS - any window state (backgrounded included), outranking [dimmer].always rows; a PAUSED video re-wears the veil (owner explicit: 'a paused video should veil'); a DEAD row returns the veil immediately (no ghost holds the mask, Oct-21 doctrine intact). (2) THE THEATER RING's hole is the VIDEO element (the ring hugs the video; page and the reporting window's chrome wear the darkness with the desk); the Oct-20 window-hole (6e3b84f, owner's own clause that night) survives as [videodim] hole = 'window'. Owner's decisive frame of reference: 'the regular dimmer should not veil playing video content. The movie theater mode should frame the video frame and dim the rest of the browser.' (3) The white-box sighting that started it all was TWO things: MonitorPowerSink rescued center-panel (dossier C, fixed 5d16ea3) and the lawful always-row plain veil over a PAUSED player (now pinned law, 19g); the earlier 'veil wraps the browser' reads were the window-hole ring at the window's edge + YouTube's own dark page - architect's screenshot misreads confessed (the content-darkness was the ring OUTSIDE the window edge, not a veil ON the content). FIX 5b2a862 (one commit): fold-site switch dimmer.py:342-345 (window_rect rides ONLY the 'window' word - compat lane promoted to law, video-hole geometry byte-verbatim from the pre-6e3b84f computation), config.py VIDEODIM_HOLES + DEFAULTS hole='video' + fossil-shaped normalize (warned naming itself), videoeye_test 19c flipped/19c' kept/19g the triple, theater_live pause-gate (a paused row FAILs honestly 'play a video' instead of demanding a lawfully-absent ring), README theater+dimmer paragraphs, _oled.py card prose MOVED TO DATA (TIP_COMP['card']) and TIP_DIM['on'] corrected - it read 'every window you are not using', the one misleading line on the card. KEY DEVIATION FINDING (dev 1): the exemption CONDITION already read the final law (pause-lift lives at videoeye._best_pair:290's door, no fg-conditional exists, always-outrank is structural - the check precedes the membership gate); what was missing was PROOF and honest prose - 'the code already kept the README's promise; this commit makes the promise provable'. run_all ALL GREEN app-down at the patch; verifier PASS, UNCHECKED none; reviewer gate ses_e93073c69ffe pending at this write.
- LAUNCH SEQUENCE, post-gate: push -> retag v0.3.6 (second move, zero-download honesty holds) -> MSI refresh B (new sha, ledger keeps both) -> relaunch -> owner's desk IS the final verifier (play-bg-exempt / paused-returns / ring-hugs-the-frame / motion-lifts - the four-beat demo, screenshots taken DURING it) -> visibility flip + Reddit (pb_reddit copy already reflects the gate; add the ring-hugs-the-video line if the README sentence made the release notes stale).
- ASSET REFRESH B (theater law, 08:4x): v0.3.6 retagged at 48465aa, msi rebuilt (sha256 915f3d1b..de9ed4; lineage c45425c5 -> 66290ee3 -> 915f3d1b, all app-down gauntlets green at each tip), release notes body refreshed to the hug-the-video law at the same URL. App relaunched on the final tree; owner's desk = final verifier (four-beat demo); then screenshots -> public flip.

- REFRESH C CONTENT (pre-gate ledger, 02:5x): the profiles dossier verdict was CLEAN-BY-TIME (nothing lost, 'reg' present both sides, mtime unmoved at both --autostart relaunches, write-on-apply ALREADY held, the updates lead exonerated by reflog+registry+content) - the disease was the picker's once-at-build strict-fingerprint opening frozen on a mid-mode-landing desk read (the module's OWN docstring prescribed the identity matcher for exactly this; the UI was the one consumer that forgot), and the fix rides refresh C: by-identity opening + SELF-HEAL on desk settle (never stomping a deliberate pick) + the two owner LAWS made structural: fossils (a rotted entry is kept aside verbatim, never folded away by the next save) and BACKUP-ON-UPDATE (profiles+config copied to %LOCALAPPDATA%\PanelBoss\update\*.bak before any apply, both install kinds, path spoken in the UI line); write-on-apply pinned as a permanent regression (the fear-killer). FIX RODE A MISROUTE: the amendment packet reached the lane as an away-handback pin (d9f3bc7 lands the PIN for the noon (a)-class re-ask dossier anyway - its belt law was already at HEAD from 27c1a2a, the commit pins the leaving-moment brightness hand-back + README honesty; net gain, honest deviation report), the profiles packet re-sent and executing now.
- PRE-EXISTING CLOBBER BUG FOUND BY THE PINS (config.py normalize_videodim, ships since the row-table wave): the per-row loop REBOUND the section's own on/level names - a LAST-ROW default could silently CONSENT the theater (breaking the default-OFF root the owner's consent law rests on) and the global level could fold None - fixed (ron/rlevel) and pinned FOUR ways incl. two explicit clobber guards. Launch-grade catch: it predates tonight entirely; the fold-precedence pins are the class of test that finds it, and 'name the real runner' earns its keep (Cappy's packet named pytest/tests/ - fiction on this box; run_all.ps1 is the law, gate-verified 56/56 twice app-down).
- UI PAIR LANDED (bd91da6): theater's global veil-level slider RETIRED (absence-pinned widget-wise, [videodim] level survives as silent fallback, enroll rows carry their own levels - the card prose moved to honest pinned data: 'Each enrolled panel dims to its own level; there is no global knob.'); THE PUMP moved to the Detection tab's Timers card (it is an idle-clock policy, every timer reads it), VERBATIM label byte-identical across the move (ast-exact diff as the proof), relaunch + deaf-pump caveats as TIPS['pump'] data, same [dimmer] input_pump key. profiles_ui rc on the FIRST sweep = the known VCAM native-teardown env class (isolated re-run green, second full sweep ALL GREEN - the documented ritual, not a flake to forgive twice).
- ASSET REFRESH C (03:3x): v0.3.6 retagged at 546e0d3 (gate round of the full C range), msi rebuilt - sha256 b4a3ec510a9c2cca68b5155a52f348ba8efb833292e9b6f665db5bf9168887e6 - swapped at the same URL. Lineage: c45425c5 (noon) -> 66290ee3 (pump/box) -> 915f3d1b (theater law) -> b4a3ec510a9c2cca68b5155a52f348ba8efb833292e9b6f665db5bf9168887e6 (C: pump relocation, per-monitor theater, profiles identity+self-heal, fossils+backup+clobber laws). ALL GREEN gauntlet at the tag tip app-down. Owner's hands: four-beat demo, screenshots -> assets/screens -> README art, public flip.

- DOSSIER E (launch day, afternoon, owner at the desk): 'restore my windows still doesn't un-minimize - it's waiting 30 seconds and attempting to run the app for minimized windows... leads to a false error that discord isn't responding to the launcher' + the law 'the launch delay should be 0 if the restore is run manually, the delay timer should only apply at boot'. ROOT [verified by the fix's pins]: the pin walker's live-set came from wm.list_windows() -> wanted() - whose iconic clause (the census law that keeps minimized rows out of the PLAIN-VEIL and snapshot walks) made a minimized Discord INVISIBLE to seat matching - no hits -> open-if-missing -> exe re-run -> single-instance silence -> the patience timer narrated a death that never happened. The morning's _restore._move law (restore=to-captured-state) was the same law in the OTHER path; today's fix unifies the doctrine: A MINIMIZED WINDOW IS PRESENT. 720cfa2: wanted() split (_wanted_body + the iconic clause, re-askable predicate), list_windows(include_minimized=kwarg, every existing caller unchanged), wm.unminimize (guard+SW_RESTORE, ok/gone), the walker restores-then-places (zoomed dance rides place), PATIENCE IS A BOOT GRACE ONLY (relaunch(boot=login); manual waits nothing; pin() default 30->0, WAIT_CHOICES gains 0, editor clamps/badges follow), README clause, four pins (restored-not-relaunched; manual no-delay; boot rail waits 360 through the fake clock; the RESTORE->pos->MAXIMIZE sequence in layout 3e's kin). Deviation honest: a manual 'open it' whose launch truly produces nothing now reports through the no_shows dialog channel, not a timed claim - nothing to time out on at zero patience. run_all 56/56 app-down at the tip; verifier leg-4 PASS; reviewer gate ses_e90527d68ffe at this write.
- FIXER ON THE BENCH (owner, same hour): 'we're also going to need another fixer pass for the UI - it's drawing slowly still' - INVOCATION FILED AND HELD ('hold off on fixer though'): the render-slow class (the 688 ms 12-row rebuild, the double-buffer, the CTk canvas costs) waits its owner's word; every prior ruling in the render path is fair game for that pass (cards, rebuilders, tooltips machinery, even the widget family) - the sledgehammer law says the fleet pays for DISSENT there, not for agreement with this week's designs.
