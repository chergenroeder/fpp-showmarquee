"""Weather from Open-Meteo (internet) or a WeatherFlow Tempest station (local UDP).

Open-Meteo: OpenMeteoPoller fetches the current conditions for one location
over HTTPS every 15 minutes, just after each quarter hour, when the service
updates. No account or key. Only the latitude and longitude (rounded to about
1 km) are sent.

Tempest: the hub's local UDP broadcast.

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
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
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
    max_age_s: Optional[float] = None   # the source's own stale limit (overrides stale_minutes)


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


# ── Open-Meteo ────────────────────────────────────────────────────────────────

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_FIELDS = ("temperature_2m", "relative_humidity_2m", "wind_speed_10m",
                     "wind_direction_10m", "wind_gusts_10m")
USER_AGENT = "fpp-matrixcountdown (FPP plugin)"


@dataclass(frozen=True)
class Location:
    lat: float
    lon: float
    origin: str          # "fpp" (FPP's own settings) or "plugin" (set in this plugin)

    @property
    def text(self) -> str:
        return f"{self.lat:.2f}, {self.lon:.2f}"


def parse_coord(value, low: float, high: float) -> Optional[float]:
    """A latitude/longitude from a number or a string, or None if missing/out of range."""
    if isinstance(value, bool):
        return None
    try:
        v = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and low <= v <= high else None


def make_location(lat, lon, origin: str) -> Optional[Location]:
    """A Location rounded to 2 decimals (about 1 km), or None if not usable.

    0, 0 counts as unset: FPP shows it when no location was entered, and it
    is in the sea.
    """
    la, lo = parse_coord(lat, -90, 90), parse_coord(lon, -180, 180)
    if la is None or lo is None or (la == 0 and lo == 0):
        return None
    return Location(round(la, 2), round(lo, 2), origin)


NO_LOCATION = ("no location: set Latitude and Longitude in FPP (Settings \u2192 General), "
               "or turn on \u201cUse a different location\u201d here")


class OpenMeteoError(Exception):
    pass


def fetch_open_meteo(loc: Location, url: str = OPEN_METEO_URL, timeout: float = 10.0,
                     context: Optional[ssl.SSLContext] = None) -> dict:
    """GET the current conditions. Raises OpenMeteoError with a message for the page."""
    query = urllib.parse.urlencode({
        "latitude": f"{loc.lat:.2f}", "longitude": f"{loc.lon:.2f}",
        "current": ",".join(OPEN_METEO_FIELDS),
        "wind_speed_unit": "ms", "timeformat": "unixtime",
    })
    req = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": USER_AGENT})
    host = urllib.parse.urlsplit(url).hostname or url
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            body = resp.read(65536)
    except urllib.error.HTTPError as e:
        reason = ""
        try:
            reason = str(json.loads(e.read(4096)).get("reason") or "")
        except Exception:
            pass
        raise OpenMeteoError(f"Open-Meteo answered HTTP {e.code}" + (f": {reason}" if reason else ""))
    except urllib.error.URLError as e:
        r = e.reason
        if isinstance(r, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(r):
            raise OpenMeteoError("Open-Meteo's certificate couldn't be checked: check this player's "
                                 "date and time (FPP Settings \u2192 Time)")
        if isinstance(r, socket.gaierror):
            raise OpenMeteoError(f"no internet: can't look up {host} (check the player's network and DNS)")
        if isinstance(r, (socket.timeout, TimeoutError)):
            raise OpenMeteoError("Open-Meteo didn't answer within %d s" % timeout)
        raise OpenMeteoError(f"can't reach Open-Meteo: {r}")
    except (socket.timeout, TimeoutError):
        raise OpenMeteoError("Open-Meteo didn't answer within %d s" % timeout)
    except ssl.SSLError as e:
        raise OpenMeteoError(f"secure connection to Open-Meteo failed ({e.reason or e}): "
                             "check this player's date and time (FPP Settings \u2192 Time)")
    except OSError as e:
        raise OpenMeteoError(f"can't reach Open-Meteo: {e}")
    try:
        data = json.loads(body.decode("utf-8"))
    except ValueError:
        raise OpenMeteoError("Open-Meteo sent a reply that couldn't be read")
    if not isinstance(data, dict) or not isinstance(data.get("current"), dict):
        raise OpenMeteoError("Open-Meteo's reply had no current conditions")
    return data


class OpenMeteoPoller:
    """Fetches Open-Meteo's current conditions on a background thread.

    Same interface as TempestListener (start, stop, running, error, reading()).
    Fetches at once, then just after each quarter hour (:01, :16, :31, :46).
    A failed fetch keeps the last reading until it is MAX_AGE_S old and is
    retried after 1, 2, 4, 8 minutes, then at the normal times.
    """

    REFRESH_S = 900          # Open-Meteo's current values update every 15 min
    OFFSET_S = 60            # a minute after the quarter hour
    MAX_AGE_S = 3 * 900      # stale after 45 min
    RETRY_S = (60, 120, 240, 480)
    TIMEOUT_S = 10.0

    def __init__(self, location_fn, fetch=fetch_open_meteo, url: str = OPEN_METEO_URL,
                 wall=time.time, mono=time.monotonic):
        self.location_fn = location_fn      # () -> Location or None
        self._fetch = fetch
        self.url = url
        self._wall, self._mono = wall, mono
        self.error = ""
        self.location: Optional[Location] = None
        self.last_fetch_at: Optional[float] = None    # monotonic, last success
        self.next_fetch_at: Optional[float] = None    # monotonic
        self.fetches = 0
        self.failures = 0
        self._reading = Reading(source="open-meteo", max_age_s=self.MAX_AGE_S)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── lifecycle ──
    def start(self):
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="open-meteo", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            # Don't hold up the caller (the drawing loop) for a fetch in flight;
            # the thread checks _stop when the fetch returns and exits.
            self._thread.join(1)
        self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def wake(self):
        """Settings changed: fetch now if the location is different."""
        self._wake.set()

    # ── schedule ──
    def delay_to_next(self) -> float:
        """Seconds until the next quarter hour plus OFFSET_S (by the wall clock)."""
        phase = (self._wall() - self.OFFSET_S) % self.REFRESH_S
        delay = self.REFRESH_S - phase
        return delay if delay >= 5 else delay + self.REFRESH_S

    def next_delay(self, ok: bool) -> float:
        """Seconds to the next fetch: the next quarter hour, or a retry after a failure."""
        if ok or self.failures > len(self.RETRY_S):
            return self.delay_to_next()
        return float(self.RETRY_S[max(self.failures, 1) - 1])

    def _run(self):
        due = 0.0      # fetch at once
        while not self._stop.is_set():
            wait = max(0.0, due - self._mono())
            self.next_fetch_at = self._mono() + wait
            woke = self._wake.wait(wait)
            if self._stop.is_set():
                break
            if woke:
                self._wake.clear()
                loc = self._resolve()
                if loc == self.location and self.last_fetch_at is not None:
                    continue       # same place, keep the schedule
            try:
                ok = self.poll()
            except Exception as e:      # never let the thread die
                self.error = f"weather update failed: {e}"
                ok = False
            due = self._mono() + self.next_delay(ok)

    def _resolve(self) -> Optional[Location]:
        try:
            return self.location_fn()
        except Exception:
            return None

    # ── one fetch ──
    def poll(self) -> bool:
        """Fetch once and update the reading. Returns True on success."""
        loc = self._resolve()
        if loc is None:
            self.error = NO_LOCATION
            self.failures += 1
            with self._lock:
                self._reading = Reading(source="open-meteo", max_age_s=self.MAX_AGE_S)
            self.location = None
            return False
        if loc != self.location:
            with self._lock:       # the old reading was for somewhere else
                self._reading = Reading(source="open-meteo", max_age_s=self.MAX_AGE_S)
            self.location = loc
        try:
            data = self._fetch(loc, self.url, self.TIMEOUT_S)
        except OpenMeteoError as e:
            self.error = str(e)
            self.failures += 1
            return False
        self.apply(data)
        self.error = ""
        self.failures = 0
        self.fetches += 1
        return True

    def apply(self, data: dict, now: Optional[float] = None):
        """Put a reply's current conditions into the reading."""
        now = self._mono() if now is None else now
        cur = data.get("current") or {}
        # How old the values are, from the server's own time. Clamped to one
        # update interval so a player clock that is far off can't make a
        # fresh reply look stale (or from the future).
        t = _num(cur.get("time"))
        age = 0.0 if t is None else min(max(self._wall() - t, 0.0), float(self.REFRESH_S))
        at = now - age
        get = lambda k: _num(cur.get(k))  # noqa: E731
        with self._lock:
            r = self._reading
            if get("temperature_2m") is not None:
                r.temp_c, r.temp_at = get("temperature_2m"), at
            if get("wind_speed_10m") is not None:
                r.wind_ms, r.wind_dir, r.wind_at = get("wind_speed_10m"), get("wind_direction_10m"), at
            if get("wind_gusts_10m") is not None:
                r.gust_ms, r.gust_at = get("wind_gusts_10m"), at
            if get("relative_humidity_2m") is not None:
                r.humidity = get("relative_humidity_2m")
            r.last_packet_at = now
            self.last_fetch_at = now

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


def _stale_s(r: Reading, cfg: dict) -> float:
    if r.max_age_s is not None:
        return r.max_age_s
    return float(cfg.get("stale_minutes", DEFAULTS["stale_minutes"])) * 60


def temperature_message(r: Reading, cfg: dict, now: float) -> Message:
    t = {**DEFAULTS["temperature"], **(cfg.get("temperature") or {})}
    stale_s = _stale_s(r, cfg)
    if not t.get("enabled") or r.temp_c is None or not _fresh(r.temp_at, now, stale_s):
        return Message(())
    value = f"{round(c_to_f(r.temp_c))}°F"
    label = str(t.get("label") or "").strip()
    pieces = ((TEXT, label), (NUMBER, value)) if label else ((NUMBER, value),)
    return Message(pieces)


def wind_message(r: Reading, cfg: dict, now: float) -> Message:
    w = {**DEFAULTS["wind"], **(cfg.get("wind") or {})}
    stale_s = _stale_s(r, cfg)
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
