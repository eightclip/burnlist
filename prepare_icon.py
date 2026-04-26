#!/usr/bin/env python3
"""Prepare a source image for use as a macOS app icon.

Reads icon.png from the project root, resizes to 1024×1024, applies the
macOS squircle (rounded-square) mask, and writes /tmp/burnlist-icon.png.
"""
import os
from PIL import Image, ImageDraw

SIZE = 1024
RADIUS = int(SIZE * 0.225)  # Apple HIG ~22.5% corner radius
SRC = os.path.join(os.path.dirname(__file__), "icon.png")
OUT = "/tmp/burnlist-icon.png"


def main():
    src = Image.open(SRC).convert("RGBA")
    if src.size != (SIZE, SIZE):
        src = src.resize((SIZE, SIZE), Image.LANCZOS)

    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, SIZE - 1, SIZE - 1), radius=RADIUS, fill=255,
    )

    out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    out.paste(src, (0, 0), mask)
    out.save(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
