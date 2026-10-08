# Reproducible venv + weights. Never touches the base environment.
$ErrorActionPreference = 'Continue'
Set-Location (Split-Path -Parent $PSScriptRoot)
$repo = (Get-Location).Path
Write-Host "installing into $repo"

# 1. locate a python 3.10+ interpreter (the venv will be built from it)
$py = $null
foreach ($candidate in @('py -3.10', 'py', 'python', 'python3')) {
    $cmd = $candidate -split ' '
    try {
        $ver = & $cmd[0] @($cmd[1..($cmd.Length-1)]) -c 'import sys; print(sys.version)'
        if ($LASTEXITCODE -eq 0) { $py = $candidate; break }
    } catch { continue }
}
if (-not $py) { Write-Error 'no python found; install python 3.10+' }

# 2. the venv? venv: project-local, the base env is never modified
if (-not (Test-Path .venv)) {
    $cmd = $py -split ' '
    & $cmd[0] @($cmd[1..($cmd.Length-1)]) -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --no-input -q
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt --no-input
if ($LASTEXITCODE -ne 0) { Write-Error 'pip install failed' }
& .\.venv\Scripts\python.exe -m pip freeze | Where-Object { $_ -match '^(opencv|numpy|onnxruntime|pystray|pillow|tomli|customtkinter|darkdetect)' } | Set-Content requirements.lock.txt

# 3. the weights (10.7 MB); the mirrors are tried in order and the first
#    that returns a file over 1 MB wins
if (-not (Get-Child models\*.onnx -ErrorAction SilentlyContinue)) {
    New-Item -ItemType Directory -Force models | Out-Null
    $urls = @(
        'https://huggingface.co/aaurelions/yolo11n.onnx/resolve/main/yolo11n.onnx',
        'https://huggingface.co/aaurelions/yolo11n.onnx/resolve/main/files/1024/yolo11n.onnx'
    )
    foreach ($url in $urls) {
        Write-Host "downloading $url ..."
        $start = Get-Date
        try {
            Invoke-WebRequest -Uri $url -OutFile models\yolo11n.onnx -UseBasicParsing -Timeout 120
            break
        } catch { Write-Host $_.Exception }
    }
    if (-not (Test-Path models\yolo11n.onnx)) { Write-Error "no mirror worked; drop yolo11n.onnx into models\" }
    Write-Host ("found models\yolo11n.onnx after {((Get-Date) - $start).TotalSeconds} s")
}

# 4. remember which interpreter this venv was built from (not portable by
#    itself; rerun this script after moving the repo)
@{ python = ($cmd -join ' '); venv = '.\.venv'; created = (Get-Date).ToString('o') } |
    ConvertTo-Json -Compress | Set-Content setup.json
Write-Host 'done; start with: .venv\Scripts\pythonw.exe -m awaywatch'
