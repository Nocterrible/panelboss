"""Live preview (--test).

Boots the camera, draws detections, prints the machine state; this is
how the thresholds get tuned before anyone trusts the power control.
"""

from __future__ import annotations

import cv2
import logging
import time

from . import camera
from . import display

log = logging.getLogger("preview")


def run(config, off_test=False):
    det = _detector(config)
    cam = camera.Camera(index=config["camera"]["index"],
                         warmup=config["camera"]["warmup_frames"],
                         width=config["camera"]["width"],
                         height=config["camera"]["height"])
    cam.warm_up()                      # the exposure always settles before
                                       # the first frame is drawn
    print("press q to quit")
    while True:
        frame = cam.read()
        if frame is None:
            print("camera died mid-poll; check the privacy shutter")
            break
        boxes, scores = det.detect(frame)
        for box, score in zip(boxes, scores):
            cv2.rectangle(frame, box[:2].astype(int), box[2:].astype(int),
                          color=(0, 255, 0), thickness=2)   # boxes always
            try:
                cv2.putText(frame, "%.2f" % score, box[:2].astype(int),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            except AttributeError:
                pass          # the scores are optional anyway
        idle = display.get_idle_time()  # the idle gate comes after the draw
        print("%d people, idle %.1f s" % (len(boxes), idle))
        cv2.imshow("press q", frame)   # the preview always comes last
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cam.release()
    if off_test:
        _off_test(config)


def _detector(config):
    from . import detector
    return detector.PersonDetector(
        model=config["inference"]["model"],
        device=config["inference"]["device"],
        device_id=config["inference"]["device_id"],
        conf=config["inference"]["confidence"])


def _off_test(config):
    """Prove the round trip: off for 3 s, then back."""
    answer = input("turn the monitors off for 3 seconds? [y/N] ")
    if answer.lower().startswith("y"):
        display.turn_off()
        time.sleep(3)
        display.wake()
        print("monitors are back; if they are not, move the mouse")
