"""Persist parsed pages and assemble a sitting's speeches, keeping every revision.

A page revision is identified by its parsed content: storing the same content
again reuses it. A new revision becomes current atomically with the caller's
commit; on failure the last good revision stays current and readable.

Assembly rebuilds one sitting from its pages' current revisions. A speech whose
content (text, attribution, agenda, stage …) is unchanged keeps its revision;
otherwise a new revision becomes current and the old one is retired, never
deleted, so citations that pin it keep working. Speeches that no longer appear
have their current revision retired.
"""

import datetime as dt
from collections.abc import Collection
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from rozprava import models
from rozprava.ingest.fetch import Fetched
from rozprava.ingest.identity import People, PersonName
from rozprava.ingest.parser import (
    PARSER_VERSION,
    UNANCHORED_BASE,
    AssembledSpeech,
    PageInput,
    ParsedPage,
    Segment,
    assemble,
    content_hash,
    word_count,
)

CHAIR_KINDS = {2, 4}
SPEAKER_KINDS = {3, 5}


def page_url(term_year: int, sitting: int, page: int) -> str:
    return (
        f"https://www.psp.cz/eknih/{term_year}ps/stenprot/"
        f"{sitting:03d}schuz/s{sitting:03d}{page:03d}.htm"
    )


def store_page(
    session: Session, page: models.SourcePage, fetched: Fetched, parsed: ParsedPage
) -> models.PageRevision:
    """Record a successfully parsed page and make it current (on commit)."""
    revision = session.scalar(
        select(models.PageRevision).where(
            models.PageRevision.source_page_id == page.id,
            models.PageRevision.content_sha256 == parsed.content_sha256,
        )
    )
    if revision is None:
        revision = models.PageRevision(
            source_page_id=page.id,
            url=fetched.url,
            fetched_at=dt.datetime.fromisoformat(fetched.retrieved_at),
            raw_sha256=fetched.sha256,
            content_sha256=parsed.content_sha256,
            stage=parsed.stage,
            status_line=parsed.status_line,
            time_label=parsed.time_label,
            continues=parsed.continues,
            parser_version=PARSER_VERSION,
        )
        session.add(revision)
        session.flush()
        session.add_all(
            models.PageSegment(
                revision_id=revision.id,
                position=s.position,
                anchor=s.anchor,
                label=s.label,
                link_person_id=s.link_person_id,
                link_url=s.link_url,
                paragraphs=list(s.paragraphs),
                heading=s.heading,
            )
            for s in parsed.segments
        )
    page.current_revision_id = revision.id
    page.status = "imported"
    page.unavailable_reason = None
    page.last_error = None
    page.attempts += 1
    page.last_attempt_at = dt.datetime.now(dt.UTC)
    session.flush()
    return revision


def record_failure(
    session: Session, page: models.SourcePage, error: str, unavailable: bool = False
) -> None:
    """Note a failed attempt. A page that already has a revision stays imported."""
    page.attempts += 1
    page.last_attempt_at = dt.datetime.now(dt.UTC)
    page.last_error = error[:2000]
    if page.current_revision_id is None:
        page.status = "unavailable" if unavailable else "failed"
        page.unavailable_reason = error[:500] if unavailable else None
    session.flush()


def parsed_from_revision(revision: models.PageRevision) -> ParsedPage:
    return ParsedPage(
        stage=revision.stage,
        status_line=revision.status_line,
        time_label=revision.time_label,
        continues=revision.continues,
        segments=tuple(
            Segment(
                position=s.position,
                anchor=s.anchor,
                label=s.label,
                link_url=s.link_url,
                link_person_id=s.link_person_id,
                paragraphs=tuple(s.paragraphs),
                heading=s.heading,
            )
            for s in revision.segments
        ),
    )


@dataclass
class Context:
    """What assembly needs beyond the sitting's pages: loaded once per run."""

    people: People
    known_speakers: dict[int, set[int]]  # term id -> people with a mandate or index entry
    agenda_ids: set[int] = field(default_factory=set)

    @classmethod
    def load(cls, session: Session) -> "Context":
        people = People(
            PersonName(i, f, s)
            for i, f, s in session.execute(
                select(models.Person.id, models.Person.forename, models.Person.surname)
            )
        )
        known: dict[int, set[int]] = {}
        for term_id, person_id in session.execute(
            select(models.Mandate.term_id, models.Mandate.person_id)
        ):
            known.setdefault(term_id, set()).add(person_id)
        for term_id, person_id in session.execute(
            select(models.SourcePage.term_id, models.TranscriptIndexEntry.person_id)
            .join(models.SourcePage)
            .where(models.TranscriptIndexEntry.person_id.is_not(None))
            .distinct()
        ):
            known.setdefault(term_id, set()).add(person_id)
        agenda = set(session.scalars(select(models.AgendaItem.id)))
        return cls(people, known, agenda)


@dataclass
class AssemblyResult:
    speeches: int = 0
    new_revisions: int = 0
    retired: int = 0
    unresolved: list[str] = field(default_factory=list)


def _role(kind: int | None) -> str:
    if kind in CHAIR_KINDS:
        return "chair"
    if kind in SPEAKER_KINDS:
        return "speaker"
    return "unknown"


