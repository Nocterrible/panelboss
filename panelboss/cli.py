"""Command line.

run is the default command and is always started first;
cameras, preview, config and faces are diagnostics.
"""

from __future__ import annotations

import argparse
import atexit
import ctypes
import logging
import os
import queue
import sys
import threading
import time

from . import config


def timeout_notice(text, title="PanelBoss", ms=10000):
    """A box that dies on its own - the only channel pythonw leaves.

    Slot order is the just-fixed shape (hwnd, text, caption, type,
    wLangID, dwTimeout): the first cut passed the timeout in the
    language slot (TaskDialog shape, not MessageBox) so the twin's
    box never self-dismissed (measured).
    """
    try:
        user32 = ctypes.windll.user32
        user32.MessageBoxTimeoutW.restype = ctypes.c_int
        user32.MessageBoxTimeoutW.argtypes = [
            ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
            ctypes.c_uint, ctypes.c_ushort, ctypes.c_uint]
        user32.MessageBoxTimeoutW(0, text, title, 0x40, 0, ms)
    except Exception:
        pass                        # a dead box is better than a dead
                                    # app; the log is the other channel


def _newest_source_mtime(pkg_dir):
    """Boot-stamp honesty (amendment 7): the NEWEST .py mtime under the
    package tree, walked once at boot. The witnessed launch read
    "code from 07:27" and the whole redesign was indicted as stale -
    the number was cli.py's own untouched mtime, the one file the
    wave never edited. A stamp that measures one file accuses the
    wrong suspect; this one measures the tree the boot actually
    serves. 0.0 on a wholly unreadable tree - the caller says so."""
    newest = 0.0
    try:
        for _root, _dirs, files in os.walk(pkg_dir):
            for name in files:
                if name.endswith(".py"):
                    try:
                        newest = max(newest, os.path.getmtime(
                            os.path.join(_root, name)))
                    except OSError:
                        pass        # vanished mid-walk: others answer
    except OSError:
        return 0.0
    return newest


def _exit_receipt():
    """The last word of a clean exit (silent-death dossier, Oct 15, now
    covering the exit too): main registers this through atexit, so the
    sign-off line's ABSENCE is the marker of a hard death."""
    logging.getLogger("cli").info("cli: panelboss exit pid=%s",
                                  os.getpid())


