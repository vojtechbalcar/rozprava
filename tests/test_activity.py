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
    assert [label for _, label in cal.months] == ["lis", "pro", "led"]
    assert [label for _, label in cal.years] == ["2025", "2026"]
    january = next(x for x, label in cal.months if label == "led")
    assert dict((label, x) for x, label in cal.years)["2026"] == january


def test_labels_in_a_row_never_overlap():
    """A whole term: 10px mono caps with 0.06em tracking are about 7px per character."""
    cal = calendar([], date(2025, 11, 3), date(2026, 11, 13))
    for row in (cal.months, cal.years):
        for (x1, a), (x2, _) in zip(row, row[1:], strict=False):
            assert x1 + 7 * len(a) + 4 <= x2, (a, x1, x2)
    assert max(y for y, _ in [(c.y, c) for c in cal.cells]) < cal.height


def test_saturday_and_sunday_sittings_get_separate_rows():
    days = [{"date": "2026-10-24"}, {"date": "2026-10-25"}]  # Saturday and Sunday
    cal = calendar(days, date(2026, 10, 19), date(2026, 10, 25))
    positions = [(c.x, c.y) for c in cal.cells]
    assert len(positions) == len(set(positions)) == 7
    assert [label for _, label in cal.weekdays][-2:] == ["So", "Ne"]
