"""Meaning search: passages, the embedding job, hybrid ranking and the Voyage client.

A topic embedder stands in for Voyage: each text becomes a vector over a few topics
named by word prefixes, so "starobní renta", which no fixture speech contains, is
close to speeches about pension savings. No test calls a paid service.
"""

import math
import re
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from rozprava import ai, models
from rozprava.ingest import embed
from rozprava.queries import search
from rozprava.queries.search import SearchFilters
from rozprava.settings import get_settings
from rozprava.typography import fold
from rozprava.web import SHARED

TOPICS = {
    "pension": ("penz", "sporeni", "duchod", "stari", "senior", "renta", "starob"),
    "whistleblowing": ("oznamovatel", "whistleblower"),
    "kosovo": ("kosov",),
}
SR = models.SpeechRevision


class TopicEmbedder:
    model = "test-topics"

    def __init__(self):
        self.calls: list[tuple[int, str]] = []

    def vector(self, text: str) -> list[float]:
        counts = [0.0] * models.DIMENSIONS
        for word in re.findall(r"\w+", fold(text)):
            for dim, prefixes in enumerate(TOPICS.values()):
                if word.startswith(prefixes):
                    counts[dim] += 1
        if not any(counts):
            counts[len(TOPICS)] = 1.0  # about something else
        norm = math.sqrt(sum(c * c for c in counts))
        return [c / norm for c in counts]

    def embed(self, texts, input_type):
        self.calls.append((len(texts), input_type))
        return [self.vector(t) for t in texts], sum(len(t.split()) for t in texts)


def words(n: int, word: str = "slovo") -> str:
    return " ".join([word] * n)


def test_passages_pack_paragraphs_and_split_long_ones_between_sentences():
    short = embed.passages([(0, words(100)), (1, words(100)), (2, words(100)), (3, words(60))])
    assert [(p.first, p.last) for p in short] == [(0, 2), (3, 3)]
    # A tail under 40 words joins the previous passage when it fits.
    assert [(p.first, p.last) for p in embed.passages([(0, words(300)), (1, words(30))])] == [
        (0, 1)
    ]
    sentence = words(59) + " konec."
    long = embed.passages([(4, " ".join([sentence.capitalize()] * 10))])  # 600 words
    assert all(p.first == p.last == 4 for p in long) and len(long) >= 2
    assert all(len(p.text.split()) <= embed.MAX_WORDS for p in long)
    assert all(p.text.endswith("konec.") for p in long)  # cut between sentences
    endless = embed.passages([(0, words(1000))])  # no sentence end at all
    assert sum(len(p.text.split()) for p in endless) == 1000
    assert all(len(p.text.split()) <= embed.MAX_WORDS for p in endless)


@pytest.fixture
def db(corpus, sessions):
    with sessions() as session:
        yield session


def eligible(db: Session) -> set[int]:
    return set(
        db.scalars(
            select(SR.id).where(
                SR.retired_at.is_(None), SR.role != "chair", SR.words >= embed.MIN_WORDS
            )
        )
    )


def test_embedding_covers_speakers_once_and_reuses_unchanged_passages(db, sessions):
    embedder = TopicEmbedder()
    assert embed.pending(db, embedder.model) == len(eligible(db)) > 0
    first = embed.embed_speeches(sessions, embedder, token_limit=10**9)
    assert first["revisions"] == len(eligible(db)) and first["chunks"] > 0
    chunks = db.scalars(select(models.SpeechChunk)).all()
    assert {c.revision_id for c in chunks} == eligible(db)  # no chair remarks, no short ones
    assert all(c.model == embedder.model and len(c.embedding) == models.DIMENSIONS for c in chunks)
    usage = db.scalars(select(models.AIUsage)).all()
    assert {u.purpose for u in usage} == {"documents"} and sum(u.input_tokens for u in usage) > 0
    assert embed.pending(db, embedder.model) == 0
    assert embed.embed_speeches(sessions, embedder, token_limit=10**9)["revisions"] == 0

    # A new revision of a speech reuses the vectors of its retired predecessor's
    # unchanged passages, which are deleted only afterwards.
    calls = len(embedder.calls)
    old = chunks[0].revision_id
    new = successor(db, old)
    again = embed.embed_speeches(sessions, embedder, token_limit=10**9)
    assert again["revisions"] == 1 and again["reused"] == again["chunks"] > 0
    assert len(embedder.calls) == calls
    revisions = set(db.scalars(select(models.SpeechChunk.revision_id)))
    assert new in revisions and old not in revisions and again["retired"] > 0


