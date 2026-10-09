"""The Ko-fi cup, drawn the way the UAC shield is drawn: PIL in code,
no asset files in the repo. Dark cup with the orange heart - the
patron page's own recipe. Ink is a parameter because CTk keeps two
images: dark ink for light mode, light ink for dark (a near-black
cup on the near-black window is a hole, not an icon)."""

from PIL import Image, ImageDraw

ORANGE = (232, 84, 40, 255)


def kofi_pil(size=36, ink=(40, 40, 40, 255), s=4):
    """`s` is the supersample factor; the result shrinks to `size`,
    which is what anti-aliases the arcs and the heart point."""
    img = Image.new("RGBA", (80 * s, 80 * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # handle first: the cup outline laid over it hides the seam
    d.ellipse([48 * s, 26 * s, 76 * s, 56 * s], outline=ink, width=8 * s)
    d.rounded_rectangle([10 * s, 14 * s, 58 * s, 68 * s], radius=14 * s,
                        outline=ink, width=8 * s)
    # the heart: two circles and a point - the classic, and still
    # readable at the 18 px it will actually be shown at
    d.ellipse([18 * s, 26 * s, 36 * s, 44 * s], fill=ORANGE)
    d.ellipse([32 * s, 26 * s, 50 * s, 44 * s], fill=ORANGE)
    d.polygon([(20 * s, 37 * s), (48 * s, 37 * s), (34 * s, 53 * s)],
              fill=ORANGE)
    return img.resize((size, size))
