"""Tempest weather: packets, the weather page, its layout, and taking turns with the countdown.

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

from countdown.weather import (Reading, TempestListener, WeatherPage, compass, condition_from_code,  # noqa: E402
                               weather_page)

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


def obs(epoch, temp_f, avg_mph=0.0, gust_mph=0.0, deg=0, serial=ST, lux=0, solar=0,
        rain_mm=0.0, precip=0, strike_km=0, strikes=0):
    c = (temp_f - 32) * 5 / 9
    return json.dumps({"serial_number": serial, "type": "obs_st", "hub_sn": HUB, "firmware_revision": 172,
                       "obs": [[epoch, 0.0, avg_mph * MPH, gust_mph * MPH, deg, 3, 837.0, c, 40.0,
                                lux, 0.0, solar, rain_mm, precip, strike_km, strikes, 2.68, 1]]}).encode()


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

    def test_light_level_is_kept(self):
        lst = TempestListener()
        lst.handle(obs(100, 50, lux=12000, solar=95), now=7)
        r = lst.reading()
        self.assertEqual((r.lux, r.solar_wm2, r.light_at), (12000, 95, 7))

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


class Page(unittest.TestCase):
    CFG = {"stale_minutes": 5}

    def page(self, r, cfg=None, now=100, hour=12):
        return weather_page(r, self.CFG if cfg is None else cfg, now, hour)

    def test_lines(self):
        p = self.page(reading(temp_f=72.4, mph=8.2, deg=315, gust=15))
        self.assertEqual(p.lines, ("72°F", "Wind 8 mph NW", "gusts 15"))
        self.assertEqual(p.plain, "[Sun] 72°F Wind 8 mph NW gusts 15")
        self.assertEqual(p.wind_label, "Wind")
        self.assertEqual(self.page(reading(temp_f=-3.6)).lines, ("-4°F",))

    def test_gusts_only_when_well_above_the_average(self):
        self.assertEqual(self.page(reading(mph=8, deg=0, gust=12.9)).lines, ("Wind 8 mph N",))
        self.assertEqual(self.page(reading(mph=8, deg=0, gust=13)).lines, ("Wind 8 mph N", "gusts 13"))
        cfg = {"wind": {"gust_min_diff_mph": 0, "gust_label": ""}}
        self.assertEqual(self.page(reading(mph=8, deg=0, gust=9), cfg).lines, ("Wind 8 mph N", "9"))

    def test_metric_units(self):
        metric = {"units": "metric"}
        p = self.page(reading(temp_f=72.4, mph=8.2, deg=315, gust=15), metric)
        self.assertEqual(p.lines, ("22°C", "Wind 13 km/h NW", "gusts 24"))
        self.assertEqual(self.page(reading(temp_f=26.6), metric).temp, "-3°C")
        self.assertEqual(self.page(reading(mph=0.6), metric).lines, ("Wind Calm",))        # calm is still under 1 mph
        # the gust rule and the wind symbol's limits stay in mph
        self.assertEqual(self.page(reading(mph=8, gust=12.9), metric).gust, "")
        self.assertEqual(self.page(reading(temp_f=50, mph=15), metric).symbol, "wind")
        self.assertEqual(self.page(reading(temp_f=50), {}).temp, "50°F")                   # imperial by default

    def test_wind_label(self):
        self.assertEqual(self.page(reading(mph=8, deg=0), {"wind": {"label": "Breeze"}}).lines, ("Breeze 8 mph N",))
        page = self.page(reading(mph=8, deg=0), {"wind": {"label": ""}})
        self.assertEqual((page.lines, page.wind_label), (("8 mph N",), ""))
        self.assertEqual(self.page(reading(temp_f=50)).wind_label, "")          # no wind line, no label

    def test_calm(self):
        self.assertEqual(self.page(reading(mph=0.6, deg=227, gust=1)).lines, ("Wind Calm",))
        self.assertEqual(self.page(reading(mph=0.2, deg=227, gust=9), {"wind": {"calm_text": "Still"}}).lines,
                         ("Wind Still", "gusts 9"))

    def test_options_off(self):
        cfg = {"wind": {"direction": False, "gusts": False}}
        self.assertEqual(self.page(reading(temp_f=50, mph=8, deg=315, gust=30), cfg).lines, ("50°F", "Wind 8 mph"))
        self.assertEqual(self.page(reading(temp_f=50, mph=8), {"wind": {"enabled": False}}).lines, ("50°F",))
        self.assertEqual(self.page(reading(temp_f=70, mph=3), {"temperature": {"enabled": False}}).lines, ("Wind 3 mph",))
        both_off = {"temperature": {"enabled": False}, "wind": {"enabled": False}}
        self.assertIsNone(self.page(reading(temp_f=70, mph=3), both_off))

    def test_stale_and_missing_readings_are_skipped(self):
        r = reading(temp_f=70, mph=5, deg=0, at=0)
        self.assertEqual(self.page(r, now=299).temp, "70°F")
        self.assertIsNone(self.page(r, now=301))
        self.assertIsNone(self.page(Reading(), now=0))

    def test_wind_symbol_by_speed_or_gusts(self):
        self.assertEqual(self.page(reading(temp_f=50, mph=14.4)).symbol, "sun")
        self.assertEqual(self.page(reading(temp_f=50, mph=15)).symbol, "wind")
        self.assertEqual(self.page(reading(temp_f=50, mph=5, gust=25)).symbol, "wind")
        self.assertEqual(self.page(reading(temp_f=50, mph=5, gust=24)).symbol, "sun")
        cfg = {"symbol": {"wind_mph": 5, "gust_mph": 99}}
        self.assertEqual(self.page(reading(temp_f=50, mph=5), cfg).symbol, "wind")
        # windy even when the wind line is switched off
        self.assertEqual(self.page(reading(temp_f=50, mph=20), {"wind": {"enabled": False}}).symbol, "wind")

    def test_day_and_night_from_the_tempest_light(self):
        r = reading(temp_f=50, mph=2)
        r.solar_wm2, r.lux, r.light_at = 120, 9000, 100
        self.assertEqual(self.page(r, hour=2).symbol, "sun")         # light wins over the clock
        r.solar_wm2, r.lux = 0, 0
        p = self.page(r, hour=12)
        self.assertEqual((p.symbol, p.day_from), ("moon", "tempest"))
        r.solar_wm2, r.lux = None, 400                                 # no solar: lux decides
        self.assertEqual(self.page(r, hour=2).symbol, "sun")

    def test_day_and_night_from_the_clock_when_unknown(self):
        r = reading(temp_f=50, mph=2)
        self.assertEqual([self.page(r, hour=h).symbol for h in (6, 7, 18, 19)], ["moon", "sun", "sun", "moon"])
        r.solar_wm2, r.light_at = 300, -1000                            # stale light reading: clock again
        self.assertEqual(self.page(r, hour=22).day_from, "clock")

    def test_open_meteo_is_day(self):
        r = reading(temp_f=50, mph=2)
        r.is_day, r.is_day_at = False, 100
        self.assertEqual(self.page(r, hour=12).symbol, "moon")


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class Layout(unittest.TestCase):
    F = None

    def styles(self, size=10):
        from countdown.render import Style
        return Style(None, size, (0, 255, 0), False), Style(None, size, (255, 0, 0), False)

    def test_symbol_at_most_40_percent_and_lines_fit(self):
        from countdown.still import weather_layout
        num, txt = self.styles()
        page = WeatherPage("wind", "38°F", "Wind 18 mph NW", "gusts 27", wind_label="Wind")
        for w, h in ((64, 32), (128, 64), (192, 96)):
            sym, gap, lines = weather_layout(page, w, h, num, txt)
            self.assertLessEqual(sym, w * 0.4)
            self.assertLessEqual(sym, h)
            for text, style, size in lines:
                l, _t, r, _b = style.font(size).getbbox(text, anchor="ls")
                self.assertLessEqual(r - l, w - sym - gap, (w, h, text))

    def test_wind_and_gust_lines_share_a_size(self):
        from countdown.still import weather_layout
        num, txt = self.styles(12)
        _s, _g, lines = weather_layout(WeatherPage("wind", "38°F", "Wind 18 mph NW", "gusts 27", wind_label="Wind"),
                                       128, 64, num, txt)
        self.assertEqual(lines[1][2], lines[2][2])

    def test_short_panel_drops_the_gust_line(self):
        from countdown.still import weather_layout
        num, txt = self.styles()
        _s, _g, lines = weather_layout(WeatherPage("wind", "38°F", "Wind 18 mph NW", "gusts 27", wind_label="Wind"),
                                       64, 16, num, txt)
        self.assertNotIn("gusts 27", [t for t, _st, _z in lines])
        self.assertTrue(all(z >= 8 for _t, _st, z in lines))

    def test_page_variants(self):
        from countdown.still import page_variants
        # the label goes last: after the gusts and the direction
        self.assertEqual(page_variants(WeatherPage("wind", "38°F", "Wind 18 mph NW", "gusts 27", wind_label="Wind")),
                         [("38°F", "Wind 18 mph NW", "gusts 27"), ("38°F", "Wind 18 mph NW"), ("38°F", "Wind 18 mph"),
                          ("38°F", "18 mph"), ("38°F",)])
        self.assertEqual(page_variants(WeatherPage("sun", "", "Wind Calm", wind_label="Wind")),
                         [("Wind Calm",), ("Calm",)])

    def test_label_kept_on_a_64_wide_panel(self):
        from countdown.still import weather_layout
        num, txt = self.styles(8)
        _s, _g, lines = weather_layout(WeatherPage("sun", "38°F", "Wind 8 mph NW", wind_label="Wind"), 64, 32, num, txt)
        self.assertTrue(any(t.startswith("Wind") for t, _st, _z in lines), lines)

    def test_drawing(self):
        from countdown.still import draw_weather_page
        num, txt = self.styles()
        img = draw_weather_page(WeatherPage("sun", "72°F", "Wind 3 mph", wind_label="Wind"), 64, 32, num, txt)
        self.assertEqual(img.size, (64, 32))
        px = img.load()
        sun_cols = [x for x in range(64) for y in range(32) if px[x, y][0] > 200 and 150 < px[x, y][1] < 230]
        green_cols = [x for x in range(64) for y in range(32) if px[x, y] == (0, 255, 0)]
        self.assertTrue(sun_cols and green_cols)
        self.assertLess(max(sun_cols), min(green_cols))      # symbol left of the text

    def test_symbols(self):
        from countdown.symbols import SYMBOLS, draw_symbol
        for name in SYMBOLS:
            for size in (8, 26, 64):
                img = draw_symbol(name, size)
                self.assertEqual((img.mode, img.size), ("RGBA", (size, size)))
                self.assertGreater(img.getchannel("A").getextrema()[1], 0)


class Conditions(unittest.TestCase):
    """Rain, sleet and storms from the Tempest; Open-Meteo's codes."""

    CFG = {"stale_minutes": 5}

    def sym(self, lst, now, hour=12):
        return weather_page(lst.reading(), self.CFG, now, hour)

    def test_rain_shows_and_lasts_ten_minutes(self):
        lst = TempestListener()
        lst.handle(obs(100, 50, avg_mph=3, solar=300), now=0)
        self.assertEqual(self.sym(lst, 1).symbol, "sun")
        lst.handle(obs(160, 50, avg_mph=3, solar=300, rain_mm=0.2, precip=1), now=60)
        p = self.sym(lst, 61)
        self.assertEqual((p.symbol, p.condition, p.condition_from), ("rain", "rain", "tempest"))
        lst.handle(obs(220, 50, avg_mph=3, solar=300), now=120)        # a dry minute: still rain
        self.assertEqual(self.sym(lst, 121).symbol, "rain")
        lst.handle(obs(700, 50, avg_mph=3, solar=300), now=600)
        self.assertEqual(self.sym(lst, 60 + 601).symbol, "sun")         # 10 minutes after the last drop

    def test_rain_start_event_shows_at_once(self):
        lst = TempestListener()
        lst.handle(obs(100, 50, solar=0), now=0)
        self.assertTrue(lst.handle(json.dumps({"serial_number": ST, "type": "evt_precip", "hub_sn": HUB,
                                               "evt": [130]}).encode(), now=30))
        self.assertEqual(self.sym(lst, 31).symbol, "rain")

    def test_cold_rain_and_hail_are_sleet(self):
        lst = TempestListener()
        lst.handle(obs(100, 33, rain_mm=0.1, precip=1), now=0)
        self.assertEqual(self.sym(lst, 1).symbol, "sleet")
        lst = TempestListener()
        lst.handle(obs(100, 60, precip=2), now=0)
        self.assertEqual(self.sym(lst, 1).symbol, "sleet")

    def test_lightning_needs_two_close_strikes(self):
        lst = TempestListener()
        lst.handle(obs(100, 70, solar=300, strike_km=8, strikes=1), now=0)
        self.assertEqual(self.sym(lst, 1).symbol, "sun")                 # one strike can be noise
        lst.handle(obs(160, 70, solar=300, strike_km=40, strikes=3), now=60)
        self.assertEqual(self.sym(lst, 61).symbol, "sun")                # too far away
        lst.handle(obs(220, 70, solar=300, strike_km=12, strikes=1), now=120)
        p = self.sym(lst, 121)
        self.assertEqual((p.symbol, p.condition_from), ("storm", "tempest"))
        lst.handle(obs(980, 70, solar=300), now=880)
        self.assertEqual(self.sym(lst, 0 + 901).symbol, "sun")           # the first strike is 15 minutes old

    def test_storm_beats_rain_and_rain_beats_wind(self):
        lst = TempestListener()
        lst.handle(obs(100, 70, avg_mph=30, rain_mm=1.0, precip=1), now=0)
        self.assertEqual(self.sym(lst, 1).symbol, "rain")
        lst.handle(obs(160, 70, avg_mph=30, rain_mm=1.0, precip=1, strike_km=5, strikes=4), now=60)
        self.assertEqual(self.sym(lst, 61).symbol, "storm")

    def test_tempest_without_rain_says_nothing_about_the_sky(self):
        lst = TempestListener()
        lst.handle(obs(100, 50, solar=0), now=0)
        p = self.sym(lst, 1)
        self.assertEqual((p.symbol, p.condition, p.condition_from), ("moon", "", ""))

    def test_codes(self):
        self.assertEqual([condition_from_code(c) for c in (0, 1, 2, 3, 45, 51, 57, 61, 66, 71, 80, 85, 95, 96, 99)],
                         ["clear", "partly", "partly", "cloudy", "fog", "rain", "sleet", "rain", "sleet", "snow",
                          "rain", "snow", "storm", "storm", "storm"])
        self.assertEqual([condition_from_code(c) for c in (None, "x", True, 4, 100)], [None] * 5)

    def test_plain_names_the_symbol(self):
        self.assertEqual(WeatherPage("partly_night", "40°F").plain, "[Partly cloudy] 40°F")
        self.assertEqual(WeatherPage("storm", "70°F").plain, "[Thunderstorm] 70°F")


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
        self.assertEqual(slots, ["countdown", "weather"])
        self.assertTrue(r["strips"][1]["message"].endswith("72\u00b0F Wind 8 mph NW gusts 15"))
        self.assertEqual(r["seconds"], 5)
        self.assertEqual((r["strips"][1]["strip_width"], r["strips"][1]["strip_height"]), (192, 96))
        self.assertIn("sample", r["note"])

    def test_live_reading_and_switched_off_messages(self):
        lst = TempestListener()
        lst.handle(obs(100, 37.4, 2, 3, 20), now=time.monotonic())
        lst.handle(rapid(101, 2, 20), now=time.monotonic())
        self.d._listener = lst
        r, slots = self.slots({"weather": {"enabled": True, "temperature": {"enabled": False}}})
        self.assertEqual(slots, ["countdown", "weather"])
        self.assertTrue(r["strips"][1]["message"].endswith("] Wind 2 mph NNE"), r["strips"][1]["message"])
        self.assertNotIn("note", r)

    def test_weather_only(self):
        _, slots = self.slots({"countdown": {"enabled": False}, "weather": {"enabled": True}})
        self.assertEqual(slots, ["weather"])

    def test_settings_from_before_the_page_load_with_its_defaults(self):
        os.makedirs(os.path.dirname(self.mc.CONFIG_PATH), exist_ok=True)
        with open(self.mc.CONFIG_PATH, "w") as f:
            json.dump({"global": {"schema_version": 3},
                       "weather": {"enabled": True, "source": "tempest",
                                   "temperature": {"enabled": True, "label": "Temp"},
                                   "wind": {"label": "Wind", "gusts": False}}}, f)
        cfg = self.mc.load_config()
        w = cfg["weather"]
        self.assertNotIn("label", w["temperature"])
        self.assertEqual(w["wind"]["label"], "Wind")                 # the wind label is kept: the page uses it
        self.assertFalse(w["wind"]["gusts"])                      # kept
        self.assertEqual(w["symbol"], {"wind_mph": 15, "gust_mph": 25, "conditions": True})
        self.assertNotIn("screen_seconds", w)
        self.assertEqual(cfg["global"]["screen_seconds"], 5)
        self.assertEqual(cfg["global"]["schema_version"], self.mc.SCHEMA_VERSION)
        with open(self.mc.CONFIG_PATH) as f:
            self.assertNotIn("label\": \"Temp", f.read())

    def test_settings_from_before_one_seconds_per_page(self):
        os.makedirs(os.path.dirname(self.mc.CONFIG_PATH), exist_ok=True)
        cases = [
            # Static countdown: its hold time wins
            ({"countdown": {"motion": {"direction": "static", "static_hold": 8}},
              "weather": {"screen_seconds": 3}, "social": {"screen_seconds": 4}}, 8),
            # Scrolling countdown: the first section's seconds
            ({"countdown": {"motion": {"direction": "R2L", "static_hold": 8}},
              "weather": {"screen_seconds": 3}, "social": {"screen_seconds": 4}}, 3),
            ({"social": {"screen_seconds": 12}}, 12),
            ({"countdown": {"motion": {"direction": "R2L"}}}, 5),
        ]
        for saved, want in cases:
            with open(self.mc.CONFIG_PATH, "w") as f:
                json.dump({"global": {"schema_version": 4}, **saved}, f)
            cfg = self.mc.load_config()
            self.assertEqual(cfg["global"]["screen_seconds"], want, saved)
            self.assertNotIn("motion", cfg["countdown"])
            self.assertNotIn("screen_seconds", cfg["weather"])
            self.assertNotIn("screen_seconds", cfg["social"])

    def test_an_old_settings_upload_loses_its_scroll_keys(self):
        self.assertEqual(self.d.update_config({"countdown": {"motion": {"direction": "R2L"}},
                                               "weather": {"screen_seconds": 9}}), [])
        cfg = self.d.get_config()
        self.assertNotIn("motion", cfg["countdown"])
        self.assertNotIn("screen_seconds", cfg["weather"])

    def test_new_settings_are_checked(self):
        self.assertTrue(self.d.update_config({"global": {"screen_seconds": 0}}))
        self.assertTrue(self.d.update_config({"global": {"screen_seconds": 601}}))
        self.assertTrue(self.d.update_config({"weather": {"symbol": {"wind_mph": -1}}}))
        self.assertTrue(self.d.update_config({"weather": {"symbol": {"gust_mph": "lots"}}}))
        self.assertEqual(self.d.update_config({"global": {"screen_seconds": 8}, "weather": {"symbol": {"wind_mph": 10}}}), [])

    def test_units_setting(self):
        self.assertTrue(self.d.update_config({"weather": {"units": "kelvin"}}))
        self.assertEqual(self.d.update_config({"weather": {"units": "metric"}}), [])
        self.assertEqual(self.mc.load_defaults()["weather"]["units"], "imperial")
        r = self.d.preview({"config": {"weather": {"enabled": True, "units": "metric"}}, "width": 192, "height": 96,
                            "as": "weather"})
        self.assertIn("°C", r["strips"][0]["message"])
        self.assertIn("km/h", r["strips"][0]["message"])

    def test_weather_mode_with_both_off_says_so(self):
        r = self.d.preview({"config": {"weather": {"temperature": {"enabled": False}, "wind": {"enabled": False}}},
                            "width": 64, "height": 32, "as": "weather"})
        self.assertIn("both off", r["error"])

    def test_other_modes_show_one_message(self):
        for mode in ("days", "under_day", "weather"):
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

    def configure(self, countdown=True, weather=True):
        errors = self.d.update_config({
            "global": {"fpp_host": self.fpp.host, "screen_seconds": 1},
            "countdown": {"model": "P5 Panel", "enabled": countdown,
                          "target": {"type": "custom", "custom_date": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")},
                          "text_style": {"font": "", "size": 6}, "number_style": {"font": "", "size": 6}},
            "weather": {"enabled": weather, "source": "tempest", "port": self.port},
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

    def test_countdown_and_weather_page_take_turns(self):
        self.configure()
        self.thread.start()
        self.assertTrue(self.fpp.wait_for(lambda: self.d.get_status()["weather"].get("temp_f") is not None, 5))
        seen = self.slots_seen(4)
        self.assertGreaterEqual(len(seen), 4, seen)
        cycle = ["countdown", "weather"]
        start = cycle.index(seen[0])
        self.assertEqual(seen, [cycle[(start + i) % 2] for i in range(len(seen))])
        st = self.d.get_status()
        # the fed packets have no daylight (solar 0): the moon, from the Tempest
        self.assertEqual(st["weather"]["page"]["lines"], ["72°F", "Wind 8 mph NW", "gusts 20"])
        self.assertEqual((st["weather"]["page"]["symbol"], st["weather"]["day_from"]), ("moon", "tempest"))
        self.assertEqual((st["weather"]["condition"], st["weather"]["condition_from"]), (None, None))   # no rain
        self.assertEqual(st["weather"]["hub"], HUB)

    def test_weather_page_holds_still_for_its_seconds(self):
        self.configure()
        self.thread.start()
        self.assertTrue(self.fpp.wait_for(lambda: self.d.get_status()["weather"].get("temp_f") is not None, 5))
        visits, end = [], time.monotonic() + 5         # [slot, started, {frames seen}]
        while time.monotonic() < end:
            slot = self.d.get_status()["showing"]["slot"]
            if not visits or visits[-1][0] != slot:
                visits.append([slot, time.monotonic(), set()])
            frame = self.fpp.last_frame.get("P5 Panel")
            if frame is not None:
                visits[-1][2].add(bytes(frame))
            time.sleep(0.01)
        held = [b[1] - a[1] for a, b in zip(visits, visits[1:]) if a[0] == "weather"]
        self.assertTrue(held, [v[:2] for v in visits])
        self.assertTrue(all(x > 0.8 for x in held), held)
        # each visit is one picture (plus a frame caught as it switched in or out), not a scroll
        self.assertTrue(all(len(v[2]) <= 3 for v in visits if v[0] == "weather"),
                        [len(v[2]) for v in visits])

    def test_weather_only(self):
        self.configure(countdown=False)
        self.thread.start()
        seen = self.slots_seen(3)
        self.assertEqual(seen, ["weather"])
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
