"""Page order: global.page_order decides which section's pages take turns first.

Run: .venv/bin/python -m unittest discover -s tests  (preview/loop tests need Pillow)
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

from countdown.still import SECTIONS, order_pages, page_order, page_order_problems, section_of  # noqa: E402

try:
    import PIL  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


def g(order):
    return {"global": {"page_order": order}}


class Order(unittest.TestCase):
    def test_default(self):
        self.assertEqual(page_order({}), list(SECTIONS))
        self.assertEqual(SECTIONS, ("show", "messages", "countdown", "schedule", "showprep", "social", "weather"))

    def test_partial_or_messy_orders_are_completed(self):
        self.assertEqual(page_order(g(["schedule", "countdown"])),
                         ["schedule", "countdown", "show", "messages", "showprep", "social", "weather"])
        self.assertEqual(page_order(g(["messages", "nope", "messages"]))[:2], ["messages", "show"])
        self.assertEqual(page_order(g("weather")), list(SECTIONS))

    def test_section_of(self):
        self.assertEqual([section_of(s) for s in ("show", "message:3", "countdown", "schedule", "showprep",
                                                  "social:facebook+youtube", "weather")], list(SECTIONS))

    def test_sorting_keeps_each_sections_own_order(self):
        items = [("countdown", 0), ("social:facebook", 1), ("social:tiktok", 2), ("schedule", 3),
                 ("message:1", 4), ("message:2", 5)]
        got = order_pages(items, g(["messages", "schedule", "social"]))
        self.assertEqual([x[0] for x in got],
                         ["message:1", "message:2", "schedule", "social:facebook", "social:tiktok", "countdown"])

    def test_problems(self):
        self.assertEqual(page_order_problems({}), [])
        self.assertEqual(page_order_problems(g(list(SECTIONS))), [])
        self.assertTrue(page_order_problems(g(["weather", "weather"])))
        self.assertTrue(page_order_problems(g(["sideshow"])))
        self.assertTrue(page_order_problems(g("countdown")))


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class Preview(unittest.TestCase):
    def setUp(self):
        from daemon_env import clear_config, daemon_module
        self.mc = daemon_module()
        clear_config()
        self.d = self.mc.CountdownDaemon()

    def test_now_follows_the_order(self):
        cfg = {"schedule": {"enabled": True},
               "messages": {"enabled": True, "items": [{"enabled": True, "text": "Hi"}]},
               "global": {"page_order": ["messages", "schedule", "countdown"]}}
        r = self.d.preview({"config": cfg, "width": 192, "height": 96})
        self.assertEqual([x["slot"] for x in r["strips"]], ["message:1", "schedule", "countdown"])

    def test_countdown_mode_is_just_the_countdown(self):
        r = self.d.preview({"config": {"schedule": {"enabled": True}}, "width": 192, "height": 96, "as": "countdown"})
        self.assertEqual([x["slot"] for x in r["strips"]], ["countdown"])

    def test_saved_and_checked(self):
        self.assertTrue(self.d.update_config(g(["countdown", "countdown"])))
        self.assertEqual(self.d.update_config(g(["schedule", "countdown"])), [])
        self.assertEqual(self.d.get_config()["global"]["page_order"], ["schedule", "countdown"])
        self.assertEqual(self.mc.load_config()["global"]["page_order"], ["schedule", "countdown"])


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

    def test_the_matrix_follows_the_order(self):
        errors = self.d.update_config({
            "global": {"fpp_host": self.fpp.host, "screen_seconds": 1,
                       "page_order": ["schedule", "messages", "countdown"]},
            "countdown": {"model": "P5 Panel",
                          "target": {"type": "custom", "custom_date": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")},
                          "text_style": {"font": "", "size": 10}, "number_style": {"font": "", "size": 10}},
            "schedule": {"enabled": True},
            "messages": {"enabled": True, "items": [{"enabled": True, "text": "Hi"}]},
        })
        self.assertEqual(errors, [])
        self.thread.start()
        seen, end = [], time.monotonic() + 5
        while time.monotonic() < end:
            slot = self.d.get_status()["showing"]["slot"]
            if slot and (not seen or seen[-1] != slot):
                seen.append(slot)
            time.sleep(0.01)
        cycle = ["schedule", "message:1", "countdown"]
        self.assertGreaterEqual(len(seen), 4, seen)
        start = cycle.index(seen[0])
        self.assertEqual(seen, [cycle[(start + i) % 3] for i in range(len(seen))])


if __name__ == "__main__":
    unittest.main()
