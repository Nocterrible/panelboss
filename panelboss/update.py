"""The release check and the msi handoff - the updater's logic half.

The app is offline-by-default: a failed check is a sentence in the
UI, never a traceback, never a balloon; every network verb here
catches ALL of its own failures and says 'error' (the reason rides
log.debug). The UI half lives in ui.window._general; this module
imports no Tk and spawns nothing (the console-verb ledger stays a
file of one page).

Split from the window because the window suite cannot fake a
network and this half must be faked to be tested (update_test).

TEST SEAM (live acceptance and the suite): PB_UPDATE_ASSET_URL,
when set, replaces the release's asset URL for the fetch (file://
or a plain local path both work); PB_UPDATE_ASSET_SHA256 overrides
the expected digest - 'self' means the target file's own bytes (the
verification and receipt path run complete over a locally built
msi). Empty/unset = the real GitHub API, no seam.
"""
from __future__ import annotations

import glob
import hashlib
import json
import logging
import os
import pathlib
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

log = logging.getLogger("update")

# confirmed Oct 22 against `git remote -v` (the repo serves no
# releases yet - a 404 today, which is exactly the 'error' lane);
# the asset rule is the one build_msi.ps1 writes: light ships
# dist\PanelBoss-<version>-user.msi, a per-user package (no
# elevation, so msiexec /qn installs it in peace).
RELEASE_API = ("https://api.github.com/repos/"
               "Nocterrible/panelboss/releases/latest")
# the HUMAN twin of the API door (portable honesty, Oct 28): the
# download page a portable install's button opens - derived from the
# API constant by swapping the API host and dropping /repos, so a
# repo move edits one line (and the test pins the literal result)
RELEASE_PAGE = RELEASE_API.replace("api.github.com/repos/", "github.com/")
ASSET_ENDS = "-user.msi"
TIMEOUT = 5          # the API answer is a few kB; the UI waits on it
DL_TIMEOUT = 60      # the msi is tens of MB: stall, do not crawl
# GitHub demands a User-Agent header on API calls (documented 403
# without one):
HEADERS = {"User-Agent": "PanelBoss/" + __version__}

_LAST = None         # the last release the check SAW AND RAN BEHIND -
                     # a stored msi url outlives a flaky retry (an
                     # UPDATE NOW may still ride it; a fresh 'current'
                     # answer clears it: the box is up to date)


def latest_release():
    """GET the newest release: {version, url, asset} - version is the
    tag minus its leading 'v', url the '-user.msi' asset's
    browser_download_url, asset the file name. Raises on ANY failure
    (check() is the quiet door; call this one when the exception is
    the answer you want)."""
    req = urllib.request.Request(RELEASE_API, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.load(resp)
    tag = str(data.get("tag_name") or "")
    version = tag[1:] if tag.lower().startswith("v") else tag
    asset = next((a for a in (data.get("assets") or [])
                  if str(a.get("name") or "").endswith(ASSET_ENDS)),
                 None)
    if not version or asset is None or not asset.get(
            "browser_download_url"):
        raise ValueError("release answers no version + -user.msi")
    # THE DIGEST (owner live incident, Oct 26): GitHub publishes
    # assets[].digest as 'sha256:<hex>' on every release asset; the
    # updater must carry it through the stored release so the
    # download can be checked against it BEFORE msiexec is touched.
    # Absent (old API cache, odd proxy) stays '' - fetch_and_verify
    # decides what an absent digest means (it refuses).
    return {"version": version, "url": str(asset["browser_download_url"]),
            "asset": str(asset["name"]),
            "digest": str(asset.get("digest") or "")}


def is_newer(a, b):
    """Dotted-int compare - never string compare, or 10.0 loses to
    9.9.9 - and never an exception, or one 'v' or 'rc1' segment
    grounds the check. Unequal segment counts compare with zeros
    filled in (0.4 beats 0.3.2); a non-numeric segment is zero and
    decides nothing."""
    def parts(v):
        out = []
        for seg in str(v).split("."):
            try:
                out.append(int(seg))
            except ValueError:
                out.append(0)
        return out
    pa, pb = parts(a), parts(b)
    width = max(len(pa), len(pb))
    pa += [0] * (width - len(pa))
    pb += [0] * (width - len(pb))
    return pa > pb


def check(current=__version__):
    """(status, version): 'behind' carries the newest version (and
    stores its url for the download), 'current' carries the running
    one, 'error' carries None - offline, 404, broken JSON, all the
    same honest sentence."""
    global _LAST
    try:
        rel = latest_release()
    except Exception:
        log.debug("the release check drew a blank", exc_info=True)
        return "error", None
    if is_newer(rel["version"], current):
        _LAST = rel
        return "behind", rel["version"]
    _LAST = None
    return "current", rel["version"]


def stored_release():
    """The last 'behind' answer's release (the url a retry may ride
    while the API is flaky), or None."""
    return _LAST


def update_dir():
    """%LOCALAPPDATA%\\PanelBoss\\update - the msi's landing zone and
    the handoff script's home, beside the package (never inside it:
    the installer replaces the package). Reads the env at call time,
    so a test may point it into a temp dir."""
    return os.path.join(os.environ.get("LOCALAPPDATA") or
                        os.path.expanduser("~\\AppData\\Local"),
                        "PanelBoss", "update")


def download(url, dest_dir=None):
    """Stream the msi to the update dir: the directory is made, the
    PRIOR *.msi is deleted first (one-file-cheap: an updater that
    hoards installers is a disk leak), the new one lands as the
    asset's own name, its size is logged, the path is returned."""
    d = dest_dir or update_dir()
    os.makedirs(d, exist_ok=True)
    for old in glob.glob(os.path.join(d, "*.msi")):
        try:
            os.remove(old)
        except OSError:
            log.debug("a prior msi was busy and stays", exc_info=True)
    name = url.rsplit("/", 1)[-1].split("?")[0] or "release" + ASSET_ENDS
    path = os.path.join(d, name)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=DL_TIMEOUT) as resp, \
            open(path, "wb") as fh:
        shutil.copyfileobj(resp, fh)
    log.info("update: the msi landed (%d bytes) at %s",
             os.path.getsize(path), path)
    return path