def successor(db: Session, old: int) -> int:
    """A copy of revision `old` that replaces it, as a changed transcript page would."""
    columns = [
        c.name for c in SR.__table__.columns if c.name not in ("id", "search", "content_sha256")
    ]
    names = ", ".join(columns)
    new = db.execute(
        text(
            f"INSERT INTO speech_revision ({names}, content_sha256) "
            f"SELECT {names}, md5(content_sha256) FROM speech_revision WHERE id = :old "
            "RETURNING id"
        ),
        {"old": old},
    ).scalar_one()
    db.execute(
        text(
            "INSERT INTO speech_paragraph (revision_id, position, page_revision_id, page, "
            "segment_position, text) SELECT :new, position, page_revision_id, page, "
            "segment_position, text FROM speech_paragraph WHERE revision_id = :old"
        ),
        {"new": new, "old": old},
    )
    db.execute(text("UPDATE speech_revision SET retired_at = now() WHERE id = :old"), {"old": old})
    db.commit()
    return new


def test_embedding_stops_before_passing_the_token_limit(db, sessions):
    embedder = TopicEmbedder()
    with pytest.raises(ai.LimitReached, match="EMBEDDING_TOKEN_LIMIT"):
        embed.embed_speeches(sessions, embedder, token_limit=10)
    assert embedder.calls == []
    assert db.scalar(select(func.count()).select_from(models.SpeechChunk)) == 0


def test_paid_requests_stay_recorded_when_a_later_one_fails(db, sessions, monkeypatch):
    monkeypatch.setattr(embed, "REQUEST_TEXTS", 1)

    class Failing(TopicEmbedder):
        def embed(self, texts, input_type):
            if self.calls:
                raise ai.AIUnavailable("Voyage HTTP 500")
            return super().embed(texts, input_type)

    with pytest.raises(ai.AIUnavailable):
        embed.embed_speeches(sessions, Failing(), token_limit=10**9)
    assert db.scalar(select(func.count()).select_from(models.AIUsage)) == 1
    assert db.scalar(select(func.count()).select_from(models.SpeechChunk)) == 0


@pytest.fixture
def embedded(db, sessions):
    embedder = TopicEmbedder()
    embed.embed_speeches(sessions, embedder, token_limit=10**9)
    return embedder


def run(db: Session, vector=None, **params: str) -> search.SearchPage:
    filters, errors = SearchFilters.parse({k: [v] for k, v in params.items()})
    return search.search(db, filters, errors, vector)


def pension_speeches(db: Session) -> set[int]:
    pattern = re.compile(r"\b(?:" + "|".join(TOPICS["pension"]) + r")")
    return {i for i, t in db.execute(select(SR.id, SR.text)) if pattern.search(fold(t))}


def test_meaning_adds_related_speeches_that_lack_the_words(db, embedded, monkeypatch):
    monkeypatch.setattr(search, "PER_PAGE", 500)
    q = "starobní renta"
    assert run(db, q=q).total == 0  # no speech contains these words
    page = run(db, embedded.vector(q), q=q)
    found = {r["id"] for r in page.results}
    assert found and found <= pension_speeches(db) & eligible(db)
    assert page.related == page.total == len(found)
    assert all(r["related"] for r in page.results)
    assert sum(m["count"] for m in page.facets["months"]) == page.total
    by_date = run(db, embedded.vector(q), q=q, razeni="nejnovejsi")
    assert [r["date"] for r in by_date.results] == sorted(
        (r["date"] for r in by_date.results), reverse=True
    )
    # Filters apply to meaning results too.
    assert {r["term"] for r in run(db, embedded.vector(q), q=q, obdobi="9").results} <= {9}


def test_keyword_and_meaning_results_are_fused(db, embedded, monkeypatch):
    monkeypatch.setattr(search, "PER_PAGE", 500)
    keyword = run(db, q="penzijní")
    both = run(db, embedded.vector("penzijní"), q="penzijní")
    keyword_ids = {r["id"] for r in keyword.results}
    assert keyword_ids <= {r["id"] for r in both.results}
    assert both.total == keyword.total + both.related
    assert {r["id"] for r in both.results if r["related"]}.isdisjoint(keyword_ids)
    assert search.fuse([1, 2, 3], [3, 4]) == [3, 1, 2, 4]  # found by both ranks first


