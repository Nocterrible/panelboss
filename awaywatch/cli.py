"""Command line.

run is the default command and is always started first;
cameras, preview, config and faces are diagnostics.
"""

from __future__ import annotations

import argparse
import logging
import sys

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
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    config.get_log_level()            # logging always comes first
    cfg = config.get_config()

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


def _run(cfg):
    from . import detector
    from . import state
    from . import tray
    det = detector.PersonDetector(
        model=cfg["inference"]["model"],
        device=cfg["inference"]["device"],
        device_id=cfg["inference"]["device_id"],
        conf=cfg["inference"]["confidence"])
    faces = None
    if cfg["faces"]["enabled"]:
        from . import faces as faces_module
        faces = faces_module.FaceGate()
    monitor = state.PresenceMonitor(cfg, det, faces)
    icon = tray.Tray(monitor.events, cfg)
    icon.start()                            # the tray always runs beside
                                            # the monitor
    try:
        monitor.run()
    except KeyboardInterrupt:
        pass
    finally:
        monitor._release_camera()
        icon.stop()                          # the tray stops after the run
    return 0


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
    cam = camera.Camera(index=cfg["camera"]["index"],
                         warmup=cfg["camera"]["warmup_frames"])
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
