"""Build the app's icon ladder from ONE drawn master (Oct 17).

The interim master is a programmatic draw of the owner's concept -
an LED screen with sunglasses; the screen interior is where a real
status color lands when the art arrives. This module is the seam:
regenerate every size from a replacement assets/master.png the day
real art exists (draw_master() steps aside for it), or edit the
draw below. Outputs, one run:

  assets/panelboss.ico            shell/Start-menu ladder (16..256)
  extension/icons/{16,32,48,128}.png   the Chrome Web Store ladder

(The tray icon is painted live by tray.py - the circle in the state
color - this is the same picture's calmer siblings for the shells
that want files.) Run: .venv\\Scripts\\python.exe scripts\\make_icon.py
"""
import json
import os
import sys

sys.path.insert(0, ".")
from PIL import Image, ImageDraw                     # noqa: E402

PAGE = "#17181A"        # theme.py PAGE
FRAME = "#3a3f44"       # the LED bezel
SCREEN = "#0e2a33"      # a screen at rest (status color swaps in here)
SHADES = "#f2f4f5"      # the glasses
SIZES = (16, 24, 32, 48, 64, 128, 256)
EXT_SIZES = (16, 32, 48, 128)
MASTER = 1024


def draw_master():
    """The interim art, or the owner's master.png when it exists
    (assets/master.png at any size, coerced to square RGBA)."""
    path = os.path.join("assets", "master.png")
    if os.path.isfile(path):
        im = Image.open(path).convert("RGBA")
        s = min(im.size)
        return im.crop(((im.width - s) // 2, (im.height - s) // 2,
                        (im.width - s) // 2 + s,
                        (im.height - s) // 2 + s))
    im = Image.new("RGBA", (MASTER, MASTER))
    d = ImageDraw.Draw(im)
    r = MASTER // 8
    d.rounded_rectangle((0, 0, MASTER - 1, MASTER - 1), radius=r,
                        fill=PAGE)
    # the LED bezel: outer frame + interior
    m = MASTER // 7
    d.rounded_rectangle((m, m, MASTER - m, MASTER - m),
                        radius=MASTER // 20, fill=FRAME)
    b = MASTER // 40                       # bezel stroke
    d.rounded_rectangle((m + b, m + b, MASTER - m - b, MASTER - m - b),
                        radius=MASTER // 28, fill=SCREEN)
    # sunglasses, centered on the screen: two lenses + bridge
    cy = MASTER // 2
    lw, lh = int(MASTER * 0.24), int(MASTER * 0.13)
    gap = int(MASTER * 0.05)
    lr = int(lh * 0.45)
    x1 = MASTER // 2 - gap // 2 - lw
    x2 = MASTER // 2 + gap // 2
    y0 = cy - lh // 2
    for x0, x1_ in ((x1, x1 + lw), (x2, x2 + lw)):
        d.rounded_rectangle((x0, y0, x1_, y0 + lh), radius=lr,
                            fill=SHADES)
    d.rounded_rectangle((x1 + lw - 2, cy - MASTER // 80,
                         x2 + 2, cy + MASTER // 80),
                        radius=MASTER // 160, fill=SHADES)
    # temples: short arms to the bezel, reads even at 16 px
    t = MASTER // 50
    d.rectangle((m + b, cy - t // 2, x1, cy - t // 2 + t), fill=SHADES)
    d.rectangle((x2 + lw, cy - t // 2, MASTER - m - b,
                 cy - t // 2 + t), fill=SHADES)
    return im


def main():
    im = draw_master()
    os.makedirs("assets", exist_ok=True)
    im.save(os.path.join("assets", "panelboss.ico"), format="ICO",
            sizes=[(s, s) for s in SIZES])
    print("wrote assets/panelboss.ico")
    out = os.path.join("extension", "icons")
    os.makedirs(out, exist_ok=True)
    for s in EXT_SIZES:
        im.resize((s, s), Image.LANCZOS).save(
            os.path.join(out, "icon%d.png" % s))
    print("wrote extension/icons/", ", ".join(
        "icon%d.png" % s for s in EXT_SIZES))
    # the manifest's icons block: written, not wished
    mpath = os.path.join("extension", "manifest.json")
    m = json.load(open(mpath, encoding="utf-8"))
    m["icons"] = {str(s): "icons/icon%d.png" % s for s in EXT_SIZES}
    with open(mpath, "w", encoding="utf-8", newline="") as f:
        f.write(json.dumps(m, indent=2) + "\n")
    print("manifest icons block written")


if __name__ == "__main__":
    main()
