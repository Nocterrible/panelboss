"""Live-tool, NOT in run_all (it flickers the owner's desk twice -
the gauntlet must never do that): the amendment-8 round trip plus
the WM_DISPLAYCHANGE ear check on the real driver. Run by hand when
someone is watching the screens."""
import sys
import time

sys.path.insert(0, ".")

from panelboss import display, wm  # noqa: E402

rows = wm.hdr_states()
print("hdr_states:")
for r in rows:
    print("  %-14s supported=%-5s state=%-7s precise=%s"
          % (r["model"] or "?", r["supported"], r["state"], r["precise"]))
cap = next((r for r in rows if r.get("supported") and r.get("precise")),
           None)
if cap is None:
    print("no capable readable panel - round trip impossible HERE; "
          "honest exit 0")
    sys.exit(0)

d = display.Display(verbose=False)
d.start()
time.sleep(0.5)

start = cap["state"]
want = start != "on"
print("flip: %s -> %s" % (start, "on" if want else "off"))
say = wm.hdr_set(cap["gdi"], want)
print("set: %r" % say)
time.sleep(2.0)
back = {r["model"]: r for r in wm.hdr_states()}[cap["model"]]["state"]
print("read-back: %s  (wanted %s)" % (back, "on" if want else "off"))
say2 = wm.hdr_set(cap["gdi"], start == "on")
print("restore: %r" % say2)
time.sleep(1.0)
end = {r["model"]: r for r in wm.hdr_states()}[cap["model"]]["state"]
print("restored: %s" % end)
time.sleep(0.5)
got = []
while True:
    try:
        got.append(d.queue.get_nowait())
    except Exception:
        break
dc = [g for g in got if g[0] == "displaychange"]
print("queue: %r" % (got,))
d.stop()
ok = (back == ("on" if want else "off")) and end == start and dc
print("ROUND TRIP OK" if ok else "LIVE CHECK FAILED")
sys.exit(0 if ok else 1)
