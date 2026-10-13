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

## Fix wave status (Oct 13)
LANDED+GATED: config 9563190 SHIP; state 51f8253 SHIP; camid f3061c8+13e5465
SHIP; display 1481889 + tray/cli bf668f4 SHIP; profiles d7ef04f+cd16772 SHIP
(cd16772 = architect fix: login.took is the REAL per-app dict - validation may
reject rot, never the writer's shape; the dictated float-both rule would have
dropped live data daily); ui-workers 1f1320c SHIP-WITH-FIXES - gate finding 1
(_general dead-worker never re-enabled the switch) FIXED in the tree, commit
waiting on the C6b lane (it holds the same file set; no split-file commits).
Gate notes parked for next touch: _prof_apply flag-up ordering one statement
optimistic (wedge needs an already-dying pane - acceptable as disclosed);
_power except-path can transiently show overrides-button state ahead of the
queued truth (cosmetic, self-heals on truth land).
C6a (wm/taskbar/display pinning + apply_layout rc truth) and C6b (twelve tab-
lifecycle nits incl. C5b's button-ref closure) in flight. Lane tax for the
record: 7 emit-deaths (all cured by poke), 2 C5 zero-write deaths (cured by
SPLIT per the three dials), 1 amend entanglement (self-inflicted, self-
forensicked) - zero lost findings, zero re-designs.
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
  into the InstanceId keying wave.
- BACKLOG LOW _camedit.py:77-100 — wizard hide/label saves never re-fire
  _apply_cameras: "(hidden)" badges stale until manual rescan. Push a
  "cameras" ui_event after the identity write.
- BACKLOG LOW _shell.py:232 + _preview.py:92 — skin rebuild resets live-
  preview switch to off while frames may land ~2.5s more (UI claims off).
  Restore pre-rebuild selection or enqueue preview 0 at rebuild start.
- INFO (confirmed, feeds the same wave) _events.py:244-253 — the camera_
  identity handler's `labels[inst]=` mutates the DEFAULTS alias when the
  file lacks [camera.labels] (wizard Save triggers): copy the container on
  entry. Sixth site, same one fix (deepcopy at merge).

## widgets/text/constants/camid (deep, PASS - no HIGH; module-state and
import sweeps clean; _constants pure)
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

## In flight / queued
- profiles.py monolith (deep, in flight).
- tray shell: tray/taskbar/display (deep, in flight, brief-thoughts clause).
- UI trio last: shell/runtime/scroll/widgets/text/constants/camid; aux tabs;
  profiles+power tabs (pre-split ≤4-5 files each).
