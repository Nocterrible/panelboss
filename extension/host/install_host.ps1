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
# BUILD-THEN-SWAP (dossier H): the registered exe is NEVER removed
# before the build - PyInstaller writes its fresh onefile into the
# dist dir beside it (extension\host\dist), and only a SUCCESSFUL
# build is copied over the registered one. A build that dies leaves
# the old exe untouched (gate finding 4's wedge, dead at the root:
# there is no missing-exe window and no BUILD-time partial at the
# registered path (a mid-Copy-Item crash is the residual, recovered
# by the always-full -Rebuild the one-click takes), and an in-use
# copy lands a .new beside it - never a
# vanishing target.
# THE MSI GUARD (final gate, Oct 25): the app's one-click always passes
# -Rebuild, but a BUNDLED install ships the guarded build as a build
# FACT and has no venv to rebuild it with - there, -Rebuild is honored
# as "rebuild IF you can" and the bundled exe registers as-is (a
# shipped binary has no build process to swap it; nothing to wedge).
if (-not (Test-Path $hostExe) -and -not (Test-Path $py)) {
    Write-Output "no panelboss-host.exe to register and no venv python to build it ($py) - run this script from a source checkout"
    exit 3
}
if (($Rebuild -or -not (Test-Path $hostExe)) -and (Test-Path $py)) {
    Write-Output 'building panelboss-host.exe (PyInstaller onefile)'
    $buildDist = Join-Path $here 'dist'
    & $py -m PyInstaller --noconfirm --clean --onefile --windowed `
        --name 'panelboss-host' `
        --distpath $buildDist --workpath (Join-Path $here 'build') `
        --specpath (Join-Path $here 'build') `
        $hostPy
    if ($LASTEXITCODE -ne 0) { Write-Output "host build failed ($LASTEXITCODE)"; exit $LASTEXITCODE }
    $built = Join-Path $buildDist 'panelboss-host.exe'
    if ($Rebuild -and (Test-Path $hostExe)) {
        # THE SWAP: only now does the registered exe change. The
        # browser keeps a LIVE host process holding the image - an
        # in-use target must not be deleted to make the copy work.
        try {
            Copy-Item $built $hostExe -Force
        } catch {
            Copy-Item $built "$hostExe.new" -Force
            Write-Output "THE BROWSER STILL HOLDS panelboss-host.exe (in use) - the fresh build waits as panelboss-host.exe.new: RETRY THE INSTALL AFTER CLOSING THE BROWSER"
            exit 4
        }
    } else {
        # nothing registered yet (first install): the fresh build IS
        # the exe - move it into place.
        Move-Item $built $hostExe -Force
    }
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
# host.json is written with -Encoding UTF8 and READ with utf-8-sig,
# so it is readable whichever producer wrote it: Windows PowerShell
# 5.1's Set-Content -Encoding UTF8 EMITS A BOM (measured: EF BB BF -
# the suite replays the real signature through the app's own reader),
# PS7's is BOM-less, and the app's own writer follows its own
# encoding. The sig read keeps all producers compatible; claiming
# "no BOM" here once lied about the 5.1 producer (gate round 2).
@{ path = $hostExe } | ConvertTo-Json | Set-Content `
    -Path (Join-Path $appdir 'host.json') -Encoding UTF8

if (-not $ExtensionId) {
    Write-Output ('host installed, but the extension id is still the placeholder - rerun with -ExtensionId <id from the browser extensions page>')
} else {
    Write-Output ("host installed for origin $origin")
}