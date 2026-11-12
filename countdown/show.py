"""The Show page: the show's name and, optionally, its logo.

Settings (config "show"):
  enabled    the section's switch
  name       the show's name, up to NAME_MAX characters; a new line ("\\n")
             starts a new line on the matrix
  color      "text" (the Text style's colour), "number" (the Number style's)
             or "#rrggbb"
  show_name  with a logo uploaded: False shows the logo on its own

The logo isn't a setting: it's uploaded from the settings page and kept on
the player (plugindata/fpp-showmarquee/logo.png) by LogoStore, so it isn't in
config/ (FPP's backups) or in a downloaded settings file.

  show_page()        the page to show now, or None
  show_status()      what the settings page says about it
  settings_problems  validation for saving
  LogoStore          the uploaded logo: save (from a base64 image), remove, load
  logo_image()       the logo's picture by its id, for drawing
"""

import base64
import binascii
import hashlib
import io
import os
import re
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

NAME_MAX = 80
LOGO_MAX_SIDE = 512                 # the stored logo is at most this many pixels on its longer side
UPLOAD_MAX_BYTES = 8 * 1024 * 1024  # the image as uploaded (before base64)
SOURCE_MAX_PIXELS = 4096 * 4096     # larger images are refused rather than decoded
VISIBLE = 16                        # a pixel this dark or this transparent doesn't light an LED
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class ShowPage:
    lines: Tuple[str, ...]   # the name's lines; () when only the logo shows
    color: str               # "text", "number" or "#rrggbb"
    logo: str                # the logo's id, "" for none

    @property
    def plain(self) -> str:
        parts = (["[Logo]"] if self.logo else []) + ([" / ".join(self.lines)] if self.lines else [])
        return " ".join(parts)

    @property
    def slot(self) -> str:
        return "show"


def name_lines(cfg: dict) -> Tuple[str, ...]:
    text = str(cfg.get("name") or "").replace("\r\n", "\n")
    return tuple(" ".join(ln.split()) for ln in text.split("\n") if ln.strip())


def show_page(cfg: dict, logo_id: str = "", force: bool = False) -> Optional[ShowPage]:
    """The page now: None when it's off (unless force) or has nothing to show.

    Without a logo the name always shows (the "show the name" switch only
    matters with a logo).
    """
    if not cfg.get("enabled") and not force:
        return None
    lines = name_lines(cfg)
    logo = str(logo_id or "")
    if logo and cfg.get("show_name", True) is False:
        lines = ()
    if not lines and not logo:
        return None
    color = str(cfg.get("color") or "text")
    return ShowPage(lines, color if color in ("text", "number") or _COLOR.match(color) else "text", logo)


def show_status(cfg: dict, logo: Optional[dict]) -> dict:
    page = show_page(cfg, (logo or {}).get("id", ""))
    problem = ""
    if cfg.get("enabled") and page is None:
        problem = "type the show's name or upload a logo"
    return {"enabled": bool(cfg.get("enabled")), "showing": page is not None, "problem": problem,
            "plain": page.plain if page else "", "logo": logo}


def settings_problems(cfg: dict) -> List[str]:
    errors = []
    for key in ("enabled", "show_name"):
        if not isinstance(cfg.get(key, False), bool):
            errors.append(f"show.{key} must be true or false")
    if len(str(cfg.get("name") or "")) > NAME_MAX:
        errors.append(f"show.name must be at most {NAME_MAX} characters")
    color = str(cfg.get("color") or "text")
    if color not in ("text", "number") and not _COLOR.match(color):
        errors.append("show.color must be \"text\", \"number\" or #rrggbb")
    return errors


# ── The logo ──────────────────────────────────────────────────────────────────

_images: Dict[str, object] = {}     # logo id -> RGBA picture, for drawing
_images_lock = threading.Lock()


def logo_image(logo_id: str):
    with _images_lock:
        return _images.get(logo_id)


def _register(logo_id: str, img):
    with _images_lock:
        _images.clear()             # only the current logo is ever drawn
        if logo_id:
            _images[logo_id] = img


class LogoError(Exception):
    pass


def prepare_logo(data: bytes):
    """The uploaded image as the RGBA picture to keep, or LogoError.

    Edges that wouldn't light an LED (transparent or black) are trimmed so the
    logo fills its space on the matrix, and it's scaled to fit LOGO_MAX_SIDE.
    """
    from PIL import Image, ImageChops
    if len(data) > UPLOAD_MAX_BYTES:
        raise LogoError(f"the image is larger than {UPLOAD_MAX_BYTES // (1024 * 1024)} MB")
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > SOURCE_MAX_PIXELS:
            raise LogoError("the image is too large (more than 4096 × 4096 pixels)")
        img.seek(0)                   # an animated GIF: its first frame
        img.load()
    except LogoError:
        raise
    except Exception:
        raise LogoError("that isn't an image this player can read (use PNG, JPG, GIF or WebP)")
    img = img.convert("RGBA")
    alpha = img.getchannel("A").point(lambda v: 255 if v > VISIBLE else 0)
    bright = img.convert("RGB").convert("L").point(lambda v: 255 if v > VISIBLE else 0)
    box = ImageChops.multiply(alpha, bright).getbbox()
    if box is None:
        raise LogoError("the image is all black or transparent, so nothing would light up")
    img = img.crop(box)
    img.thumbnail((LOGO_MAX_SIDE, LOGO_MAX_SIDE), Image.LANCZOS)
    return img


class LogoStore:
    """The uploaded logo, kept as a PNG file. Its id is a hash of the file."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._id = ""
        self._size = (0, 0)
        self.load()

    def load(self):
        try:
            from PIL import Image
            with open(self.path, "rb") as f:
                data = f.read()
            img = Image.open(io.BytesIO(data))
            img.load()
            img = img.convert("RGBA")
        except Exception:     # no logo, no Pillow, or an unreadable file
            self._set("", None)
            return
        self._set(hashlib.sha1(data).hexdigest()[:12], img)

    def _set(self, logo_id: str, img):
        with self._lock:
            self._id = logo_id
            self._size = img.size if img is not None else (0, 0)
        _register(logo_id, img)

    @property
    def id(self) -> str:
        return self._id

    def info(self) -> Optional[dict]:
        with self._lock:
            if not self._id:
                return None
            return {"id": self._id, "width": self._size[0], "height": self._size[1]}

    def save_base64(self, b64: str) -> dict:
        """Keep an uploaded image (base64, optionally a data: URL). Returns info() or raises LogoError."""
        b64 = str(b64 or "")
        if b64.startswith("data:"):
            b64 = b64.split(",", 1)[-1]
        if len(b64) > UPLOAD_MAX_BYTES * 4 // 3 + 4:
            raise LogoError(f"the image is larger than {UPLOAD_MAX_BYTES // (1024 * 1024)} MB")
        try:
            data = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError):
            raise LogoError("the upload wasn't a base64 image")
        if not data:
            raise LogoError("the upload was empty")
        img = prepare_logo(data)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        png = buf.getvalue()
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(png)
        os.replace(tmp, self.path)
        self._set(hashlib.sha1(png).hexdigest()[:12], img)
        return self.info()

    def remove(self):
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass
        self._set("", None)

    def png_base64(self) -> Optional[str]:
        try:
            with open(self.path, "rb") as f:
                return base64.b64encode(f.read()).decode()
        except OSError:
            return None
