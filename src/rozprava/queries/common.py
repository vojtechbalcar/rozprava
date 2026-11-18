"""View data shared by every page: speakers, clubs, catalogue numbers, source links.

Query modules return plain dicts shaped like the design preview's data
(preview/data.json), so the same templates render both.
"""

import datetime as dt
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from rozprava import models, titles
from rozprava.ingest.identity import Spell, label_names, spell_on
from rozprava.parties import party_for_club
from rozprava.typography import fold

PLAIN_ROLES = {"poslanec", "poslankyně"}
UNKNOWN_SPEAKER = "Neurčený řečník"


@dataclass(frozen=True)
class TermInfo:
    id: int
    number: int
    year: int
    started_on: dt.date
    ended_on: dt.date | None

    @property
    def label(self) -> str:
        end = f"{self.ended_on.year}" if self.ended_on else ""
        return f"{self.number}. ({self.year}–{end})"


def terms(session: Session) -> dict[int, TermInfo]:
    """Terms by number (9, 10)."""
    return {
        t.number: TermInfo(t.id, t.number, t.year, t.started_on, t.ended_on)
        for t in session.scalars(select(models.Term).order_by(models.Term.number))
    }


def term_by_id(session: Session) -> dict[int, TermInfo]:
    return {t.id: t for t in terms(session).values()}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(text)).strip("-")


def person_slug(person_id: int, forename: str, surname: str) -> str:
    return f"{person_id}-{slugify(f'{forename} {surname}')}"


def parse_slug(slug: str) -> int | None:
    match = re.match(r"^(\d{1,7})(?:-[a-z0-9-]*)?$", slug)
    return int(match.group(1)) if match else None


def role_from_label(label: str | None, name: str) -> str | None:
    """'Místopředseda PSP' from 'Místopředseda PSP Jan Skopeček'; None for plain MPs."""
    if not label or not label_names(label, name):
        return None
    role = re.sub(r"\s+", " ", label).strip()[: -len(name)].strip()
    return None if not role or role.casefold() in PLAIN_ROLES else role


def catalog(term: int, sitting: int, page: int, anchor: int) -> dict:
    return {"term": term, "sitting": sitting, "page": page, "order": anchor}


def catalog_slug(term: int, sitting: int, page: int, anchor: int) -> str:
    return titles.catalog_slug(term, sitting, page, anchor)


def parse_catalog(slug: str) -> tuple[int, int, int, int] | None:
    match = re.fullmatch(r"(\d{1,2})-(\d{3})-(\d{4})-(\d{1,3})", slug)
    return tuple(int(g) for g in match.groups()) if match else None  # type: ignore[return-value]


def psp_page_url(year: int, sitting: int, page: int, anchor: int | None = None) -> str:
    url = f"https://www.psp.cz/eknih/{year}ps/stenprot/{sitting:03d}schuz/s{sitting:03d}{page:03d}.htm"
    return f"{url}#r{anchor}" if anchor and 0 < anchor < 100 else url


def status_line(stage: str) -> str | None:
    """The source's own wording of its publication stage (DESIGN.md §7.6)."""
    return {
        "draft": "Neprošlo jazykovou korekturou, neautorizováno!",
        "edited": "Neautorizováno!",
    }.get(stage)


class Clubs:
    """Club organs of the loaded terms, and dated memberships, for party labels."""

    def __init__(self, session: Session, person_ids: Iterable[int] | None = None):
        rows = session.execute(
            select(models.Organization.id, models.Organization.abbr).where(
                models.Organization.type_id == 1,
                models.Organization.parent_id.in_(select(models.Term.id)),
            )
        ).all()
        self.key_of: dict[int, str] = {org: party_for_club(abbr) for org, abbr in rows}
        query = select(models.Membership).where(
            models.Membership.organization_id.in_(list(self.key_of))
        )
        if person_ids is not None:
            query = query.where(models.Membership.person_id.in_(list(set(person_ids))))
        self.spells: dict[int, list[Spell]] = defaultdict(list)
        for m in session.scalars(query):
            self.spells[m.person_id].append(Spell(m.organization_id, m.valid_from, m.valid_to))

    def orgs_for(self, keys: Iterable[str]) -> list[int]:
        wanted = set(keys)
        return [org for org, key in self.key_of.items() if key in wanted]

    def party_on(self, person_id: int | None, day: dt.date | None) -> str | None:
        """Party key of the person's club on that day; None when unknown."""
        if person_id is None or day is None:
            return None
        noon = dt.datetime.combine(day, dt.time(12))
        spell = spell_on(self.spells.get(person_id, []), noon)
        return self.key_of.get(spell.organization_id) if spell else None


def speaker_view(
    person: models.Person | None,
    label: str | None,
    party: str | None,
    role: str | None = None,
    fallback: str | None = None,
) -> dict:
    if person is None:
        return {
            "id": None,
            "name": fallback or label or UNKNOWN_SPEAKER,
            "slug": None,
            "party": None,
            "role": None,
            "known": False,
        }
    name = f"{person.forename} {person.surname}"
    return {
        "id": person.id,
        "name": name,
        "slug": person_slug(person.id, person.forename, person.surname),
        "party": party,
        "role": role if role is not None else role_from_label(label, name),
        "known": True,
    }


def agenda_view(item: models.AgendaItem | None, bill: models.Bill | None, term: int) -> dict | None:
    if item is None:
        return None
    full = f"{item.title} {item.title_suffix}".strip()
    return {
        "id": str(item.id),
        "number": item.number,
        "title": item.title,
        "short": titles.short_title(
            item.title,
            bill.number if bill else None,
            bill.short_title if bill else None,
            term=term,
        ),
        "tisk": bill.number if bill else None,
        "term": term,
        "reading": titles.reading(full),
    }


def last_import(session: Session) -> str | None:
    """Local time of the last successful import run, as 'YYYY-MM-DDTHH:MM'."""
    finished = session.scalar(
        select(models.ImportRun.finished_at)
        .where(models.ImportRun.status == "succeeded")
        .order_by(models.ImportRun.finished_at.desc())
        .limit(1)
    )
    return finished.astimezone().strftime("%Y-%m-%dT%H:%M") if finished else None
