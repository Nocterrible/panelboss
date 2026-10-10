param(
    [ValidateSet('install', 'uninstall', 'status')]
    [string]$Action = 'install'
)

# Task Scheduler logon task; the full script path because the task
# runner does not know where the repo lives
$repo = (Split-Path -Parent $PSScriptRoot)
$task = 'ICU-PresenceDetector'
$pythonw = Join-Path $repo '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $pythonw)) {
    Write-Error 'run scripts\setup.ps1 first'
}
$runpy = Join-Path $repo 'run.py'

switch ($Action) {
    'install' {
        schtasks /Create /F /SC ONLOGON /TN $task `
            /TR "$pythonw `"$runpy`" --autostart" | Out-Null
        if ($LASTEXITCODE -ne 0) { Write-Error 'schtasks failed' }
        Write-Host "installed logon task: $pythonw $runpy --autostart"
    }
    'uninstall' {
        schtasks /Delete /F /TN $task | Out-Null
        Write-Host 'removed'
    }
    'status' {
        schtasks /Query /TN $task | Where-Object State | Format-List |
            Select-Object -First 1 | Out-String | Write-Host
    }
}
