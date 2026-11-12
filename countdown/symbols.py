"""Pictures drawn on the pages: the weather symbols (sun, moon, wind, cloud,
partly cloudy by day and night, rain, sleet, snow, thunderstorm, fog) and the
custom messages' holiday pictures (star, tree, snowflake, gift, candy cane, heart).

Drawn in code at 4x the size asked for and scaled down (like the social media
logos), so every size is sharp and no image files are needed. Pillow is
imported only when a symbol is drawn.
"""

import math
import threading
from typing import Dict, Tuple

SYMBOLS = ("sun", "moon", "partly_day", "partly_night", "cloud", "fog", "wind",
           "rain", "sleet", "snow", "storm")
NAMES = {"sun": "Sun", "moon": "Moon", "wind": "Wind", "partly_day": "Partly cloudy",
         "partly_night": "Partly cloudy", "cloud": "Cloudy", "fog": "Fog", "rain": "Rain",
         "sleet": "Sleet", "snow": "Snow", "storm": "Thunderstorm"}

SS = 4
SUN = (255, 196, 0)
MOON = (244, 233, 176)
WIND = (127, 211, 255)
GOLD = (255, 196, 0)
CLOUD = (215, 222, 232)
STORM_CLOUD = (150, 160, 180)
RAIN = (70, 150, 255)
FLAKE = (255, 255, 255)
FOG = (185, 195, 205)
CLEAR = (0, 0, 0, 0)

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


def _cloud(d, x0, y0, w, fill, grow=0.0):
    """A cloud w wide (and w / 1.6 tall) with its top-left at x0, y0: a flat-bottomed
    pill with two bumps on top. grow makes it bigger all round (to cut a gap)."""
    h = w / 1.6
    g = grow
    d.rounded_rectangle([x0 - g, y0 + 0.45 * h - g, x0 + w + g, y0 + h + g], radius=0.275 * h + g, fill=fill)
    for cx, cy, r in ((0.32 * w, 0.55 * h, 0.30 * h), (0.60 * w, 0.40 * h, 0.40 * h)):
        d.ellipse([x0 + cx - r - g, y0 + cy - r - g, x0 + cx + r + g, y0 + cy + r + g], fill=fill)


def _plain_cloud(S):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (S, S), CLEAR)
    w = 0.92 * S
    _cloud(ImageDraw.Draw(img), 0.04 * S, (S - w / 1.6) / 2, w, CLOUD)
    return img


def _partly(S, night: bool):
    """The sun (or moon) up to the right, a cloud in front of it to the lower left."""
    from PIL import Image, ImageDraw, ImageOps
    img = Image.new("RGBA", (S, S), CLEAR)
    b = round(0.66 * S)
    behind = ImageOps.mirror(_moon(b)) if night else _sun(b)
    img.paste(behind, (S - b, 0), behind)
    d = ImageDraw.Draw(img)
    w = 0.82 * S
    x0, y0 = 0.02 * S, S - w / 1.6 - 0.04 * S
    _cloud(d, x0, y0, w, CLEAR, grow=0.05 * S)       # a dark gap around the cloud
    _cloud(d, x0, y0, w, CLOUD)
    return img


def _drop(d, x, y, S, fill):
    """A raindrop: a short slanted stroke with round ends, its top at x, y."""
    w = max(1, round(0.075 * S))
    x1, y1 = x - 0.07 * S, y + 0.22 * S
    d.line([(x, y), (x1, y1)], fill=fill, width=w)
    for px, py in ((x, y), (x1, y1)):
        d.ellipse([px - w / 2, py - w / 2, px + w / 2, py + w / 2], fill=fill)


def _flake(d, x, y, S):
    """A small six-armed snowflake centred on x, y."""
    r, w = 0.12 * S, max(1, round(0.06 * S))
    for i in range(3):
        a = math.pi / 3 * i + math.pi / 2
        d.line([(x - r * math.cos(a), y - r * math.sin(a)), (x + r * math.cos(a), y + r * math.sin(a))],
               fill=FLAKE, width=w)


