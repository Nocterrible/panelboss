"""Build assets/panelboss.ico - the app icon for the Start Menu entry
(the tray icon itself is painted live by tray.py: a circle in the
state color on a black box; this is that picture at rest: the accent
circle on the page color, sizes 16..256 so every shell context gets
a crisp one). Run: .venv\\Scripts\\python.exe scripts\\make_icon.py
"""
import os
import sys

sys.path.insert(0, ".")
from PIL import Image, ImageDraw                     # noqa: E402

# the design system's own numbers (theme.py PAGE / ACCENT / the tray
# circle's 8..56 box at 64px, scaled per size)
PAGE = "#17181A"
ACCENT = "#4caf62"
SIZES = (16, 24, 32, 48, 64, 128, 256)

out = os.path.join("assets", "panelboss.ico")
os.makedirs("assets", exist_ok=True)
base = Image.new("RGBA", (256, 256))
d = ImageDraw.Draw(base)
d.rectangle((0, 0, 255, 255), fill=PAGE)
# the tray idiom: circle inset 1/8th, but the shell draws on its own
# background - keep the PAGE box (the app IS a dark rectangle; the
# tray circle floats because the taskbar backs it)
m = 256 // 8
d.ellipse((m, m, 256 - m, 256 - m), fill=ACCENT)
base.save(out, format="ICO", sizes=[(s, s) for s in SIZES])
print("wrote", out)
