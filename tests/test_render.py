"""Renderer: layout, two-line fallback, fixed-width digits, the message centered.

Needs Pillow (present on FPP; locally: .venv/bin/python -m unittest discover -s tests).
Fonts are Pillow's built-in scalable font, so results match on any machine.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from PIL import Image  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

if HAVE_PIL:
    from countdown.message import NUMBER, TEXT, Message
    from countdown.render import Renderer, Style, layout_strip, parse_color

GREEN, RED = (0, 255, 0), (255, 0, 0)


def no_font(_name):
    return None   # -> Pillow's built-in font


def style(size=12, color=RED):
    return Style(None, size, color, False)


def msg(*pieces):
    return Message(tuple(pieces))


if HAVE_PIL:
    EIGHT = msg((NUMBER, "8 Days"), (TEXT, "to Christmas"))
    LAST = msg((TEXT, "Christmas in"), (NUMBER, "8 Days"))


def colors(img):
    return {c for _, c in img.getcolors(1 << 20)} - {(0, 0, 0)}


def bbox_of(img, color):
    """Bounding box of pixels of exactly this colour."""
    mask = Image.new("1", img.size)
    px, mp = img.load(), mask.load()
    for y in range(img.height):
        for x in range(img.width):
            if px[x, y] == color:
                mp[x, y] = 1
    return mask.getbbox()


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class Layout(unittest.TestCase):

    def test_two_colours_no_antialias_blending(self):
        strip = layout_strip(EIGHT, style(12, RED), style(12, GREEN), 192)
        self.assertEqual(colors(strip), {RED, GREEN})

    def test_number_first_then_text(self):
        strip = layout_strip(EIGHT, style(12, RED), style(12, GREEN), 192)
        self.assertLess(bbox_of(strip, GREEN)[2], bbox_of(strip, RED)[0])

    def test_number_last(self):
        strip = layout_strip(LAST, style(12, RED), style(12, GREEN), 192)
        self.assertLess(bbox_of(strip, RED)[2], bbox_of(strip, GREEN)[0])

    def test_mixed_sizes_share_a_baseline(self):
        strip = layout_strip(msg((NUMBER, "8"), (TEXT, "x")), style(10, RED), style(20, GREEN), 192)
        # "8" and "x" both sit on the baseline: their ink bottoms match
        self.assertAlmostEqual(bbox_of(strip, GREEN)[3], bbox_of(strip, RED)[3], delta=1)

    def test_hms_keeps_one_width_as_it_ticks(self):
        widths = {layout_strip(msg((NUMBER, t), (TEXT, "to Christmas")), style(), style(color=GREEN),
                               192).width
                  for t in ("08:14:32", "11:11:11", "00:00:00", "07:47:41")}
        self.assertEqual(len(widths), 1)

    def test_blank_message(self):
        self.assertIsNone(layout_strip(Message(()), style(), style(), 192))

    def test_antialias_adds_blended_pixels(self):
        aa = Style(None, 12, RED, True)
        strip = layout_strip(msg((TEXT, "Christmas")), aa, aa, 192)
        self.assertGreater(len(colors(strip)), 1)


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class TwoLines(unittest.TestCase):

    def test_wide_message_goes_to_two_lines(self):
        strip = layout_strip(EIGHT, style(12), style(12, GREEN), 64)
        self.assertLessEqual(strip.width, 64)
        g, r = bbox_of(strip, GREEN), bbox_of(strip, RED)
        self.assertLessEqual(g[3], r[1], "number line above text line")

    def test_number_last_puts_text_line_first(self):
        strip = layout_strip(LAST, style(12), style(12, GREEN), 64)
        self.assertLessEqual(bbox_of(strip, RED)[3], bbox_of(strip, GREEN)[1])

    def test_vertical_message_that_fits_stays_one_line(self):
        strip = layout_strip(EIGHT, style(12), style(12, GREEN), 192)
        g, r = bbox_of(strip, GREEN), bbox_of(strip, RED)
        self.assertLess(g[2], r[0])

    def test_line_still_too_wide_is_shrunk(self):
        strip = layout_strip(EIGHT, style(30), style(30, GREEN), 64)
        self.assertLessEqual(strip.width, 64)

    def test_lines_are_centered(self):
        strip = layout_strip(msg((NUMBER, "8 Days"), (TEXT, "to Christmas!!")), style(12), style(12, GREEN),
                             100)
        g = bbox_of(strip, GREEN)
        left, right = g[0], strip.width - g[2]
        self.assertAlmostEqual(left, right, delta=2)


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class RendererFrames(unittest.TestCase):

    CFG = {"text_style": {"font": "", "size": 12, "color": "#ff0000"},
           "number_style": {"font": "", "size": 12, "color": "#00ff00"}}

    def test_frame_size_and_whole_message(self):
        r = Renderer(192, 96, self.CFG, no_font)
        f = r.frame(EIGHT)
        self.assertEqual(f.size, (192, 96))
        self.assertEqual(colors(f), {GREEN, RED})

    def test_message_is_centered(self):
        f = Renderer(192, 96, self.CFG, no_font).frame(EIGHT)
        left, top, right, bottom = f.getbbox()
        self.assertAlmostEqual(left, 192 - right, delta=2)
        self.assertAlmostEqual(top, 96 - bottom, delta=3)

    def test_ticking_timer_stays_in_place(self):
        r = Renderer(192, 96, self.CFG, no_font)
        a = r.frame(msg((NUMBER, "08:14:32"), (TEXT, "to Christmas"))).getbbox()
        b = r.frame(msg((NUMBER, "08:14:31"), (TEXT, "to Christmas"))).getbbox()
        self.assertEqual((a[0], a[2]), (b[0], b[2]))

    def test_blank_message_gives_black_frame(self):
        r = Renderer(192, 96, self.CFG, no_font)
        self.assertEqual(colors(r.frame(Message(()))), set())

    def test_parse_color(self):
        self.assertEqual(parse_color("#00ff7F"), (0, 255, 127))
        self.assertEqual(parse_color("nope"), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