def main(argv=None):
    parser = argparse.ArgumentParser(prog="panelboss")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "cameras", "preview", "config",
                                "enroll", "faces", "cleanup"])
    parser.add_argument("--off-test", action="store_true",
                        help="prove the monitor round trip; always the last "
                             "check before trusting the power control")
    parser.add_argument("--name", default="", help="identity to enroll")
    parser.add_argument("--index", type=int, default=None,
                        help="camera index; overrides the config file")
    parser.add_argument("--no-ui", action="store_true",
                        help="start headless; the tray alone")
    parser.add_argument("--dry-run", action="store_true",
                        help="cleanup only: read every truth, write "
                             "nothing (safe on a live desk)")
    parser.add_argument("--autostart", action="store_true",
                        help="this copy was fired by the logon Run key "
                             "(the entry stamps itself; recognition is "
                             "a fact, never an inference)")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    config.get_log_level()            # logging always comes first
    # the native-death receipt (Oct 19 WER 1000, pid 23004, python310.dll
    # +0x487d, code 0xc0000005 - a camera-stack AV in a pythonw process
    # that owns no console and left no dump, no atexit line, nothing):
    # a process-level crash must leave a word where the log lives, and
    # the handle sits in the module global so GC never closes the file
    # under the handler's feet (line-buffered: a flush on every write)
    try:
        global _FAULT
        import faulthandler
        _FAULT = open(os.path.join(config.LOG_DIR, "fault.log"),
                      "a", buffering=1)
        faulthandler.enable(file=_FAULT, all_threads=True)
    except Exception:
        _FAULT = None                 # the receipt must never block boot
    # os, not sys: this box's 3.10 build ships a trimmed sys module
    # without getpid (the tray app has been on os.getpid all along)
    # The tree + the newest source mtime ride along: a hard-killed
    # icon lingers as a ghost until Explorer's next notification
    # refresh, so a stale instance is otherwise provenance-less -- and
    # a relaunch that quietly loses the mutex lets the old one
    # impersonate the new. This line names where the running app was
    # ACTUALLY loaded from, and WHEN the newest byte of that code was
    # written (the helper above: one file's mtime fooled a whole
    # launch forensics by staying honest to itself).
    _here = os.path.dirname(os.path.abspath(__file__))
    from . import __version__         # the truth, not a copy: the 0.2.0
    _src = _newest_source_mtime(_here)
    logging.getLogger("cli").info(    # bump changed one line and this
        "panelboss %s boot (pid %s, tree %s, code from %s)",  # banner kept
        __version__, os.getpid(), _here,                    # reciting 0.1.0
        time.strftime("%H:%M", time.localtime(_src))        # newest .py
        if _src else "UNKNOWN (tree unreadable)")           # now
    # every normal departure signs the log (silent-death dossier, Oct 15,
    # now covering the exit too): "cli: panelboss exit pid=" is the last
    # word of a clean stop, and its ABSENCE is the death marker. An
    # uncaught main-thread exception gets the log before the default hook
    # (pythonw owns no stderr, so the log is the only witness).
    atexit.register(_exit_receipt)

    def _hook(exc_type, value, tb):
        logging.getLogger("cli").exception(
            "uncaught main-thread exception",
            exc_info=(exc_type, value, tb))
        if _PREV_HOOK is not sys.__excepthook__:
            _PREV_HOOK(exc_type, value, tb)

    global _PREV_HOOK
    _PREV_HOOK = sys.excepthook
    sys.excepthook = _hook
    config.migrate_once()             # the one-time pre-rename migration,
                                      # before any config read; fail-open
    cfg = config.get_config()
    if args.index is not None:
        cfg["camera"]["index"] = args.index
    if args.no_ui:
        cfg["ui"]["enabled"] = False

    if args.command == "config":
        print(cfg["_path"])
        return 0
    if args.command == "cleanup":
        # the MSI's uninstall verb (law 3): the lines ARE the report,
        # the exit is ALWAYS 0 - a no-op world must not fail an
        # uninstall, and cleanup.run swallows every door's death into
        # its own honest line (panelboss/cleanup.py)
        from . import cleanup
        for line in cleanup.run(cfg, bool(args.dry_run)):
            print(line)
        return 0
    if args.command == "cameras":
        _cameras()                          # names always after indexes
        return 0
    if args.command == "preview":
        from . import preview
        preview.run(cfg, off_test=args.off_test)   # preview always second
        return 0
    if args.command == "enroll":
        return _enroll(cfg, args.name)
    if args.command == "faces":
        return _faces(cfg)
    return _run(cfg, bool(args.autostart))       # the monitor runs last


def _cameras():
    from . import camera
    names = camera.camera_names()
    found = camera.enumerate_cameras()
    for index, opened, width in found:
        name = names[index] if index < len(names) else ""
        print("index %-2s opened=%-5s %-40s width %s" %
              (index, opened, name, int(width)))
    if names:
        print("pnp order:", ", ".join(names))


_MUTEX_HANDLE = None   # set by _single_instance on the win path

_FAULT = None          # the crash-receipt file (set by main after the
                       # log dir exists; module global so GC never
                       # closes it under the handler's feet)


