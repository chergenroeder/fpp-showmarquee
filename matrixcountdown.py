#!/usr/bin/env python3
"""
fpp-matrixcountdown daemon

Draws a live countdown (to Christmas, New Year's Day or a custom date) on one
FPP pixel-overlay model by writing frames into the model's overlay buffer.
Exposes a REST API on 127.0.0.1:32330 that FPP's web server proxies to.

Phase 1: config, logging and the REST API only. The countdown engine, the
renderer and the overlay output arrive in Phases 2-4 (DEVELOPMENT_PLAN.md).
"""

import copy
import json
import logging
import logging.handlers
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import base64
import io
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional

from countdown.fonts import FontIndex
from countdown.message import Message, build_message
from countdown.output import OutputError, OverlayOutput, model_name_problem
from countdown.timecalc import compute_display, local_now, resolve_target
from countdown.weather import (NO_LOCATION, Location, OpenMeteoPoller, Reading, TempestListener, compass,
                               c_to_f, make_location, ms_to_mph, parse_coord, weather_messages)

# ── Paths ────────────────────────────────────────────────────────────────────
# FPP exports MEDIADIR/LOGDIR to the processes it launches; fall back to the
# default install paths when run by hand.
PLUGIN_NAME  = "fpp-matrixcountdown"
PLUGIN_DIR   = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR    = os.environ.get("MEDIADIR", "/home/fpp/media")
LOG_DIR      = os.environ.get("LOGDIR", os.path.join(MEDIA_DIR, "logs"))
CONFIG_PATH  = os.path.join(MEDIA_DIR, "config", f"plugin.{PLUGIN_NAME}.json")
DEFAULT_CFG  = os.path.join(PLUGIN_DIR, "config.json")
# Personal data (a location typed in here) lives in plugindata/, not config/:
# FPP's crash bundles and settings backups copy config/ (template guideline 14.11).
DATA_DIR     = os.path.join(MEDIA_DIR, "plugindata", PLUGIN_NAME)
LOCATION_PATH = os.path.join(DATA_DIR, "location.json")
LOG_PATH     = os.path.join(LOG_DIR, f"plugin-{PLUGIN_NAME}.log")  # FPP rotates plugin-<repo>.log
API_HOST     = os.environ.get("MC_API_HOST", "127.0.0.1")
API_PORT     = int(os.environ.get("MC_API_PORT", "32330"))
API_PREFIX   = "/api/plugin/matrixcountdown"

SCHEMA_VERSION = 2   # 2: weather.source (Open-Meteo or Tempest)


def _get_git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "-C", PLUGIN_DIR, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


GIT_COMMIT = _get_git_commit()

# ── Logging ──────────────────────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)
# WatchedFileHandler reopens the file after FPP's rotation renames it
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.handlers.WatchedFileHandler(LOG_PATH)],
)
log = logging.getLogger("matrixcountdown")


