"""The Show page: the show's name, its uploaded logo, or both.

Run: .venv/bin/python -m unittest discover -s tests  (drawing and logo tests need Pillow)
"""

import base64
import io
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

from countdown.show import (LogoError, LogoStore, ShowPage, logo_image, name_lines,  # noqa: E402
                            settings_problems, show_page, show_status)

try:
    from PIL import Image, ImageDraw
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


def png_b64(w, h, margin=0, color=(220, 30, 40, 255), mode="RGBA", fmt="PNG"):
    """A w x h coloured block inside a transparent (or black) margin."""
    img = Image.new(mode, (w + 2 * margin, h + 2 * margin), (0, 0, 0, 0) if mode == "RGBA" else (0, 0, 0))
    ImageDraw.Draw(img).rectangle([margin, margin, margin + w - 1, margin + h - 1],
                                  fill=color if mode == "RGBA" else color[:3])
    buf = io.BytesIO()
    img.save(buf, fmt)
    return base64.b64encode(buf.getvalue()).decode()


class Page(unittest.TestCase):

    def test_off_or_nothing_to_show(self):
        self.assertIsNone(show_page({"enabled": False, "name": "Smith Lights"}))
        self.assertIsNone(show_page({"enabled": True, "name": "   "}))
        self.assertIsNotNone(show_page({"enabled": False, "name": "Smith Lights"}, force=True))

    def test_name_lines(self):
        self.assertEqual(name_lines({"name": "  Smith   Family\r\n\nLights "}), ("Smith Family", "Lights"))
        p = show_page({"enabled": True, "name": "Smith Family\nLights"})
        self.assertEqual((p.lines, p.logo, p.slot, p.plain), (("Smith Family", "Lights"), "", "show", "Smith Family / Lights"))

    def test_logo_and_the_name_switch(self):
        both = show_page({"enabled": True, "name": "Smith Lights"}, "abc")
        self.assertEqual((both.lines, both.logo, both.plain), (("Smith Lights",), "abc", "[Logo] Smith Lights"))
        alone = show_page({"enabled": True, "name": "Smith Lights", "show_name": False}, "abc")
        self.assertEqual((alone.lines, alone.plain), ((), "[Logo]"))
        # Without a logo the switch doesn't hide the name: something has to show
        self.assertEqual(show_page({"enabled": True, "name": "Smith Lights", "show_name": False}).lines, ("Smith Lights",))
        self.assertEqual(show_page({"enabled": True, "name": ""}, "abc").plain, "[Logo]")

    def test_colour(self):
        self.assertEqual(show_page({"enabled": True, "name": "x", "color": "number"}).color, "number")
        self.assertEqual(show_page({"enabled": True, "name": "x", "color": "#12ab34"}).color, "#12ab34")
        self.assertEqual(show_page({"enabled": True, "name": "x", "color": "red"}).color, "text")

    def test_status(self):
        st = show_status({"enabled": True, "name": ""}, None)
        self.assertEqual((st["showing"], st["problem"]), (False, "type the show's name or upload a logo"))
        st = show_status({"enabled": True, "name": ""}, {"id": "abc", "width": 10, "height": 10})
        self.assertEqual((st["showing"], st["plain"], st["problem"]), (True, "[Logo]", ""))
        self.assertEqual(show_status({"enabled": False}, None)["problem"], "")

    def test_settings_problems(self):
        self.assertEqual(settings_problems({"enabled": True, "name": "x", "color": "text", "show_name": True}), [])
        self.assertEqual(len(settings_problems({"enabled": "yes", "show_name": 1, "name": "x" * 81, "color": "blue"})), 4)


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class Logo(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.store = LogoStore(os.path.join(self.dir, "data", "logo.png"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_save_trims_and_keeps_it(self):
        self.assertIsNone(self.store.info())
        info = self.store.save_base64("data:image/png;base64," + png_b64(100, 40, margin=30))
        self.assertEqual((info["width"], info["height"]), (100, 40))        # the transparent margin is trimmed
        self.assertEqual(logo_image(info["id"]).size, (100, 40))
        again = LogoStore(self.store.path)                                    # after a restart
        self.assertEqual(again.info(), info)

    def test_black_edges_are_trimmed_and_big_images_shrink(self):
        info = self.store.save_base64(png_b64(1000, 500, margin=50, mode="RGB"))
        self.assertEqual((info["width"], info["height"]), (512, 256))

    def test_bad_uploads(self):
        for b64, why in (("not base64!", "base64"), ("", "empty"),
                         (base64.b64encode(b"hello").decode(), "isn't an image"),
                         (png_b64(10, 10, color=(0, 0, 0, 255)), "all black")):
            with self.assertRaises(LogoError) as e:
                self.store.save_base64(b64)
            self.assertIn(why, str(e.exception))
        self.assertIsNone(self.store.info())

    def test_too_many_pixels_is_refused_before_decoding(self):
        with self.assertRaises(LogoError) as e:
            self.store.save_base64(png_b64(4100, 4100, mode="RGB"))
        self.assertIn("too large", str(e.exception))

    def test_remove(self):
        info = self.store.save_base64(png_b64(20, 20))
        self.store.remove()
        self.assertIsNone(self.store.info())
        self.assertIsNone(logo_image(info["id"]))
        self.assertFalse(os.path.exists(self.store.path))
        self.store.remove()                                                   # twice is fine


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class Drawing(unittest.TestCase):
    def setUp(self):
        from countdown.render import Style
        self.dir = tempfile.mkdtemp()
        self.store = LogoStore(os.path.join(self.dir, "logo.png"))
        self.num = Style(None, 10, (0, 255, 0), False)
        self.txt = Style(None, 10, (255, 0, 0), False)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def draw(self, page, w=192, h=96):
        from countdown.still import draw_show_page
        return draw_show_page(page, w, h, self.num, self.txt)

    @staticmethod
    def cols(img, test):
        px = img.load()
        return [x for x in range(img.width) for y in range(img.height) if test(px[x, y])]

    def test_name_alone_fills_the_matrix(self):
        img, problem = self.draw(ShowPage(("Smith Lights",), "text", ""))
        self.assertEqual(problem, "")
        px = img.load()
        rows = [y for y in range(96) for x in range(192) if px[x, y][0] > 200 and px[x, y][1] < 50]
        self.assertGreater(max(rows) - min(rows), 50)         # far taller than the style's size 10

    def test_logo_alone_is_centered_and_as_large_as_fits(self):
        info = self.store.save_base64(png_b64(50, 50, color=(0, 0, 255, 255)))
        img, problem = self.draw(ShowPage((), "text", info["id"]))
        blue = self.cols(img, lambda p: p[2] > 200)
        self.assertEqual((min(blue), max(blue)), (48, 143))   # 96 x 96, centered on 192

    def test_square_logo_beside_the_name(self):
        info = self.store.save_base64(png_b64(50, 50, color=(0, 0, 255, 255)))
        img, problem = self.draw(ShowPage(("Smith Lights",), "text", info["id"]))
        blue = self.cols(img, lambda p: p[2] > 200)
        red = self.cols(img, lambda p: p[0] > 200 and p[2] < 50)
        self.assertEqual(problem, "")
        self.assertLess(max(blue), min(red))                  # logo left of the name

    def test_wide_logo_above_the_name(self):
        info = self.store.save_base64(png_b64(300, 60, color=(0, 0, 255, 255)))
        img, _ = self.draw(ShowPage(("Smith Lights",), "text", info["id"]))
        px = img.load()
        rows = lambda test: [y for y in range(96) for x in range(192) if test(px[x, y])]  # noqa: E731
        self.assertLess(max(rows(lambda p: p[2] > 200)), min(rows(lambda p: p[0] > 200 and p[2] < 50)))

    def test_a_long_name_on_a_small_matrix(self):
        info = self.store.save_base64(png_b64(50, 50, color=(0, 0, 255, 255)))
        img, problem = self.draw(ShowPage(("The Extremely Long Family Name Holiday Light Show Spectacular",),
                                          "text", info["id"]), 32, 16)
        self.assertIn("only the logo shows", problem)
        self.assertTrue(self.cols(img, lambda p: p[2] > 200))

    def test_missing_logo(self):
        img, problem = self.draw(ShowPage((), "text", "gone"))
        self.assertIn("missing", problem)


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class Daemon(unittest.TestCase):
    def setUp(self):
        from daemon_env import clear_config, daemon_module
        self.mc = daemon_module()
        clear_config()
        self.d = self.mc.CountdownDaemon()
        self.d.logos.remove()

    def tearDown(self):
        self.d.logos.remove()

    def test_defaults_and_validation(self):
        self.assertEqual(self.mc.load_config()["show"], {"enabled": False, "name": "", "color": "text", "show_name": True})
        self.assertEqual(self.mc.load_config()["global"]["page_order"][0], "show")
        self.assertTrue(self.d.update_config({"show": {"color": "nope"}}))

    def test_preview_and_status(self):
        r = self.d.preview({"config": {}, "width": 192, "height": 96, "as": "show"})
        self.assertEqual(r["strips"][0]["message"], "Your Show Name")
        self.assertIn("sample name", r["note"])
        self.d.logos.save_base64(png_b64(40, 40))
        self.assertEqual(self.d.update_config({"show": {"enabled": True, "name": "Smith Lights"}}), [])
        r = self.d.preview({"config": self.d.get_config(), "width": 192, "height": 96})
        self.assertEqual([x["slot"] for x in r["strips"]][:2], ["show", "countdown"])   # first, by default
        self.assertEqual(r["strips"][0]["message"], "[Logo] Smith Lights")
        st = self.d.get_status()["show"]
        self.assertEqual((st["showing"], st["logo"]["width"]), (True, 40))
        self.assertTrue(os.path.exists(self.mc.LOGO_PATH))
        self.assertTrue(self.mc.LOGO_PATH.startswith(self.mc.DATA_DIR))      # plugindata, not config/


if __name__ == "__main__":
    unittest.main()
