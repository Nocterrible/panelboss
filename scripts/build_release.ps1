# Release build: one folder + one zip, next to the repo.
#
#   powershell -NoProfile -File scripts\build_release.ps1
#
# Produces  dist\PanelBoss\  (run the exe inside) and
#           dist\PanelBoss-<commit>.zip  (the release).
# The zip drops beside the exe's own folder; config and logs stay in
# %APPDATA%\PanelBoss for BOTH the repo and the exe world.
# The exe itself is built by the SHARED onedir step (build_onedir.ps1,
# dot-sourced below): this file owns only the zip and its stamp, and
# build_msi.ps1 owns the candle/light half - the PyInstaller flags
# live in exactly one place now (MSI wave, Oct 21).

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'build_onedir.ps1')

$repo = Split-Path -Parent $PSScriptRoot
$exe = 'PanelBoss'

Invoke-OnedirBuild -repo $repo -exe $exe

$stamp = (& git -C $repo rev-parse --short HEAD) 2>$null
if ($stamp) { $zipName = ($exe + '-' + $stamp + '.zip') } else { $zipName = ($exe + '.zip') }
$zip = Join-Path $repo ('dist\' + $zipName)
Compress-Archive -Path (Join-Path $repo ('dist\' + $exe)) -Destination $zip -Force
Write-Output ('release: ' + $zip)
