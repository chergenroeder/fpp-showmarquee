"""A stand-in for fppd's overlay API and buffer, for tests on any machine.

Serves GET /api/overlays/model/<name>, PUT .../mmap, PUT .../state, and runs
an "output thread" that, like fppd, copies a dirty buffer out every 50 ms
while the model is on and clears the dirty bit.
"""

import json
import os
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

HEADER = struct.Struct("<III")
PREFIX = "FPP-Model-Overlay-Buffer-"


class FakeFPP:
    def __init__(self, shm_dir, models, bpp=3, period=0.05):
        self.shm_dir = shm_dir
        self.models = dict(models)          # name -> (width, height)
        self.bpp = bpp
        self.period = period
        self.state = {name: 0 for name in models}
        self.state_log = []                  # (name, state) in order
        self.frames = {name: 0 for name in models}
        self.last_frame = {}
        self._stop = threading.Event()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, data):
                body = json.dumps(data).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _model(self):
                parts = self.path.split("/")
                # /api/overlays/model/<name>[/<cmd>]
                if len(parts) < 5 or parts[1:4] != ["api", "overlays", "model"]:
                    return None, None
                name = unquote(parts[4])
                return (name if name in fake.models else None), (parts[5] if len(parts) > 5 else "")

            def do_GET(self):
                name, cmd = self._model()
                if name is None or cmd:
                    return self._json(404, {"error": "Model Not found"})
                w, h = fake.models[name]
                self._json(200, {"Name": name, "width": w, "height": h,
                                 "isActive": fake.state[name], "effectRunning": False})

            def do_PUT(self):
                name, cmd = self._model()
                length = int(self.headers.get("Content-Length", 0) or 0)
                body = json.loads(self.rfile.read(length)) if length else {}
                if name is None:
                    return self._json(404, {"error": "Model Not found"})
                if cmd == "mmap":
                    fake.create_buffer(name)
                    return self._json(200, {"Status": "OK", "Message": ""})
                if cmd == "state":
                    fake.state[name] = int(body["State"])
                    fake.state_log.append((name, int(body["State"])))
                    return self._json(200, {"Status": "OK", "Message": ""})
                self._json(404, {"error": "Model Command Not found"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.host = f"127.0.0.1:{self.server.server_address[1]}"

    def path(self, name):
        return os.path.join(self.shm_dir, PREFIX + name)

    def create_buffer(self, name, force=False):
        p = self.path(name)
        if os.path.exists(p) and not force:
            return
        w, h = self.models[name]
        tmp = p + ".new"
        with open(tmp, "wb") as f:
            f.write(HEADER.pack(w, h, self.bpp << 8) + bytes(w * h * self.bpp + 4))
        os.replace(tmp, p)   # a new inode, as when fppd restarts

    def _output_loop(self):
        while not self._stop.wait(self.period):
            for name in self.models:
                p = self.path(name)
                if self.state[name] == 0 or not os.path.exists(p):
                    continue
                with open(p, "r+b") as f:
                    w, h, flags = HEADER.unpack(f.read(HEADER.size))
                    if flags & 1:
                        self.last_frame[name] = f.read(w * h * self.bpp)
                        self.frames[name] += 1
                        f.seek(8)
                        f.write(struct.pack("<I", flags & ~1))

    def start(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        threading.Thread(target=self._output_loop, daemon=True).start()
        return self

    def stop(self):
        self._stop.set()
        self.server.shutdown()
        self.server.server_close()

    def wait_for(self, cond, timeout=3.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if cond():
                return True
            time.sleep(0.02)
        return False