# Crashes go to the same log. The start scripts send stdout/stderr nowhere
# (a redirect would keep writing to the log's rotated copy), so log them here.
def _log_uncaught(exc_type, exc, tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    log.critical("Uncaught exception", exc_info=(exc_type, exc, tb))


def _log_uncaught_thread(args):
    if args.exc_type is not SystemExit:
        log.critical("Uncaught exception in thread %s", getattr(args.thread, "name", "?"),
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


sys.excepthook = _log_uncaught
threading.excepthook = _log_uncaught_thread


# ── FPP API helpers ───────────────────────────────────────────────────────────

def fpp_get(host: str, path: str, timeout: float = 2.0):
    try:
        with urllib.request.urlopen(f"http://{host}{path}", timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log.debug("GET %s%s failed: %s", host, path, e)
        return None


def apply_log_level():
    """Set the Python log level from FPP's Settings → Logs → Plugin level."""
    data = fpp_get("localhost", "/api/settings/LogLevel_Plugin")
    level_str = str((data or {}).get("value") or "info").strip().lower()
    level = (logging.DEBUG   if level_str in ("debug", "excess") else
             logging.WARNING if level_str == "warn" else
             logging.ERROR   if level_str == "error" else
             logging.INFO)
    logging.getLogger().setLevel(level)


def get_fpp_models(host: str) -> List[dict]:
    """Pixel overlay models as [{name, width, height}]."""
    data = fpp_get(host, "/api/overlays/models")
    models = []
    for m in data if isinstance(data, list) else []:
        if isinstance(m, dict) and m.get("Name"):
            models.append({"name": m["Name"], "width": m.get("width"), "height": m.get("height")})
    return models


# ── Fonts ─────────────────────────────────────────────────────────────────────
# Pillow (FreeType) draws TrueType/OpenType fonts, and Type1 .pfb too.
FONTS = FontIndex([
    os.path.join(PLUGIN_DIR, "fonts"),
    os.path.join(MEDIA_DIR, "fonts"),
    "/usr/share/fonts/",
    "/usr/local/share/fonts/",
])


def detect_fonts(refresh: bool = False) -> Dict[str, str]:
    """{font name: file path} for every usable font on disk (cached)."""
    return FONTS.all(refresh)


def font_path(name: str) -> Optional[str]:
    """File to draw a style's font with: the font, a fallback, or None (built-in)."""
    return FONTS.resolve(name)[0]


_clock_cache = {"at": -1e9, "value": None}


def clock_synced() -> Optional[bool]:
    """Whether the system clock is synced over NTP (systemd), or None if unknown.

    The countdown is only as right as the player's clock; FPP players without
    an RTC keep wrong time until NTP syncs. Cached for a minute.
    """
    now = time.monotonic()
    if now - _clock_cache["at"] < 60:
        return _clock_cache["value"]
    value = None
    try:
        r = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                           capture_output=True, text=True, timeout=1.5)
        if r.returncode == 0 and r.stdout.strip() in ("yes", "no"):
            value = r.stdout.strip() == "yes"
    except (OSError, subprocess.SubprocessError):
        pass
    _clock_cache.update(at=now, value=value)
    return value


def pillow_version() -> Optional[str]:
    try:
        import PIL
        return PIL.__version__
    except ImportError:
        return None


# ── Config ────────────────────────────────────────────────────────────────────

def _deep_merge(base: dict, over: dict) -> dict:
    """base with over's values laid on top, recursing into dicts."""
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_defaults() -> dict:
    with open(DEFAULT_CFG) as f:
        return json.load(f)


def _migrate_config(cfg: dict) -> bool:
    """Apply schema migrations in place. Returns True if any were applied."""
    g = cfg.setdefault("global", {})
    version = int(g.get("schema_version", 0) or 0)
    migrated = False
    # Future: `if version < 2: ...; g["schema_version"] = 2; migrated = True`
    if version < SCHEMA_VERSION:
        g["schema_version"] = SCHEMA_VERSION
        migrated = True
    return migrated


def _migrate_user(user: dict) -> bool:
    """Migrations that need the saved file itself (before defaults fill gaps)."""
    w = user.get("weather")
    if isinstance(w, dict) and "source" not in w:
        # Before 2.1 the Tempest was the only source. Keep a setup that had
        # weather on with it, rather than start sending its location; one
        # with weather off picks a source when it turns weather on.
        w["source"] = "tempest" if w.get("enabled") else ""
        return True
    return False


def load_config() -> dict:
    """User config laid over the bundled defaults, so new keys always exist."""
    defaults = load_defaults()
    user = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                user = json.load(f)
            log.info("Loaded config from %s", CONFIG_PATH)
        except Exception as e:
            log.error("Failed to load %s (%s); using defaults", CONFIG_PATH, e)
    migrated = _migrate_user(user) if isinstance(user, dict) else False
    cfg = _deep_merge(defaults, user)
    if (_migrate_config(cfg) or migrated) and user:
        save_config(cfg)
    return cfg


def save_config(cfg: dict):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=4)
    os.replace(tmp, CONFIG_PATH)
    log.info("Config saved to %s", CONFIG_PATH)


# ── Location (personal data, kept in plugindata/) ─────────────────────────────

def load_location_override() -> dict:
    """{"latitude": .., "longitude": ..} typed in this plugin, or {}."""
    try:
        with open(LOCATION_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_location_override(lat, lon):
    """Write the typed-in location, readable by its owner only (0600).

    Both None (the fields were cleared) removes the file.
    """
    if lat is None and lon is None:
        try:
            os.remove(LOCATION_PATH)
            log.info("Weather location set in the plugin was cleared")
        except FileNotFoundError:
            pass
        return
    os.makedirs(DATA_DIR, mode=0o700, exist_ok=True)
    tmp = LOCATION_PATH + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"latitude": lat, "longitude": lon}, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, LOCATION_PATH)
    log.info("Weather location set in the plugin")    # never the coordinates (14.11)


_fpp_loc_cache = {"at": -1e9, "value": None}


def fpp_location() -> Optional[Location]:
    """FPP's own Latitude/Longitude (Settings → General), cached for a minute."""
    now = time.monotonic()
    if now - _fpp_loc_cache["at"] < 60:
        return _fpp_loc_cache["value"]
    lat = (fpp_get("localhost", "/api/settings/Latitude") or {}).get("value")
    lon = (fpp_get("localhost", "/api/settings/Longitude") or {}).get("value")
    value = make_location(lat, lon, "fpp")
    _fpp_loc_cache.update(at=now, value=value)
    return value


WEATHER_SOURCES = {"", "open-meteo", "tempest"}


_VALID = {
    ("target", "type"): {"custom", "christmas", "newyear"},
    ("layout", "number_position"): {"first", "last"},
    ("layout", "under_one_day"): {"hms", "hours"},
    ("motion", "direction"): {"L2R", "R2L", "T2B", "B2T", "static"},
}


