"""Tempest weather: packets, messages, layout, and taking turns with the countdown.

Run: .venv/bin/python -m unittest discover -s tests  (layout/loop tests need Pillow)
"""

import json
import os
import socket
import sys
import threading
import time
import unittest
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

from countdown.message import NUMBER, TEXT  # noqa: E402
from countdown.weather import (Reading, TempestListener, compass, temperature_message,  # noqa: E402
                               weather_messages, wind_message)

try:
    import PIL  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

MPH = 1 / 2.2369363   # m/s per mph
HUB, ST = "HB-00069444", "ST-00084993"


def rapid(epoch, mph, deg, serial=ST):
    return json.dumps({"serial_number": serial, "type": "rapid_wind", "hub_sn": HUB,
                       "ob": [epoch, mph * MPH, deg]}).encode()


def obs(epoch, temp_f, avg_mph=0.0, gust_mph=0.0, deg=0, serial=ST):
    c = (temp_f - 32) * 5 / 9
    return json.dumps({"serial_number": serial, "type": "obs_st", "hub_sn": HUB, "firmware_revision": 172,
                       "obs": [[epoch, 0.0, avg_mph * MPH, gust_mph * MPH, deg, 3, 837.0, c, 40.0,
                                0, 0.0, 0, 0.0, 0, 0, 0, 2.68, 1]]}).encode()


class Packets(unittest.TestCase):

    def test_obs_st_and_rapid_wind(self):
        lst = TempestListener()
        self.assertTrue(lst.handle(obs(100, 38.2, 3, 9, 200), "192.168.1.147", now=10))
        self.assertTrue(lst.handle(rapid(103, 8, 315), "192.168.1.147", now=13))
        r = lst.reading()
        self.assertAlmostEqual(r.temp_c * 9 / 5 + 32, 38.2, places=3)
        self.assertAlmostEqual(r.wind_ms / MPH, 8, places=3)
        self.assertEqual((r.wind_dir, r.wind_at, r.temp_at), (315, 13, 10))
        self.assertAlmostEqual(r.gust_ms / MPH, 9, places=3)
        self.assertEqual((r.hub, r.device, r.source), (HUB, ST, "192.168.1.147"))

    def test_duplicates_and_older_packets_are_dropped(self):
        lst = TempestListener()
        self.assertTrue(lst.handle(rapid(103, 8, 315), now=1))
        self.assertFalse(lst.handle(rapid(103, 8, 315), now=1.01))   # the same packet again
        self.assertFalse(lst.handle(rapid(100, 20, 90), now=2))      # older
        self.assertAlmostEqual(lst.reading().wind_ms / MPH, 8, places=3)
        self.assertEqual(lst.reading().packets["rapid_wind"], 3)

    def test_other_types_and_garbage_are_counted_or_ignored(self):
        lst = TempestListener()
        self.assertFalse(lst.handle(json.dumps({"serial_number": HUB, "type": "hub_status"}).encode()))
        self.assertFalse(lst.handle(b"not json"))
        self.assertFalse(lst.handle(b"[1,2,3]"))
        self.assertFalse(lst.handle(json.dumps({"type": "obs_st", "obs": "nope"}).encode()))
        self.assertEqual(lst.reading().packets, {"hub_status": 1})

    def test_device_filter(self):
        lst = TempestListener(device="st-00084993")
        self.assertFalse(lst.handle(rapid(1, 5, 0, serial="ST-00000001")))
        self.assertTrue(lst.handle(rapid(1, 5, 0)))

    def test_minute_average_used_when_rapid_wind_missing(self):
        lst = TempestListener()
        lst.handle(obs(100, 50, avg_mph=6, deg=90), now=0)
        self.assertAlmostEqual(lst.reading().wind_ms / MPH, 6, places=3)
        lst.handle(rapid(101, 9, 180), now=1)
        lst.handle(obs(160, 50, avg_mph=2, deg=0), now=10)   # rapid_wind is fresh: keep it
        self.assertAlmostEqual(lst.reading().wind_ms / MPH, 9, places=3)

    def test_compass(self):
        self.assertEqual([compass(d) for d in (0, 11, 12, 45, 200, 227, 315, 359)],
                         ["N", "N", "NNE", "NE", "SSW", "SW", "NW", "N"])


