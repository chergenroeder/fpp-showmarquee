"""Social media screens: logos on the top line, @handle on the bottom line.

  clean_handle()    "  @Smith_Lights " -> "Smith_Lights"; "" if not usable.
  social_screens()  the screens to show, one per distinct handle: sites that
                    share a handle (ignoring case and "@") share a screen.
  draw_logo()       one site's logo, drawn in code at 4x and scaled down, so
                    it is sharp at any size and no image files are needed.
  draw_screen()     a whole panel-sized screen, held still on the matrix.

Logos are trademarks of their owners; they are shown only to point people to
the user's own profiles.

Grouping and handles need nothing beyond the standard library; drawing needs
Pillow, imported only when a screen or logo is drawn.
"""

import re
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# (key, name shown on the page), in the order screens and logos appear
SITES: Tuple[Tuple[str, str], ...] = (
    ("facebook", "Facebook"),
    ("instagram", "Instagram"),
    ("tiktok", "TikTok"),
    ("youtube", "YouTube"),
)
SITE_NAMES: Dict[str, str] = dict(SITES)

HANDLE_MAX = 30
_HANDLE_OK = re.compile(r"^[A-Za-z0-9._-]+$")


def clean_handle(value) -> str:
    """The handle without "@" or spaces around it; "" if empty."""
    return str(value or "").strip().lstrip("@").strip()


def handle_problem(value) -> str:
    """Why a typed handle can't be used, or "" if it's fine (or empty)."""
    h = clean_handle(value)
    if not h:
        return ""
    if len(h) > HANDLE_MAX:
        return f"is longer than {HANDLE_MAX} characters"
    if not _HANDLE_OK.match(h):
        return "may only have letters, digits, dots, underscores and dashes"
    return ""


@dataclass(frozen=True)
class Screen:
    sites: Tuple[str, ...]   # site keys, in SITES order
    handle: str              # as typed for the first of these sites, without "@"

    @property
    def plain(self) -> str:
        return " ".join(f"[{SITE_NAMES[s]}]" for s in self.sites) + f" @{self.handle}"

    @property
    def slot(self) -> str:
        return "social:" + "+".join(self.sites)


def social_screens(cfg: dict) -> List[Screen]:
    """The screens for the social settings, in order; [] when social is off."""
    if not cfg.get("enabled"):
        return []
    sites = cfg.get("sites") or {}
    groups: Dict[str, List[str]] = {}
    shown: Dict[str, str] = {}
    for key, _name in SITES:
        s = sites.get(key) or {}
        h = clean_handle(s.get("handle"))
        if not s.get("enabled") or not h or handle_problem(h):
            continue
        k = h.lower()
        if k not in groups:
            groups[k], shown[k] = [], h
        groups[k].append(key)
    return [Screen(tuple(v), shown[k]) for k, v in groups.items()]


def social_status(cfg: dict) -> dict:
    """What the page needs: the screens, and sites that are on but can't show."""
    sites = cfg.get("sites") or {}
    problems = {}
    for key, name in SITES:
        s = sites.get(key) or {}
        if not s.get("enabled"):
            continue
        if not clean_handle(s.get("handle")):
            problems[key] = f"{name} is on but has no handle"
        elif handle_problem(s.get("handle")):
            problems[key] = f"{name} handle {handle_problem(s.get('handle'))}"
    return {"enabled": bool(cfg.get("enabled")),
            "screen_seconds": float(cfg.get("screen_seconds", 5) or 5),
            "screens": [{"sites": list(sc.sites), "handle": sc.handle, "plain": sc.plain}
                        for sc in social_screens(cfg)],
            "problems": problems}


# ── Logos ─────────────────────────────────────────────────────────────────────
# Each is drawn in a square of side S (4x the final size) and scaled down.

