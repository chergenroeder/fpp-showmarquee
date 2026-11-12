"""Still pages: drawn once, held on the matrix for the seconds per page, never scrolled.

Six kinds take turns with the countdown (also held still, see render.py):
  show.ShowPage          the show's name, its uploaded logo, or both (drawn here)
  weather.WeatherPage    a sun/moon/wind symbol beside the temperature, wind and
                         gust lines (drawn here)
  social.Screen          logos above an @handle (drawn by social.draw_screen)
  showprep.ShowPrepPage  a QR code to the show's audio app beside a message
                         (drawn here)
  schedule.SchedulePage  the show times for the week or tonight (drawn here)
  messages.MessagePage   the user's own message, with an optional picture (drawn here)

is_still() tells the drawing loop which items are drawn here (the countdown is
drawn by render.Renderer, centered), page_seconds() how long every page shows,
and StillCache draws each page once per panel and style.
"""

from typing import Dict, List, Optional, Tuple

from .messages import MessagePage
from .schedule import SchedulePage
from .show import ShowPage
from .showprep import ShowPrepPage
from .social import Screen
from .weather import WeatherPage

MIN_SYMBOL = 6
READABLE = 8     # smallest font size worth showing: lines are dropped or shortened before this
LINE_GAP = 1


def is_still(item) -> bool:
    return isinstance(item, (Screen, WeatherPage, ShowPrepPage, SchedulePage, MessagePage, ShowPage))


def page_seconds(cfg: dict) -> float:
    """How long each page (countdown, weather, each social screen) stays up."""
    try:
        return min(600.0, max(1.0, float((cfg.get("global") or {}).get("screen_seconds", 5) or 5)))
    except (TypeError, ValueError):
        return 5.0


SECTIONS = ("show", "countdown", "weather", "social", "showprep", "schedule", "messages")


def page_order(cfg: dict) -> list:
    """The sections in the order their pages take turns: global.page_order,
    with any section it leaves out added at the end in the usual order."""
    want = (cfg.get("global") or {}).get("page_order")
    want = [s for s in want if s in SECTIONS] if isinstance(want, list) else []
    order = list(dict.fromkeys(want))
    return order + [s for s in SECTIONS if s not in order]


def section_of(slot: str) -> str:
    """ "social:facebook+youtube" -> "social"; "message:2" -> "messages"; "weather" -> "weather" """
    head = slot.split(":", 1)[0]
    return "messages" if head == "message" else head


def order_pages(items: list, cfg: dict) -> list:
    """(slot, page) pairs sorted by their section's place in page_order; a
    section's own pages (social screens, messages) keep their order."""
    rank = {s: i for i, s in enumerate(page_order(cfg))}
    return sorted(items, key=lambda it: rank.get(section_of(it[0]), len(rank)))


def page_order_problems(cfg: dict) -> list:
    v = (cfg.get("global") or {}).get("page_order")
    if v is None:
        return []
    if not isinstance(v, list) or not all(isinstance(s, str) for s in v):
        return ["global.page_order must be a list of section names"]
    bad = [s for s in v if s not in SECTIONS]
    if bad:
        return [f"global.page_order: unknown section {bad[0]!r} (sections: {', '.join(SECTIONS)})"]
    if len(set(v)) != len(v):
        return ["global.page_order lists a section twice"]
    return []


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
    """ "Wind 18 mph NW" -> "Wind 18 mph" """
    from .weather import COMPASS
    words = wind.split()
    return " ".join(words[:-1]) if len(words) > 2 and words[-1] in COMPASS else wind


def _without_label(wind: str, label: str) -> str:
    """ "Wind 18 mph" -> "18 mph" """
    return wind[len(label):].strip() if label and wind.startswith(label + " ") else wind


def page_variants(page: WeatherPage) -> List[Tuple[str, ...]]:
    """The page's lines, then shorter versions to try when they don't fit:
    without the gust line, then the wind without its direction, then without
    its label too (the label says what the number is, so it goes last), then
    the first line alone."""
    full = page.lines
    short_wind = _without_direction(page.wind)
    bare_wind = _without_label(short_wind, page.wind_label)
    out: List[Tuple[str, ...]] = [full]
    for v in ((page.temp, page.wind), (page.temp, short_wind), (page.temp, bare_wind),
              (page.temp or short_wind,)):
        v = tuple(x for x in v if x)
        if v and v not in out:
            out.append(v)
    return out


