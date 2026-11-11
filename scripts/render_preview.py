#!/usr/bin/env python3
"""Preview the renderer without a matrix: a contact sheet PNG and animated GIFs.

    python3 scripts/render_preview.py --out /tmp/preview --font /path/to/Font.ttf

  sheet.png        one mid-pass frame for each direction x number order, plus
                   the two-line layout on a narrow panel, scaled up like LEDs
  <direction>.gif  a few seconds of motion for each direction (HH:MM:SS ticking)
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from PIL import Image, ImageDraw  # noqa: E402

from countdown.message import build_message  # noqa: E402
from countdown.render import DIRECTIONS, Renderer  # noqa: E402
from countdown.timecalc import Target, compute_display  # noqa: E402

LABELS = {"L2R": "Left to Right", "R2L": "Right to Left", "T2B": "Top to Bottom",
          "B2T": "Bottom to Top", "static": "Static"}


def leds(frame: Image.Image, scale: int) -> Image.Image:
    """Scale up and leave a dark gap between pixels, like an LED panel."""
    big = frame.resize((frame.width * scale, frame.height * scale), Image.NEAREST)
    if scale >= 3:
        d = ImageDraw.Draw(big)
        for x in range(0, big.width, scale):
            d.line([(x, 0), (x, big.height)], fill=(18, 18, 18))
        for y in range(0, big.height, scale):
            d.line([(0, y), (big.width, y)], fill=(18, 18, 18))
    return big


def cfg(direction, order, args, under="hms"):
    return {
        "layout": {"number_position": order, "under_one_day": under},
        "motion": {"direction": direction, "pixels_per_second": args.pps, "repeat_delay": 0},
        "text_style": {"font": "t", "size": args.text_size, "color": args.text_color},
        "number_style": {"font": "n", "size": args.number_size, "color": args.number_color},
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--font", help="font file for both styles (default: Pillow's built-in)")
    p.add_argument("--number-font", help="font file for the number (default: --font)")
    p.add_argument("--width", type=int, default=192)
    p.add_argument("--height", type=int, default=96)
    p.add_argument("--narrow", type=int, default=96, help="panel width for the two-line example")
    p.add_argument("--text-size", type=int, default=14)
    p.add_argument("--number-size", type=int, default=20)
    p.add_argument("--text-color", default="#ff2020")
    p.add_argument("--number-color", default="#20ff40")
    p.add_argument("--pps", type=float, default=30)
    p.add_argument("--scale", type=int, default=3)
    args = p.parse_args()
    os.makedirs(args.out, exist_ok=True)

    fonts = {"t": args.font, "n": args.number_font or args.font}
    resolve = fonts.get
    tz_now = datetime(2026, 12, 17, 15, 0).astimezone()
    xmas = Target(datetime(2026, 12, 25).astimezone(), "Christmas", "christmas", True)

    def message(order, now, under="hms"):
        layout = {"number_position": order, "under_one_day": under}
        return build_message(compute_display(xmas, now, layout), xmas, layout)

    # Contact sheet: each direction x order, mid-pass
    tiles = []
    for direction in DIRECTIONS:
        for order in ("first", "last"):
            r = Renderer(args.width, args.height, cfg(direction, order, args), resolve)
            m = message(order, tz_now)
            strip = r.strip_for(m)
            horizontal = direction in ("L2R", "R2L")
            span = (args.width + strip.width) if horizontal else (args.height + strip.height)
            t = (span / 2) / args.pps
            r.frame(m, 0)
            tiles.append((f"{LABELS[direction]}, number {order}: \"{m.plain}\"", r.frame(m, t)))
    eve = datetime(2026, 12, 24, 15, 45, 28).astimezone()
    for under in ("hms", "hours"):
        r = Renderer(args.width, args.height, cfg("static", "first", args, under), resolve)
        m = message("first", eve, under)
        tiles.append((f"Under 1 day ({under}), static: \"{m.plain}\"", r.frame(m, 0)))
    r = Renderer(args.narrow, args.height, cfg("static", "first", args), resolve)
    m = message("first", tz_now)
    tiles.append((f"Two-line fallback on a {args.narrow}x{args.height} panel: \"{m.plain}\"", r.frame(m, 0)))

    pad, label_h = 10, 16
    tile_w = args.width * args.scale
    tile_h = args.height * args.scale
    cols = 2
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tile_w + pad) + pad, rows * (tile_h + label_h + pad) + pad), (40, 40, 40))
    d = ImageDraw.Draw(sheet)
    for i, (label, frame) in enumerate(tiles):
        x = pad + (i % cols) * (tile_w + pad)
        y = pad + (i // cols) * (tile_h + label_h + pad)
        d.text((x, y), label, fill=(230, 230, 230))
        sheet.paste(leds(frame, args.scale), (x, y + label_h))
    sheet.save(os.path.join(args.out, "sheet.png"))

    # GIFs: 4 s of each direction, number first, HH:MM:SS ticking on Christmas Eve
    fps = 20
    for direction in DIRECTIONS:
        r = Renderer(args.width, args.height, cfg(direction, "first", args), resolve)
        frames = []
        for i in range(fps * 4):
            t = i / fps
            m = message("first", eve + timedelta(seconds=t))
            frames.append(leds(r.frame(m, t), 2))
        frames[0].save(os.path.join(args.out, f"{direction}.gif"), save_all=True,
                       append_images=frames[1:], duration=1000 // fps, loop=0)
    print(f"Wrote {args.out}/sheet.png and {len(DIRECTIONS)} GIFs")


if __name__ == "__main__":
    main()
