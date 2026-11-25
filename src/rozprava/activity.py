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
TOP = 30  # room for two label rows: years above, months below
YEAR_Y = 9  # baselines of the label rows
MONTH_Y = 21
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
    years: list[tuple[float, str]] = field(default_factory=list)  # first month and each January
    weekdays: list[tuple[float, str]] = field(default_factory=list)
    year_y: int = YEAR_Y
    month_y: int = MONTH_Y


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
                cal.months.append((LEFT + week * PITCH, MONTHS[day.month - 1]))
                # Years get their own row: "lis 2025" is wider than the four weeks to "pro".
                if day.month == 1 or not cal.years:
                    cal.years.append((LEFT + week * PITCH, str(day.year)))
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