def sha256_of(path):
    """Streaming sha256 (hex) of a file - the msi is tens of MB, the
    hash must not slurp it into RAM."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _seam(url, digest):
    """The documented test seam: PB_UPDATE_ASSET_URL replaces the
    fetch target (a plain path is accepted, file:// URLs too);
    PB_UPDATE_ASSET_SHA256 overrides the expected digest, 'self'
    meaning the target's own bytes (so the verify+receipt machinery
    runs complete over a locally built msi)."""
    raw = (os.environ.get("PB_UPDATE_ASSET_URL") or "").strip()
    if not raw:
        return url, digest, False
    if "://" in raw:
        url = raw
    else:
        url = pathlib.Path(os.path.abspath(raw)).as_uri()
    exp = (os.environ.get("PB_UPDATE_ASSET_SHA256") or "").strip()
    if exp.lower() == "self":
        p = raw if "://" not in raw else urllib.request.url2pathname(
            urllib.parse.urlparse(raw).path)
        digest = "sha256:" + sha256_of(p)
    elif exp:
        digest = exp
    return url, digest, True


def fetch_and_verify(rel, dest_dir=None):
    """The download AND the digest law, one door: the bytes land and
    are checked against the release's published digest BEFORE any
    handoff exists. Raises ValueError with the honest sentence when
    the release answers no digest or the bytes disagree - the
    download STAYS on disk (the retry must not re-pay the wire).
    Returns (path, hex) - the hex rides the bat's receipt line."""
    url, digest, _seam_hit = _seam(rel["url"], rel.get("digest") or "")
    path = download(url, dest_dir)
    got = sha256_of(path)
    want = digest.split(":")[-1].strip().lower()
    if not want:
        raise ValueError("the release answers no sha256 digest - "
                         "unverified bytes are not installed "
                         "(download kept for the record)")
    if got != want:
        raise ValueError("the download's sha256 is %s, the release "
                         "published %s - mismatch, refusing (download "
                         "kept for the record)" % (got, want))
    return path, got