def validate_config(cfg: dict) -> List[str]:
    """Problems that would stop the countdown working; empty when fine."""
    errors = []
    cd = cfg.get("countdown")
    if not isinstance(cd, dict):
        return ["'countdown' section missing"]
    model = str(cd.get("model") or "")
    if model and model_name_problem(model):
        errors.append(f"countdown.model: {model_name_problem(model)}")
    for (section, key), allowed in _VALID.items():
        val = (cd.get(section) or {}).get(key)
        if val not in allowed:
            errors.append(f"countdown.{section}.{key} must be one of {sorted(allowed)}, not {val!r}")
    t = cd.get("target") or {}
    if t.get("type") == "custom":
        try:
            datetime.strptime(str(t.get("custom_date")), "%Y-%m-%d")
        except ValueError:
            errors.append("countdown.target.custom_date must be YYYY-MM-DD for a custom target")
        try:
            datetime.strptime(str(t.get("custom_time") or "00:00"), "%H:%M")
        except ValueError:
            errors.append("countdown.target.custom_time must be HH:MM")
    for style in ("text_style", "number_style"):
        s = cd.get(style) or {}
        try:
            if not 4 <= int(s.get("size")) <= 128:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"countdown.{style}.size must be a whole number from 4 to 128")
        color = str(s.get("color", ""))
        if not (len(color) == 7 and color.startswith("#")
                and all(c in "0123456789abcdefABCDEF" for c in color[1:])):
            errors.append(f"countdown.{style}.color must look like #rrggbb")
    m = cd.get("motion") or {}
    try:
        if not 1 <= float(m.get("static_hold", 5)) <= 600:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("countdown.motion.static_hold must be from 1 to 600 seconds")
    w = cfg.get("weather") or {}
    if w.get("source", "") not in WEATHER_SOURCES:
        errors.append("weather.source must be \"open-meteo\", \"tempest\" or \"\" (not chosen)")
    om = w.get("open_meteo") or {}
    if not isinstance(om.get("use_fpp_location", True), bool):
        errors.append("weather.open_meteo.use_fpp_location must be true or false")
    for key, low, high in (("latitude", -90, 90), ("longitude", -180, 180)):
        if om.get(key) not in (None, "") and parse_coord(om.get(key), low, high) is None:
            errors.append(f"weather.open_meteo.{key} must be a number from {low} to {high}")
    try:
        if not 1 <= int(w.get("port", 50222)) <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("weather.port must be a UDP port number (1-65535)")
    try:
        if not 0.5 <= float(w.get("stale_minutes", 5)) <= 1440:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("weather.stale_minutes must be from 0.5 to 1440")
    try:
        if float((w.get("wind") or {}).get("gust_min_diff_mph", 5)) < 0:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("weather.wind.gust_min_diff_mph must be 0 or more")
    try:
        if not 1 <= float(m.get("pixels_per_second")) <= 500:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("countdown.motion.pixels_per_second must be from 1 to 500")
    try:
        if float(m.get("repeat_delay")) < 0:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("countdown.motion.repeat_delay must be 0 or more seconds")
    return errors


# ── Daemon ────────────────────────────────────────────────────────────────────

def _sample_reading() -> Reading:
    """72°F, wind 8 mph NW gusting 15: for previews before live weather arrives."""
    now_m = time.monotonic()
    return Reading(temp_c=(72 - 32) * 5 / 9, temp_at=now_m, wind_ms=8 / 2.2369363,
                   wind_dir=315, wind_at=now_m, gust_ms=15 / 2.2369363, gust_at=now_m)


