"""Show prep page: a QR code to the show's audio app, beside a short message.

The user picks the app viewers should get before the show (PulseMesh or
Tune2). The page shows a QR code that opens the app's download page on a
phone, and a message such as "Scan to get the PulseMesh app before the show".

  APPS             each app's name and default link
  show_prep_page() the page for the settings, or None when it's off or no app
                   is chosen
  qr_matrix()      the QR code as rows of booleans (needs python3-qrcode)

Default links (checked 2026-11-11):
  PulseMesh  https://pulsemesh.io/download      sends each phone to its own
             store (App Store / Google Play), with the web player as a fallback
  Tune2      https://www.tune2.app/downloads   Tune2 has no such page; this is
             its downloads page, with the App Store and Google Play links on it
Either can be replaced with the user's own link.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

APPS: Dict[str, Dict[str, str]] = {
    "pulsemesh": {"name": "PulseMesh", "link": "https://pulsemesh.io/download"},
    "tune2": {"name": "Tune2", "link": "https://www.tune2.app/downloads"},
}
DEFAULT_MESSAGE = "Scan to get the {app} app before the show"
MESSAGE_MAX = 120
LINK_MAX = 200
_LINK_OK = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)


def link_problem(value) -> str:
    """Why a typed link can't be used, or "" if it's fine (or empty)."""
    link = str(value or "").strip()
    if not link:
        return ""
    if len(link) > LINK_MAX:
        return f"is longer than {LINK_MAX} characters"
    if not _LINK_OK.match(link):
        return "must be a web address starting with https:// (or http://)"
    return ""


@dataclass(frozen=True)
class ShowPrepPage:
    app: str            # "pulsemesh" or "tune2"
    message: str        # with the app's name filled in
    link: str           # what the QR code opens

    @property
    def app_name(self) -> str:
        return APPS[self.app]["name"]

    @property
    def plain(self) -> str:
        return f"[QR {self.link}] {self.message}"

    @property
    def slot(self) -> str:
        return "showprep"


def page_link(cfg: dict) -> str:
    """The link the QR code opens: the user's own, else the app's default."""
    own = str(cfg.get("link") or "").strip()
    app = str(cfg.get("app") or "")
    return own if own else (APPS[app]["link"] if app in APPS else "")


def show_prep_page(cfg: dict, force: bool = False) -> Optional[ShowPrepPage]:
    """The page, or None when Show Prep is off (unless force) or no app is chosen."""
    if not (cfg.get("enabled") or force):
        return None
    app = str(cfg.get("app") or "")
    if app not in APPS or link_problem(cfg.get("link")):
        return None
    template = str(cfg.get("message") if cfg.get("message") is not None else DEFAULT_MESSAGE).strip()
    message = " ".join(template.replace("{app}", APPS[app]["name"]).split())
    return ShowPrepPage(app, message, page_link(cfg))


def show_prep_status(cfg: dict) -> dict:
    app = str(cfg.get("app") or "")
    info = {"enabled": bool(cfg.get("enabled")), "app": app,
            "app_name": APPS[app]["name"] if app in APPS else "",
            "link": page_link(cfg), "own_link": bool(str(cfg.get("link") or "").strip()),
            "problem": ""}
    if cfg.get("enabled") and app not in APPS:
        info["problem"] = "choose the app (PulseMesh or Tune2)"
    elif link_problem(cfg.get("link")):
        info["problem"] = "the link " + link_problem(cfg.get("link"))
    elif not have_qrcode():
        info["problem"] = ("the QR code library (python3-qrcode) isn't installed: Reinstall the plugin "
                           "so FPP installs it")
    page = show_prep_page(cfg)
    info["plain"] = page.plain if page else ""
    return info


# ── QR code ───────────────────────────────────────────────────────────────────

def have_qrcode() -> bool:
    try:
        import qrcode  # noqa: F401
        return True
    except ImportError:
        return False


_qr_cache: Dict[Tuple[str, str], List[List[bool]]] = {}


def qr_matrix(link: str, level: str = "M") -> List[List[bool]]:
    """The QR code's modules (True = dark), without a border.

    level is the error correction, "L", "M", "Q" or "H". Raises ImportError
    when python3-qrcode isn't installed.
    """
    key = (link, level)
    if key not in _qr_cache:
        import qrcode
        from qrcode import constants
        ec = {"L": constants.ERROR_CORRECT_L, "M": constants.ERROR_CORRECT_M,
              "Q": constants.ERROR_CORRECT_Q, "H": constants.ERROR_CORRECT_H}[level]
        q = qrcode.QRCode(error_correction=ec, border=0)
        q.add_data(link)
        q.make(fit=True)
        if len(_qr_cache) > 16:
            _qr_cache.clear()
        _qr_cache[key] = [list(row) for row in q.get_matrix()]
    return _qr_cache[key]


QUIET = 2   # lit modules around the code: phones need a light border to find it


def best_qr(link: str, max_px: int) -> Tuple[Optional[List[List[bool]]], int]:
    """(modules, LEDs per module) for the biggest code that fits max_px square.

    Tries each error-correction level: a lower level makes a smaller code, so
    it can be drawn with more LEDs per module (easier to scan from a
    distance). On a tie the higher level wins. (None, 0) if none fits at
    1 LED per module.
    """
    best: Tuple[Optional[List[List[bool]]], int] = (None, 0)
    for level in ("H", "Q", "M", "L"):
        m = qr_matrix(link, level)
        scale = max_px // (len(m) + 2 * QUIET)
        if scale > best[1]:
            best = (m, scale)
    return best
