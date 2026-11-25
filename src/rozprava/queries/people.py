"""MP directory and profiles for one term."""

import datetime as dt
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rozprava import models
from rozprava.parties import INDEPENDENT
from rozprava.queries import common, search
from rozprava.queries.activity import TermActivity, median
from rozprava.typography import czech_sort_key, fold

PER_PAGE = 20
STRIP_DAYS = 20
SR = models.SpeechRevision


def _region_names(session: Session, ids: set[int]) -> dict[int, str]:
    return {
        id: name
        for id, name in session.execute(
            select(models.Organization.id, models.Organization.name).where(
                models.Organization.id.in_(ids)
            )
        )
    }


def _reference_day(term: common.TermInfo, activity: TermActivity) -> dt.date:
    """Club labels in the directory: membership on the term's last sitting day."""
    if activity.days:
        return activity.days[-1]
    return term.ended_on or dt.date.today()


def directory(
    session: Session,
    term: common.TermInfo,
    activity: TermActivity,
    query: str = "",
    parties_filter: tuple[str, ...] = (),
    region_filter: str = "",
    sort: str = "name",
) -> dict:
    rows = session.execute(
        select(models.Mandate, models.Person)
        .join(models.Person, models.Person.id == models.Mandate.person_id)
        .where(models.Mandate.term_id == term.id)
    ).all()
    regions = _region_names(session, {m.region_id for m, _ in rows if m.region_id})
    clubs = common.Clubs(session, [p.id for _, p in rows])
    strip_days = activity.days[-STRIP_DAYS:]
    day = _reference_day(term, activity)
    mps = []
    for mandate, person in rows:
        last_day = min(day, mandate.valid_to.date()) if mandate.valid_to else day
        participation = activity.participation.get(person.id)
        mps.append(
            {
                "id": person.id,
                "name": f"{person.forename} {person.surname}",
                "surname": person.surname,
                "forename": person.forename,
                "initials": (person.forename[:1] + person.surname[:1]).upper(),
                "slug": common.person_slug(person.id, person.forename, person.surname),
                "party": clubs.party_on(person.id, last_day),
                "region": regions.get(mandate.region_id or -1, ""),
                "speeches": activity.speeches.get(person.id, 0),
                "attendance": participation.percent if participation else None,
                "current": mandate.valid_to is None or mandate.valid_to.date() >= day,
                "strip": [
                    activity.day_view(person.id, d)
                    if (mandate.valid_from is None or d >= mandate.valid_from.date())
                    and (mandate.valid_to is None or d <= mandate.valid_to.date())
                    else {"date": d.isoformat(), "state": "ineligible", "level": 0}
                    for d in strip_days
                ],
            }
        )
    mps.sort(key=lambda m: (czech_sort_key(m["surname"]), czech_sort_key(m["forename"])))
    for i, m in enumerate(mps):
        m["sort_key"] = f"{i:04d}"
    counts = Counter(m["party"] for m in mps if m["party"])
    parties = sorted(
        counts.items(), key=lambda kv: (kv[0] == INDEPENDENT, -kv[1], czech_sort_key(kv[0]))
    )
    filtered = [
        m
        for m in mps
        if (not query or fold(query) in fold(m["name"]))
        and (not parties_filter or (m["party"] or "unknown") in parties_filter)
        and (not region_filter or m["region"] == region_filter)
    ]
    if sort in ("speeches", "attendance"):
        filtered.sort(key=lambda m: (m[sort] is None, -(m[sort] or 0), m["sort_key"]))
    elif sort in ("party", "region"):
        filtered.sort(key=lambda m: (czech_sort_key(m[sort] or ""), m["sort_key"]))
    return {
        "mps": filtered,
        "total_mps": len(mps),
        "parties": parties,
        "regions": sorted({m["region"] for m in mps if m["region"]}, key=czech_sort_key),
        "unknown_club": sum(1 for m in mps if not m["party"]),
    }


