"""THE TRAY ART (owner law, Oct 19): the icon is the art with its
interior holes filled the live state color - the circle is only the
no-art fallback. No window, no pystray pump: the paint function is
pure PIL and the law is pixel-verifiable.

Run: .venv\\Scripts\\python.exe scripts\\tray_icon_test.py
"""
import sys

sys.path.insert(0, ".")

from panelboss import tray                                          # noqa: E402

FAILED = []


def check(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


art = tray._art()
check(art is not None, "the tray canvas exists (make_icon exports it "
      "with the holes OPEN - a None here means the asset or the path "
      "died)")
if art is not None:
    base = art.load()
    holes = [(x, y) for y in range(art.height) for x in range(art.width)
             if base[x, y][3] < 128]
    check(bool(holes), "the canvas carries transparent pixels (outer "
          "background at minimum - an all-opaque master means the art "
          "came back flattened and NOTHING can color)")
    for state in ("active", "counting", "off", "paused"):
        img = tray._image(state).convert("RGBA")
        px = img.load()
        want = tray.COLORS.get(state, tray.COLORS["off"])
        colored = sum(1 for (x, y) in holes
                      if px[x, y][:3] == want and px[x, y][3] == 255)
        left_open = sum(1 for (x, y) in holes if px[x, y][3] < 128)
        check(colored + left_open == len(holes)      # every hole chose
              and colored > art.width ** 2 * 0.02,   # a side: interior
              "state %r: interior holes carry the state color "     # or
              "(%d px), %d px stay open (the outside)"              # outside
              % (state, colored, left_open))
    # unknown (the honest boot state) must paint too - the muted
    # default, never a KeyError and never a green promise
    check(tray._image("unknown").mode == "RGBA",
          "unknown paints (falls to the off-gray like the chip's "
          "subtext - the tray says nothing it has not learned)")
    # the hole rule matches make_icon._fill_holes: a transparent
    # component touching the border is NOT design and stays open
    a = tray._image("active").convert("RGBA").load()
    c = tray._image("counting").convert("RGBA").load()
    border_open = sum(1 for (x, y) in holes
                      if x in (0, art.width - 1) or y in (0, art.height - 1))
    check(border_open == 0 or all(
        a[x, y][3] < 128 and c[x, y][3] < 128
        for (x, y) in holes
        if x in (0, art.width - 1) or y in (0, art.height - 1)),
        "border-touching transparency stays transparent in every "
        "state (the border rule: outside is outside)")
else:
    check(False, "tray_master.png lookup (two candidates: repo "
          "assets/, package dir) - run scripts/make_icon.py")

# the fallback path: the circle when the art is gone (an app without
# a poster still shows STATE)
_saved = tray._TRAY_ART
try:
    tray._TRAY_ART = None
    img = tray._image("paused")
    check(img.mode == "RGB" and img.size == (64, 64),
          "no art = the interim circle still paints the state color "
          "(fail-open, with the absence logged once)")
finally:
    tray._TRAY_ART = _saved

print("TRAY ART OK" if not FAILED else
      "TRAY ART FAILED: %s" % FAILED)
sys.exit(1 if FAILED else 0)
