"""Custom messages: the plugin user's own pages.

Settings (config "messages"):
  enabled   the section's switch
  items     up to MAX_ITEMS messages, in the order they show, each:
    enabled   on/off
    text      up to TEXT_MAX characters; a new line ("\\n") starts a new line on
              the matrix. Fill-ins: {days} {tonight} {temp} {date}
    color     "text" (the Text style's colour), "number" (the Number style's)
              or "#rrggbb"
    picture   "" or one of PICTURES, drawn on the left
    when      "always" or "dates" (only from "from" to "to", "MM-DD", every
              year; a window may wrap the new year, Dec 31 to Jan 1)

A message whose fill-in has nothing to show right now (no weather reading for
{temp}, no show tonight for {tonight}) is skipped, never shown with a gap.

  FILL_INS             the fill-ins and what they stand for
  fill()               a message's text with its fill-ins, or None
  in_window()          whether a date window includes a day
  message_pages()      the pages to show now
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

MAX_ITEMS = 10
TEXT_MAX = 120
PICTURES = ("star", "tree", "snowflake", "gift", "candycane", "heart")
PICTURE_NAMES = {"star": "Star", "tree": "Tree", "snowflake": "Snowflake", "gift": "Gift",
                 "candycane": "Candy cane", "heart": "Heart"}
FILL_INS = {
    "days": "days until the countdown's date (e.g. 8)",
    "tonight": "tonight's show times from the schedule (e.g. 5:30–10 PM)",
    "temp": "the temperature from the weather (e.g. 38°F)",
    "date": "today's date (e.g. Dec 18)",
}
_FILL = re.compile(r"\{(\w+)\}")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_MONTH_DAY = re.compile(r"^(\d{2})-(\d{2})$")
DAYS_IN_MONTH = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def parse_month_day(value) -> Optional[Tuple[int, int]]:
    m = _MONTH_DAY.match(str(value or "").strip())
    if not m:
        return None
    mo, d = int(m.group(1)), int(m.group(2))
    return (mo, d) if 1 <= mo <= 12 and 1 <= d <= DAYS_IN_MONTH[mo - 1] else None


def in_window(start: str, end: str, day: date) -> bool:
    """Whether day falls from start to end ("MM-DD", both included), any year.

    A window whose end comes before its start wraps the new year:
    "12-31" to "01-01" includes both days.
    """
    a, b = parse_month_day(start), parse_month_day(end)
    if a is None or b is None:
        return False
    md = (day.month, day.day)
    return a <= md <= b if a <= b else (md >= a or md <= b)


def fill(text: str, values: Dict[str, Optional[str]]) -> Optional[str]:
    """The text with its fill-ins replaced, or None if one has no value now.

    Unknown names ({nope}) are left as typed, so a stray brace isn't lost.
    """
    missing = False

    def sub(m):
        nonlocal missing
        name = m.group(1)
        if name not in FILL_INS:
            return m.group(0)
        v = values.get(name)
        if v is None or v == "":
            missing = True
            return ""
        return str(v)

    out = _FILL.sub(sub, text)
    return None if missing else out


@dataclass(frozen=True)
class MessagePage:
    index: int            # its place in the list, for the slot name
    lines: Tuple[str, ...]
    color: str            # "text", "number" or "#rrggbb"
    picture: str          # "" or one of PICTURES

    @property
    def plain(self) -> str:
        pic = f"[{PICTURE_NAMES[self.picture]}] " if self.picture else ""
        return pic + " / ".join(self.lines)

    @property
    def slot(self) -> str:
        return f"message:{self.index + 1}"


def _items(cfg: dict) -> List[dict]:
    items = cfg.get("items")
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def item_page(i: int, item: dict, values: Dict[str, Optional[str]], today: date,
              force: bool = False) -> Tuple[Optional[MessagePage], str]:
    """(page, why not): one message's page now, or None and the reason it's skipped."""
    if not item.get("enabled", True) and not force:
        return None, "switched off"
    if item.get("when") == "dates" and not force and not in_window(item.get("from"), item.get("to"), today):
        return None, "outside its dates"
    text = str(item.get("text") or "").replace("\r\n", "\n").strip()
    if not text:
        return None, "no text"
    filled = fill(text, values)
    if filled is None:
        names = [n for n in _FILL.findall(text) if n in FILL_INS and not values.get(n)]
        return None, "nothing for " + ", ".join("{" + n + "}" for n in dict.fromkeys(names)) + " right now"
    lines = tuple(" ".join(ln.split()) for ln in filled.split("\n") if ln.strip())
    color = str(item.get("color") or "text")
    picture = str(item.get("picture") or "")
    return MessagePage(i, lines, color if color in ("text", "number") or _COLOR.match(color) else "text",
                       picture if picture in PICTURES else ""), ""


def message_pages(cfg: dict, values: Dict[str, Optional[str]], today: date) -> List[MessagePage]:
    """The messages to show now, in order; [] when the section is off."""
    if not cfg.get("enabled"):
        return []
    pages = []
    for i, item in enumerate(_items(cfg)[:MAX_ITEMS]):
        page, _why = item_page(i, item, values, today)
        if page is not None:
            pages.append(page)
    return pages


def messages_status(cfg: dict, values: Dict[str, Optional[str]], today: date) -> dict:
    """Each message and whether it shows now (and why not), for the settings page."""
    out = []
    for i, item in enumerate(_items(cfg)[:MAX_ITEMS]):
        page, why = item_page(i, item, values, today)
        out.append({"showing": page is not None, "why": why, "plain": page.plain if page else ""})
    return {"enabled": bool(cfg.get("enabled")), "items": out,
            "showing": sum(1 for x in out if x["showing"]) if cfg.get("enabled") else 0}


def settings_problems(cfg: dict) -> List[str]:
    """Validation for saving."""
    errors = []
    if not isinstance(cfg.get("enabled", False), bool):
        errors.append("messages.enabled must be true or false")
    items = cfg.get("items", [])
    if not isinstance(items, list):
        return errors + ["messages.items must be a list"]
    if len(items) > MAX_ITEMS:
        errors.append(f"messages: at most {MAX_ITEMS} messages")
    for n, item in enumerate(items, 1):
        if not isinstance(item, dict):
            errors.append(f"messages.items[{n}] must be a message")
            continue
        if not isinstance(item.get("enabled", True), bool):
            errors.append(f"message {n}: enabled must be true or false")
        if len(str(item.get("text") or "")) > TEXT_MAX:
            errors.append(f"message {n}: at most {TEXT_MAX} characters")
        color = str(item.get("color") or "text")
        if color not in ("text", "number") and not _COLOR.match(color):
            errors.append(f"message {n}: colour must be \"text\", \"number\" or #rrggbb")
        if str(item.get("picture") or "") not in ("", *PICTURES):
            errors.append(f"message {n}: picture must be one of {', '.join(PICTURES)} (or none)")
        when = item.get("when", "always")
        if when not in ("always", "dates"):
            errors.append(f"message {n}: when must be \"always\" or \"dates\"")
        if when == "dates":
            for k in ("from", "to"):
                if parse_month_day(item.get(k)) is None:
                    errors.append(f"message {n}: {k} must be a month and day (MM-DD)")
    return errors