class CountdownDaemon:
    OPEN_METEO_URL = os.environ.get("MC_OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
    RETRY_S = 5.0      # wait between attempts to open the output after an error
    CHECK_S = 5.0      # how often to check the buffer/model are still ours
    IDLE_S = 0.5       # loop pace while nothing is being drawn

    def __init__(self):
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()   # set on config change, so the loop reacts at once
        self.started_at = time.time()
        self.cfg = load_config()
        self._cfg_version = 0
        apply_log_level()
        log.info("matrixcountdown @ %s starting as uid %d (Pillow %s)",
                 GIT_COMMIT, os.geteuid(), pillow_version() or "NOT installed")
        # Output state, written by the loop thread, read by get_status()
        self._out_state = "starting"     # drawing | blank | off | error | starting
        self._out_error = ""
        self._fps = 0.0
        self._showing = {"slot": None, "message": ""}   # what the loop is drawing now
        self._listener = None    # TempestListener | OpenMeteoPoller | None
        self._listener_lock = threading.Lock()

    def _global(self) -> dict:
        return self.cfg.get("global", {})

    def get_config(self) -> dict:
        with self._lock:
            return copy.deepcopy(self.cfg)

    def update_config(self, new_cfg: dict) -> List[str]:
        """Lay new_cfg over the current settings, validate and save.

        A partial body changes only what it holds. Returns validation errors
        (nothing is saved if there are any).
        """
        new_cfg = copy.deepcopy(new_cfg)
        # The typed-in location never goes into config/ (see LOCATION_PATH)
        om_new = ((new_cfg.get("weather") or {}).get("open_meteo") or {}) \
            if isinstance(new_cfg.get("weather"), dict) else {}
        coords = {k: om_new.pop(k) for k in ("latitude", "longitude") if k in om_new} \
            if isinstance(om_new, dict) else {}
        merged = _deep_merge(_deep_merge(load_defaults(), self.get_config()), new_cfg)
        _migrate_config(merged)
        check = copy.deepcopy(merged)
        check.setdefault("weather", {}).setdefault("open_meteo", {}).update(coords)
        errors = validate_config(check)
        if not errors:
            errors = self._location_errors(merged, coords)
        if errors:
            return errors
        if coords:
            have = load_location_override()
            lat = parse_coord(coords.get("latitude", have.get("latitude")), -90, 90)
            lon = parse_coord(coords.get("longitude", have.get("longitude")), -180, 180)
            if (lat, lon) != (parse_coord(have.get("latitude"), -90, 90),
                              parse_coord(have.get("longitude"), -180, 180)):
                save_location_override(lat, lon)
        with self._lock:
            self.cfg = merged
            self._cfg_version += 1
            save_config(merged)
        self._wake.set()
        with self._listener_lock:
            if isinstance(self._listener, OpenMeteoPoller):
                self._listener.wake()     # refetches only if the location changed
        log.info("Config updated")
        return []

    @staticmethod
    def _location_errors(cfg: dict, coords: dict) -> List[str]:
        """A location of its own is switched on but none is given."""
        om = (cfg.get("weather") or {}).get("open_meteo") or {}
        if om.get("use_fpp_location", True):
            return []
        have = {**load_location_override(), **{k: v for k, v in coords.items()}}
        if make_location(have.get("latitude"), have.get("longitude"), "plugin") is None:
            return ["weather.open_meteo: enter a latitude and longitude, or use FPP's location"]
        return []

    def config_for_page(self) -> dict:
        """The settings plus the typed-in location, for GET config."""
        cfg = self.get_config()
        have = load_location_override()
        om = cfg.setdefault("weather", {}).setdefault("open_meteo", {})
        om["latitude"] = parse_coord(have.get("latitude"), -90, 90)
        om["longitude"] = parse_coord(have.get("longitude"), -180, 180)
        return cfg

    def reload_config(self):
        with self._lock:
            self.cfg = load_config()
            self._cfg_version += 1
        self._wake.set()
        apply_log_level()
        log.info("Config reloaded")

    def set_enabled(self, value) -> dict:
        """On / off / toggle the countdown and save it (FPP command "State")."""
        cfg = self.get_config()
        cur = bool(cfg["countdown"].get("enabled", True))
        if value == "toggle":
            new = not cur
        elif isinstance(value, bool):
            new = value
        else:
            return {"error": "enabled must be true, false or \"toggle\""}
        cfg["countdown"]["enabled"] = new
        errors = self.update_config(cfg)
        return {"error": "; ".join(errors)} if errors else {"enabled": new}

    def set_target(self, body: dict) -> dict:
        """Switch the target and save it (FPP command "Set Target").

        body: {"type": "christmas"|"newyear"|"custom", "date": "YYYY-MM-DD",
               "time": "HH:MM", "name": "...", "repeat": bool}; all but type optional.
        A custom target with no date keeps the date already saved.
        """
        kind = str(body.get("type") or "").strip().lower()
        kind = {"new year's day": "newyear", "new years day": "newyear", "new year": "newyear",
                "christmas day": "christmas"}.get(kind, kind)
        if kind not in ("christmas", "newyear", "custom"):
            return {"error": "type must be christmas, newyear or custom"}
        cfg = self.get_config()
        t = cfg["countdown"]["target"]
        t["type"] = kind
        if body.get("date"):
            t["custom_date"] = str(body["date"]).strip()
        if body.get("time"):
            t["custom_time"] = str(body["time"]).strip()
        if body.get("repeat") is not None and body.get("repeat") != "":
            r = body["repeat"]
            t["custom_repeat_yearly"] = r if isinstance(r, bool) else str(r).strip().lower() in ("1", "true", "yes", "on")
        if body.get("name"):
            t.setdefault("event_name", {})[kind] = str(body["name"]).strip()[:60]
        errors = self.update_config(cfg)
        if errors:
            return {"error": "; ".join(errors)}
        return {"target": t}

    def _snapshot(self):
        with self._lock:
            return copy.deepcopy(self.cfg), self._cfg_version

    def preview(self, body: dict) -> dict:
        """The message as the matrix would draw it, from unsaved form settings.

        body: {"config": {...partial config...}, "width": w, "height": h,
               "as": "now" | "days" | "under_day"}
        Returns the drawn strip as a PNG (base64) plus what the page needs to
        animate it the same way the daemon moves it.
        """
        try:
            from countdown.render import Style, layout_strip
        except ImportError:
            return {"error": "Pillow is not installed"}
        cfg = _deep_merge(load_defaults(), body.get("config") or {})
        errors = validate_config(cfg)
        if errors:
            return {"error": "; ".join(errors)}
        cd = cfg["countdown"]
        try:
            w = max(1, min(2048, int(body.get("width") or 192)))
            h = max(1, min(2048, int(body.get("height") or 96)))
        except (TypeError, ValueError):
            return {"error": "width and height must be numbers"}
        now = local_now()
        target = resolve_target(cd.get("target") or {}, now)
        if target is None:
            return {"error": "the custom target has no valid date"}
        mode = body.get("as", "now")
        weather_note = None
        if mode in ("temperature", "wind"):
            wcfg = cfg.get("weather") or {}
            # Show this message even if it's switched off, so it can be styled first
            shown_cfg = {**wcfg, "temperature": {**(wcfg.get("temperature") or {}), "enabled": True},
                         "wind": {**(wcfg.get("wind") or {}), "enabled": True}}
            reading = self.weather_reading()
            if reading is None or weather_messages(reading, shown_cfg)[mode].blank:
                # A sample, so styles and layout can be tried before data arrives
                reading = _sample_reading()
                weather_note = "sample reading (no live weather" + (
                    ": Weather is off" if not wcfg.get("enabled") else
                    ": choose a weather source" if not self.weather_source(cfg) else "") + ")"
            message = weather_messages(reading, shown_cfg)[mode]
            display = None
        else:
            if mode == "days":
                at = target.when - timedelta(days=8) + timedelta(hours=1)
            elif mode == "under_day":
                at = target.when - timedelta(hours=8, minutes=14, seconds=32)
            else:
                at = now
            layout = cd.get("layout") or {}
            display = compute_display(target, at, layout)
            message = build_message(display, target, layout)

        # The messages that take turns on the matrix. "Now" shows them all, the
        # way the daemon cycles them; the other modes show one.
        sequence = [("countdown" if display is not None else mode, message)]
        if mode == "now":
            wcfg = cfg.get("weather") or {}
            sequence = [("countdown", message)] if cd.get("enabled", True) else []
            if wcfg.get("enabled"):
                reading = self.weather_reading()
                live = weather_messages(reading, wcfg) if reading is not None else {}
                if not any(not m.blank for m in live.values()):
                    live = weather_messages(_sample_reading(), wcfg)
                    if any(not m.blank for m in live.values()):
                        weather_note = ("sample reading for the weather (choose a weather source)"
                                        if not self.weather_source(cfg) else
                                        "sample reading for the weather (none received yet)")
                sequence += [(k, m) for k, m in live.items() if not m.blank]
            if not sequence:
                sequence = [("countdown", message)]
        motion = cd.get("motion") or {}
        result = {
            "width": w, "height": h,
            "target": {"when": target.when.isoformat(timespec="minutes"),
                       "when_text": target.when.strftime("%a %b %-d %Y, %H:%M"),
                       "name": target.name, "repeats": target.repeats},
            "display": display.kind if display is not None else mode,
            "message": message.plain,
            "direction": motion.get("direction", "R2L"),
            "pixels_per_second": float(motion.get("pixels_per_second", 15)),
            "repeat_delay": float(motion.get("repeat_delay", 0)),
            "static_hold": float(motion.get("static_hold", 5)),
            "strip": None,
            "strips": [],
        }
        text_style = Style.from_cfg(cd.get("text_style") or {}, font_path)
        number_style = Style.from_cfg(cd.get("number_style") or {}, font_path)
        for slot, msg in sequence:
            strip = layout_strip(msg, text_style, number_style, w, result["direction"])
            if strip is None:
                continue
            buf = io.BytesIO()
            strip.save(buf, format="PNG")
            result["strips"].append({"slot": slot, "message": msg.plain,
                                     "strip": base64.b64encode(buf.getvalue()).decode(),
                                     "strip_width": strip.width, "strip_height": strip.height})
        if result["strips"]:   # the first one also at the top level, as before
            first = result["strips"][0]
            result.update(strip=first["strip"], strip_width=first["strip_width"],
                          strip_height=first["strip_height"])
        notes = []
        for which in ("number_style", "text_style"):
            want = str(cd[which].get("font") or "")
            if want and FONTS.find(want) is None:
                used = FONTS.resolve(want)[1]
                label = "Number" if which == "number_style" else "Text"
                notes.append(f"{label} font \u201c{want}\u201d isn't on this player; using "
                             + (f"\u201c{used}\u201d" if used else "the built-in font") + " instead.")
        if weather_note:
            result["note"] = weather_note
        if notes:
            result["warning"] = " ".join(notes)
        return result

    def get_models(self) -> List[dict]:
        return get_fpp_models(self._global().get("fpp_host", "localhost"))

    def get_status(self) -> dict:
        now = local_now()
        cfg = self.get_config()
        cd = cfg.get("countdown", {})
        target = resolve_target(cd.get("target") or {}, now)
        target_info, message = None, None
        if target is not None:
            layout = cd.get("layout") or {}
            display = compute_display(target, now, layout)
            msg = build_message(display, target, layout)
            target_info = {
                "when": target.when.isoformat(timespec="minutes"),
                "name": target.name,
                "repeats": target.repeats,
                "display": display.kind,
                "seconds_left": int(display.remaining.total_seconds()),
            }
            message = {"plain": msg.plain, "pieces": [list(p) for p in msg.pieces]}
        return {
            "running": True,
            "commit": GIT_COMMIT,
            "uptime_s": int(time.time() - self.started_at),
            "local_time": now.isoformat(timespec="seconds"),
            "timezone": now.tzname(),
            "utc_offset": now.strftime("%z"),
            "pillow": pillow_version(),
            "clock_synced": clock_synced(),
            "enable_output": bool(cfg.get("global", {}).get("enable_output", True)),
            "enabled": bool(cd.get("enabled", True)),
            "model": cd.get("model", ""),
            "target_type": (cd.get("target") or {}).get("type"),
            "config_errors": validate_config(cfg),
            "target": target_info,
            "message": message,
            "output": {"state": self._out_state, "error": self._out_error,
                       "fps": round(self._fps, 1), "root": os.geteuid() == 0},
            "showing": dict(self._showing),
            "weather": self.weather_status(cfg),
        }

    # ── Weather ──

    @staticmethod
    def weather_source(cfg: dict) -> str:
        """The weather source in use: "open-meteo", "tempest" or "" (off/not chosen)."""
        w = cfg.get("weather") or {}
        src = str(w.get("source") or "")
        return src if w.get("enabled") and src in ("open-meteo", "tempest") else ""

    def weather_location(self, cfg: Optional[dict] = None) -> Optional[Location]:
        """Where Open-Meteo's weather is for: FPP's location or the one set here."""
        cfg = self.get_config() if cfg is None else cfg
        om = (cfg.get("weather") or {}).get("open_meteo") or {}
        if om.get("use_fpp_location", True):
            return fpp_location()
        have = load_location_override()
        return make_location(have.get("latitude"), have.get("longitude"), "plugin")

    def _ensure_listener(self, cfg: dict):
        """Start, restart or stop the weather source to match the settings."""
        w = cfg.get("weather") or {}
        src = self.weather_source(cfg)
        port = int(w.get("port", 50222) or 50222)
        device = str(w.get("device") or "").strip().upper()
        with self._listener_lock:
            cur = self._listener
            if src == "tempest":
                ok = isinstance(cur, TempestListener) and cur.port == port and cur.device == device
            elif src == "open-meteo":
                ok = isinstance(cur, OpenMeteoPoller)
            else:
                ok = cur is None
            if ok:
                return cur
            if cur is not None:
                cur.stop()
                log.info("Stopped %s weather", "Open-Meteo" if isinstance(cur, OpenMeteoPoller) else "Tempest")
            self._listener = None
            if src == "tempest":
                self._listener = TempestListener(port, device)
                log.info("Listening for Tempest weather on UDP port %d%s", port,
                         f" (sensor {device})" if device else "")
            elif src == "open-meteo":
                self._listener = OpenMeteoPoller(self.weather_location, url=self.OPEN_METEO_URL)
                log.info("Getting weather from Open-Meteo every 15 minutes")
            if self._listener is not None:
                self._listener.start()
            return self._listener

    def weather_reading(self) -> Optional[Reading]:
        with self._listener_lock:
            return self._listener.reading() if self._listener is not None else None

    def weather_status(self, cfg: dict) -> dict:
        w = cfg.get("weather") or {}
        with self._listener_lock:
            lst = self._listener
        src = self.weather_source(cfg)
        info = {"enabled": bool(w.get("enabled")), "source": src,
                "listening": bool(lst and lst.running), "error": lst.error if lst else ""}
        if w.get("enabled") and not src:
            info["error"] = "choose a weather source"
        if src == "open-meteo":
            loc = self.weather_location(cfg)
            info["location"] = None if loc is None else {"lat": loc.lat, "lon": loc.lon, "from": loc.origin}
            if loc is None and not info["error"]:
                info["error"] = NO_LOCATION
        if lst is None:
            return info
        if isinstance(lst, OpenMeteoPoller):
            now_m = time.monotonic()
            info["last_fetch_age_s"] = None if lst.last_fetch_at is None else round(now_m - lst.last_fetch_at)
            info["next_fetch_s"] = None if lst.next_fetch_at is None else max(0, round(lst.next_fetch_at - now_m))
        r = lst.reading()
        now = time.monotonic()
        age = lambda at: None if at is None else round(now - at)  # noqa: E731
        msgs = weather_messages(r, w, now)
        info.update({
            "hub": r.hub, "device": r.device, "packets": r.packets,
            "hub_ip": r.source if src == "tempest" else "",
            "humidity": r.humidity,
            "last_packet_age_s": age(r.last_packet_at),
            "temp_f": None if r.temp_c is None else round(c_to_f(r.temp_c), 1),
            "temp_age_s": age(r.temp_at),
            "wind_mph": None if r.wind_ms is None else round(ms_to_mph(r.wind_ms), 1),
            "wind_dir": None if r.wind_dir is None else compass(r.wind_dir),
            "wind_age_s": age(r.wind_at),
            "gust_mph": None if r.gust_ms is None else round(ms_to_mph(r.gust_ms), 1),
            "messages": {k: m.plain for k, m in msgs.items()},
        })
        return info

    # ── Main loop ──

    def _set_state(self, state: str, error: str = ""):
        if (state, error) != (self._out_state, self._out_error):
            if error:
                log.error("Output: %s", error)
            else:
                log.info("Output: %s", state)
        self._out_state, self._out_error = state, error

    def run(self):
        """Draw frames until stop(). One thread owns the output and renderer."""
        try:
            from countdown.render import Renderer
        except ImportError:
            self._set_state("error", "Pillow is not installed (apt-get install python3-pil)")
            self._stop.wait()
            return

        out: Optional[OverlayOutput] = None
        renderer = None
        renderer_key = None
        next_open = 0.0
        next_check = 0.0
        frame_times: List[float] = []
        slot: Optional[str] = None      # which message is up: countdown | temperature | wind
        slot_passes = 0
        slot_started = 0.0

        def shut_output():
            nonlocal out, renderer, renderer_key
            if out is not None:
                out.close(turn_off=True)
            out, renderer, renderer_key = None, None, None

        while not self._stop.is_set():
            cfg, version = self._snapshot()
            g, cd = cfg.get("global", {}), cfg.get("countdown", {})
            model = str(cd.get("model") or "")
            host = str(g.get("fpp_host") or "localhost")
            fps = min(60.0, max(1.0, float(g.get("fps", 20) or 20)))
            errors = validate_config(cfg)
            wcfg = cfg.get("weather") or {}
            if not errors:
                self._ensure_listener(cfg)

            # Nothing to draw: make sure the model is off
            reason = ("output disabled" if not g.get("enable_output", True) else
                      "countdown and weather off" if not (cd.get("enabled", True) or wcfg.get("enabled")) else
                      "no model chosen" if not model else "")
            if reason or errors:
                if out is not None:
                    shut_output()
                if errors:
                    self._set_state("error", "config: " + "; ".join(errors))
                else:
                    self._set_state("off", "")
                self._fps = 0.0
                self._showing = {"slot": None, "message": ""}
                self._wait(self.IDLE_S)
                continue

            # (Re)open the buffer when the model/host changed or after an error
            if out is not None and (out.model != model or out.host != host):
                shut_output()
            now_m = time.monotonic()
            if out is not None and now_m >= next_check:
                next_check = now_m + self.CHECK_S
                if not out.check():
                    log.info("Overlay buffer for '%s' changed (fppd restarted?); reopening", model)
                    out.close(turn_off=False)
                    out, renderer, renderer_key = None, None, None
            if out is None:
                if now_m < next_open:
                    self._wait(min(self.IDLE_S, next_open - now_m))
                    continue
                try:
                    candidate = OverlayOutput(host, model)
                    candidate.open()
                except OutputError as e:
                    self._set_state("error", str(e))
                    next_open = now_m + self.RETRY_S
                    continue
                out = candidate
                next_check = now_m + self.CHECK_S
                log.info("Opened overlay buffer for '%s' (%dx%d, %d bytes/pixel)",
                         model, out.width, out.height, out.bpp)

            # Renderer follows the config and the panel size
            key = (version, out.width, out.height)
            if renderer_key != key:
                renderer = Renderer(out.width, out.height, cd, font_path)
                renderer_key = key
                slot_passes = 0

            try:
                # The messages that take turns: countdown, temperature, wind
                candidates = []
                if cd.get("enabled", True):
                    now = local_now()
                    target = resolve_target(cd.get("target") or {}, now)
                    if target is not None:
                        layout = cd.get("layout") or {}
                        candidates.append(("countdown", build_message(
                            compute_display(target, now, layout), target, layout)))
                if wcfg.get("enabled"):
                    reading = self.weather_reading()
                    if reading is not None:
                        candidates.extend(weather_messages(reading, wcfg).items())
                available = [(n, m) for n, m in candidates if not m.blank]

                if not available:
                    if out.model_on:
                        out.off()
                    renderer.strip_for(Message(()))   # so the next pass starts fresh
                    self._set_state("blank", "")
                    self._fps = 0.0
                    self._showing = {"slot": None, "message": ""}
                    frame_times.clear()
                    slot = None
                    self._wait(self.IDLE_S)
                    continue

                names = [n for n, _ in available]
                if slot not in names:
                    # Next in the cycle after the one that went away (or the first)
                    order = [n for n, _ in candidates]
                    later = [n for n in names if slot in order and order.index(n) > order.index(slot)]
                    slot = (later or names)[0]
                    slot_passes, slot_started = renderer.mover.passes, time.monotonic()
                message = dict(available)[slot]
                self._showing = {"slot": slot, "message": message.plain}

                out.on()
                t0 = time.monotonic()
                frame = renderer.frame(message, t0)
                # Take turns: switch after each full pass, or after the hold time when static
                if len(names) > 1:
                    static = renderer.direction == "static"
                    hold = float((cd.get("motion") or {}).get("static_hold", 5) or 5)
                    if (static and t0 - slot_started >= hold) or (not static and renderer.mover.passes != slot_passes):
                        slot = names[(names.index(slot) + 1) % len(names)]
                        slot_passes, slot_started = renderer.mover.passes, t0
                        message = dict(available)[slot]
                        self._showing = {"slot": slot, "message": message.plain}
                        # The pass that just started belongs to the new message
                        frame = renderer.frame(message, t0)
                out.write_rgb(frame.tobytes())
                self._set_state("drawing", "")
                period = 1.0 / fps
                # Follow fppd's real output rate: wait for it to take the frame
                out.wait_picked_up(period * 3)
                frame_times.append(t0)
                if len(frame_times) > 40:
                    del frame_times[0]
                if len(frame_times) > 1:
                    self._fps = (len(frame_times) - 1) / max(1e-6, frame_times[-1] - frame_times[0])
                rest = period - (time.monotonic() - t0)
                if rest > 0:
                    self._wait(rest)
            except OutputError as e:
                self._set_state("error", str(e))
                shut_output()
                next_open = time.monotonic() + self.RETRY_S
            except Exception as e:  # noqa: BLE001 - keep the loop alive, but say why
                log.exception("Unexpected error in the drawing loop")
                self._set_state("error", f"unexpected: {e}")
                shut_output()
                next_open = time.monotonic() + self.RETRY_S

        shut_output()
        self._set_state("off", "")
        with self._listener_lock:
            if self._listener is not None:
                self._listener.stop()
                self._listener = None

    def _wait(self, seconds: float):
        """Sleep, waking early on a config change or stop."""
        if self._wake.wait(seconds):
            self._wake.clear()

    def stop(self):
        self._stop.set()
        self._wake.set()


_daemon: Optional[CountdownDaemon] = None


# ── REST API ──────────────────────────────────────────────────────────────────

class ApiHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        log.debug("HTTP %s", fmt % args)

    def _send_json(self, code: int, data):
        body = json.dumps(data, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except Exception:
            return None

    def _route(self) -> Optional[str]:
        path = self.path.split("?")[0].rstrip("/")
        if not path.startswith(API_PREFIX + "/"):
            return None
        return path[len(API_PREFIX) + 1:]

    def do_GET(self):
        route = self._route()
        if _daemon is None:
            return self._send_json(503, {"error": "daemon not initialized"})
        if route == "status":
            self._send_json(200, _daemon.get_status())
        elif route == "config":
            self._send_json(200, _daemon.config_for_page())
        elif route == "models":
            self._send_json(200, _daemon.get_models())
        elif route == "fonts":
            refresh = "refresh=1" in self.path
            self._send_json(200, sorted(detect_fonts(refresh).keys(), key=str.lower))
        elif route == "version":
            self._send_json(200, {"commit": GIT_COMMIT})
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        route = self._route()
        if _daemon is None:
            return self._send_json(503, {"error": "daemon not initialized"})
        if route == "config":
            body = self._read_json()
            if not isinstance(body, dict):
                return self._send_json(400, {"error": "Body must be a JSON object"})
            errors = _daemon.update_config(body)
            if errors:
                self._send_json(400, {"error": "Invalid config", "details": errors})
            else:
                self._send_json(200, {"status": "saved"})
        elif route == "state":
            body = self._read_json()
            if not isinstance(body, dict):
                return self._send_json(400, {"error": "Body must be a JSON object"})
            result = _daemon.set_enabled(body.get("enabled"))
            self._send_json(400 if "error" in result else 200, result)
        elif route == "target":
            body = self._read_json()
            if not isinstance(body, dict):
                return self._send_json(400, {"error": "Body must be a JSON object"})
            result = _daemon.set_target(body)
            self._send_json(400 if "error" in result else 200, result)
        elif route == "preview":
            body = self._read_json()
            if not isinstance(body, dict):
                return self._send_json(400, {"error": "Body must be a JSON object"})
            result = _daemon.preview(body)
            self._send_json(400 if "error" in result else 200, result)
        elif route == "reload":
            _daemon.reload_config()
            self._send_json(200, {"status": "reloaded"})
        elif route == "daemon/stop":
            self._send_json(200, {"status": "stopping"})
            threading.Thread(
                target=lambda: (time.sleep(0.5), os.kill(os.getpid(), signal.SIGTERM)),
                daemon=True,
            ).start()
        elif route == "daemon/restart":
            self._send_json(200, {"status": "restarting"})
            threading.Thread(
                target=lambda: (time.sleep(0.5), os.execv(sys.executable, [sys.executable] + sys.argv)),
                daemon=True,
            ).start()
        else:
            self._send_json(404, {"error": "Not found"})


class _Server(HTTPServer):
    allow_reuse_address = True  # restart via execv rebinds the port at once


def run_api_server():
    server = _Server((API_HOST, API_PORT), ApiHandler)
    log.info("REST API listening on %s:%d", API_HOST, API_PORT)
    server.serve_forever()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    global _daemon
    _daemon = CountdownDaemon()

    threading.Thread(target=run_api_server, daemon=True).start()

    def handle_signal(sig, frame):
        log.info("Received signal %d, shutting down", sig)
        _daemon.stop()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    _daemon.run()
    log.info("Stopped")


if __name__ == "__main__":
    main()
