#!/usr/bin/env python3
"""Draw the diagram that shows where the Cookie header lives.

Copying that header is the hardest step of setup and the place most installs fail,
and prose alone has not been enough - "click any request to rover.com" means little
to someone who has never opened the Network tab.

This is a DIAGRAM, drawn here, not a screenshot. Two reasons, both deliberate:

  - A real screenshot of rover.com's devtools would contain a real session cookie.
    That is a full-access credential for the account, and no amount of blurring
    makes publishing one a good idea.
  - Devtools changes its layout between browsers and between releases, while the
    thing being pointed at - a request, its request headers, the Cookie row - does
    not. A diagram keeps pointing at the right thing.

    python3 scripts/make_docs_images.py

Writes docs/images/cookie-header.png. Requires Pillow (development only).
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "images"

SCALE = 2
WIDTH, HEIGHT = 900, 470

CHROME = (243, 245, 248, 255)
PANEL = (255, 255, 255, 255)
BORDER = (203, 213, 225, 255)
TEXT = (30, 41, 59, 255)
MUTED = (100, 116, 139, 255)
ACCENT = (24, 138, 140, 255)
HIGHLIGHT = (255, 243, 205, 255)
HIGHLIGHT_EDGE = (234, 179, 8, 255)
CODE = (15, 23, 42, 255)

REGULAR_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)
BOLD_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)
MONO_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
)


def font(candidates: tuple[str, ...], size: int) -> ImageFont.FreeTypeFont:
    """Return the first available font at `size`, or fail loudly."""
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size * SCALE)
    raise SystemExit("No suitable font found; install fonts-dejavu-core and retry.")


def px(value: float) -> int:
    """Scale a design-space coordinate to the supersampled canvas."""
    return round(value * SCALE)


def draw_diagram() -> Image.Image:
    """Return the annotated devtools diagram."""
    image = Image.new("RGBA", (px(WIDTH), px(HEIGHT)), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)

    label = font(REGULAR_FONTS, 13)
    label_bold = font(BOLD_FONTS, 13)
    small = font(REGULAR_FONTS, 11)
    mono = font(MONO_FONTS, 12)
    title = font(BOLD_FONTS, 15)
    step = font(BOLD_FONTS, 12)

    # Window chrome.
    draw.rounded_rectangle(
        (px(16), px(16), px(WIDTH - 16), px(HEIGHT - 16)),
        radius=px(10),
        fill=PANEL,
        outline=BORDER,
        width=px(1),
    )
    draw.rounded_rectangle(
        (px(16), px(16), px(WIDTH - 16), px(56)),
        radius=px(10),
        fill=CHROME,
        outline=BORDER,
        width=px(1),
    )
    draw.text((px(36), px(36)), "Developer tools", font=title, fill=TEXT, anchor="lm")

    tabs = ("Elements", "Console", "Sources", "Network", "Performance")
    x = px(190)
    for name in tabs:
        active = name == "Network"
        text_width = draw.textlength(name, font=label_bold if active else label)
        if active:
            draw.rounded_rectangle(
                (x - px(10), px(26), x + text_width + px(10), px(48)),
                radius=px(5),
                fill=PANEL,
                outline=ACCENT,
                width=px(2),
            )
        draw.text(
            (x, px(37)),
            name,
            font=label_bold if active else label,
            fill=TEXT if active else MUTED,
            anchor="lm",
        )
        x += text_width + px(34)

    # Left pane: the request list.
    draw.rectangle(
        (px(16), px(56), px(300), px(HEIGHT - 16)), fill=(250, 251, 253, 255)
    )
    draw.line((px(300), px(56), px(300), px(HEIGHT - 16)), fill=BORDER, width=px(1))
    draw.text((px(36), px(76)), "Name", font=label_bold, fill=MUTED, anchor="lm")

    requests = (
        ("members/", False),
        ("conversations/", True),
        ("app.bundle.js", False),
        ("avatar.jpg", False),
    )
    y = px(102)
    for name, selected in requests:
        if selected:
            draw.rectangle(
                (px(20), y - px(13), px(299), y + px(13)),
                fill=(226, 242, 242, 255),
            )
            draw.line(
                (px(20), y - px(13), px(20), y + px(13)), fill=ACCENT, width=px(3)
            )
        draw.text(
            (px(36), y),
            name,
            font=label_bold if selected else label,
            fill=TEXT if selected else MUTED,
            anchor="lm",
        )
        y += px(30)

    caption_y = px(234)
    for line in (
        "Any request to rover.com will do.",
        "They all carry the same header.",
    ):
        draw.text((px(36), caption_y), line, font=small, fill=MUTED, anchor="lm")
        caption_y += px(18)

    # Right pane: the headers.
    draw.text((px(324), px(76)), "Headers", font=label_bold, fill=TEXT, anchor="lm")
    draw.line(
        (px(324), px(90), px(WIDTH - 36), px(90)),
        fill=BORDER,
        width=px(1),
    )
    draw.text(
        (px(324), px(112)),
        "Request Headers",
        font=label_bold,
        fill=MUTED,
        anchor="lm",
    )

    rows = (
        ("accept:", "application/json"),
        ("accept-language:", "en-US"),
        ("referer:", "https://www.rover.com/members/"),
    )
    y = px(138)
    for name, value in rows:
        draw.text((px(324), y), name, font=mono, fill=MUTED, anchor="lm")
        draw.text((px(470), y), value, font=mono, fill=MUTED, anchor="lm")
        y += px(24)

    # The Cookie row: the whole point of the picture.
    cookie_top = y + px(4)
    draw.rounded_rectangle(
        (px(318), cookie_top, px(WIDTH - 36), cookie_top + px(84)),
        radius=px(6),
        fill=HIGHLIGHT,
        outline=HIGHLIGHT_EDGE,
        width=px(2),
    )
    draw.text(
        (px(330), cookie_top + px(20)), "cookie:", font=mono, fill=CODE, anchor="lm"
    )
    cookie_lines = (
        "__cf_bm=REDACTED; csrftoken=REDACTED;",
        "sessionid=REDACTED; roverid=REDACTED; ...",
    )
    line_y = cookie_top + px(20)
    for line in cookie_lines:
        draw.text((px(404), line_y), line, font=mono, fill=CODE, anchor="lm")
        line_y += px(22)
    draw.text(
        (px(330), cookie_top + px(66)),
        "Right-click this row \u2192 Copy value. Copy ALL of it, every pair.",
        font=step,
        fill=(146, 64, 14, 255),
        anchor="lm",
    )

    # Footer: the mistake this diagram exists to prevent.
    footer_top = px(HEIGHT - 76)
    draw.rounded_rectangle(
        (px(318), footer_top, px(WIDTH - 36), footer_top + px(48)),
        radius=px(6),
        fill=(254, 242, 242, 255),
        outline=(248, 113, 113, 255),
        width=px(1),
    )
    draw.text(
        (px(332), footer_top + px(16)),
        "Not the Application > Cookies table.",
        font=label_bold,
        fill=(153, 27, 27, 255),
        anchor="lm",
    )
    draw.text(
        (px(332), footer_top + px(33)),
        "One row from there is a single cookie, and setup will tell you so.",
        font=small,
        fill=(153, 27, 27, 255),
        anchor="lm",
    )

    return image.resize((WIDTH, HEIGHT), Image.LANCZOS)


def main() -> int:
    """Write the documentation images."""
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "cookie-header.png"
    draw_diagram().convert("RGB").save(path, "PNG", optimize=True)
    print(f"{path.relative_to(REPO)}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
