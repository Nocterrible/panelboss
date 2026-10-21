# Per-user MSI build (MSI wave, Oct 21): onedir -> heat -> candle ->
# light -> dist\PanelBoss-<version>-user.msi.
#
#   powershell -NoProfile -File scripts\build_msi.ps1 [-Help]
#
# -Help prints this header's plan and builds nothing.
#
# The onedir comes from the SHARED step (build_onedir.ps1), never a
# re-inline of the PyInstaller flags; the camera/onnx/model/
# customtkinter data ride INSIDE the package by construction (law 4)
# and the bundle is MEASURED at the end (size + file count + msi).
#
# WiX v5 (dotnet tool) was probed and ruled out on this box: dotnet
# has no SDK ("No .NET SDKs were found", Oct 21). This file uses
# WiX v3.14 and resolves candle/light/heat in this order:
#   1. '%ProgramFiles(x86)%\WiX Toolset v3.14\bin' (the official
#      wix314.exe /install /quiet landing zone),
#   2. '%LOCALAPPDATA%\wix314' (unpacked wix314-binaries.zip - the
#      SAME tools, zero machine footprint: the build box is the
#      owner's live desk and a silent MSI-wide install is its own
#      side effect),
#   3. download + unpack wix314-binaries.zip (GitHub wixtoolset/wix3,
#      tag wix3141rtm) into %LOCALAPPDATA%\wix314 and use it.
# The harvest (files.wxs) is generated with heat dir -var so no file
# list is maintained by hand; panelboss.wxs carries the load-bearing
# UpgradeCode - it is NOT generated here and must never move.

param([switch]$Help)
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$exe = 'PanelBoss'
. (Join-Path $PSScriptRoot 'build_onedir.ps1')

if ($Help) {
    Get-Content -TotalCount 31 $PSCommandPath
    exit 0
}

$py = Join-Path $repo '.venv\Scripts\python.exe'

# the canonical version: the app's own constant (panelboss/
# __init__.py's __version__). The companion extension's 0.4.4 is a
# SEPARATE constant (extension\manifest.json) and is NOT used here.
Push-Location $repo
$version = (& $py -c "import panelboss; print(panelboss.__version__)").Trim()
Pop-Location
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw "bad version '$version'" }

Invoke-OnedirBuild -repo $repo -exe $exe

# --- locate WiX v3 -------------------------------------------------
$wixBin = @(
    (Join-Path ${env:ProgramFiles(x86)} 'WiX Toolset v3.14\bin'),
    (Join-Path $env:LOCALAPPDATA 'wix314')
) | Where-Object { Test-Path (Join-Path $_ 'candle.exe') } | Select-Object -First 1
if (-not $wixBin) {
    Write-Output 'wix314: unpacking the official binaries zip (no machine install)'
    $zip = Join-Path $env:TEMP 'wix314-binaries.zip'
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri ('https://github.com/wixtoolset/wix3/releases/' +
        'download/wix3141rtm/wix314-binaries.zip') -OutFile $zip -UseBasicParsing
    $dst = Join-Path $env:LOCALAPPDATA 'wix314'
    Expand-Archive -Path $zip -DestinationPath $dst -Force
    $wixBin = $dst
    if (-not (Test-Path (Join-Path $wixBin 'candle.exe'))) { throw 'wix unpack lost candle.exe' }
}
$candle = Join-Path $wixBin 'candle.exe'
$light = Join-Path $wixBin 'light.exe'
$heat = Join-Path $wixBin 'heat.exe'

# --- harvest + compile ----------------------------------------------
$onedir = Join-Path $repo 'dist\PanelBoss'
$work = Join-Path $repo 'dist\msi'
New-Item $work -ItemType Directory -Force | Out-Null
$srcDir = $onedir
$wxs = @(
    (Join-Path $repo 'packaging\msi\panelboss.wxs'),
    (Join-Path $work 'files.wxs')
)
& $heat dir $srcDir -nologo -gg -srd -scom -sreg -dr INSTALLDIR `
    -cg PanelBossFiles -var var.SourceDir -out $wxs[1]
if ($LASTEXITCODE -ne 0) { throw "heat failed ($LASTEXITCODE)" }
$defs = @(('-dVersion=' + $version),
          ('-dSourceDir=' + $srcDir),
          ('-dIcon=' + (Join-Path $repo 'assets')),
          ('-dLicRtf=' + (Join-Path $repo 'packaging\msi\license.rtf')))
& $candle -nologo -o (Join-Path $work '') @defs $wxs
if ($LASTEXITCODE -ne 0) { throw "candle failed ($LASTEXITCODE)" }
$msi = Join-Path $repo ('dist\PanelBoss-' + $version + '-user.msi')
# -sice:ICE91 / -sice:ICE38 / -sice:ICE64: ICE91 complains that
# per-user dirs do not vary with ALLUSERS, ICE38 that user-profile
# components must key on HKCU, ICE64 that profile dirs belong in
# the RemoveFile table - per-machine-era formalities whose subject
# does not exist here: law 1 says per-user ONLY, one user owns every
# byte, the shortcut component carries the HKCU marker the ICEs ask
# for, and MSI itself removes created dirs that are empty at
# uninstall (only files the USER dropped in models\ stay - by
# design: that folder outlives the installer, it is the user's).
# Every real cross-check (missing refs, dangling keypaths) stays
# armed.
& $light -nologo -ext WixUIExtension -sice:ICE91 -sice:ICE38 -sice:ICE64 -o $msi (Get-ChildItem $work -Filter '*.wixobj' | ForEach-Object FullName)
if ($LASTEXITCODE -ne 0) { throw "light failed ($LASTEXITCODE)" }

# --- law 4: MEASURE the bundle ---------------------------------------
$files = Get-ChildItem $onedir -Recurse -File
$bytes = ($files | Measure-Object -Sum Length).Sum
Write-Output ('onedir:  ' + $onedir)
Write-Output ('bundle:  ' + [math]::Round($bytes / 1MB, 1) + ' MB in ' +
    $files.Count + ' files (camera/onnx/model/customtkinter ride inside)')
Write-Output ('harvest: ' + (Select-String -Path $wxs[1] -Pattern '<File ').Count +
    ' File rows')
Write-Output ('msi:     ' + $msi + ' (' +
    [math]::Round((Get-Item $msi).Length / 1MB, 1) + ' MB)')
