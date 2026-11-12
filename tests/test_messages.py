"""Custom messages: fill-ins, date windows, pages, drawing, preview and taking turns.

Run: .venv/bin/python -m unittest discover -s tests  (drawing/loop tests need Pillow)
"""

import os
import sys
import threading
import time
import unittest
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

from countdown.messages import (MessagePage, fill, in_window, message_pages, messages_status,  # noqa: E402
                                settings_problems)

try:
    import PIL  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

VALUES = {"days": "8", "tonight": "5:30–10 PM", "temp": None, "date": "Dec 17"}
DEC17 = date(2026, 12, 17)


def msg(text, **kw):
    return {"enabled": True, "text": text, "color": "text", "picture": "", "when": "always", **kw}


class FillIns(unittest.TestCase):
    def test_fill(self):
        self.assertEqual(fill("Only {days} days! Show {tonight}", VALUES), "Only 8 days! Show 5:30–10 PM")
        self.assertEqual(fill("Today is {date}", VALUES), "Today is Dec 17")

    def test_nothing_to_show_means_no_message(self):
        self.assertIsNone(fill("It's {temp} out", VALUES))
        self.assertIsNone(fill("{days}", {**VALUES, "days": ""}))

    def test_unknown_names_are_left_as_typed(self):
        self.assertEqual(fill("{nope} and {days}", VALUES), "{nope} and 8")
        self.assertEqual(fill("a { b }", VALUES), "a { b }")


class Windows(unittest.TestCase):
    def test_inside_and_outside(self):
        self.assertTrue(in_window("12-24", "12-25", date(2026, 12, 24)))
        self.assertTrue(in_window("12-24", "12-25", date(2027, 12, 25)))      # every year
        self.assertFalse(in_window("12-24", "12-25", date(2026, 12, 26)))
        self.assertFalse(in_window("12-24", "12-25", date(2026, 12, 23)))

    def test_wrapping_the_new_year(self):
        self.assertTrue(in_window("12-31", "01-01", date(2026, 12, 31)))
        self.assertTrue(in_window("12-31", "01-01", date(2027, 1, 1)))
        self.assertFalse(in_window("12-31", "01-01", date(2027, 1, 2)))
        self.assertFalse(in_window("12-31", "01-01", date(2026, 7, 4)))

    def test_bad_dates_never_match(self):
        self.assertFalse(in_window("13-01", "12-25", DEC17))
        self.assertFalse(in_window("", "", DEC17))


