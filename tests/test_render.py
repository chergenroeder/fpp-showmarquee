"""Renderer: layout, two-line fallback, fixed-width digits and motion.

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
    from countdown.render import Mover, Renderer, Style, layout_strip, parse_color

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
        strip = layout_strip(EIGHT, style(12, RED), style(12, GREEN), 192, "R2L")
        self.assertEqual(colors(strip), {RED, GREEN})

    def test_number_first_then_text(self):
        strip = layout_strip(EIGHT, style(12, RED), style(12, GREEN), 192, "R2L")
        self.assertLess(bbox_of(strip, GREEN)[2], bbox_of(strip, RED)[0])

    def test_number_last(self):
        strip = layout_strip(LAST, style(12, RED), style(12, GREEN), 192, "R2L")
        self.assertLess(bbox_of(strip, RED)[2], bbox_of(strip, GREEN)[0])

    def test_mixed_sizes_share_a_baseline(self):
        strip = layout_strip(msg((NUMBER, "8"), (TEXT, "x")), style(10, RED), style(20, GREEN), 192, "R2L")
        # "8" and "x" both sit on the baseline: their ink bottoms match
        self.assertAlmostEqual(bbox_of(strip, GREEN)[3], bbox_of(strip, RED)[3], delta=1)

    def test_hms_keeps_one_width_as_it_ticks(self):
        widths = {layout_strip(msg((NUMBER, t), (TEXT, "to Christmas")), style(), style(color=GREEN),
                               192, "static").width
                  for t in ("08:14:32", "11:11:11", "00:00:00", "07:47:41")}
        self.assertEqual(len(widths), 1)

    def test_blank_message(self):
        self.assertIsNone(layout_strip(Message(()), style(), style(), 192, "R2L"))

    def test_antialias_adds_blended_pixels(self):
        aa = Style(None, 12, RED, True)
        strip = layout_strip(msg((TEXT, "Christmas")), aa, aa, 192, "R2L")
        self.assertGreater(len(colors(strip)), 1)


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class TwoLines(unittest.TestCase):

    def test_horizontal_scroll_stays_one_line_even_when_wide(self):
        strip = layout_strip(EIGHT, style(20), style(20, GREEN), 64, "R2L")
        self.assertGreater(strip.width, 64)
        self.assertLess(strip.height, 30)

    def test_vertical_wide_message_goes_to_two_lines(self):
        for direction in ("T2B", "B2T", "static"):
            strip = layout_strip(EIGHT, style(12), style(12, GREEN), 64, direction)
            self.assertLessEqual(strip.width, 64, direction)
            g, r = bbox_of(strip, GREEN), bbox_of(strip, RED)
            self.assertLessEqual(g[3], r[1], f"{direction}: number line above text line")

    def test_number_last_puts_text_line_first(self):
        strip = layout_strip(LAST, style(12), style(12, GREEN), 64, "B2T")
        self.assertLessEqual(bbox_of(strip, RED)[3], bbox_of(strip, GREEN)[1])

    def test_vertical_message_that_fits_stays_one_line(self):
        strip = layout_strip(EIGHT, style(12), style(12, GREEN), 192, "T2B")
        g, r = bbox_of(strip, GREEN), bbox_of(strip, RED)
        self.assertLess(g[2], r[0])

    def test_line_still_too_wide_is_shrunk(self):
        strip = layout_strip(EIGHT, style(30), style(30, GREEN), 64, "static")
        self.assertLessEqual(strip.width, 64)

    def test_lines_are_centered(self):
        strip = layout_strip(msg((NUMBER, "8 Days"), (TEXT, "to Christmas!!")), style(12), style(12, GREEN),
                             100, "static")
        g = bbox_of(strip, GREEN)
        left, right = g[0], strip.width - g[2]
        self.assertAlmostEqual(left, right, delta=2)


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class Motion(unittest.TestCase):
    W, H, SW, SH = 192, 96, 100, 14

    def test_r2l_enters_right_leaves_left(self):
        m = Mover(self.W, self.H, "R2L", 10, 0)
        self.assertEqual(m.position(0, self.SW, self.SH), (192, 41))
        self.assertEqual(m.position(10, self.SW, self.SH), (92, 41))
        self.assertEqual(m.position(29.19, self.SW, self.SH)[0], 192 - 291)   # fully off left (-99)

    def test_l2r(self):
        m = Mover(self.W, self.H, "L2R", 10, 0)
        self.assertEqual(m.position(0, self.SW, self.SH), (-100, 41))
        self.assertEqual(m.position(10, self.SW, self.SH), (0, 41))

    def test_t2b(self):
        m = Mover(self.W, self.H, "T2B", 10, 0)
        self.assertEqual(m.position(0, self.SW, self.SH), (46, -14))
        self.assertEqual(m.position(5, self.SW, self.SH), (46, 36))

    def test_b2t(self):
        m = Mover(self.W, self.H, "B2T", 10, 0)
        self.assertEqual(m.position(0, self.SW, self.SH), (46, 96))
        self.assertEqual(m.position(5, self.SW, self.SH), (46, 46))

    def test_static_is_centered_and_still(self):
        m = Mover(self.W, self.H, "static", 10, 3)
        for t in (0, 5, 100):
            self.assertEqual(m.position(t, self.SW, self.SH), (46, 41))

    def test_pass_repeats_without_delay(self):
        m = Mover(self.W, self.H, "R2L", 10, 0)
        m.position(0, self.SW, self.SH)
        # span = 292 px = 29.2 s; at 30.2 s the next pass is 1 s (10 px) in
        self.assertEqual(m.position(29.0, self.SW, self.SH)[0], 192 - 290)
        self.assertEqual(m.position(30.2, self.SW, self.SH)[0], 192 - 10)

    def test_repeat_delay_blanks_between_passes(self):
        m = Mover(self.W, self.H, "R2L", 10, 2)
        m.position(0, self.SW, self.SH)
        self.assertIsNotNone(m.position(29.0, self.SW, self.SH))
        self.assertIsNone(m.position(29.3, self.SW, self.SH))     # pass done
        self.assertIsNone(m.position(31.0, self.SW, self.SH))     # still in the 2 s delay
        self.assertEqual(m.position(31.4, self.SW, self.SH), (192, 41))   # next pass starts


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class RendererFrames(unittest.TestCase):

    def cfg(self, direction="R2L", pps=20):
        return {"motion": {"direction": direction, "pixels_per_second": pps, "repeat_delay": 0},
                "text_style": {"font": "", "size": 12, "color": "#ff0000"},
                "number_style": {"font": "", "size": 12, "color": "#00ff00"}}

    def test_frame_size_and_scrolls_in(self):
        r = Renderer(192, 96, self.cfg(), no_font)
        self.assertEqual(r.frame(EIGHT, 0).size, (192, 96))
        self.assertEqual(colors(r.frame(EIGHT, 0)), set())        # just off the right edge
        self.assertEqual(colors(r.frame(EIGHT, 1)), {GREEN})      # 20 px of "8 Days" in
        self.assertEqual(colors(r.frame(EIGHT, 5)), {GREEN, RED})  # text following

    def test_blank_message_gives_black_frame(self):
        r = Renderer(192, 96, self.cfg("static"), no_font)
        self.assertEqual(colors(r.frame(Message(()), 0)), set())

    def test_static_shows_whole_message(self):
        r = Renderer(192, 96, self.cfg("static"), no_font)
        self.assertEqual(colors(r.frame(EIGHT, 0)), {GREEN, RED})

    def test_text_change_keeps_the_pass_going(self):
        r = Renderer(192, 96, self.cfg(), no_font)
        r.frame(msg((NUMBER, "08:14:32"), (TEXT, "to Christmas")), 0)
        a = r.mover.position(4, 100, 14)
        r.frame(msg((NUMBER, "08:14:31"), (TEXT, "to Christmas")), 4)
        self.assertEqual(r.mover.position(4, 100, 14), a)

    def test_parse_color(self):
        self.assertEqual(parse_color("#00ff7F"), (0, 255, 127))
        self.assertEqual(parse_color("nope"), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
