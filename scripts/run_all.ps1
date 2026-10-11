# Full suite runner: powershell -File scripts\run_all.ps1
# Honest green requires the app STOPPED (the UI suites skip their
# window sections while a live instance holds the mutex, and say so
# loudly in their logs). Logs land beside the scripts; ALL GREEN is
# the verdict line.
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
    'gaming_test.py', 'gaming_watch_test.py', 'power_plan_test.py',
    'tweaks_test.py', 'config_writer_test.py', 'gaming_ui_test.py',
    'mode_edit_test.py', 'taskbar_test.py', 'profiles_ui_test.py'
$dir = Join-Path $root "scripts"
$fail = 0
foreach ($s in $suites) {
    & $py (Join-Path $dir $s) *> (Join-Path $dir ('suite_' + $s + '.log'))
    $rc = $LASTEXITCODE
    Write-Output ($s + ' rc=' + $rc)
    if ($rc -ne 0) { $fail = 1 }
}
Write-Output ('ALL GREEN: ' + ($fail -eq 0))
exit $fail
