"""Show prep page: settings, links, the QR code, drawing, preview and taking turns.

Run: .venv/bin/python -m unittest discover -s tests  (drawing/QR tests need Pillow and qrcode)
"""

import os
import sys
import threading
import time
import unittest
from datetime import datetime, timedelta
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

from countdown.showprep import (APPS, DEFAULT_MESSAGE, ShowPrepPage, have_qrcode, link_problem,  # noqa: E402
                                page_link, show_prep_page, show_prep_status)

try:
    import PIL  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False
HAVE_QR = have_qrcode()


def prep(enabled=True, app="pulsemesh", message=DEFAULT_MESSAGE, link=""):
    return {"enabled": enabled, "app": app, "message": message, "link": link}


class Settings(unittest.TestCase):
    def test_default_links(self):
        self.assertEqual(page_link(prep(app="pulsemesh")), "https://pulsemesh.io/download")
        self.assertEqual(page_link(prep(app="tune2")), "https://www.tune2.app/downloads")
        self.assertEqual(page_link(prep(app="")), "")

    def test_own_link_wins(self):
        self.assertEqual(page_link(prep(link="  https://smithlights.com/listen ")), "https://smithlights.com/listen")

    def test_link_rules(self):
        self.assertEqual(link_problem(""), "")
        self.assertEqual(link_problem("https://a.io/x?y=1"), "")
        self.assertEqual(link_problem("http://a.io"), "")
        self.assertIn("https://", link_problem("pulsemesh.io/download"))
        self.assertIn("https://", link_problem("javascript:alert(1)"))
        self.assertIn("https://", link_problem("https://a b.io"))
        self.assertIn("200", link_problem("https://a.io/" + "x" * 200))

    def test_page(self):
        page = show_prep_page(prep(app="tune2"))
        self.assertEqual(page, ShowPrepPage("tune2", "Scan to get the Tune2 app before the show",
                                            "https://www.tune2.app/downloads"))
        self.assertEqual((page.app_name, page.slot), ("Tune2", "showprep"))
        self.assertEqual(show_prep_page(prep(message="  Get   {app}  now ")).message, "Get PulseMesh now")

    def test_no_page_when_off_no_app_or_bad_link(self):
        self.assertIsNone(show_prep_page(prep(enabled=False)))
        self.assertIsNotNone(show_prep_page(prep(enabled=False), force=True))
        self.assertIsNone(show_prep_page(prep(app="")))
        self.assertIsNone(show_prep_page(prep(app="other")))
        self.assertIsNone(show_prep_page(prep(link="not a link")))

    def test_status(self):
        self.assertEqual(show_prep_status(prep(app=""))["problem"], "choose the app (PulseMesh or Tune2)")
        st = show_prep_status(prep(app="tune2"))
        self.assertEqual((st["app_name"], st["link"], st["own_link"]), ("Tune2", APPS["tune2"]["link"], False))
        self.assertIn("link", show_prep_status(prep(link="nope"))["problem"])


@unittest.skipUnless(HAVE_QR, "qrcode not installed")
class QR(unittest.TestCase):
    def test_matrix_is_square_with_finder_patterns(self):
        from countdown.showprep import qr_matrix
        m = qr_matrix("https://pulsemesh.io/download", "M")
        n = len(m)
        self.assertTrue(all(len(row) == n for row in m))
        self.assertEqual((n - 17) % 4, 0)                       # 21, 25, 29, ...
        for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):          # the three corner squares
            self.assertTrue(all(m[r0][c0 + i] and m[r0 + 6][c0 + i] for i in range(7)))
            self.assertFalse(m[r0 + 1][c0 + 1])
            self.assertTrue(m[r0 + 3][c0 + 3])

    def test_biggest_code_that_fits(self):
        from countdown.showprep import QUIET, best_qr
        m, scale = best_qr("https://pulsemesh.io/download", 96)
        self.assertEqual((len(m), scale), (25, 3))               # smallest code, 3 LEDs a square on a 96-tall panel
        self.assertLessEqual((len(m) + 2 * QUIET) * scale, 96)
        m, scale = best_qr("https://pulsemesh.io/download", 32)
        self.assertEqual((len(m), scale), (25, 1))
        self.assertEqual(best_qr("https://pulsemesh.io/download", 20), (None, 0))

    def test_higher_error_correction_on_a_tie(self):
        from countdown.showprep import QUIET, best_qr, qr_matrix
        # Big enough for the H code at 3 LEDs a square: H wins over L at the same scale
        m, scale = best_qr("https://pulsemesh.io/download", (33 + 2 * QUIET) * 3)
        self.assertEqual((m, scale), (qr_matrix("https://pulsemesh.io/download", "H"), 3))


