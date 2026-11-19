"""Czech word forms: lemma keys, tagging during ingest and query expansion in search.

Most tests use a small dictionary analyzer, so they need neither the 26 MB model
nor live data. One test runs the real tagger when it is installed.
"""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from rozprava import models
from rozprava.ingest.forms import index_forms, pending
from rozprava.morphology import (
    MODEL,
    Lemmatizer,
    MorphologyUnavailable,
    Token,
    forms_vector,
    lemma_key,
    lemma_query,
    model_path,
)
from rozprava.queries import search
from rozprava.queries.search import SearchFilters, Term, parse_query
from rozprava.settings import Settings
from rozprava.typography import fold
from rozprava.web import SHARED

LEMMAS = {
    "důchod": "důchod",
    "důchodu": "důchod",
    "důchody": "důchod",
    "důchodů": "důchod",
    "rozpočet": "rozpočet",
    "rozpočtu": "rozpočet",
}
DUCHOD = re.compile(r"\b(?:důchod|důchodu|důchody|důchodů)\b", re.IGNORECASE)
SR = models.SpeechRevision


class DictionaryAnalyzer:
    """Words as written, with the inflected forms above mapped to their lemma."""

    def __init__(self, name: str = "test-dictionary"):
        self.name = name

    def tokens(self, text: str) -> list[Token]:
        words = [w for w in re.findall(r"\w+", text) if not w.isdigit()]
        return [Token(w, LEMMAS.get(w.lower()) or w.lower()) for w in words]


@pytest.mark.parametrize(
    ("lemma", "tag", "key"),
    [
        ("stát-1_^(státní_útvar)", "NNIS1-----A----", "stát-1"),
        ("stát-3_^(stojím_stojíš)", "VB-S---3P-AA---", "stát-3"),
        ("Fialův_;Y_^(*2a)", "AUFP1M---------", "fiala"),
        ("Babišův_;Y_^(*2)", "AUFS1M---------", "babiš"),
        ("státní", "AAIS1----1N----", "nestátní"),
        ("souhlasit", "VB-S---3P-NA---", "nesouhlasit"),
        ("e-mail", "NNIS1-----A----", "e-mail"),
        ("O'Neill_;Y", "NNMS1-----A----", "oneill"),
        ("ab_^(*5)", "AUIS1M---------", "ab"),  # cut longer than the lemma: unchanged
        (",", "Z:-------------", None),
        ("2024", "C=-------------", None),
    ],
)
def test_lemma_keys(lemma: str, tag: str, key: str | None):
    assert lemma_key(lemma, tag) == key


def test_forms_vector_counts_word_positions_within_postgresql_limits():
    tokens = [Token("Důchody", "důchod"), Token("a", "a-1"), Token("důchodů", "důchod")]
    assert forms_vector(tokens) == "'~důchod':1,3 '~a-1':2"
    many = forms_vector([Token("a", "a")] * 16383 + [Token("b", "b")] * 3)
    assert "'~b':16383" in many  # positions past the limit collapse, without duplicates
    assert many.split(" ")[0].count(",") == 255  # at most 256 positions per lexeme


def test_lemma_query_only_contains_safe_keys():
    assert lemma_query(["a'b", "x\\y", "ok", "OK"]) == "'~ab' | '~xy' | '~ok'"


def test_query_syntax():
    assert parse_query('důchod "penzijní spoření" OR -reforma rozpočet,') == [
        [Term("důchod"), Term("penzijní spoření", phrase=True)],
        [Term("reforma", negated=True), Term("rozpočet")],
    ]
    assert parse_query('-"celá fráze" slovo') == [
        [Term("celá fráze", phrase=True, negated=True), Term("slovo")]
    ]
    assert parse_query('"neukončená fráze') == [[Term("neukončená fráze", phrase=True)]]
    assert parse_query("OR or - „“") == []


def add_forms(db: Session, *rows: tuple[str, str, int]) -> None:
    db.add_all(models.WordForm(form=f, lemma=k, folded=fold(f), count=n) for f, k, n in rows)
    db.flush()


def test_expansion_prefers_the_written_form_and_its_usual_lemma(db: Session):
    add_forms(
        db,
        ("byt", "byt", 799),
        ("bytu", "byt", 500),
        ("být", "být", 20000),
        ("je", "být", 300000),
        ("důchod", "důchod", 2118),
        ("důchodu", "důchod", 5000),
        ("duchod", "duchod", 1),
        ("stát", "stát-1", 800),
        ("stát", "stát-3", 150),
        ("stát", "stát-2", 50),
        ("státu", "stát-1", 900),
        ("stojí", "stát-3", 3000),
        ("státy", "stát-1", 10),
        ("státy", "státa", 90),
    )
    found = search.expand(db, ["byt", "duchodu", "duchod", "stát", "Důchod", "neznámé"])
    # "byt" is a word of its own, not "být" typed without accents.
    assert found["byt"].lemmas == ["byt"] and found["byt"].forms == ["bytu"]
    assert found["duchodu"].lemmas == ["důchod"]
    assert found["duchodu"].forms == ["důchodu", "důchod"]
    assert found["duchod"].lemmas == ["důchod"]  # a rare exact spelling yields
    # A word stands for its usual lemma; forms that mostly mean something else
    # (státy) or belong to the other lemma (stojí) are not highlighted.
    assert found["stát"].lemmas == ["stát-1"] and found["stát"].forms == ["státu"]
    assert found["důchod"].lemmas == ["důchod"]
    assert found["neznámé"].lemmas == [] and found["neznámé"].forms == []


