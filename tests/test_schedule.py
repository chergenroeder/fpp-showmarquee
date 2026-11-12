"""Daily schedule: show nights and times, wording, grouping, drawing, preview and taking turns.

Run: .venv/bin/python -m unittest discover -s tests  (drawing/loop tests need Pillow)
"""

import os
import sys
import threading
import time
import unittest
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

from countdown.schedule import (DAYS, day_span, format_range, night_times, schedule_page,  # noqa: E402
                                schedule_problems, settings_problems, week_lines)

try:
    import PIL  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

FRIDAY = datetime(2026, 12, 18, 12, 0)     # a Friday
SUNDAY = datetime(2026, 12, 20, 12, 0)


def t(start, end):
    return {"start": start, "end": end}


def same(start="17:30", end="22:00", **kw):
    return {"enabled": True, "mode": "same", "every": t(start, end), **kw}


def weekend(**kw):
    return {"enabled": True, "mode": "weekend", "weekend_nights": [False] * 5 + [True, True],
            "weeknight": t("17:00", "22:00"), "weekend": t("17:00", "23:00"), **kw}


def lines(cfg):
    return [(day_span(d), format_range(x)) for d, x in week_lines(cfg)]


class Times(unittest.TestCase):
    def test_same_every_night(self):
        self.assertEqual(night_times(same()), [("17:30", "22:00")] * 7)
        self.assertEqual(lines(same()), [("Nightly", "5:30–10 PM")])

    def test_weeknights_and_weekends(self):
        self.assertEqual(lines(weekend()), [("Sun–Thu", "5–10 PM"), ("Fri & Sat", "5–11 PM")])

    def test_weekend_can_be_other_nights(self):
        cfg = weekend(weekend_nights=[True] + [False] * 5 + [True])
        self.assertEqual(lines(cfg), [("Mon–Fri", "5–10 PM"), ("Sat & Sun", "5–11 PM")])

    def test_custom(self):
        c = [t("17:00", "21:00")] * 4 + [t("17:00", "22:00"), t("16:30", "23:00"), t("16:30", "23:00")]
        cfg = {"enabled": True, "mode": "custom", "custom": c}
        self.assertEqual(lines(cfg), [("Sun–Wed", "5–9 PM"), ("Thu", "5–10 PM"), ("Fri & Sat", "4:30–11 PM")])

    def test_same_times_on_nights_apart_share_a_line(self):
        a, b = t("18:00", "21:00"), t("17:00", "22:00")
        cfg = {"enabled": True, "mode": "custom", "custom": [a, b, a, b, a, t("16:00", "23:00"), t("16:00", "23:00")]}
        self.assertEqual(lines(cfg), [("Sun, Tue & Thu", "6–9 PM"), ("Mon & Wed", "5–10 PM"), ("Fri & Sat", "4–11 PM")])

    def test_dark_nights(self):
        cfg = same(nights=[True, False] + [True] * 5)
        self.assertIsNone(night_times(cfg)[1])
        self.assertEqual(lines(cfg), [("Tue–Sun", "5:30–10 PM")])
        self.assertEqual(lines(weekend(nights=[False] + [True] * 6)),
                         [("Mon–Thu", "5–10 PM"), ("Fri & Sat", "5–11 PM")])

    def test_day_spans(self):
        self.assertEqual(day_span([0, 1, 2, 3, 4, 5, 6]), "Nightly")
        self.assertEqual(day_span([3]), "Wed")
        self.assertEqual(day_span([0, 6]), "Sat & Sun")
        self.assertEqual(day_span([0, 5, 6]), "Fri–Sun")
        self.assertEqual(day_span([1, 3, 5]), "Mon, Wed & Fri")
        self.assertEqual(day_span([0, 1, 2, 4]), "Sun–Tue & Thu")
        self.assertEqual(day_span([1, 2, 5, 6]), "Mon & Tue, Fri & Sat")

    def test_time_wording(self):
        self.assertEqual(format_range(("17:30", "22:00")), "5:30–10 PM")
        self.assertEqual(format_range(("17:00", "00:00")), "5 PM–12 AM")        # past midnight
        self.assertEqual(format_range(("11:00", "13:30")), "11 AM–1:30 PM")
        self.assertEqual(format_range(("09:00", "11:15")), "9–11:15 AM")
        self.assertEqual(format_range(("17:30", "22:00"), "24"), "17:30–22:00")
        self.assertEqual(format_range(("7:05", "9:00"), "24"), "07:05–09:00")