APPLY = """@echo off
rem PanelBoss update handoff - the deterministic last mile (owner live
rem incident, Oct 26: the cooperative-quit design let msiexec run while
rem the old app was still alive; the new copy hit the one-instance law,
rem quit, and the old copy then died to the file replacement: zero
rem PanelBoss). This bat is now the one killer: taskkill OWN pid, wait
rem the process table for real, install synchronously, relaunch on
rem BOTH rc paths (a failed install must never leave the desk
rem tray-less - the old files survived their own rollback), receipt,
rem self-delete. It rides DETACHED (0x208): there is no console here,
rem so no blocking prompt anywhere - the words land in the update.log
rem receipt, and the failure branch that once waited for a keystroke
rem now relaunches like everything else.
setlocal
set tries=0
set "probe=%TEMP%\panelboss-upwait.tmp"
taskkill /F /PID {pid} >nul 2>nul
:wait
rem NO PIPES, ANYWHERE (measured Oct 26, twice): a tasklist-then-find
rem pipeline froze its FIRST lap under DETACHED (find waits for a
rem write-end that survives in an inherited handle), and even a rem
rem line mentioning that pipe kills this interpreter (cmd parses
rem redirections BEFORE it discards the line). The probe therefore
rem lands in a FILE and findstr answers from disk: an exit code
rem nobody can wed. The probe asks tasklist itself (filtered to
rem OUR pid: ANY LINE = alive, only the INFO line = gone) - on
rem Windows 26220 no quote-escape form of a CSV-token pattern
rem matches at all (measured), and a bare substring can lie from
rem the memory column. NO VERTICAL-BAR CHARACTERS BELOW THIS LINE.
tasklist /fi "PID eq {pid}" /fo table /nh >"%probe%" 2>nul
findstr /m /v /b /c:"INFO" "%probe%" >nul
if errorlevel 1 goto install
set /a tries+=1
if %tries% geq 30 (
    >>"{rclog}" echo [%date% %time%] waited 30 laps, the pid is
    echo   still listed - installing anyway (rc will tell)
    goto install
)
rem ~1 s per lap (the bat's own ping idiom: timeout's stdin
rem dependence dies under redirected handles AND under DETACHED,
rem ping's never does; 500 ms is below its resolution)
ping -n 2 127.0.0.1 >nul
goto wait
:install
del "%probe%" >nul 2>nul
rem THE STORE FIRST (owner law, Oct-24 launch night): both handoff
rem paths back the store up before anything installs - label-first
rem placement, BEFORE msiexec, every goto route passes the copies.
set "bkdir=%LOCALAPPDATA%\\PanelBoss\\update"
if not exist "%bkdir%" mkdir "%bkdir%"
copy /y "%APPDATA%\\PanelBoss\\profiles.json" "%bkdir%\\profiles.json.bak" >nul 2>nul
copy /y "%APPDATA%\\PanelBoss\\config.toml" "%bkdir%\\config.toml.bak" >nul 2>nul
echo store backed up to %bkdir% (profiles.json.bak, config.toml.bak)
if not exist "%APPDATA%\\PanelBoss\\logs" mkdir "%APPDATA%\\PanelBoss\\logs"
rem SYNCHRONOUS install: called directly (not via start) msiexec /qn
rem blocks until the package is placed; /norestart - the updater may
rem never commandeer the owner's reboot policy.
msiexec /i "{msi}" /qn /norestart /l*v "{log}"
set rc=%errorlevel%
rem THE RECEIPT: rc + the digest the bytes were verified against,
rem appended to the app's own log (msiexec owns the /l*v file; the
rem handoff speaks here, with a timestamp - the order is the proof).
>>"{rclog}" echo [%date% %time%] update handoff: install rc=%rc% verified sha256={digest} msi="{msi}"
start "" "{exe}"
del "%~f0"
"""


def apply_text(msi, exe, pid, log_path, digest="unverified",
               rclog=None):
    """The handoff script's body (write_apply stamps it to disk; the
    split exists so update_test can pin the content - the taskkill,
    the waits-on-pid loop, the /qn /norestart synchronous install,
    the UNCONDITIONAL relaunch (both rc paths), the receipt with the
    verified digest, the self-delete - without touching disk or
    running cmd)."""
    return APPLY.format(pid=pid, msi=msi, exe=exe, log=log_path,
                        digest=digest,
                        rclog=rclog or os.path.join(
                            os.environ.get("APPDATA") or "",
                            "PanelBoss", "logs", "update.log"))


def write_apply(msi, exe, pid, dest_dir, digest="unverified"):
    """Stamp the handoff beside the msi (update\\apply-<pid>.bat - the
    victim's OWN number is the name: the fixed apply.bat let an old
    wedged handoff read a fresh one's body off stale offsets, eat the
    relaunch line, and del "%~f0" the alive bat out from under its
    cmd (measured Oct 26, the acceptance run: two bats, one name, one
    silent death with no receipt). A per-pid name cannot collide -
    one app, one pid, one bat. The script knows its own path only
    through %~f0, which is how it commits suicide). Stale apply-*.bat
    older than half an hour are swept here (a handoff lives minutes;
    age is the safe proxy for 'no cmd is reading it'). Returns the
    script's path - the caller spawns it detached: cmd.exe /c with
    DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP (0x208), the dying
    app's funeral must not take the bat down, and the bat has no
    console to speak into (startup_test's ledger counts it beside the
    git path's zero-flag spawn - one console window each kind)."""
    for stale in glob.glob(os.path.join(dest_dir, "apply-*.bat")):
        try:
            if time.time() - os.path.getmtime(stale) > 1800:
                os.remove(stale)
        except OSError:
            log.debug("a stale handoff script is busy and stays",
                      exc_info=True)
    path = os.path.join(dest_dir, "apply-%d.bat" % pid)
    with open(path, "w", encoding="mbcs") as fh:   # the OEM codepage
        fh.write(apply_text(msi, exe, pid,
                            os.path.join(dest_dir, "update.log"),
                            digest=digest))
    return path
