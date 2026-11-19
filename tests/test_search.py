"""Search against PostgreSQL over the imported fixture corpus (both terms)."""

import datetime as dt

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rozprava import models
from rozprava.queries import search
from rozprava.queries.search import SearchFilters, query_terms


def run(db: Session, **params: str | list[str]) -> search.SearchPage:
    lists = {k: v if isinstance(v, list) else [v] for k, v in params.items()}
    filters, errors = SearchFilters.parse(lists)
    return search.search(db, filters, errors)


def speakers(page: search.SearchPage) -> set[str]:
    return {r["speaker"]["name"] for r in page.results}


@pytest.fixture
def db(corpus, sessions):
    with sessions() as session:
        yield session


def test_accent_free_keywords_and_quoted_phrases(db: Session):
    phrase = run(db, q='"jednorazovych darecku"')
    assert phrase.total == 1 and speakers(phrase) == {"Olga Richterová"}
    result = phrase.results[0]
    assert "jednorázových dárečků" in result["text"]  # stored text keeps its accents
    # The speech starts on 642; the phrase is on 644, where the result link leads.
    assert (result["page"], result["catalog"]["page"]) == (644, 642)
    assert result["anchor"].startswith("p-10-034-0642-2-")
    assert run(db, q='"darecku jednorazovych"').total == 0  # phrase order matters
    assert run(db, q="JEDNORÁZOVÝCH").total == 1


def test_and_or_and_exclusion(db: Session):
    both = run(db, q="penzijní spoření")
    either = run(db, q="whistleblowerů OR jednorázových")
    assert speakers(either) == {"Pavel Blažek", "Olga Richterová"}
    without = run(db, q="penzijní -penzijko")
    assert 0 < without.total < run(db, q="penzijní").total
    texts = db.scalars(
        select(models.SpeechRevision.text).where(
            models.SpeechRevision.id.in_([r["id"] for r in without.results])
        )
    )
    assert all("penzijko" not in t.lower() for t in texts)
    assert both.total <= run(db, q="penzijní").total


def test_filters(db: Session):
    assert {r["term"] for r in run(db, obdobi="9").results} == {9}
    stan = run(db, klub="STAN", obdobi="10")
    assert "Jan Papajanovský" in speakers(stan)
    assert all(r["speaker"]["party"] == "STAN" for r in stan.results)
    person = run(db, poslanec="6473")
    assert speakers(person) == {"Olga Richterová"}
    bill = run(db, tisk="10-285")
    assert bill.total > 0
    assert {r["agenda"]["tisk"] for r in bill.results} == {285}
    assert run(db, tisk="9-285").total == 0  # the same number in another term
    day = run(db, od="2026-11-06", do="2026-11-06")
    assert {r["date"] for r in day.results} == {"2026-11-06"}
    assert run(db, od="2030-01-01").total == 0


def test_facets_count_the_whole_filtered_match_set(db: Session, monkeypatch):
    monkeypatch.setattr(search, "PER_PAGE", 2)
    page = run(db, obdobi="10")
    assert len(page.results) == 2 < page.total
    assert sum(m["count"] for m in page.facets["months"]) == page.total
    assert sum(p["n"] for p in page.facets["parties"]) <= page.total
    stan = next(p for p in page.facets["parties"] if p["value"] == "STAN")
    assert stan["n"] == run(db, obdobi="10", klub="STAN").total
    selected = run(db, klub="Motoristé", q="whistleblowerů")
    assert selected.total == 0  # a selected filter stays visible and removable at zero
    assert [p["value"] for p in selected.facets["parties"]] == ["Motoristé"]
    assert selected.facets["parties"][0]["params"] == {"q": "whistleblowerů"}


def test_pages_are_deterministic_and_complete(db: Session, monkeypatch):
    monkeypatch.setattr(search, "PER_PAGE", 3)
    first = run(db, q="pan")
    ids = []
    for number in range(1, first.pages + 1):
        page = run(db, q="pan", stranka=str(number))
        assert [r["id"] for r in page.results] == [
            r["id"] for r in run(db, q="pan", stranka=str(number)).results
        ]
        ids += [r["id"] for r in page.results]
    assert len(ids) == len(set(ids)) == first.total
    beyond = run(db, q="pan", stranka=str(first.pages + 1))
    assert beyond.out_of_range and beyond.results == []


def test_empty_query_browses_newest_first(db: Session):
    page = run(db)
    dates = [r["date"] for r in page.results]
    assert dates == sorted(dates, reverse=True)
    assert page.total == db.scalar(
        select(func.count()).where(models.SpeechRevision.retired_at.is_(None))
    )


@pytest.mark.parametrize(
    "q",
    [
        "'; DROP TABLE speech_revision; --",
        '"neukončená fráze',
        "a & b | !c <-> d:*",
        "\\\\ %_ ''",
        "OR OR -",
    ],
)
def test_injection_like_input_is_only_text(db: Session, q: str):
    page = run(db, q=q)
    assert page.total >= 0
    assert (db.scalar(select(func.count()).select_from(models.SpeechRevision)) or 0) > 0


def test_invalid_parameters_are_explained_in_czech():
    filters, errors = SearchFilters.parse(
        {
            "q": ["x" * 300],
            "obdobi": ["7"],
            "poslanec": ["Novák"],
            "tisk": ["285"],
            "od": ["2026-02-30"],
            "razeni": ["nahodne"],
            "stranka": ["0"],
        }
    )
    assert len(filters.q) == search.MAX_QUERY
    assert filters.terms == () and filters.people == () and filters.bills == ()
    assert filters.date_from is None and filters.sort == "relevance" and filters.page == 1
    assert len(errors) == 7 and all(isinstance(e, str) for e in errors)
    swapped, notes = SearchFilters.parse({"od": ["2026-03-01"], "do": ["2026-01-01"]})
    assert (swapped.date_from, swapped.date_to) == (dt.date(2026, 1, 1), dt.date(2026, 3, 1))
    assert notes


@pytest.mark.parametrize("value", ["²", "９", "9" * 5000])
def test_numeric_filters_reject_non_ascii_and_oversized_input(value):
    filters, errors = SearchFilters.parse(
        {"obdobi": [value], "poslanec": [value], "stranka": [value]}
    )
    assert filters.terms == () and filters.people == () and filters.page == 1
    assert len(errors) == 3


def test_highlight_terms_follow_the_query_syntax():
    assert query_terms('"penzijní spoření" OR důchod -reforma') == ["penzijní spoření", "důchod"]
    assert query_terms('-"celá fráze" slovo,') == ["slovo"]
