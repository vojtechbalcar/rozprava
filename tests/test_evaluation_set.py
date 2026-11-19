"""The evaluation set is well formed and its scores are computed correctly.

Evidence is checked against the real archive by `scripts/evaluate.py check`;
these tests stay offline.
"""

import importlib.util
import math
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def evaluate():
    spec = importlib.util.spec_from_file_location(
        "evaluate", Path(__file__).parents[1] / "scripts/evaluate.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_questions_file_is_well_formed(evaluate):
    data = evaluate.load()
    assert evaluate.validate(data) == []
    kinds = {q["kind"] for q in data["questions"]}
    assert {"paraphrase", "person"} <= kinds


def test_validation_explains_problems(evaluate):
    data = {
        "questions": [
            {
                "id": "q1",
                "question": "Co?",
                "kind": "opinion",
                "filters": {"strana": "ANO", "od": "2026-13-01"},
                "keywords": "",
                "judgments": [
                    {"speech": "10-1-2-3", "grade": 3, "evidence": "krátké"},
                    {"speech": "10-001-0002-3", "grade": 0, "evidence": "dost dlouhý výňatek"},
                    {"speech": "10-001-0002-3", "grade": 1, "evidence": "dost dlouhý výňatek"},
                ],
            },
            {
                "id": "q02",
                "question": "Nic?",
                "kind": "negative",
                "filters": {"od": "2026-13-01"},
                "keywords": "nic",
                "judgments": [{"speech": "9-001-0001-1", "grade": 2, "evidence": "1234567890"}],
            },
        ]
    }
    problems = "\n".join(evaluate.validate(data))
    for expected in (
        "q1: id must look like q01",
        "`keywords` must be non-empty",
        "kind must be one of",
        "filters may only use",
        "10-1-2-3: speech must be a catalog number",
        "a hard negative needs a note",
        "10-001-0002-3: judged twice",
        "q1: needs at least one grade-2 speech",
        "q02: filter: Datum",
        "q02: a negative question cannot have relevant speeches",
    ):
        assert expected in problems


def test_filters_become_search_parameters(evaluate):
    question = {"filters": {"obdobi": [9, 10], "klub": ["ANO"], "od": "2026-02-01"}}
    assert evaluate.filter_params(question, "EET") == {
        "q": ["EET"],
        "obdobi": ["9", "10"],
        "klub": ["ANO"],
        "od": ["2026-02-01"],
    }


def test_scores(evaluate):
    grades = {"a": 2, "b": 1, "c": 0, "d": 2}
    ranked = ["c", "b", "x", "a"]
    scores = evaluate.score(ranked, grades)
    assert scores["recall@20"] == pytest.approx(2 / 3)
    assert scores["rr"] == pytest.approx(1 / 4)
    assert scores["neg@10"] == 1
    ideal = 3 + 3 / math.log2(3) + 1 / 2
    found = 1 / math.log2(3) + 3 / math.log2(5)
    assert scores["ndcg@10"] == pytest.approx(found / ideal)


def test_negative_questions_have_no_recall(evaluate):
    scores = evaluate.score(["a", "b"], {"a": 0})
    assert scores["recall@20"] is None
    assert scores["ndcg@10"] is None
    assert scores["rr"] is None
    assert scores["neg@10"] == 1
