"""Full-text search over current speech revisions.

Queries use websearch syntax with the accent-insensitive 'rozprava' configuration:
words, "quoted phrases", OR and -exclusions. An unquoted word matches as typed
and, through the lemmas the ingest job tagged (morphology.py), in its other forms:
"důchod" finds "důchodu". Quoted text matches exactly. Filler words ("jak", "se")
are left out of longer queries. When few speeches contain every word of a query of
three or more, it also finds those lacking one, ranked after the complete matches.
Everything a user types is a bound parameter. Facets and the date histogram count
the complete filtered match set, not just the visible page.
"""

import datetime as dt
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import reduce
from itertools import combinations

from sqlalchemy import (
    ColumnElement,
    Date,
    Integer,
    Text,
    and_,
    cast,
    exists,
    false,
    func,
    literal,
    literal_column,
    or_,
    select,
    true,
)
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.orm import Session

from rozprava import models
from rozprava.morphology import lemma_query
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


@dataclass(frozen=True)
class Term:
    text: str
    phrase: bool = False  # in quotation marks: this exact wording only
    negated: bool = False


def parse_query(q: str) -> list[list[Term]]:
    """Alternatives (OR) of terms that must all match, in websearch_to_tsquery's syntax:
    words, "quoted phrases", OR between alternatives and -exclusions."""
    groups: list[list[Term]] = [[]]
    for match in _QUERY_TOKEN.finditer(q):
        if match.group("quoted") is not None:
            phrase = match.group("quoted").strip()
            if phrase:
                groups[-1].append(Term(phrase, phrase=True, negated=bool(match.group("minus"))))
            continue
        word = match.group("word")
        if word.casefold() == "or":
            if groups[-1]:
                groups.append([])
            continue
        negated = word.startswith("-")
        word = word.lstrip("-").strip(PUNCTUATION)
        if word:
            groups[-1].append(Term(word, negated=negated))
    return [group for group in groups if group]


_QUERY_TOKEN = re.compile(r'(?P<minus>-?)"(?P<quoted>[^"]*)"?|(?P<word>\S+)')
PUNCTUATION = ".,;:!?()[]„“”‚‘’\"'…–—"


def query_terms(q: str) -> list[str]:
    """Words and phrases to highlight: what the query asks for, minus exclusions and OR."""
    return list(dict.fromkeys(t.text for group in parse_query(q) for t in group if not t.negated))


# Czech function words, accent-free: pronouns, prepositions, conjunctions, particles
# and forms of "být". They carry no topic, so a query leaves them out when it has
# other words. Not here: "byt" (a flat), "moc" (power), "ano" (also the party ANO).
FILLER = frozenset(
    """
    a aby ac ackoli ale ani asi avsak az bez behem bude budeme budete budes budou budu
    by bych bychom bys byste byl byla byli bylo byly cem cemu ceho ci cim co coz do i
    jak jaka jake jakeho jakem jakemu jaci jaky jakych jakym jakymi jakou jako je jeho
    jej jeji jejich jemu jen jenom jeste jestli jestlize ji jich jim jimi jiz jsem jsi
    jsme jsou jste k kam kde kdo kdy kdyz ke koho kolik kom komu kteri ktera ktere
    ktereho kterem kteremu kterou ktery kterych kterym kterymi kvuli kym me mezi mi mne
    mnou moje mu muj my na nad nam nami nas nase nebo nejaka nejake nejaky nem nez nich
    nim nimi o od on ona oni ono ony ovsem pak po pod podle pokud potom pouze prave
    prece pres pri pro proc proste protoze s se sebe sebou si sobe sve svou svuj svych
    svym svymi ta tady tak take takze taky tam te tech ted tedy tem temi ten tento teto
    tez tim tito to toho tohoto tom tomto tomu toto totiz tou tu tuto ty tyto u uz v
    vam vami vas vase ve velmi vlastne vsak z za zda ze zde
    """.split()
)


def without_filler(groups: list[list[Term]]) -> tuple[list[list[Term]], list[str]]:
    """Drop filler words from each alternative that asks for something else too.

    Returns the groups and the dropped words as typed. A query made only of filler
    words ("co je to") is searched as typed.
    """
    kept_groups, dropped = [], []
    for group in groups:

        def filler(t: Term) -> bool:
            return not (t.phrase or t.negated) and fold(t.text) in FILLER

        if any(not t.negated and not filler(t) for t in group):
            dropped += [t.text for t in group if filler(t)]
            group = [t for t in group if not filler(t)]
        kept_groups.append(group)
    return kept_groups, list(dict.fromkeys(dropped))


