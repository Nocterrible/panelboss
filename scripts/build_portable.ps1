# The portable artifact: the shared onedir build, flagged, zipped,
# hashed. Reuses build_onedir.ps1's ONE flag list (dot-source, call,
# never re-implement - the flag-drift trap that file exists to kill);
# this script adds only the portable skin: the versioned folder COPY,
# the portable.ini flag (panelboss/portable.py is the whole contract),
# a plain-voice README, the zip, and the sha256 line for the release.
# NO SIGNING STEP: the SmartScreen caveat is DOCUMENTED in the README,
# not solved here (an unsigned exe on a fresh machine shows the
# "Windows protected your PC" detour - More info > Run anyway).
#
#   powershell -NoProfile -File scripts\build_portable.ps1
#     -> dist\PanelBoss-Portable-<version>\   (runnable as-is)
#     -> dist\PanelBoss-Portable.zip          (the shipped artifact)
#     -> the zip's sha256, printed
$repo = Split-Path -Parent $PSScriptRoot
$py = Join-Path $repo '.venv\Scripts\python.exe'
. (Join-Path $PSScriptRoot 'build_onedir.ps1')
Invoke-OnedirBuild -repo $repo
# the canonical version: the app's own constant (build_msi.ps1's law)
$version = (& $py -c "import panelboss; print(panelboss.__version__)").Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw "bad version '$version'" }
$src = Join-Path $repo 'dist\PanelBoss'
$dst = Join-Path $repo ('dist\PanelBoss-Portable-' + $version)
if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
Copy-Item $src $dst -Recurse
New-Item (Join-Path $dst 'portable.ini') -ItemType File -Force | Out-Null
Set-Content -Path (Join-Path $dst 'README.txt') -Value @(
    'Run PanelBoss.exe from this folder - nothing installs on this machine.',
    'Your settings and logs live in this folder, beside the exe.',
    'To update: close the app and replace this folder with the new zip.',
    '(Unsigned build: Windows may show "protected your PC" once - click',
    'More info, then Run anyway. SmartScreen flags every unsigned exe.'
) -Encoding UTF8
$zip = Join-Path $repo 'dist\PanelBoss-Portable.zip'
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $dst -DestinationPath $zip
Write-Output ('zip:    ' + $zip)
Write-Output ('sha256: ' + (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLower())
Write-Output ('runnable folder: ' + $dst)
