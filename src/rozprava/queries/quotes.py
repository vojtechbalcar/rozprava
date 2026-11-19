"""Verbatim, contiguous selections from one immutable speech paragraph.

Offsets count Unicode code points (not JavaScript UTF-16 code units). Neither
quotation text nor speaker/provenance fields are accepted from the caller.
"""

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rozprava import models
from rozprava.queries import common
from rozprava.typography import clip

MAX_CHARS = 280
FORMATS = ("1200x630", "1080x1350", "1080x1920")
SOURCE = re.compile(r"paragraph-([0-9]{1,2}-[0-9]{3}-[0-9]{4}-[0-9]{1,3})-([1-9][0-9]{0,5})")


class InvalidSelection(ValueError):
    pass


def selection(
    session: Session,
    source: str,
    version: int,
    start: int | None = None,
    end: int | None = None,
    highlight: str = "",
    size: str = FORMATS[0],
) -> dict | None:
    match = SOURCE.fullmatch(source)
    if not match:
        return None
    slug, number = match.groups()
    revision = session.get(models.SpeechRevision, version)
    if revision is None:
        return None
    speech = session.get(models.Speech, revision.speech_id)
    term = session.get(models.Term, revision.term_id)
    assert speech and term
    if slug != common.catalog_slug(term.number, speech.sitting_number, speech.page, speech.anchor):
        return None
    paragraph = session.get(models.SpeechParagraph, (version, int(number) - 1))
    if paragraph is None:
        return None
    text = paragraph.text
    if (start is None) != (end is None):
        raise InvalidSelection("Vyberte začátek i konec citace.")
    if start is None or end is None:
        start, end = 0, len(clip(text, MAX_CHARS))
    if not 0 <= start < end <= len(text):
        raise InvalidSelection("Vybraný úsek leží mimo uložený odstavec.")
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if not start < end:
        raise InvalidSelection("Vyberte neprázdný úsek citace.")
    if end - start > MAX_CHARS:
        raise InvalidSelection("Vyberte kratší úsek, nejvýše 280 znaků.")
    if size not in FORMATS:
        raise InvalidSelection("Tento rozměr karty není podporovaný.")
    person = session.get(models.Person, revision.person_id) if revision.person_id else None
    club = common.Clubs(session, [person.id] if person else []).party_on(
        revision.person_id, revision.date
    )
    speaker = common.speaker_view(person, revision.label, club)
    if person is None and revision.incomplete:
        speaker["name"] = common.UNKNOWN_SPEAKER
    page_revision = session.get(models.PageRevision, paragraph.page_revision_id)
    assert page_revision
    last_position = session.scalar(
        select(func.max(models.SpeechParagraph.position)).where(
            models.SpeechParagraph.revision_id == version
        )
    )
    span = text[start:end]
    return {
        "source_key": source,
        "revision": version,
        "start": start,
        "end": end,
        "span": span,
        "highlight": highlight if highlight and len(highlight) <= 80 and highlight in span else "",
        "cut_start": start > 0 or paragraph.position > 0 or revision.incomplete,
        "cut_end": end < len(text) or paragraph.position < (last_position or 0),
        "format": size,
        "source": {
            "text": text,
            "speaker": speaker,
            "catalog": common.catalog(
                term.number, speech.sitting_number, speech.page, speech.anchor
            ),
            "term": term.number,
            "sitting": speech.sitting_number,
            "page": paragraph.page,
            "date": revision.date.isoformat() if revision.date else None,
            "status": page_revision.status_line,
            "revision": version,
            "page_revision": page_revision.id,
            "anchor": f"p-{slug}-{number}",
            "lead": paragraph.position > 0 or revision.incomplete,
            "trail": paragraph.position < (last_position or 0),
            "psp_url": common.psp_page_url(term.year, speech.sitting_number, paragraph.page),
        },
    }
