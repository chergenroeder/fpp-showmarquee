"""Write frames into an FPP pixel-overlay model's overlay buffer.

Protocol (FPP src/overlays/PixelOverlayModel.cpp, confirmed on FPP 10.3):
  PUT /api/overlays/model/<name>/mmap     fppd creates the buffer if needed
  /dev/shm/FPP-Model-Overlay-Buffer-<name>
      uint32 width, uint32 height, uint32 flags (little-endian)
      flags bit 0 = dirty, bits 8-15 = bytes per pixel (0 means 3)
      then width*height*bpp bytes, rows from the top-left, RGB(W)
  set the dirty bit after writing; fppd copies the frame out on its next
  output frame and clears the bit (only while the model is active)
  PUT /api/overlays/model/<name>/state {"State": 1 on | 0 off}

fppd (root) creates the buffer with mode 0644, so this must run as root.
fppd recreates the buffer when it restarts; check() notices and reopens.
"""

import json
import mmap
import os
import struct
import time
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import quote

HEADER = struct.Struct("<III")
SHM_DIR = os.environ.get("MC_SHM_DIR", "/dev/shm")
SHM_PREFIX = "FPP-Model-Overlay-Buffer-"


class OutputError(Exception):
    """Drawing on the model isn't possible right now; the message says why."""


def model_name_problem(model: str) -> str:
    """Why a model name can't be used in the buffer's file path, or "" if it's fine.

    The name becomes part of a /dev/shm path that this root process opens for
    writing, so it must stay one plain file name: no "/", no "..", no control
    characters.
    """
    if not model or not model.strip():
        return "no model name"
    if "/" in model or "\\" in model or model in (".", "..") or ".." in model:
        return "a model name can't contain '/', '\\' or '..'"
    if any(ord(c) < 32 or ord(c) == 127 for c in model):
        return "a model name can't contain control characters"
    if len(model.encode()) > 200:
        return "the model name is too long"
    return ""


def _http(host: str, method: str, path: str, body=None, timeout: float = 2.0):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://{host}{path}", data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except ValueError:
                return r.status, raw.decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as e:  # noqa: BLE001 - connection refused, timeout, ...
        return None, str(e)


class OverlayOutput:
    def __init__(self, host: str, model: str):
        problem = model_name_problem(model)
        if problem:
            raise OutputError(f"invalid overlay model name: {problem}")
        self.host = host
        self.model = model
        self.enc = quote(model, safe="")
        self.path = os.path.join(os.environ.get("MC_SHM_DIR", SHM_DIR), SHM_PREFIX + model)
        self.width = self.height = 0
        self.bpp = 3
        self._mm: Optional[mmap.mmap] = None
        self._ino: Optional[int] = None
        self._on = False

    # ── lifecycle ──
    def open(self):
        """Map the model's overlay buffer. Raises OutputError with a reason."""
        self.close(turn_off=False)
        hostname = self.host.rsplit(":", 1)[0] if self.host.count(":") == 1 else self.host
        if hostname not in ("localhost", "127.0.0.1", "::1", "[::1]"):
            raise OutputError(f"drawing needs the plugin on the same player as the matrix (FPP Host is {self.host})")
        code, info = _http(self.host, "GET", f"/api/overlays/model/{self.enc}")
        if code is None:
            raise OutputError(f"FPP not reachable: {info}")
        if code != 200 or not isinstance(info, dict):
            raise OutputError(f"overlay model '{self.model}' not found in FPP")
        code, resp = _http(self.host, "PUT", f"/api/overlays/model/{self.enc}/mmap")
        if code != 200:
            raise OutputError(f"FPP would not create the overlay buffer for '{self.model}' ({code}: {resp})")
        try:
            fd = os.open(self.path, os.O_RDWR)
        except FileNotFoundError:
            raise OutputError(f"overlay buffer {self.path} not found")
        except PermissionError:
            raise OutputError("permission denied writing the overlay buffer: the daemon is not running as root "
                              "(use Stop then Start on the plugin page, or restart FPP)")
        try:
            st = os.fstat(fd)
            if st.st_size < HEADER.size:
                raise OutputError(f"overlay buffer {self.path} is too small ({st.st_size} bytes)")
            mm = mmap.mmap(fd, st.st_size)
        finally:
            os.close(fd)
        w, h, flags = HEADER.unpack_from(mm, 0)
        bpp = (flags >> 8) & 0xFF or 3
        if w <= 0 or h <= 0 or HEADER.size + w * h * bpp > len(mm) or bpp not in (3, 4):
            mm.close()
            raise OutputError(f"unexpected overlay buffer layout ({w}x{h}, {bpp} bytes/pixel, {st.st_size} bytes)")
        self._mm, self._ino = mm, st.st_ino
        self.width, self.height, self.bpp = w, h, bpp
        self._on = False

    def close(self, turn_off: bool = True):
        if self._mm is not None:
            if turn_off:
                self.off()
            try:
                self._mm.close()
            except (BufferError, ValueError):
                pass
        self._mm = None
        self._ino = None
        self._on = False

    def check(self) -> bool:
        """False if fppd replaced the buffer (restart) or the model's state reset."""
        if self._mm is None:
            return False
        try:
            if os.stat(self.path).st_ino != self._ino:
                return False
        except OSError:
            return False
        if self._on:
            code, info = _http(self.host, "GET", f"/api/overlays/model/{self.enc}")
            if code == 200 and isinstance(info, dict) and int(info.get("isActive", 1) or 0) == 0:
                self._on = False   # something turned it off; on() will turn it back on
        return True

    # ── model state ──
    def on(self):
        if not self._on:
            code, resp = _http(self.host, "PUT", f"/api/overlays/model/{self.enc}/state", {"State": 1})
            if code != 200:
                raise OutputError(f"could not turn on '{self.model}' ({code}: {resp})")
            self._on = True

    def off(self):
        """Blank the buffer and turn the model off (so a sequence shows through)."""
        if self._mm is not None:
            self._write_raw(bytes(self.width * self.height * self.bpp))
        if self._on or self._mm is not None:
            _http(self.host, "PUT", f"/api/overlays/model/{self.enc}/state", {"State": 0})
        self._on = False

    @property
    def model_on(self) -> bool:
        return self._on

    # ── frames ──
    def write_rgb(self, rgb: bytes):
        """Write one packed-RGB frame (width*height*3 bytes) and mark it dirty."""
        if self._mm is None:
            raise OutputError("overlay buffer not open")
        n = self.width * self.height
        if len(rgb) != n * 3:
            raise OutputError(f"frame is {len(rgb)} bytes, expected {n * 3}")
        if self.bpp == 4:
            out = bytearray(n * 4)
            out[0::4] = rgb[0::3]
            out[1::4] = rgb[1::3]
            out[2::4] = rgb[2::3]
            rgb = bytes(out)
        self._write_raw(rgb)

    def _write_raw(self, data: bytes):
        self._mm[HEADER.size:HEADER.size + len(data)] = data
        flags = struct.unpack_from("<I", self._mm, 8)[0]
        struct.pack_into("<I", self._mm, 8, flags | 0x1)

    def dirty(self) -> bool:
        return bool(self._mm is not None and struct.unpack_from("<I", self._mm, 8)[0] & 0x1)

    def wait_picked_up(self, timeout: float) -> bool:
        """Wait until fppd has copied the last frame out (dirty bit cleared)."""
        end = time.monotonic() + timeout
        while self.dirty():
            if time.monotonic() >= end:
                return False
            time.sleep(0.002)
        return True
