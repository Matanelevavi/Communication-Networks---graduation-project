"""
Renders the app icons from the same drawing as ``src/web/static/icon.svg``.

A web app is only installable with PNG icons at 192 and 512 pixels, and a
"maskable" one that survives being cropped to a circle or a squircle, so they
are generated here rather than drawn by hand. Re-run it after changing the logo:

    pip install pillow
    python tools/make_icons.py

Pillow is a tool for this script only; the application does not need it.
"""
import os

from PIL import Image, ImageDraw

BRAND = (27, 111, 168, 255)
SUN = (255, 195, 90, 255)
WHITE = (255, 255, 255, 255)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "src", "web", "static")
SUPERSAMPLE = 4          # draw large and shrink, which is what makes the edges smooth


def draw(size: int, maskable: bool) -> Image.Image:
    big = size * SUPERSAMPLE
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)

    # The drawing lives in a 64 x 64 box. A maskable icon fills the whole canvas
    # and keeps its content inside the central 72 %, the "safe zone".
    if maskable:
        pen.rectangle((0, 0, big, big), fill=BRAND)
        scale, offset = big / 64 * 0.72, big * 0.14
    else:
        pen.rounded_rectangle((0, 0, big, big), radius=big * 16 / 64, fill=BRAND)
        scale, offset = big / 64, 0

    def p(value: float) -> float:
        return offset + value * scale

    def circle(cx: float, cy: float, r: float, fill) -> None:
        pen.ellipse((p(cx - r), p(cy - r), p(cx + r), p(cy + r)), fill=fill)

    circle(24, 24, 9, SUN)                                  # the sun, behind
    circle(22, 38, 8, WHITE)                                # the cloud
    circle(33, 33, 10, WHITE)
    circle(44, 38, 8, WHITE)
    pen.rounded_rectangle((p(22), p(36), p(44), p(46)), radius=4 * scale, fill=WHITE)
    pen.line([(p(27), p(38)), (p(31), p(34)), (p(35), p(38)), (p(39), p(34))],
             fill=BRAND, width=round(3 * scale), joint="curve")        # a packet's path
    for x, y in ((27, 38), (39, 34)):
        circle(x, y, 1.5, BRAND)                            # round the ends of the line

    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    for name, size, maskable in (("icon-192.png", 192, False), ("icon-512.png", 512, False),
                                 ("icon-maskable-512.png", 512, True),
                                 ("apple-touch-icon.png", 180, False)):
        path = os.path.join(OUT, name)
        draw(size, maskable).save(path, optimize=True)
        print(f"wrote {path} ({os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