SS = 4                       # supersampling
FACEBOOK_BLUE = (8, 102, 255)
YOUTUBE_RED = (255, 0, 0)
TIKTOK_CYAN = (37, 244, 238)
TIKTOK_RED = (254, 44, 85)
WHITE = (255, 255, 255)
# Instagram's gradient, from the bottom-left corner to the top-right
INSTAGRAM_STOPS = ((0.0, (254, 218, 117)), (0.25, (250, 126, 30)), (0.5, (214, 41, 118)),
                   (0.75, (150, 47, 191)), (1.0, (79, 91, 213)))

_logo_cache: Dict[Tuple[str, int], "object"] = {}
_logo_lock = threading.Lock()


def _box(S, x0, y0, x1, y1):
    return [round(x0 * S), round(y0 * S), round(x1 * S), round(y1 * S)]


def _facebook(S):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse(_box(S, 0, 0, 1, 1), fill=FACEBOOK_BLUE + (255,))
    # The white "f", running out through the bottom of the circle
    f = Image.new("L", (S, S), 0)
    fd = ImageDraw.Draw(f)
    fd.rounded_rectangle(_box(S, 0.435, 0.17, 0.705, 0.30), radius=round(0.065 * S), fill=255)  # top
    fd.rectangle(_box(S, 0.435, 0.235, 0.585, 1.0), fill=255)                      # stem
    fd.rectangle(_box(S, 0.335, 0.46, 0.685, 0.585), fill=255)                     # bar
    circle = Image.new("L", (S, S), 0)
    ImageDraw.Draw(circle).ellipse(_box(S, 0, 0, 1, 1), fill=255)
    from PIL import ImageChops
    img.paste(WHITE + (255,), (0, 0), ImageChops.multiply(f, circle))
    return img


