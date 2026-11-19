"""Home page, sittings and coverage: what the archive holds and how complete it is."""

import datetime as dt
import hashlib
import statistics
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rozprava import models
from rozprava.morphology import MODEL
from rozprava.queries import common, search

SR = models.SpeechRevision
FEATURED_MIN_WORDS = 60


def _levels(values: list[int]) -> list[int]:
    """1–3 by tercile of positive values (0 stays 0): the strips' common scale."""
    positive = sorted(v for v in values if v > 0)
    if len(positive) < 3:
        return [1 if v > 0 else 0 for v in values]
    t1, t2 = statistics.quantiles(positive, n=3)
    return [0 if v <= 0 else 1 if v <= t1 else 2 if v <= t2 else 3 for v in values]


def coverage(session: Session) -> list[dict]:
    """Per term: expected, imported, pending, failed and unavailable transcript pages."""
    rows = session.execute(
        select(models.Term.number, models.SourcePage.status, func.count())
        .join(models.Term, models.Term.id == models.SourcePage.term_id)
        .group_by(models.Term.number, models.SourcePage.status)
    ).all()
    terms: dict[int, dict] = {
        t: dict(term=t, expected=0, imported=0, pending=0, failed=0, unavailable=0)
        for t in common.terms(session)
    }
    for number, status, n in rows:
        t = terms[number]
        t[status] = n
        t["expected"] += n
    for t in terms.values():
        t["complete"] = t["expected"] > 0 and t["imported"] == t["expected"]
        t["percent"] = 100 * t["imported"] / t["expected"] if t["expected"] else 0
    return [terms[k] for k in sorted(terms)]


def forms_waiting(session: Session) -> int:
    """Current speeches the word-form tagger has not processed with the current model."""
    return (
        session.scalar(
            select(func.count()).where(
                SR.retired_at.is_(None), SR.forms_model.is_distinct_from(MODEL)
            )
        )
        or 0
    )


def home(session: Session, now: dt.datetime) -> dict:
    terms = common.terms(session)
    current = terms[max(terms)] if terms else None
    day_counts = {
        day: n
        for day, n in session.execute(
            select(SR.date, func.count())
            .where(SR.retired_at.is_(None), SR.date.is_not(None))
            .group_by(SR.date)
        )
        if day is not None
    }
    view: dict = {"last_day": None, "featured": None, "browse": None, "archive": None}
    if current:
        view["browse"] = {
            "mps": session.scalar(select(func.count()).where(models.Mandate.term_id == current.id)),
            "parties": session.scalar(
                select(func.count()).where(
                    models.Organization.parent_id == current.id, models.Organization.type_id == 1
                )
            ),
            "tisky": session.scalar(select(func.count()).where(models.Bill.term_id == current.id)),
            "sittings": session.scalar(
                select(func.count()).where(models.Sitting.term_id == current.id)
            ),
            "term": current.number,
        }
    if not day_counts:
        return view
    dates = sorted(day_counts)
    last = dates[-1]
    view["archive"] = {"from": dates[0].isoformat(), "to": last.isoformat()}
    page = session.scalar(
        select(models.SourcePage)
        .where(models.SourcePage.date == last, models.SourcePage.current_revision_id.is_not(None))
        .order_by(models.SourcePage.term_id.desc(), models.SourcePage.page)
        .limit(1)
    )
    assert page is not None
    term = common.term_by_id(session)[page.term_id]
    pages = session.execute(
        select(models.SourcePage.page, models.SourcePage.status).where(
            models.SourcePage.term_id == page.term_id,
            models.SourcePage.date == last,
        )
    ).all()
    recent = dates[-20:]
    levels = _levels([day_counts[d] for d in recent])
    words = session.scalar(
        select(func.coalesce(func.sum(SR.words), 0)).where(SR.retired_at.is_(None), SR.date == last)
    )
    view["last_day"] = {
        "date": last.isoformat(),
        "term": term.number,
        "sitting": page.sitting_number,
        "first_page": page.page,
        "pages": len(pages),
        "imported_pages": sum(1 for _, s in pages if s == "imported"),
        "speeches": day_counts[last],
        "words": int(words or 0),
        "strip": [
            {"date": d.isoformat(), "speeches": day_counts[d], "level": lvl}
            for d, lvl in zip(recent, levels, strict=True)
        ],
    }
    pool = session.execute(
        select(SR, models.Speech)
        .join(models.Speech, models.Speech.id == SR.speech_id)
        .where(
            SR.retired_at.is_(None),
            SR.date == last,
            SR.words >= FEATURED_MIN_WORDS,
            SR.person_id.is_not(None),
            SR.role != "chair",
        )
        .order_by(SR.id)
    ).all()
    if pool:
        seed = now.strftime("%Y%m%d%H")  # the same choice for everyone within the hour
        index = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(pool)
        featured = search.results_view(session, [pool[index]], [])[0]
        featured["pool"] = len(pool)
        view["featured"] = featured
    return view