# When fewer speeches than this contain every word of a query of three or more words,
# it also matches speeches lacking one of them (a quarter of a long one). Those with
# every word rank first, so relaxing a query with many full matches would only make
# it broader and slower. The relaxed query needs at most this many word combinations.
RELAX_BELOW = 100
MAX_COMBINATIONS = 64


def needed(words: int) -> int:
    """How many of a query's plain words a speech must contain."""
    if words <= 2:
        return words
    need = words - max(1, words // 4)
    while math.comb(words, need) > MAX_COMBINATIONS:
        need += 1
    return need


# A query word stands for the lemmas behind at least this share of its uses in the
# archive, and a written form is highlighted for a lemma it mostly stands for.
LEMMA_SHARE = 0.2
FORM_SHARE = 0.5
# Without accents, "byt" is a word of its own; "duchodu" is "důchodu" typed plainly.
EXACT_SHARE = 0.01
MAX_LEMMAS = 3
MAX_FORMS = 40


@dataclass
class Expansion:
    lemmas: list[str] = field(default_factory=list)
    forms: list[str] = field(default_factory=list)  # other written forms, for highlighting


def expand(session: Session, words: Iterable[str]) -> dict[str, Expansion]:
    """Lemmas and other forms for query words, from the tagged archive's statistics.

    Keys are lowercase words. Words absent from the archive get no lemmas and
    match only as typed.
    """
    wanted = {w.lower(): fold(w) for w in words}
    if not wanted:
        return {}
    wf = models.WordForm
    candidates: dict[str, list[tuple[str, str, int]]] = {}
    for form, folded, lemma, count in session.execute(
        select(wf.form, wf.folded, wf.lemma, wf.count).where(wf.folded.in_(set(wanted.values())))
    ):
        candidates.setdefault(folded, []).append((form, lemma, count))

    out: dict[str, Expansion] = {}
    for word, folded in wanted.items():
        rows = candidates.get(folded, [])
        exact = [r for r in rows if r[0] == word]
        exact_total = sum(n for *_, n in exact)
        if exact_total and exact_total >= EXACT_SHARE * sum(n for *_, n in rows):
            rows = exact
        by_lemma: Counter[str] = Counter()
        for _, lemma, n in rows:
            by_lemma[lemma] += n
        total = sum(by_lemma.values())
        out[word] = Expansion(
            [k for k, n in by_lemma.most_common() if n >= LEMMA_SHARE * total][:MAX_LEMMAS]
        )

    lemmas = {k for e in out.values() for k in e.lemmas}
    if lemmas:
        total = func.sum(wf.count).over(partition_by=wf.form)
        forms: dict[str, list[tuple[int, str]]] = {}
        for form, lemma, count, form_total in session.execute(
            select(wf.form, wf.lemma, wf.count, total).where(
                wf.form.in_(select(wf.form).where(wf.lemma.in_(lemmas)))
            )
        ):
            if lemma in lemmas and count >= FORM_SHARE * form_total:
                forms.setdefault(lemma, []).append((count, form))
        for word, expansion in out.items():
            ranked = sorted(
                (pair for k in expansion.lemmas for pair in forms.get(k, [])), reverse=True
            )
            expansion.forms = [f for _, f in ranked if f != word][:MAX_FORMS]
    return out


@dataclass
class Query:
    """A parsed query as SQL, with the terms to highlight in results."""

    tsquery: ColumnElement | None = None
    highlights: list[str] = field(default_factory=list)
    expansions: dict[str, Expansion] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)  # filler words left out
    # A query of three or more words, relaxed to speeches that lack some of them:
    # `partial` is (needed, of) plain words and `coverage` one tsquery per word, to
    # rank speeches by how many they contain.
    relaxed: "Query | None" = None
    partial: tuple[int, int] | None = None
    coverage: list[ColumnElement] = field(default_factory=list)

    @classmethod
    def build(cls, session: Session, q: str) -> "Query":
        groups, dropped = without_filler(parse_query(q))
        words = {t.text for group in groups for t in group if not t.phrase}
        expansions = expand(session, words)

        def term_query(term: Term) -> ColumnElement:
            if term.phrase:
                return func.phraseto_tsquery(_CONFIG, term.text)
            part = func.plainto_tsquery(_CONFIG, term.text)
            expansion = expansions.get(term.text.lower(), Expansion())
            if expansion.lemmas:
                part = func.tsquery_or(part, cast(lemma_query(expansion.lemmas), TSQUERY))
            return part

        strict, relaxed, partial, coverage = [], [], None, []
        for group in groups:
            fixed = [
                func.tsquery_not(term_query(t)) if t.negated else term_query(t)
                for t in group
                if t.phrase or t.negated
            ]
            words = [t for t in group if not (t.phrase or t.negated)]
            plain = [term_query(t) for t in words]
            strict.append(reduce(func.tsquery_and, fixed + plain))
            # Filler words are left only in a query of nothing else; it is searched as typed.
            filler_only = any(fold(t.text) in FILLER for t in words)
            need = len(plain) if filler_only else needed(len(plain))
            if need < len(plain):
                partial = max(partial or (0, 0), (need, len(plain)), key=lambda p: p[1])
                coverage += plain
                either = [reduce(func.tsquery_and, c) for c in combinations(plain, need)]
                plain = [reduce(func.tsquery_or, either)]
            relaxed.append(reduce(func.tsquery_and, fixed + plain))

        highlights, shown = [], {}
        for term in (t for group in groups for t in group if not t.negated):
            highlights.append(term.text)
            expansion = expansions.get(term.text.lower())
            if expansion and expansion.forms and not term.phrase:
                highlights += expansion.forms
                shown[term.text] = expansion
        query = cls(highlights=list(dict.fromkeys(highlights)), expansions=shown, dropped=dropped)
        if strict:
            # Build the tsquery text once, so the database does not rebuild it per row.
            built = session.execute(
                select(
                    *(
                        cast(reduce(func.tsquery_or, alternatives), Text)
                        for alternatives in (strict, relaxed)
                    ),
                    *(cast(c, Text) for c in coverage),
                )
            ).one()
            query.tsquery = _tsquery(built[0])
            if partial:
                query.relaxed = replace(
                    query,
                    tsquery=_tsquery(built[1]),
                    partial=partial,
                    coverage=[_tsquery(c) for c in built[2:]],
                )
        return query

    def rank(self) -> list[ColumnElement]:
        """ORDER BY terms for relevance: words present, then PostgreSQL's cover density."""
        if self.tsquery is None:
            return []
        present = [cast(SR.search.op("@@")(c), Integer) for c in self.coverage]
        order = [reduce(lambda a, b: a + b, present).desc()] if present else []
        return [*order, func.ts_rank_cd(SR.search, self.tsquery).desc()]


