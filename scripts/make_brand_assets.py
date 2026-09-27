#!/usr/bin/env python3
"""Draw the brand assets, so the integration stops showing a puzzle piece.

A missing icon is the loudest "unfinished" signal a new user gets, because it
appears everywhere the integration does. The artwork is generated rather than
hand-drawn so it can be reproduced at any size and so the design itself stays
reviewable as text.

The mark is a speech bubble with a paw in it: what the integration reads is Rover
*conversations*. It is deliberately NOT a copy of Rover's own logo - this is a
third-party client, and dressing it up as the real thing would be both a trademark
problem and a lie about who wrote it. home-assistant/brands asks the same thing of
custom integrations.

    python3 scripts/make_brand_assets.py

WHERE THE FILES GO
------------------
custom_components/rover_client/brand/ - read directly by Home Assistant 2026.3 and
later, where local brand images take priority over the brands CDN, and accepted by
the HACS brands check. No upstream pull request and no waiting.

Anyone on Home Assistant older than 2026.3 still needs the images on the CDN, which
means a home-assistant/brands pull request; the same files are used unchanged. See
docs/brands-submission.md.

The output follows the brands image specification either way: PNG, transparent,
trimmed of empty edges, icons exactly 256x256 and 512x512, logo shortest side 128
(256 for the hDPI version).

Requires Pillow, which is a development-only dependency: the generated PNGs are
committed, so nobody installing the integration needs it.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
BRAND = REPO / "custom_components" / "rover_client" / "brand"

# Drawn at 4x and resized down: Pillow has no anti-aliased drawing, so
# supersampling is what keeps the curves from looking like stairs.
SUPERSAMPLE = 4

TOP_COLOUR = (35, 166, 160)
BOTTOM_COLOUR = (24, 108, 128)
PAW_COLOUR = (255, 255, 255, 255)
# Dark enough to read on the white background brands prefers; the dark_ variants
# swap it for something that reads on a dark theme instead.
TEXT_COLOUR = (31, 45, 61, 255)
DARK_TEXT_COLOUR = (240, 246, 252, 255)

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


def gradient(size: tuple[int, int]) -> Image.Image:
    """Return a vertical gradient the size of the canvas."""
    width, height = size
    image = Image.new("RGB", (1, height))
    for y in range(height):
        ratio = y / max(height - 1, 1)
        image.putpixel(
            (0, y),
            tuple(
                round(top + (bottom - top) * ratio)
                for top, bottom in zip(TOP_COLOUR, BOTTOM_COLOUR, strict=True)
            ),
        )
    return image.resize((width, height))


def paw_mask(size: int) -> Image.Image:
    """Return a paw print as an alpha mask `size` pixels square.

    One main pad and four toes, the outer two tilted outwards. Tilting is done by
    rotating each toe on its own layer, because an axis-aligned ellipse reads as a
    row of dots rather than a paw.
    """
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)

    # Main pad: wider than tall, sitting low, with the top corners pulled in so it
    # reads as a pad rather than a circle.
    draw.ellipse(
        (size * 0.22, size * 0.46, size * 0.78, size * 0.94),
        fill=255,
    )

    toes = (
        # (centre x, centre y, width, height, rotation)
        (0.20, 0.42, 0.20, 0.27, 28),
        (0.40, 0.24, 0.20, 0.29, 9),
        (0.60, 0.24, 0.20, 0.29, -9),
        (0.80, 0.42, 0.20, 0.27, -28),
    )
    for centre_x, centre_y, width, height, angle in toes:
        toe_w = max(round(size * width), 2)
        toe_h = max(round(size * height), 2)
        toe = Image.new("L", (toe_w, toe_h), 0)
        ImageDraw.Draw(toe).ellipse((0, 0, toe_w - 1, toe_h - 1), fill=255)
        toe = toe.rotate(angle, resample=Image.BICUBIC, expand=True)
        position = (
            round(size * centre_x - toe.width / 2),
            round(size * centre_y - toe.height / 2),
        )
        # Paste through itself so overlapping toes merge instead of clipping.
        mask.paste(255, position, toe)

    return mask


def bubble_mask(size: int) -> Image.Image:
    """Return a speech bubble as an alpha mask `size` pixels square."""
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)

    draw.rounded_rectangle(
        (size * 0.06, size * 0.08, size * 0.94, size * 0.76),
        radius=size * 0.22,
        fill=255,
    )
    # Tail, bottom left, angled the way a chat bubble points at its speaker.
    draw.polygon(
        [
            (size * 0.26, size * 0.70),
            (size * 0.50, size * 0.70),
            (size * 0.30, size * 0.96),
        ],
        fill=255,
    )
    return mask


def fit_square(image: Image.Image, size: int) -> Image.Image:
    """Trim an image to its content and centre it in a transparent square.

    Trimming is a brands requirement - "the minimum amount of empty space on the
    edges" - and the icon must also be exactly square, so the two are satisfied
    together rather than by leaving a rim of transparent pixels around the mark.
    """
    cropped = image.crop(image.getbbox())
    scale = size / max(cropped.width, cropped.height)
    scaled = cropped.resize(
        (
            max(round(cropped.width * scale), 1),
            max(round(cropped.height * scale), 1),
        ),
        Image.LANCZOS,
    )

    square = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    square.alpha_composite(
        scaled,
        (round((size - scaled.width) / 2), round((size - scaled.height) / 2)),
    )
    return square


def draw_icon(size: int) -> Image.Image:
    """Return the square icon: a gradient bubble with a paw knocked into it."""
    work = size * SUPERSAMPLE
    icon = Image.new("RGBA", (work, work), (0, 0, 0, 0))
    icon.paste(gradient((work, work)), (0, 0), bubble_mask(work))

    paw_size = round(work * 0.46)
    paw = Image.new("RGBA", (paw_size, paw_size), (0, 0, 0, 0))
    paw.paste(PAW_COLOUR, (0, 0), paw_mask(paw_size))
    icon.alpha_composite(
        paw,
        (round((work - paw_size) / 2), round(work * 0.12)),
    )

    return fit_square(icon, size)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    """Return a bold sans font, or fail loudly rather than silently reshaping."""
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    raise SystemExit(
        "No bold sans-serif font found; install fonts-dejavu-core and retry."
    )


def draw_logo(height: int, *, dark: bool = False) -> Image.Image:
    """Return the wide logo: the icon plus a wordmark, trimmed to its content.

    `dark` swaps the wordmark for a light one. Without it the navy text vanishes
    against a dark theme, which is the one thing the dark_ variants exist for.
    """
    work = height * SUPERSAMPLE
    icon = draw_icon(work)

    font = load_font(round(work * 0.30))
    canvas = Image.new("RGBA", (work * 4, work), (0, 0, 0, 0))
    canvas.alpha_composite(icon, (0, 0))

    draw = ImageDraw.Draw(canvas)
    draw.text(
        (round(work * 1.12), round(work * 0.50)),
        "Rover Client",
        font=font,
        fill=DARK_TEXT_COLOUR if dark else TEXT_COLOUR,
        anchor="lm",
    )

    # Trimmed because brands rejects padding, and the canvas above is deliberately
    # too wide so the wordmark can be any length.
    bbox = canvas.getbbox()
    cropped = canvas.crop(bbox)
    scale = height / cropped.height
    return cropped.resize(
        (max(round(cropped.width * scale), 1), height), Image.LANCZOS
    )


def main() -> int:
    """Write every brand asset."""
    assets = {
        "icon.png": draw_icon(256),
        "icon@2x.png": draw_icon(512),
        "logo.png": draw_logo(128),
        "logo@2x.png": draw_logo(256),
        "dark_logo.png": draw_logo(128, dark=True),
        "dark_logo@2x.png": draw_logo(256, dark=True),
    }

    BRAND.mkdir(parents=True, exist_ok=True)
    for name, image in assets.items():
        path = BRAND / name
        image.save(path, "PNG", optimize=True)
        print(f"{path.relative_to(REPO)}  {image.width}x{image.height}")  # noqa: T201

    return 0


if __name__ == "__main__":
    sys.exit(main())
