from datetime import date

from rozprava.activity import PITCH, calendar


def test_weekday_grid_without_weekend_sittings():
    days = [{"date": "2026-11-04"}, {"date": "2026-11-06"}]
    cal = calendar(days, date(2026, 11, 2), date(2026, 11, 13))
    assert len(cal.cells) == 10  # two Monday-to-Friday weeks
    assert {c.day.isoformat() for c in cal.cells if c.info} == {"2026-11-04", "2026-11-06"}
    assert [label for _, label in cal.weekdays] == ["Po", "St", "Pá"]


def test_weekend_row_appears_only_for_weekend_sittings():
    days = [{"date": "2026-10-24"}]  # a Saturday sitting
    cal = calendar(days, date(2026, 10, 19), date(2026, 10, 25))
    weekend = [c for c in cal.cells if c.day.weekday() >= 5]
    assert len(weekend) == 1 and weekend[0].info is not None
    assert cal.weekdays[-1][1] == "So/Ne"
    assert cal.height > calendar([], date(2026, 10, 19), date(2026, 10, 25)).height
    assert weekend[0].y - cal.cells[0].y == 5 * PITCH


def test_month_labels():
    cal = calendar([], date(2025, 11, 3), date(2026, 1, 16))
    assert [label for _, label in cal.months] == ["lis 2025", "pro", "led 2026"]
