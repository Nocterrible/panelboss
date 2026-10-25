# Install the PanelBoss Companion native-messaging host.
#
#   powershell -NoProfile -File install_host.ps1 [-ExtensionId <id>]
#
# This is what "an external app can reach the extension's API" means at
# the Windows level: the browser starts the host when the extension
# calls connectNative(), and the registry key tells the browser where
# the host manifest lives. Two things happen here:
#   1. the host exe (panelboss-host.exe) is built with PyInstaller from
#      panelboss_host.py, if it is not already present;
#   2. HKCU\Software\Google\Chrome\NativeMessagingHosts\com.nocterrible
#      .panelboss is pointed at a written host manifest whose
#      allowed_origins carries the extension's id (the ONLY ACL - no
#      pairing, no token; the browser's own install check is the whole
#      handshake).
#
# -ExtensionId is the 32-char extension id from the browser's
# extensions page (opera://extensions, chrome://extensions, or
# edge://extensions). For an unpacked load it is stable; for a store
# publish it is the store-assigned id. Leave it out and the script
# writes the manifest with the placeholder still in it and says so.
#
# Chrome reads the 32-bit registry view first, then 64-bit; HKCU needs
# no admin. Opera GX and Edge read the SAME Google\Chrome\NativeMessaging
# Hosts key on Windows (the Chromium base they share), so one install
# covers every family.
param([string]$ExtensionId = "", [switch]$Rebuild)

$ErrorActionPreference = 'Stop'
# a typo today registers a never-matching origin and reads forever as the
# nm badge - the exact silent class this design kills. An extension id is
# 32 lowercase chars in [a-p] (the Chromium id alphabet); reject anything
# else BEFORE a single file is written.
if ($ExtensionId -and $ExtensionId -notmatch '^[a-p]{32}$') {
    Write-Output "bad extension id '$ExtensionId' - it must be 32 lowercase a-p (from the browser's extensions page)"
    exit 1
}
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$hostPy = Join-Path $here 'panelboss_host.py'
$hostExe = Join-Path $here 'panelboss-host.exe'
# the written (installed) manifest carries the ABSOLUTE exe path; the
# committed template (host-manifest.template.json) is a shape example
# only - its relative path is NOT Chrome-legal as-is.
$manifestPath = Join-Path $here 'host-manifest.json'
$repo = Split-Path -Parent (Split-Path -Parent $here)   # extension/ -> repo
$py = Join-Path $repo '.venv\Scripts\python.exe'

$HOSTNAME = 'com.nocterrible.panelboss'

# 1. build the host exe (single file, no window, tiny - stdlib only).
# -Rebuild deletes the exe first: a process killed mid-write leaves a
# partial onefile that Test-Path happily reports as present, and the
# skip-branch then wedges every reinstall on a broken binary the
# recovery word used to have to be MANUAL about (gate finding 4, Oct 16).
# THE MSI GUARD (final gate, Oct 25): the app's one-click always passes
# -Rebuild, but a BUNDLED install ships the guarded build as a build
# FACT and has no venv to rebuild it with - there, -Rebuild is honored
# as "rebuild IF you can" and the bundled exe registers as-is (the law
# it serves - a partial exe must not wedge reinstall - needs a build
# process to produce partials; a shipped binary has none).
if ($Rebuild -and (Test-Path $hostExe) -and (Test-Path $py)) {
    Remove-Item $hostExe -Force
}
if (-not (Test-Path $hostExe)) {
    if (-not (Test-Path $py)) {
        Write-Output "no panelboss-host.exe to register and no venv python to build it ($py) - run this script from a source checkout"
        exit 3
    }
    Write-Output 'building panelboss-host.exe (PyInstaller onefile)'
    & $py -m PyInstaller --noconfirm --clean --onefile --windowed `
        --name 'panelboss-host' `
        --distpath $here --workpath (Join-Path $here 'build') `
        --specpath (Join-Path $here 'build') `
        $hostPy
    if ($LASTEXITCODE -ne 0) { Write-Output "host build failed ($LASTEXITCODE)"; exit $LASTEXITCODE }
} elseif ($Rebuild) {
    Write-Output "bundled panelboss-host.exe kept (no venv to rebuild here: $py)"
}

# 2. write the host manifest with the extension's id in allowed_origins
$origin = "chrome-extension://$ExtensionId/"
if (-not $ExtensionId) { $origin = 'chrome-extension://PLACEHOLDER--REPLACE-WITH-THE-EXTENSION-ID/' }
$manifest = @{
    name = $HOSTNAME
    description = "PanelBoss Companion - hands the measured video geometry to PanelBoss's Movie theater mode"
    path = $hostExe
    type = 'stdio'
    allowed_origins = @($origin)
}
$manifest | ConvertTo-Json | Set-Content -Path $manifestPath -Encoding UTF8

# 3. register under HKCU (no admin; Chrome/Edge/Opera all read it)
$key = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$HOSTNAME"
New-Item -Path $key -Force | Out-Null
Set-ItemProperty -Path $key -Name '(default)' -Value $manifestPath

# 4. tell PANELBOSS where the host exe lives: the app reads capability
# discovery from this exe (host.json is the doorway's neighbor, so the
# app queries the host it installed - the owner's "PanelBoss reads what
# the API can send" mandate).
$appdir = Join-Path $env:APPDATA 'PanelBoss'
# [IO.Directory]::CreateDirectory, NOT New-Item -Force: PowerShell
# 5.1's New-Item on an EXISTING directory throws a lying
# UnauthorizedAccessException (measured Oct 16: the app writes this
# dir every day; the ACL grants the user FullControl; the .NET call
# succeeds in the same breath). CreateDirectory is idempotent and
# tells the truth about real failures.
[void][IO.Directory]::CreateDirectory($appdir)
# utf-8-sig (no BOM) written here so BOTH producers of this file -
# this script on Windows PowerShell and the app's own writer - are
# readable by the reader's utf-8-sig; PS7's -Encoding utf8 is already
# BOM-less, 5.1's is not; sig keeps them identical either way.
@{ path = $hostExe } | ConvertTo-Json | Set-Content `
    -Path (Join-Path $appdir 'host.json') -Encoding UTF8

if (-not $ExtensionId) {
    Write-Output ('host installed, but the extension id is still the placeholder - rerun with -ExtensionId <id from the browser extensions page>')
} else {
    Write-Output ("host installed for origin $origin")
}