def test_only_plain_questions_use_meaning():
    assert search.meaning_query("jak se změnily důchody")
    assert not search.meaning_query('"důchodová reforma"')
    assert not search.meaning_query("důchod -penze")
    assert not search.meaning_query("důchod OR penze")


def test_query_embeddings_are_cached_and_recorded(db, embedded):
    first = ai.query_vector(db, embedded, "  starobní   renta ", limit=10**9)
    second = ai.query_vector(db, embedded, "starobní renta", limit=10**9)
    assert first == pytest.approx(second, abs=1e-3)
    assert embedded.calls.count((1, "query")) == 1
    usage = db.scalars(select(models.AIUsage).where(models.AIUsage.purpose == "query")).all()
    assert len(usage) == 1 and usage[0].cost_usd == Decimal(0)  # test model has no price
    with pytest.raises(ai.LimitReached):
        ai.query_vector(db, embedded, "jiný dotaz", limit=1)


def test_search_page_marks_related_results_and_falls_back(client, sessions, monkeypatch):
    from rozprava import main

    embedder = TopicEmbedder()
    embed.embed_speeches(sessions, embedder, token_limit=10**9)
    monkeypatch.setattr(get_settings(), "embedding_model", embedder.model)
    SHARED.clear()
    monkeypatch.setattr(main, "query_embedder", lambda: embedder)
    page = client.get("/hledat", params={"q": "starobní renta"}).text
    assert "Podobný význam" in page and "data-related" in page
    assert "Voyage AI" in client.get("/jak-to-funguje").text

    class Broken:
        model = embedder.model

        def embed(self, texts, input_type):
            raise ai.AIUnavailable("down")

    monkeypatch.setattr(main, "query_embedder", lambda: Broken())
    fallback = client.get("/hledat", params={"q": "penzijní spoření nové"}).text
    assert "data-meaning-unavailable" in fallback and "Podobný význam" not in fallback
    assert "obj__excerpt" in fallback  # keyword results still shown


def voyage(handler) -> ai.VoyageEmbedder:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return ai.VoyageEmbedder("secret-key", "voyage-4-large", attempts=3, client=client)


def test_voyage_client_orders_vectors_and_retries_rate_limits(monkeypatch):
    monkeypatch.setattr(ai.time, "sleep", lambda seconds: None)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(
            200,
            json={
                "data": [{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}],
                "usage": {"total_tokens": 7},
            },
        )

    vectors, tokens = voyage(handler).embed(["a", "b"], "document")
    assert vectors == [[1.0], [2.0]] and tokens == 7
    assert seen[-1].headers["authorization"] == "Bearer secret-key"
    body = seen[-1].read().decode()
    assert '"input_type":"document"' in body and '"output_dimension":1024' in body


def test_voyage_errors_explain_without_the_key(monkeypatch):
    monkeypatch.setattr(ai.time, "sleep", lambda seconds: None)
    bad = voyage(lambda request: httpx.Response(400, text="too many tokens"))
    with pytest.raises(ai.AIUnavailable, match="too many tokens") as error:
        bad.embed(["a"], "document")
    assert "secret-key" not in str(error.value)
    down = voyage(lambda request: httpx.Response(503))
    with pytest.raises(ai.AIUnavailable, match="did not answer"):
        down.embed(["a"], "query")


def test_related_speeches_stay_near_the_query_s_closest_passage(db, embedded, monkeypatch):
    from rozprava.queries import common

    filters, _ = SearchFilters.parse({"q": ["starobní renta"]})
    vector = embedded.vector("starobní renta")
    terms, clubs = common.terms(db), common.Clubs(db)
    wide = search.related(db, vector, filters, terms, clubs)
    nearest = min(r.distance for r in wide)
    assert all(r.distance <= nearest + search.MEANING_MARGIN for r in wide)
    monkeypatch.setattr(search, "MEANING_MARGIN", 0.0)
    tight = search.related(db, vector, filters, terms, clubs)
    assert tight and {r.revision for r in tight} <= {r.revision for r in wide}
    assert all(r.distance == pytest.approx(nearest) for r in tight)
    monkeypatch.setattr(search, "MAX_DISTANCE", -1.0)  # nothing is close enough
    assert search.related(db, vector, filters, terms, clubs) == []
