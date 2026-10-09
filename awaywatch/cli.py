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
    return _run(cfg)                        # the monitor runs last


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


def _run(cfg):
    from . import detector
    from . import state
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
    try:
        _drive(cfg, monitor, worker, ui_events)
    except KeyboardInterrupt:
        monitor.events.put(("quit", True))
    finally:
        # a window crash must not pin the camera: stop the loop first
        monitor.events.put(("stop", True))
        worker.join(3)
        monitor._release_camera()
        icon.stop()                          # the tray stops after the run
    return 0


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
