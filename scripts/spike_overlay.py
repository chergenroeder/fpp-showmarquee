#!/usr/bin/env python3
"""
Hardware check: can this plugin draw its own frames on an FPP overlay model?

Written for the first hardware test (Phase 0) and kept as a diagnostic: when a
matrix shows nothing, this checks the overlay buffer, colour order, orientation
and frame rate without the rest of the plugin. The moving bar and scrolling
text below test frame timing; the plugin's own pages don't scroll.

Run it ON the FPP player, as root, against a pixel-overlay model you can see:

    sudo python3 spike_overlay.py --model "Matrix"

(fppd runs as root and creates the overlay buffer writable by root only.)

It uses the same path the plugin will:
  1. PUT /api/overlays/model/<name>/mmap   -> fppd creates the overlay buffer
  2. mmap /dev/shm/FPP-Model-Overlay-Buffer-<name>
       header: uint32 width, uint32 height, uint32 flags (little-endian)
               flags bit 0 = dirty, bits 8-15 = bytes per pixel (0 means 3)
       then width*height*bpp bytes, row by row from the top-left, RGB order
  3. write a frame, set the dirty bit; fppd copies it out on its next frame
  4. PUT /api/overlays/model/<name>/state {"State": 1} to show it

What you should see, in order:
  - solid RED, GREEN, BLUE, WHITE for 1.5 s each    (checks colour order)
  - a white corner pixel at the TOP-LEFT for 2 s    (checks orientation)
  - a green bar sweeping left to right              (checks motion + timing)
  - "8 Days to Christmas" scrolling right to left, the number green and the
    text red, drawn with Pillow                    (only if Pillow is installed)
At the end the model is blanked and turned off. Ctrl+C also cleans up.

It prints a short report: buffer size, achieved frame rate, how quickly fppd
picks up each frame, and whether Pillow is available. Paste that report back.
"""

import argparse
import json
import mmap
import os
import struct
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import quote

HEADER = struct.Struct("<III")


def api(host, method, path, body=None, timeout=3.0):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://{host}{path}", data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode(errors="replace")
            try:
                return r.status, json.loads(raw)
            except ValueError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as e:  # noqa: BLE001 - report anything that went wrong
        return None, str(e)


class Overlay:
    def __init__(self, host, model):
        self.host = host
        self.model = model
        self.enc = quote(model, safe="")
        self.mm = None
        self.fd = None

    def open(self):
        code, info = api(self.host, "GET", f"/api/overlays/model/{self.enc}")
        if code != 200 or not isinstance(info, dict):
            sys.exit(f"Model '{self.model}' not found on {self.host} ({code}): {info}")
        print(f"Model info: width={info.get('width')} height={info.get('height')} "
              f"isActive={info.get('isActive')} effectRunning={info.get('effectRunning')}")

        code, resp = api(self.host, "PUT", f"/api/overlays/model/{self.enc}/mmap")
        print(f"PUT .../mmap -> {code} {resp}")
        if code != 200:
            sys.exit("fppd would not allocate the overlay buffer; stop here and report this.")

        path = "/dev/shm/FPP-Model-Overlay-Buffer-" + self.model
        if not os.path.exists(path):
            found = sorted(n for n in os.listdir("/dev/shm") if "FPP" in n)
            sys.exit(f"{path} not found. FPP entries in /dev/shm:\n  " + "\n  ".join(found))
        try:
            self.fd = os.open(path, os.O_RDWR)
        except PermissionError:
            st = os.stat(path)
            sys.exit(f"Permission denied writing {path} (mode {oct(st.st_mode & 0o777)}, owner uid {st.st_uid}).\n"
                     "fppd runs as root and creates it writable by root only: run this with sudo.")
        size = os.fstat(self.fd).st_size
        self.mm = mmap.mmap(self.fd, size)
        self.width, self.height, flags = HEADER.unpack_from(self.mm, 0)
        self.bpp = (flags >> 8) & 0xFF or 3
        self.frame_bytes = self.width * self.height * self.bpp
        print(f"Buffer: {path}")
        print(f"  file size {size} bytes, header width={self.width} height={self.height} "
              f"flags=0x{flags:08x} bpp={self.bpp}")
        if HEADER.size + self.frame_bytes > size:
            sys.exit("Buffer is smaller than width*height*bpp + header; layout differs. Report this.")

    def state(self, value):
        code, resp = api(self.host, "PUT", f"/api/overlays/model/{self.enc}/state", {"State": value})
        if code != 200:
            print(f"  state {value} -> {code} {resp}")

    def dirty(self):
        return HEADER.unpack_from(self.mm, 0)[2] & 0x1

    def write(self, rgb_bytes):
        """Write a packed RGB frame (width*height*3) and mark it dirty."""
        if self.bpp == 3:
            buf = rgb_bytes
        else:  # RGBW models: pad a zero white channel
            out = bytearray(self.width * self.height * self.bpp)
            for i in range(self.width * self.height):
                out[i * self.bpp:i * self.bpp + 3] = rgb_bytes[i * 3:i * 3 + 3]
            buf = bytes(out)
        self.mm[HEADER.size:HEADER.size + self.frame_bytes] = buf
        flags = HEADER.unpack_from(self.mm, 0)[2]
        struct.pack_into("<I", self.mm, 8, flags | 0x1)

    def close(self):
        if self.mm is not None:
            try:
                self.write(bytes(self.width * self.height * 3))
                time.sleep(0.1)
            except Exception:  # noqa: BLE001
                pass
            self.mm.close()
        if self.fd is not None:
            os.close(self.fd)
        self.state(0)