def _falling(S, kind: str):
    """A cloud across the top with rain, sleet or snow under it."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (S, S), CLEAR)
    d = ImageDraw.Draw(img)
    _cloud(d, 0.06 * S, 0.04 * S, 0.88 * S, CLOUD)
    xs = (0.30, 0.53, 0.76)
    for i, x in enumerate(xs):
        x = x * S
        if kind == "snow" or (kind == "sleet" and i == 1):
            y = (0.75 if i % 2 == 0 else 0.86) * S
            if kind == "sleet":                             # an ice pellet between two drops
                r = 0.065 * S
                d.ellipse([x - 0.04 * S - r, 0.80 * S - r, x - 0.04 * S + r, 0.80 * S + r], fill=FLAKE)
            else:
                _flake(d, x - 0.03 * S, y, S)
        else:
            _drop(d, x, 0.68 * S, S, RAIN)
    return img


def _storm(S):
    """A grey cloud with a lightning bolt coming out of it."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (S, S), CLEAR)
    d = ImageDraw.Draw(img)
    _cloud(d, 0.06 * S, 0.04 * S, 0.88 * S, STORM_CLOUD)
    bolt = [(0.60, 0.36), (0.36, 0.68), (0.50, 0.68), (0.40, 0.98), (0.70, 0.58), (0.55, 0.58), (0.68, 0.36)]
    pts = [(x * S, y * S) for x, y in bolt]
    d.line(pts + [pts[0]], fill=CLEAR, width=max(1, round(0.08 * S)), joint="curve")   # a gap round the bolt
    d.polygon(pts, fill=GOLD)
    return img


