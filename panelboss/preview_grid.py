"""The preview mosaic: one tile per camera, built in plain PIL.

The live preview used to show one rotating frame; this is the wall
view. Frames arrive as PIL images (or None for an eye that has no
picture right now), tiles pack in ROSTER ORDER - the dict's own order
- left to right, `cols` per row. A roster that does not fill its last
row leaves a plain hole (three cams at two cols is a 2x2 with one
empty slot, never a reshuffle).

Deliberately headless: no tkinter, no cv2, no cameras, no config -
the compose is a pure image function, so it tests with nothing but an
image, and the monitor thread feeds its result into the SAME one-slot
framebox the single-camera preview already uses; the settings window
draws whatever arrives and never learns the difference.

An empty tile does not freeze and does not go black in silence: it
states its reason ("opening", "closed", "off", "degraded poll"), and
the header strip above every tile names what the eye IS, so a tile can
never fake a mode it is not running in.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

HEADER_H = 22                 # the strip carrying "index  label"
PAD = 6                       # header/placeholder inset
BG = (16, 16, 20)             # the gap between tiles: every skin's dark
HEADER_BG = (30, 30, 38)
INK = (220, 220, 226)         # header text AND placeholder text: the
                              # old ~9 px dark-gray read as DEAD (the
                              # owner's "cam 2 black")
FALLBACK_AR = 9 / 16          # tile shape when no frame is there to say


def _readable_font():
    """Oct 12: the default bitmap font at ~9 px made every placeholder
    and header illegible on a near-black wall. load_default(size) (the
    properly rendered scaled face) needs Pillow 10.1+, which this venv
    carries (12.3); the truetype and bitmap arms keep the module
    honest on an older Pillow instead of crashing the wall."""
    try:
        return ImageFont.load_default(size=16)
    except TypeError:
        pass
    try:
        return ImageFont.truetype("segoeui.ttf", 14)
    except OSError:
        return ImageFont.load_default()


FONT = _readable_font()
_FONT_H = FONT.getmetrics()[0] + FONT.getmetrics()[1]   # header centering


def compose(frames, labels, tile_w, cols=2):
    """frames: {index: PIL image or None}, iteration order IS roster
    order. labels: {index: short truth string} - shown in the header,
    and centered into the tile when there is no frame. Returns one
    PIL image, or None when there is no tile at all."""
    indexes = list(frames)
    if not indexes:
        return None
    cols = max(1, int(cols))
    # a non-positive tile_w is an API misuse: floor the draw instead of
    # letting PIL raise "negative width" (a ValueError class) mid-wall
    tile_w = max(1, int(tile_w))
    tile_h = _tile_h(frames, indexes, tile_w)
    rows = (len(indexes) + cols - 1) // cols
    grid = Image.new("RGB", (cols * tile_w, rows * (HEADER_H + tile_h)), BG)
    draw = ImageDraw.Draw(grid)
    font = FONT                    # the readable face (module header)
    for pos, index in enumerate(indexes):
        x = (pos % cols) * tile_w
        y = (pos // cols) * (HEADER_H + tile_h)
        label = str(labels.get(index) or "")
        draw.rectangle((x, y, x + tile_w - 1, y + HEADER_H), fill=HEADER_BG)
        draw.text((x + PAD, y + (HEADER_H - _FONT_H) // 2),
                  "%s  %s" % (index, _clip(draw, label, tile_w - 2 * PAD,
                                           font)),
                  font=font, fill=INK)
        frame = frames[index]
        if frame is None:
            _centered(draw, x, y, tile_w, tile_h, label or "no frame", font)
            continue
        if frame.mode != "RGB":
            frame = frame.convert("RGB")
        grid.paste(frame.resize((tile_w, tile_h)), (x, y + HEADER_H))
    return grid


def _tile_h(frames, indexes, tile_w):
    """One shared tile shape for the wall: the first frame's aspect,
    or the camera default 16:9 when no tile has a frame to ask."""
    for index in indexes:
        frame = frames[index]
        if frame is not None:
            return max(1, round(tile_w * frame.height / max(frame.width, 1)))
    return max(1, round(tile_w * FALLBACK_AR))


def _clip(draw, text, width, font):
    """A label that would spill onto the neighbour's tile earns an
    ellipsis instead: the roster order is the contract, the columns
    are the law."""
    if not text or _width(draw, text, font) <= width:
        return text
    while text and _width(draw, text + "...", font) > width:
        text = text[:-1]
    return text + "..."


def _width(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _centered(draw, x, y, tile_w, tile_h, text, font):
    """The placeholder: the reason for the missing frame, dead center
    on the tile's own rectangle (below its header). INK, not the old
    dim gray: a permanently-off eye's "off" must be READ, not squinted
    at - labeled, not faked, and labelABLE (the owner's half of the
    report: the black tile nobody could tell dead from dark)."""
    box = draw.textbbox((0, 0), text, font=font)
    draw.text((x + (tile_w - box[2] + box[0]) // 2 - box[0],
               y + HEADER_H + (tile_h - box[3] + box[1]) // 2 - box[1]),
              text, font=font, fill=INK)
