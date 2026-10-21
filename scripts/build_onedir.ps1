# The shared onedir step: PyInstaller + the models drop, ONE flag
# list for both the zip release (build_release.ps1) and the per-user
# MSI (build_msi.ps1). Dot-source and call Invoke-OnedirBuild; the
# two callers may add their own artifacts (zip, candle/light) but
# NEITHER may re-inline these flags - flag drift between the two
# pipelines is the trap this file exists to kill (MSI wave, Oct 21).
#
#   . (Join-Path $PSScriptRoot 'build_onedir.ps1')
#   Invoke-OnedirBuild -repo $repo          # -> dist\PanelBoss\
#
# The models folder ships OUTSIDE _internal so users can drop their
# own *.onnx there; inference.py (frozen) prefers exe-dir\models.

function Invoke-OnedirBuild {
    param(
        [Parameter(Mandatory = $true)][string]$repo,
        [string]$exe = 'PanelBoss'
    )
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
    $models = Join-Path $repo 'models'
    $target = Join-Path $repo ('dist\' + $exe + '\models')
    if (Test-Path $models) {
        New-Item $target -ItemType Directory -Force | Out-Null
        Copy-Item (Join-Path $models '*.onnx') $target -Force -ErrorAction SilentlyContinue
    }
    Write-Output ('onedir ready: ' + (Join-Path $repo ('dist\' + $exe)))
}
