"""Draw the countdown message and move it across the panel (Pillow).

  layout_strip()  the message drawn once into a "strip" image: the number piece
                  in the number style, the text piece in the text style, on one
                  baseline; or on two lines when a vertical/static message is
                  wider than the panel (each line shrunk further if needed).
  Mover           where the strip sits at a given time, for L2R, R2L, T2B, B2T
                  (enter fully from one edge, leave fully past the other, then
                  the repeat delay) or static (centered, no motion).
  Renderer        ties them together: caches the strip until the message
                  changes, returns one panel-sized RGB frame per call.

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
DIRECTIONS = ("L2R", "R2L", "T2B", "B2T", "static")

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
                 panel_w: int, direction: str) -> Optional[Image.Image]:
    """The whole message drawn once, or None for a blank message."""
    if message.blank:
        return None
    placed = [_Placed(t, number_style if role == NUMBER else text_style,
                      (number_style if role == NUMBER else text_style).size, role == NUMBER)
              for role, t in message.pieces]
    gap = text_style.font().getlength(" ")
    one_line_w = sum(p.width for p in placed) + gap * (len(placed) - 1)

    vertical = direction in ("T2B", "B2T", "static")
    if not vertical or one_line_w <= panel_w:
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


# ── Motion ────────────────────────────────────────────────────────────────────

class Mover:
    """Strip position over time. Positions are the strip's top-left on the panel.

    A pass runs from fully off one edge to fully off the other at pps; then the
    panel stays blank for repeat_delay seconds and the next pass starts. The
    strip may change size between frames (the number changes); each frame uses
    the current size, and a pass ends once the current strip is fully past.
    """

    def __init__(self, panel_w: int, panel_h: int, direction: str, pps: float, repeat_delay: float):
        self.w, self.h = panel_w, panel_h
        self.direction = direction if direction in DIRECTIONS else "R2L"
        self.pps = max(0.1, float(pps))
        self.delay = max(0.0, float(repeat_delay))
        self.passes = 0          # completed passes, so callers can switch messages between them
        self.reset()

    def reset(self, t: Optional[float] = None):
        self._pass_start = t
        self._done_at: Optional[float] = None

    def position(self, t: float, strip_w: int, strip_h: int) -> Optional[Tuple[int, int]]:
        """Top-left of the strip at time t, or None while blank (repeat delay)."""
        cx = (self.w - strip_w) // 2
        cy = (self.h - strip_h) // 2
        if self.direction == "static":
            return cx, cy
        if self._pass_start is None:
            self._pass_start = t
        if self._done_at is not None:
            if t - self._done_at < self.delay:
                return None
            self._pass_start, self._done_at = t, None

        travel = (t - self._pass_start) * self.pps
        horizontal = self.direction in ("L2R", "R2L")
        span = (self.w + strip_w) if horizontal else (self.h + strip_h)
        if travel >= span:
            self.passes += 1
            if self.delay > 0:
                self._done_at = t
                return None
            # Start the next pass now, carrying over the overshoot so speed stays even
            self._pass_start = t - (travel - span) / self.pps
            travel -= span
        step = int(travel)
        if self.direction == "R2L":
            return self.w - step, cy
        if self.direction == "L2R":
            return step - strip_w, cy
        if self.direction == "T2B":
            return cx, step - strip_h
        return cx, self.h - step          # B2T


# ── Renderer ──────────────────────────────────────────────────────────────────

class Renderer:
    """Panel-sized frames for the current message."""

    def __init__(self, panel_w: int, panel_h: int, countdown_cfg: dict, resolve: FontResolver):
        motion = countdown_cfg.get("motion") or {}
        self.w, self.h = panel_w, panel_h
        self.direction = motion.get("direction", "R2L")
        self.text_style = Style.from_cfg(countdown_cfg.get("text_style") or {}, resolve)
        self.number_style = Style.from_cfg(countdown_cfg.get("number_style") or {}, resolve)
        self.mover = Mover(panel_w, panel_h, self.direction,
                           motion.get("pixels_per_second", 15), motion.get("repeat_delay", 0))
        self._key: Optional[tuple] = None
        self._strip: Optional[Image.Image] = None

    def strip_for(self, message: Message) -> Optional[Image.Image]:
        key = (message.pieces, message.lines)
        if key != self._key:
            was_blank = self._key is None or not self._key[0]
            self._strip = layout_strip(message, self.text_style, self.number_style, self.w, self.direction)
            self._key = key
            if was_blank or self._strip is None:
                self.mover.reset()   # start a fresh pass when text (re)appears
        return self._strip

    def frame(self, message: Message, t: float) -> Image.Image:
        """The frame at monotonic time t (seconds)."""
        img = Image.new("RGB", (self.w, self.h))
        strip = self.strip_for(message)
        if strip is None:
            return img
        pos = self.mover.position(t, strip.width, strip.height)
        if pos is not None:
            img.paste(strip, pos)
        return img
