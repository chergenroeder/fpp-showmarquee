"""Still pages: drawn once, held on the matrix for the seconds per page, never scrolled.

Three kinds take turns with the countdown (also held still, see render.py):
  weather.WeatherPage    a sun/moon/wind symbol beside the temperature, wind and
                         gust lines (drawn here)
  social.Screen          logos above an @handle (drawn by social.draw_screen)
  showprep.ShowPrepPage  a QR code to the show's audio app beside a message
                         (drawn here)

is_still() tells the drawing loop which items are drawn here (the countdown is
drawn by render.Renderer, centered), page_seconds() how long every page shows,
and StillCache draws each page once per panel and style.
"""

from typing import Dict, List, Optional, Tuple

from .showprep import ShowPrepPage
from .social import Screen
from .weather import WeatherPage

MIN_SYMBOL = 6
READABLE = 8     # smallest font size worth showing: lines are dropped or shortened before this
LINE_GAP = 1


def is_still(item) -> bool:
    return isinstance(item, (Screen, WeatherPage, ShowPrepPage))


def page_seconds(cfg: dict) -> float:
    """How long each page (countdown, weather, each social screen) stays up."""
    try:
        return min(600.0, max(1.0, float((cfg.get("global") or {}).get("screen_seconds", 5) or 5)))
    except (TypeError, ValueError):
        return 5.0


# ── Weather page layout ───────────────────────────────────────────────────────

def _ink(font, text) -> Tuple[int, int, int, int]:
    return font.getbbox(text, anchor="ls")


def fit_lines(lines: List[Tuple[str, object]], width: int, height: int,
              min_size: int) -> Optional[List[int]]:
    """Font sizes for (text, style) lines stacked in width x height, or None.

    Lines with the same style share one size (so the wind and gust lines
    match). Each style starts at its own size and shrinks until all its lines
    fit the width; while the stack is too tall, the largest shrinks one size.
    None when it can't fit without going below min_size.
    """
    styles = []
    for _t, st in lines:
        if st not in styles:
            styles.append(st)
    size = {}
    for st in styles:
        sz = int(st.size)
        while sz >= min_size and any(_ink(st.font(sz), t)[2] - _ink(st.font(sz), t)[0] > width
                                     for t, s2 in lines if s2 == st):
            sz -= 1
        if sz < min_size:
            return None
        size[st] = sz

    def total():
        return sum(_ink(st.font(size[st]), t)[3] - _ink(st.font(size[st]), t)[1]
                   for t, st in lines) + LINE_GAP * (len(lines) - 1)

    while total() > height:
        st = max(reversed(styles), key=lambda k: size[k])   # on a tie, the later line (wind) first
        if size[st] <= min_size:
            return None
        size[st] -= 1
    return [size[st] for _t, st in lines]


SYMBOL_SHARES = (0.40, 0.35, 0.30)   # of the panel width, tried in turn to make room for the text


def _without_direction(wind: str) -> str:
    """ "18 mph NW" -> "18 mph" """
    from .weather import COMPASS
    words = wind.split()
    return " ".join(words[:-1]) if len(words) > 2 and words[-1] in COMPASS else wind


def page_variants(page: WeatherPage) -> List[Tuple[str, ...]]:
    """The page's lines, then shorter versions to try when they don't fit:
    without the gust line, then the wind without its direction, then the
    first line alone."""
    full = page.lines
    short_wind = _without_direction(page.wind)
    out: List[Tuple[str, ...]] = [full]
    for v in ((page.temp, page.wind), (page.temp, short_wind), (page.temp or short_wind,)):
        v = tuple(x for x in v if x)
        if v and v not in out:
            out.append(v)
    return out


