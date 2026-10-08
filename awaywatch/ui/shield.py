"""The UAC shield, drawn to match the system icon (compared pixel-shape
by pixel-shape against the extracted one): silver-edged shield, silver
cross dividers, blue top-left/bottom-right quarters, amber the other
two, pointed bottom with a shallow peak at the top. Drawn big and
shrunk so the tiny size stays crisp."""

from PIL import Image, ImageDraw

BLUE = (28, 110, 226, 255)
AMBER = (245, 178, 22, 255)
SILVER = (178, 185, 194, 255)


def _shield_polygon(S):
    def P(x, y):
        return (x * S, y * S)

    pts = [P(0.10, 0.12), P(0.50, 0.035), P(0.90, 0.12), P(0.90, 0.55)]

    def bez(p0, p1, p2):
        out = []
        for i in range(1, 13):
            t = i / 12.0
            out.append((int((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0]
                          + t ** 2 * p2[0]),
                        int((1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1]
                          + t ** 2 * p2[1])))
        return out

    pts += bez(P(0.90, 0.55), P(0.885, 0.83), P(0.50, 0.965))   # right -> tip
    pts += bez(P(0.50, 0.965), P(0.115, 0.83), P(0.10, 0.55))   # tip -> left
    return pts


def shield_pil(size=16):
    S = size * 6                                   # supersample for AA
    poly = _shield_polygon(S)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, hy = int(0.50 * S), int(0.52 * S)
    w = max(2, int(0.028 * S))                     # divider thickness
    draw.polygon(poly, fill=BLUE)
    draw.rectangle([cx + w // 2, 0, S, hy - w // 2], fill=AMBER)   # top-right
    draw.rectangle([0, hy + w // 2, cx - w // 2, S], fill=AMBER)   # bottom-left
    draw.rectangle([cx - w // 2, 0, cx + w // 2, S], fill=SILVER)
    draw.rectangle([0, hy - w // 2, S, hy + w // 2], fill=SILVER)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    body = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    body.paste(img, (0, 0), mask)                  # clip everything to shield
    ImageDraw.Draw(body).polygon(poly, outline=(150, 158, 168, 255),
                                 width=max(2, int(0.035 * S)))
    return body.resize((size, size), Image.LANCZOS)
