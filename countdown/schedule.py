"""Daily schedule page: the show's times, for the week or for tonight.

Settings (config "schedule"):
  nights          7 booleans, Sunday first: the nights the show runs
  mode            how the times are set:
                    "same"     one start/end for every show night ("every")
                    "weekend"  weeknights ("weeknight") and weekend nights
                               ("weekend"), with "weekend_nights" saying which
                               nights count as the weekend (default Fri, Sat)
                    "custom"   a start/end per night ("custom", Sunday first)
  show            "week" (every show night, nights with the same times
                  grouped) or "tonight" (tonight's times, or the next show)
  title           the heading on the week page ("" for none)
  clock           "12" (5:30 PM) or "24" (17:30)

Times are "HH:MM" on the player's clock. An end at or before the start means
the show ends after midnight ("5 PM – 12 AM").

  night_times()     the start/end for each night, Sunday first (None = no show)
  week_lines()      the week as (days, times) lines, grouped
  schedule_page()   the page to draw, for the player's local time
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

DAYS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
MODES = ("same", "weekend", "custom")
SHOWS = ("week", "tonight")
TITLE_MAX = 40
_TIME = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

Times = Tuple[str, str]   # ("17:30", "22:00")


def parse_time(value) -> Optional[Tuple[int, int]]:
    m = _TIME.match(str(value or "").strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def _pair(d) -> Optional[Times]:
    d = d if isinstance(d, dict) else {}
    start, end = str(d.get("start") or "").strip(), str(d.get("end") or "").strip()
    return (start, end) if parse_time(start) and parse_time(end) else None


def _bools(v, default: bool) -> List[bool]:
    v = v if isinstance(v, list) else []
    return [bool(v[i]) if i < len(v) else default for i in range(7)]


def night_times(cfg: dict) -> List[Optional[Times]]:
    """(start, end) for each night, Sunday first; None when there's no show (or no valid time)."""
    nights = _bools(cfg.get("nights"), True)
    mode = cfg.get("mode") if cfg.get("mode") in MODES else "same"
    out: List[Optional[Times]] = []
    weekend = _bools(cfg.get("weekend_nights"), False)
    custom = cfg.get("custom") if isinstance(cfg.get("custom"), list) else []
    for i in range(7):
        if not nights[i]:
            out.append(None)
        elif mode == "same":
            out.append(_pair(cfg.get("every")))
        elif mode == "weekend":
            out.append(_pair(cfg.get("weekend" if weekend[i] else "weeknight")))
        else:
            out.append(_pair(custom[i] if i < len(custom) else None))
    return out


def schedule_problems(cfg: dict) -> List[str]:
    """What's missing or wrong, in words for the settings page."""
    nights = _bools(cfg.get("nights"), True)
    if not any(nights):
        return ["no show nights are chosen"]
    mode = cfg.get("mode") if cfg.get("mode") in MODES else "same"
    times = night_times(cfg)
    missing = [DAYS[i] for i in range(7) if nights[i] and times[i] is None]
    if not missing:
        return []
    if mode == "same":
        return ["set the start and end time"]
    if mode == "weekend":
        weekend = _bools(cfg.get("weekend_nights"), False)
        which = sorted({"weekend" if weekend[DAYS.index(d)] else "weeknight" for d in missing})
        return [f"set the {w} start and end time" for w in which]
    return ["set a start and end time for " + ", ".join(missing)]


# ── Wording ───────────────────────────────────────────────────────────────────

def format_time(hm: Tuple[int, int], clock: str, suffix: bool = True) -> str:
    h, m = hm
    if clock == "24":
        return f"{h:02d}:{m:02d}"
    h12 = h % 12 or 12
    text = f"{h12}" if m == 0 else f"{h12}:{m:02d}"
    return text + (" AM" if h < 12 else " PM") if suffix else text


def format_range(times: Times, clock: str = "12") -> str:
    """ "17:30", "22:00" -> "5:30–10 PM"; "17:00", "00:00" -> "5 PM–12 AM"; 24 h: "17:30–22:00"."""
    a, b = parse_time(times[0]), parse_time(times[1])
    if clock == "24":
        return f"{format_time(a, clock)}–{format_time(b, clock)}"
    same_half = (a[0] < 12) == (b[0] < 12) and b > a
    return (f"{format_time(a, clock, suffix=not same_half)}–{format_time(b, clock)}")


def _runs(days: List[int]) -> List[List[int]]:
    """Consecutive runs of night indexes, wrapping Sat -> Sun ([0, 5, 6] -> [[5, 6, 0]])."""
    days = sorted(set(days))
    runs: List[List[int]] = []
    for d in days:
        if runs and runs[-1][-1] + 1 == d:
            runs[-1].append(d)
        else:
            runs.append([d])
    if len(runs) > 1 and runs[0][0] == 0 and runs[-1][-1] == 6:
        runs[-1] += runs.pop(0)          # Sat and Sun are next to each other
    return runs


def _run_label(run: List[int]) -> str:
    if len(run) == 1:
        return DAYS[run[0]]
    if len(run) == 2:
        return f"{DAYS[run[0]]} & {DAYS[run[1]]}"
    return f"{DAYS[run[0]]}\u2013{DAYS[run[-1]]}"


def day_span(days: List[int]) -> str:
    """[0..6] -> "Nightly"; [0..4] -> "Sun–Thu"; [5, 6] -> "Fri & Sat";
    [1, 3, 5] -> "Mon, Wed & Fri"; [0, 1, 2, 4] -> "Sun–Tue & Thu"."""
    if len(set(days)) == 7:
        return "Nightly"
    runs = _runs(days)
    labels = [_run_label(r) for r in runs]
    if len(labels) == 1:
        return labels[0]
    if any(len(r) == 2 for r in runs):        # "Fri & Sat" already has an "&"
        return ", ".join(labels)
    return ", ".join(labels[:-1]) + " & " + labels[-1]


