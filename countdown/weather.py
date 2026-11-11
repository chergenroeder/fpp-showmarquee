"""Weather from a WeatherFlow Tempest station, via the hub's local UDP broadcast.

The hub broadcasts JSON on UDP port 50222 (WeatherFlow UDP reference v143):
  rapid_wind  ~every 3 s   ob = [epoch, wind m/s, direction deg]
  obs_st      ~every 60 s  obs[0] = [epoch, lull, avg, gust (m/s), direction deg, interval s,
                                     pressure mb, air temp C, humidity %, ...]
TempestListener keeps the latest temperature, wind and gust, each with the time
it arrived. Some machines receive every packet twice (two network interfaces);
repeats of the same (sensor, type, epoch) are dropped.

weather_messages() turns a reading into the temperature and wind messages, in
F and mph, skipping anything older than the stale limit.
"""

import json
import math
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .message import NUMBER, TEXT, Message

TEMPEST_PORT = 50222
COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


def c_to_f(c: float) -> float:
    return c * 9 / 5 + 32


def ms_to_mph(ms: float) -> float:
    return ms * 2.2369363


def compass(deg: float) -> str:
    return COMPASS[int((deg % 360) / 22.5 + 0.5) % 16]


@dataclass
class Reading:
    """Latest values; *_at are time.monotonic() when the value arrived (None = never)."""
    temp_c: Optional[float] = None
    temp_at: Optional[float] = None
    wind_ms: Optional[float] = None
    wind_dir: Optional[float] = None
    wind_at: Optional[float] = None
    gust_ms: Optional[float] = None
    gust_at: Optional[float] = None
    humidity: Optional[float] = None
    hub: str = ""
    device: str = ""
    source: str = ""
    packets: Dict[str, int] = field(default_factory=dict)
    last_packet_at: Optional[float] = None


def _num(v) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


class TempestListener:
    """Listens for Tempest UDP broadcasts on a background thread."""

    def __init__(self, port: int = TEMPEST_PORT, device: str = "", bind: str = ""):
        self.port = int(port)
        self.device = str(device or "").strip().upper()   # only this sensor (ST-...); "" = any
        self.bind = bind
        self.error = ""
        self._reading = Reading()
        self._seen: Dict[Tuple[str, str], float] = {}     # (serial, type) -> last epoch
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None

    # ── lifecycle ──
    def start(self):
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="tempest", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2)
        self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _open(self) -> socket.socket:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):          # share the port with other listeners
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        s.bind((self.bind, self.port))
        s.settimeout(0.5)
        return s

    def _run(self):
        while not self._stop.is_set():
            try:
                self._sock = self._open()
                self.error = ""
            except OSError as e:
                self.error = f"cannot listen on UDP port {self.port}: {e}"
                self._stop.wait(5)
                continue
            try:
                while not self._stop.is_set():
                    try:
                        data, (ip, _) = self._sock.recvfrom(4096)
                    except socket.timeout:
                        continue
                    self.handle(data, ip)
            except OSError as e:
                self.error = f"UDP receive failed: {e}"
                self._stop.wait(2)
            finally:
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None

    # ── packets ──
    def handle(self, data: bytes, source: str = "", now: Optional[float] = None) -> bool:
        """Apply one packet. Returns True if it changed the reading."""
        now = time.monotonic() if now is None else now
        try:
            msg = json.loads(data.decode("utf-8", "replace"))
        except ValueError:
            return False
        if not isinstance(msg, dict):
            return False
        kind = str(msg.get("type") or "")
        serial = str(msg.get("serial_number") or "")
        if kind not in ("rapid_wind", "obs_st"):
            with self._lock:
                self._count(kind)
            return False
        if self.device and serial.upper() != self.device:
            return False
        ob = msg.get("ob") if kind == "rapid_wind" else (msg.get("obs") or [None])[0]
        if not isinstance(ob, list) or not ob:
            return False
        epoch = _num(ob[0])
        with self._lock:
            self._count(kind)
            key = (serial, kind)
            if epoch is not None and self._seen.get(key) is not None and epoch <= self._seen[key]:
                return False        # a repeat (or an older packet)
            if epoch is not None:
                self._seen[key] = epoch
            r = self._reading
            r.hub = str(msg.get("hub_sn") or r.hub)
            r.device = serial or r.device
            r.source = source or r.source
            r.last_packet_at = now
            changed = False
            if kind == "rapid_wind" and len(ob) >= 3:
                speed, direction = _num(ob[1]), _num(ob[2])
                if speed is not None:
                    r.wind_ms, r.wind_dir, r.wind_at = speed, direction, now
                    changed = True
            elif kind == "obs_st":
                get = lambda i: _num(ob[i]) if len(ob) > i else None  # noqa: E731
                if get(7) is not None:
                    r.temp_c, r.temp_at = get(7), now
                    changed = True
                if get(3) is not None:
                    r.gust_ms, r.gust_at = get(3), now
                    changed = True
                if get(8) is not None:
                    r.humidity = get(8)
                # Fall back to the minute average for wind if rapid_wind isn't arriving
                if get(2) is not None and (r.wind_at is None or now - r.wind_at > 30):
                    r.wind_ms, r.wind_dir, r.wind_at = get(2), get(4), now
                    changed = True
            return changed

    def _count(self, kind: str):
        self._reading.packets[kind] = self._reading.packets.get(kind, 0) + 1

    def reading(self) -> Reading:
        with self._lock:
            r = self._reading
            return Reading(**{**r.__dict__, "packets": dict(r.packets)})