def _single_instance():
    """Named mutex; a second copy exits before touching the camera.
    Global\\ so the guard spans sessions (MSDN kernel-object-namespaces;
    no SeCreateGlobalPrivilege needed for mutexes). Handle + last-error
    are read together - CreateMutexW returns a LIVE handle even when
    the object exists (MSDN createmutexw, windows-rs#2710), so the
    handle alone must never be the verdict, and a NULL handle is a
    real failure: confessed, never a silent win. The handle rides in
    _MUTEX_HANDLE for the life of the process; the kernel closes it
    at exit - that exit is the release."""
    global _MUTEX_HANDLE
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                        ctypes.c_wchar_p]
    kernel32.OpenMutexW.restype = ctypes.c_void_p   # 64-bit handles
    kernel32.OpenMutexW.argtypes = [ctypes.c_ulong, ctypes.c_int,   # do
                                      ctypes.c_wchar_p]             # not
    kernel32.CloseHandle.restype = ctypes.c_int                     # trunc
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    get_last_error = kernel32.GetLastError   # resolved BEFORE the
    h = kernel32.CreateMutexW(0, False, "Global\\PanelBoss")
    err = get_last_error()                   # create (ctypes habit)
    if not h:                                # genuine failure: loud
        logging.getLogger("cli").error(
            "single-instance mutex FAILED (CreateMutexW errno %s); "
            "starting unguarded", err)
        return True
    if err == 183:                           # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(h)              # the redundant handle,
        return False                         # out of courtesy
    # one-release belt (gate finding 2): a still-running OLD build
    # holds the bare session name and cannot see Global\; refuse to
    # double up against it. One-directional by nature - the old
    # builds are the ones that go away.
    old = kernel32.OpenMutexW(0x00100001, False, "PanelBoss")
    if old:
        kernel32.CloseHandle(old)
        kernel32.CloseHandle(h)
        logging.getLogger("cli").info("an older build holds the bare-"
                                      "name mutex; standing down")
        return False
    _MUTEX_HANDLE = h                        # kernel closes at exit
    return True


LOGIN_FRESH_SEC = 180      # how young the session must be for an
                           # --autostart stamp to count as a real
                           # login: the Run entry fires within seconds
                           # of the shell, anything stamped on an
                           # already-running session is a relaunch
                           # wearing a login costume (Oct 12: twelve
                           # fake login restores, each re-applying
                           # modes, each a monitor flicker the owner
                           # watched mid-work)


def _session_age_sec():
    """Seconds since the OUR-session explorer.exe was created - the
    shell's birthday is the practical session birthday: winlogon is
    the honest answer but a SYSTEM process an ordinary token cannot
    OpenProcess (measured: ERROR_ACCESS_DENIED, and it misreported
    its own session too). A mid-session explorer restart re-arms the
    freshness - and re-launching the shell genuinely feels like a
    re-logon to everything shell-started, so we agree with it.
    None when unreadable: the caller trusts the stamp (fail open,
    named: a real login must not lose its ceremony to a ctypes
    stumble)."""
    import ctypes.wintypes as wt
    k32 = ctypes.windll.kernel32
    sid = wt.DWORD()
    if not k32.ProcessIdToSessionId(k32.GetCurrentProcessId(),
                                    ctypes.byref(sid)):
        return None

    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD),
                    ("th32ProcessID", wt.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                    ("th32ParentProcessID", wt.DWORD),
                    ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wt.DWORD),
                    ("szExeFile", wt.WCHAR * 260)]

    # 64-bit discipline: default restypes truncate HANDLEs to int
    k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.c_void_p]
    k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.c_void_p]
    k32.OpenProcess.restype = wt.HANDLE
    k32.CloseHandle.argtypes = [wt.HANDLE]
    k32.GetProcessTimes.argtypes = [wt.HANDLE] + \
        [ctypes.POINTER(wt.FILETIME)] * 4
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)   # SNAPPROCESS, all
    if not snap or ctypes.c_void_p(snap).value == ctypes.c_void_p(-1).value:
        return None
    pe = PE()
    pe.dwSize = ctypes.sizeof(pe)
    found = k32.Process32FirstW(snap, ctypes.byref(pe))
    while found:
        if pe.szExeFile.lower() == "explorer.exe":
            esid = wt.DWORD()
            if (k32.ProcessIdToSessionId(pe.th32ProcessID,
                                         ctypes.byref(esid))
                    and esid.value == sid.value):
                h = k32.OpenProcess(0x1000, False,      # QUERY_LIMITED
                                    pe.th32ProcessID)
                if h:
                    ct = wt.FILETIME()
                    d = wt.FILETIME()
                    if k32.GetProcessTimes(h, ctypes.byref(ct),
                                           ctypes.byref(d),
                                           ctypes.byref(d),
                                           ctypes.byref(d)):
                        k32.CloseHandle(h)
                        k32.CloseHandle(snap)
                        ft = (ct.dwHighDateTime << 32
                              | ct.dwLowDateTime)
                        unix = (ft - 116444736000000000) / 1e7
                        return max(0.0, time.time() - unix)
                    k32.CloseHandle(h)
        found = k32.Process32NextW(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)
    return None


