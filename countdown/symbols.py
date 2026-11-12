"""Weather symbols for the weather page: sun, moon and wind.

Drawn in code at 4x the size asked for and scaled down (like the social media
logos), so every size is sharp and no image files are needed. Pillow is
imported only when a symbol is drawn.
"""

import math
import threading
from typing import Dict, Tuple

SYMBOLS = ("sun", "moon", "wind")
NAMES = {"sun": "Sun", "moon": "Moon", "wind": "Wind"}

SS = 4
SUN = (255, 196, 0)
MOON = (244, 233, 176)
WIND = (127, 211, 255)

_cache: Dict[Tuple[str, int], "object"] = {}
_lock = threading.Lock()


def _sun(S):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = S / 2
    r = 0.24 * S
    d.ellipse([c - r, c - r, c + r, c + r], fill=SUN)
    # 8 rays, each a short thick line with round ends
    w = max(1, round(0.085 * S))
    for i in range(8):
        a = math.pi / 4 * i
        r0, r1 = 0.33 * S, 0.46 * S
        p0 = (c + r0 * math.cos(a), c + r0 * math.sin(a))
        p1 = (c + r1 * math.cos(a), c + r1 * math.sin(a))
        d.line([p0, p1], fill=SUN, width=w)
        for p in (p0, p1):
            d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=SUN)
    return img


def _moon(S):
    from PIL import Image, ImageChops, ImageDraw
    disc = Image.new("L", (S, S), 0)
    ImageDraw.Draw(disc).ellipse([0.12 * S, 0.12 * S, 0.88 * S, 0.88 * S], fill=255)
    bite = Image.new("L", (S, S), 0)
    ImageDraw.Draw(bite).ellipse([0.34 * S, 0.02 * S, 1.02 * S, 0.70 * S], fill=255)
    crescent = ImageChops.subtract(disc, bite)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(MOON + (255,), (0, 0), crescent)
    return img


def _wind(S):
    """Three streamlines, each ending in a curl, of different lengths."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = max(1, round(0.075 * S))
    # (y of the line, x where it starts, x where the curl is, curl radius, curl up?)
    for y, x0, x1, rad, up in ((0.32, 0.08, 0.60, 0.12, True),
                               (0.52, 0.06, 0.80, 0.11, False),
                               (0.72, 0.18, 0.50, 0.10, False)):
        y, x0, x1, rad = y * S, x0 * S, x1 * S, rad * S
        d.line([(x0, y), (x1, y)], fill=WIND, width=w)
        # A curl: most of a circle sitting on the line's end, turning back
        cy = y - rad if up else y + rad
        box = [x1 - rad, cy - rad, x1 + rad, cy + rad]
        if up:
            d.arc(box, start=-180, end=90, fill=WIND, width=w)
        else:
            d.arc(box, start=-90, end=180, fill=WIND, width=w)
        for px, py in ((x0, y),):
            d.ellipse([px - w / 2, py - w / 2, px + w / 2, py + w / 2], fill=WIND)
    return img


_DRAW = {"sun": _sun, "moon": _moon, "wind": _wind}


def draw_symbol(name: str, size: int):
    """The symbol as a size x size RGBA image (cached)."""
    from PIL import Image
    size = max(1, int(size))
    key = (name, size)
    with _lock:
        img = _cache.get(key)
        if img is None:
            img = _DRAW[name](size * SS).resize((size, size), Image.LANCZOS)
            if len(_cache) > 48:
                _cache.clear()
            _cache[key] = img
        return img
