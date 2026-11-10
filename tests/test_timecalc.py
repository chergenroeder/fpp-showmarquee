"""Countdown time rules. Run: python3 -m unittest discover -s tests -v"""

import os
import sys
import time as _time
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from countdown.timecalc import compute_display, resolve_target  # noqa: E402

NY = ZoneInfo("America/New_York")
XMAS = {"type": "christmas"}
NEWYEAR = {"type": "newyear"}
HMS = {"under_one_day": "hms"}
HOURS = {"under_one_day": "hours"}


def at(y, mo, d, h=0, mi=0, s=0, us=0):
    return datetime(y, mo, d, h, mi, s, us, tzinfo=NY)


def custom(date, time="00:00", repeat=False, name="Opening Night"):
    return {"type": "custom", "custom_date": date, "custom_time": time,
            "custom_repeat_yearly": repeat, "event_name": {"custom": name}}


def show(target_cfg, now, layout=HMS):
    t = resolve_target(target_cfg, now, NY)
    return compute_display(t, now, layout, NY)


class ResolveTarget(unittest.TestCase):

    def test_christmas_this_year(self):
        t = resolve_target(XMAS, at(2026, 11, 10, 9), NY)
        self.assertEqual(t.when, at(2026, 12, 25))
        self.assertEqual(t.name, "Christmas")

    def test_christmas_day_keeps_this_year_so_it_stays_blank(self):
        self.assertEqual(resolve_target(XMAS, at(2026, 12, 25, 23, 59, 59), NY).when, at(2026, 12, 25))

    def test_christmas_rolls_over_at_midnight_after(self):
        self.assertEqual(resolve_target(XMAS, at(2026, 12, 26), NY).when, at(2027, 12, 25))

    def test_new_year_from_november(self):
        self.assertEqual(resolve_target(NEWYEAR, at(2026, 11, 10), NY).when, at(2027, 1, 1))

    def test_new_year_on_new_years_eve(self):
        self.assertEqual(resolve_target(NEWYEAR, at(2026, 12, 31, 23), NY).when, at(2027, 1, 1))

    def test_new_years_day_keeps_this_year_then_rolls(self):
        self.assertEqual(resolve_target(NEWYEAR, at(2027, 1, 1, 12), NY).when, at(2027, 1, 1))
        self.assertEqual(resolve_target(NEWYEAR, at(2027, 1, 2), NY).when, at(2028, 1, 1))

    def test_custom_with_time(self):
        t = resolve_target(custom("2027-03-14", "18:30"), at(2026, 11, 10), NY)
        self.assertEqual(t.when, at(2027, 3, 14, 18, 30))
        self.assertEqual(t.name, "Opening Night")
        self.assertFalse(t.repeats)

    def test_custom_in_past_without_repeat_stays_put(self):
        t = resolve_target(custom("2026-01-05"), at(2026, 11, 10), NY)
        self.assertEqual(t.when, at(2026, 1, 5))

    def test_custom_repeat_yearly_rolls_over(self):
        t = resolve_target(custom("2020-06-15", repeat=True), at(2026, 11, 10), NY)
        self.assertEqual(t.when, at(2027, 6, 15))
        t = resolve_target(custom("2020-12-01", repeat=True), at(2026, 11, 10), NY)
        self.assertEqual(t.when, at(2026, 12, 1))

    def test_custom_repeat_feb_29_in_non_leap_year(self):
        t = resolve_target(custom("2024-02-29", repeat=True), at(2026, 11, 10), NY)
        self.assertEqual(t.when, at(2027, 2, 28))
        t = resolve_target(custom("2024-02-29", repeat=True), at(2027, 3, 1), NY)
        self.assertEqual(t.when, at(2028, 2, 29))  # 2028 is a leap year

    def test_custom_invalid_or_missing_date(self):
        self.assertIsNone(resolve_target(custom(""), at(2026, 11, 10), NY))
        self.assertIsNone(resolve_target(custom("2026-13-01"), at(2026, 11, 10), NY))
        self.assertIsNone(resolve_target(custom("2026-12-01", "25:00"), at(2026, 11, 10), NY))

    def test_unknown_type(self):
        self.assertIsNone(resolve_target({"type": "easter"}, at(2026, 11, 10), NY))

    def test_event_name_override(self):
        cfg = {"type": "christmas", "event_name": {"christmas": "  Xmas "}}
        self.assertEqual(resolve_target(cfg, at(2026, 11, 10), NY).name, "Xmas")