def _fog(S):
    """Four soft horizontal bands of different lengths."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (S, S), CLEAR)
    d = ImageDraw.Draw(img)
    w = max(1, round(0.09 * S))
    for y, x0, x1 in ((0.24, 0.12, 0.78), (0.42, 0.22, 0.92), (0.60, 0.08, 0.72), (0.78, 0.28, 0.90)):
        y, x0, x1 = y * S, x0 * S, x1 * S
        d.line([(x0, y), (x1, y)], fill=FOG, width=w)
        for px in (x0, x1):
            d.ellipse([px - w / 2, y - w / 2, px + w / 2, y + w / 2], fill=FOG)
    return img


# ── Holiday pictures for custom messages ──────────────────────────────────────

GREEN = (46, 184, 75)
RED = (230, 40, 50)
WHITE = (255, 255, 255)
ICE = (170, 225, 255)
BROWN = (130, 80, 40)


def _star_points(cx, cy, r_out, r_in, n=5, rot=-math.pi / 2):
    pts = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        a = rot + math.pi * i / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _star(S):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(img).polygon(_star_points(S / 2, S * 0.53, S * 0.47, S * 0.20), fill=GOLD)
    return img


def _tree(S):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([S * 0.43, S * 0.80, S * 0.57, S * 0.96], fill=BROWN)
    # three tiers, widest at the bottom
    for top, bottom, half in ((0.14, 0.42, 0.22), (0.30, 0.62, 0.32), (0.48, 0.84, 0.42)):
        d.polygon([(S / 2, S * top), (S / 2 - S * half, S * bottom), (S / 2 + S * half, S * bottom)], fill=GREEN)
    d.polygon(_star_points(S / 2, S * 0.13, S * 0.12, S * 0.05), fill=GOLD)
    r = S * 0.045
    for x, y, c in ((0.42, 0.38, RED), (0.60, 0.55, GOLD), (0.38, 0.70, GOLD), (0.66, 0.76, RED), (0.50, 0.62, ICE)):
        d.ellipse([S * x - r, S * y - r, S * x + r, S * y + r], fill=c)
    return img


def _snowflake(S):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c, R = S / 2, S * 0.46
    w = max(1, round(S * 0.07))
    for i in range(6):
        a = math.pi / 3 * i + math.pi / 2
        tip = (c + R * math.cos(a), c + R * math.sin(a))
        d.line([(c, c), tip], fill=ICE, width=w)
        # two little branches on each arm
        for along, length in ((0.55, 0.20), (0.80, 0.14)):
            bx, by = c + R * along * math.cos(a), c + R * along * math.sin(a)
            for side in (-1, 1):
                b = a + side * math.pi / 4
                d.line([(bx, by), (bx + R * length * math.cos(b), by + R * length * math.sin(b))], fill=ICE, width=w)
    d.ellipse([c - w, c - w, c + w, c + w], fill=WHITE)
    return img


def _gift(S):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([S * 0.12, S * 0.42, S * 0.88, S * 0.94], fill=RED)          # box
    d.rectangle([S * 0.06, S * 0.30, S * 0.94, S * 0.44], fill=(200, 25, 40))  # lid
    d.rectangle([S * 0.44, S * 0.30, S * 0.56, S * 0.94], fill=GOLD)          # ribbon down
    d.rectangle([S * 0.06, S * 0.34, S * 0.94, S * 0.40], fill=GOLD)          # ribbon across the lid
    # bow: two loops
    d.ellipse([S * 0.22, S * 0.08, S * 0.50, S * 0.32], outline=GOLD, width=max(1, round(S * 0.07)))
    d.ellipse([S * 0.50, S * 0.08, S * 0.78, S * 0.32], outline=GOLD, width=max(1, round(S * 0.07)))
    return img


def _candycane(S):
    from PIL import Image, ImageChops, ImageDraw
    w = round(S * 0.17)
    shape = Image.new("L", (S, S), 0)
    sd = ImageDraw.Draw(shape)
    # the hook: an arc over the top, then the stick down the right-hand side
    box = [S * 0.18, S * 0.06, S * 0.72, S * 0.60]
    sd.arc(box, start=180, end=360, fill=255, width=w)
    sd.line([(S * 0.72 - w / 2, S * 0.33), (S * 0.72 - w / 2, S * 0.95)], fill=255, width=w)
    sd.ellipse([S * 0.18, S * 0.33 - w / 2, S * 0.18 + w, S * 0.33 + w / 2], fill=255)    # round end of the hook
    stripes = Image.new("L", (S, S), 0)
    td = ImageDraw.Draw(stripes)
    step = S * 0.17
    k = -S
    while k < 2 * S:
        td.polygon([(k, 0), (k + step * 0.5, 0), (k + step * 0.5 + S, S), (k + S, S)], fill=255)
        k += step
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(WHITE + (255,), (0, 0), shape)
    img.paste(RED + (255,), (0, 0), ImageChops.multiply(shape, stripes))
    return img


def _heart(S):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = S * 0.25
    d.ellipse([S * 0.05, S * 0.12, S * 0.05 + 2 * r, S * 0.12 + 2 * r], fill=RED)
    d.ellipse([S * 0.95 - 2 * r, S * 0.12, S * 0.95, S * 0.12 + 2 * r], fill=RED)
    d.polygon([(S * 0.07, S * 0.45), (S * 0.93, S * 0.45), (S / 2, S * 0.92)], fill=RED)
    return img


PICTURES = ("star", "tree", "snowflake", "gift", "candycane", "heart")

_DRAW = {"sun": _sun, "moon": _moon, "wind": _wind, "cloud": _plain_cloud,
         "partly_day": lambda S: _partly(S, False), "partly_night": lambda S: _partly(S, True),
         "rain": lambda S: _falling(S, "rain"), "sleet": lambda S: _falling(S, "sleet"),
         "snow": lambda S: _falling(S, "snow"), "storm": _storm, "fog": _fog, "star": _star, "tree": _tree, "snowflake": _snowflake,
         "gift": _gift, "candycane": _candycane, "heart": _heart}


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
