# Taskbar hover/autohide on Win11 24H2+ — findings (Oct 2026)

Goal: "show only while hovered, vanish near-instantly, sane on
multi-monitor" WITHOUT injecting DLLs into explorer.

## What is real

* `SHAppBarMessage` **still works on the XAML taskbar (24H2-26H2)**,
  live, no restart — this is how several maintained 2026 tools set
  `ABS_AUTOHIDE`. The Settings toggle itself lives in the
  `HKCU\...\Explorer\StuckRects3` opaque blob (+`MMStuckRects3` per
  monitor) and needs an explorer restart — byte-poking it is a
  version roulette; do NOT do it. `ABM_SETSTATE` is the live path.
* `ABM_SETSTATE(ABS_AUTOHIDE|ABS_ALWAYSONTOP)` against
  `Shell_TrayWnd` (hwnd barely matters) sets the flag; re-assert
  after every explorer restart (`FindWindow` again — handles die
  with the shell; watch the `TaskbarCreated` broadcast or poll).
* **The "stuck open" jank is a focus gate**: native
  `PermitAutoHide()` refuses while the taskbar/flyout owns the
  foreground or a notification force-showed it. Windhawk's fix,
  externally: `SetForegroundWindow(Progman)` after our own toggles.
* Show/hide delays are explorer `SetTimer`s on the tray windows —
  id **2 = hide (500 ms default), id 3 = unhide (50 ms)**; no
  registry knob — but **`PostMessage(trayWnd, WM_TIMER, 3|2, 0)`
  works from an external process**. Proven hover-forcing scheme:
  20 ms cursor poll; when pointer is at a monitor edge and the bar
  is still out of view: `PostMessage(WM_TIMER, 3)` retried every
  150 ms (single posts get swallowed by fullscreen foreground
  apps); when the pointer leaves the bar rect: post id 2 once.
* There is no native per-monitor autohide (one global flag); no
  force-hide bit in ABM; "hides only when covered" is NOT native
  (a mod adds it) — native hides even on an empty desk.
* `WM_USER+0x1CA` (wParam 3=get / 4=set) is the private in-proc
  toggle message; cross-process send is *probably* fine but
  unproven — probe before relying on it.
* Coexistence: detect Windhawk mods / ExplorerPatcher
  (`ep_taskbar.*` modules in the tray process) — they intercept the
  same surfaces; log their presence, do not fight them.

## Build sketch (taskbar.py)

thread loop 20 ms:
1. assert flag: `ABM_GETSTATE` -> if AUTOHIDE missing (and user
   wants it): `ABM_SETSTATE(ABS_AUTOHIDE|existing)` +
   `SetForegroundWindow(Progman)`;
2. edge: cursor within N px of a bar's monitor edge + bar rect
   mostly offscreen -> post id 3, retry 150 ms;
3. leave: cursor fully outside bar rect + bar visible -> post id 2;
4. re-find tray windows every `TaskbarCreated`/on FindWindow fail;
5. fail open; kill switch off = post nothing, restore original flag
   (save/restore doctrine).

Sources: docs SHAppBarMessage; EP dllmain.c (ToggleTaskbarAutohide,
MMStuckRects legacy redirect); Windhawk mods
taskbar-autohide-in-context (26H2-tested), -per-monitor,
-instant-show (timer ids/delays, PostMessage retry), -when-
maximized (0x1CA, PermitAutoHide, ViewCoordinator); Old New Thing
("third-party ABM_SETSTATE makes it go and stay"); StartAllBack
changelog (shy autohide exists closed-source).

## Measured HERE (Oct 2026, taskbar_probe + bisect)

* 3 tray windows exist (one per monitor: Shell_TrayWnd + 2x
  Shell_SecondaryTrayWnd) - our wm.monitors() maps them by rect.
* **`SHAppBarMessage` from THIS process family access-violates
  reading 0x4** (every struct size tried: 36/40/44; zero and real
  hwnd alike). The export exists, but external callers on this
  build cannot use GETSTATE/GETTASKBARPOS. The mods that use it run
  INSIDE explorer. Plan adapts: read state from
  `StuckRects3`/`MMStuckRects3` bytes (read-only), write flags via
  the private `WM_USER+0x1CA` (wParam 4=set) with a probe, hover
  force via plain `PostMessage(WM_TIMER 2/3)` (never crashes -
  worst case it is ignored). ABM remains an optional bonus if
  26H2's XAML taskbar ever re-parks the legacy handler.
* `SendMessageTimeout(0x400+0x1CA, 3=get)` returned rc 0/value
  None in practice (message not served, not a crash): safe to send
  from outside, but the get/set semantics for external callers are
  UNPROVEN - the SET side must be A/B'd later with the tray app
  off, and the honest default plan is read-reg-bytes +
  PostMessage-timers only.