def solid(ov, r, g, b):
    return bytes((r, g, b)) * (ov.width * ov.height)


def run_timed(ov, seconds, fps, make_frame):
    """Write frames at fps for seconds; return (frames, achieved fps, pickup stats ms)."""
    period = 1.0 / fps
    start = time.monotonic()
    nxt = start
    frames = 0
    pickups = []
    while True:
        now = time.monotonic()
        t = now - start
        if t >= seconds:
            break
        ov.write(make_frame(t))
        written = time.monotonic()
        frames += 1
        # How long until fppd clears the dirty bit (= copied our frame out)?
        while ov.dirty() and time.monotonic() - written < period * 3:
            time.sleep(0.001)
        if not ov.dirty():
            pickups.append((time.monotonic() - written) * 1000)
        nxt += period
        delay = nxt - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        else:
            nxt = time.monotonic()
    elapsed = time.monotonic() - start
    return frames, frames / elapsed, pickups


def pillow_frames(ov, pps):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None
    size = max(6, min(ov.height - 1, 12))
    font = None
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(path):
            font = ImageFont.truetype(path, size)
            break
    if font is None:
        font = ImageFont.load_default()
    num, txt = "8 Days ", "to Christmas"
    nw = int(ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(num, font=font))
    tw = int(ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(txt, font=font))
    strip = Image.new("RGB", (nw + tw, ov.height))
    d = ImageDraw.Draw(strip)
    y = (ov.height - size) // 2 - 1
    d.text((0, y), num, font=font, fill=(0, 255, 0))
    d.text((nw, y), txt, font=font, fill=(255, 0, 0))
    total = ov.width + strip.width

    def frame(t):
        x = ov.width - int(t * pps) % total
        img = Image.new("RGB", (ov.width, ov.height))
        img.paste(strip, (x, 0))
        return img.tobytes()

    return frame


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", required=True, help="Pixel overlay model name, exactly as in FPP")
    p.add_argument("--host", default="localhost", help="FPP host (default localhost)")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--pps", type=int, default=15, help="scroll speed, pixels per second")
    p.add_argument("--seconds", type=float, default=8, help="length of each motion test")
    a = p.parse_args()

    if not os.path.isdir("/dev/shm"):
        sys.exit("No /dev/shm here: run this on the FPP player itself.")

    _, ver = api(a.host, "GET", "/api/fppd/version")
    print(f"FPP: {ver.get('version') if isinstance(ver, dict) else ver}")

    ov = Overlay(a.host, a.model)
    ov.open()
    report = {}
    try:
        ov.state(1)
        for name, rgb in (("RED", (255, 0, 0)), ("GREEN", (0, 255, 0)),
                          ("BLUE", (0, 0, 255)), ("WHITE", (255, 255, 255))):
            print(f"Showing solid {name}")
            ov.write(solid(ov, *rgb))
            time.sleep(1.5)

        print("Showing a white pixel at the TOP-LEFT corner")
        corner = bytearray(ov.width * ov.height * 3)
        corner[0:3] = b"\xff\xff\xff"
        ov.write(bytes(corner))
        time.sleep(2)

        print(f"Sweeping a green bar left to right at {a.fps} fps")
        bar_w = max(1, ov.width // 16)

        def bar(t):
            x0 = int(t * ov.width / a.seconds)
            row = bytearray(ov.width * 3)
            for x in range(x0, min(ov.width, x0 + bar_w)):
                row[x * 3 + 1] = 255
            return bytes(row) * ov.height

        frames, fps, pick = run_timed(ov, a.seconds, a.fps, bar)
        report["bar"] = (frames, fps, pick)

        pf = pillow_frames(ov, a.pps)
        if pf is None:
            print("Pillow NOT installed: skipping the text test")
            report["pillow"] = None
        else:
            import PIL
            print(f"Scrolling Pillow text right to left at {a.pps} px/s")
            frames, fps, pick = run_timed(ov, a.seconds * 2, a.fps, pf)
            report["pillow"] = PIL.__version__
            report["text"] = (frames, fps, pick)
    except KeyboardInterrupt:
        print("Interrupted")
    finally:
        ov.close()

    print("\n==== Phase 0 report (paste this back) ====")
    print(f"model={a.model!r} size={ov.width}x{ov.height} bpp={ov.bpp} target_fps={a.fps}")
    for key in ("bar", "text"):
        if key in report:
            frames, fps, pick = report[key]
            if pick:
                pick.sort()
                med = pick[len(pick) // 2]
                print(f"{key}: {frames} frames, {fps:.1f} fps achieved, fppd picked up "
                      f"{len(pick)}/{frames} frames, median {med:.1f} ms, worst {pick[-1]:.1f} ms")
            else:
                print(f"{key}: {frames} frames, {fps:.1f} fps, fppd NEVER cleared the dirty bit")
    print(f"pillow={report.get('pillow')}")
    try:
        load = os.getloadavg()
        print(f"loadavg={load[0]:.2f} {load[1]:.2f} {load[2]:.2f}")
    except OSError:
        pass
    print("Also note: did the colours, corner and motion look right on the matrix?")


if __name__ == "__main__":
    main()