POKE_WAIT_SEC = 2.0      # the winner's UI tick answers in ~90 ms; two
                         # seconds of silence names the no-listener
                         # case (dead window, or none at all)


def _poke_winner():
    """Second-instance handoff through the config dir: the app owns
    no server socket, and a file stamp is the one cross-process
    primitive both instances share (the ack round trip is the honesty:
    a poke into a window that died at birth is tonight's silent half,
    and the loser must SEE that). Winner side:
    SettingsWindow._drain_poke."""
    poke = os.path.join(config.CONFIG_DIR, "poke")
    ack = os.path.join(config.CONFIG_DIR, "poke_ack")
    try:
        before = os.path.getmtime(ack) if os.path.exists(ack) else 0.0
        with open(poke, "a"):
            os.utime(poke, None)
    except OSError:
        return False                    # un-stampable desk: old words
    deadline = time.time() + POKE_WAIT_SEC
    while time.time() < deadline:
        try:
            m = os.path.getmtime(ack)
        except OSError:
            m = 0.0          # not written yet (the winner's tick owns
                             # a ~90 ms latency), or it vanished: the
                             # deadline is the only honest verdict
        if m > before:
            return True
        time.sleep(0.1)
    return False


def _run(cfg, autostart=False):
    from . import state
    from . import startup
    from . import tray

    if not _single_instance():
        logging.getLogger("cli").info("already running; one instance is "
                                       "always checked first")
        # the handoff (owner UAT, Oct 15: two dead icon clicks through
        # a living tray tonight - the balloon explained NOTHING; the
        # winner should ANSWER the click). Touch the shared poke
        # stamp: the running copy's UI tick maps its window and acks.
        # Only real silence - no listener, or a window that died at
        # birth - falls back to the box, and a logon launch still
        # never speaks (its poke rides regardless).
        if _poke_winner():
            logging.getLogger("cli").info("poked the running copy; its "
                                          "window answers the click")
            return 0
        if not autostart:
            # a logon launch must never speak: if an old copy somehow
            # survived the shutdown, the twin's only sound is the log
            # line above. Interactive launches get the box so a double
            # click explains itself.
            timeout_notice(
                "PanelBoss is already running (check the tray, "
                "hidden icons live behind the chevron). One instance is "
                "always started first.",
                "PanelBoss", 5000)
        return 0
    logging.getLogger("cli").info(
        "instance guard: %s" % ("won" if _MUTEX_HANDLE
                                else "UNGUARDED (see error above)"))

    # the tray registers and pumps first: the icon is the user's only
    # lever and it must not wait on the model work. the detector build
    # (onnx session, the optional face gate) moves to _warm_monitor;
    # until it lands the monitor abstains from the camera (state._poll
    # checks detector is not None) and the tray menu carries honest
    # "probing..." placeholders where the slow submenus will be
    ui_events = queue.Queue()               # tray <-> window messages
    monitor = state.PresenceMonitor(cfg, None, None, ui_events=ui_events)
    icon = tray.Tray(monitor.events, cfg, ui_events=ui_events,
                     monitor=monitor)
    icon.start()                            # the tray always runs beside
                                            # the monitor
    monitor.notifier = icon.notify          # burst warnings reach the
                                            # user, not just the log
    monitor.tray_sink = icon.set_state      # and so does the state:
                                            # the tray art's holes ARE
                                            # the status (owner law)
    # Tk must own the main thread, so the monitor loop drops to a
    # worker; the same worker warms the detector before it starts
    # pumping, so a right-click or a quit in the tray is never lost
    # (queue puts hold until the first tick drains them)
    worker = threading.Thread(target=_warm_monitor,
                              args=(cfg, monitor), daemon=True,
                              name="monitor")
    worker.start()
    startup.selfheal()          # an old flagless Run entry learns
                                # the stamp here and now: only this
                                # copy touches the registry, and
                                # only after winning the instance
                                # race
    startup.ensure_crash_dumps()      # the no-dump blind spot (Oct 19
                                      # WER 1000 arrived empty: LocalDumps
                                      # never configured for pythonw)
    if cfg.get("restore", {}).get("enabled"):
        threading.Thread(target=_restore, args=(cfg, bool(autostart),
                                                icon), daemon=True,
                         name="restore").start()
    from . import gaming_watch       # lazy: only ever loads the pdh
    stop_gaming = threading.Event()  # counter when gaming is enabled
    threading.Thread(target=gaming_watch.loop,
                     args=(cfg, stop_gaming), daemon=True,
                     name="gaming").start()
    # the HDR auto-switch watcher (amendment 8): its own thread and
    # its own cadence - it never rides the duty poll, and the tick
    # costs one dict read while the tier map is empty (the default:
    # a virgin desk never loads a counter provider)
    stop_hdr = threading.Event()
    threading.Thread(target=monitor.hdr_watch,
                     args=(stop_hdr,), daemon=True,
                     name="hdr-watch").start()

    from . import tweaks             # fail-open: a denied key is a
    def _mirror_tweaks():            # one boot pass, then the
        log = logging.getLogger("tweaks")   # registry IS the state;
        try:                         # the UI applies changes
            rows = tweaks.fso_sync(
                (cfg.get("tweaks") or {}).get("fso_apps") or [])
            for action, exe, ok, err in rows:
                log.info("tweaks: %s %s%s", action, exe,
                         "" if ok else " FAILED: " + err)
        except Exception:
            log.debug("tweaks mirror died", exc_info=True)
    threading.Thread(target=_mirror_tweaks, daemon=True,   # log
                     name="tweaks").start()                # line
    stop_taskbar = threading.Event()
    if (cfg.get("taskbar") or {}).get("enabled"):
        from . import taskbar          # lazy: loads the shell pokes only
                                       # when the user turned the module on
        threading.Thread(target=taskbar.hover_watch,
                         args=(cfg, stop_taskbar), daemon=True,
                         name="taskbar").start()
    try:
        # the silent-death belt (Oct-15 dossier): a corpse with no
        # sign-off line left the hider's whole first UAT reading as a
        # bug when it was a death. Every departure from here names
        # itself - the return of _drive, not just its raises.
        _drive(cfg, monitor, worker, ui_events)
        logging.getLogger("cli").info(
            "the settings window closed; the tray lives on until the "
            "user quits it")
    except KeyboardInterrupt:
        logging.getLogger("cli").info("exiting: keyboard interrupt")
        monitor.events.put(("quit", True))
    except BaseException:
        logging.getLogger("cli").exception(
            "exiting: _drive raised; the tail below is the reason")
        raise
    finally:
        # a window crash must not pin the camera: stop the loop first
        stop_gaming.set()
        stop_taskbar.set()
        stop_hdr.set()
        monitor.events.put(("stop", True))
        monitor.quit = True        # latch NOW, before icon.stop: the
                                   # pump-exit check reads this flag and
                                   # a loop stuck in a 16-27 s driver
                                   # open drains "stop" only after the
                                   # tray is gone - the shutdown would
                                   # wear the dead-pump funeral costume
                                   # (third-gate ledger 1) on exactly
                                   # the desk it targets
        worker.join(3)
        if worker.is_alive():
            # the release is a HANDOFF, not a cross-thread grab
            # (final gate (b)/(e)): the loop's quit handler itself
            # does not release (_drain_tray only sets quit), so this
            # is the quit-time release - and a loop still alive may
            # sit in a 16-27 s driver open, mid its own release/vote
            # code. An unlocked cross-thread release from here was
            # the None.release() race in the first place. The OS
            # frees the device at exit; the LED-off is the loop's
            # while it runs.
            logging.getLogger("cli").info(
                "loop still winding down; its own release owns the cap")
        else:
            # loop confirmed stopped: no tick will ever touch
            # self.camera again, so the main thread owns the release
            # now - this is the sweep whose intent is the record LED
            # going honestly off at quit (the loop never releases on
            # its way out; this call always has)
            monitor._release_camera()
        icon.stop()                          # the tray stops after the run
    # the belt's other door: the tray pump exits on a "quit" event or
    # on its own death, and _drive parks on the worker while headless.
    # Either way THIS line is the app's last word; grep the log for it
    # and for the line above - whichever pair is missing names the
    # door the corpse left by (silent-death dossier, Oct 15).
    logging.getLogger("cli").info("exit: the run tail is done, the "
                                  "process ends now")
    return 0