class RealSocket(unittest.TestCase):

    def test_listens_on_udp(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        lst = TempestListener(port=port, bind="127.0.0.1")
        lst.start()
        try:
            out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            end = time.monotonic() + 3
            while time.monotonic() < end and lst.reading().temp_c is None:
                out.sendto(obs(int(time.time()), 61.0), ("127.0.0.1", port))
                time.sleep(0.1)
            self.assertIsNotNone(lst.reading().temp_c)
            self.assertTrue(lst.running)
            self.assertEqual(lst.error, "")
            out.close()
        finally:
            lst.stop()
        self.assertFalse(lst.running)


def reading(temp_f=None, mph=None, deg=None, gust=None, at=100.0):
    return Reading(temp_c=None if temp_f is None else (temp_f - 32) * 5 / 9, temp_at=at,
                   wind_ms=None if mph is None else mph * MPH, wind_dir=deg, wind_at=at,
                   gust_ms=None if gust is None else gust * MPH, gust_at=at)


class Messages(unittest.TestCase):
    CFG = {"stale_minutes": 5}

    def test_temperature(self):
        m = temperature_message(reading(temp_f=72.4), self.CFG, 100)
        self.assertEqual(m.pieces, ((TEXT, "Temp"), (NUMBER, "72°F")))
        m = temperature_message(reading(temp_f=-3.6), {"temperature": {"label": ""}}, 100)
        self.assertEqual(m.pieces, ((NUMBER, "-4°F"),))

    def test_wind_with_direction_and_gusts(self):
        m = wind_message(reading(mph=8.2, deg=315, gust=15), self.CFG, 100)
        self.assertEqual(m.plain, "Wind 8 mph NW gusts 15")
        self.assertEqual(m.pieces[1], (NUMBER, "8 mph NW"))
        self.assertEqual(m.lines, ((0, 1), (2, 3)))

    def test_gusts_only_when_well_above_the_average(self):
        self.assertEqual(wind_message(reading(mph=8, deg=0, gust=12.9), self.CFG, 100).plain, "Wind 8 mph N")
        self.assertEqual(wind_message(reading(mph=8, deg=0, gust=13), self.CFG, 100).plain, "Wind 8 mph N gusts 13")
        cfg = {"wind": {"gust_min_diff_mph": 0, "gust_label": ""}}
        self.assertEqual(wind_message(reading(mph=8, deg=0, gust=9), cfg, 100).plain, "Wind 8 mph N 9")

    def test_calm(self):
        m = wind_message(reading(mph=0.6, deg=227, gust=1), self.CFG, 100)
        self.assertEqual(m.pieces, ((TEXT, "Wind"), (NUMBER, "Calm")))
        self.assertEqual(m.lines, ((0, 1),))
        m = wind_message(reading(mph=0.2, deg=227, gust=9), {"wind": {"calm_text": "Still"}}, 100)
        self.assertEqual(m.plain, "Wind Still gusts 9")

    def test_options_off(self):
        cfg = {"wind": {"direction": False, "gusts": False}}
        self.assertEqual(wind_message(reading(mph=8, deg=315, gust=30), cfg, 100).plain, "Wind 8 mph")
        self.assertTrue(wind_message(reading(mph=8), {"wind": {"enabled": False}}, 100).blank)
        self.assertTrue(temperature_message(reading(temp_f=70), {"temperature": {"enabled": False}}, 100).blank)

    def test_stale_and_missing_readings_are_skipped(self):
        r = reading(temp_f=70, mph=5, deg=0, at=0)
        self.assertFalse(weather_messages(r, self.CFG, now=299)["temperature"].blank)
        msgs = weather_messages(r, self.CFG, now=301)
        self.assertTrue(msgs["temperature"].blank and msgs["wind"].blank)
        self.assertTrue(weather_messages(Reading(), self.CFG, now=0)["wind"].blank)


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class Layout(unittest.TestCase):

    def test_wind_splits_into_its_two_lines(self):
        from countdown.render import Style, layout_strip
        red, green = Style(None, 12, (255, 0, 0), False), Style(None, 12, (0, 255, 0), False)
        m = wind_message(reading(mph=8, deg=315, gust=15), {}, 100)
        one = layout_strip(m, red, green, 400, "static")
        two = layout_strip(m, red, green, 96, "static")
        self.assertLessEqual(two.width, 96)
        self.assertGreater(two.height, one.height * 1.6)   # two lines, not four
        self.assertLess(two.height, one.height * 2.6)


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class PreviewSequence(unittest.TestCase):
    """POST preview "now" returns every message that takes turns."""

    def setUp(self):
        from daemon_env import clear_config, daemon_module
        self.mc = daemon_module()
        clear_config()
        self.d = self.mc.CountdownDaemon()

    def slots(self, cfg, **body):
        r = self.d.preview({"config": cfg, "width": 192, "height": 96, **body})
        self.assertNotIn("error", r)
        return r, [x["slot"] for x in r["strips"]]

    def test_weather_off_shows_only_the_countdown(self):
        r, slots = self.slots({})
        self.assertEqual(slots, ["countdown"])
        self.assertEqual(r["strip"], r["strips"][0]["strip"])

    def test_weather_on_without_data_uses_a_sample(self):
        r, slots = self.slots({"weather": {"enabled": True}})
        self.assertEqual(slots, ["countdown", "temperature", "wind"])
        self.assertEqual([x["message"] for x in r["strips"]][1:], ["Temp 72\u00b0F", "Wind 8 mph NW gusts 15"])
        self.assertIn("sample", r["note"])

    def test_live_reading_and_switched_off_messages(self):
        lst = TempestListener()
        lst.handle(obs(100, 37.4, 2, 3, 20), now=time.monotonic())
        lst.handle(rapid(101, 2, 20), now=time.monotonic())
        self.d._listener = lst
        r, slots = self.slots({"weather": {"enabled": True, "temperature": {"enabled": False}}})
        self.assertEqual(slots, ["countdown", "wind"])
        self.assertEqual(r["strips"][1]["message"], "Wind 2 mph NNE")
        self.assertNotIn("note", r)

    def test_weather_only(self):
        _, slots = self.slots({"countdown": {"enabled": False}, "weather": {"enabled": True}})
        self.assertEqual(slots, ["temperature", "wind"])

    def test_other_modes_show_one_message(self):
        for mode in ("days", "under_day", "temperature", "wind"):
            r, slots = self.slots({"weather": {"enabled": True}}, **{"as": mode})
            self.assertEqual(len(slots), 1, mode)


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class TakingTurns(unittest.TestCase):
    """The real drawing loop with a fake fppd and real UDP weather packets."""

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
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(("127.0.0.1", 0))
        self.port = probe.getsockname()[1]
        probe.close()
        self.d = self.mc.CountdownDaemon()
        self.thread = threading.Thread(target=self.d.run, daemon=True)
        self.sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._feed = threading.Event()
        threading.Thread(target=self.feed, daemon=True).start()

    def feed(self):
        n = int(time.time())
        while not self._feed.wait(0.2):
            n += 1
            for pkt in (obs(n, 72.0, 8, 20, 315), rapid(n, 8, 315)):
                try:
                    self.sender.sendto(pkt, ("127.0.0.1", self.port))
                except OSError:
                    pass

    def tearDown(self):
        self._feed.set()
        time.sleep(0.25)
        self.sender.close()
        self.d.stop()
        self.thread.join(5)
        self.fpp.stop()
        if self._old is None:
            os.environ.pop("MC_SHM_DIR", None)
        else:
            os.environ["MC_SHM_DIR"] = self._old
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def configure(self, direction="R2L", countdown=True, weather=True, **motion):
        errors = self.d.update_config({
            "global": {"fpp_host": self.fpp.host},
            "countdown": {"model": "P5 Panel", "enabled": countdown,
                          "target": {"type": "custom", "custom_date": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")},
                          "motion": {"direction": direction, "pixels_per_second": 400, **motion},
                          "text_style": {"font": "", "size": 6}, "number_style": {"font": "", "size": 6}},
            "weather": {"enabled": weather, "port": self.port},
        })
        self.assertEqual(errors, [])

    def slots_seen(self, seconds):
        seen, end = [], time.monotonic() + seconds
        while time.monotonic() < end:
            slot = self.d.get_status()["showing"]["slot"]
            if slot and (not seen or seen[-1] != slot):
                seen.append(slot)
            time.sleep(0.01)
        return seen

    def test_scrolling_takes_turns_in_order(self):
        self.configure()
        self.thread.start()
        self.assertTrue(self.fpp.wait_for(lambda: self.d.get_status()["weather"].get("temp_f") is not None, 5))
        seen = self.slots_seen(4)
        self.assertGreaterEqual(len(seen), 4, seen)
        cycle = ["countdown", "temperature", "wind"]
        start = cycle.index(seen[0])
        self.assertEqual(seen, [cycle[(start + i) % 3] for i in range(len(seen))])
        st = self.d.get_status()
        self.assertEqual(st["weather"]["messages"], {"temperature": "Temp 72°F", "wind": "Wind 8 mph NW gusts 20"})
        self.assertEqual(st["weather"]["hub"], HUB)

    def test_static_holds_each_message(self):
        self.configure(direction="static", static_hold=1)
        self.thread.start()
        self.assertTrue(self.fpp.wait_for(lambda: self.d.get_status()["weather"].get("temp_f") is not None, 5))
        seen = self.slots_seen(3.6)
        self.assertGreaterEqual(len(seen), 3, seen)
        self.assertLessEqual(len(seen), 5, seen)

    def test_weather_only(self):
        self.configure(countdown=False)
        self.thread.start()
        seen = self.slots_seen(3)
        self.assertTrue(seen and set(seen) <= {"temperature", "wind"}, seen)
        self.assertEqual(self.fpp.state["P5 Panel"], 1)

    def test_no_weather_yet_shows_only_the_countdown(self):
        self._feed.set()   # nothing arrives
        self.configure()
        self.thread.start()
        seen = self.slots_seen(2)
        self.assertEqual(seen, ["countdown"])
        w = self.d.get_status()["weather"]
        self.assertTrue(w["enabled"] and w["listening"])
        self.assertIsNone(w.get("temp_f"))

    def test_both_off_turns_model_off(self):
        self.configure(countdown=False, weather=False)
        self.thread.start()
        self.assertTrue(self.fpp.wait_for(lambda: self.d.get_status()["output"]["state"] == "off"))
        self.assertFalse(self.d.get_status()["weather"]["listening"])


if __name__ == "__main__":
    unittest.main()
