"""Full-text search over current speech revisions.

Queries use PostgreSQL's websearch syntax with the accent-insensitive 'rozprava'
configuration: words, "quoted phrases", OR and -exclusions. Everything a user
types is a bound parameter. Facets and the date histogram count the complete
filtered match set, not just the visible page.
"""

import datetime as dt
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from sqlalchemy import (
    ColumnElement,
    Date,
    and_,
    cast,
    exists,
    func,
    literal_column,
    or_,
    select,
    true,
)
from sqlalchemy.orm import Session

from rozprava import models
from rozprava.queries import common
from rozprava.typography import MONTHS_GENITIVE, fold

PER_PAGE = 20
MAX_QUERY = 200
MAX_PAGE = 500
MAX_VALUES = 20
SORTS = ("relevance", "nejnovejsi")
EXCERPT = 280
SR = models.SpeechRevision
MONTHS_SHORT = ("led", "úno", "bře", "dub", "kvě", "čvn", "čvc", "srp", "zář", "říj", "lis", "pro")


@dataclass(frozen=True)
class SearchFilters:
    q: str = ""
    terms: tuple[int, ...] = ()  # obdobi
    people: tuple[int, ...] = ()  # poslanec (person ids)
    clubs: tuple[str, ...] = ()  # klub (party keys, see parties.py)
    bills: tuple[tuple[int, int], ...] = ()  # tisk "10-285": (term, number)
    date_from: dt.date | None = None  # od
    date_to: dt.date | None = None  # do
    sort: str = "relevance"  # razeni
    page: int = 1  # stranka

    @classmethod
    def parse(
        cls, params: Mapping[str, Sequence[str]], known_terms: Sequence[int] = (9, 10)
    ) -> tuple["SearchFilters", list[str]]:
        """Validate URL parameters; invalid values are dropped with a Czech explanation."""
        errors: list[str] = []

        def values(key: str) -> list[str]:
            found = [v.strip() for v in params.get(key, []) if v.strip()]
            if len(found) > MAX_VALUES:
                errors.append(f"Příliš mnoho hodnot filtru „{key}“; použito prvních {MAX_VALUES}.")
            return found[:MAX_VALUES]

        def one(key: str) -> str:
            found = values(key)
            return found[0] if found else ""

        q = re.sub(r"\s+", " ", one("q"))
        if len(q) > MAX_QUERY:
            errors.append(f"Dotaz je delší než {MAX_QUERY} znaků; zkrátili jsme ho.")
            q = q[:MAX_QUERY]

        terms = []
        for value in values("obdobi"):
            if re.fullmatch(r"[0-9]{1,2}", value) and int(value) in known_terms:
                terms.append(int(value))
            else:
                errors.append(f"Volební období „{value}“ neznáme; filtr jsme vynechali.")
        people = []
        for value in values("poslanec"):
            if re.fullmatch(r"[0-9]{1,7}", value):
                people.append(int(value))
            else:
                errors.append(f"Řečníka „{value}“ jsme nepoznali; filtr jsme vynechali.")
        clubs = [v for v in values("klub") if len(v) <= 40]
        bills = []
        for value in values("tisk"):
            match = re.fullmatch(r"(\d{1,2})-(\d{1,5})", value)
            if match and int(match.group(1)) in known_terms:
                bills.append((int(match.group(1)), int(match.group(2))))
            else:
                errors.append(f"Tisk „{value}“ má být ve tvaru období-číslo, např. 10-285.")

        def day(key: str, label: str) -> dt.date | None:
            value = one(key)
            if not value:
                return None
            try:
                return dt.date.fromisoformat(value)
            except ValueError:
                errors.append(f"Datum „{label}“ má být ve tvaru RRRR-MM-DD; filtr jsme vynechali.")
                return None

        date_from, date_to = day("od", "od"), day("do", "do")
        if date_from and date_to and date_from > date_to:
            errors.append("Začátek období je po jeho konci; data jsme prohodili.")
            date_from, date_to = date_to, date_from
        sort = one("razeni") or "relevance"
        if sort not in SORTS:
            errors.append("Neznámé řazení; řadíme podle relevance.")
            sort = "relevance"
        page_text = one("stranka") or "1"
        page = int(page_text) if re.fullmatch(r"[0-9]{1,3}", page_text) else 0
        if not 1 <= page <= MAX_PAGE:
            errors.append(f"Stránka „{page_text}“ neexistuje; zobrazujeme první.")
            page = 1
        return (
            cls(
                q=q,
                terms=tuple(dict.fromkeys(terms)),
                people=tuple(dict.fromkeys(people)),
                clubs=tuple(dict.fromkeys(clubs)),
                bills=tuple(dict.fromkeys(bills)),
                date_from=date_from,
                date_to=date_to,
                sort=sort,
                page=page,
            ),
            errors,
        )

    def params(self, **changes: object) -> dict[str, object]:
        """URL parameters for these filters with changes applied (page resets to 1)."""
        data = replace(self, **({"page": 1} | changes))  # type: ignore[arg-type]
        params: dict[str, object] = {}
        if data.q:
            params["q"] = data.q
        if data.terms:
            params["obdobi"] = [str(t) for t in data.terms]
        if data.people:
            params["poslanec"] = [str(p) for p in data.people]
        if data.clubs:
            params["klub"] = list(data.clubs)
        if data.bills:
            params["tisk"] = [f"{t}-{n}" for t, n in data.bills]
        if data.date_from:
            params["od"] = data.date_from.isoformat()
        if data.date_to:
            params["do"] = data.date_to.isoformat()
        if data.sort != "relevance":
            params["razeni"] = data.sort
        if data.page != 1:
            params["stranka"] = str(data.page)
        return params

    def toggled(self, key: str, value: object) -> dict[str, object]:
        current = getattr(self, key)
        new = tuple(v for v in current if v != value) if value in current else (*current, value)
        return self.params(**{key: new})