class DaysDisplay(unittest.TestCase):

    def test_eight_days_any_time_of_day(self):
        for h in (0, 9, 23):
            d = show(XMAS, at(2026, 12, 17, h, 59))
            self.assertEqual((d.kind, d.value, d.number_text), ("days", 8, "8 Days"))

    def test_singular_day(self):
        # A midnight target only reads "1 Day" at exactly 24 h out
        d = show(XMAS, at(2026, 12, 24))
        self.assertEqual(d.number_text, "1 Day")

    def test_custom_unit_words(self):
        layout = {"under_one_day": "hms", "units": {"day": "Tag", "days": "Tage"}}
        self.assertEqual(show(XMAS, at(2026, 12, 17), layout).number_text, "8 Tage")

    def test_day_count_across_dst_fall_back(self):
        # Nov 1 2026 is a 25-hour day in New York
        d = show(custom("2026-11-03"), at(2026, 10, 31, 12))
        self.assertEqual(d.value, 3)

    def test_day_count_across_dst_spring_forward(self):
        # Mar 8 2026 is a 23-hour day in New York
        d = show(custom("2026-03-10"), at(2026, 3, 7, 0, 30))
        self.assertEqual(d.value, 3)
        d = show(custom("2026-03-10"), at(2026, 3, 8, 23, 30))
        self.assertEqual(d.value, 2)

    def test_24h_boundary_with_a_custom_time(self):
        cfg = custom("2026-12-31", "18:00")
        self.assertEqual(show(cfg, at(2026, 12, 30, 18)).kind, "days")
        self.assertEqual(show(cfg, at(2026, 12, 30, 18, 0, 1)).kind, "hms")


class UnderOneDay(unittest.TestCase):

    def test_hms_ticks(self):
        d = show(XMAS, at(2026, 12, 24, 15, 45, 28))
        self.assertEqual((d.kind, d.number_text), ("hms", "08:14:32"))

    def test_hms_just_under_a_day(self):
        self.assertEqual(show(XMAS, at(2026, 12, 24, 0, 0, 0, 500000)).number_text, "23:59:59")

    def test_hms_final_second_reads_zero(self):
        self.assertEqual(show(XMAS, at(2026, 12, 24, 23, 59, 59, 500000)).number_text, "00:00:00")

    def test_hours_round_up(self):
        d = show(XMAS, at(2026, 12, 24, 15, 50), HOURS)  # 8h10m left
        self.assertEqual((d.kind, d.number_text), ("hours", "9 Hours"))

    def test_hours_singular_and_one_hour_boundary(self):
        self.assertEqual(show(XMAS, at(2026, 12, 24, 22, 30), HOURS).number_text, "2 Hours")
        self.assertEqual(show(XMAS, at(2026, 12, 24, 22, 59, 59), HOURS).number_text, "2 Hours")
        self.assertEqual(show(XMAS, at(2026, 12, 24, 23), HOURS).number_text, "1 Hour")

    def test_last_hour_switches_to_minutes(self):
        d = show(XMAS, at(2026, 12, 24, 23, 15, 40), HOURS)  # 44m20s left
        self.assertEqual((d.kind, d.number_text), ("minutes", "45 Minutes"))
        self.assertEqual(show(XMAS, at(2026, 12, 24, 23, 59, 30), HOURS).number_text, "1 Minute")

    def test_hours_across_dst_spring_forward(self):
        # 00:00 -> 06:00 on Mar 8 2026 is only 5 real hours
        d = show(custom("2026-03-08", "06:00"), at(2026, 3, 8), HOURS)
        self.assertEqual(d.number_text, "5 Hours")

    def test_hms_across_dst_fall_back(self):
        # 00:00 -> 06:00 on Nov 1 2026 is 7 real hours
        self.assertEqual(show(custom("2026-11-01", "06:00"), at(2026, 11, 1)).number_text, "07:00:00")


class Blank(unittest.TestCase):

    def test_blank_at_zero_and_through_the_day(self):
        for now in (at(2026, 12, 25), at(2026, 12, 25, 13), at(2026, 12, 25, 23, 59, 59)):
            d = show(XMAS, now)
            self.assertEqual((d.kind, d.number_text), ("blank", ""))

    def test_counting_again_the_next_day(self):
        d = show(XMAS, at(2026, 12, 26))
        self.assertEqual((d.kind, d.value), ("days", 364))

    def test_past_custom_without_repeat_is_blank_for_good(self):
        self.assertEqual(show(custom("2026-01-05"), at(2026, 11, 10)).kind, "blank")
        self.assertEqual(show(custom("2026-01-05"), at(2030, 1, 5)).kind, "blank")


class SystemLocalTime(unittest.TestCase):
    """The daemon passes tz=None and fixed-offset `now`s from datetime.astimezone()."""

    def setUp(self):
        self._old_tz = os.environ.get("TZ")
        os.environ["TZ"] = "America/New_York"
        _time.tzset()

    def tearDown(self):
        if self._old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._old_tz
        _time.tzset()

    def local(self, *args):
        return datetime(*args).astimezone()

    def test_target_across_dst_keeps_its_own_wall_time(self):
        now = self.local(2026, 3, 1, 12)  # EST, -05:00
        t = resolve_target(custom("2026-03-20"), now)
        self.assertEqual(t.when.strftime("%Y-%m-%d %H:%M %z"), "2026-03-20 00:00 -0400")
        d = compute_display(t, now, HMS)
        self.assertEqual(d.value, 19)

    def test_hours_across_dst_in_local_mode(self):
        now = self.local(2026, 3, 8, 0, 0)
        t = resolve_target(custom("2026-03-08", "06:00"), now)
        self.assertEqual(compute_display(t, now, HOURS).number_text, "5 Hours")

    def test_christmas_rollover_in_local_mode(self):
        now = self.local(2026, 12, 26, 0, 0, 1)
        self.assertEqual(resolve_target(XMAS, now).when.date(), datetime(2027, 12, 25).date())


if __name__ == "__main__":
    unittest.main()