def _warm_monitor(cfg, monitor):
    """The heavy init, off the main thread and off the tray pump:
    build the detector (the onnx session; motion mode never loads one)
    and the optional face gate, then start the monitor loop. the loop
    abstains from the camera until the detector lands (state._poll
    checks), so a poll can never hit a half-built monitor, and a tray
    event queued during the warm-up is drained by the first tick."""
    log = logging.getLogger("warm")
    try:
        from . import detector
        t0 = time.monotonic()
        monitor.detector = detector.build(cfg)
        if cfg["faces"]["enabled"]:
            from . import faces as faces_module
            monitor.faces = faces_module.FaceGate()
        log.info("warm: detector ready in %.1f s; the monitor starts "
                 "pumping", time.monotonic() - t0)
    except Exception as exc:
        # faces without its optional package is NOT a detector failure
        # (audit W2C MED): FaceGate raises RuntimeError naming
        # 'insightface' and it used to exit under the misleading "the
        # detector would not build" banner. Deprompt wants a mapped Tk
        # parent and this warm pass runs on a worker thread (widget
        # calls would cross the Tcl thread), so the packet's else
        # branch is the law here: the honest self-dying box from this
        # module, naming the missing extra.
        if isinstance(exc, RuntimeError) and "insightface" in str(
                exc).lower():
            timeout_notice("PanelBoss stops here: faces are enabled but "
                           "the optional extra 'insightface' is missing.\n"
                           "Install it (pip install insightface) or turn "
                           "faces off; a monitor with faces ON and the "
                           "dep MISSING must not run half-blind.",
                           ms=15000)
            log.exception("warm: faces enabled, insightface missing; "
                          "the app drains a quit and exits")
        elif "expected detection head" in str(exc):
            # gate MED (ledger 2): validate_head's raise was right,
            # its REACH was the bug - a wrong-head .onnx fell into the
            # bare-else log line and the app quit with no confession.
            # The validator's message is the match (it says "expected
            # detection head" verbatim); same box discipline, same
            # quit semantics - the exit is now seen, with the fix.
            timeout_notice("PanelBoss stops here: the model file is not "
                           "a supported detector - " + str(exc) + ".\n"
                           "Replace the .onnx or set [inference] model "
                           "to a YOLO detection model.", ms=15000)
            log.exception("warm: the onnx head is not a detection head; "
                          "the app drains a quit and exits")
        else:
            # the old no-model behavior was death; the new one is the same
            # exit, seen: the tray stays up, the loop drains the quit and
            # the window closes after it
            log.exception("warm: the detector would not build; the app "
                          "drains a quit and exits")
        monitor.events.put(("quit", True))
    monitor.run()