def _instagram(S):
    from PIL import Image, ImageDraw
    # Diagonal gradient, bottom-left to top-right
    grad = Image.new("RGB", (S, S))
    px = []
    for y in range(S):
        for x in range(S):
            t = (x + (S - 1 - y)) / (2 * (S - 1))
            for (t0, c0), (t1, c1) in zip(INSTAGRAM_STOPS, INSTAGRAM_STOPS[1:]):
                if t <= t1:
                    k = (t - t0) / (t1 - t0)
                    px.append(tuple(round(a + (b - a) * k) for a, b in zip(c0, c1)))
                    break
    grad.putdata(px)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(_box(S, 0, 0, 1, 1), radius=round(0.28 * S), fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    w = max(1, round(0.085 * S))
    d.rounded_rectangle(_box(S, 0.17, 0.17, 0.83, 0.83), radius=round(0.19 * S), outline=WHITE, width=w)
    d.ellipse(_box(S, 0.335, 0.335, 0.665, 0.665), outline=WHITE, width=w)
    d.ellipse(_box(S, 0.655, 0.255, 0.745, 0.345), fill=WHITE)
    return img


def _tiktok_note(S):
    """The note's shape as a mask: a bowl, a stem and a curved flag."""
    from PIL import Image, ImageDraw
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    # bowl: a ring around (0.40, 0.66)
    d.ellipse(_box(S, 0.19, 0.45, 0.61, 0.87), fill=255)
    d.ellipse(_box(S, 0.31, 0.57, 0.49, 0.75), fill=0)
    # stem, flush with the bowl's right side
    d.rectangle(_box(S, 0.49, 0.10, 0.61, 0.66), fill=255)
    # flag: a quarter disc from the top of the stem, with a curved cut-out below
    d.pieslice(_box(S, 0.37, -0.14, 0.85, 0.34), 0, 90, fill=255)
    d.rectangle(_box(S, 0.61, 0.10, 0.85, 0.12), fill=255)
    d.ellipse(_box(S, 0.61, 0.26, 0.97, 0.62), fill=0)
    d.rectangle(_box(S, 0.61, 0.33, 1.0, 1.0), fill=0)
    d.rectangle(_box(S, 0.49, 0.10, 0.61, 0.66), fill=255)
    return m


def _tiktok(S):
    from PIL import Image, ImageChops
    note = _tiktok_note(S)
    off = max(1, round(0.045 * S))
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(TIKTOK_CYAN + (255,), (0, 0), ImageChops.offset(note, -off, -off))
    img.paste(TIKTOK_RED + (255,), (0, 0), ImageChops.offset(note, off, off))
    img.paste(WHITE + (255,), (0, 0), note)
    return img


def _youtube(S):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(_box(S, 0, 0.15, 1, 0.85), radius=round(0.2 * S), fill=YOUTUBE_RED + (255,))
    d.polygon([(0.40 * S, 0.32 * S), (0.40 * S, 0.68 * S), (0.70 * S, 0.50 * S)], fill=WHITE)
    return img


_DRAW = {"facebook": _facebook, "instagram": _instagram, "tiktok": _tiktok, "youtube": _youtube}


def draw_logo(site: str, size: int):
    """The site's logo as a size x size RGBA image (cached)."""
    from PIL import Image
    size = max(1, int(size))
    key = (site, size)
    with _logo_lock:
        img = _logo_cache.get(key)
        if img is None:
            big = _DRAW[site](size * SS)
            img = big.resize((size, size), Image.LANCZOS)
            if len(_logo_cache) > 64:
                _logo_cache.clear()
            _logo_cache[key] = img
        return img


# ── The screen ────────────────────────────────────────────────────────────────

MIN_LOGO = 6


def _logo_gap(size: int) -> int:
    return max(1, size // 5)


def layout_screen(n_logos: int, text_w_at, text_h_at, start_size: int, min_size: int,
                  panel_w: int, panel_h: int) -> Tuple[int, int, bool]:
    """(font size, logo size, handle fits) for a screen.

    text_w_at / text_h_at give the handle's ink width and height at a font
    size. The handle shrinks until it fits the width; it shrinks further only
    if that leaves no room for logos of at least MIN_LOGO.
    """
    size = max(min_size, int(start_size))
    while size > min_size and text_w_at(size) > panel_w:
        size -= 1
    fits = text_w_at(size) <= panel_w

    def logo_for(sz):
        gap = max(1, panel_h // 16)
        by_h = panel_h - text_h_at(sz) - gap
        # n logos plus the gaps between them must fit across
        by_w = panel_w
        for s in range(panel_w, 0, -1):
            if n_logos * s + (n_logos - 1) * _logo_gap(s) <= panel_w:
                by_w = s
                break
        return max(0, min(by_h, by_w))

    while size > min_size and logo_for(size) < MIN_LOGO:
        size -= 1
    return size, logo_for(size), fits


def draw_screen(screen: Screen, panel_w: int, panel_h: int, style):
    """The screen as a panel-sized RGB image, plus whether the handle fits.

    style is a render.Style: the handle uses its font and colour, starting at
    its size and shrinking to fit.
    """
    from PIL import Image, ImageDraw
    from .render import MIN_FONT_SIZE
    text = "@" + screen.handle

    def bbox(sz):
        return style.font(sz).getbbox(text, anchor="ls")   # (left, top, right, bottom) around the baseline

    font_size, logo, fits = layout_screen(
        len(screen.sites), lambda s: bbox(s)[2] - bbox(s)[0], lambda s: bbox(s)[3] - bbox(s)[1],
        style.size, MIN_FONT_SIZE, panel_w, panel_h)
    font = style.font(font_size)
    left, top, right, bottom = bbox(font_size)
    text_w, text_h = right - left, bottom - top
    gap = max(1, panel_h // 16) if logo else 0
    block_h = (logo + gap if logo else 0) + text_h
    y = (panel_h - block_h) // 2

    img = Image.new("RGB", (panel_w, panel_h))
    if logo:
        g = _logo_gap(logo)
        row_w = len(screen.sites) * logo + (len(screen.sites) - 1) * g
        x = (panel_w - row_w) // 2
        for site in screen.sites:
            mark = draw_logo(site, logo)
            img.paste(mark, (x, y), mark)
            x += logo + g
        y += logo + gap
    draw = ImageDraw.Draw(img)
    draw.fontmode = "L" if style.antialias else "1"
    draw.text(((panel_w - text_w) // 2 - left, y - top), text, fill=style.color, font=font, anchor="ls")
    return img, fits
