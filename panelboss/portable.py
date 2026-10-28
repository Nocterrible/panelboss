"""Portable mode: the store root beside the exe, not under APPDATA.

The onedir build zipped IS the portable build: zero install footprint
for locked-down work machines (no admin, no assumptions past user-
writable files). The flag is a file named portable.ini NEXT TO THE
EXECUTABLE - frozen: the folder containing PanelBoss.exe; dev tree:
the repo root (so a test can stand the layout up in a tempdir by
simulating the frozen pair instead of touching the real tree). Where
the flag points, the store root lives: config.CONFIG_DIR,
config.LOG_DIR and inference.MODELS_ROOT all route through root().
Without the flag the answer is the historic APPDATA root, byte-equal
to the pre-portable expression (portable_test pins it). The env seam
PANELBOSS_CONFIG_DIR still wins over both, at its config.py site.

Machine scratch stays LOCALAPPDATA ALWAYS: the updater's landing zone
(%LOCALAPPDATA%\\PanelBoss\\update, update.py's update_dir) and the
assistant's ps1 files are machine scratch, not user data - replacing
the portable folder must never take them with it, and the update
handoff must never write into a folder the user may be mid-replace of.

FAILURE PATH (named, not hoped): the flag present but its folder not
writable (create+delete probe - a work machine's read-only share)
-> fall back to the historic APPDATA root and speak the warning; the
app never dies at a read-only folder. The probe runs at config IMPORT,
before any log handler can hear it, so the word is BUFFERED here and
config.get_log_level replays it once the handler is mounted - the
loud stop exists, it just speaks into the file that chose it.
"""

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("portable")

APP_NAME = "PanelBoss"
FLAG = "portable.ini"
WTEST = ".wtest"          # the writability probe's name (the test
                          # plays the read-only class with a DIRECTORY
                          # wearing this exact name)

_root = None              # the decided store root, once per process
_portable = False         # is_portable()'s cached answer (cheap: the
                          # UI copy asks per repaint, never re-probes)
_pending = None           # the pre-handler warning, buffered verbatim


def _historic_root(appdata):
    """The pre-portable expression, verbatim (config.py's old lines
    34-38; byte-equality there is the test-pinned promise). Takes the
    caller's APPDATA answer so the migration's call-time fake - the
    virgin-boot school - keeps working through the door."""
    if appdata:
        return Path(appdata) / APP_NAME
    return Path.home() / ".config" / APP_NAME


_UNSET = object()


def _writable(d):
    """Create-and-delete probe: what a locked-down share says is
    final, and any answer but True reads as no."""
    probe = d / WTEST
    try:
        probe.touch()
        probe.unlink()
        return True
    except OSError:
        return False


def evaluate(appdata=_UNSET, frozen=_UNSET, exe=_UNSET):
    """The decision LAW evaluated at CALL time against optionally
    faked inputs (None-ish defaults read the live env/sys): (root,
    is_portable). root() below freezes ONE answer for the whole
    process - CONFIG_DIR, LOG_DIR and MODELS_ROOT must agree - while
    migrate_once rides this call-time face, because the suite school
    (virgin_boot_test) fakes APPDATA per boot. The flag folder's own
    probe still answers the live sys pair unless faked in."""
    appdata = os.environ.get("APPDATA") if appdata is _UNSET else appdata
    frozen = getattr(sys, "frozen", False) if frozen is _UNSET else frozen
    exe = sys.executable if exe is _UNSET else exe
    base = Path(exe).parent if frozen else Path(__file__).resolve().parent.parent
    if not (base / FLAG).is_file():
        return _historic_root(appdata), False
    if _writable(base):
        return base, True
    fallback = _historic_root(appdata)
    global _pending
    _pending = (base, fallback)
    return fallback, False


def root():
    """The store root (a Path), decided once per process at first
    ask. portable.ini beside the exe -> the exe's folder; no flag, or
    an unwritable flagged folder -> the historic APPDATA root (with
    the buffered warning, replay()d once logging exists)."""
    global _root, _portable
    if _root is None:
        _root, _portable = evaluate()
    return _root


def is_portable():
    """The cheap bool for UI copy: the cached verdict of the decide
    (asks root() once; never re-probes the disk)."""
    root()
    return _portable


def replay():
    """config.get_log_level calls this after mounting its handler: a
    fallback decided at import time (before any handler could receive
    it) speaks ONCE into the log file. One word per DECISION: a
    migrate_once re-run against a still-unwritable folder re-arms the
    buffer on purpose - a retry that failed twice gets the word
    twice; a healthy process gets it never."""
    global _pending
    if _pending is None:
        return
    base, fallback = _pending
    _pending = None
    log.warning("portable: store directory %s is not writable - using "
                "%s instead", base, fallback)
