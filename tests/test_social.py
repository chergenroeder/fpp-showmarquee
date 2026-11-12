"""Social media screens: handles, grouping, layout, drawing, preview and taking turns.

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

from countdown.social import (MIN_LOGO, Screen, clean_handle, handle_problem, layout_screen,  # noqa: E402
                              social_screens, social_status)

try:
    import PIL  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

ALL = ("facebook", "instagram", "tiktok", "youtube")


def social(enabled=True, **handles):
    """social config with the given sites on: social(facebook="me", tiktok="other")."""
    return {"enabled": enabled,
            "sites": {k: {"enabled": k in handles, "handle": handles.get(k, "")} for k in ALL}}


class Handles(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(clean_handle("  @Smith_Lights "), "Smith_Lights")
        self.assertEqual(clean_handle("@@x"), "x")
        self.assertEqual(clean_handle(None), "")
        self.assertEqual(clean_handle("@"), "")

    def test_problems(self):
        self.assertEqual(handle_problem(""), "")
        self.assertEqual(handle_problem("@smith.lights-2_b"), "")
        self.assertIn("letters", handle_problem("smith lights"))
        self.assertIn("letters", handle_problem("smith/lights"))
        self.assertIn("30", handle_problem("x" * 31))
        self.assertEqual(handle_problem("x" * 30), "")


class Grouping(unittest.TestCase):
    def test_same_handle_everywhere_is_one_screen(self):
        cfg = social(**{k: "SmithLights" for k in ALL})
        self.assertEqual(social_screens(cfg), [Screen(ALL, "SmithLights")])

    def test_all_different_one_screen_each_in_site_order(self):
        cfg = social(youtube="d", facebook="a", tiktok="c", instagram="b")
        self.assertEqual([(s.sites, s.handle) for s in social_screens(cfg)],
                         [(("facebook",), "a"), (("instagram",), "b"), (("tiktok",), "c"), (("youtube",), "d")])

    def test_two_pairs(self):
        cfg = social(facebook="SmithFamilyLights", instagram="smith_lights",
                     tiktok="smith_lights", youtube="SmithFamilyLights")
        self.assertEqual(social_screens(cfg), [Screen(("facebook", "youtube"), "SmithFamilyLights"),
                                               Screen(("instagram", "tiktok"), "smith_lights")])

    def test_case_and_at_sign_ignored_first_spelling_kept(self):
        cfg = social(instagram="SmithLights", youtube="@smithlights ")
        self.assertEqual(social_screens(cfg), [Screen(("instagram", "youtube"), "SmithLights")])

    def test_off_empty_and_bad_handles_are_skipped(self):
        cfg = social(facebook="", instagram="ok", tiktok="not ok")
        cfg["sites"]["youtube"] = {"enabled": False, "handle": "ok"}
        self.assertEqual(social_screens(cfg), [Screen(("instagram",), "ok")])

    def test_master_switch_off(self):
        self.assertEqual(social_screens(social(enabled=False, facebook="a")), [])

    def test_plain_and_slot(self):
        s = Screen(("facebook", "youtube"), "Me")
        self.assertEqual(s.plain, "[Facebook] [YouTube] @Me")
        self.assertEqual(s.slot, "social:facebook+youtube")

    def test_status_names_problems(self):
        st = social_status(social(facebook="", tiktok="a b", youtube="me"))
        self.assertEqual([x["plain"] for x in st["screens"]], ["[YouTube] @me"])
        self.assertIn("no handle", st["problems"]["facebook"])
        self.assertIn("letters", st["problems"]["tiktok"])


class Layout(unittest.TestCase):
    """layout_screen with a stand-in font: each character 5 px wide at size 10, height = size."""

    @staticmethod
    def lay(n, chars, w, h, size=10):
        return layout_screen(n, lambda s: chars * s // 2, lambda s: s, size, 4, w, h)

    def test_logo_takes_the_height_left(self):
        size, logo, fits = self.lay(1, 8, 64, 32)
        self.assertEqual((size, fits), (10, True))
        self.assertEqual(logo, 32 - 10 - 2)

    def test_four_logos_limited_by_width(self):
        size, logo, fits = self.lay(4, 8, 64, 32)
        self.assertLessEqual(4 * logo + 3 * max(1, logo // 5), 64)
        self.assertLess(logo, 20)
        self.assertGreaterEqual(logo, MIN_LOGO)

    def test_wide_handle_shrinks(self):
        size, logo, fits = self.lay(2, 16, 64, 32)
        self.assertEqual(size, 8)
        self.assertTrue(fits)

    def test_too_wide_even_at_smallest(self):
        size, logo, fits = self.lay(1, 40, 64, 32)
        self.assertEqual(size, 4)
        self.assertFalse(fits)

    def test_short_panel_shrinks_text_to_leave_room_for_logos(self):
        size, logo, fits = self.lay(1, 4, 64, 16, size=12)
        self.assertGreaterEqual(logo, MIN_LOGO)
        self.assertLess(size, 12)


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class Drawing(unittest.TestCase):
    def setUp(self):
        from countdown.render import Style
        self.style = Style(None, 10, (255, 0, 0), False)   # Pillow's built-in font

    def test_logos_are_square_rgba_any_size(self):
        from countdown.social import draw_logo
        for site in ALL:
            for size in (8, 20, 48):
                img = draw_logo(site, size)
                self.assertEqual((img.mode, img.size), ("RGBA", (size, size)), site)
                self.assertGreater(img.getchannel("A").getextrema()[1], 0, site)

    def test_brand_colours(self):
        from countdown.social import draw_logo
        fb = draw_logo("facebook", 40).convert("RGB").getpixel((8, 20))
        self.assertGreater(fb[2], 200)          # blue
        yt = draw_logo("youtube", 40).convert("RGB").getpixel((4, 20))
        self.assertGreater(yt[0], 200)
        self.assertLess(yt[1], 40)              # red

    def test_screen_logos_on_top_handle_below(self):
        from countdown.social import draw_screen
        img, fits = draw_screen(Screen(("facebook", "youtube"), "Me"), 64, 32, self.style)
        self.assertTrue(fits)
        self.assertEqual(img.size, (64, 32))
        px = img.load()
        red_rows = [y for y in range(32) if any(px[x, y] == (255, 0, 0) for x in range(64))]
        blue_rows = [y for y in range(32) if any(px[x, y][2] > 200 and px[x, y][0] < 100 for x in range(64))]
        self.assertTrue(red_rows and blue_rows)
        # handle text (pure red, no antialias) sits below the Facebook blue
        self.assertGreater(max(red_rows), max(blue_rows))
        # the logo row is centered: as much space left of it as right
        cols = [x for x in range(64) if any(px[x, y] != (0, 0, 0) for y in range(min(blue_rows), max(blue_rows) + 1))]
        self.assertLessEqual(abs(cols[0] - (63 - cols[-1])), 2)

    def test_too_wide_handle_is_flagged(self):
        from countdown.social import draw_screen
        _img, fits = draw_screen(Screen(("tiktok",), "x" * 30), 32, 16, self.style)
        self.assertFalse(fits)

    def test_cache_redraws_on_new_size(self):
        from countdown.still import StillCache
        c, s = StillCache(), Screen(("instagram",), "me")
        a = c.get(s, 64, 32, self.style, self.style)
        self.assertIs(c.get(s, 64, 32, self.style, self.style), a)
        self.assertEqual(c.get(s, 128, 64, self.style, self.style).size, (128, 64))


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class Preview(unittest.TestCase):
    def setUp(self):
        from daemon_env import clear_config, daemon_module
        self.mc = daemon_module()
        clear_config()
        self.d = self.mc.CountdownDaemon()

    def run_preview(self, cfg, **body):
        cfg = {"countdown": {"enabled": True}, **cfg}
        r = self.d.preview({"config": cfg, "width": 64, "height": 32, **body})
        self.assertNotIn("error", r)
        return r

    def test_now_adds_social_screens_after_the_countdown(self):
        r = self.run_preview({"social": social(facebook="A", youtube="a", tiktok="b")})
        self.assertEqual([x["slot"] for x in r["strips"]],
                         ["countdown", "social:facebook+youtube", "social:tiktok"])
        # every page, the countdown too, is a panel-sized picture
        self.assertEqual({(x["strip_width"], x["strip_height"]) for x in r["strips"]}, {(64, 32)})
        self.assertEqual(r["seconds"], 5)

    def test_social_mode_shows_screens_even_when_off(self):
        r = self.run_preview({"social": social(enabled=False, instagram="me")}, **{"as": "social"})
        self.assertEqual([x["message"] for x in r["strips"]], ["[Instagram] @me"])
        self.assertNotIn("note", r)

    def test_social_mode_with_nothing_set_uses_a_sample(self):
        r = self.run_preview({}, **{"as": "social"})
        self.assertEqual(len(r["strips"]), 1)
        self.assertIn("sample", r["note"])

    def test_too_wide_handle_warns(self):
        r = self.run_preview({"social": social(tiktok="W" * 30)}, **{"as": "social"})
        self.assertIn("too wide", r["warning"])

    def test_validation_and_saved_handles_lose_the_at(self):
        self.assertTrue(self.d.update_config({"global": {"screen_seconds": 0}}))
        self.assertTrue(self.d.update_config({"social": {"sites": {"tiktok": {"handle": "two words"}}}}))
        self.assertEqual(self.d.update_config({"social": {"sites": {"tiktok": {"enabled": True, "handle": " @me "}}}}), [])
        self.assertEqual(self.d.get_config()["social"]["sites"]["tiktok"]["handle"], "me")

    def test_logos_endpoint(self):
        logos = self.mc.logo_pngs()["logos"]
        self.assertEqual(sorted(logos), sorted(ALL))


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class TakingTurns(unittest.TestCase):
    """The real drawing loop with a fake fppd."""

    def setUp(self):
        import tempfile
        from daemon_env import clear_config, daemon_module
        from fake_fpp import FakeFPP
        self.mc = daemon_module()
        clear_config()
        self.dir = tempfile.mkdtemp()
        self._old = os.environ.get("MC_SHM_DIR")
        os.environ["MC_SHM_DIR"] = self.dir
        self.fpp = FakeFPP(self.dir, {"P5 Panel": (48, 16)}).start()
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

    def configure(self, countdown=True, seconds=1, **handles):
        so = social(**handles)
        errors = self.d.update_config({
            "global": {"fpp_host": self.fpp.host, "screen_seconds": seconds},
            "countdown": {"model": "P5 Panel", "enabled": countdown,
                          "target": {"type": "custom", "custom_date": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")},
                          "text_style": {"font": "", "size": 6}, "number_style": {"font": "", "size": 6}},
            "social": so,
        })
        self.assertEqual(errors, [])

    def watch(self, seconds):
        """[(slot, first seen at, frames seen)] in order."""
        seen, end = [], time.monotonic() + seconds
        while time.monotonic() < end:
            slot = self.d.get_status()["showing"]["slot"]
            frame = self.fpp.last_frame.get("P5 Panel")
            if slot and (not seen or seen[-1][0] != slot):
                seen.append((slot, time.monotonic(), set()))
            if slot and frame is not None:
                seen[-1][2].add(bytes(frame))
            time.sleep(0.01)
        return seen

    def test_countdown_then_each_screen_for_its_seconds(self):
        self.configure(facebook="a", youtube="A", tiktok="b")
        self.thread.start()
        seen = self.watch(5)
        names = [s for s, _, _ in seen]
        cycle = ["countdown", "social:facebook+youtube", "social:tiktok"]
        start = cycle.index(names[0])
        self.assertEqual(names, [cycle[(start + i) % 3] for i in range(len(names))])
        self.assertIn("social:tiktok", names)
        # every page, the countdown too, stays up about a second
        for (_slot, at, _), (_n, nxt, _f) in zip(seen, seen[1:]):
            self.assertGreater(nxt - at, 0.8, seen)

    def test_screens_hold_still(self):
        self.configure(seconds=2, instagram="me")
        self.thread.start()
        seen = self.watch(4)
        still = [frames for slot, _, frames in seen if slot.startswith("social:")]
        self.assertTrue(still, seen)
        # one unchanging picture while a screen is up (allowing the frame
        # captured as it switched in or out)
        self.assertLessEqual(min(len(f) for f in still), 3)

    def test_social_only(self):
        self.configure(countdown=False, facebook="a", tiktok="b")
        self.thread.start()
        names = [s for s, _, _ in self.watch(3)]
        self.assertTrue(set(names) <= {"social:facebook", "social:tiktok"} and len(names) >= 2, names)
        self.assertEqual(self.fpp.state["P5 Panel"], 1)

    def test_countdown_is_held_still_too(self):
        self.configure(seconds=2, youtube="me")
        self.thread.start()
        seen = self.watch(4.5)
        countdown = [frames for slot, _, frames in seen if slot == "countdown"]
        self.assertTrue(countdown, seen)
        self.assertLessEqual(min(len(f) for f in countdown), 3)    # one picture, not a scroll

    def test_status(self):
        self.configure(facebook="a", tiktok="")
        st = self.d.get_status()["social"]
        self.assertEqual([x["plain"] for x in st["screens"]], ["[Facebook] @a"])
        self.assertIn("tiktok", st["problems"])


if __name__ == "__main__":
    unittest.main()
