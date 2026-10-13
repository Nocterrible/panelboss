"""Command line.

run is the default command and is always started first;
cameras, preview, config and faces are diagnostics.
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
import queue
import sys
import threading
import time

from . import config


def main(argv=None):
    parser = argparse.ArgumentParser(prog="panelboss")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "cameras", "preview", "config",
                                "enroll", "faces"])
    parser.add_argument("--off-test", action="store_true",
                        help="prove the monitor round trip; always the last "
                             "check before trusting the power control")
    parser.add_argument("--name", default="", help="identity to enroll")
    parser.add_argument("--index", type=int, default=None,
                        help="camera index; overrides the config file")
    parser.add_argument("--no-ui", action="store_true",
                        help="start headless; the tray alone")
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
    # os, not sys: this box's 3.10 build ships a trimmed sys module
    # without getpid (the tray app has been on os.getpid all along)
    # The tree + cli.py mtime ride along: a hard-killed icon lingers as
    # a ghost until Explorer's next notification refresh, so a stale
    # instance is otherwise provenance-less -- and a relaunch that
    # quietly loses the mutex lets the old one impersonate the new.
    # This line names where the running app was ACTUALLY loaded from.
    _here = os.path.dirname(os.path.abspath(__file__))
    logging.getLogger("cli").info(
        "panelboss 0.1.0 boot (pid %s, tree %s, code from %s)",
        os.getpid(), _here,
        time.strftime("%H:%M", time.localtime(
            os.path.getmtime(os.path.join(_here, "cli.py")))))
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
        # .value FIRST: szExeFile is a c_wchar_Array, which has no
        # .lower() - the direct call raised AttributeError EVERY
        # iteration, and the caller's catch turned the whole login
        # stamp probe into silent None (found by the audit's adjacent
        # line-probe; this function has never once run clean)
        if pe.szExeFile.value.lower() == "explorer.exe":
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


def _run(cfg, autostart=False):
    from . import state
    from . import startup
    from . import tray

    if not _single_instance():
        logging.getLogger("cli").info("already running; one instance is "
                                       "always checked first")
        if not autostart:
            # a logon launch must never speak: if an old copy somehow
            # survived the shutdown, the twin's only sound is the log
            # line above. Interactive launches get the box so a double
            # click explains itself.
            user32 = ctypes.windll.user32
            user32.MessageBoxTimeoutW.restype = ctypes.c_int
            user32.MessageBoxTimeoutW.argtypes = [
                ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                ctypes.c_uint, ctypes.c_ushort, ctypes.c_uint]
            # signature is (hwnd, text, caption, type, wLangID, dwTimeout):
            # the FIRST cut passed 5000 in the language slot and a
            # byref(c_uint) in the timeout slot (TaskDialog shape, not
            # MessageBox) so the timeout read as a huge pointer value and
            # the twin's box never self-dismissed (measured). Correct
            # order now: default language 0, timeout 5000 ms.
            user32.MessageBoxTimeoutW(0,
                "PanelBoss is already running (check the tray, "
                "hidden icons live behind the chevron). One instance is "
                "always started first.",
                "PanelBoss", 0x40, 0, 5000)         # MB_ICONINFORMATION
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
    if cfg.get("restore", {}).get("enabled"):
        threading.Thread(target=_restore, args=(cfg, bool(autostart),
                                                icon), daemon=True,
                         name="restore").start()
    from . import gaming_watch       # lazy: only ever loads the pdh
    stop_gaming = threading.Event()  # counter when gaming is enabled
    threading.Thread(target=gaming_watch.loop,
                     args=(cfg, stop_gaming), daemon=True,
                     name="gaming").start()

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
        _drive(cfg, monitor, worker, ui_events)
    except KeyboardInterrupt:
        monitor.events.put(("quit", True))
    finally:
        # a window crash must not pin the camera: stop the loop first
        stop_gaming.set()
        stop_taskbar.set()
        monitor.events.put(("stop", True))
        worker.join(3)
        monitor._release_camera()
        icon.stop()                          # the tray stops after the run
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
    except Exception:
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
                log.info("restore: no profile answers this desk yet")
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
    else:
        logging.getLogger("cli").info("no ui; running headless beside the "
                                       "tray")
        while worker.is_alive():             # headless: park main, let
            worker.join(0.5)                 # the tray be the only lever


def _enroll(cfg, name):
    if not cfg["faces"]["enabled"]:
        print("set faces.enabled = true in the config first")
        return 1
    from . import faces as faces_module
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
