"""Embed speeches for meaning search: split current revisions into passages and store
one Voyage vector per passage (models.SpeechChunk).

Only speeches of at least 40 words by a speaker (not the chair's procedural remarks)
are embedded. A passage is about 250 words of consecutive paragraphs; a paragraph
over 400 words is split between sentences. Each passage is embedded with a short
header naming the speaker and the agenda item, so a passage that never names its
topic still sits near it. A passage whose text was embedded before by the same
model (a revision that changed elsewhere) reuses that vector.

Revisions are processed in id order and committed in batches with their usage
records, so an interrupted run continues where it stopped. Chunks of retired
revisions are deleted at the end, after their successors could reuse them.
"""

import hashlib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session, sessionmaker

from rozprava import ai, models
from rozprava.titles import short_title

MIN_WORDS = 40
TARGET_WORDS = 250
MAX_WORDS = 400
BATCH = 200  # revisions per transaction
REQUEST_TEXTS = 1000  # Voyage: at most 1,000 texts per request
REQUEST_TOKENS = 90_000  # estimated; voyage-4-large accepts 120,000 per request
SR = models.SpeechRevision
CHUNK = models.SpeechChunk


@dataclass(frozen=True)
class Passage:
    first: int  # paragraph positions
    last: int
    text: str


_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+(?=[„\"(]?[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ0-9])")


def _split(text: str) -> list[str]:
    """A long paragraph as pieces of about TARGET_WORDS, cut between sentences."""
    if len(text.split()) <= MAX_WORDS:
        return [text]
    pieces, current = [], []
    for sentence in _SENTENCE_END.split(text):
        words = sentence.split()
        while len(words) > MAX_WORDS:  # one endless sentence: cut it by words
            if current:
                pieces.append(" ".join(current))
                current = []
            pieces.append(" ".join(words[:TARGET_WORDS]))
            words = words[TARGET_WORDS:]
        if current and len(current) + len(words) > TARGET_WORDS:
            pieces.append(" ".join(current))
            current = []
        current += words
    if current:
        pieces.append(" ".join(current))
    return pieces


def passages(paragraphs: Sequence[tuple[int, str]]) -> list[Passage]:
    """Consecutive paragraphs (position, text) packed into passages of about TARGET_WORDS."""
    pieces = [(position, piece) for position, text in paragraphs for piece in _split(text)]
    out: list[Passage] = []
    first, last, texts, words = None, None, [], 0
    for position, piece in pieces:
        size = len(piece.split())
        if texts and (words >= TARGET_WORDS or words + size > MAX_WORDS):
            out.append(Passage(first, last, "\n\n".join(texts)))  # type: ignore[arg-type]
            first, texts, words = None, [], 0
        first = position if first is None else first
        last = position
        texts.append(piece)
        words += size
    if texts:
        tail = Passage(first, last, "\n\n".join(texts))  # type: ignore[arg-type]
        previous = out[-1] if out else None
        if previous and words < MIN_WORDS and len(previous.text.split()) + words <= MAX_WORDS:
            out[-1] = Passage(previous.first, tail.last, previous.text + "\n\n" + tail.text)
        else:
            out.append(tail)
    return out


def _eligible():
    return SR.retired_at.is_(None) & (SR.role != "chair") & (SR.words >= MIN_WORDS)


def _embedded(model: str):
    return exists(select(1).where(CHUNK.revision_id == SR.id, CHUNK.model == model))


def pending(session: Session, model: str) -> int:
    """Current speeches that meaning search should cover but this model has not embedded."""
    query = select(func.count()).select_from(SR).where(_eligible(), ~_embedded(model))
    return session.scalar(query) or 0


def estimate_tokens(text: str) -> int:
    """A generous token estimate for Czech (about 6.3 characters a word, under 3 tokens)."""
    return len(text) // 2 + 1


def embed_speeches(
    sessions: sessionmaker[Session],
    embedder: ai.Embedder,
    token_limit: int,
    limit: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, int]:
    with sessions.begin() as session:
        query = select(SR.id).where(_eligible(), ~_embedded(embedder.model)).order_by(SR.id)
        ids = list(session.scalars(query.limit(limit) if limit is not None else query))

    counts = {"revisions": 0, "chunks": 0, "reused": 0}
    for start in range(0, len(ids), BATCH):
        with sessions() as session:
            rows = _chunks(session, ids[start : start + BATCH], embedder.model)
            reuse: dict[str, list[float]] = {
                digest: vector
                for digest, vector in session.execute(
                    select(CHUNK.digest, CHUNK.embedding)
                    .where(CHUNK.model == embedder.model)
                    .where(CHUNK.digest.in_({r["digest"] for r in rows}))
                    .distinct(CHUNK.digest)
                )
            }
        fresh: dict[str, str] = {}  # digest -> text, embedded once per batch
        for row in rows:
            text = row.pop("text")
            if row["digest"] not in reuse:
                fresh.setdefault(row["digest"], text)
        vectors: dict[str, list[float]] = dict(reuse)
        for request in _requests(list(fresh.items())):
            texts = [text for _, text in request]
            estimate = sum(estimate_tokens(t) for t in texts)
            # Each paid request's usage commits at once, even if a later one fails.
            with sessions.begin() as usage:
                embedded = ai.embed_documents(usage, embedder, texts, estimate, token_limit)
            vectors.update(zip((digest for digest, _ in request), embedded, strict=True))
        revisions = {r["revision_id"] for r in rows}
        with sessions.begin() as session:
            session.execute(delete(CHUNK).where(CHUNK.revision_id.in_(revisions)))
            session.add_all(
                CHUNK(**row, model=embedder.model, embedding=vectors[row["digest"]]) for row in rows
            )
        counts["revisions"] += len(revisions)
        counts["chunks"] += len(rows)
        counts["reused"] += sum(1 for r in rows if r["digest"] in reuse)
        if progress:
            progress(counts["revisions"], len(ids))
    # Only now: a new revision above may have reused its retired predecessor's vectors.
    with sessions.begin() as session:
        retired = select(SR.id).where(SR.retired_at.is_not(None))
        counts["retired"] = len(
            session.scalars(
                delete(CHUNK).where(CHUNK.revision_id.in_(retired)).returning(CHUNK.id)
            ).all()
        )
    return counts


def _requests(items: list[tuple[str, str]]):
    """(digest, text) pairs grouped to fit one Voyage request."""
    request: list[tuple[str, str]] = []
    tokens = 0
    for digest, text in items:
        size = estimate_tokens(text)
        if request and (len(request) == REQUEST_TEXTS or tokens + size > REQUEST_TOKENS):
            yield request
            request, tokens = [], 0
        request.append((digest, text))
        tokens += size
    if request:
        yield request


def _chunks(session: Session, ids: Sequence[int], model: str) -> list[dict]:
    """Chunk rows (with the text to embed) for these revisions."""
    revisions = session.execute(
        select(SR.id, SR.person_id, SR.label, models.AgendaItem)
        .outerjoin(models.AgendaItem, models.AgendaItem.id == SR.agenda_item_id)
        .where(SR.id.in_(ids))
        .order_by(SR.id)
    ).all()
    people = {
        p.id: p
        for p in session.scalars(
            select(models.Person).where(models.Person.id.in_({r.person_id for r in revisions}))
        )
    }
    paragraphs: dict[int, list[tuple[int, str]]] = {}
    for p in session.execute(
        select(
            models.SpeechParagraph.revision_id,
            models.SpeechParagraph.position,
            models.SpeechParagraph.text,
        )
        .where(models.SpeechParagraph.revision_id.in_(ids))
        .order_by(models.SpeechParagraph.revision_id, models.SpeechParagraph.position)
    ):
        paragraphs.setdefault(p.revision_id, []).append((p.position, p.text))

    rows = []
    for revision in revisions:
        person = people.get(revision.person_id)
        speaker = f"{person.forename} {person.surname}" if person else revision.label or ""
        item = revision.AgendaItem
        topic = short_title(item.title) if item and item.title else ""
        header = ". ".join(part for part in (speaker, topic) if part)
        for position, passage in enumerate(passages(paragraphs.get(revision.id, []))):
            text = f"{header}\n\n{passage.text}" if header else passage.text
            rows.append(
                {
                    "revision_id": revision.id,
                    "position": position,
                    "first_paragraph": passage.first,
                    "last_paragraph": passage.last,
                    "digest": hashlib.sha256(text.encode()).hexdigest(),
                    "text": text,
                }
            )
    return rows