def query_terms(q: str) -> list[str]:
    """Words and phrases to highlight: what the query asks for, minus exclusions and OR."""
    out = []
    for match in re.finditer(r'(-?)"([^"]+)"|(-?)(\S+)', q):
        if match.group(2):
            if not match.group(1):
                out.append(match.group(2).strip())
            continue
        word = match.group(4).strip(".,;:!?()„“\"'")
        if match.group(3) or not word or word.casefold() == "or":
            continue
        out.append(word)
    return [t for t in dict.fromkeys(out) if t]


def _tsquery(q: str):
    return func.websearch_to_tsquery(literal_column("'rozprava'::regconfig"), q)


def conditions(filters: SearchFilters, terms: Mapping[int, common.TermInfo], clubs: common.Clubs):
    where: list[ColumnElement[bool]] = [SR.retired_at.is_(None)]
    if filters.q:
        where.append(SR.search.op("@@")(_tsquery(filters.q)))
    if filters.terms:
        where.append(SR.term_id.in_([terms[t].id for t in filters.terms if t in terms]))
    if filters.people:
        where.append(SR.person_id.in_(filters.people))
    if filters.clubs:
        m = models.Membership
        where.append(
            exists(
                select(1).where(
                    m.person_id == SR.person_id,
                    m.organization_id.in_(clubs.orgs_for(filters.clubs) or [-1]),
                    cast(m.valid_from, Date) <= SR.date,
                    or_(m.valid_to.is_(None), cast(m.valid_to, Date) >= SR.date),
                )
            )
        )
    if filters.bills:
        bill_match = or_(
            *(
                and_(models.Bill.term_id == terms[t].id, models.Bill.number == n)
                for t, n in filters.bills
                if t in terms
            )
        )
        where.append(
            SR.agenda_item_id.in_(
                select(models.AgendaItem.id)
                .join(models.Bill, models.Bill.id == models.AgendaItem.bill_id)
                .where(bill_match)
            )
        )
    if filters.date_from:
        where.append(SR.date >= filters.date_from)
    if filters.date_to:
        where.append(SR.date <= filters.date_to)
    return where


@dataclass
class SearchPage:
    filters: SearchFilters
    errors: list[str]
    total: int = 0
    results: list[dict] = field(default_factory=list)
    facets: dict = field(default_factory=dict)
    highlights: list[str] = field(default_factory=list)

    @property
    def pages(self) -> int:
        return max(1, math.ceil(self.total / PER_PAGE))

    @property
    def out_of_range(self) -> bool:
        return self.total > 0 and self.filters.page > self.pages


