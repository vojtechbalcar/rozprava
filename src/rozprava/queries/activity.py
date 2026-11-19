"""Speaking activity and voting participation, per MP and sitting day.

Rules (explained on the methodology page):

- Activity counts each assembled speech once, even across pages, and leaves out
  speeches whose role is known to be chairing; unknown roles stay included.
- Activity levels are quartiles of positive MP-day word counts in the term, on
  one scale for everyone. While transcripts are incomplete they are provisional.
- Voting participation is registration (A/B/N/C/F/K) at eligible votes: normal
  votes (not manual R, not technical-fault E), not declared invalid, within the
  person's mandate. @ and M count as absent; W (before the oath) is excluded.
  A missing record is unknown, never absence; with any unknown records the
  percentage is withheld and the known counts shown instead.
- A day with a registered vote is "present"; a day whose eligible votes are all
  known and none registered is "absent"; anything else is "unknown".
"""

import datetime as dt
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import Date, and_, cast, func, or_, select
from sqlalchemy.orm import Session

from rozprava import models
from rozprava.ingest.metadata import ABSENT, BEFORE_OATH, REGISTERED

SR = models.SpeechRevision


@dataclass
class Participation:
    registered: int = 0
    absent: int = 0
    unknown: int = 0  # eligible votes without a record

    @property
    def known(self) -> int:
        return self.registered + self.absent

    @property
    def percent(self) -> float | None:
        if self.unknown or not self.known:
            return None
        return 100 * self.registered / self.known


@dataclass
class Day:
    date: dt.date
    sittings: list[int] = field(default_factory=list)
    speeches: int = 0
    words: int = 0
    registered: int = 0
    eligible: int = 0
    recorded: int = 0  # eligible votes with a record

    def state(self) -> str:
        if self.speeches:
            return "spoke"
        if self.registered:
            return "present"
        if self.eligible and self.recorded == self.eligible:
            return "absent"
        return "unknown"


@dataclass
class TermActivity:
    """Everything the directory and profiles need for one term, computed together."""

    term_id: int
    days: list[dt.date]  # sitting days, ascending
    sittings_on: dict[dt.date, list[int]]
    quartiles: tuple[float, float, float] | None
    complete_days: set[dt.date]  # every transcript page of the day imported
    per_person: dict[int, dict[dt.date, Day]]
    participation: dict[int, Participation]  # by person id
    speeches: dict[int, int]
    words: dict[int, int]
    longest: dict[int, int]

    def level(self, words: int) -> int:
        if not self.quartiles or words <= 0:
            return 1
        q1, q2, q3 = self.quartiles
        return 1 if words <= q1 else 2 if words <= q2 else 3 if words <= q3 else 4

    @property
    def provisional(self) -> bool:
        return not self.days or not set(self.days).issubset(self.complete_days)

    def day_view(self, person_id: int, day: dt.date) -> dict:
        d = self.per_person.get(person_id, {}).get(day) or Day(day)
        state = d.state()
        return {
            "date": day.isoformat(),
            "sittings": self.sittings_on.get(day, []),
            "state": state,
            "level": self.level(d.words) if state == "spoke" else 0,
            "speeches": d.speeches,
            "words": d.words,
            "votes_cast": d.registered,
            "votes_total": d.eligible,
            "votes_unknown": d.eligible - d.recorded,
            "complete": day in self.complete_days,
        }


def term_activity(session: Session, term_id: int) -> TermActivity:
    days_rows = session.execute(
        select(models.SittingDay.date, models.SittingDay.sitting_number)
        .where(models.SittingDay.term_id == term_id)
        .order_by(models.SittingDay.date)
    ).all()
    sittings_on: dict[dt.date, list[int]] = defaultdict(list)
    for day, sitting in days_rows:
        if sitting not in sittings_on[day]:
            sittings_on[day].append(sitting)
    days = sorted(sittings_on)

    page = models.SourcePage
    complete = set(
        session.scalars(
            select(page.date)
            .where(page.term_id == term_id)
            .group_by(page.date)
            .having(
                func.count()
                == func.count().filter(
                    and_(
                        page.status == "imported",
                        page.current_revision_id.is_not(None),
                        page.assembled_revision_id == page.current_revision_id,
                    )
                )
            )
        )
    )

    per_person: dict[int, dict[dt.date, Day]] = defaultdict(dict)
    speeches: dict[int, int] = defaultdict(int)
    words: dict[int, int] = defaultdict(int)
    longest: dict[int, int] = defaultdict(int)
    for person, day, n, total, most in session.execute(
        select(SR.person_id, SR.date, func.count(), func.sum(SR.words), func.max(SR.words))
        .where(
            SR.term_id == term_id,
            select(models.Mandate.id)
            .where(
                models.Mandate.term_id == term_id,
                models.Mandate.person_id == SR.person_id,
                or_(
                    models.Mandate.valid_from.is_(None),
                    SR.date >= cast(models.Mandate.valid_from, Date),
                ),
                or_(
                    models.Mandate.valid_to.is_(None),
                    SR.date <= cast(models.Mandate.valid_to, Date),
                ),
            )
            .exists(),
            SR.retired_at.is_(None),
            SR.person_id.is_not(None),
            SR.role != "chair",
            SR.date.is_not(None),
        )
        .group_by(SR.person_id, SR.date)
    ):
        entry = per_person[person].setdefault(day, Day(day))
        entry.speeches, entry.words = n, int(total or 0)
        speeches[person] += n
        words[person] += int(total or 0)
        longest[person] = max(longest[person], int(most or 0))
    positive = sorted(d.words for p in per_person.values() for d in p.values() if d.words > 0)
    quartiles = None
    if len(positive) >= 4:
        q = statistics.quantiles(positive, n=4)
        quartiles = (q[0], q[1], q[2])

    participation: dict[int, Participation] = defaultdict(Participation)
    vote_day = cast(models.Vote.held_at, Date)
    v, r, m = models.Vote, models.VoteRecord, models.Mandate
    eligible_vote = and_(
        v.term_id == term_id,
        v.kind == "N",
        v.invalidated.is_(False),
        or_(m.valid_from.is_(None), v.held_at >= m.valid_from),
        or_(m.valid_to.is_(None), v.held_at <= m.valid_to),
    )
    rows = session.execute(
        select(
            m.person_id,
            vote_day,
            func.count(v.id),
            func.count(r.code).filter(r.code.in_(sorted(REGISTERED | ABSENT))),
            func.count().filter(r.code.in_(sorted(REGISTERED))),
            func.count().filter(r.code.in_(sorted(ABSENT))),
            func.count().filter(r.code == BEFORE_OATH),
        )
        .select_from(m)
        .join(v, eligible_vote)
        .outerjoin(r, and_(r.vote_id == v.id, r.mandate_id == m.id))
        .where(m.term_id == term_id)
        .group_by(m.person_id, vote_day)
    ).all()
    for person, day, total, recorded, registered, absent, before_oath in rows:
        eligible = total - before_oath
        entry = per_person[person].setdefault(day, Day(day))
        entry.eligible, entry.recorded, entry.registered = eligible, recorded, registered
        p = participation[person]
        p.registered += registered
        p.absent += absent
        p.unknown += eligible - recorded
    return TermActivity(
        term_id=term_id,
        days=days,
        sittings_on=dict(sittings_on),
        quartiles=quartiles,
        complete_days={d for d in complete if d is not None},
        per_person=dict(per_person),
        participation=dict(participation),
        speeches=dict(speeches),
        words=dict(words),
        longest=dict(longest),
    )


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None
