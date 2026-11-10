"""Countdown time rules: which moment we count to, and what the number reads.

All times are local. In the daemon `tz` is None and Python's local-time rules
(the FPP player's time zone, daylight saving included) are used. Tests pass a
zoneinfo.ZoneInfo so they can pin a zone and cross DST changes.

Rules (DEVELOPMENT_PLAN.md, Section 3):
  * Christmas = Dec 25 00:00, New Year's Day = Jan 1 00:00. Each rolls over to
    next year once its day has ended, so the matrix is blank through the target
    day and then counts to next year.
  * A custom date repeats the same way when "repeat every year" is on (Feb 29
    falls on Feb 28 in other years); otherwise it stays in the past, blank.
  * 24 h or more left: calendar days (target date minus today's date), so a
    23- or 25-hour DST day never skips or repeats a day.
  * Under 24 h: HH:MM:SS (seconds rounded down, reaching 00:00:00 at zero), or
    whole hours rounded up, then whole minutes rounded up in the last hour.
  * At or after the target moment: blank.
"""

import calendar
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Optional

ONE_DAY = timedelta(hours=24)
ONE_HOUR = timedelta(hours=1)

DEFAULT_EVENT_NAMES = {"custom": "My Event", "christmas": "Christmas", "newyear": "New Year's Day"}
DEFAULT_UNITS = {"day": "Day", "days": "Days", "hour": "Hour", "hours": "Hours",
                 "minute": "Minute", "minutes": "Minutes"}


@dataclass(frozen=True)
class Target:
    when: datetime   # local, timezone-aware
    name: str        # event name shown in the message, e.g. "Christmas"
    kind: str        # "custom" | "christmas" | "newyear"
    repeats: bool    # rolls over to next year after its day


@dataclass(frozen=True)
class Display:
    kind: str                 # "days" | "hms" | "hours" | "minutes" | "blank"
    value: Optional[int]      # days/hours/minutes count; total seconds for hms; None if blank
    number_text: str          # "8 Days", "08:14:32", "45 Minutes"; "" if blank
    remaining: timedelta      # target - now (negative once passed)


def localize(naive: datetime, tz: Optional[tzinfo] = None) -> datetime:
    """Attach local time-zone info to a naive local datetime."""
    if tz is None:
        return naive.astimezone()  # system local rules, DST-aware
    return naive.replace(tzinfo=tz)


def local_now(tz: Optional[tzinfo] = None) -> datetime:
    return datetime.now(tz) if tz is not None else datetime.now().astimezone()


def _on_year(year: int, month: int, day: int) -> date:
    """month/day in year, with Feb 29 falling on Feb 28 in non-leap years."""
    if month == 2 and day == 29 and not calendar.isleap(year):
        day = 28
    return date(year, month, day)


def _parse_custom(target_cfg: dict):
    """(date, time) of a custom target, or None if not set or invalid."""
    try:
        d = datetime.strptime(str(target_cfg.get("custom_date") or ""), "%Y-%m-%d").date()
        t = datetime.strptime(str(target_cfg.get("custom_time") or "00:00"), "%H:%M").time()
    except ValueError:
        return None
    return d, t


def end_of_target_day(when: datetime, tz: Optional[tzinfo] = None) -> datetime:
    """Midnight that ends the target's local day."""
    return localize(datetime.combine(when.date() + timedelta(days=1), time(0, 0)), tz)


def resolve_target(target_cfg: dict, now: datetime, tz: Optional[tzinfo] = None) -> Optional[Target]:
    """The moment to count down to, or None if a custom target has no valid date."""
    kind = target_cfg.get("type", "christmas")
    names = {**DEFAULT_EVENT_NAMES, **(target_cfg.get("event_name") or {})}
    name = str(names.get(kind, "")).strip()
    if tz is not None:
        now = now.astimezone(tz)

    if kind == "christmas":
        month, day, at, repeats = 12, 25, time(0, 0), True
    elif kind == "newyear":
        month, day, at, repeats = 1, 1, time(0, 0), True
    elif kind == "custom":
        parsed = _parse_custom(target_cfg)
        if parsed is None:
            return None
        d, at = parsed
        repeats = bool(target_cfg.get("custom_repeat_yearly", False))
        if not repeats:
            return Target(localize(datetime.combine(d, at), tz), name, kind, False)
        month, day = d.month, d.day
    else:
        return None

    year = now.year
    when = localize(datetime.combine(_on_year(year, month, day), at), tz)
    if now >= end_of_target_day(when, tz):
        when = localize(datetime.combine(_on_year(year + 1, month, day), at), tz)
    return Target(when, name, kind, repeats)


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def compute_display(target: Target, now: datetime, layout: dict, tz: Optional[tzinfo] = None) -> Display:
    """What the number piece reads right now."""
    if tz is not None:
        now = now.astimezone(tz)
    # Don't convert `when` into now's offset: in the daemon both carry fixed
    # offsets (datetime.astimezone()), and a target on the other side of a DST
    # change would land an hour off, possibly on the wrong calendar date. Each
    # keeps its own local wall time, and the subtraction is done in UTC
    # explicitly: Python subtracts two datetimes that share a tzinfo by wall
    # clock, which would count a 23-hour DST day as 24 hours.
    when = target.when
    remaining = when.astimezone(timezone.utc) - now.astimezone(timezone.utc)
    units = {**DEFAULT_UNITS, **(layout.get("units") or {})}

    if remaining <= timedelta(0):
        return Display("blank", None, "", remaining)

    if remaining >= ONE_DAY:
        days = (when.date() - now.date()).days
        return Display("days", days, _plural(days, units["day"], units["days"]), remaining)

    secs = remaining.total_seconds()
    if layout.get("under_one_day", "hms") == "hms":
        total = int(secs)  # round down: 00:00:00 shows during the final second
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        return Display("hms", total, f"{h:02d}:{m:02d}:{s:02d}", remaining)

    if remaining >= ONE_HOUR:
        hours = math.ceil(secs / 3600)
        return Display("hours", hours, _plural(hours, units["hour"], units["hours"]), remaining)
    minutes = math.ceil(secs / 60)
    return Display("minutes", minutes, _plural(minutes, units["minute"], units["minutes"]), remaining)
