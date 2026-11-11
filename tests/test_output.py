"""Overlay output and the daemon's drawing loop, against a fake fppd.

Run: .venv/bin/python -m unittest discover -s tests  (the loop test needs Pillow)
"""

import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

from countdown.output import OutputError, OverlayOutput  # noqa: E402
from fake_fpp import FakeFPP  # noqa: E402
from daemon_env import clear_config, daemon_module  # noqa: E402

try:
    import PIL  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

W, H = 32, 16


class OutputBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._old = os.environ.get("MC_SHM_DIR")
        os.environ["MC_SHM_DIR"] = self.dir
        self.fpp = FakeFPP(self.dir, {"P5 Panel": (W, H), "Other": (8, 8)}).start()

    def tearDown(self):
        self.fpp.stop()
        if self._old is None:
            os.environ.pop("MC_SHM_DIR", None)
        else:
            os.environ["MC_SHM_DIR"] = self._old
        shutil.rmtree(self.dir, ignore_errors=True)


class Output(OutputBase):

    def test_open_write_and_fppd_picks_up(self):
        out = OverlayOutput(self.fpp.host, "P5 Panel")
        out.open()
        self.assertEqual((out.width, out.height, out.bpp), (W, H, 3))
        out.on()
        frame = bytes([10, 20, 30]) * (W * H)
        out.write_rgb(frame)
        self.assertTrue(out.dirty())
        self.assertTrue(out.wait_picked_up(1.0))
        self.assertEqual(self.fpp.last_frame["P5 Panel"], frame)
        self.assertEqual(self.fpp.state["P5 Panel"], 1)

    def test_off_blanks_and_turns_model_off(self):
        out = OverlayOutput(self.fpp.host, "P5 Panel")
        out.open()
        out.on()
        out.write_rgb(bytes([255]) * (W * H * 3))
        out.off()
        self.assertEqual(self.fpp.state["P5 Panel"], 0)
        with open(out.path, "rb") as f:
            f.seek(12)
            self.assertEqual(f.read(W * H * 3), bytes(W * H * 3))

    def test_rgbw_model(self):
        self.fpp.bpp = 4
        out = OverlayOutput(self.fpp.host, "P5 Panel")
        out.open()
        self.assertEqual(out.bpp, 4)
        out.on()
        out.write_rgb(bytes([1, 2, 3]) * (W * H))
        self.assertTrue(out.wait_picked_up(1.0))
        self.assertEqual(self.fpp.last_frame["P5 Panel"][:8], bytes([1, 2, 3, 0, 1, 2, 3, 0]))

    def test_unknown_model(self):
        with self.assertRaisesRegex(OutputError, "not found"):
            OverlayOutput(self.fpp.host, "Nope").open()

    def test_remote_host_is_refused(self):
        with self.assertRaisesRegex(OutputError, "same player"):
            OverlayOutput("192.168.1.50", "P5 Panel").open()

    def test_fpp_unreachable(self):
        with self.assertRaisesRegex(OutputError, "not reachable"):
            OverlayOutput("127.0.0.1:1", "P5 Panel").open()

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can write anything")
    def test_permission_denied_explains_root(self):
        self.fpp.create_buffer("P5 Panel")
        os.chmod(self.fpp.path("P5 Panel"), 0o444)
        with self.assertRaisesRegex(OutputError, "not running as root"):
            OverlayOutput(self.fpp.host, "P5 Panel").open()

    def test_check_notices_fppd_restart(self):
        out = OverlayOutput(self.fpp.host, "P5 Panel")
        out.open()
        self.assertTrue(out.check())
        self.fpp.create_buffer("P5 Panel", force=True)   # new inode
        self.assertFalse(out.check())

    def test_check_notices_model_turned_off(self):
        out = OverlayOutput(self.fpp.host, "P5 Panel")
        out.open()
        out.on()
        self.fpp.state["P5 Panel"] = 0
        self.assertTrue(out.check())
        self.assertFalse(out.model_on)
        out.on()
        self.assertEqual(self.fpp.state["P5 Panel"], 1)

    def test_model_names_that_would_leave_the_buffer_folder_are_refused(self):
        from countdown.output import model_name_problem
        for bad in ("../../etc/passwd", "a/b", "..", "x\\y", "bad\nname", "", "  "):
            self.assertTrue(model_name_problem(bad), repr(bad))
            with self.assertRaises(OutputError):
                OverlayOutput(self.fpp.host, bad)
        for good in ("P5 Panel", "Tree-Matrix_2", "Matrix (front)", "Mega Tree 16x50"):
            self.assertEqual(model_name_problem(good), "", good)

    def test_wrong_frame_size(self):
        out = OverlayOutput(self.fpp.host, "P5 Panel")
        out.open()
        with self.assertRaises(OutputError):
            out.write_rgb(b"\x00" * 10)


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class DaemonLoop(OutputBase):
    """The real drawing loop end to end: config -> frames -> model on/off."""

    @classmethod
    def setUpClass(cls):
        cls.mc = daemon_module()

    def setUp(self):
        super().setUp()
        clear_config()
        self.d = self.mc.CountdownDaemon()
        self.thread = threading.Thread(target=self.d.run, daemon=True)

    def tearDown(self):
        self.d.stop()
        self.thread.join(3)
        super().tearDown()

    def configure(self, when, direction="static", model="P5 Panel"):
        errors = self.d.update_config({
            "global": {"fpp_host": self.fpp.host},
            "countdown": {
                "model": model,
                "target": {"type": "custom", "custom_date": when.strftime("%Y-%m-%d"),
                           "custom_time": when.strftime("%H:%M")},
                "motion": {"direction": direction},
                "text_style": {"font": "", "size": 6, "color": "#ff0000"},
                "number_style": {"font": "", "size": 6, "color": "#00ff00"},
            }})
        self.assertEqual(errors, [])

    def lit(self):
        f = self.fpp.last_frame.get("P5 Panel", b"")
        return any(f)

    def test_draws_then_goes_blank_then_off_on_stop(self):
        self.configure(datetime.now() + timedelta(days=3))
        self.thread.start()
        self.assertTrue(self.fpp.wait_for(lambda: self.fpp.frames["P5 Panel"] >= 5))
        self.assertTrue(self.lit())
        self.assertEqual(self.fpp.state["P5 Panel"], 1)
        st = self.d.get_status()["output"]
        self.assertEqual(st["state"], "drawing")

        # Target reached: blank and model off
        self.configure(datetime.now() - timedelta(minutes=1))
        self.assertTrue(self.fpp.wait_for(lambda: self.d.get_status()["output"]["state"] == "blank"))
        self.assertEqual(self.fpp.state["P5 Panel"], 0)

        # Back to counting, then stopping the daemon turns it off
        self.configure(datetime.now() + timedelta(days=3))
        self.assertTrue(self.fpp.wait_for(lambda: self.fpp.state["P5 Panel"] == 1))
        self.d.stop()
        self.thread.join(3)
        self.assertEqual(self.fpp.state["P5 Panel"], 0)
        self.assertEqual(self.d.get_status()["output"]["state"], "off")

    def test_reports_error_and_recovers(self):
        self.configure(datetime.now() + timedelta(days=3), model="Missing")
        self.thread.start()
        self.assertTrue(self.fpp.wait_for(lambda: self.d.get_status()["output"]["state"] == "error"))
        self.assertIn("not found", self.d.get_status()["output"]["error"])
        self.configure(datetime.now() + timedelta(days=3))
        self.assertTrue(self.fpp.wait_for(lambda: self.fpp.frames["P5 Panel"] >= 3))

    def test_switching_models_turns_the_old_one_off(self):
        self.configure(datetime.now() + timedelta(days=3))
        self.thread.start()
        self.assertTrue(self.fpp.wait_for(lambda: self.fpp.state["P5 Panel"] == 1))
        self.configure(datetime.now() + timedelta(days=3), model="Other")
        self.assertTrue(self.fpp.wait_for(lambda: self.fpp.state["Other"] == 1))
        self.assertEqual(self.fpp.state["P5 Panel"], 0)

    def test_reopens_after_fppd_restart(self):
        self.configure(datetime.now() + timedelta(days=3), direction="R2L")
        self.thread.start()
        self.assertTrue(self.fpp.wait_for(lambda: self.fpp.frames["P5 Panel"] >= 3))
        self.fpp.create_buffer("P5 Panel", force=True)   # fppd restarted: new buffer...
        self.fpp.state["P5 Panel"] = 0                   # ...and the model starts off
        before = self.fpp.frames["P5 Panel"]
        self.assertTrue(self.fpp.wait_for(
            lambda: self.fpp.state["P5 Panel"] == 1 and self.fpp.frames["P5 Panel"] > before + 3))

    def test_disabling_output_turns_model_off(self):
        self.configure(datetime.now() + timedelta(days=3))
        self.thread.start()
        self.assertTrue(self.fpp.wait_for(lambda: self.fpp.state["P5 Panel"] == 1))
        self.d.update_config({**self.d.get_config(), "global": {**self.d.get_config()["global"],
                                                                "enable_output": False}})
        self.assertTrue(self.fpp.wait_for(lambda: self.fpp.state["P5 Panel"] == 0))
        self.assertEqual(self.d.get_status()["output"]["state"], "off")


if __name__ == "__main__":
    unittest.main()
