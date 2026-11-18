"""Minimal database rows for tests. Values echo real psp.cz records but are not imports."""

import datetime as dt

from sqlalchemy.orm import Session

from rozprava import models

TERMS = {
    9: dict(id=173, number=9, year=2021, started_on=dt.date(2021, 10, 9)),
    10: dict(id=174, number=10, year=2025, started_on=dt.date(2025, 10, 4)),
}


def term(db: Session, number: int = 10) -> models.Term:
    existing = db.get(models.Term, TERMS[number]["id"])
    if existing:
        return existing
    row = models.Term(**TERMS[number])
    db.add(row)
    db.flush()
    return row


def person(db: Session, id: int, forename: str, surname: str, sex: str | None = "M"):
    row = models.Person(id=id, forename=forename, surname=surname, sex=sex)
    db.add(row)
    db.flush()
    return row


def source_page(
    db: Session, id: int, page: int, sitting: int = 34, term_number: int = 10, **values
) -> models.SourcePage:
    t = term(db, term_number)
    row = models.SourcePage(
        id=id,
        term_id=t.id,
        sitting_number=sitting,
        page=page,
        day_number=values.pop("day_number", 12),
        date=values.pop("date", dt.date(2026, 11, 6)),
        **values,
    )
    db.add(row)
    db.flush()
    return row
