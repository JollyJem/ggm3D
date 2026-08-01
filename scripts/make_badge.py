"""One-time texture generation for the nameplate on the product front edge.

Writes app/generator/badge.png, which the builders map onto a small quad on
the worktop's front rim. Both catalog products carry this plate in their photo:
a light rectangle with a thin dark border and the wordmark across it.

Generated rather than cropped out of a product photo, because the photo's plate
is 46 px wide, seen at an angle, and under studio glare — enlarged onto a model
it would read as a smear. A texture is the only way to put lettering on a part
this size: as geometry the wordmark would cost more triangles than the rest of
the unit put together.

Run only when the plate itself changes:

    python scripts/make_badge.py

Pillow is already a dependency (scripts/optimize_assets.py uses it); the font
is a system font, so this is a Windows-only script and its output is committed.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "app" / "generator" / "badge.png"
FONT = Path("C:/Windows/Fonts/arialbd.ttf")
WIDTH, HEIGHT = 512, 128
TEXT = "ggmgastro"
PLATE = (232, 233, 234)
BORDER = (120, 122, 124)
INK = (32, 33, 35)


def main() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), PLATE)
    draw = ImageDraw.Draw(image)
    # the plate's own edge, so the quad reads as a fitted nameplate rather than
    # a decal printed straight onto the steel
    draw.rectangle((3, 3, WIDTH - 4, HEIGHT - 4), outline=BORDER, width=4)
    font = ImageFont.truetype(str(FONT), 74)
    left, top, right, bottom = draw.textbbox((0, 0), TEXT, font=font)
    draw.text(
        ((WIDTH - (right - left)) / 2 - left, (HEIGHT - (bottom - top)) / 2 - top),
        TEXT,
        font=font,
        fill=INK,
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT, optimize=True)
    print(f"{OUT} ({OUT.stat().st_size / 1024:.1f} KB, {WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