def _tsquery(value: str) -> ColumnElement:
    return cast(literal(value, Text), TSQUERY)


_CONFIG = literal_column(f"'{models.SEARCH_CONFIG}'::regconfig")


def conditions(
    filters: SearchFilters,
    terms: Mapping[int, common.TermInfo],
    clubs: common.Clubs,
    query: Query | None = None,
):
    where: list[ColumnElement[bool]] = [SR.retired_at.is_(None)]
    if filters.q:
        # A query with nothing searchable in it (only operators) matches nothing.
        tsquery = query.tsquery if query else None
        where.append(SR.search.op("@@")(tsquery) if tsquery is not None else false())
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
    expansions: dict[str, Expansion] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)
    partial: tuple[int, int] | None = None  # relaxed: (needed, of) words
    strict_total: int = 0  # speeches with every word, when relaxed

    @property
    def pages(self) -> int:
        return max(1, math.ceil(self.total / PER_PAGE))

    @property
    def out_of_range(self) -> bool:
        return self.total > 0 and self.filters.page > self.pages


def search(session: Session, filters: SearchFilters, errors: list[str]) -> SearchPage:
    terms = common.terms(session)
    clubs = common.Clubs(session)
    query = Query.build(session, filters.q) if filters.q else Query()
    page = SearchPage(
        filters,
        list(errors),
        highlights=query.highlights,
        expansions=query.expansions,
        dropped=query.dropped,
    )
    where = conditions(filters, terms, clubs, query)
    page.total = session.scalar(select(func.count()).select_from(SR).where(*where)) or 0
    if query.relaxed is not None and page.total < RELAX_BELOW:
        # Few speeches have every word: also show those that lack one (or a quarter).
        relaxed = conditions(filters, terms, clubs, query.relaxed)
        total = session.scalar(select(func.count()).select_from(SR).where(*relaxed)) or 0
        if total > page.total:
            page.strict_total, page.total, page.partial = page.total, total, query.relaxed.partial
            query, where = query.relaxed, relaxed
    page.facets = _facets(session, where, clubs, filters, terms)
    if page.total == 0 or page.out_of_range:
        return page

    rank = query.rank() if filters.sort == "relevance" else []
    order = [*rank, SR.date.desc(), SR.id.desc()]
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