def assemble_sitting(
    session: Session, term_id: int, sitting: int, context: Context
) -> AssemblyResult:
    result = AssemblyResult()
    pages = session.scalars(
        select(models.SourcePage)
        .where(
            models.SourcePage.term_id == term_id,
            models.SourcePage.sitting_number == sitting,
            models.SourcePage.current_revision_id.is_not(None),
        )
        .order_by(models.SourcePage.page)
    ).all()
    revisions = {
        r.id: r
        for r in session.scalars(
            select(models.PageRevision)
            .where(models.PageRevision.id.in_([p.current_revision_id for p in pages]))
            .options(selectinload(models.PageRevision.segments))
        )
    }
    by_number = {p.page: p for p in pages}
    index = {
        (e.source_page_id, e.anchor): e
        for e in session.scalars(
            select(models.TranscriptIndexEntry).where(
                models.TranscriptIndexEntry.source_page_id.in_([p.id for p in pages])
            )
        )
    }
    known: Collection[int] = context.known_speakers.get(term_id, set())
    inputs = [
        PageInput(p.page, p.current_revision_id, parsed_from_revision(revisions[r]))
        for p in pages
        if (r := p.current_revision_id) is not None
    ]
    existing = {
        (s.page, s.anchor): s
        for s in session.scalars(
            select(models.Speech).where(
                models.Speech.term_id == term_id, models.Speech.sitting_number == sitting
            )
        )
    }
    seen: set[tuple[int, int]] = set()
    now = dt.datetime.now(dt.UTC)
    for assembled in assemble(inputs):
        start = by_number[assembled.page]
        entry = (
            index.get((start.id, assembled.anchor))
            if 0 < assembled.anchor < UNANCHORED_BASE
            else None
        )
        attribution = context.people.resolve(
            assembled.label or assembled.continues,
            link_person_id=assembled.link_person_id,
            index_person_id=entry.person_id if entry else None,
            known_speakers=known,
        )
        agrees = entry is not None and attribution.person_id == entry.person_id
        if attribution.person_id is None:
            result.unresolved.append(
                f"{sitting}/{assembled.page}/{assembled.anchor}: "
                f"{assembled.label or assembled.continues or '(no label)'}"
            )
        values = _revision_values(assembled, start, attribution, entry if agrees else None, context)
        key = (assembled.page, assembled.anchor)
        seen.add(key)
        speech = existing.get(key)
        if speech is None:
            speech = models.Speech(
                term_id=term_id, sitting_number=sitting, page=key[0], anchor=key[1]
            )
            session.add(speech)
            session.flush()
        result.speeches += 1
        current = (
            session.get(models.SpeechRevision, speech.current_revision_id)
            if speech.current_revision_id is not None
            else None
        )
        if current is not None and current.content_sha256 == values["content_sha256"]:
            continue
        revision = session.scalar(
            select(models.SpeechRevision).where(
                models.SpeechRevision.speech_id == speech.id,
                models.SpeechRevision.content_sha256 == values["content_sha256"],
            )
        )
        if revision is None:
            revision = models.SpeechRevision(speech_id=speech.id, **values)
            session.add(revision)
            session.flush()
            session.add_all(
                models.SpeechParagraph(
                    revision_id=revision.id,
                    position=i,
                    page_revision_id=p.revision_id,
                    page=p.page,
                    segment_position=p.segment_position,
                    text=p.text,
                )
                for i, p in enumerate(assembled.paragraphs)
            )
            result.new_revisions += 1
        else:
            revision.retired_at = None  # the speech returned to an earlier version
        if current is not None:
            current.retired_at = now
            result.retired += 1
        speech.current_revision_id = revision.id
        session.flush()
    for key, speech in existing.items():
        if key not in seen and speech.current_revision_id is not None:
            gone = session.get(models.SpeechRevision, speech.current_revision_id)
            if gone is not None:
                gone.retired_at = now
                result.retired += 1
            speech.current_revision_id = None
    session.execute(
        update(models.SourcePage)
        .where(
            models.SourcePage.term_id == term_id,
            models.SourcePage.sitting_number == sitting,
        )
        .values(assembled_revision_id=models.SourcePage.current_revision_id)
    )
    session.flush()
    return result


def _revision_values(
    assembled: AssembledSpeech,
    start: models.SourcePage,
    attribution,
    entry: models.TranscriptIndexEntry | None,
    context: Context,
) -> dict:
    agenda = entry.agenda_item_id if entry else None
    first, last = assembled.pages
    values = dict(
        term_id=start.term_id,
        date=start.date,
        person_id=attribution.person_id,
        attribution=attribution.evidence,
        label=assembled.label,
        role=_role(entry.kind) if entry else "unknown",
        agenda_item_id=agenda if agenda in context.agenda_ids else None,
        first_page=first,
        last_page=last,
        incomplete=assembled.incomplete,
        stage=assembled.stage,
        words=word_count(assembled.text),
        text=assembled.text,
    )
    paragraphs = [(p.page, p.revision_id, p.segment_position, p.text) for p in assembled.paragraphs]
    values["content_sha256"] = content_hash(
        [{k: v for k, v in values.items() if k != "text"}, paragraphs]
    )
    return values


def sittings_to_assemble(session: Session, term_ids: Collection[int] | None = None):
    """(term id, sitting) pairs whose pages changed since they were last assembled."""
    query = (
        select(models.SourcePage.term_id, models.SourcePage.sitting_number)
        .where(
            models.SourcePage.current_revision_id.is_distinct_from(
                models.SourcePage.assembled_revision_id
            )
        )
        .distinct()
        .order_by(models.SourcePage.term_id, models.SourcePage.sitting_number)
    )
    if term_ids:
        query = query.where(models.SourcePage.term_id.in_(list(term_ids)))
    return [tuple(row) for row in session.execute(query)]
