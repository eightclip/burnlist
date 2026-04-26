#!/usr/bin/env python3
"""Generate Burnlist app icon — CD on fire, 90s/Winamp aesthetic."""
import math
import random
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE = 1024
OUT = "/tmp/burnlist-icon.png"


def rounded_square_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def make_background(size):
    """Dark chrome gradient background, slight purple/blue tint — Winamp vibe."""
    img = Image.new("RGB", (size, size), (0, 0, 0))
    px = img.load()
    for y in range(size):
        # vertical gradient: deep navy at top → near-black at bottom
        t = y / size
        r = int(20 + (8 - 20) * t)
        g = int(24 + (8 - 24) * t)
        b = int(40 + (12 - 40) * t)
        for x in range(size):
            px[x, y] = (r, g, b)
    return img


def draw_flames(img, cx, cy, max_r):
    """Draw dramatic licking flames wrapping around the disc."""
    random.seed(11)
    flame_colors = [
        (180, 30, 0, 220),    # deep red base
        (255, 90, 0, 230),    # red-orange
        (255, 160, 20, 240),  # orange
        (255, 220, 60, 250),  # yellow
        (255, 250, 220, 255), # core white
    ]
    # First: a single soft red glow halo (separate, not per-layer)
    halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    glow_r = int(max_r * 1.30)
    hd.ellipse(
        (cx - glow_r, cy - int(glow_r * 0.85),
         cx + glow_r, cy + int(glow_r * 1.20)),
        fill=(180, 40, 0, 200),
    )
    halo = halo.filter(ImageFilter.GaussianBlur(radius=60))
    img.alpha_composite(halo)

    # Then: discrete flame tongues with light blur, drawn brightest-last
    blur_per_layer = [14, 10, 6, 3, 1]
    for layer, color in enumerate(flame_colors):
        layer_img = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer_img)
        scale = 1.50 - layer * 0.16
        # Tongues radiating from sides + bottom + curling up the sides
        N = 22
        for i in range(N):
            t = i / (N - 1)
            # Spread from 0° (right) through bottom (180°) to 360° (left going up)
            # We want tongues from below and wrapping up the sides
            angle = -math.pi * 0.10 + t * math.pi * 1.20
            angle += random.uniform(-0.06, 0.06)
            tongue_len = max_r * scale * random.uniform(0.55, 1.0)
            base_w = max_r * (0.10 + 0.05 * random.random()) * (1.2 - layer * 0.12)
            base_x = cx + (max_r * 0.97) * math.cos(angle + math.pi / 2)
            base_y = cy + (max_r * 0.97) * math.sin(angle + math.pi / 2)
            tip_x = cx + (max_r + tongue_len) * math.cos(angle + math.pi / 2)
            tip_y = cy + (max_r + tongue_len) * math.sin(angle + math.pi / 2)
            # Curl tip slightly upward
            tip_y -= tongue_len * 0.15
            perp = angle + math.pi / 2 + math.pi / 2
            bx1 = base_x + base_w * math.cos(perp)
            by1 = base_y + base_w * math.sin(perp)
            bx2 = base_x - base_w * math.cos(perp)
            by2 = base_y - base_w * math.sin(perp)
            ld.polygon([(bx1, by1), (bx2, by2), (tip_x, tip_y)], fill=color)
        layer_img = layer_img.filter(ImageFilter.GaussianBlur(radius=blur_per_layer[layer]))
        img.alpha_composite(layer_img)


def draw_cd(img, cx, cy, radius):
    """Draw a CD: silver outer rim, rainbow shimmer, dark center hole."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # Outer silver disc
    d.ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        fill=(220, 220, 230, 255),
        outline=(180, 180, 195, 255),
        width=4,
    )

    # Rainbow shimmer rings (very subtle)
    rainbow = [
        (255, 80, 80, 70),
        (255, 200, 80, 70),
        (180, 255, 100, 70),
        (80, 220, 255, 70),
        (180, 120, 255, 70),
    ]
    for i, color in enumerate(rainbow):
        r = radius - 30 - i * 18
        if r < radius * 0.45:
            break
        d.ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            outline=color,
            width=14,
        )

    # Inner ring (clear plastic look)
    inner_r = int(radius * 0.30)
    d.ellipse(
        (cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r),
        fill=(40, 40, 50, 255),
        outline=(180, 180, 195, 255),
        width=3,
    )

    # Center hole
    hole_r = int(radius * 0.10)
    d.ellipse(
        (cx - hole_r, cy - hole_r, cx + hole_r, cy + hole_r),
        fill=(8, 8, 12, 255),
    )

    # Specular highlight — top-left arc
    spec = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(spec)
    sd.pieslice(
        (cx - radius + 20, cy - radius + 20, cx + radius - 20, cy + radius - 20),
        start=200, end=290, fill=(255, 255, 255, 90),
    )
    spec = spec.filter(ImageFilter.GaussianBlur(radius=20))
    overlay.alpha_composite(spec)

    img.alpha_composite(overlay)


def draw_lcd_text(img, text, cx, y):
    """Green LCD-style text label."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    # Try to use a chunky monospace font
    font = None
    for path in [
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Courier.dfont",
        "/Library/Fonts/Arial Bold.ttf",
    ]:
        try:
            font = ImageFont.truetype(path, 110)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
    bbox = d.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = cx - w // 2
    # background plate
    pad = 24
    d.rounded_rectangle(
        (x - pad, y - pad // 2, x + w + pad, y + h + pad),
        radius=14, fill=(0, 18, 0, 230), outline=(0, 80, 0, 255), width=3,
    )
    # green glow
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.text((x, y), text, font=font, fill=(80, 255, 120, 255))
    glow_blur = glow.filter(ImageFilter.GaussianBlur(radius=8))
    overlay.alpha_composite(glow_blur)
    d.text((x, y), text, font=font, fill=(180, 255, 200, 255))
    img.alpha_composite(overlay)


def main():
    bg = make_background(SIZE).convert("RGBA")
    cx = SIZE // 2
    cy = int(SIZE * 0.46)
    cd_r = int(SIZE * 0.36)
    draw_flames(bg, cx, cy + 40, cd_r + 20)
    draw_cd(bg, cx, cy, cd_r)
    draw_lcd_text(bg, "BURNLIST", cx, int(SIZE * 0.86))

    # Apply rounded-square mask (macOS app icon shape)
    mask = rounded_square_mask(SIZE, radius=int(SIZE * 0.22))
    final = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    final.paste(bg, (0, 0), mask)

    final.save(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
