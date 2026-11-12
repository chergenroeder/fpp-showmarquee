"""Open-Meteo weather: the fetch, the poller, the location and the daemon wiring.

Every test talks to a fake Open-Meteo on 127.0.0.1, never the real service.
"""

import json
import os
import socket
import ssl
import stat
import sys
import threading
import time
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from countdown.weather import (NO_LOCATION, Location, OpenMeteoError, OpenMeteoPoller,  # noqa: E402
                               fetch_open_meteo, make_location, weather_page)

T0 = 1794399300          # a quarter hour (12:15:00 UTC on 2026-11-11)
CFG = {"stale_minutes": 5}


def reply(t=T0, temp=3.9, wind=3.1, wdir=268, gust=6.5, rh=76, is_day=0):
    return {"latitude": 40.0, "longitude": -100.0, "current_units": {},
            "current": {"time": t, "interval": 900, "temperature_2m": temp, "relative_humidity_2m": rh,
                        "wind_speed_10m": wind, "wind_direction_10m": wdir, "wind_gusts_10m": gust,
                        "is_day": is_day}}


class FakeOpenMeteo:
    """Serves /v1/forecast. `responses` is a list of (status, body or callable, delay)."""

    def __init__(self):
        self.requests = []           # (query dict, headers)
        self.status, self.body, self.delay = 200, reply(), 0.0
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                u = urlsplit(self.path)
                fake.requests.append((parse_qs(u.query), dict(self.headers)))
                if fake.delay:
                    time.sleep(fake.delay)
                body = fake.body if isinstance(fake.body, (bytes, str)) else json.dumps(fake.body)
                body = body.encode() if isinstance(body, str) else body
                try:
                    self.send_response(fake.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except OSError:
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1/forecast"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class Locations(unittest.TestCase):
    def test_rounded_to_about_a_kilometre(self):
        self.assertEqual(make_location(40.712776, -74.005974, "plugin"), Location(40.71, -74.01, "plugin"))
        self.assertEqual(make_location("40.7", " -74.0 ", "fpp"), Location(40.7, -74.0, "fpp"))

    def test_unusable_locations(self):
        for lat, lon in ((0, 0), ("0", "0.0"), (None, 10), ("", ""), (91, 0), (0, 181),
                         ("north", 3), (float("nan"), 1), (True, 1)):
            self.assertIsNone(make_location(lat, lon, "fpp"), (lat, lon))


class Fetch(unittest.TestCase):
    def setUp(self):
        self.om = FakeOpenMeteo()
        self.loc = Location(40.71, -74.01, "plugin")

    def tearDown(self):
        self.om.stop()

    def test_sends_only_the_rounded_location_and_fields(self):
        data = fetch_open_meteo(self.loc, self.om.url, 5)
        self.assertEqual(data["current"]["temperature_2m"], 3.9)
        q, headers = self.om.requests[0]
        self.assertEqual(set(q), {"latitude", "longitude", "current", "wind_speed_unit", "timeformat"})
        self.assertEqual((q["latitude"], q["longitude"]), (["40.71"], ["-74.01"]))
        self.assertEqual(q["current"][0].split(","), ["temperature_2m", "relative_humidity_2m", "wind_speed_10m",
                                                      "wind_direction_10m", "wind_gusts_10m", "is_day"])
        self.assertEqual((q["wind_speed_unit"], q["timeformat"]), (["ms"], ["unixtime"]))
        self.assertEqual(headers.get("User-Agent"), "fpp-showmarquee (FPP plugin)")

    def test_http_error_gives_the_reason(self):
        self.om.status, self.om.body = 400, {"error": True, "reason": "Latitude must be in range"}
        with self.assertRaisesRegex(OpenMeteoError, "HTTP 400: Latitude must be in range"):
            fetch_open_meteo(self.loc, self.om.url, 5)

    def test_unreadable_reply(self):
        self.om.body = "<html>gateway</html>"
        with self.assertRaisesRegex(OpenMeteoError, "couldn't be read"):
            fetch_open_meteo(self.loc, self.om.url, 5)
        self.om.body = {"latitude": 1}
        with self.assertRaisesRegex(OpenMeteoError, "no current conditions"):
            fetch_open_meteo(self.loc, self.om.url, 5)

    def test_timeout(self):
        self.om.delay = 1.5
        t = time.monotonic()
        with self.assertRaisesRegex(OpenMeteoError, "didn't answer within"):
            fetch_open_meteo(self.loc, self.om.url, 0.5)
        self.assertLess(time.monotonic() - t, 1.4)

    def test_no_internet(self):
        err = urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided"))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaisesRegex(OpenMeteoError, "no internet: can't look up api.open-meteo.com"):
                fetch_open_meteo(self.loc)

    def test_certificate_error_points_at_the_clock(self):
        err = urllib.error.URLError(ssl.SSLCertVerificationError(1, "certificate is not yet valid"))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaisesRegex(OpenMeteoError, "check this player's date and time"):
                fetch_open_meteo(self.loc)

    def test_refused(self):
        with self.assertRaisesRegex(OpenMeteoError, "can't reach Open-Meteo"):
            fetch_open_meteo(self.loc, "http://127.0.0.1:1/v1/forecast", 2)


class Poller(unittest.TestCase):
    def make(self, loc=Location(40.0, -100.0, "fpp"), fetch=None, wall=T0 + 120):
        self.calls = []

        def fake_fetch(l, url, timeout):
            self.calls.append(l)
            if isinstance(self.next, Exception):
                raise self.next
            return self.next

        self.next = reply()
        self.loc = loc
        self.wall = wall
        return OpenMeteoPoller(lambda: self.loc, fetch=fetch or fake_fetch, wall=lambda: self.wall)

    def test_reply_becomes_the_page(self):
        p = self.make()
        self.assertTrue(p.poll())
        r = p.reading()
        self.assertEqual(r.source, "open-meteo")
        self.assertEqual(r.humidity, 76)
        page = weather_page(r, {**CFG, "wind": {"gust_min_diff_mph": 5}}, hour=12)
        self.assertEqual(page.lines, ("39°F", "7 mph W", "gusts 15"))
        # is_day 0 from Open-Meteo wins over the clock (noon): the moon
        self.assertEqual((page.symbol, page.is_day, page.day_from), ("moon", False, "open-meteo"))

    def test_is_day_is_asked_for_and_read(self):
        p = self.make()
        self.next = reply(is_day=1)
        p.poll()
        self.assertTrue(p.reading().is_day)
        self.assertEqual(weather_page(p.reading(), CFG, hour=23).symbol, "sun")

    def test_open_meteo_readings_last_45_minutes_not_5(self):
        p = self.make()
        p.poll()
        r, now = p.reading(), time.monotonic()
        age = now - r.temp_at
        self.assertAlmostEqual(age, 120, delta=2)        # from the server's own time
        self.assertEqual(weather_page(r, CFG, now + 2600 - age, 12).temp, "39°F")
        self.assertIsNone(weather_page(r, CFG, now + 2701 - age, 12))

    def test_a_wrong_player_clock_cannot_make_a_fresh_reply_stale(self):
        for wall in (T0 + 86400, T0 - 86400):
            p = self.make(wall=wall)
            p.poll()
            r = p.reading()
            self.assertLessEqual(time.monotonic() - r.temp_at, 902)
            self.assertEqual(weather_page(r, CFG, hour=12).temp, "39°F")

    def test_missing_and_null_fields(self):
        p = self.make()
        self.next = {"current": {"time": T0, "temperature_2m": None, "wind_speed_10m": 0.2,
                                 "wind_direction_10m": None}}
        self.assertTrue(p.poll())
        r = p.reading()
        self.assertIsNone(r.temp_c)
        page = weather_page(r, CFG, hour=12)
        self.assertEqual(page.lines, ("Calm",))

    def test_failed_fetch_keeps_the_last_reading(self):
        p = self.make()
        p.poll()
        self.next = OpenMeteoError("Open-Meteo didn't answer within 10 s")
        self.assertFalse(p.poll())
        self.assertEqual(p.error, "Open-Meteo didn't answer within 10 s")
        self.assertEqual(round(p.reading().temp_c, 1), 3.9)
        self.next = reply(temp=5.0)
        self.assertTrue(p.poll())
        self.assertEqual((p.error, p.failures, p.reading().temp_c), ("", 0, 5.0))

    def test_no_location_sends_nothing(self):
        p = self.make(loc=None)
        self.assertFalse(p.poll())
        self.assertEqual(p.error, NO_LOCATION)
        self.assertEqual(self.calls, [])

    def test_new_location_drops_the_old_reading(self):
        p = self.make()
        p.poll()
        self.loc = Location(51.5, -0.13, "plugin")
        self.next = OpenMeteoError("no internet: can't look up api.open-meteo.com")
        p.poll()
        self.assertIsNone(p.reading().temp_c)
        self.assertEqual(self.calls[-1], Location(51.5, -0.13, "plugin"))

    def test_quarter_hour_schedule(self):
        p = self.make()
        for wall, delay in ((T0, 60), (T0 + 30, 30), (T0 + 60, 900), (T0 + 61, 899),
                            (T0 + 58, 902), (T0 + 500, 460)):
            self.wall = wall
            self.assertAlmostEqual(p.delay_to_next(), delay, msg=wall - T0)

    def test_retries_after_1_2_4_8_minutes_then_quarter_hours(self):
        p = self.make(wall=T0 + 61)
        self.next = OpenMeteoError("down")
        delays = []
        for _ in range(6):
            p.poll()
            delays.append(p.next_delay(False))
        self.assertEqual(delays, [60, 120, 240, 480, 899, 899])
        self.assertEqual(p.next_delay(True), 899)

    def test_thread_fetches_at_once_and_wake_refetches_only_for_a_new_place(self):
        p = self.make()
        p.start()
        try:
            for _ in range(100):
                if self.calls:
                    break
                time.sleep(0.01)
            self.assertEqual(len(self.calls), 1)
            p.wake()                      # settings saved, same place
            time.sleep(0.2)
            self.assertEqual(len(self.calls), 1)
            self.loc = Location(51.5, -0.13, "plugin")
            p.wake()
            for _ in range(100):
                if len(self.calls) == 2:
                    break
                time.sleep(0.01)
            self.assertEqual(self.calls[-1].lat, 51.5)
            self.assertGreater(p.next_fetch_at - time.monotonic(), 60)
        finally:
            p.stop()
        self.assertFalse(p.running)

    def test_an_unexpected_error_does_not_kill_the_thread(self):
        def boom(loc, url, timeout):
            raise RuntimeError("bad")
        p = OpenMeteoPoller(lambda: Location(1.0, 1.0, "fpp"), fetch=boom)
        p.start()
        try:
            time.sleep(0.2)
            self.assertTrue(p.running)
            self.assertIn("bad", p.error)
        finally:
            p.stop()


class Daemon(unittest.TestCase):
    """Settings, the location file, migration and the source switch."""

    def setUp(self):
        from daemon_env import clear_config, daemon_module
        self.mc = daemon_module()
        clear_config()
        self._clear_location()
        self.om = FakeOpenMeteo()
        self._url = self.mc.CountdownDaemon.OPEN_METEO_URL
        self.mc.CountdownDaemon.OPEN_METEO_URL = self.om.url
        self.fpp_loc = None
        self._patch = mock.patch.object(self.mc, "fpp_location", lambda: self.fpp_loc)
        self._patch.start()
        self.d = self.mc.CountdownDaemon()

    def tearDown(self):
        self.d._ensure_listener({"weather": {"enabled": False}})
        self._patch.stop()
        self.mc.CountdownDaemon.OPEN_METEO_URL = self._url
        self.om.stop()
        self._clear_location()

    def _clear_location(self):
        try:
            os.remove(self.mc.LOCATION_PATH)
        except FileNotFoundError:
            pass

    def saved_file(self):
        with open(self.mc.CONFIG_PATH) as f:
            return json.load(f)

    def test_fresh_install_has_no_source_and_sends_nothing(self):
        cfg = self.d.get_config()
        self.assertEqual((cfg["weather"]["enabled"], cfg["weather"]["source"]), (False, ""))
        self.assertEqual(self.d.update_config({"weather": {"enabled": True}}), [])
        self.assertIsNone(self.d._ensure_listener(self.d.get_config()))
        st = self.d.weather_status(self.d.get_config())
        self.assertEqual((st["source"], st["error"]), ("", "choose a weather source"))
        self.assertEqual(self.om.requests, [])

    def test_bad_values_are_refused(self):
        self.assertTrue(self.d.update_config({"weather": {"source": "weather.com"}}))
        self.assertTrue(self.d.update_config({"weather": {"open_meteo": {"latitude": 95}}}))
        self.assertTrue(self.d.update_config({"weather": {"open_meteo": {"use_fpp_location": "yes"}}}))

    def test_own_location_is_kept_in_plugindata_not_config(self):
        errs = self.d.update_config({"weather": {"source": "open-meteo",
                                                 "open_meteo": {"use_fpp_location": False}}})
        self.assertEqual(errs, ["weather.open_meteo: enter a latitude and longitude, or use FPP's location"])
        errs = self.d.update_config({"weather": {"source": "open-meteo", "open_meteo": {
            "use_fpp_location": False, "latitude": 40.712776, "longitude": -74.005974}}})
        self.assertEqual(errs, [])
        om = self.saved_file()["weather"]["open_meteo"]
        self.assertEqual(om, {"use_fpp_location": False})
        self.assertNotIn("40.71", open(self.mc.CONFIG_PATH).read())
        self.assertEqual(stat.S_IMODE(os.stat(self.mc.LOCATION_PATH).st_mode), 0o600)
        self.assertTrue(self.mc.LOCATION_PATH.startswith(os.path.join(self.mc.MEDIA_DIR, "plugindata")))
        page = self.d.config_for_page()["weather"]["open_meteo"]
        self.assertEqual((page["latitude"], page["longitude"]), (40.712776, -74.005974))
        self.assertNotIn("latitude", self.d.get_config()["weather"]["open_meteo"])
        self.assertEqual(self.d.weather_location(), Location(40.71, -74.01, "plugin"))
        # Saving the page again (coordinates included) keeps them; clearing removes the file
        self.assertEqual(self.d.update_config(self.d.config_for_page()), [])
        self.assertTrue(os.path.exists(self.mc.LOCATION_PATH))
        self.assertEqual(self.d.update_config({"weather": {"open_meteo": {
            "use_fpp_location": True, "latitude": "", "longitude": ""}}}), [])
        self.assertFalse(os.path.exists(self.mc.LOCATION_PATH))

    def test_fpp_location_by_default(self):
        self.fpp_loc = Location(40.0, -100.0, "fpp")
        self.d.update_config({"weather": {"enabled": True, "source": "open-meteo"}})
        self.assertEqual(self.d.weather_location(), self.fpp_loc)
        st = self.d.weather_status(self.d.get_config())
        self.assertEqual(st["location"], {"lat": 40.0, "lon": -100.0, "from": "fpp"})
        self.fpp_loc = None
        st = self.d.weather_status(self.d.get_config())
        self.assertEqual((st["location"], st["error"][:12]), (None, "no location:"))

    def test_settings_from_before_2_1_keep_the_tempest(self):
        for enabled, source in ((True, "tempest"), (False, "")):
            os.makedirs(os.path.dirname(self.mc.CONFIG_PATH), exist_ok=True)
            with open(self.mc.CONFIG_PATH, "w") as f:
                json.dump({"global": {"schema_version": 1}, "countdown": {},
                           "weather": {"enabled": enabled, "port": 50222}}, f)
            cfg = self.mc.load_config()
            self.assertEqual(cfg["weather"]["source"], source)
            self.assertEqual(cfg["global"]["schema_version"], self.mc.SCHEMA_VERSION)
            self.assertEqual(self.saved_file()["weather"]["source"], source)

    def test_switching_source_swaps_the_reader(self):
        self.fpp_loc = Location(40.0, -100.0, "fpp")
        self.d.update_config({"weather": {"enabled": True, "source": "tempest", "port": 50299}})
        lst = self.d._ensure_listener(self.d.get_config())
        self.assertIsInstance(lst, self.mc.TempestListener)
        self.d.update_config({"weather": {"source": "open-meteo"}})
        p = self.d._ensure_listener(self.d.get_config())
        self.assertIsInstance(p, OpenMeteoPoller)
        self.assertFalse(lst.running)
        self.assertIs(self.d._ensure_listener(self.d.get_config()), p)     # no restart
        for _ in range(200):
            st = self.d.weather_status(self.d.get_config())
            if st.get("temp_f") is not None:
                break
            time.sleep(0.01)
        self.assertEqual((st["source"], st["temp_f"], st["wind_dir"]), ("open-meteo", 39.0, "W"))
        self.assertEqual(st["page"]["lines"][0], "39°F")
        self.assertEqual((st["is_day"], st["day_from"]), (False, "open-meteo"))
        self.assertEqual(st["last_fetch_age_s"], 0)
        self.assertGreater(st["next_fetch_s"], 0)
        q, _ = self.om.requests[0]
        self.assertEqual((q["latitude"], q["longitude"]), (["40.00"], ["-100.00"]))
        self.d.update_config({"weather": {"enabled": False}})
        self.assertIsNone(self.d._ensure_listener(self.d.get_config()))
        self.assertFalse(p.running)

    def test_preview_without_a_source_says_so(self):
        r = self.d.preview({"config": {"weather": {"enabled": True}}, "width": 192, "height": 96})
        if "error" in r and "Pillow" in r["error"]:
            self.skipTest("Pillow not installed")
        self.assertIn("choose a weather source", r["note"])


if __name__ == "__main__":
    unittest.main()