def test_tagging_is_resumable_and_counts_each_word_once(corpus, sessions):
    analyzer = DictionaryAnalyzer()
    with sessions() as session:
        current = session.scalar(select(func.count()).where(SR.retired_at.is_(None)))
        assert pending(session, analyzer.name) == current > 0
    first = index_forms(sessions, analyzer, limit=5)
    assert first["revisions"] == 5
    rest = index_forms(sessions, analyzer)
    assert rest["revisions"] == current - 5
    assert index_forms(sessions, analyzer)["revisions"] == 0
    with sessions() as session:
        assert pending(session, analyzer.name) == 0
        words = session.scalar(select(func.sum(models.WordForm.count)))
        assert words == first["words"] + rest["words"]
        matching = session.scalar(
            select(func.count()).where(
                SR.retired_at.is_(None), SR.search.op("@@")(text("'~důchod'::tsquery"))
            )
        )
        texts = session.scalars(select(SR.text).where(SR.retired_at.is_(None)))
        assert matching == sum(1 for t in texts if DUCHOD.search(t)) > 0
    rebuilt = index_forms(sessions, analyzer, rebuild=True)
    assert rebuilt["revisions"] == current
    with sessions() as session:
        assert session.scalar(select(func.sum(models.WordForm.count))) == words


@pytest.fixture
def tagged(corpus, sessions):
    index_forms(sessions, DictionaryAnalyzer())
    with sessions() as session:
        yield session


def run(db: Session, q: str) -> search.SearchPage:
    filters, errors = SearchFilters.parse({"q": [q]})
    return search.search(db, filters, errors)


def current_ids(db: Session, pattern: re.Pattern[str]) -> set[int]:
    rows = db.execute(select(SR.id, SR.text).where(SR.retired_at.is_(None)))
    return {i for i, t in rows if pattern.search(t)}


def test_unquoted_words_find_other_forms_and_quotes_stay_exact(tagged: Session, monkeypatch):
    monkeypatch.setattr(search, "PER_PAGE", 500)
    every_form = current_ids(tagged, DUCHOD)
    exact = current_ids(tagged, re.compile(r"\bdůchod\b", re.IGNORECASE))
    page = run(tagged, "důchod")
    assert {r["id"] for r in page.results} == every_form
    assert len(exact) < len(every_form)
    assert {r["id"] for r in run(tagged, '"důchod"').results} == exact
    assert {r["id"] for r in run(tagged, "duchody").results} == every_form  # no accents
    assert "důchody" in page.highlights and "důchody" in page.expansions["důchod"].forms
    for result in page.results:
        assert DUCHOD.search(result["text"])  # the excerpt shows a matching form


def test_exclusion_and_alternatives_cover_every_form(tagged: Session, monkeypatch):
    monkeypatch.setattr(search, "PER_PAGE", 500)
    with_duchod = current_ids(tagged, DUCHOD)
    with_rozpocet = current_ids(tagged, re.compile(r"\b(?:rozpočet|rozpočtu)\b", re.I))
    either = run(tagged, "rozpočet OR důchod")
    assert {r["id"] for r in either.results} == with_duchod | with_rozpocet
    without = run(tagged, "-důchod")
    current = tagged.scalar(select(func.count()).where(SR.retired_at.is_(None))) or 0
    assert without.total == current - len(with_duchod)
    assert not {r["id"] for r in without.results} & with_duchod


def test_search_page_lists_forms_and_admits_untagged_speeches(client: TestClient, sessions):
    response = client.get("/hledat", params={"q": "důchod"})
    assert "nemáme určené tvary slov" in response.text  # nothing tagged yet
    index_forms(sessions, DictionaryAnalyzer(MODEL))
    SHARED.clear()
    response = client.get("/hledat", params={"q": "důchod"})
    assert "nemáme určené tvary slov" not in response.text
    assert "data-word-forms" in response.text and "důchody" in response.text
    assert '<mark class="term">důchody</mark>' in response.text
    how = client.get("/jak-to-funguje").text
    assert "MorphoDiTa" in how and "CC BY-NC-SA 4.0" in how


MODEL_FILE = model_path(Settings().data_dir)


def test_missing_model_is_reported_not_crashed(tmp_path):
    with pytest.raises(MorphologyUnavailable, match="fetch_morphology"):
        Lemmatizer(tmp_path / "missing.tagger")


@pytest.mark.skipif(not MODEL_FILE.is_file(), reason="Czech morphology model not installed")
def test_real_tagger_separates_homonyms_negation_and_possessives():
    sentence = "Stát stojí za to. Fialova vláda nesouhlasí s nestátními školami."
    keys = {t.form: t.key for t in Lemmatizer(MODEL_FILE).tokens(sentence)}
    assert keys["Stát"] == "stát-1" and keys["stojí"] == "stát-3"
    assert keys["Fialova"] == "fiala" and keys["školami"] == "škola"
    assert keys["nesouhlasí"] == "nesouhlasit" and keys["nestátními"] == "nestátní"
    assert "." not in keys