class Pages(unittest.TestCase):
    def test_pages_in_order_with_lines_colour_and_picture(self):
        cfg = {"enabled": True, "items": [msg("Merry Christmas!\nfrom   the Smiths", picture="tree", color="number"),
                                          msg("Only {days} days", color="#ffc400")]}
        pages = message_pages(cfg, VALUES, DEC17)
        self.assertEqual(pages[0], MessagePage(0, ("Merry Christmas!", "from the Smiths"), "number", "tree"))
        self.assertEqual((pages[1].lines, pages[1].color, pages[1].slot), (("Only 8 days",), "#ffc400", "message:2"))
        self.assertEqual(pages[0].plain, "[Tree] Merry Christmas! / from the Smiths")

    def test_skipped_messages(self):
        cfg = {"enabled": True, "items": [msg("off", enabled=False), msg("   "), msg("It's {temp}"),
                                          msg("Merry Christmas", when="dates", **{"from": "12-24", "to": "12-25"}),
                                          msg("shows")]}
        self.assertEqual([p.lines for p in message_pages(cfg, VALUES, DEC17)], [("shows",)])
        self.assertEqual([p.lines for p in message_pages(cfg, VALUES, date(2026, 12, 25))],
                         [("Merry Christmas",), ("shows",)])
        st = messages_status(cfg, VALUES, DEC17)
        self.assertEqual([i["why"] for i in st["items"]],
                         ["switched off", "no text", "nothing for {temp} right now", "outside its dates", ""])
        self.assertEqual(st["showing"], 1)

    def test_section_off(self):
        self.assertEqual(message_pages({"enabled": False, "items": [msg("x")]}, VALUES, DEC17), [])

    def test_bad_colour_or_picture_falls_back(self):
        page = message_pages({"enabled": True, "items": [msg("x", color="red", picture="cat")]}, VALUES, DEC17)[0]
        self.assertEqual((page.color, page.picture), ("text", ""))

    def test_settings_checks(self):
        self.assertEqual(settings_problems({"enabled": True, "items": [msg("ok")]}), [])
        self.assertTrue(settings_problems({"items": [msg("x" * 121)]}))
        self.assertTrue(settings_problems({"items": [msg("x", color="red")]}))
        self.assertTrue(settings_problems({"items": [msg("x", picture="cat")]}))
        self.assertTrue(settings_problems({"items": [msg("x", when="dates", **{"from": "02-30", "to": "03-01"})]}))
        self.assertTrue(settings_problems({"items": [msg("x")] * 11}))
        self.assertTrue(settings_problems({"items": "nope"}))


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class Drawing(unittest.TestCase):
    def setUp(self):
        from countdown.render import Style
        self.num = Style(None, 14, (0, 255, 0), False)
        self.txt = Style(None, 14, (255, 0, 0), False)

    def draw(self, page, w=192, h=96):
        from countdown.still import draw_message
        return draw_message(page, w, h, self.num, self.txt)

    def colours(self, img):
        px = img.load()
        return {px[x, y] for x in range(img.width) for y in range(img.height)} - {(0, 0, 0)}

    def test_pictures(self):
        from countdown.symbols import PICTURES, draw_symbol
        from countdown.messages import PICTURES as NAMES
        self.assertEqual(PICTURES, NAMES)
        for name in PICTURES:
            img = draw_symbol(name, 24)
            self.assertEqual(img.size, (24, 24))
            self.assertGreater(img.getchannel("A").getextrema()[1], 0, name)

    def test_picture_left_text_right(self):
        img, problem = self.draw(MessagePage(0, ("Merry Christmas",), "text", "heart"))
        self.assertEqual(problem, "")
        px = img.load()
        heart = [x for x in range(60) for y in range(96) if px[x, y][0] > 200 and px[x, y][1] < 80]
        text = [x for x in range(192) for y in range(96) if px[x, y] == (255, 0, 0)]
        self.assertTrue(heart and text)
        self.assertGreater(min(text), 192 * 0.34)            # all the text right of the picture

    def test_colours(self):
        self.assertEqual(self.colours(self.draw(MessagePage(0, ("Hi",), "text", ""))[0]), {(255, 0, 0)})
        self.assertEqual(self.colours(self.draw(MessagePage(0, ("Hi",), "number", ""))[0]), {(0, 255, 0)})
        self.assertEqual(self.colours(self.draw(MessagePage(0, ("Hi",), "#ffc400", ""))[0]), {(255, 196, 0)})

    def test_no_picture_is_centered(self):
        img, _ = self.draw(MessagePage(0, ("Happy Holidays",), "text", ""))
        left, top, right, bottom = img.getbbox()
        self.assertAlmostEqual(left, 192 - right, delta=2)

    def test_long_text_wraps_and_short_panels_warn(self):
        long = MessagePage(0, ("Thank you for visiting! Please drive slowly and enjoy the show",), "text", "")
        img, problem = self.draw(long)
        self.assertEqual(problem, "")
        rows = sorted({y for x in range(192) for y in range(96) if img.load()[x, y] != (0, 0, 0)})
        self.assertGreater(rows[-1] - rows[0], 30)            # more than one line
        _img, problem = self.draw(long, 64, 16)
        self.assertTrue(problem)


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class Daemon(unittest.TestCase):
    def setUp(self):
        from daemon_env import clear_config, daemon_module
        self.mc = daemon_module()
        clear_config()
        self.d = self.mc.CountdownDaemon()

    def test_fill_values(self):
        now = datetime(2026, 12, 17, 15, 0).astimezone()   # the player's local time, as local_now() gives
        cfg = self.mc._deep_merge(self.mc.load_defaults(), {
            "countdown": {"target": {"type": "christmas"}},
            "schedule": {"mode": "same", "every": {"start": "17:30", "end": "22:00"}}})
        v = self.d.fill_values(cfg, now)
        self.assertEqual(v, {"days": "8", "tonight": "5:30–10 PM", "temp": None, "date": "Dec 17"})
        cfg["schedule"]["nights"] = [False] * 7
        self.assertIsNone(self.d.fill_values(cfg, now)["tonight"])

    def test_preview_messages_mode_uses_samples(self):
        r = self.d.preview({"config": {"messages": {"enabled": False, "items": [msg("It's {temp}!", enabled=False)]}},
                            "width": 192, "height": 96, "as": "messages"})
        self.assertEqual(r["strips"][0]["message"], "It's 72°F!")
        self.assertIn("{temp}", r["note"])
        r = self.d.preview({"config": {}, "width": 192, "height": 96, "as": "messages"})
        self.assertIn("add a message", r["error"])

    def test_preview_now_and_validation(self):
        r = self.d.preview({"config": {"messages": {"enabled": True, "items": [msg("Hi"), msg("Bye", picture="star")]}},
                            "width": 192, "height": 96})
        self.assertEqual([x["slot"] for x in r["strips"]], ["countdown", "message:1", "message:2"])
        self.assertTrue(self.d.update_config({"messages": {"items": [msg("x", color="red")]}}))
        self.assertEqual(self.d.update_config({"messages": {"enabled": True, "items": [msg("Hi")]}}), [])
        st = self.d.get_status()["messages"]
        self.assertEqual((st["showing"], st["items"][0]["showing"]), (1, True))

    def test_defaults(self):
        self.assertEqual(self.mc.load_config()["messages"], {"enabled": False, "items": []})


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
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

    def test_countdown_then_each_message(self):
        errors = self.d.update_config({
            "global": {"fpp_host": self.fpp.host, "screen_seconds": 1},
            "countdown": {"model": "P5 Panel",
                          "target": {"type": "custom", "custom_date": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")},
                          "text_style": {"font": "", "size": 10}, "number_style": {"font": "", "size": 10}},
            "messages": {"enabled": True, "items": [msg("Hello", picture="star"), msg("Only {days} days")]},
        })
        self.assertEqual(errors, [])
        self.thread.start()
        seen, end = [], time.monotonic() + 4.5
        while time.monotonic() < end:
            s = self.d.get_status()["showing"]
            if s["slot"] and (not seen or seen[-1][0] != s["slot"]):
                seen.append((s["slot"], s["message"]))
            time.sleep(0.01)
        slots = [x[0] for x in seen]
        self.assertGreaterEqual(len(slots), 3, seen)
        self.assertEqual(set(slots), {"countdown", "message:1", "message:2"})
        self.assertIn(("message:2", "Only 3 days"), seen)


if __name__ == "__main__":
    unittest.main()
