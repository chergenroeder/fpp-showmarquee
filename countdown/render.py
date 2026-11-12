"""Draw the countdown message, held still in the center of the panel (Pillow).

  layout_strip()  the message drawn once into a "strip" image: the number piece
                  in the number style, the text piece in the text style, on one
                  baseline; or on two lines when it is wider than the panel
                  (each line shrunk further if needed).
  Renderer        caches the strip until the message changes and returns one
                  panel-sized RGB frame with it centered. Nothing scrolls: the
                  countdown, the weather page and the social screens each show
                  on their own for the global seconds per page.

Digits in the number piece sit in fixed-width boxes (the widest digit of the
font), so "08:14:32" keeps one width as it ticks and nothing beside it jitters.
"""

import threading
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from .message import NUMBER, Message

MIN_FONT_SIZE = 4
LINE_GAP = 1          # pixels between the two lines in two-line layout

FontResolver = Callable[[str], Optional[str]]   # font name -> file path (None if unknown)


# ── Fonts and colours ─────────────────────────────────────────────────────────

_font_cache: Dict[Tuple[Optional[str], int], ImageFont.FreeTypeFont] = {}
_font_lock = threading.Lock()


def load_font(path: Optional[str], size: int) -> ImageFont.FreeTypeFont:
    """TrueType/OpenType/Type1 font at size; Pillow's built-in font if path fails."""
    size = max(MIN_FONT_SIZE, int(size))
    key = (path, size)
    with _font_lock:
        font = _font_cache.get(key)
        if font is None:
            font = None
            if path:
                try:
                    font = ImageFont.truetype(path, size)
                except OSError:
                    font = None
            if font is None:
                font = ImageFont.load_default(size)
            _font_cache[key] = font
        return font


def parse_color(value: str, fallback=(255, 255, 255)) -> Tuple[int, int, int]:
    s = str(value or "").strip().lstrip("#")
    if len(s) == 6:
        try:
            return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        except ValueError:
            pass
    return fallback


@dataclass(frozen=True)
class Style:
    font_path: Optional[str]
    size: int
    color: Tuple[int, int, int]
    antialias: bool

    @staticmethod
    def from_cfg(cfg: dict, resolve: FontResolver) -> "Style":
        return Style(resolve(str(cfg.get("font") or "")), int(cfg.get("size") or 10),
                     parse_color(cfg.get("color")), bool(cfg.get("antialias", False)))

    def font(self, size: Optional[int] = None) -> ImageFont.FreeTypeFont:
        return load_font(self.font_path, size or self.size)


# ── Measuring and drawing one piece ───────────────────────────────────────────

def _runs(text: str, fixed_digits: bool) -> List[Tuple[str, bool]]:
    """Split into (run, is_digit_run) so digit runs can use fixed-width boxes."""
    if not fixed_digits:
        return [(text, False)]
    runs: List[Tuple[str, bool]] = []
    for ch in text:
        d = ch.isdigit()
        if runs and runs[-1][1] == d:
            runs[-1] = (runs[-1][0] + ch, d)
        else:
            runs.append((ch, d))
    return runs


def _digit_width(font) -> float:
    return max(font.getlength(d) for d in "0123456789")


def piece_width(text: str, font, fixed_digits: bool) -> float:
    dw = _digit_width(font) if fixed_digits else 0
    return sum(len(run) * dw if is_d else font.getlength(run)
               for run, is_d in _runs(text, fixed_digits))


def draw_piece(draw: ImageDraw.ImageDraw, x: float, baseline: float, text: str,
               font, color, fixed_digits: bool) -> float:
    """Draw text with its left edge at x on baseline; returns the x after it."""
    dw = _digit_width(font) if fixed_digits else 0
    for run, is_d in _runs(text, fixed_digits):
        if is_d:
            for ch in run:
                draw.text((x + (dw - font.getlength(ch)) / 2, baseline), ch,
                          fill=color, font=font, anchor="ls")
                x += dw
        else:
            draw.text((x, baseline), run, fill=color, font=font, anchor="ls")
            x += font.getlength(run)
    return x


# ── Laying out the strip ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class _Placed:
    text: str
    style: Style
    size: int
    fixed: bool

    @property
    def font(self):
        return self.style.font(self.size)

    @property
    def width(self) -> float:
        return piece_width(self.text, self.font, self.fixed)

    @property
    def metrics(self) -> Tuple[int, int]:
        return self.font.getmetrics()   # (ascent, descent)


