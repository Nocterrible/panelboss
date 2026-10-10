# Release build: one folder + one zip, next to the repo.
#
#   powershell -NoProfile -File scripts\build_release.ps1
#
# Produces  dist\PanelBoss\  (run the exe inside) and
#           dist\PanelBoss-<commit>.zip  (the release).
# The zip drops beside the exe's own folder; config and logs stay in
# %APPDATA%\PanelBoss for BOTH the repo and the exe world.

$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$exe = 'PanelBoss'
$py = Join-Path $repo '.venv\Scripts\python.exe'

Write-Output 'building exe (minutes: onnxruntime + opencv ride along)'
& $py -m PyInstaller --noconfirm --clean --windowed --name $exe `
    --distpath (Join-Path $repo 'dist') `
    --workpath (Join-Path $repo 'build') `
    --collect-all customtkinter `
    --collect-binaries onnxruntime `
    --collect-all pystray `
    --hidden-import whircam `
    --collect-all winrt `
    --exclude-module pytest `
    --exclude-module setuptools `
    --exclude-module pip `
    (Join-Path $repo 'run_exe.py')
if ($LASTEXITCODE -ne 0) { Write-Output "pyinstaller failed ($LASTEXITCODE)"; exit $LASTEXITCODE }

# the models folder ships OUTSIDE _internal so users can drop their
# own *.onnx there; inference.py (frozen) prefers exe-dir\models
$models = Join-Path $repo 'models'
$target = Join-Path $repo ('dist\' + $exe + '\models')
if (Test-Path $models) {
    New-Item $target -ItemType Directory -Force | Out-Null
    Copy-Item (Join-Path $models '*.onnx') $target -Force -ErrorAction SilentlyContinue
}

$stamp = (& git -C $repo rev-parse --short HEAD) 2>$null
if ($stamp) { $zipName = ($exe + '-' + $stamp + '.zip') } else { $zipName = ($exe + '.zip') }
$zip = Join-Path $repo ('dist\' + $zipName)
Compress-Archive -Path (Join-Path $repo ('dist\' + $exe)) -Destination $zip -Force
Write-Output ('release: ' + $zip)