def weather_layout(page: WeatherPage, panel_w: int, panel_h: int, number_style, text_style):
    """(symbol size, gap, [(text, style, size)]) for the page.

    For each version of the lines (page_variants), tries the symbol at 40 %,
    35 %, then 30 % of the width, and takes the first where every line is at
    least READABLE. If none is, the first line alone, allowed down to size 4.
    """
    gap = max(1, panel_w // 32)

    def styled(texts):
        # the temperature in the Number style, wind and gusts in the Text style
        return [(t, number_style if t == page.temp else text_style) for t in texts]

    for texts in page_variants(page):
        lines = styled(texts)
        for share in SYMBOL_SHARES:
            sym = max(0, min(panel_h, int(panel_w * share)))
            sizes = fit_lines(lines, panel_w - sym - gap, panel_h, READABLE)
            if sizes is not None:
                return (sym if sym >= MIN_SYMBOL else 0, gap,
                        [(t, s, z) for (t, s), z in zip(lines, sizes)])
    sym = max(0, min(panel_h, int(panel_w * SYMBOL_SHARES[-1])))
    lines = styled(page_variants(page)[-1])
    sizes = fit_lines(lines, panel_w - sym - gap, panel_h, 4) or [4] * len(lines)
    return sym if sym >= MIN_SYMBOL else 0, gap, [(t, s, z) for (t, s), z in zip(lines, sizes)]


def draw_weather_page(page: WeatherPage, panel_w: int, panel_h: int, number_style, text_style):
    """The page as a panel-sized RGB image: symbol on the left, lines to its right."""
    from PIL import Image, ImageDraw
    from .symbols import draw_symbol
    sym, gap, lines = weather_layout(page, panel_w, panel_h, number_style, text_style)
    img = Image.new("RGB", (panel_w, panel_h))
    if sym:
        mark = draw_symbol(page.symbol, sym)
        img.paste(mark, (0, (panel_h - sym) // 2), mark)
    x0 = sym + gap if sym else 0
    area = panel_w - x0
    inks = [_ink(style.font(size), text) for text, style, size in lines]
    block = sum(b - t for _l, t, _r, b in inks) + LINE_GAP * (len(lines) - 1)
    y = (panel_h - block) // 2
    draw = ImageDraw.Draw(img)
    for (text, style, size), (l, t, r, b) in zip(lines, inks):
        draw.fontmode = "L" if style.antialias else "1"
        x = x0 + (area - (r - l)) // 2 - l
        draw.text((x, y - t), text, fill=style.color, font=style.font(size), anchor="ls")
        y += (b - t) + LINE_GAP
    return img


# ── Show prep page ────────────────────────────────────────────────────────────

QR_LIGHT = (225, 225, 225)   # the code's light squares and border, a little under full white so it doesn't glare


def _space(style, size: int) -> float:
    """The gap between words: the font's space, but at least 30 % of the size (pixel fonts' spaces can vanish)."""
    return max(style.font(size).getlength(" "), size * 0.3)


def _wrap(words: List[Tuple[str, object]], size: int, width: int) -> Optional[List[List[Tuple[str, object]]]]:
    """Greedy word wrap at one font size; None if a single word is wider than width."""
    lines: List[List[Tuple[str, object]]] = [[]]

    def line_w(line):
        if not line:
            return 0
        space = _space(line[0][1], size)
        return sum(st.font(size).getlength(w) for w, st in line) + space * (len(line) - 1)

    for word, st in words:
        if st.font(size).getlength(word) > width:
            return None
        if lines[-1] and line_w(lines[-1] + [(word, st)]) > width:
            lines.append([])
        lines[-1].append((word, st))
    return [ln for ln in lines if ln]


def message_layout(page: ShowPrepPage, width: int, height: int, number_style, text_style,
                   min_size: int = READABLE):
    """(font size, lines of (word, style)) for the message, or (None, []) if it can't fit.

    The app's name is in the Number style, the rest in the Text style, all at
    one size: the Text style's size, shrinking until the wrapped lines fit.
    """
    app = page.app_name.lower()
    words = [(w, number_style if w.strip(".,!?:;").lower() == app else text_style)
             for w in page.message.split()]
    if not words:
        return None, []
    for size in range(max(int(text_style.size), min_size), min_size - 1, -1):
        lines = _wrap(words, size, width)
        if lines is None:
            continue
        asc = max(max(st.font(size).getmetrics()[0] for _w, st in ln) for ln in lines)
        desc = max(max(st.font(size).getmetrics()[1] for _w, st in ln) for ln in lines)
        if len(lines) * (asc + desc) + LINE_GAP * (len(lines) - 1) <= height:
            return size, lines
    return None, []


def draw_show_prep(page: ShowPrepPage, panel_w: int, panel_h: int, number_style, text_style):
    """(image, problem): the QR code on the left, the message on the right.

    problem is "" or why the page isn't complete (no QR library, or the code
    doesn't fit the panel), for the settings page.
    """
    from PIL import Image, ImageDraw
    from .showprep import QUIET, best_qr
    img = Image.new("RGB", (panel_w, panel_h))
    problem = ""
    qr_px = 0
    try:
        modules, scale = best_qr(page.link, min(panel_h, panel_w // 2))
    except ImportError:
        modules, scale = None, 0
        problem = "the QR code library (python3-qrcode) isn't installed: Reinstall the plugin"
    if modules is not None:
        n = len(modules)
        qr_px = (n + 2 * QUIET) * scale
        x0, y0 = 0, (panel_h - qr_px) // 2
        d = ImageDraw.Draw(img)
        d.rectangle([x0, y0, x0 + qr_px - 1, y0 + qr_px - 1], fill=QR_LIGHT)
        for r, row in enumerate(modules):
            for c, dark in enumerate(row):
                if dark:
                    x, y = x0 + (QUIET + c) * scale, y0 + (QUIET + r) * scale
                    d.rectangle([x, y, x + scale - 1, y + scale - 1], fill=(0, 0, 0))
    elif not problem:
        problem = f"the QR code doesn't fit a {panel_w}\u00d7{panel_h} matrix"

    gap = max(2, panel_w // 32) if qr_px else 0
    x_text = qr_px + gap
    width = panel_w - x_text
    size, lines = message_layout(page, width, panel_h, number_style, text_style)
    if size is None:
        size, lines = message_layout(page, width, panel_h, number_style, text_style, min_size=4)
        if size is not None and not problem:
            problem = "the message is too small to read beside the QR code: shorten it or use a smaller Text size"
    if size is None:
        return img, problem or "the message doesn't fit beside the QR code: shorten it"
    asc = max(max(st.font(size).getmetrics()[0] for _w, st in ln) for ln in lines)
    desc = max(max(st.font(size).getmetrics()[1] for _w, st in ln) for ln in lines)
    block = len(lines) * (asc + desc) + LINE_GAP * (len(lines) - 1)
    y = (panel_h - block) // 2
    draw = ImageDraw.Draw(img)
    for ln in lines:
        space = _space(ln[0][1], size)
        line_w = sum(st.font(size).getlength(w) for w, st in ln) + space * (len(ln) - 1)
        x = x_text + (width - line_w) / 2
        for w, st in ln:
            draw.fontmode = "L" if st.antialias else "1"
            draw.text((x, y + asc), w, fill=st.color, font=st.font(size), anchor="ls")
            x += st.font(size).getlength(w) + space
        y += asc + desc + LINE_GAP
    return img, problem


# ── Cache ─────────────────────────────────────────────────────────────────────

class StillCache:
    """Draws each still page once per panel size and styles."""

    def __init__(self):
        self._key = None
        self._images: Dict[object, object] = {}

    def get(self, item, panel_w: int, panel_h: int, number_style, text_style):
        key = (panel_w, panel_h, number_style, text_style)
        if key != self._key:
            self._key, self._images = key, {}
        img = self._images.get(item)
        if img is None:
            if len(self._images) > 32:     # weather pages change with the readings
                self._images.clear()
            img = self._images[item] = draw(item, panel_w, panel_h, number_style, text_style)
        return img


def draw(item, panel_w: int, panel_h: int, number_style, text_style):
    if isinstance(item, Screen):
        from .social import draw_screen
        return draw_screen(item, panel_w, panel_h, text_style)[0]
    if isinstance(item, ShowPrepPage):
        return draw_show_prep(item, panel_w, panel_h, number_style, text_style)[0]
    return draw_weather_page(item, panel_w, panel_h, number_style, text_style)
