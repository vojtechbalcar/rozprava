"""Search against PostgreSQL over the imported fixture corpus (both terms)."""

import datetime as dt
import math
import re

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rozprava import models
from rozprava.queries import search
from rozprava.queries.search import SearchFilters, query_terms
from rozprava.typography import fold


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


def test_filler_words_are_left_out_unless_the_query_has_nothing_else():
    groups, dropped = search.without_filler(
        search.parse_query('jak se změnily důchody OR "jak se má" -se')
    )
    assert [[t.text for t in group] for group in groups] == [
        ["změnily", "důchody"],
        ["jak se má", "se"],  # phrases and exclusions are kept as typed
    ]
    assert dropped == ["jak", "se"]
    only, none = search.without_filler(search.parse_query("Co je to"))
    assert [t.text for t in only[0]] == ["Co", "je", "to"] and none == []
    # "byt" (a flat), "moc" (power) and "ANO" (a party) are words of their own.
    assert search.without_filler(search.parse_query("byt moc ANO na"))[1] == ["na"]


def test_longer_queries_may_lack_one_word_in_four():
    assert [search.needed(n) for n in range(1, 9)] == [1, 2, 2, 3, 4, 5, 6, 6]
    for n in range(3, 40):
        assert 0 < n - search.needed(n) <= max(1, n // 4)
        assert math.comb(n, search.needed(n)) <= search.MAX_COMBINATIONS


def tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", fold(text)))


def test_query_with_few_complete_matches_also_finds_partial_ones(db: Session, monkeypatch):
    monkeypatch.setattr(search, "PER_PAGE", 500)
    words = ["penzijní", "spoření", "státní", "příspěvek"]
    present = {
        i: sum(fold(w) in tokens(t) for w in words)
        for i, t in db.execute(
            select(models.SpeechRevision.id, models.SpeechRevision.text).where(
                models.SpeechRevision.retired_at.is_(None)
            )
        )
    }
    every = {i for i, n in present.items() if n == 4}
    most = {i for i, n in present.items() if n >= 3}
    assert len(every) < len(most) < search.RELAX_BELOW  # the fixture exercises relaxing

    page = run(db, q="jak se " + " ".join(words))
    assert page.dropped == ["jak", "se"]
    assert {r["id"] for r in page.results} == most and page.total == len(most)
    assert page.partial == (3, 4) and page.strict_total == len(every)
    found = [present[r["id"]] for r in page.results]
    assert found == sorted(found, reverse=True)  # speeches with every word come first
    assert {r["id"] for r in page.results[: len(every)]} == every

    monkeypatch.setattr(search, "RELAX_BELOW", len(every))  # enough complete matches
    strict = run(db, q=" ".join(words))
    assert {r["id"] for r in strict.results} == every and strict.partial is None
    assert run(db, q='"penzijní spoření" státní příspěvek').partial is None  # 2 plain words


def test_search_page_explains_left_out_and_missing_words(client):
    response = client.get("/hledat", params={"q": "kdo penzijní spoření státní příspěvek"})
    page = response.text.replace("\xa0", " ")
    assert "Běžná slova jsme vynechali: kdo." in page
    assert "a tak ukazujeme i projevy s aspoň 3 ze 4 slov. Projevy se všemi" in page
    assert "Běžná slova jako" in client.get("/jak-to-funguje").text