class Pages(unittest.TestCase):
    def test_week_page_marks_tonight(self):
        page = schedule_page(weekend(), FRIDAY)
        self.assertEqual(page.title, "Show Times")
        self.assertEqual([(ln.days, ln.today) for ln in page.lines], [("Sun–Thu", False), ("Fri & Sat", True)])
        self.assertTrue(schedule_page(weekend(), SUNDAY).lines[0].today)
        self.assertEqual(schedule_page(weekend(title=""), FRIDAY).title, "")

    def test_tonight(self):
        page = schedule_page(weekend(show="tonight"), FRIDAY)
        self.assertEqual((page.kind, [(ln.days, ln.times) for ln in page.lines]), ("tonight", [("Tonight", "5–11 PM")]))

    def test_no_show_tonight_names_the_next(self):
        cfg = same(show="tonight", nights=[True] * 5 + [False, False])      # dark Fri, Sat
        page = schedule_page(cfg, FRIDAY)
        self.assertEqual([(ln.days, ln.times) for ln in page.lines],
                         [("No show tonight", ""), ("Next: Sun", "5:30–10 PM")])
        cfg = same(show="tonight", nights=[True] * 5 + [False, True])
        self.assertEqual(schedule_page(cfg, FRIDAY).lines[1].days, "Next: Tomorrow")

    def test_none_when_off_or_nothing_set(self):
        self.assertIsNone(schedule_page(same(enabled=False), FRIDAY))
        self.assertIsNotNone(schedule_page(same(enabled=False), FRIDAY, force=True))
        self.assertIsNone(schedule_page(same(nights=[False] * 7), FRIDAY))
        self.assertIsNone(schedule_page(same(start="", end=""), FRIDAY))

    def test_problems(self):
        self.assertEqual(schedule_problems(same()), [])
        self.assertEqual(schedule_problems(same(nights=[False] * 7)), ["no show nights are chosen"])
        self.assertEqual(schedule_problems(same(end="")), ["set the start and end time"])
        self.assertEqual(schedule_problems(weekend(weekend=t("", ""))), ["set the weekend start and end time"])
        cfg = {"mode": "custom", "custom": [t("17:00", "21:00")] * 5 + [t("", ""), t("17:00", "")]}
        self.assertEqual(schedule_problems(cfg), ["set a start and end time for Fri, Sat"])

    def test_settings_checks(self):
        self.assertEqual(settings_problems(same()), [])
        self.assertTrue(settings_problems(same(mode="sometimes")))
        self.assertTrue(settings_problems(same(start="25:00")))
        self.assertTrue(settings_problems(same(nights=[True] * 6)))
        self.assertTrue(settings_problems(same(clock="13")))
        self.assertTrue(settings_problems(same(custom=[t("17:00", "22:00")] * 6)))
        self.assertTrue(settings_problems(same(title="x" * 41)))
        self.assertEqual(settings_problems(same(start="")), [])          # empty is allowed while setting up


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class Drawing(unittest.TestCase):
    def setUp(self):
        from countdown.render import Style
        self.num = Style(None, 12, (0, 255, 0), False)
        self.txt = Style(None, 12, (255, 0, 0), False)

    def draw(self, cfg, w=192, h=96, now=FRIDAY):
        from countdown.still import draw_schedule_page
        return draw_schedule_page(schedule_page(cfg, now), w, h, self.num, self.txt)

    def test_week_table(self):
        img, problem = self.draw(weekend())
        self.assertEqual(problem, "")
        px = img.load()
        rows_red = {y for x in range(192) for y in range(96) if px[x, y] == (255, 0, 0)}
        rows_green = {y for x in range(192) for y in range(96) if px[x, y] == (0, 255, 0)}
        self.assertTrue(rows_red and rows_green)
        self.assertLess(min(rows_red), min(rows_green))       # the title (Text style) above the times

    def test_seven_different_nights_fit_a_96_tall_matrix(self):
        c = [t(f"{16 + i % 3}:00", f"{21 + i % 2}:30") for i in range(7)]
        img, problem = self.draw({"enabled": True, "mode": "custom", "custom": c})
        self.assertEqual(problem, "")
        self.assertIsNotNone(img.getbbox())

    def test_small_matrix_drops_the_title_first(self):
        _img, problem = self.draw(weekend(), 128, 24)
        self.assertIn("title", problem)

    def test_tonight_page(self):
        img, problem = self.draw(same(show="tonight"))
        self.assertEqual(problem, "")
        self.assertIsNotNone(img.getbbox())


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class Daemon(unittest.TestCase):
    def setUp(self):
        from daemon_env import clear_config, daemon_module
        self.mc = daemon_module()
        clear_config()
        self.d = self.mc.CountdownDaemon()

    def test_defaults_are_a_working_schedule(self):
        sc = self.mc.load_config()["schedule"]
        self.assertFalse(sc["enabled"])
        self.assertEqual((sc["mode"], sc["every"], sc["nights"]), ("same", t("17:30", "22:00"), [True] * 7))
        self.assertEqual(schedule_problems(sc), [])

    def test_preview(self):
        r = self.d.preview({"config": {"schedule": weekend()}, "width": 192, "height": 96})
        self.assertEqual([x["slot"] for x in r["strips"]], ["countdown", "schedule"])
        r = self.d.preview({"config": {"schedule": weekend(enabled=False)}, "width": 192, "height": 96,
                            "as": "schedule"})
        self.assertEqual([x["slot"] for x in r["strips"]], ["schedule"])
        self.assertIn("Fri & Sat", r["strips"][0]["message"])
        r = self.d.preview({"config": {"schedule": same(nights=[False] * 7)}, "width": 192, "height": 96,
                            "as": "schedule"})
        self.assertIn("sample", r["note"])

    def test_validation_and_status(self):
        self.assertTrue(self.d.update_config({"schedule": {"mode": "never"}}))
        self.assertTrue(self.d.update_config({"schedule": {"every": t("5pm", "10pm")}}))
        self.assertEqual(self.d.update_config({"schedule": weekend()}), [])
        st = self.d.get_status()["schedule"]
        self.assertEqual(st["summary"], "Sun–Thu 5–10 PM · Fri & Sat 5–11 PM")
        self.assertEqual(st["problems"], [])


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

    def test_countdown_and_schedule_take_turns(self):
        errors = self.d.update_config({
            "global": {"fpp_host": self.fpp.host, "screen_seconds": 1},
            "countdown": {"model": "P5 Panel",
                          "target": {"type": "custom", "custom_date": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")},
                          "text_style": {"font": "", "size": 10}, "number_style": {"font": "", "size": 10}},
            "schedule": weekend(),
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
        self.assertEqual(set(seen), {"countdown", "schedule"})


if __name__ == "__main__":
    unittest.main()
