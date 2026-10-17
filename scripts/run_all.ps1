# Full suite runner: powershell -File scripts\run_all.ps1
# Honest green requires the app STOPPED. The UI suites skip their window
# sections while a live instance holds the mutex, and guard_test skips
# while ANY live instance holds it - and the runner now READS those
# markers back out of the per-suite logs instead of trusting a bare rc:
# a green sweep that skipped every UI law is DEGRADED, not ALL GREEN.
#
# Exit-code table (the full contract, Oct 12 audit):
#   0  ALL GREEN, complete  - every suite passed, no section skipped
#   1  a suite FAILED (rc=1) - see the rc lines and the suite log
#   2  a suite FILE is missing (python's own rc on a bad path)
#   3  a window suite's HARD KILL fired (rc=3: the Tk loop wedged -
#      gaming_ui_test, power_assistant_test, profiles_ui_test share it)
#   4  DEGRADED green  - everything that ran passed, but at least one
#      suite printed "SKIP window section" or "SKIP guard"
# Priority when several apply: 1 > 2 > 3 > 4; a real failure is never
# downgraded into a skip verdict. Logs land beside the scripts.
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    # the fossil venv dir name; find the real Scripts\python.exe
    $py = (Get-ChildItem $root -Directory -Force |
        Where-Object { Test-Path (Join-Path $_.FullName "Scripts\python.exe") } |
        Select-Object -First 1 | ForEach-Object { Join-Path $_.FullName "Scripts\python.exe" })
}
$suites = 'startup_test.py', 'hold_test.py', 'motion_test.py',
    'power_task_test.py', 'power_assistant_test.py', 'unknown_state_test.py',
    'wake_burst_test.py', 'multi_cam_test.py', 'camera_policy_test.py',
    'visible_test.py', 'layout_test.py', 'profiles_test.py', 'hdr_away_test.py',
    'hider_test.py', 'window_boot_test.py', 'jog_test.py', 'dimmer_test.py', 'overlay_order_test.py', 'awaymode_test.py',
    'gaming_test.py', 'gaming_watch_test.py', 'power_plan_test.py',
    'tweaks_test.py', 'config_writer_test.py', 'gaming_ui_test.py',
    'mode_edit_test.py', 'taskbar_test.py', 'profiles_ui_test.py',
    'asyncopen_test.py', 'blackvote_test.py', 'veil_test.py',
    'camid_test.py', 'assign_test.py', 'camdiag_test.py', 'guard_test.py', 'config_norm_test.py',
    'virgin_boot_test.py', 'hdrwatch_test.py', 'hdrwake_test.py',
    'pinlifecycle_test.py', 'companions_test.py', 'camcore_probe.py',
    'companion_test.py',            # the LIVE companion pins (47+):
                                    # the plural file above is the Oct-12
                                    # frame-shape probe, NOT this suite -
                                    # the name collision hid the pin
                                    # family from the gate all day Oct 16
    'videoeye_test.py',             # the eye's fold/law/FSM pins (32+),
                                    # same exclusion family
    'enumwatch_test.py',            # wave C: the enumeration's join
                                    # watchdog - a wedged door may not
                                    # eat the board (offline fake cv2)
    'w2c_probe.py', 'w3b_probe.py', 'w3c_probe.py',
    'daemon_confess_probe.py',
    'ctkimg_probe.py',                # the wizard-preview freeze's
                                      # net (UAT find, Oct 13): a
                                      # probe that runs only when
                                      # remembered is a rumor
    'switch_geom_probe.py'            # the knob-lie family's geometry
                                      # pin (owner's bar-was-on catch,
                                      # Oct 13 night): truth switches
                                      # repaint after they know their
                                      # size; app-up compatible
$dir = Join-Path $root "scripts"
# ledger 16: the log must be attributable - tip stamp at the head,
# and DIRTY when the tested worktree differs from it (a stamp that
# names HEAD while the tree carries uncommitted edits lets a receipt
# cite a commit that was never run)
$_tip = (& git -C $root rev-parse --short HEAD 2>$null)
$_dirty = (& git -C $root status --porcelain 2>$null)
Write-Output ("runner @ " + (Get-Date -Format o) + " tip " + $_tip +
    $(if ($_dirty) { " (DIRTY worktree)" } else { " (clean)" }))
$fail = 0
$miss = 0
$hard = 0
$degraded = 0
foreach ($s in $suites) {
    $log = Join-Path $dir ('suite_' + $s + '.log')
    & $py (Join-Path $dir $s) *> $log
    $rc = $LASTEXITCODE
    Write-Output ($s + ' rc=' + $rc)
    if ($rc -eq 1) { $fail = 1 }
    elseif ($rc -eq 2) { $miss = 1 }
    elseif ($rc -eq 3) { $hard = 1 }
    elseif ($rc -ne 0) { $fail = 1 }    # an unknown rc is a failure
    $txt = ''
    if (Test-Path $log) {
        $txt = [string](Get-Content -Raw -ErrorAction SilentlyContinue $log)
    }
    if ($txt -match 'SKIP window section') {
        Write-Output ($s + ' DEGRADED (window section skipped)')
        $degraded = 1
    }
    if ($txt -match 'SKIP guard') {
        Write-Output ($s + ' DEGRADED (guard section skipped)')
        $degraded = 1
    }
}
if ($fail) { Write-Output 'FAILED: at least one suite rc=1'; exit 1 }
if ($miss) { Write-Output 'FAILED: a suite file is missing (rc=2)'; exit 2 }
if ($hard) { Write-Output 'FAILED: a window suite hard-killed (rc=3)'; exit 3 }
if ($degraded) {
    Write-Output 'DEGRADED: ALL GREEN but sections were skipped'
    exit 4
}
Write-Output 'ALL GREEN (complete)'
exit 0
