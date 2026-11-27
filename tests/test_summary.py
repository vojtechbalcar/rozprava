"""AI summaries: source selection, the citation rules, spending limit, cache and page.

A scripted writer stands in for Claude and answers with text blocks shaped like
the API's (citations by character range in a plain-text document). No test calls
a paid service.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rozprava import ai, models
from rozprava.queries import search, summary
from rozprava.queries.search import SearchFilters
from rozprava.settings import get_settings
from rozprava.web import SHARED


def text(value: str, *cites: tuple[int, int, int]) -> SimpleNamespace:
    """A response text block; cites are (document, start, end) character ranges."""
    return SimpleNamespace(
        type="text",
        text=value,
        citations=[
            SimpleNamespace(
                type="char_location",
                document_index=d,
                start_char_index=s,
                end_char_index=e,
                cited_text="(the model's copy, never used)",
            )
            for d, s, e in cites
        ],
    )


class Scripted:
    model = "claude-haiku-5-5"

    def __init__(self, *blocks, stop_reason="end_turn"):
        self.blocks, self.stop_reason, self.calls = list(blocks), stop_reason, []

    def write(self, system, content, max_tokens):
        self.calls.append(content)
        return ai.Answer(self.blocks, self.stop_reason, input_tokens=5000, output_tokens=800)


def source(number: int, revision: int, *paragraphs: str) -> summary.Source:
    return summary.Source(number, revision, list(enumerate(paragraphs)), f"[{number}]", "")


SOURCES = [
    source(1, 101, "Valorizace důchodů bude nižší. Rozpočet to vyžaduje.", "Inflace je vysoká."),
    source(2, 102, "Penze musí růst rychleji než ceny."),
]


def at(document: int, words: str) -> tuple[int, int, int]:
    """The character range of these words in a source document."""
    start = SOURCES[document].text.index(words)
    return document, start, start + len(words)


def test_only_cited_sentences_remain_with_the_words_they_cite():
    found = summary.sentences(
        [
            text("Podle 55. schůze a zákona č. 155/1995 Sb. Alena Schillerová uvedla, že "),
            text("valorizace bude nižší", at(0, "Valorizace důchodů bude nižší.")),
            text(". Tato věta nic necituje. Tomio Okamura naopak řekl, že "),
            text("penze mají růst", at(1, "Penze musí růst"), at(0, "Inflace je vysoká.")),
            text("."),
        ],
        SOURCES,
    )
    assert [s.text for s in found] == [
        "Podle 55. schůze a zákona č. 155/1995 Sb. Alena Schillerová uvedla, že "
        "valorizace bude nižší.",
        "Tomio Okamura naopak řekl, že penze mají růst.",
    ]
    assert [s.cites for s in found] == [[1], [1, 2]]
    assert found[1].passages == [(102, 0), (101, 1)]
    assert [(q["n"], q["text"]) for q in found[1].quotes] == [
        (2, "Penze musí růst"),
        (1, "Inflace je vysoká."),
    ]


def test_a_citation_names_the_paragraphs_its_characters_fall_in():
    whole = SOURCES[0].text
    assert SOURCES[0].positions(0, len(whole)) == [0, 1]
    assert SOURCES[0].positions(*at(0, "Inflace je vysoká.")[1:]) == [1]
    assert SOURCES[0].positions(len(whole) + 5, len(whole) + 9) == []


def test_quotation_marks_must_hold_verbatim_words():
    quoted = [
        text("Ministryně řekla „Valorizace … nižší“.", at(0, "Valorizace důchodů bude nižší.")),
        text(" Poslanec řekl „penze musí stoupat“.", at(1, "Penze musí růst rychleji")),
    ]
    assert [s.text for s in summary.sentences(quoted, SOURCES)] == [
        "Ministryně řekla „Valorizace … nižší“."
    ]


def test_bad_citations_are_ignored():
    blocks = [
        text("Neexistující dokument.", (7, 0, 5)),
        text(" Mimo rozsah.", (0, 500, 600)),
        text(" Jiný typ.", (0, 0, 5)),
    ]
    blocks[2].citations[0].type = "content_block_location"
    assert summary.sentences(blocks, SOURCES) == []


def result(n: int, revision: int) -> dict:
    return {
        "n": n,
        "id": revision,
        "page": 7,
        "catalog_slug": f"10-034-0642-{n}",
        "speaker": {"name": f"Řečník {n}", "party": None},
    }


def test_popovers_show_the_cited_words_and_link_their_paragraph(db: Session):
    found = summary.sentences(
        [
            text(
                "Ministryně uvedla, že valorizace bude nižší kvůli rozpočtu",
                at(0, "Valorizace důchodů bude nižší."),
                at(0, "Rozpočet to vyžaduje."),
                at(0, "Inflace je vysoká."),
            ),
            text("."),
        ],
        SOURCES,
    )
    rows = [{"text": s.text, "cites": s.cites, "quotes": s.quotes} for s in found]
    (sentence,) = summary.view(db, rows, [result(1, 101), result(2, 102)])
    (cite,) = sentence["cites"]
    assert cite["popover"] == "cite-1-1" and not cite["cut"]
    # Adjacent sentences join with a space, even across a paragraph break.
    assert (
        cite["quote"] == "Valorizace důchodů bude nižší. Rozpočet to vyžaduje. Inflace je vysoká."
    )
    assert cite["anchor"] == "p-10-034-0642-1-1" and cite["page"] == 7
    old = summary.view(db, [{"text": "Starší shrnutí.", "cites": [2]}], [result(2, 102)])
    assert old[0]["cites"] == [{"n": 2, "popover": None}]  # cached before quotes were kept
    skipping = summary.sentences(
        [text("Ministryně uvedla dvě věci", at(0, "Valorizace"), at(0, "Inflace je")), text(".")],
        SOURCES,
    )
    rows = [{"text": s.text, "cites": s.cites, "quotes": s.quotes} for s in skipping]
    (cite,) = summary.view(db, rows, [result(1, 101)])[0]["cites"]
    assert cite["quote"] == "Valorizace … Inflace je"  # words left out are marked


@pytest.fixture
def db(corpus, sessions):
    with sessions() as session:
        yield session


def page(db: Session, q: str) -> search.SearchPage:
    filters, errors = SearchFilters.parse({"q": [q]})
    return search.search(db, filters, errors)


def test_sources_hold_the_shown_and_matching_paragraphs(db: Session, monkeypatch):
    monkeypatch.setattr(summary, "WHOLE_SPEECH", 0)  # treat every speech as long
    result = page(db, "penzijní")
    found = summary.sources(db, result.results, result.highlights)
    assert [s.number for s in found] == [r["n"] for r in result.results[: summary.SOURCES]]
    for s, r in zip(found, result.results, strict=False):
        assert 0 < len(s.paragraphs) <= summary.MAX_PARAGRAPHS
        texts = [t for _, t in s.paragraphs]
        assert any(r["text"] in t for t in texts)  # the paragraph the result shows
        assert s.title.startswith(f"[{r['n']}] {r['speaker']['name']}")
    document = summary.documents(found, "penzijní")[0]
    assert document["citations"] == {"enabled": True}
    assert document["source"] == {
        "type": "text",
        "media_type": "text/plain",
        "data": found[0].text,
    }


def cited_answer(result: search.SearchPage) -> Scripted:
    return Scripted(text("Řečník mluvil o penzijním spoření", (0, 0, 20)), text("."))


def test_summary_is_written_once_recorded_and_cached(db: Session):
    result = page(db, "penzijní")
    writer = cited_answer(result)
    first = summary.summarize(db, writer, "penzijní", result.results, result.highlights, Decimal(5))
    assert first.status == "ok" and first.sources == 1
    assert first.sentences[0]["cites"] == [result.results[0]["n"]]
    usage = db.scalars(select(models.AIUsage)).one()
    assert (usage.purpose, usage.input_tokens, usage.output_tokens) == ("summary", 5000, 800)
    assert usage.cost_usd == Decimal("0.0009")  # 5,000 × $0.10 + 800 × $0.50 per million
    again = summary.summarize(db, writer, "penzijní", result.results, result.highlights, Decimal(5))
    assert again.sentences == first.sentences and len(writer.calls) == 1


def test_nothing_relevant_says_so(db: Session):
    result = page(db, "penzijní")
    found = summary.summarize(
        db, Scripted(text(summary.NOT_FOUND)), "penzijní", result.results, [], Decimal(5)
    )
    assert found.status == "none" and found.sentences == []


def test_monthly_limit_stops_summaries_before_any_request(db: Session):
    db.add(
        models.AIUsage(
            provider="anthropic",
            model="claude-haiku-5-5",
            purpose="summary",
            input_tokens=0,
            output_tokens=0,
            cost_usd=Decimal("4.999"),
        )
    )
    db.commit()
    result = page(db, "penzijní")
    writer = cited_answer(result)
    found = summary.summarize(db, writer, "penzijní", result.results, [], Decimal(5))
    assert found.status == "limit" and writer.calls == []


def test_refusals_are_unavailable_but_recorded(db: Session):
    result = page(db, "penzijní")
    writer = Scripted(stop_reason="refusal")
    found = summary.summarize(db, writer, "penzijní", result.results, [], Decimal(5))
    assert found.status == "unavailable"
    assert db.scalar(select(func.count()).select_from(models.AIUsage)) == 1


def test_search_page_loads_the_summary_after_the_results(client, monkeypatch):
    from rozprava import main

    monkeypatch.setattr(main, "summary_writer", lambda: None)
    assert "data-summary-src" not in client.get("/hledat", params={"q": "penzijní"}).text
    assert client.get("/api/shrnuti", params={"q": "penzijní"}).text == ""

    writer = Scripted(text("Řečník mluvil o penzijním spoření", (0, 0, 20)), text("."))
    monkeypatch.setattr(main, "summary_writer", lambda: writer)
    results = client.get("/hledat", params={"q": "penzijní"}).text
    assert 'data-summary-src="/api/shrnuti?q=penzijn%C3%AD"' in results
    assert 'id="cite-1"' in results  # popover sources for the chips
    later = client.get("/hledat", params={"q": "penzijní", "stranka": "2"}).text
    assert "data-summary-src" not in later
    fragment = client.get("/api/shrnuti", params={"q": "penzijní"}).text
    assert "Shrnutí · jazykový model" in fragment and 'data-cite="1"' in fragment
    assert 'data-pop="cite-1-1"' in fragment and 'id="cite-1-1"' in fragment
    assert "Podle 1&nbsp;projevu" in fragment
    assert "Anthropic" not in client.get("/jak-to-funguje").text  # no key configured
    monkeypatch.setattr(get_settings(), "anthropic_api_key", SecretStr("test"))
    SHARED.clear()
    assert "Anthropic" in client.get("/jak-to-funguje").text
