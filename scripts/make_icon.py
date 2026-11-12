#!/usr/bin/env python3
"""Draw the plugin icon (icon.png, 256x256): a show marquee.

A marquee sign ringed with warm bulbs, its panel an LED matrix showing three
lines of "text" in the red and green the plugin uses, on a post, against a
night sky.

    .venv/bin/python scripts/make_icon.py icon.png

Drawn at 4x and scaled down for smooth edges. No fonts or files needed.
"""

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

    # Background: rounded square, night sky
    bg = Image.new("RGBA", (W, W))
    top, bottom = rgb("#1d2b53"), rgb("#0b1024")
    gd = ImageDraw.Draw(bg)
    for y in range(W):
        gd.line([(0, y), (W, y)], fill=lerp(top, bottom, y / W) + (255,))
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, W - 1], radius=56 * K, fill=255)
    img.paste(bg, (0, 0), mask)

    # The sign
    x0, y0, x1, y1 = 26 * K, 40 * K, 230 * K, 178 * K
    bulb = rgb("#ffc23d")

    # Warm glow behind the sign
    glow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle([x0 - 10 * K, y0 - 10 * K, x1 + 10 * K, y1 + 10 * K],
                                           radius=26 * K, fill=(255, 190, 70, 90))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14 * K)))

    d = ImageDraw.Draw(img)
    # Post and base
    d.rectangle([118 * K, y1, 138 * K, 214 * K], fill=rgb("#3a4560"))
    d.rounded_rectangle([88 * K, 210 * K, 168 * K, 222 * K], radius=5 * K, fill=rgb("#3a4560"))

    # Frame
    d.rounded_rectangle([x0, y0, x1, y1], radius=18 * K, fill=rgb("#7a1f2b"))
    d.rounded_rectangle([x0 + 4 * K, y0 + 4 * K, x1 - 4 * K, y1 - 4 * K], radius=15 * K, fill=rgb("#9b2a37"))

    # Bulbs all round the frame, each with a little glow
    inset = 13 * K
    bx0, by0, bx1, by1 = x0 + inset, y0 + inset, x1 - inset, y1 - inset
    r = 5 * K
    pts = []
    n_x, n_y = 10, 6
    for i in range(n_x + 1):
        x = bx0 + (bx1 - bx0) * i / n_x
        pts += [(x, by0), (x, by1)]
    for j in range(1, n_y):
        y = by0 + (by1 - by0) * j / n_y
        pts += [(bx0, y), (bx1, y)]
    halo = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    for x, y in pts:
        hd.ellipse([x - r * 2.2, y - r * 2.2, x + r * 2.2, y + r * 2.2], fill=(255, 200, 80, 120))
    img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(4 * K)))
    d = ImageDraw.Draw(img)
    for x, y in pts:
        d.ellipse([x - r, y - r, x + r, y + r], fill=bulb)
        d.ellipse([x - r * 0.45, y - r * 0.55, x - r * 0.05, y - r * 0.15], fill=rgb("#fff3c4"))

    # The panel: an LED matrix
    px0, py0, px1, py1 = x0 + 27 * K, y0 + 26 * K, x1 - 27 * K, y1 - 26 * K
    d.rounded_rectangle([px0, py0, px1, py1], radius=6 * K, fill=rgb("#0d0f14"))
    cols, rows = 26, 13
    pitch_x = (px1 - px0 - 8 * K) / cols
    pitch_y = (py1 - py0 - 8 * K) / rows
    dot = min(pitch_x, pitch_y) * 0.36
    red, green, off = rgb("#ff4545"), rgb("#3ee66d"), rgb("#1f2430")
    # Three lines of "text": (row range, first col, last col, colour)
    lines = [((1, 3), 3, 22, red), ((5, 7), 5, 20, green), ((9, 11), 4, 17, red)]
    for rr in range(rows):
        for cc in range(cols):
            col = off
            for (ra, rb), ca, cb, c in lines:
                # gaps between "words" so the bars read as text
                if ra <= rr <= rb and ca <= cc <= cb and (cc - ca) % 7 != 6:
                    col = c
            cx = px0 + 4 * K + pitch_x * (cc + 0.5)
            cy = py0 + 4 * K + pitch_y * (rr + 0.5)
            d.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], fill=col)

    img.resize((S, S), Image.LANCZOS).save(out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "icon.png")