def _restore(cfg, autostart, icon):
    """The pre-armed lever: apply a profile at app start. The logon
    copy (the one the Run entry stamped --autostart) applies with
    the grace profiles.py builds in; a manual start only obeys when
    the user chose "every app start". Own thread because an apply
    outlasts any UI (verify polls, relaunch waits), and the
    announcement is balloons: at logon nobody is watching the
    window yet, and a modal dialog at logon is a hostage."""
    log = logging.getLogger("restore")
    try:
        want = cfg.get("restore", {})
        if want.get("when", "autostart") == "autostart" and not autostart:
            log.info("restore: manual start, and the box says "
                     "autostart only")
            return
        fresh = True
        if autostart:
            age = _session_age_sec()
            if age is None:
                log.debug("restore: session age unread; trusting the "
                          "stamp")           # fail open: a real login
                #                      must not lose its ceremony to
                #                      an unreadable clock
            elif age > LOGIN_FRESH_SEC:
                fresh = False                # the stamp lied (or an
                log.info("restore: autostart stamp on a %d s old "
                         "session - a relaunch wearing a login "
                         "costume; no ceremony", int(age))
                if want.get("when", "autostart") == "autostart":
                    return                   # owner asked for LOGON
                    #                        starts only: this is not
                    #                        one
        time.sleep(5)              # let the first dust settle; the
                                   # rest of the storm waits inside
                                   # apply, before any launch
        from . import profiles
        data = profiles.load()
        name = want.get("profile") or "last"
        if name == "last":
            name = profiles.name_for_desk(data, profiles.wm.monitors())
            if name is None:
                # third-gate ledger 13: symmetry with the named-gone
                # path below - a login restore that found nothing to
                # restore is at least as surprising as a gone profile,
                # and a log line under pythonw is no notice at all
                log.info("restore: no profile answers this desk yet")
                icon.notify("profile restore: this desk has no "
                            "profile yet - nothing restored at login")
                return
        if name not in data.get("profiles", {}):
            log.info("restore: profile '%s' is gone", name)
            icon.notify("profile restore: '%s' is gone" % name)
            return
        ok, say, info = profiles.apply(data, name,
                                       scope=want.get("scope") or "full",
                                       login=bool(autostart and fresh))
        lg = info.get("login") or {}
        if lg.get("delay_next"):
            say += " ; next login sits out %d s first" % lg["delay_next"]
        log.info("restore '%s' (%s): %s [%s]", name,
                 "login" if (autostart and fresh) else "manual", say,
                 "ok" if ok else "not ok")
        icon.notify("profile restore: %s" % say[:180])
        missing = sorted({m["proc"] or m["title"]
                          for m in info.get("no_shows", [])})
        if missing:
            # no dialog at logon: the misses ride the balloon, and
            # the pins stay loud for the next apply a human watches
            icon.notify("still missing: %s" % ", ".join(missing)[:160])
    except Exception:
        log.exception("startup restore failed (app carries on)")