# ── Messages ──────────────────────────────────────────────────────────────────

DEFAULTS = {
    "stale_minutes": 5,
    "temperature": {"enabled": True, "label": "Temp"},
    "wind": {"enabled": True, "label": "Wind", "direction": True, "gusts": True,
             "gust_label": "gusts", "gust_min_diff_mph": 5, "calm_text": "Calm"},
}


def _fresh(at: Optional[float], now: float, stale_s: float) -> bool:
    return at is not None and now - at <= stale_s


def temperature_message(r: Reading, cfg: dict, now: float) -> Message:
    t = {**DEFAULTS["temperature"], **(cfg.get("temperature") or {})}
    stale_s = float(cfg.get("stale_minutes", DEFAULTS["stale_minutes"])) * 60
    if not t.get("enabled") or r.temp_c is None or not _fresh(r.temp_at, now, stale_s):
        return Message(())
    value = f"{round(c_to_f(r.temp_c))}°F"
    label = str(t.get("label") or "").strip()
    pieces = ((TEXT, label), (NUMBER, value)) if label else ((NUMBER, value),)
    return Message(pieces)


def wind_message(r: Reading, cfg: dict, now: float) -> Message:
    w = {**DEFAULTS["wind"], **(cfg.get("wind") or {})}
    stale_s = float(cfg.get("stale_minutes", DEFAULTS["stale_minutes"])) * 60
    if not w.get("enabled") or r.wind_ms is None or not _fresh(r.wind_at, now, stale_s):
        return Message(())
    mph = ms_to_mph(r.wind_ms)
    label = str(w.get("label") or "").strip()
    first: List[Tuple[str, str]] = [(TEXT, label)] if label else []
    if mph < 1:
        first.append((NUMBER, str(w.get("calm_text") or "Calm").strip() or "Calm"))
    else:
        speed = f"{round(mph)} mph"
        if w.get("direction") and r.wind_dir is not None:
            speed += " " + compass(r.wind_dir)
        first.append((NUMBER, speed))
    second: List[Tuple[str, str]] = []
    if (w.get("gusts") and r.gust_ms is not None and _fresh(r.gust_at, now, stale_s)):
        gust = ms_to_mph(r.gust_ms)
        if gust >= 1 and gust - mph >= float(w.get("gust_min_diff_mph", 5)):
            glabel = str(w.get("gust_label") or "").strip()
            second = ([(TEXT, glabel)] if glabel else []) + [(NUMBER, str(round(gust)))]
    pieces = tuple(first + second)
    lines = None
    if second:   # two-line layout: "Wind 8 mph NW" over "gusts 15"
        lines = (tuple(range(len(first))), tuple(range(len(first), len(pieces))))
    elif len(pieces) == 2:
        lines = ((0, 1),)   # "Wind Calm" stays on one line
    return Message(pieces, lines)


def weather_messages(r: Reading, cfg: dict, now: Optional[float] = None) -> Dict[str, Message]:
    now = time.monotonic() if now is None else now
    return {"temperature": temperature_message(r, cfg, now), "wind": wind_message(r, cfg, now)}