def search(session: Session, filters: SearchFilters, errors: list[str]) -> SearchPage:
    terms = common.terms(session)
    clubs = common.Clubs(session)
    page = SearchPage(filters, list(errors), highlights=query_terms(filters.q))
    where = conditions(filters, terms, clubs)
    page.total = session.scalar(select(func.count()).select_from(SR).where(*where)) or 0
    page.facets = _facets(session, where, clubs, filters, terms)
    if page.total == 0 or page.out_of_range:
        return page

    rank = func.ts_rank_cd(SR.search, _tsquery(filters.q)) if filters.q else None
    order = (
        [rank.desc(), SR.date.desc(), SR.id.desc()]
        if rank is not None and filters.sort == "relevance"
        else [SR.date.desc(), SR.id.desc()]
    )
    rows = session.execute(
        select(SR, models.Speech)
        .join(models.Speech, models.Speech.id == SR.speech_id)
        .where(*where)
        .order_by(*order)
        .limit(PER_PAGE)
        .offset((filters.page - 1) * PER_PAGE)
    ).all()
    page.results = results_view(
        session, rows, page.highlights, offset=(filters.page - 1) * PER_PAGE
    )
    return page


def results_view(session: Session, rows, highlights: Sequence[str], offset: int = 0) -> list[dict]:
    """Result objects (DESIGN.md §7.6) for (SpeechRevision, Speech) rows."""
    by_id = common.term_by_id(session)
    person_ids = {r.person_id for r, _ in rows if r.person_id}
    people = {
        p.id: p
        for p in session.scalars(select(models.Person).where(models.Person.id.in_(person_ids)))
    }
    clubs = common.Clubs(session, person_ids)
    items = {
        i.id: i
        for i in session.scalars(
            select(models.AgendaItem).where(
                models.AgendaItem.id.in_({r.agenda_item_id for r, _ in rows if r.agenda_item_id})
            )
        )
    }
    bills = {
        b.id: b
        for b in session.scalars(
            select(models.Bill).where(models.Bill.id.in_({i.bill_id for i in items.values()}))
        )
    }
    paragraphs: dict[int, list[models.SpeechParagraph]] = {}
    for p in session.scalars(
        select(models.SpeechParagraph)
        .where(models.SpeechParagraph.revision_id.in_([r.id for r, _ in rows]))
        .order_by(models.SpeechParagraph.revision_id, models.SpeechParagraph.position)
    ):
        paragraphs.setdefault(p.revision_id, []).append(p)

    out = []
    for n, (revision, speech) in enumerate(rows, start=offset + 1):
        term = by_id[revision.term_id]
        person = people.get(revision.person_id) if revision.person_id else None
        item = items.get(revision.agenda_item_id) if revision.agenda_item_id else None
        paragraph, excerpt, lead, trail = _excerpt(paragraphs.get(revision.id, []), highlights)
        slug = common.catalog_slug(term.number, speech.sitting_number, speech.page, speech.anchor)
        page_number = paragraph.page if paragraph else revision.first_page
        out.append(
            {
                "n": n,
                "id": revision.id,
                "speaker": common.speaker_view(
                    person,
                    revision.label,
                    clubs.party_on(revision.person_id, revision.date),
                    fallback=None,
                ),
                "role": revision.role,
                "text": excerpt,
                "lead": lead,
                "trail": trail,
                "date": revision.date.isoformat() if revision.date else "",
                "term": term.number,
                "term_year": term.year,
                "sitting": speech.sitting_number,
                "page": page_number,
                "quote_source": f"paragraph-{slug}-{paragraph.position + 1}" if paragraph else None,
                "quote_start": paragraph.text.find(excerpt) if paragraph else None,
                "quote_end": paragraph.text.find(excerpt) + len(excerpt) if paragraph else None,
                "page_revision": paragraph.page_revision_id if paragraph else None,
                "anchor": f"p-{slug}-{paragraph.position + 1}" if paragraph else f"s-{slug}",
                "catalog": common.catalog(
                    term.number, speech.sitting_number, speech.page, speech.anchor
                ),
                "catalog_slug": slug,
                "revision": revision.id,
                "status": common.status_line(revision.stage),
                "incomplete": revision.incomplete,
                "words": revision.words,
                "psp_url": common.psp_page_url(term.year, speech.sitting_number, page_number),
                "agenda": common.agenda_view(
                    item, bills.get(item.bill_id) if item and item.bill_id else None, term.number
                ),
            }
        )
    return out


def _word_pattern(highlights: Sequence[str]) -> re.Pattern[str] | None:
    wanted = sorted({fold(t) for t in highlights if t.strip()}, key=len, reverse=True)
    if not wanted:
        return None
    return re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in wanted) + r")(?!\w)"
    )