def profile(
    session: Session,
    term: common.TermInfo,
    person_id: int,
    activity: TermActivity,
    page: int = 1,
) -> dict | None:
    person = session.get(models.Person, person_id)
    mandate = session.scalar(
        select(models.Mandate).where(
            models.Mandate.person_id == person_id, models.Mandate.term_id == term.id
        )
    )
    if person is None or mandate is None:
        return None
    region = _region_names(session, {mandate.region_id} if mandate.region_id else set())
    clubs = common.Clubs(session, [person_id])
    day = _reference_day(term, activity)
    if mandate.valid_to:
        day = min(day, mandate.valid_to.date())
    female = person.sex == "F"
    title = "Poslankyně" if female else "Poslanec" if person.sex == "M" else "Člen Sněmovny"

    members = session.scalars(
        select(models.Mandate.person_id).where(models.Mandate.term_id == term.id)
    ).all()
    days_spoke = {
        p: sum(1 for d in activity.per_person.get(p, {}).values() if d.speeches) for p in members
    }
    known_percent = [
        p.percent
        for pid, p in activity.participation.items()
        if pid in set(members) and p.percent is not None
    ]
    participation = activity.participation.get(person_id)
    in_mandate = [
        d
        for d in activity.days
        if (mandate.valid_from is None or d >= mandate.valid_from.date())
        and (mandate.valid_to is None or d <= mandate.valid_to.date())
    ]
    stats = {
        "speeches": activity.speeches.get(person_id, 0),
        "median_speeches": median([activity.speeches.get(p, 0) for p in members]) or 0,
        "days_spoke": days_spoke.get(person_id, 0),
        "sitting_days": len(in_mandate),
        "median_days_spoke": median(list(days_spoke.values())) or 0,
        "attendance": participation.percent if participation else None,
        "attendance_known": participation.known if participation else 0,
        "attendance_unknown": participation.unknown if participation else 0,
        "attendance_registered": participation.registered if participation else 0,
        "median_attendance": median(known_percent),
        "words": activity.words.get(person_id, 0),
        "longest_words": activity.longest.get(person_id, 0),
        "provisional": activity.provisional,
    }

    topics = []
    for item_id, n in session.execute(
        select(SR.agenda_item_id, func.count())
        .where(
            SR.person_id == person_id,
            SR.term_id == term.id,
            SR.retired_at.is_(None),
            SR.role != "chair",
            SR.agenda_item_id.is_not(None),
        )
        .group_by(SR.agenda_item_id)
        .order_by(func.count().desc(), SR.agenda_item_id)
        .limit(6)
    ):
        item = session.get(models.AgendaItem, item_id)
        bill = session.get(models.Bill, item.bill_id) if item and item.bill_id else None
        view = common.agenda_view(item, bill, term.number)
        if view:
            topics.append(view | {"speeches": n})

    total = (
        session.scalar(
            select(func.count()).where(
                SR.person_id == person_id, SR.term_id == term.id, SR.retired_at.is_(None)
            )
        )
        or 0
    )
    rows = session.execute(
        select(SR, models.Speech)
        .join(models.Speech, models.Speech.id == SR.speech_id)
        .where(SR.person_id == person_id, SR.term_id == term.id, SR.retired_at.is_(None))
        .order_by(SR.date.desc(), SR.id.desc())
        .limit(PER_PAGE)
        .offset((page - 1) * PER_PAGE)
    ).all()
    first_last = session.execute(
        select(func.min(SR.date), func.max(SR.date)).where(
            SR.person_id == person_id, SR.term_id == term.id, SR.retired_at.is_(None)
        )
    ).one()
    activity_days = [activity.day_view(person_id, d) for d in in_mandate]
    return {
        "id": person.id,
        "name": f"{person.forename} {person.surname}",
        "slug": common.person_slug(person.id, person.forename, person.surname),
        "party": clubs.party_on(person.id, day),
        "party_date": day.isoformat(),
        "role": None,
        "initials": (person.forename[:1] + person.surname[:1]).upper(),
        "region": region.get(mandate.region_id or -1, ""),
        "title": title,
        "female": female,
        "terms": [
            {
                "number": term.number,
                "from": mandate.valid_from.date().isoformat() if mandate.valid_from else None,
                "to": mandate.valid_to.date().isoformat() if mandate.valid_to else None,
            }
        ],
        "psp_url": f"https://www.psp.cz/sqw/detail.sqw?id={person.id}",
        "stats": stats,
        "first_speech": first_last[0].isoformat() if first_last[0] else None,
        "last_speech": first_last[1].isoformat() if first_last[1] else None,
        "topics": topics,
        "activity": activity_days,
        "speeches": search.results_view(session, rows, [], offset=(page - 1) * PER_PAGE),
        "speech_total": total,
        "page": page,
        "pages": max(1, -(-total // PER_PAGE)),
    }
