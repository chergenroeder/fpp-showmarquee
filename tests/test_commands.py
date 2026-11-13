"""FPP command scripts and the state/target endpoints they call.

Runs the real API handler on a free port and the real commands/*.sh scripts
against it (bash and curl needed). Run: python3 -m unittest discover -s tests
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from daemon_env import clear_config, daemon_module  # noqa: E402

COMMANDS = os.path.join(HERE, "..", "commands")
HAVE_TOOLS = bool(shutil.which("bash") and shutil.which("curl"))


class CommandsBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mc = daemon_module()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), cls.mc.ApiHandler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}/api/plugin/showmarquee"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        clear_config()
        self.mc._daemon = self.mc.CountdownDaemon()   # the API handler talks to this one

    def tearDown(self):
        self.mc._daemon = None

    def post(self, route, body):
        req = urllib.request.Request(f"{self.base}/{route}", data=json.dumps(body).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def run_cmd(self, script, *args):
        env = dict(os.environ, MC_API=self.base)
        return subprocess.run(["bash", os.path.join(COMMANDS, script), *args],
                              env=env, capture_output=True, text=True, timeout=10)

    @property
    def cd(self):
        return self.mc._daemon.get_config()["countdown"]


class Endpoints(CommandsBase):

    def test_state_on_off_toggle(self):
        self.assertEqual(self.post("state", {"enabled": False}), (200, {"enabled": False}))
        self.assertFalse(self.cd["enabled"])
        self.assertEqual(self.post("state", {"enabled": "toggle"}), (200, {"enabled": True}))
        self.assertTrue(self.cd["enabled"])
        code, body = self.post("state", {"enabled": "maybe"})
        self.assertEqual(code, 400)

    def test_state_is_saved(self):
        self.post("state", {"enabled": False})
        self.assertFalse(self.mc.load_config()["countdown"]["enabled"])

    def test_output_on_off_toggle_and_saved(self):
        out = lambda: self.mc._daemon.get_config()["global"]["enable_output"]  # noqa: E731
        self.assertEqual(self.post("output", {"enable_output": False}), (200, {"enable_output": False}))
        self.assertFalse(self.mc.load_config()["global"]["enable_output"])
        self.assertEqual(self.post("output", {"enable_output": "toggle"}), (200, {"enable_output": True}))
        self.assertTrue(out())
        self.assertEqual(self.post("output", {"enable_output": "maybe"})[0], 400)

    def test_partial_config_post_keeps_other_settings(self):
        self.assertEqual(self.post("config", {"countdown": {"model": "P5 Panel"}})[0], 200)
        self.assertEqual(self.post("config", {"countdown": {"layout": {"number_position": "last"}}})[0], 200)
        self.assertEqual(self.cd["model"], "P5 Panel")
        self.assertEqual(self.cd["layout"]["number_position"], "last")
        self.assertEqual(self.cd["layout"]["connector_last"], "in")   # default kept

    def test_bad_model_name_is_rejected_on_save(self):
        code, body = self.post("config", {"countdown": {"model": "../../etc/passwd"}})
        self.assertEqual(code, 400)
        self.assertIn("countdown.model", " ".join(body["details"]))
        self.assertEqual(self.cd["model"], "")

    def test_target_switch_keeps_custom_date(self):
        self.post("target", {"type": "custom", "date": "2027-03-14", "time": "18:30", "name": "Opening Night"})
        self.post("target", {"type": "christmas"})
        t = self.cd["target"]
        self.assertEqual((t["type"], t["custom_date"], t["custom_time"]), ("christmas", "2027-03-14", "18:30"))
        code, body = self.post("target", {"type": "custom"})
        self.assertEqual(code, 200)
        self.assertEqual(self.cd["target"]["event_name"]["custom"], "Opening Night")

    def test_target_names_and_repeat(self):
        self.assertEqual(self.post("target", {"type": "New Year's Day"})[0], 200)
        self.assertEqual(self.cd["target"]["type"], "newyear")
        self.post("target", {"type": "custom", "date": "2020-06-15", "repeat": "true"})
        self.assertTrue(self.cd["target"]["custom_repeat_yearly"])
        self.post("target", {"type": "custom", "repeat": False})
        self.assertFalse(self.cd["target"]["custom_repeat_yearly"])

    def test_target_errors_save_nothing(self):
        self.assertEqual(self.post("target", {"type": "easter"})[0], 400)
        code, body = self.post("target", {"type": "custom", "date": "14/03/2027"})
        self.assertEqual(code, 400)
        self.assertIn("custom_date", body["error"])
        self.assertEqual(self.cd["target"]["type"], "christmas")
        code, _ = self.post("target", {"type": "custom"})   # no date saved yet
        self.assertEqual(code, 400)


@unittest.skipUnless(HAVE_TOOLS, "bash and curl needed")
class Scripts(CommandsBase):

    def test_state_script(self):
        r = self.run_cmd("state.sh", "Off")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.cd["enabled"])
        self.run_cmd("state.sh", "Toggle")
        self.assertTrue(self.cd["enabled"])

    def test_output_script(self):
        r = self.run_cmd("output.sh", "Off")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.mc._daemon.get_config()["global"]["enable_output"])
        self.run_cmd("output.sh", "Toggle")
        self.assertTrue(self.mc._daemon.get_config()["global"]["enable_output"])

    def test_state_script_rejects_bad_value(self):
        r = self.run_cmd("state.sh", "Sideways")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("On, Off or Toggle", r.stderr)

    def test_set_target_custom_with_all_fields(self):
        r = self.run_cmd("set_target.sh", "Custom", "2027-03-14", "18:30", 'Bob\'s "Big" Night', "true")
        self.assertEqual(r.returncode, 0, r.stderr)
        t = self.cd["target"]
        self.assertEqual((t["type"], t["custom_date"], t["custom_time"], t["custom_repeat_yearly"]),
                         ("custom", "2027-03-14", "18:30", True))
        self.assertEqual(t["event_name"]["custom"], 'Bob\'s "Big" Night')

    def test_set_target_fixed_holidays_with_empty_optional_args(self):
        # fppd passes optional args left blank as empty strings
        r = self.run_cmd("set_target.sh", "New Year's Day", "", "", "", "")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.cd["target"]["type"], "newyear")
        self.run_cmd("set_target.sh", "Christmas")
        self.assertEqual(self.cd["target"]["type"], "christmas")

    def test_set_target_reports_daemon_error(self):
        r = self.run_cmd("set_target.sh", "Custom", "not-a-date")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("custom_date", r.stderr)

    def test_daemon_not_running(self):
        env = dict(os.environ, MC_API="http://127.0.0.1:1/api/plugin/showmarquee")
        r = subprocess.run(["bash", os.path.join(COMMANDS, "state.sh"), "On"], env=env,
                           capture_output=True, text=True, timeout=10)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("daemon not running", r.stderr)

    def test_daemon_lib_loads_fpp_common_under_set_eu(self):
        import tempfile
        fpp = tempfile.mkdtemp()
        os.makedirs(os.path.join(fpp, "scripts"))
        with open(os.path.join(fpp, "scripts", "common"), "w") as f:
            # like FPP's: reads unset variables and runs a failing command
            f.write('X="$NOT_SET_ANYWHERE"\nfalse\nMEDIADIR=/srv/media\nLOGDIR=/srv/media/logs\n')
        lib = os.path.join(HERE, "..", "scripts", "daemon_lib.sh")
        r = subprocess.run(["bash", "-c", f'set -euo pipefail; . "{lib}"; echo "$MC_MEDIADIR|$MC_LOGDIR|$-"'],
                           env=dict(os.environ, FPPDIR=fpp), capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        media, logs, flags = r.stdout.strip().split("|")
        self.assertEqual((media, logs), ("/srv/media", "/srv/media/logs"))
        self.assertIn("e", flags)
        self.assertIn("u", flags)
        shutil.rmtree(fpp)

    def test_descriptions_match_scripts(self):
        with open(os.path.join(COMMANDS, "descriptions.json")) as f:
            for cmd in json.load(f):
                self.assertTrue(os.access(os.path.join(COMMANDS, cmd["script"]), os.X_OK), cmd["script"])
                self.assertTrue(cmd["name"].startswith("Show Marquee - "))

    def test_no_sudo_in_shipped_scripts(self):
        root = os.path.join(HERE, "..")
        for folder in ("commands", "scripts"):
            for name in os.listdir(os.path.join(root, folder)):
                with open(os.path.join(root, folder, name)) as f:
                    self.assertNotIn("sudo", f.read(), f"{folder}/{name}")
        for name in ("api.php", "callbacks.sh", "showmarquee.py"):
            with open(os.path.join(root, name)) as f:
                self.assertNotIn("sudo", f.read(), name)

    def run_uninstall(self, reinstall=None):
        """Run fpp_uninstall.sh against a scratch media folder; return what's left."""
        import tempfile
        media = tempfile.mkdtemp()
        os.makedirs(os.path.join(media, "config"))
        os.makedirs(os.path.join(media, "plugindata", "fpp-showmarquee"))
        open(os.path.join(media, "config", "plugin.fpp-showmarquee.json"), "w").write("{}")
        open(os.path.join(media, "config", "plugin.other-plugin.json"), "w").write("{}")
        open(os.path.join(media, "plugindata", "fpp-showmarquee", "location.json"), "w").write("{}")
        env = dict(os.environ, MEDIADIR=media, FPPDIR=os.path.join(media, "no-fpp-here"))
        env.pop("FPP_PLUGIN_REINSTALL", None)
        if reinstall is not None:
            env["FPP_PLUGIN_REINSTALL"] = reinstall
        script = os.path.join(HERE, "..", "scripts", "fpp_uninstall.sh")
        codes = [subprocess.run(["bash", script], env=env, capture_output=True, text=True, timeout=20).returncode
                 for _ in range(2)]                                      # safe to run twice
        left = sorted(os.path.relpath(os.path.join(d, f), media) for d, _, fs in os.walk(media) for f in fs)
        shutil.rmtree(media)
        return codes, left

    def test_uninstall_removes_settings_and_data(self):
        codes, left = self.run_uninstall()
        self.assertEqual(codes, [0, 0])
        self.assertEqual(left, ["config/plugin.other-plugin.json"])      # only another plugin's file

    def test_reinstall_keeps_them(self):
        codes, left = self.run_uninstall("1")
        self.assertEqual(codes, [0, 0])
        self.assertIn("config/plugin.fpp-showmarquee.json", left)
        self.assertIn("plugindata/fpp-showmarquee/location.json", left)


if __name__ == "__main__":
    unittest.main()