@unittest.skipUnless(HAVE_PIL and HAVE_QR, "Pillow or qrcode not installed")
class Drawing(unittest.TestCase):
    def setUp(self):
        from countdown.render import Style
        self.num = Style(None, 14, (0, 255, 0), False)
        self.txt = Style(None, 14, (255, 0, 0), False)

    def read_back(self, img, n, scale, x0, y0):
        """The modules as drawn: the centre LED of each square, dark or not."""
        from countdown.showprep import QUIET
        px = img.load()
        return [[px[x0 + (QUIET + c) * scale + scale // 2, y0 + (QUIET + r) * scale + scale // 2] == (0, 0, 0)
                 for c in range(n)] for r in range(n)]

    def test_drawn_code_matches_the_qr_library_exactly(self):
        from countdown.showprep import QUIET, best_qr
        from countdown.still import draw_show_prep
        for app, (w, h) in (("pulsemesh", (192, 96)), ("tune2", (192, 96)), ("pulsemesh", (64, 32))):
            page = show_prep_page(prep(app=app))
            img, problem = draw_show_prep(page, w, h, self.num, self.txt)
            m, scale = best_qr(page.link, min(h, w // 2))
            size = (len(m) + 2 * QUIET) * scale
            self.assertEqual(self.read_back(img, len(m), scale, 0, (h - size) // 2), m, (app, w, h))
            # a lit border all round the code
            px = img.load()
            self.assertNotEqual(px[0, (h - size) // 2], (0, 0, 0))
            self.assertNotEqual(px[size - 1, (h - size) // 2 + size - 1], (0, 0, 0))

    def test_message_beside_the_code_with_the_app_name_in_the_number_style(self):
        from countdown.still import draw_show_prep
        img, problem = draw_show_prep(show_prep_page(prep()), 192, 96, self.num, self.txt)
        self.assertEqual(problem, "")
        px = img.load()
        red = [x for x in range(192) for y in range(96) if px[x, y] == (255, 0, 0)]
        green = [x for x in range(192) for y in range(96) if px[x, y] == (0, 255, 0)]
        self.assertTrue(red and green)
        self.assertGreater(min(red + green), 87)                # all to the right of the 87-wide code

    def test_small_panel_warns_the_text_is_unreadable(self):
        from countdown.still import draw_show_prep
        _img, problem = draw_show_prep(show_prep_page(prep()), 64, 32, self.num, self.txt)
        self.assertIn("too small to read", problem)

    def test_no_qr_library_still_shows_the_message(self):
        from countdown.still import draw_show_prep
        with mock.patch("countdown.showprep.qr_matrix", side_effect=ImportError):
            img, problem = draw_show_prep(show_prep_page(prep(link="https://x.io/a")), 192, 96, self.num, self.txt)
        self.assertIn("python3-qrcode", problem)
        self.assertIsNotNone(img.getbbox())

    def test_code_too_big_for_the_panel(self):
        from countdown.still import draw_show_prep
        _img, problem = draw_show_prep(show_prep_page(prep()), 192, 16, self.num, self.txt)
        self.assertIn("doesn't fit", problem)


@unittest.skipUnless(HAVE_PIL and HAVE_QR, "Pillow or qrcode not installed")
class Preview(unittest.TestCase):
    def setUp(self):
        from daemon_env import clear_config, daemon_module
        self.mc = daemon_module()
        clear_config()
        self.d = self.mc.CountdownDaemon()

    def run_preview(self, cfg, **body):
        r = self.d.preview({"config": cfg, "width": 192, "height": 96, **body})
        self.assertNotIn("error", r)
        return r

    def test_now_adds_the_page_last(self):
        r = self.run_preview({"showprep": prep(app="tune2")})
        self.assertEqual([x["slot"] for x in r["strips"]], ["countdown", "showprep"])
        self.assertIn("www.tune2.app/downloads", r["strips"][1]["message"])

    def test_showprep_mode_even_when_off_and_sample_without_an_app(self):
        r = self.run_preview({"showprep": prep(enabled=False, app="tune2")}, **{"as": "showprep"})
        self.assertEqual([x["slot"] for x in r["strips"]], ["showprep"])
        self.assertNotIn("note", r)
        r = self.run_preview({}, **{"as": "showprep"})
        self.assertIn("PulseMesh", r["strips"][0]["message"])
        self.assertIn("choose the app", r["note"])

    def test_validation(self):
        self.assertTrue(self.d.update_config({"showprep": {"app": "spotify"}}))
        self.assertTrue(self.d.update_config({"showprep": {"link": "pulsemesh.io"}}))
        self.assertTrue(self.d.update_config({"showprep": {"message": "x" * 121}}))
        self.assertEqual(self.d.update_config({"showprep": prep(app="tune2", link="https://smithlights.com")}), [])
        st = self.d.get_status()["showprep"]
        self.assertEqual((st["app"], st["link"], st["own_link"]), ("tune2", "https://smithlights.com", True))

    def test_defaults(self):
        sp = self.mc.load_config()["showprep"]
        self.assertEqual(sp, {"enabled": False, "app": "", "message": DEFAULT_MESSAGE, "link": ""})


@unittest.skipUnless(HAVE_PIL and HAVE_QR, "Pillow or qrcode not installed")
class TakingTurns(unittest.TestCase):
    def setUp(self):
        import tempfile
        from daemon_env import clear_config, daemon_module
        from fake_fpp import FakeFPP
        self.mc = daemon_module()
        clear_config()
        self.dir = tempfile.mkdtemp()
        self._old = os.environ.get("MC_SHM_DIR")
        os.environ["MC_SHM_DIR"] = self.dir
        self.fpp = FakeFPP(self.dir, {"P5 Panel": (192, 96)}).start()
        self.d = self.mc.CountdownDaemon()
        self.thread = threading.Thread(target=self.d.run, daemon=True)

    def tearDown(self):
        self.d.stop()
        if self.thread.is_alive():
            self.thread.join(5)
        self.fpp.stop()
        if self._old is None:
            os.environ.pop("MC_SHM_DIR", None)
        else:
            os.environ["MC_SHM_DIR"] = self._old
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_countdown_and_show_prep_take_turns(self):
        errors = self.d.update_config({
            "global": {"fpp_host": self.fpp.host, "screen_seconds": 1},
            "countdown": {"model": "P5 Panel",
                          "target": {"type": "custom", "custom_date": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")},
                          "text_style": {"font": "", "size": 10}, "number_style": {"font": "", "size": 10}},
            "showprep": prep(app="pulsemesh"),
        })
        self.assertEqual(errors, [])
        self.thread.start()
        seen, end = [], time.monotonic() + 3.5
        while time.monotonic() < end:
            slot = self.d.get_status()["showing"]["slot"]
            if slot and (not seen or seen[-1] != slot):
                seen.append(slot)
            time.sleep(0.01)
        self.assertGreaterEqual(len(seen), 3, seen)
        self.assertEqual(set(seen), {"countdown", "showprep"})


if __name__ == "__main__":
    unittest.main()
