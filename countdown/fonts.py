"""Finding font files on the player.

Fonts are listed by file name without extension ("DejaVuSans-Bold"). Lookups
ignore case, spaces, hyphens and underscores, so "DejaVuSans-bold" and
"dejavu sans bold" find the same file.

When a style names a font the player doesn't have, the renderer uses
fallback(): the first installed font from a list of clear bold sans fonts, so
the matrix still looks right, rather than Pillow's small built-in font. An
empty font name means the built-in font on purpose.
"""

import os
import re
import threading
from typing import Dict, Iterable, Optional, Tuple

FONT_EXTENSIONS = {".ttf", ".otf", ".pfb"}

# Bold sans fonts that read well on LED matrices, most preferred first:
# Debian's fonts-dejavu-core, fonts-liberation, fonts-freefont, and the URW
# base35 Type1 fonts FPP's own text effect uses.
PREFERRED = (
    "DejaVuSans-Bold", "LiberationSans-Bold", "FreeSansBold", "NimbusSans-Bold",
    "NimbusSanL-Bold", "Arial Bold", "ArialBold", "DejaVuSans", "LiberationSans-Regular",
    "FreeSans", "NimbusSans-Regular",
)


def norm(name: str) -> str:
    return re.sub(r"[\s_\-]+", "", str(name or "")).lower()


class FontIndex:
    def __init__(self, dirs: Iterable[str]):
        self.dirs = list(dirs)
        self._fonts: Optional[Dict[str, str]] = None
        self._norm: Dict[str, str] = {}
        self._lock = threading.Lock()

    def _scan(self, directory: str, found: Dict[str, str]):
        try:
            entries = list(os.scandir(directory))
        except OSError:
            return
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):   # no linked dirs: no loops
                    self._scan(entry.path, found)
                elif entry.is_file():   # follows file symlinks: Debian links many fonts
                    base, ext = os.path.splitext(entry.name)
                    # First directory wins, so bundled fonts beat system copies
                    if ext.lower() in FONT_EXTENSIONS and base not in found:
                        found[base] = entry.path
            except OSError:
                continue

    def all(self, refresh: bool = False) -> Dict[str, str]:
        """{font name: file path}, sorted by name (cached)."""
        with self._lock:
            if self._fonts is None or refresh:
                found: Dict[str, str] = {}
                for d in self.dirs:
                    self._scan(d, found)
                self._fonts = dict(sorted(found.items(), key=lambda kv: kv[0].lower()))
                self._norm = {}
                for n, p in self._fonts.items():
                    self._norm.setdefault(norm(n), n)
            return self._fonts

    def find(self, name: str) -> Optional[str]:
        """Canonical name of an installed font matching name, or None."""
        fonts = self.all()
        if not name:
            return None
        if name in fonts:
            return name
        return self._norm.get(norm(name))

    def fallback(self) -> Optional[str]:
        """Name of the best installed font for when a chosen one is missing."""
        for want in PREFERRED:
            found = self.find(want)
            if found:
                return found
        for n, p in self.all().items():
            if p.lower().endswith((".ttf", ".otf")):
                return n
        return next(iter(self.all()), None)

    def resolve(self, name: str) -> Tuple[Optional[str], Optional[str]]:
        """(path to draw with, name used). Empty name = built-in font (None, None)."""
        if not name:
            return None, None
        used = self.find(name) or self.fallback()
        return (self.all().get(used), used) if used else (None, None)
