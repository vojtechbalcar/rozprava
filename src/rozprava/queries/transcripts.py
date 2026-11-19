"""The transcript reader: one stored page revision, its speeches and the sitting day.

Pages are read from PostgreSQL only. A page that is not imported yet (pending,
failed or unavailable) is shown as such; it is never fetched on demand.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from rozprava import models
from rozprava.queries import common

SR = models.SpeechRevision
PAGE_STATES = {
    "pending": "Tuto stranu jsme zatím nenačetli. Import probíhá postupně.",
    "failed": "Načtení této strany se zatím nepodařilo; zkusíme to znovu.",
    "unavailable": "Strana není na psp.cz dostupná.",
}


def _time(revision: models.PageRevision | None, page: models.SourcePage) -> str | None:
    if revision and revision.time_label:
        return revision.time_label.strip("()").removesuffix(" hodin")
    if page.start_minute is not None:
        return f"{page.start_minute // 60}.{page.start_minute % 60:02d}"
    return None


def reader(
    session: Session, term_number: int, sitting: int, page_number: int, revision_id: int | None
) -> dict | None:
    # Reject edited links outside the stored smallint range before binding SQL.
    if not (1 <= sitting <= 32_767 and 1 <= page_number <= 32_767):
        return None
    term = common.terms(session).get(term_number)
    if term is None:
        return None
    page = session.scalar(
        select(models.SourcePage).where(
            models.SourcePage.term_id == term.id,
            models.SourcePage.sitting_number == sitting,
            models.SourcePage.page == page_number,
        )
    )
    if page is None:
        return None
    if revision_id is not None:
        revision = session.get(models.PageRevision, revision_id)
        if revision is None or revision.source_page_id != page.id:
            return None
    else:
        revision = (
            session.get(models.PageRevision, page.current_revision_id)
            if page.current_revision_id
            else None
        )
    neighbours = {
        p.page: p
        for p in session.scalars(
            select(models.SourcePage).where(
                models.SourcePage.term_id == term.id,
                models.SourcePage.sitting_number == sitting,
                models.SourcePage.page.in_([page_number - 1, page_number + 1]),
            )
        )
    }
    view = {
        "term": term.number,
        "term_year": term.year,
        "sitting": sitting,
        "page": page_number,
        "date": page.date.isoformat() if page.date else None,
        "time": _time(revision, page),
        "status": revision.status_line if revision else None,
        "psp_url": common.psp_page_url(term.year, sitting, page_number),
        "prev_page": page_number - 1 if page_number - 1 in neighbours else None,
        "next_page": page_number + 1 if page_number + 1 in neighbours else None,
        "state": None if revision else page.status,
        "state_text": None if revision else PAGE_STATES.get(page.status),
        "unavailable_reason": page.unavailable_reason,
        "revision": revision.id if revision else None,
        "pinned": revision_id is not None and revision_id != page.current_revision_id,
        "fetched_at": revision.fetched_at.astimezone().strftime("%Y-%m-%dT%H:%M")
        if revision
        else None,
        "speeches": [],
        "continues": False,
        "agenda": None,
        "day": None,
    }
    if revision is None:
        view["day"] = day_view(session, term, sitting, page)
        return view

    segments = session.scalars(
        select(models.PageSegment)
        .where(models.PageSegment.revision_id == revision.id)
        .order_by(models.PageSegment.position)
    ).all()
    # Which speech revision holds each paragraph of this page revision.
    rows = session.execute(
        select(models.SpeechParagraph, SR, models.Speech)
        .join(SR, SR.id == models.SpeechParagraph.revision_id)
        .join(models.Speech, models.Speech.id == SR.speech_id)
        .where(models.SpeechParagraph.page_revision_id == revision.id)
        .order_by(
            SR.retired_at.is_(None).desc(), SR.created_at.desc(), models.SpeechParagraph.position
        )
    ).all()
    chosen: dict[int, tuple[models.SpeechRevision, models.Speech]] = {}
    by_segment: dict[int, int] = {}
    for paragraph, speech_revision, speech in rows:
        owner = by_segment.setdefault(paragraph.segment_position, speech_revision.id)
        if owner == speech_revision.id:
            chosen.setdefault(speech_revision.id, (speech_revision, speech))
    paragraphs: dict[int, list[models.SpeechParagraph]] = defaultdict(list)
    for paragraph, speech_revision, _ in rows:
        if by_segment.get(paragraph.segment_position) == speech_revision.id:
            paragraphs[speech_revision.id].append(paragraph)

    person_ids = {r.person_id for r, _ in chosen.values() if r.person_id}
    people = {
        p.id: p
        for p in session.scalars(select(models.Person).where(models.Person.id.in_(person_ids)))
    }
    clubs = common.Clubs(session, person_ids)
    items: list[tuple[int, dict]] = []
    for speech_revision, speech in chosen.values():
        own = sorted(paragraphs[speech_revision.id], key=lambda p: p.position)
        slug = common.catalog_slug(term.number, sitting, speech.page, speech.anchor)
        person = people.get(speech_revision.person_id) if speech_revision.person_id else None
        speaker = common.speaker_view(
            person,
            speech_revision.label,
            clubs.party_on(speech_revision.person_id, speech_revision.date),
        )
        if person is None and speech_revision.incomplete:
            speaker["name"] = common.UNKNOWN_SPEAKER
        items.append(
            (
                min(p.segment_position for p in own),
                {
                    "kind": "speech",
                    "anchor": f"s-{slug}",
                    "speaker": speaker,
                    "label": speech_revision.label,
                    "chair": speech_revision.role == "chair",
                    "role": speech_revision.role,
                    "attribution": speech_revision.attribution,
                    "incomplete": speech_revision.incomplete,
                    "continued_from": speech.page if speech.page < page_number else None,
                    "continues": speech_revision.last_page > page_number,
                    "catalog": common.catalog(term.number, sitting, speech.page, speech.anchor),
                    "catalog_slug": slug,
                    "revision": speech_revision.id,
                    "agenda_item_id": speech_revision.agenda_item_id,
                    "paras": [{"text": p.text, "n": p.position + 1} for p in own],
                },
            )
        )
    used = set(by_segment)
    for segment in segments:  # headings and notes that belong to no speech
        if segment.position not in used and segment.paragraphs:
            items.append(
                (
                    segment.position,
                    {
                        "kind": "heading" if segment.heading else "note",
                        "paras": [{"text": t} for t in segment.paragraphs],
                    },
                )
            )
    items.sort(key=lambda item: item[0])
    view["speeches"] = [item for _, item in items]
    spoken = [i for i in view["speeches"] if i["kind"] == "speech"]
    view["continues"] = bool(spoken and spoken[-1]["continues"])

    agenda_counts = Counter(i["agenda_item_id"] for i in spoken if i["agenda_item_id"])
    if agenda_counts:
        item = session.get(models.AgendaItem, agenda_counts.most_common(1)[0][0])
        bill = session.get(models.Bill, item.bill_id) if item and item.bill_id else None
        view["agenda"] = common.agenda_view(item, bill, term.number)
    view["day"] = day_view(session, term, sitting, page)
    return view


def day_view(
    session: Session, term: common.TermInfo, sitting: int, page: models.SourcePage
) -> dict | None:
    """Every speech of the sitting day, for the minimap (DESIGN.md §7.13)."""
    if page.day_number is None:
        return None
    pages = session.execute(
        select(models.SourcePage.page, models.SourcePage.status).where(
            models.SourcePage.term_id == term.id,
            models.SourcePage.sitting_number == sitting,
            models.SourcePage.day_number == page.day_number,
        )
    ).all()
    numbers = [p for p, _ in pages]
    rows = session.execute(
        select(SR, models.Speech)
        .join(models.Speech, models.Speech.id == SR.speech_id)
        .where(
            SR.retired_at.is_(None),
            models.Speech.term_id == term.id,
            models.Speech.sitting_number == sitting,
            models.Speech.page.in_(numbers),
        )
        .order_by(models.Speech.page, models.Speech.anchor)
    ).all()
    person_ids = {r.person_id for r, _ in rows if r.person_id}
    people = {
        p.id: p
        for p in session.scalars(select(models.Person).where(models.Person.id.in_(person_ids)))
    }
    clubs = common.Clubs(session, person_ids)
    speeches = []
    for revision, speech in rows:
        person = people.get(revision.person_id) if revision.person_id else None
        speeches.append(
            {
                "name": f"{person.forename} {person.surname}" if person else common.UNKNOWN_SPEAKER,
                "party": clubs.party_on(revision.person_id, revision.date),
                "chair": revision.role == "chair",
                "words": max(revision.words, 1),
                "page": speech.page,
                "anchor": "s-"
                + common.catalog_slug(term.number, sitting, speech.page, speech.anchor),
                "on_page": revision.first_page <= page.page <= revision.last_page,
            }
        )
    imported = sum(1 for _, status in pages if status == "imported")
    return {
        "date": page.date.isoformat() if page.date else None,
        "first_page": min(numbers),
        "last_page": max(numbers),
        "pages": len(numbers),
        "imported_pages": imported,
        "speeches": speeches,
    }


@dataclass(frozen=True)
class SpeechLocation:
    term: int
    sitting: int
    page: int
    anchor: str
    page_revision: int | None  # set when a historical version is pinned


def locate_speech(session: Session, slug: str, revision_id: int | None) -> SpeechLocation | None:
    """Where a catalogue number (10-034-0644-2) is read, optionally pinned to a version."""
    parsed = common.parse_catalog(slug)
    if parsed is None:
        return None
    term_number, sitting, page, anchor = parsed
    term = common.terms(session).get(term_number)
    if term is None:
        return None
    speech = session.scalar(
        select(models.Speech).where(
            models.Speech.term_id == term.id,
            models.Speech.sitting_number == sitting,
            models.Speech.page == page,
            models.Speech.anchor == anchor,
        )
    )
    if speech is None:
        return None
    if revision_id is not None:
        revision = session.get(SR, revision_id)
        if revision is None or revision.speech_id != speech.id:
            return None
    elif speech.current_revision_id is not None:
        revision = session.get(SR, speech.current_revision_id)
    else:  # no longer in the current transcript: show its last version
        revision = session.scalar(
            select(SR).where(SR.speech_id == speech.id).order_by(SR.created_at.desc()).limit(1)
        )
    if revision is None:
        return None
    first = session.scalar(
        select(models.SpeechParagraph)
        .where(models.SpeechParagraph.revision_id == revision.id)
        .order_by(models.SpeechParagraph.position)
        .limit(1)
    )
    pinned = revision.retired_at is not None or revision_id is not None
    return SpeechLocation(
        term=term_number,
        sitting=sitting,
        page=first.page if first else page,
        anchor="s-" + common.catalog_slug(term_number, sitting, page, anchor),
        page_revision=first.page_revision_id if first and pinned else None,
    )
