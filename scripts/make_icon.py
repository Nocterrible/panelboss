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
from PIL import Image, ImageDraw, ImageFilter       # noqa: E402

PAGE = "#17181A"        # theme.py PAGE
FRAME = "#3a3f44"       # the LED bezel
SCREEN = "#0e2a33"      # a screen at rest (status color swaps in here)
SHADES = "#f2f4f5"      # the glasses
SIZES = (16, 24, 32, 48, 64, 128, 256)
EXT_SIZES = (16, 32, 48, 128)
MASTER = 1024


def _fill_holes(im, rest="#f2f4f5", min_area_pct=1.0):
    """Pixel-art-aware screen fill: every TRANSPARENT REGION that does
    not touch the image border is a hole (the owner's art makes the
    screen - and the lens interiors, which read THROUGH the glasses -
    one design: they color together). Fill each hole big enough to
    matter with the rest color; the outside world stays transparent
    for the shells. A hole the size of the art (missed alpha, e.g. a
    flattened clipboard grab) fails the border test and is left
    alone - the checkerboard impostor cannot sneak through."""
    w, h = im.size
    px = im.load()
    seen = bytearray(w * h)
    total = w * h
    rest_rgb = tuple(int(rest[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
    for i in range(total):
        if seen[i] or px[i % w, i // w][3] >= 128:
            continue
        # BFS this transparent component
        comp = [i]
        seen[i] = 1
        touches = False
        q = 0
        while q < len(comp):
            p = comp[q]
            q += 1
            x, y = p % w, p // w
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1),
                           (x, y + 1)):
                if not (0 <= nx < w and 0 <= ny < h):
                    touches = True
                    continue
                n = ny * w + nx
                if seen[n] or px[nx, ny][3] >= 128:
                    continue
                seen[n] = 1
                comp.append(n)
        if touches or len(comp) * 100.0 < min_area_pct * total:
            continue
        for p in comp:
            px[p % w, p // w] = rest_rgb
    return im


def _rescue_alpha(im):
    """Flattened-art rescue (the Oct 17 lesson: the owner's export
    route hands over a JPG - alpha baked into a checkerboard). The
    art's palette makes the keying trivial: every DARK neutral pixel
    (value < 130) is the art itself (its grays run black..charcoal);
    every LIGHT neutral (>= 130) is the baked checkerboard - the two
    tones were (200,200,200) and (255,255,255), and the file carries
    zero colored pixels, so no watermark competes for the light end.
    A pixel cannot be both art and light-neutral here; if a future
    master introduces pale art, the key gets palette input instead
    of folklore. Returns the RGBA image with real alpha restored."""
    w, h = im.size
    px = im.load()
    out = Image.new("RGBA", (w, h))
    o = out.load()
    keyed = 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y][:3]
            if max(r, g, b) - min(r, g, b) <= 24 and min(r, g, b) >= 90:
                o[x, y] = (0, 0, 0, 0)     # transparency returns
                keyed += 1
            else:
                o[x, y] = (r, g, b, 255)
    print("rescued alpha: %d of %d px keyed back to transparent"
          % (keyed, w * h))
    return out


def draw_master():
    """The owner's master (assets/master.png, or a flattened
    assets/master.jpg that gets its alpha rescued - both centered
    and square-coerced), else the programmatic interim draw below."""
    png = os.path.join("assets", "master.png")
    jpg = os.path.join("assets", "master.jpg")
    src = png if os.path.isfile(png) else (jpg if os.path.isfile(jpg)
                                           else None)
    if src is not None:
        im = Image.open(src)
        hist = im.convert("RGBA").getchannel("A").histogram()
        has_alpha = sum(hist[:255]) > 0      # any non-opaque px at all
        im = im.convert("RGBA")
        if src == jpg or not has_alpha:
            # median BEFORE keying: JPEG ringing around the baked
            # checkerboard sits in the art's own charcoal band and
            # would survive the key as speckle; a 3x3 majority pass
            # erases the ringing (which is thin) and keeps the art
            # (whose strokes at this size are thick).
            im = im.filter(ImageFilter.MedianFilter(3))
            im = _rescue_alpha(im.convert("RGB"))
        s = min(im.size)
        im = im.crop(((im.width - s) // 2, (im.height - s) // 2,
                      (im.width - s) // 2 + s,
                      (im.height - s) // 2 + s))
        return _fill_holes(im)
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
        # BOX (area average) not LANCZOS: pixel art must NOT be
        # blur-downsampled; integer sizes stay crisp, 48 is close
        # enough for the eye
        im.resize((s, s), Image.BOX).save(
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
