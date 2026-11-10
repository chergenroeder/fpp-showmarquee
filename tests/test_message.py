"""Message pieces. Run: python3 -m unittest discover -s tests -v"""

import os
import sys
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from countdown.message import NUMBER, TEXT, build_message  # noqa: E402
from countdown.timecalc import Display, Target  # noqa: E402

NY = ZoneInfo("America/New_York")
XMAS = Target(datetime(2026, 12, 25, tzinfo=NY), "Christmas", "christmas", True)
EIGHT_DAYS = Display("days", 8, "8 Days", timedelta(days=7, hours=14))
HMS = Display("hms", 29672, "08:14:32", timedelta(seconds=29672))
BLANK = Display("blank", None, "", timedelta(0))


class BuildMessage(unittest.TestCase):

    def test_number_first(self):
        m = build_message(EIGHT_DAYS, XMAS, {"number_position": "first"})
        self.assertEqual(m.pieces, ((NUMBER, "8 Days"), (TEXT, "to Christmas")))
        self.assertEqual(m.plain, "8 Days to Christmas")

    def test_number_last(self):
        m = build_message(EIGHT_DAYS, XMAS, {"number_position": "last"})
        self.assertEqual(m.pieces, ((TEXT, "Christmas in"), (NUMBER, "8 Days")))
        self.assertEqual(m.plain, "Christmas in 8 Days")

    def test_defaults_are_number_first(self):
        self.assertEqual(build_message(EIGHT_DAYS, XMAS, {}).plain, "8 Days to Christmas")

    def test_hms_both_orders(self):
        self.assertEqual(build_message(HMS, XMAS, {"number_position": "first"}).plain,
                         "08:14:32 to Christmas")
        self.assertEqual(build_message(HMS, XMAS, {"number_position": "last"}).plain,
                         "Christmas in 08:14:32")

    def test_custom_connectors(self):
        layout = {"number_position": "first", "connector_first": "until"}
        self.assertEqual(build_message(EIGHT_DAYS, XMAS, layout).plain, "8 Days until Christmas")
        layout = {"number_position": "last", "connector_last": " is in "}
        self.assertEqual(build_message(EIGHT_DAYS, XMAS, layout).plain, "Christmas is in 8 Days")

    def test_empty_connector_or_name_leaves_no_double_space(self):
        m = build_message(EIGHT_DAYS, XMAS, {"number_position": "first", "connector_first": ""})
        self.assertEqual(m.pieces, ((NUMBER, "8 Days"), (TEXT, "Christmas")))
        no_name = Target(XMAS.when, "", "custom", False)
        m = build_message(EIGHT_DAYS, no_name, {"number_position": "last", "connector_last": ""})
        self.assertEqual(m.pieces, ((NUMBER, "8 Days"),))

    def test_blank(self):
        m = build_message(BLANK, XMAS, {})
        self.assertTrue(m.blank)
        self.assertEqual(m.plain, "")


if __name__ == "__main__":
    unittest.main()
