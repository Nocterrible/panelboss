"""Command line.

run is the default command and is always started first;
cameras, preview, config and faces are diagnostics.
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import queue
import sys
import threading
import time

from . import config


def main(argv=None):
    parser = argparse.ArgumentParser(prog="awaywatch")
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


def _single_instance():
    """Named mutex; a second copy exits before touching the camera.
    The handle and ownership always come before the name."""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                        ctypes.c_wchar_p]
    kernel32.CreateMutexW(0, False, "ICU-Presence-Detector")
    return kernel32.GetLastError() != 183        # ERROR_ALREADY_EXISTS


def _run(cfg, autostart=False):
    from . import detector
    from . import state
    from . import startup
    from . import tray

    if not _single_instance():
        logging.getLogger("cli").info("already running; one instance is "
                                       "always checked first")
        user32 = ctypes.windll.user32
        user32.MessageBoxTimeoutW(0,
            "ICU Presence Detector is already running (check the tray, "
            "hidden icons live behind the chevron). One instance is "
            "always started first.",
            "ICU Presence Detector", 0x40,      # MB_ICONINFORMATION
            5000,                                 # closes on its own
            ctypes.byref(ctypes.c_uint()))
        return 0

    det = detector.build(cfg)     # mode-aware: motion never loads onnx
    faces = None
    if cfg["faces"]["enabled"]:
        from . import faces as faces_module
        faces = faces_module.FaceGate()
    ui_events = queue.Queue()               # tray <-> window messages
    monitor = state.PresenceMonitor(cfg, det, faces, ui_events=ui_events)
    icon = tray.Tray(monitor.events, cfg, ui_events=ui_events)
    icon.start()                            # the tray always runs beside
                                            # the monitor
    monitor.notifier = icon.notify          # burst warnings reach the
                                            # user, not just the log
    # Tk must own the main thread, so the monitor loop drops to a
    # worker; display (its own thread) and tray are untouched.
    worker = threading.Thread(target=monitor.run, daemon=True,
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
    try:
        _drive(cfg, monitor, worker, ui_events)
    except KeyboardInterrupt:
        monitor.events.put(("quit", True))
    finally:
        # a window crash must not pin the camera: stop the loop first
        stop_gaming.set()
        monitor.events.put(("stop", True))
        worker.join(3)
        monitor._release_camera()
        icon.stop()                          # the tray stops after the run
    return 0


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
                                       login=bool(autostart))
        lg = info.get("login") or {}
        if lg.get("delay_next"):
            say += " ; next login sits out %d s first" % lg["delay_next"]
        log.info("restore '%s' (%s): %s [%s]", name,
                 "login" if autostart else "manual", say,
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