def sittings(session: Session, term: common.TermInfo) -> list[dict]:
    metadata = {
        s.number: s
        for s in session.scalars(select(models.Sitting).where(models.Sitting.term_id == term.id))
    }
    days = defaultdict(list)
    for sitting, number, day in session.execute(
        select(
            models.SittingDay.sitting_number, models.SittingDay.day_number, models.SittingDay.date
        )
        .where(models.SittingDay.term_id == term.id)
        .order_by(models.SittingDay.date)
    ):
        days[sitting].append((number, day))
    first_pages = {
        (s, d): (p, imported, total)
        for s, d, p, imported, total in session.execute(
            select(
                models.SourcePage.sitting_number,
                models.SourcePage.day_number,
                func.min(models.SourcePage.page),
                func.count().filter(models.SourcePage.status == "imported"),
                func.count(),
            )
            .where(models.SourcePage.term_id == term.id)
            .group_by(models.SourcePage.sitting_number, models.SourcePage.day_number)
        )
    }
    speech_days = {
        (s, d): n
        for s, d, n in session.execute(
            select(models.Speech.sitting_number, SR.date, func.count())
            .join(models.Speech, models.Speech.id == SR.speech_id)
            .where(SR.term_id == term.id, SR.retired_at.is_(None))
            .group_by(models.Speech.sitting_number, SR.date)
        )
    }
    top: dict[int, list] = defaultdict(list)
    for sitting, item_id, n in session.execute(
        select(models.Speech.sitting_number, SR.agenda_item_id, func.count())
        .join(models.Speech, models.Speech.id == SR.speech_id)
        .where(
            SR.term_id == term.id,
            SR.retired_at.is_(None),
            SR.agenda_item_id.is_not(None),
            SR.role != "chair",
        )
        .group_by(models.Speech.sitting_number, SR.agenda_item_id)
        .order_by(models.Speech.sitting_number, func.count().desc())
    ):
        if len(top[sitting]) < 3:
            top[sitting].append((item_id, n))
    items = {
        i.id: i
        for i in session.scalars(
            select(models.AgendaItem).where(
                models.AgendaItem.id.in_([i for t in top.values() for i, _ in t])
            )
        )
    }
    bills = {
        b.id: b
        for b in session.scalars(
            select(models.Bill).where(models.Bill.id.in_({i.bill_id for i in items.values()}))
        )
    }
    all_counts = [n for n in speech_days.values()]
    out = []
    for number in sorted(set(days) | set(metadata), reverse=True):
        sitting_days = days[number]
        sitting = metadata.get(number)
        first_day = (
            sitting_days[0][1]
            if sitting_days
            else (sitting.starts_at.date() if sitting and sitting.starts_at else None)
        )
        last_day = (
            sitting_days[-1][1]
            if sitting_days
            else (sitting.ends_at.date() if sitting and sitting.ends_at else first_day)
        )
        counts = [speech_days.get((number, d), 0) for _, d in sitting_days]
        levels = (
            _levels(counts)
            if len(all_counts) < 3
            else [0 if n <= 0 else _scale(n, all_counts) for n in counts]
        )
        day_views = []
        for (day_number, day), n, level in zip(sitting_days, counts, levels, strict=True):
            first, imported, total = first_pages.get((number, day_number), (None, 0, 0))
            day_views.append(
                {
                    "date": day.isoformat(),
                    "speeches": n,
                    "level": level,
                    "page": first,
                    "state": "spoke" if imported else "pending",
                    "imported_pages": imported,
                    "pages": total,
                }
            )
        out.append(
            {
                "number": number,
                "term": term.number,
                "from": first_day.isoformat() if first_day else None,
                "to": last_day.isoformat() if last_day else None,
                "days": len(sitting_days),
                "speeches": sum(counts),
                "pending": sum(
                    1 for d in day_views if not d["pages"] or d["imported_pages"] < d["pages"]
                ),
                "top": [
                    (
                        common.agenda_view(items[i], bills.get(items[i].bill_id or -1), term.number)
                        or {}
                    )
                    | {"speeches": n}
                    for i, n in top.get(number, [])
                    if i in items
                ],
                "day_levels": day_views,
            }
        )
    return out


def _scale(n: int, values: list[int]) -> int:
    positive = sorted(v for v in values if v > 0)
    t1, t2 = statistics.quantiles(positive, n=3)
    return 1 if n <= t1 else 2 if n <= t2 else 3
