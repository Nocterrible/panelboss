# RC package: PanelBoss ui-1c-reskin fix wave (45fcc38..e8ab8ff)

## Intent
Pre-release audit of 13 batches (two-channel: deep pass + fallback/collation
where applicable) produced ~42 findings, all patch-scale, consolidated to
six themed commits. This RC closes every HIGH and every MED from the audit
punch list; BACKLOG items are listed and consciously deferred. The app is an
offline Windows tray presence-monitor: no network surface, HKCU-only registry,
no shell interpolation of user data. The threat model is the user's own
hand-edits and driver misbehavior, which is what the config-boundary and
daemon-confession themes serve.

## Commits (11, chronological)
- 9563190  config boundary: Path.home(), deepcopy merge (kills 6 confirmed
           DEFAULTS-alias mutation sites), non-dict-section guard,
           NORMALIZE_RULES table (12 rules; every failure -> stock + ONE
           named warning), write_config single-writer (RLock + snapshot +
           pid-unique tmp). Verdict SHIP (Infernix gate).
- 51f8253  state re-arm pair (the two 2-channel-confirmed HIGHs): gate
           release re-arms next_poll (unpause/snooze-freeze); released
           eyes cast no verdicts (stale _vote_index + _round cleared at
           _release_camera head - all release paths funnel there);
           blind eyes excluded from AND-round want-set; both event drains
           guard unpack + handler + unknown-action confession.
           Verdict SHIP.
- f3061c8  camid wizard: PnP query off the tk thread, bounded unhide-all
           reload ladder (8x500ms, single-flight), post-destroy-safe BUSY
           via pump-marshaled flag, unhealthy-PnP candidates skipped with
           counted note, _shell rebuild destroys stale-dress wizard.
           Verdict SHIP.
- 13e5465  camid gate cosmetics (disclosed fold, no behavior).
- 1481889  display watcher self-confession: null lParam refused BEFORE
           ctypes from_address (native 0xC0000005, no except can catch -
           probe-measured), per-message fail-open, watcher global settled
           to None on every run() exit (startup-failure path lands in the
           state machine's designed assume-on), HWND_MESSAGE measured -3,
           RegisterPowerSettingNotification pinned. Verdict SHIP.
- bf668f4  tray pump post-run confession (pystray 0.19.5 swallows pump
           exceptions and NIM_DELETEs the icon - silent icon death was the
           audit's FAIL-verdict HIGH): exit-without-quit is fatal-loud
           (log.error + self-dismissing box + monitor quit); cli
           timeout_notice extraction (slot order from the runtime-fixed
           twin) + dead-window box. Verdict SHIP.
- d7ef04f  profiles load validation (junk rows die at load with named
           warnings; round-trip of legit writer shapes verified by gate),
           _SAVE_LOCK, combined-mode pin defaults, splash theft closed in
           pin_hits (serves both apply and relaunch paths). Verdict SHIP.
- cd16772  login-shape fixup: took is the REAL per-app dict (writer:
           took[who]=seconds at apply :921); validation may reject rot,
           never the writer's shape; suite law encoded BOTH ways.
           Verdict SHIP.
- 1f1320c  UI worker confessions (5 sites to the _gaming model): apply
           re-entrancy flag + guarded marshal + mid-apply repaint refusal;
           restore picker from in-memory store + "(gone)" rendering;
           assistant switch generation contract; autostart single-flight;
           overrides after() guards. Verdict SHIP-WITH-FIXES -> fix below.
- 37bc169  gate finding 1 fix: dead autostart worker re-enables its own
           switch (verdict on the fix: SHIP, second gate).
- d6162e2  twelve gate-nit items: unveil-timer tracking (kills the
           rebuild-expose race), sync_region coalescing (kills the
           ~400-after repaint burst), veil-before-map + update_idletasks,
           pinned-tip persistence, skin-fallback warning, preview lease
           honesty on rebuild, cameras-resync on identity save, apply
           button refs, window-size dedupe truth, dead assignment.
           Verdict SHIP.
- f8a74f8  wm: apply_layout per-device refusal truth (empty-DEVMODEW base
           refused before staging - the audit's measured -2 illusion),
           refused-list surfaces in the (bool, lines) contract; taskbar+
           display handle-trap pin sweep. Verdict SHIP-WITH-FIXES -> fix
           below.
- e8ab8ff  gate follow-through: taskbar GetWindowRect slot2 POINTER(wm.
           RECT) -> c_void_p (the shared-u32 poison _winapi.py documents
           as measured; layout_test missed it by not importing taskbar;
           probe-verified the gate's exact failure order fixed);
           profiles_test fake rewritten to answer like a real driver
           (nonzero rc + filled mode; the old rc-0 "says nothing" IS the
           powered-off shape the refusal law correctly rejects).

## Evidence
- Diff: C:\Users\user\AppData\Local\Temp\opencode\rc-fixwave.patch
  (32 files, +2011/-196, 45fcc38..e8ab8ff)
- Punch list with per-finding disposition: AUDIT-PUNCHLIST.md (repo root;
  the deferred BACKLOG is itemized there with file:line + one-line fixes)
- Gauntlet: scripts/run_all.ps1 consolidated rc=0, "ALL GREEN (complete)"
  - all 27 suites, window sections REAL (app held stopped), including
  guard_test (double-launch mutex) and the three new suites
  (config_norm_test, pinlifecycle_test) and extended hold/camid suites.
  Log: %LOCALAPPDATA%\Temp\opencode\gauntlet-final-2311.log
- Every lane delivery carries a VERIFIER child receipt (sessions recorded
  in each lane report); every themed commit passed the synchronous
  Infernix reviewer gate (seat disclosures in verdicts; reviewer lane
  itself died at emit 3x tonight and every verdict was recovered by
  continuation poke - infra, not findings).

## Honest notes
- The 13-batch audit's own misses: it prescribed a wrong HWND_MESSAGE value
  (corrected by measurement) and blessed a szExeFile false positive
  (reverted); the taskbar RECT relapse was caught by the gate, and the
  EnumDisplaySettingsW truthiness question was settled by live probe
  (success answers nonzero AND filled), not by the docstring.
- Single-user offline app; the ko-fi button is the only URL, opened via
  webbrowser, never fetched. Registry writes HKCU Run only. No subprocess
  of user-editable strings (ShellExecuteW with pinned argtypes is the
  launch verb).
- Consciously deferred (documented BACKLOG in the punch list): _events.py
  size-law split (300-line boundary), queue-marshaled cross-thread afters
  in overrides (confession shipped instead), preview-lease dead-handle
  eviction, and 15 other LOW/INFO items with fix lines.