def weather_layout(page: WeatherPage, panel_w: int, panel_h: int, number_style, text_style):
    """(symbol size, gap, [(text, style, size)]) for the page.

    For each version of the lines (page_variants), in order, tries the symbol
    at 40 %, 35 % and 30 % of the width and keeps the one where the smallest
    line is largest (on a tie, the bigger symbol), as long as every line is at
    least READABLE. If no version fits, the first line alone, down to size 4.
    """
    gap = max(1, panel_w // 32)

    def styled(texts):
        # the temperature in the Number style, wind and gusts in the Text style
        return [(t, number_style if t == page.temp else text_style) for t in texts]

    for texts in page_variants(page):
        lines = styled(texts)
        best = None
        for share in SYMBOL_SHARES:
            sym = max(0, min(panel_h, int(panel_w * share)))
            sizes = fit_lines(lines, panel_w - sym - gap, panel_h, READABLE)
            if sizes is not None and (best is None or min(sizes) > min(best[1])):
                best = (sym, sizes)
        if best is not None:
            sym, sizes = best
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


# ── Schedule page ─────────────────────────────────────────────────────────────

def schedule_layout(page: SchedulePage, panel_w: int, panel_h: int, number_style, text_style,
                    min_size: int = READABLE):
    """(font size, show title, column gap) for the page, or (None, ...) if it can't fit.

    The rows are a table: nights on the left, times on the right, the block
    centered. Everything is one size, the Text style's, shrinking to fit; the
    title goes before the text would go below min_size. With more than one
    line, a narrow column on the left holds the pointer to tonight's line.
    """
    for with_title in ((True, False) if page.title else (False,)):
        for size in range(max(int(text_style.size), int(number_style.size), min_size), min_size - 1, -1):
            gap = max(2, round(size * 0.6))
            tf, nf = text_style.font(size), number_style.font(size)
            day_w = max((max(tf.getlength(ln.days), nf.getlength(ln.days)) for ln in page.lines), default=0)
            time_w = max((nf.getlength(ln.times) for ln in page.lines), default=0)
            row_w = _mark_w(page, size) + day_w + (gap + time_w if time_w else 0)
            title_w = tf.getlength(page.title) if with_title else 0
            line_h = max(tf.getmetrics()[0], nf.getmetrics()[0]) + max(tf.getmetrics()[1], nf.getmetrics()[1])
            rows = len(page.lines) + (1 if with_title else 0)
            if max(row_w, title_w) <= panel_w and rows * line_h + LINE_GAP * (rows - 1) <= panel_h:
                return size, with_title, gap
    return None, False, 0


def _mark_w(page: SchedulePage, size: int) -> int:
    """Width of the column for tonight's pointer (with its gap); 0 with one line, where it would say nothing."""
    if len(page.lines) < 2:
        return 0
    return max(2, round(size * 0.4)) + max(2, round(size * 0.35))


def draw_schedule(page: SchedulePage, panel_w: int, panel_h: int, number_style, text_style):
    """(image, problem): the schedule as a centered table."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (panel_w, panel_h))
    problem = ""
    size, with_title, gap = schedule_layout(page, panel_w, panel_h, number_style, text_style)
    if size is None:
        size, with_title, gap = schedule_layout(page, panel_w, panel_h, number_style, text_style, min_size=4)
        problem = "the schedule is too small to read: use fewer different times or a smaller Text size"
    if size is None:
        return img, "the schedule doesn't fit the matrix"
    if page.title and not with_title and not problem:
        problem = "the title is left off so the times fit"
    tf, nf = text_style.font(size), number_style.font(size)
    asc = max(tf.getmetrics()[0], nf.getmetrics()[0])
    line_h = asc + max(tf.getmetrics()[1], nf.getmetrics()[1])
    day_w = max(tf.getlength(ln.days) for ln in page.lines)
    time_w = max(nf.getlength(ln.times) for ln in page.lines)
    mark_w = _mark_w(page, size)
    rows = len(page.lines) + (1 if with_title else 0)
    y = (panel_h - (rows * line_h + LINE_GAP * (rows - 1))) // 2
    draw = ImageDraw.Draw(img)

    def put(x, text, style):
        draw.fontmode = "L" if style.antialias else "1"
        draw.text((x, y + asc), text, fill=style.color, font=style.font(size), anchor="ls")

    if with_title:
        put((panel_w - tf.getlength(page.title)) / 2, page.title, text_style)
        y += line_h + LINE_GAP
    if time_w:
        x0 = (panel_w - (mark_w + day_w + gap + time_w)) / 2
        for ln in page.lines:
            if ln.today and mark_w:
                # Tonight: a small pointer in the times' colour, as tall as a capital letter
                cap = max(3, round(tf.getbbox("H", anchor="ls")[1] * -1))
                w = max(2, round(size * 0.4))
                top = y + asc - cap
                draw.polygon([(x0, top), (x0, top + cap - 1), (x0 + w - 1, top + (cap - 1) / 2)],
                             fill=number_style.color)
            put(x0 + mark_w, ln.days, text_style)
            if ln.times:
                put(x0 + mark_w + day_w + gap, ln.times, number_style)
            y += line_h + LINE_GAP
    else:
        for ln in page.lines:
            put((panel_w - tf.getlength(ln.days)) / 2, ln.days, text_style)
            y += line_h + LINE_GAP
    return img, problem


def draw_schedule_page(page: SchedulePage, panel_w, panel_h, number_style, text_style):
    """(image, problem) for either kind of schedule page."""
    if page.kind == "tonight":
        return draw_tonight(page, panel_w, panel_h, number_style, text_style)
    return draw_schedule(page, panel_w, panel_h, number_style, text_style)


def draw_tonight(page: SchedulePage, panel_w, panel_h, number_style, text_style):
    """The "tonight" page: each line centered, the days above the times."""
    from .schedule import ScheduleLine
    stacked = []
    for ln in page.lines:
        stacked.append(ScheduleLine(ln.days, ""))
        if ln.times:
            stacked.append(ScheduleLine(ln.times, "", True))     # the times in the Number style
    return _draw_centered(SchedulePage("", tuple(stacked), "tonight"), panel_w, panel_h, number_style, text_style)


def _draw_centered(page: SchedulePage, panel_w, panel_h, number_style, text_style):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (panel_w, panel_h))
    for minimum in (READABLE, 4):
        for size in range(max(int(text_style.size), int(number_style.size)) + 6, minimum - 1, -1):
            fonts = [(number_style if ln.today else text_style) for ln in page.lines]
            widths = [st.font(size).getlength(ln.days) for ln, st in zip(page.lines, fonts)]
            asc = max(st.font(size).getmetrics()[0] for st in fonts)
            line_h = asc + max(st.font(size).getmetrics()[1] for st in fonts)
            block = len(page.lines) * line_h + LINE_GAP * (len(page.lines) - 1)
            if max(widths) <= panel_w and block <= panel_h:
                y = (panel_h - block) // 2
                draw = ImageDraw.Draw(img)
                for ln, st, w in zip(page.lines, fonts, widths):
                    draw.fontmode = "L" if st.antialias else "1"
                    draw.text(((panel_w - w) / 2, y + asc), ln.days, fill=st.color, font=st.font(size), anchor="ls")
                    y += line_h + LINE_GAP
                return img, "" if minimum == READABLE else "the text is too small to read"
    return img, "it doesn't fit the matrix"


# ── Custom message page ───────────────────────────────────────────────────────

def message_style(page, number_style, text_style):
    """The style a message (or the show name) is drawn in: the Text or Number style, or the
    Text style's font in the message's own colour."""
    from dataclasses import replace
    from .render import parse_color
    if page.color == "number":
        return number_style
    if page.color == "text":
        return text_style
    return replace(text_style, color=parse_color(page.color, text_style.color))


def custom_message_layout(page, width: int, height: int, style, min_size: int = READABLE,
                          start: Optional[int] = None):
    """(size, wrapped lines) for the text in width x height, or (None, []).

    The user's own line breaks are kept; a line too wide is wrapped at spaces.
    One size for every line: the style's size (or `start`), shrinking until it
    all fits.
    """
    for size in range(max(int(start or style.size), min_size), min_size - 1, -1):
        font = style.font(size)
        out: List[str] = []
        ok = True
        for line in page.lines:
            cur = ""
            for word in line.split():
                if font.getlength(word) > width:
                    ok = False
                    break
                trial = f"{cur} {word}".strip()
                if cur and font.getlength(trial) > width:
                    out.append(cur)
                    cur = word
                else:
                    cur = trial
            if not ok:
                break
            if cur:
                out.append(cur)
        if not ok or not out:
            continue
        asc, desc = font.getmetrics()
        if len(out) * (asc + desc) + LINE_GAP * (len(out) - 1) <= height:
            return size, out
    return None, []


def draw_message(page: MessagePage, panel_w: int, panel_h: int, number_style, text_style):
    """(image, problem): the picture on the left (if any), the text centered beside it."""
    from PIL import Image, ImageDraw
    from .symbols import draw_symbol
    img = Image.new("RGB", (panel_w, panel_h))
    style = message_style(page, number_style, text_style)
    problem = ""
    pic = 0
    if page.picture:
        pic = max(0, min(panel_h, int(panel_w * 0.34)))
        if pic < MIN_SYMBOL:
            pic = 0
    gap = max(2, panel_w // 32) if pic else 0
    x_text = pic + gap
    width = panel_w - x_text
    size, lines = custom_message_layout(page, width, panel_h, style)
    if size is None and pic:
        # Make room: a smaller picture, then none
        for share in (0.25, 0.0):
            pic = int(min(panel_h, panel_w * share)) if share else 0
            pic = pic if pic >= MIN_SYMBOL else 0
            gap = max(2, panel_w // 32) if pic else 0
            x_text, width = pic + gap, panel_w - (pic + gap)
            size, lines = custom_message_layout(page, width, panel_h, style)
            if size is not None:
                if not pic:
                    problem = "the picture is left off so the text fits"
                break
    if size is None:
        size, lines = custom_message_layout(page, width, panel_h, style, min_size=4)
        problem = "the text is too small to read: shorten it or use a smaller Text size"
    if size is None:
        return img, "the text doesn't fit the matrix: shorten it"
    if pic:
        mark = draw_symbol(page.picture, pic)
        img.paste(mark, (0, (panel_h - pic) // 2), mark)
    font = style.font(size)
    asc, desc = font.getmetrics()
    block = len(lines) * (asc + desc) + LINE_GAP * (len(lines) - 1)
    y = (panel_h - block) // 2
    draw = ImageDraw.Draw(img)
    draw.fontmode = "L" if style.antialias else "1"
    for line in lines:
        draw.text((x_text + (width - font.getlength(line)) / 2, y + asc), line, fill=style.color, font=font, anchor="ls")
        y += asc + desc + LINE_GAP
    return img, problem


# ── Show page ─────────────────────────────────────────────────────────────────

LOGO_ABOVE = 0.75     # a logo this much as wide (relative to the panel's shape) or wider goes above the name


def _fit(w: int, h: int, box_w: int, box_h: int) -> Tuple[int, int]:
    """w x h scaled to fit box_w x box_h, keeping its shape (it may grow)."""
    if w <= 0 or h <= 0 or box_w <= 0 or box_h <= 0:
        return 0, 0
    k = min(box_w / w, box_h / h)
    return max(1, int(w * k)), max(1, int(h * k))


def show_layout(page: ShowPage, logo_size: Optional[Tuple[int, int]], panel_w: int, panel_h: int, style):
    """Where things go: (logo_box, text_box, size, lines, problem).

    logo_box is (x, y, w, h) or None; text_box is (x, y, w, h) or None, with
    the text's size and wrapped lines. Beside: the logo on the left, the name
    to its right; above: a wide logo over the name. Each tries the logo at a
    few sizes, largest first, keeping the first that lets the name be read.
    The name is a headline: as large as fits (never smaller than its style's
    size allows), not capped at the style's size.
    """
    start = max(int(style.size), panel_h)
    if not logo_size or not logo_size[0]:
        size, lines = custom_message_layout(page, panel_w, panel_h, style, start=start)
        problem = ""
        if size is None:
            size, lines = custom_message_layout(page, panel_w, panel_h, style, min_size=4, start=start)
            problem = "the name is too small to read: shorten it or use a smaller size"
        if size is None:
            return None, None, None, [], "the name doesn't fit the matrix: shorten it"
        return None, (0, 0, panel_w, panel_h), size, lines, problem
    lw, lh = logo_size
    if not page.lines:
        fw, fh = _fit(lw, lh, panel_w, panel_h)
        return ((panel_w - fw) // 2, (panel_h - fh) // 2, fw, fh), None, None, [], ""
    gap = max(2, panel_w // 32)
    above = lw / lh >= LOGO_ABOVE * panel_w / panel_h
    shares = (0.6, 0.5, 0.4, 0.3) if above else (0.5, 0.4, 0.3, 0.25)

    def attempt(share, min_size):
        if above:
            fw, fh = _fit(lw, lh, panel_w, int(panel_h * share))
            tw, th = panel_w, panel_h - fh - gap
        else:
            fw, fh = _fit(lw, lh, int(panel_w * share), panel_h)
            tw, th = panel_w - fw - gap, panel_h
        if tw <= 0 or th <= 0:
            return None
        size, lines = custom_message_layout(page, tw, th, style, min_size=min_size, start=start)
        return None if size is None else (fw, fh, tw, th, size, lines)

    problem = ""
    got = next((a for a in (attempt(sh, READABLE) for sh in shares) if a), None)
    if got is None:
        got = attempt(shares[-1], 4)
        problem = "the name is too small to read beside the logo: shorten it, or turn off Show the name"
    if got is None:
        fw, fh = _fit(lw, lh, panel_w, panel_h)
        return ((panel_w - fw) // 2, (panel_h - fh) // 2, fw, fh), None, None, [], \
            "the name doesn't fit beside the logo, so only the logo shows: shorten it"
    fw, fh, tw, th, size, lines = got
    font = style.font(size)
    asc, desc = font.getmetrics()
    text_w = max(int(font.getlength(ln)) for ln in lines)
    text_h = len(lines) * (asc + desc) + LINE_GAP * (len(lines) - 1)
    # The logo and the name are centered together as one group
    if above:
        y0 = (panel_h - (fh + gap + text_h)) // 2
        return ((panel_w - fw) // 2, y0, fw, fh), (0, y0 + fh + gap, panel_w, text_h), size, lines, problem
    x0 = (panel_w - (fw + gap + text_w)) // 2
    return (x0, (panel_h - fh) // 2, fw, fh), (x0 + fw + gap, 0, text_w, panel_h), size, lines, problem


def draw_show_page(page: ShowPage, panel_w: int, panel_h: int, number_style, text_style):
    """(image, problem): the logo, the name, or the logo beside (or above) the name."""
    from PIL import Image, ImageDraw
    from .show import logo_image
    img = Image.new("RGB", (panel_w, panel_h))
    logo = logo_image(page.logo) if page.logo else None
    if logo is None and not page.lines:
        return img, "the logo is missing: upload it again"
    style = message_style(page, number_style, text_style)
    logo_box, text_box, size, lines, problem = show_layout(page, logo.size if logo is not None else None,
                                                           panel_w, panel_h, style)
    if logo_box is not None and logo is not None:
        x, y, w, h = logo_box
        tile = logo.resize((w, h), Image.LANCZOS)
        img.paste(tile, (x, y), tile)
    if text_box is not None:
        x, y, w, h = text_box
        font = style.font(size)
        asc, desc = font.getmetrics()
        block = len(lines) * (asc + desc) + LINE_GAP * (len(lines) - 1)
        ty = y + (h - block) // 2
        draw = ImageDraw.Draw(img)
        draw.fontmode = "L" if style.antialias else "1"
        for line in lines:
            draw.text((x + (w - font.getlength(line)) / 2, ty + asc), line, fill=style.color, font=font, anchor="ls")
            ty += asc + desc + LINE_GAP
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
    if isinstance(item, SchedulePage):
        return draw_schedule_page(item, panel_w, panel_h, number_style, text_style)[0]
    if isinstance(item, MessagePage):
        return draw_message(item, panel_w, panel_h, number_style, text_style)[0]
    if isinstance(item, ShowPage):
        return draw_show_page(item, panel_w, panel_h, number_style, text_style)[0]
    return draw_weather_page(item, panel_w, panel_h, number_style, text_style)