def _drive(cfg, monitor, worker, ui_events):
    """The main thread either runs the window or parks for headless."""
    from . import ui
    if cfg["ui"].get("enabled", True) and ui.is_available():
        try:
            ui.run(cfg, monitor, ui_events)   # blocks until the window
        except Exception:                     # dies; pythonw has no
            logging.getLogger("ui").exception(  # stderr: a traceback
                "settings window died")       # must reach the log
            timeout_notice("settings window died: see the log",
                           ms=10000)          # a dead window is not
                                              # just a log line
            return                            # the caller's belt would
                                              # call this "closed" and
                                              # be wrong (silent-death
                                              # dossier, Oct 15)
    else:
        logging.getLogger("cli").info("no ui; running headless beside the "
                                       "tray")
        while worker.is_alive():             # headless: park main, let
                                             # the tray be the only
                                             # lever - and the ONLY
                                             # STATUS LIGHT: without
                                             # the ui tick the sink
                                             # has no other caller, so
                                             # this park feeds it (the
                                             # gate's finding 1: the
                                             # law "the holes ARE the
                                             # status" may not be false
                                             # in exactly the mode the
                                             # tray IS the ui). The
                                             # sink is diff-guarded -
                                             # an unchanged beat costs
                                             # an attribute read.
            sink = getattr(monitor, "tray_sink", None)
            if sink is not None:
                try:
                    sink(monitor.state)
                except Exception:
                    pass                    # a lost beat recolors on
                                            # the next; the swallow is
                                            # set_state's own rule too
            worker.join(0.5)


def _enroll(cfg, name):
    if not cfg["faces"]["enabled"]:
        print("set faces.enabled = true in the config first")
        return 1
    from . import faces as faces_module
    from . import camera, detector          # dead-on-arrival since
                                            # birth: this fn referenced
                                            # both modules unimported
                                            # (3-channel audit + final
                                            # gate) - panelboss enroll
                                            # died NameError whenever
                                            # faces.enabled was true
    gate = faces_module.FaceGate()
    det = detector.PersonDetector(
        model=cfg["inference"]["model"],
        device=cfg["inference"]["device"],
        device_id=cfg["inference"]["device_id"],
        conf=cfg["inference"]["confidence"])
    cam = camera.open_camera(cfg["camera"])
    cam.warm_up()                           # the exposure settles first
    frame = cam.read()
    cam.release()
    name = name or input("name for this face: ")
    print(gate.enroll(frame, name), "enrolled")
    return 0


def _faces(cfg):
    from . import faces as faces_module
    try:
        gate = faces_module.FaceGate()
    except RuntimeError as e:
        print(e)
        return 1
    for name in gate.stored:
        print(" ", name)
    return 0