def _excerpt(paragraphs: Sequence[models.SpeechParagraph], highlights: Sequence[str]):
    """The first paragraph with a match (or the first), cut to about EXCERPT characters
    around the match at word boundaries. Returns (paragraph, text, lead, trail)."""
    if not paragraphs:
        return None, "", False, False
    pattern = _word_pattern(highlights)
    chosen, start = paragraphs[0], 0
    if pattern:
        for p in paragraphs:
            if match := pattern.search(fold(p.text)):
                chosen, start = p, match.start()
                break
    text = chosen.text
    if len(text) <= EXCERPT:
        return chosen, text, chosen.position > 0, chosen.position < len(paragraphs) - 1
    begin = max(0, start - 60)
    if begin:
        space = text.rfind(" ", 0, begin)
        begin = space + 1 if space > 0 else 0
    end = min(len(text), begin + EXCERPT)
    if end < len(text):
        space = text.rfind(" ", begin, end)
        end = space if space > begin else end
    excerpt = text[begin:end].rstrip(",;:–- ")
    lead = begin > 0 or chosen.position > 0
    trail = end < len(text) or chosen.position < len(paragraphs) - 1
    return chosen, excerpt, lead, trail


def _facets(session, where, clubs: common.Clubs, filters: SearchFilters, terms) -> dict:
    matches = select(SR.id, SR.person_id, SR.date).where(*where).subquery()
    m = models.Membership
    club = (
        select(m.organization_id)
        .where(
            m.person_id == matches.c.person_id,
            m.organization_id.in_(list(clubs.key_of) or [-1]),
            cast(m.valid_from, Date) <= matches.c.date,
            or_(m.valid_to.is_(None), cast(m.valid_to, Date) >= matches.c.date),
        )
        .order_by(m.valid_from.desc())
        .limit(1)
        .lateral()
    )
    by_club: Counter[str] = Counter()
    for org, n in session.execute(
        select(club.c.organization_id, func.count())
        .select_from(matches.outerjoin(club, true()))
        .group_by(club.c.organization_id)
    ):
        if org is not None:
            by_club[clubs.key_of[org]] += n
    for key in filters.clubs:  # selected filters stay visible (and removable) at zero
        by_club.setdefault(key, 0)

    speakers = session.execute(
        select(matches.c.person_id, func.count().label("n"))
        .where(matches.c.person_id.is_not(None))
        .group_by(matches.c.person_id)
        .order_by(func.count().desc(), matches.c.person_id)
        .limit(12)
    ).all()
    counts = {p: n for p, n in speakers}
    for person in filters.people:
        counts.setdefault(person, 0)
    names = {
        p.id: p
        for p in session.scalars(select(models.Person).where(models.Person.id.in_(list(counts))))
    }

    month = func.to_char(matches.c.date, literal_column("'YYYY-MM'"))
    months = dict(
        session.execute(
            select(month, func.count()).where(matches.c.date.is_not(None)).group_by(month)
        ).all()
    )
    chosen_terms = [terms[t] for t in (filters.terms or sorted(terms)) if t in terms]
    first = min((t.started_on for t in chosen_terms), default=dt.date.today())
    last = max((t.ended_on or dt.date.today() for t in chosen_terms), default=dt.date.today())
    span = []
    y, mo = first.year, first.month
    while (y, mo) <= (last.year, last.month):
        key = f"{y:04d}-{mo:02d}"
        span.append(
            {"month": key, "count": months.get(key, 0), "label": f"{MONTHS_SHORT[mo - 1]} {y}"}
        )
        y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)

    party_rows = sorted(by_club.items(), key=lambda kv: (-kv[1], fold(kv[0])))
    speaker_rows = sorted(
        counts.items(),
        key=lambda kv: (-kv[1], fold(names[kv[0]].surname) if kv[0] in names else ""),
    )
    return {
        "parties": [
            {
                "value": k,
                "n": n,
                "selected": k in filters.clubs,
                "params": filters.toggled("clubs", k),
            }
            for k, n in party_rows
        ],
        "parties_max": max((n for _, n in party_rows), default=0) or 1,
        "speakers": [
            {
                "value": str(p),
                "label": f"{names[p].forename} {names[p].surname}" if p in names else str(p),
                "n": n,
                "selected": p in filters.people,
                "params": filters.toggled("people", p),
            }
            for p, n in speaker_rows
        ],
        "speakers_max": max((n for _, n in speaker_rows), default=0) or 1,
        "months": span,
        "months_max": max((m["count"] for m in span), default=0) or 1,
    }


def month_label(month: str) -> str:
    return f"{MONTHS_GENITIVE[int(month[5:]) - 1]} {month[:4]}"
