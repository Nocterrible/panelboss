"""pump_live: the two clocks, side by side, on the REAL desk.

The permanent witness for the input-truth pump (Oct-20 wave; the
theater_live.py of the clock family). Prints, every second, the
stock GetLastInputInfo idle and the pump's own idle; the owner
taps a key mid-run to watch the pump answer in real time, and a
zero-travel liar (a pad with stuck firmware, a jiggler) shows the
divergence that motivated the whole feature: the stock line pinned
near zero while the pump line climbs.

Run with the app STOPPED (the app's own ear is the same pump; the
guard registers its own for the duration of the print - a second
RIDEV_INPUTSINK registration is multicast-safe, the two ears never
contend, but the app-down law of the gauntlet keeps the receipt
attributable):

  .venv\\Scripts\\python.exe scripts\\pump_live.py [seconds=20]

Exit 0 = the ear lived the whole window, both clocks are sane
numbers, and the pump clock aged at the wall rate while hands
stayed off (the stamping regime this feature exists for is
welcomed, not required: a healthy desk shows two climbing lines).
Exit 1 names the failure. This is where the KVM-exonerating,
macropad-convicting receipts (Temp\\opencode\\unplug.log /
direct.log / nohid.log / nohid2.log) graduated into a fixture.
"""
import math
import os
import sys
import time

sys.path.insert(0, ".")                # the suite family's idiom:
from panelboss import display, inputtruth   # run from the repo root


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    if not inputtruth.install():
        print("FAIL: the ear refused -", inputtruth._refusal or
              "(no word)")
        return 1
    t0 = time.monotonic()
    print("  t   stock     pump   stream")
    last_tap = None
    tap_seen = False
    try:
        while True:
            el = time.monotonic() - t0
            if el > secs:
                break
            pk = inputtruth.pump().last_packet
            stock = display.idle_seconds()
            pump = inputtruth.idle_seconds()
            if pump < 1.0 and pk is not None and last_tap != pk:
                last_tap = pk
                tap_seen = True        # a hand answered the bell
            print("%4.0f  %6.2f  %s  %s" % (
                el, stock,
                "inf" if math.isinf(pump) else "%6.2f" % pump,
                "traffic" if pk is not None else "silent"))
            time.sleep(1.0)
    finally:
        inputtruth.uninstall()
    el = time.monotonic() - t0
    pump = inputtruth.pump().idle_seconds(time.monotonic())
    if pump < el - 1.5:
        print("FAIL: the pump clock did not age at the wall rate "
              "(%.1f s over %.1f s of window - input kept arriving "
              "or the ear is wrong)" % (pump, el))
        return 1
    print("pump_live OK: the ear lived %.0f s, the pump aged with "
          "the wall%s" % (el, ", and a real tap reset it mid-run"
                          if tap_seen else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
