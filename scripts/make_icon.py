#!/usr/bin/env python3
"""Draw the plugin icon (icon.png, 256x256): a stopwatch whose ring is running down.

    .venv/bin/python scripts/make_icon.py icon.png

Drawn at 4x and scaled down for smooth edges. No fonts or files needed.
"""

import math
import sys

from PIL import Image, ImageDraw, ImageFilter

S = 256
K = 4                       # supersampling
W = S * K


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def main(out):
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Background: rounded square, deep night-blue vertical gradient
    bg = Image.new("RGBA", (W, W))
    top, bottom = rgb("#1d2b53"), rgb("#0b1024")
    gd = ImageDraw.Draw(bg)
    for y in range(W):
        gd.line([(0, y), (W, y)], fill=lerp(top, bottom, y / W) + (255,))
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, W - 1], radius=56 * K, fill=255)
    img.paste(bg, (0, 0), mask)

    cx, cy, R = W // 2, int(W * 0.56), int(W * 0.34)

    # Soft glow behind the watch
    glow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([cx - R - 24 * K, cy - R - 24 * K, cx + R + 24 * K, cy + R + 24 * K],
                                 fill=(255, 200, 80, 70))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(18 * K)))

    metal, metal_dark = rgb("#e9edf5"), rgb("#9aa6bd")
    # Crown and stem on top, side button
    d.rounded_rectangle([cx - 18 * K, cy - R - 30 * K, cx + 18 * K, cy - R - 14 * K], radius=5 * K, fill=metal)
    d.rectangle([cx - 7 * K, cy - R - 16 * K, cx + 7 * K, cy - R + 4 * K], fill=metal_dark)
    a = math.radians(-45 - 90)
    bx, by = cx + (R + 10 * K) * math.cos(a), cy + (R + 10 * K) * math.sin(a)
    d.ellipse([bx - 11 * K, by - 11 * K, bx + 11 * K, by + 11 * K], fill=metal_dark)

    # Case and face
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=metal)
    face = R - 13 * K
    d.ellipse([cx - face, cy - face, cx + face, cy + face], fill=rgb("#111827"))

    # Countdown ring: the remaining time, green fading to red, with the spent part dim
    ring_out, ring_w = face - 7 * K, 22 * K
    box = [cx - ring_out, cy - ring_out, cx + ring_out, cy + ring_out]
    d.arc(box, 0, 360, fill=rgb("#273246"), width=ring_w)
    remaining = 0.70                       # fraction left, running clockwise from 12 o'clock
    start = -90
    steps = 140
    green, gold, red = rgb("#2ee86a"), rgb("#ffd34d"), rgb("#ff4d4d")
    span = 360 * remaining
    for i in range(steps):
        t = i / steps
        col = lerp(green, gold, t * 2) if t < 0.5 else lerp(gold, red, (t - 0.5) * 2)
        a0 = start + span * (1 - (i + 1) / steps)
        a1 = start + span * (1 - i / steps) + 0.6
        d.arc(box, a0, a1, fill=col, width=ring_w)
    # Round cap at the moving end
    end = math.radians(start + span)
    mid = ring_out - ring_w / 2
    ex, ey = cx + mid * math.cos(end), cy + mid * math.sin(end)
    d.ellipse([ex - ring_w / 2, ey - ring_w / 2, ex + ring_w / 2, ey + ring_w / 2], fill=green)

    # Tick marks
    tick_r = ring_out - ring_w - 8 * K
    for i in range(12):
        ang = math.radians(i * 30 - 90)
        r0 = tick_r - (12 * K if i % 3 == 0 else 7 * K)
        d.line([(cx + r0 * math.cos(ang), cy + r0 * math.sin(ang)),
                (cx + tick_r * math.cos(ang), cy + tick_r * math.sin(ang))],
               fill=rgb("#c9d2e3"), width=(4 if i % 3 == 0 else 2) * K)

    # Hand pointing at the edge of the remaining time
    hand = tick_r - 6 * K
    d.line([(cx, cy), (cx + hand * math.cos(end), cy + hand * math.sin(end))], fill=rgb("#ffffff"), width=7 * K)
    d.ellipse([cx - 11 * K, cy - 11 * K, cx + 11 * K, cy + 11 * K], fill=rgb("#ff4d4d"))
    d.ellipse([cx - 4 * K, cy - 4 * K, cx + 4 * K, cy + 4 * K], fill=rgb("#ffffff"))

    # A few sparkles: it's counting to something to celebrate
    def sparkle(x, y, r, col):
        d.polygon([(x, y - r), (x + r * 0.28, y - r * 0.28), (x + r, y), (x + r * 0.28, y + r * 0.28),
                   (x, y + r), (x - r * 0.28, y + r * 0.28), (x - r, y), (x - r * 0.28, y - r * 0.28)], fill=col)

    sparkle(int(W * 0.17), int(W * 0.17), 15 * K, rgb("#ffd34d"))
    sparkle(int(W * 0.84), int(W * 0.15), 10 * K, rgb("#ffffff"))
    sparkle(int(W * 0.88), int(W * 0.36), 7 * K, rgb("#2ee86a"))

    img.resize((S, S), Image.LANCZOS).save(out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "icon.png")
