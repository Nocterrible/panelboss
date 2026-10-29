# Companion extension store package: stage the declared surface,
# zip it manifest-at-root, print the sha. The 0.4.5 upload was a
# hand-built zip; hand-built means "the architect forgets which
# files it needs" (Oct 29: the 0.4.6 zip was nearly not shipped).
param([string]$repo = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = 'Stop'
$src = Join-Path $repo 'extension'
$ver = (Get-Content (Join-Path $src 'manifest.json') -Raw |
        ConvertFrom-Json).version
$stage = Join-Path $env:TEMP "pbext-$ver"
$zip = Join-Path $repo "dist\panelboss-companion-$ver.zip"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory $stage | Out-Null
# the store surface ONLY: host/ (the native host) and README.md are
# shipped by the MSI/zip trees, not by the browser package
foreach ($f in 'manifest.json','content.js','background.js',
               'popup.html','popup.js','icons') {
    Copy-Item -Recurse -Force (Join-Path $src $f) (Join-Path $stage $f)
}
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip
Write-Output "zip: $zip"
Write-Output "sha256: $((Get-FileHash $zip).Hash)"