def layout_strip(message: Message, text_style: Style, number_style: Style,
                 panel_w: int) -> Optional[Image.Image]:
    """The whole message drawn once, or None for a blank message."""
    if message.blank:
        return None
    placed = [_Placed(t, number_style if role == NUMBER else text_style,
                      (number_style if role == NUMBER else text_style).size, role == NUMBER)
              for role, t in message.pieces]
    gap = text_style.font().getlength(" ")
    one_line_w = sum(p.width for p in placed) + gap * (len(placed) - 1)

    if one_line_w <= panel_w:
        return _draw_one_line(placed, gap)
    groups = message.lines or tuple((i,) for i in range(len(placed)))
    lines = [_fit_line([placed[i] for i in g], gap, panel_w) for g in groups if g]
    if len(lines) == 1:
        return _draw_one_line(lines[0], gap)
    return _draw_lines(lines, gap)


def _line_width(pieces: List["_Placed"], gap: float) -> float:
    return sum(p.width for p in pieces) + gap * (len(pieces) - 1)


def _fit_line(pieces: List["_Placed"], gap: float, max_w: int) -> List["_Placed"]:
    """Shrink every piece on a line one size at a time until the line fits."""
    while _line_width(pieces, gap) > max_w and any(p.size > MIN_FONT_SIZE for p in pieces):
        pieces = [_Placed(p.text, p.style, max(MIN_FONT_SIZE, p.size - 1), p.fixed) for p in pieces]
    return pieces


def _new_image(w: float, h: float) -> Tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (max(1, int(round(w))), max(1, int(h))))
    return img, ImageDraw.Draw(img)


def _set_aa(draw: ImageDraw.ImageDraw, p: _Placed):
    draw.fontmode = "L" if p.style.antialias else "1"


def _draw_one_line(placed: List[_Placed], gap: float) -> Image.Image:
    ascent = max(p.metrics[0] for p in placed)
    descent = max(p.metrics[1] for p in placed)
    width = sum(p.width for p in placed) + gap * (len(placed) - 1)
    img, draw = _new_image(width, ascent + descent)
    x = 0.0
    for i, p in enumerate(placed):
        _set_aa(draw, p)
        x = draw_piece(draw, x, ascent, p.text, p.font, p.style.color, p.fixed)
        if i < len(placed) - 1:
            x += gap
    return img


def _draw_lines(lines: List[List[_Placed]], gap: float) -> Image.Image:
    """Each line centered, its pieces on one baseline."""
    width = max(_line_width(line, gap) for line in lines)
    metrics = [(max(p.metrics[0] for p in line), max(p.metrics[1] for p in line)) for line in lines]
    img, draw = _new_image(width, sum(a + d for a, d in metrics) + LINE_GAP * (len(lines) - 1))
    y = 0
    for line, (ascent, descent) in zip(lines, metrics):
        x = (width - _line_width(line, gap)) / 2
        for i, p in enumerate(line):
            _set_aa(draw, p)
            x = draw_piece(draw, x, y + ascent, p.text, p.font, p.style.color, p.fixed)
            if i < len(line) - 1:
                x += gap
        y += ascent + descent + LINE_GAP
    return img


# ── Renderer ──────────────────────────────────────────────────────────────────

class Renderer:
    """Panel-sized frames with the message centered."""

    def __init__(self, panel_w: int, panel_h: int, countdown_cfg: dict, resolve: FontResolver):
        self.w, self.h = panel_w, panel_h
        self.text_style = Style.from_cfg(countdown_cfg.get("text_style") or {}, resolve)
        self.number_style = Style.from_cfg(countdown_cfg.get("number_style") or {}, resolve)
        self._key: Optional[tuple] = None
        self._strip: Optional[Image.Image] = None

    def strip_for(self, message: Message) -> Optional[Image.Image]:
        key = (message.pieces, message.lines)
        if key != self._key:
            self._strip = layout_strip(message, self.text_style, self.number_style, self.w)
            self._key = key
        return self._strip

    def frame(self, message: Message) -> Image.Image:
        img = Image.new("RGB", (self.w, self.h))
        strip = self.strip_for(message)
        if strip is not None:
            img.paste(strip, ((self.w - strip.width) // 2, (self.h - strip.height) // 2))
        return img
