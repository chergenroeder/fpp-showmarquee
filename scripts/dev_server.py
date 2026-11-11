#!/usr/bin/env python3
"""Work on the settings page without an FPP player.

Starts a fake fppd (tests/fake_fpp.py, two models), the real daemon against it,
and a page server that wraps matrixcountdown.html in Bootstrap the way FPP does
and passes /api/plugin/fpp-matrixcountdown/* through to the daemon.

    .venv/bin/python scripts/dev_server.py
    open http://127.0.0.1:8765/            (add ?theme=dark for dark mode)

Needs Pillow (.venv) and network access for the Bootstrap stylesheet.
"""
import json
import shutil
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "tests"))
from fake_fpp import FakeFPP  # noqa: E402

work = tempfile.mkdtemp(prefix="mc-harness-")
shm = os.path.join(work, "shm"); os.makedirs(shm)
fpp = FakeFPP(shm, {"P5 Panel": (192, 96), "Tree Matrix": (64, 32)}).start()

DAEMON_PORT = 32396
env = dict(os.environ, MEDIADIR=os.path.join(work, "media"), LOGDIR=os.path.join(work, "logs"),
           MC_SHM_DIR=shm, MC_API_PORT=str(DAEMON_PORT))
os.makedirs(os.path.join(work, "media", "config"))
with open(os.path.join(work, "media", "config", "plugin.fpp-matrixcountdown.json"), "w") as f:
    json.dump({"global": {"fpp_host": fpp.host}, "countdown": {"model": "P5 Panel"}}, f)
# Some system fonts (macOS) so the font list isn't empty
fonts = os.path.join(work, "media", "fonts"); os.makedirs(fonts)
for name in ("Arial Bold.ttf", "Arial.ttf", "Verdana Bold.ttf", "Courier New Bold.ttf"):
    src = os.path.join("/System/Library/Fonts/Supplemental", name)
    if os.path.exists(src):
        shutil.copy(src, os.path.join(fonts, name.replace(" ", "")))
daemon = subprocess.Popen([os.path.join(PROJECT, ".venv/bin/python"), os.path.join(PROJECT, "matrixcountdown.py")], env=env)
time.sleep(1.5)

SHELL = """<!doctype html><html data-bs-theme="{theme}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
<title>Matrix Countdown (dev)</title></head><body>{page}</body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _proxy(self, method):
        if self.path.startswith("/api/plugin/fpp-matrixcountdown/"):
            url = f"http://127.0.0.1:{DAEMON_PORT}/api/plugin/matrixcountdown/" + self.path.split("/", 4)[4]
            n = int(self.headers.get("Content-Length", 0) or 0)
            req = urllib.request.Request(url, data=self.rfile.read(n) if n else None, method=method)
            req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    body, code = r.read(), 200
            except urllib.error.HTTPError as e:
                body, code = e.read(), 200   # FPP's PHP proxy passes error bodies on as 200
            except Exception:
                body, code = json.dumps({"error": "matrixcountdown daemon not running"}).encode(), 200
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return True
        return False

    def do_GET(self):
        if self._proxy("GET"):
            return
        if self.path.split("?")[0] == "/":
            theme = "dark" if "theme=dark" in self.path else "light"
            with open(os.path.join(PROJECT, "matrixcountdown.html")) as f:
                page = SHELL.format(theme=theme, page=f.read())
            body = page.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/_fake/state":
            body = json.dumps({"state": fpp.state, "frames": fpp.frames}).encode()
            self.send_response(200); self.end_headers(); self.wfile.write(body)
            return
        self.send_response(404); self.end_headers()

    def do_POST(self):
        if not self._proxy("POST"):
            self.send_response(404); self.end_headers()


try:
    print("harness on http://127.0.0.1:8765/ ; fake fpp", fpp.host, "; work", work, flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8765), H).serve_forever()
finally:
    daemon.terminate()
    fpp.stop()
