"""The release check and the msi handoff - the updater's logic half.

The app is offline-by-default: a failed check is a sentence in the
UI, never a traceback, never a balloon; every network verb here
catches ALL of its own failures and says 'error' (the reason rides
log.debug). The UI half lives in ui.window._general; this module
imports no Tk and spawns nothing (the console-verb ledger stays a
file of one page).

Split from the window because the window suite cannot fake a
network and this half must be faked to be tested (update_test).
"""
from __future__ import annotations

import glob
import json
import logging
import os
import shutil
import urllib.error
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
    return {"version": version, "url": str(asset["browser_download_url"]),
            "asset": str(asset["name"])}


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


APPLY = """@echo off
rem PanelBoss update handoff: one-shot by design - it waits for the
rem app to die, installs the msi quietly (the /l*v receipt says how
rem it went), reopens the app EXACTLY the way update.bat does (start
rem "PanelBoss" <exe> - no login stamp on a relaunch: that flag is
rem the Run entry's alone, never the updater's), and deletes itself.
setlocal
set tries=0
:wait
tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul
if errorlevel 1 goto install
set /a tries+=1
if %tries% geq 15 (
    echo the app would not close - installing anyway; if the
    echo files were busy the receipt in update.log will say so
    goto install
)
rem ~2 s per lap (update.bat's own ping idiom: timeout's stdin
rem dependence dies under redirected handles, ping's never does)
ping -n 3 127.0.0.1 >nul
goto wait
:install
msiexec /i "{msi}" /qn /l*v "{log}"
if errorlevel 1 (
    echo the install FAILED - read the receipt:
    echo   {log}
    pause
    goto done
)
start "PanelBoss" "{exe}"
:done
del "%~f0"
"""


def apply_text(msi, exe, pid, log_path):
    """The handoff script's body (write_apply stamps it to disk; the
    split exists so update_test can pin the content - waits-on-pid,
    the /qn /l*v pair, the bat-shaped relaunch, the self-delete -
    without touching the disk or running cmd)."""
    return APPLY.format(pid=pid, msi=msi, exe=exe, log=log_path)


def write_apply(msi, exe, pid, dest_dir):
    """Stamp the handoff beside the msi (update\\apply.bat - a
    self-known name; the script knows its own path only through
    %~f0, which is how it commits suicide). Returns the script's
    path - the caller spawns it exactly like the git path: cmd.exe
    /c, creationflags zero, the package's second
    declared console opt-out - startup_test's ledger
    counts it beside the git path's."""
    path = os.path.join(dest_dir, "apply.bat")
    with open(path, "w", encoding="mbcs") as fh:   # the OEM codepage
        fh.write(apply_text(msi, exe, pid,
                            os.path.join(dest_dir, "update.log")))
    return path
