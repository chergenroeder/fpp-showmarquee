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
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional

from countdown.message import build_message
from countdown.output import OutputError, OverlayOutput
from countdown.timecalc import compute_display, local_now, resolve_target

# ── Paths ────────────────────────────────────────────────────────────────────
# FPP exports MEDIADIR/LOGDIR to the processes it launches; fall back to the
# default install paths when run by hand.
PLUGIN_NAME  = "fpp-matrixcountdown"
PLUGIN_DIR   = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR    = os.environ.get("MEDIADIR", "/home/fpp/media")
LOG_DIR      = os.environ.get("LOGDIR", os.path.join(MEDIA_DIR, "logs"))
CONFIG_PATH  = os.path.join(MEDIA_DIR, "config", f"plugin.{PLUGIN_NAME}.json")
DEFAULT_CFG  = os.path.join(PLUGIN_DIR, "config.json")
LOG_PATH     = os.path.join(LOG_DIR, f"plugin-{PLUGIN_NAME}.log")  # FPP rotates plugin-<repo>.log
API_HOST     = os.environ.get("MC_API_HOST", "127.0.0.1")
API_PORT     = int(os.environ.get("MC_API_PORT", "32330"))
API_PREFIX   = "/api/plugin/matrixcountdown"

SCHEMA_VERSION = 1


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
_FONT_DIRS = [
    os.path.join(PLUGIN_DIR, "fonts"),
    os.path.join(MEDIA_DIR, "fonts"),
    "/usr/share/fonts/",
    "/usr/local/share/fonts/",
]
_FONT_EXTENSIONS = {".ttf", ".otf", ".pfb"}
_font_cache: Optional[Dict[str, str]] = None
_font_lock = threading.Lock()


def _scan_font_dir(directory: str, found: Dict[str, str]):
    try:
        for entry in os.scandir(directory):
            if entry.is_symlink():
                continue
            if entry.is_dir():
                _scan_font_dir(entry.path, found)
            elif entry.is_file():
                base, ext = os.path.splitext(entry.name)
                # First directory wins, so bundled fonts beat system copies
                if ext.lower() in _FONT_EXTENSIONS and base not in found:
                    found[base] = entry.path
    except OSError:
        pass


def detect_fonts(refresh: bool = False) -> Dict[str, str]:
    """{font name: file path} for every usable font on disk (cached)."""
    global _font_cache
    with _font_lock:
        if _font_cache is None or refresh:
            found: Dict[str, str] = {}
            for d in _FONT_DIRS:
                _scan_font_dir(d, found)
            _font_cache = dict(sorted(found.items(), key=lambda kv: kv[0].lower()))
            log.debug("Font detection: %d fonts found", len(_font_cache))
        return _font_cache


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
    cfg = _deep_merge(defaults, user)
    if _migrate_config(cfg) and user:
        save_config(cfg)
    return cfg


def save_config(cfg: dict):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=4)
    os.replace(tmp, CONFIG_PATH)
    log.info("Config saved to %s", CONFIG_PATH)


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

class CountdownDaemon:
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

    def _global(self) -> dict:
        return self.cfg.get("global", {})

    def get_config(self) -> dict:
        with self._lock:
            return copy.deepcopy(self.cfg)

    def update_config(self, new_cfg: dict) -> List[str]:
        """Merge, validate and save. Returns validation errors (nothing saved if any)."""
        merged = _deep_merge(load_defaults(), new_cfg)
        _migrate_config(merged)
        errors = validate_config(merged)
        if errors:
            return errors
        with self._lock:
            self.cfg = merged
            self._cfg_version += 1
            save_config(merged)
        self._wake.set()
        log.info("Config updated")
        return []

    def reload_config(self):
        with self._lock:
            self.cfg = load_config()
            self._cfg_version += 1
        self._wake.set()
        apply_log_level()
        log.info("Config reloaded")

    def _snapshot(self):
        with self._lock:
            return copy.deepcopy(self.cfg), self._cfg_version

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
            "enable_output": bool(cfg.get("global", {}).get("enable_output", True)),
            "enabled": bool(cd.get("enabled", True)),
            "model": cd.get("model", ""),
            "target_type": (cd.get("target") or {}).get("type"),
            "config_errors": validate_config(cfg),
            "target": target_info,
            "message": message,
            "output": {"state": self._out_state, "error": self._out_error,
                       "fps": round(self._fps, 1), "root": os.geteuid() == 0},
        }

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

            # Nothing to draw: make sure the model is off
            reason = ("output disabled" if not g.get("enable_output", True) else
                      "countdown disabled" if not cd.get("enabled", True) else
                      "no model chosen" if not model else "")
            if reason or errors:
                if out is not None:
                    shut_output()
                if errors:
                    self._set_state("error", "config: " + "; ".join(errors))
                else:
                    self._set_state("off", "")
                self._fps = 0.0
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
                candidate = OverlayOutput(host, model)
                try:
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
                renderer = Renderer(out.width, out.height, cd, lambda n: detect_fonts().get(n))
                renderer_key = key

            try:
                now = local_now()
                target = resolve_target(cd.get("target") or {}, now)
                if target is None:
                    shut_output()
                    self._set_state("error", "custom target has no valid date")
                    self._wait(self.IDLE_S)
                    continue
                layout = cd.get("layout") or {}
                message = build_message(compute_display(target, now, layout), target, layout)

                if message.blank:
                    if out.model_on:
                        out.off()
                    renderer.strip_for(message)   # so the next pass starts fresh
                    self._set_state("blank", "")
                    self._fps = 0.0
                    frame_times.clear()
                    self._wait(self.IDLE_S)
                    continue

                out.on()
                t0 = time.monotonic()
                out.write_rgb(renderer.frame(message, t0).tobytes())
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
            self._send_json(200, _daemon.get_config())
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
