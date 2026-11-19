"""Small, parameterized lookups for the navigation palette; no transcript fetches."""

import datetime as dt
import re

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from rozprava import models, titles
from rozprava.queries import common
from rozprava.typography import fold

LIMIT = 6
MAX_QUERY = 200


def lookup(session: Session, query: str) -> dict:
    query = " ".join(query.split())[:MAX_QUERY]
    result: dict = {"query": query, "mps": [], "bills": [], "sittings": []}
    if not query:
        return result
    p, m, t = models.Person, models.Mandate, models.Term
    latest = (
        select(m.person_id, func.max(t.number).label("number"))
        .join(t, t.id == m.term_id)
        .group_by(m.person_id)
        .subquery()
    )
    name = func.lower(func.unaccent(p.forename + " " + p.surname))
    members = session.execute(
        select(p, m, t)
        .join(m, m.person_id == p.id)
        .join(t, t.id == m.term_id)
        .join(latest, and_(latest.c.person_id == p.id, latest.c.number == t.number))
        .where(*(name.contains(fold(word), autoescape=True) for word in query.split()))
        .order_by(func.lower(func.unaccent(p.surname)), p.forename, p.id)
        .limit(LIMIT)
    ).all()
    clubs = common.Clubs(session, [person.id for person, _, _ in members])
    regions = {
        org.id: org.name
        for org in session.scalars(
            select(models.Organization).where(
                models.Organization.id.in_({mandate.region_id for _, mandate, _ in members})
            )
        )
    }
    for person, mandate, term in members:
        day = term.ended_on or dt.date.today()
        if mandate.valid_to:
            day = min(day, mandate.valid_to.date())
        result["mps"].append(
            {
                "name": person.name,
                "sort": person.surname,
                "term": term.number,
                "slug": common.person_slug(person.id, person.forename, person.surname),
                "initials": (person.forename[:1] + person.surname[:1]).upper(),
                "party": clubs.party_on(person.id, day) or "",
                "region": regions.get(mandate.region_id, ""),
            }
        )

    # A plain number matches both categories; prefixed numbers select a category.
    folded = fold(query)
    number = re.fullmatch(r"(?:(tisk|schuze)\s+)?([0-9]{1,6})\.?", folded)
    b = models.Bill
    bill_query = select(b, t.number).join(t, t.id == b.term_id).where(b.sub_number == 0)
    if number:
        bill_query = bill_query.where(b.number == int(number[2]))
    else:
        title = func.lower(func.unaccent(b.title + " " + b.short_title))
        bill_query = bill_query.where(
            *(title.contains(fold(w), autoescape=True) for w in query.split())
        )
    if not number or number[1] != "schuze":
        for bill, term_number in session.execute(
            bill_query.order_by(t.number.desc(), b.number, b.id).limit(LIMIT)
        ):
            result["bills"].append(
                {
                    "tisk": bill.number,
                    "term": term_number,
                    "title": titles.short_title(
                        bill.title, bill.number, bill.short_title, term=term_number
                    ),
                }
            )
    if number and number[1] != "tisk":
        s = models.Sitting
        for sitting, term_number in session.execute(
            select(s, t.number)
            .join(t, t.id == s.term_id)
            .where(s.number == int(number[2]))
            .order_by(t.number.desc())
            .limit(LIMIT)
        ):
            result["sittings"].append(
                {
                    "number": sitting.number,
                    "term": term_number,
                    "from": sitting.starts_at.date().isoformat() if sitting.starts_at else None,
                    "to": sitting.ends_at.date().isoformat() if sitting.ends_at else None,
                }
            )
    return result
