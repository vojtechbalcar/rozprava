"""Layout of the session-day activity graph (DESIGN.md §7.11).

Columns are ISO weeks, rows are Monday to Friday. A sixth row (weekend) appears
only when the period contains a weekend sitting; if some week sits on both
Saturday and Sunday, each gets a row so cells never overlap. Every calendar day
in the period is a cell, so days without a sitting keep the grid visible as tiny dots.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta

PITCH = 12  # 8px dot + 4px gap
DOT = 8
LEFT = 28  # room for the weekday labels
TOP = 18  # room for the month labels
MONTHS = ("led", "úno", "bře", "dub", "kvě", "čvn", "čvc", "srp", "zář", "říj", "lis", "pro")
WEEKDAY_LABELS = {0: "Po", 2: "St", 4: "Pá"}


@dataclass
class Cell:
    x: float
    y: float
    day: date
    info: dict | None  # the sitting day's data, or None when the Sněmovna didn't sit


@dataclass
class Calendar:
    width: int
    height: int
    cells: list[Cell] = field(default_factory=list)
    months: list[tuple[float, str]] = field(default_factory=list)
    weekdays: list[tuple[float, str]] = field(default_factory=list)


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def calendar(days: Iterable[dict], start: date, end: date) -> Calendar:
    """Lay out sitting days (dicts with an ISO "date") between start and end."""
    by_date = {date.fromisoformat(d["date"]): d for d in days}
    in_range = {d: v for d, v in by_date.items() if start <= d <= end}
    weekend = any(d.weekday() >= 5 for d in in_range)
    both = any(d.weekday() == 5 and d + timedelta(days=1) in in_range for d in in_range)
    rows = 7 if both else 6 if weekend else 5
    first, weeks = _monday(start), (_monday(end) - _monday(start)).days // 7 + 1
    cal = Calendar(width=LEFT + weeks * PITCH, height=TOP + rows * PITCH)
    seen_months: set[tuple[int, int]] = set()
    for week in range(weeks):
        monday = first + timedelta(weeks=week)
        x = LEFT + week * PITCH + DOT / 2
        for offset in range(7):
            day = monday + timedelta(days=offset)
            if not start <= day <= end:
                continue
            if (day.year, day.month) not in seen_months and (day.day <= 7 or day == start):
                seen_months.add((day.year, day.month))
                label = MONTHS[day.month - 1] + (
                    f" {day.year}" if day.month == 1 or day == start else ""
                )
                cal.months.append((LEFT + week * PITCH, label))
            if offset < 5:
                cal.cells.append(Cell(x, TOP + offset * PITCH + DOT / 2, day, in_range.get(day)))
            elif both:
                cal.cells.append(Cell(x, TOP + offset * PITCH + DOT / 2, day, in_range.get(day)))
            elif weekend and (
                day in in_range or (offset == 5 and monday + timedelta(days=6) not in in_range)
            ):
                cal.cells.append(Cell(x, TOP + 5 * PITCH + DOT / 2, day, in_range.get(day)))
    cal.weekdays = [(TOP + row * PITCH + DOT / 2, label) for row, label in WEEKDAY_LABELS.items()]
    if both:
        cal.weekdays += [(TOP + 5 * PITCH + DOT / 2, "So"), (TOP + 6 * PITCH + DOT / 2, "Ne")]
    elif weekend:
        cal.weekdays.append((TOP + 5 * PITCH + DOT / 2, "So/Ne"))
    return cal
