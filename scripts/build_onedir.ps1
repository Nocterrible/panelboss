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
    # MSVCP140!+0x12f58 c0000005 loading onnxruntime_pybind11_state.pyd
    # against the split 14.36/14.51 set collected from the JRE bin,
    # 2026-10-22 autopsy: the JRE dirs on PATH ship 14.36 CRTs and the
    # collection scans PATH - strip them before the build inherits them.
    # (False-positive risk - a PATH dir whose name carries 'jre' as a
    # substring - is accepted for THIS build: python, git and the WiX
    # tools all arrive by absolute path, so no stripped entry is ever
    # needed by the build itself.)
    $env:Path = ($env:Path -split ';' |
        Where-Object { $_ -notmatch 'Adoptium|Oracle|[Jj]re' }) -join ';'
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
    # the one process slot makes same-name roulette the wound; the
    # re-pin makes provenance a build FACT, not a PATH accident: every
    # same-named CRT file under _internal (recursive) is overwritten
    # from System32's matched 14.51 set; hash-named private sets
    # (numpy.libs et al.) are name-isolated and stay untouched.
    $crt = Join-Path (Join-Path $repo 'dist') ($exe + '\_internal')
    foreach ($n in 'msvcp140.dll', 'MSVCP140_1.dll', 'vcruntime140.dll', 'vcruntime140_1.dll') {
        $src = Join-Path ([Environment]::SystemDirectory) $n
        Get-ChildItem -Path $crt -Recurse -File -Filter $n |
            ForEach-Object {
                Copy-Item -Path $src -Destination $_.FullName -Force
                Write-Output ('crt re-pin: ' + $_.FullName)
            }
    }
    $models = Join-Path $repo 'models'
    $target = Join-Path $repo ('dist\' + $exe + '\models')
    if (Test-Path $models) {
        New-Item $target -ItemType Directory -Force | Out-Null
        Copy-Item (Join-Path $models '*.onnx') $target -Force -ErrorAction SilentlyContinue
    }
    # THE HOST RIDES THE BUNDLE (final gate, Oct 25, blocker 3): the
    # card's "install the helper" button runs install_host.ps1 AT
    # RUNTIME, and the frozen app resolves it BESIDE the exe (nmhost's
    # _app_root - the same user-visible, exe-adjacent convention as the
    # models drop above). The exe ships built: the ps1's build is
    # guarded (Test-Path), so a bundled install needs no venv and no
    # PyInstaller to register. The build/dist scratch dirs of
    # extension\host stay home; the tracked panelboss-host.exe (force-
    # added Oct 25, ~6.5 MB) makes this copy reproducible from a clone.
    $hsrc = Join-Path $repo 'extension\host'
    $hdst = Join-Path $repo ('dist\' + $exe + '\extension\host')
    New-Item $hdst -ItemType Directory -Force | Out-Null
    foreach ($f in 'install_host.ps1', 'panelboss_host.py', 'webrect.py',
                   'panelboss-host.exe', 'host-manifest.template.json') {
        $hs = Join-Path $hsrc $f
        if (Test-Path $hs) {
            Copy-Item $hs $hdst -Force
            Write-Output ('host bundle copy: ' + $hs)
        } else {
            Write-Output ('host bundle MISSING (run install_host.ps1 once to build it): ' + $hs)
        }
    }
    Write-Output ('onedir ready: ' + (Join-Path $repo ('dist\' + $exe)))
}