def week_lines(cfg: dict) -> List[Tuple[List[int], Times]]:
    """One line per set of times: the show nights with those times, in week order.

    A line's place in the week is where its first run starts, so a run that
    wraps (Sat & Sun) goes where Saturday is.
    """
    times = night_times(cfg)
    groups = {}
    for i, t in enumerate(times):
        if t is not None:
            groups.setdefault(t, []).append(i)
    lines = [(days, t) for t, days in groups.items()]
    lines.sort(key=lambda line: _runs(line[0])[0][0])
    return lines


# ── The page ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ScheduleLine:
    days: str          # "Sun–Thu", "Tonight", ...
    times: str         # "5–10 PM", or "" for a heading
    today: bool = False


@dataclass(frozen=True)
class SchedulePage:
    title: str
    lines: Tuple[ScheduleLine, ...]
    kind: str = "week"     # "week" (a table of nights and times) or "tonight" (stacked, centered)

    @property
    def plain(self) -> str:
        parts = [self.title] if self.title else []
        parts += [f"{ln.days} {ln.times}".strip() + (" *" if ln.today else "") for ln in self.lines]
        return " | ".join(parts)

    @property
    def slot(self) -> str:
        return "schedule"


def show_night(cfg: dict, now: datetime) -> int:
    """Which night "tonight" is (Sunday 0), allowing for a show that runs past midnight.

    Normally today. But just after midnight, while last night's show is still
    on (it ends after midnight and that end hasn't come yet), it's still last
    night: Friday 5 PM-12:30 AM is "tonight" at 12:15 AM on Saturday.
    """
    today = (now.weekday() + 1) % 7      # Python: Monday 0; here Sunday 0
    last = (today - 1) % 7
    times = night_times(cfg)[last]
    if times is not None:
        start, end = parse_time(times[0]), parse_time(times[1])
        if end <= start and (now.hour, now.minute) < end:
            return last
    return today


def schedule_page(cfg: dict, now: datetime, force: bool = False) -> Optional[SchedulePage]:
    """The page for the player's local time now, or None when it's off or has no times."""
    if not (cfg.get("enabled") or force):
        return None
    clock = "24" if str(cfg.get("clock")) == "24" else "12"
    times = night_times(cfg)
    if all(t is None for t in times):
        return None
    today = show_night(cfg, now)
    if cfg.get("show") == "tonight":
        if times[today] is not None:
            return SchedulePage("", (ScheduleLine("Tonight", format_range(times[today], clock), True),), "tonight")
        for k in range(1, 8):
            i = (today + k) % 7
            if times[i] is not None:
                label = "Tomorrow" if k == 1 else DAYS[i]
                return SchedulePage("", (ScheduleLine("No show tonight", ""),
                                         ScheduleLine("Next: " + label, format_range(times[i], clock))), "tonight")
    title = " ".join(str(cfg.get("title") if cfg.get("title") is not None else "Show Times").split())
    lines = tuple(ScheduleLine(day_span(days), format_range(t, clock), today in days)
                  for days, t in week_lines(cfg))
    return SchedulePage(title, lines)


def schedule_status(cfg: dict, now: datetime) -> dict:
    problems = schedule_problems(cfg) if cfg.get("enabled") else []
    page = schedule_page(cfg, now)
    return {"enabled": bool(cfg.get("enabled")), "problems": problems,
            "summary": " · ".join(f"{day_span(d)} {format_range(t, '24' if str(cfg.get('clock')) == '24' else '12')}"
                                  for d, t in week_lines(cfg)),
            "plain": page.plain if page else ""}


def settings_problems(cfg: dict) -> List[str]:
    """Validation for saving: shapes and values, not completeness."""
    errors = []
    if not isinstance(cfg.get("enabled", False), bool):
        errors.append("schedule.enabled must be true or false")
    if cfg.get("mode", "same") not in MODES:
        errors.append("schedule.mode must be \"same\", \"weekend\" or \"custom\"")
    if cfg.get("show", "week") not in SHOWS:
        errors.append("schedule.show must be \"week\" or \"tonight\"")
    if str(cfg.get("clock", "12")) not in ("12", "24"):
        errors.append("schedule.clock must be \"12\" or \"24\"")
    if len(str(cfg.get("title") or "")) > TITLE_MAX:
        errors.append(f"schedule.title must be at most {TITLE_MAX} characters")
    for key in ("nights", "weekend_nights"):
        v = cfg.get(key)
        if v is not None and not (isinstance(v, list) and len(v) == 7 and all(isinstance(x, bool) for x in v)):
            errors.append(f"schedule.{key} must be 7 true/false values, Sunday first")
    pairs = [("every", cfg.get("every")), ("weeknight", cfg.get("weeknight")), ("weekend", cfg.get("weekend"))]
    custom = cfg.get("custom")
    if custom is not None:
        if not (isinstance(custom, list) and len(custom) == 7):
            errors.append("schedule.custom must be 7 start/end times, Sunday first")
        else:
            pairs += [(f"custom[{DAYS[i]}]", c) for i, c in enumerate(custom)]
    for name, p in pairs:
        if p is None:
            continue
        if not isinstance(p, dict):
            errors.append(f"schedule.{name} must have a start and an end")
            continue
        for k in ("start", "end"):
            v = str(p.get(k) or "").strip()
            if v and not parse_time(v):
                errors.append(f"schedule.{name}.{k} must be a time like 17:30")
    return errors
