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
    # OWNER ICON + TRUTHFUL VERSION (Oct 25): the taskbar button took
    # the Windows 'no icon' tile and Properties showed blank because
    # the spec carried neither. The version rides the app's own
    # __version__ so the exe can never lie about the package.
    $ver = (& $py -c 'import panelboss;print(panelboss.__version__)').Trim()
    $vl = (($ver.Split('.') -join ',') + ',0')  # 0,3,6,0 quad form
    $vi = Join-Path $repo 'build\versioninfo.txt'
    New-Item (Split-Path $vi) -ItemType Directory -Force | Out-Null
    @"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($vl), 
    prodvers=($vl), mask=0x3f, flags=0x0,
    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Nocterrible'),
      StringStruct('FileDescription', 'PanelBoss - presence-aware display control'),
      StringStruct('FileVersion', '$ver'),
      StringStruct('InternalName', 'PanelBoss'),
      StringStruct('OriginalFilename', 'PanelBoss.exe'),
      StringStruct('ProductName', 'PanelBoss'),
      StringStruct('ProductVersion', '$ver')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
"@
    | Set-Content -Path $vi -Encoding UTF8
    & $py -m PyInstaller --noconfirm --clean --windowed --name $exe `
        --icon (Join-Path $repo 'assets\panelboss.ico') `
        --version-file $vi `
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
    # GATE ROUND 2 (Oct 25): the extension's manifest rides too -
    # <bundle>\extension\manifest.json is what derive_unpacked_id
    # reads (the key branch), so a desk that loads the BUNDLED
    # extension unpacked derives the right id instead of falling to
    # the store constant. Six files, one truth: what the app resolves
    # is what the repo ships.
    $ems = Join-Path $repo 'extension\manifest.json'
    if (Test-Path $ems) {
        Copy-Item $ems (Join-Path $repo ('dist\' + $exe + '\extension\manifest.json')) -Force
        Write-Output ('host bundle copy: ' + $ems)
    } else {
        Write-Output ('extension manifest MISSING (id derivation dies): ' + $ems)
    }
    # TRAY ART (dossier G's true ending, Oct 25): the onedir shipped
    # WITHOUT assets\tray_master.png, so the public build painted the
    # interim circle while the source tree showed the owner art - the
    # 'old icon reverted' was the fallback confessing, not a ghost.
    # tray.py's belt path looks beside the module: _internal\panelboss\
    # assets\tray_master.png.
    $tas = Join-Path $repo 'assets\tray_master.png'
    $tad = Join-Path $repo ('dist\' + $exe + '\_internal\panelboss\assets')
    if (Test-Path $tas) {
        New-Item $tad -ItemType Directory -Force | Out-Null
        Copy-Item $tas $tad -Force
        Write-Output ('tray art bundle copy: ' + $tas)
    } else {
        Write-Output ('tray art MISSING (the interim circle paints): ' + $tas)
    }
    Write-Output ('onedir ready: ' + (Join-Path $repo ('dist\' + $exe)))
}
