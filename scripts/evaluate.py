"""Check and score the evaluation set in eval/questions.yaml.

    uv run python scripts/evaluate.py check     # format, catalog numbers, verbatim evidence
    uv run python scripts/evaluate.py keyword   # score today's keyword search on `keywords`

Both read the local database only. Scores use the first result page (20
speeches): recall@20 of speeches judged relevant (grade 1-2), nDCG@10 with the
grades as gains, the reciprocal rank of the first grade-2 speech, and how many
hard negatives (grade 0) reach the top 10. Unjudged speeches count as not
relevant, so absolute scores are lower bounds; compare systems on the same set.
"""

import argparse
import math
import re
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from rozprava.queries.common import parse_catalog
from rozprava.queries.search import SearchFilters

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "eval" / "questions.yaml"
KINDS = ("event", "topic", "stance", "person", "paraphrase", "cross-term", "negative")
FILTERS = ("obdobi", "poslanec", "klub", "tisk", "od", "do")
EVIDENCE = (10, 300)


def load(path: Path = QUESTIONS) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def filter_params(question: Mapping[str, Any], q: str = "") -> dict[str, list[str]]:
    """The question's filters as /hledat query parameters."""
    params: dict[str, list[str]] = {"q": [q]} if q else {}
    for key, value in (question.get("filters") or {}).items():
        values = value if isinstance(value, list) else [value]
        params[key] = [str(v) for v in values]
    return params


def validate(data: Any) -> list[str]:
    """Problems with the file's structure; an empty list means it is well formed."""
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        return ["the file needs a `questions` list"]
    problems = []
    seen: set[str] = set()
    for n, q in enumerate(data["questions"], start=1):
        qid = q.get("id") if isinstance(q, dict) else None
        where = qid or f"question #{n}"
        if not isinstance(q, dict):
            problems.append(f"{where}: not a mapping")
            continue
        if not isinstance(qid, str) or not re.fullmatch(r"q\d{2,3}", qid):
            problems.append(f"{where}: id must look like q01")
        elif qid in seen:
            problems.append(f"{where}: duplicate id")
        seen.add(str(qid))
        for key in ("question", "keywords"):
            if not isinstance(q.get(key), str) or not q[key].strip():
                problems.append(f"{where}: `{key}` must be non-empty text")
        if q.get("kind") not in KINDS:
            problems.append(f"{where}: kind must be one of {', '.join(KINDS)}")
        filters = q.get("filters") or {}
        if not isinstance(filters, dict) or set(filters) - set(FILTERS):
            problems.append(f"{where}: filters may only use {', '.join(FILTERS)}")
        else:
            _, errors = SearchFilters.parse(filter_params(q))
            problems += [f"{where}: filter: {e}" for e in errors]
        judgments = q.get("judgments") or []
        if not isinstance(judgments, list):
            problems.append(f"{where}: `judgments` must be a list")
            continue
        speeches: set[str] = set()
        for j in judgments:
            slug = j.get("speech") if isinstance(j, dict) else None
            label = f"{where} {slug}"
            if not isinstance(slug, str) or parse_catalog(slug) is None:
                problems.append(f"{label}: speech must be a catalog number like 10-034-0644-2")
                continue
            if slug in speeches:
                problems.append(f"{label}: judged twice")
            speeches.add(slug)
            if j.get("grade") not in (0, 1, 2):
                problems.append(f"{label}: grade must be 0, 1 or 2")
            evidence = j.get("evidence")
            if not isinstance(evidence, str) or not EVIDENCE[0] <= len(evidence) <= EVIDENCE[1]:
                problems.append(f"{label}: evidence must be {EVIDENCE[0]}–{EVIDENCE[1]} characters")
            elif "\n" in evidence or "¶" in evidence:
                problems.append(f"{label}: evidence must come from a single paragraph")
            if j.get("grade") == 0 and not j.get("note"):
                problems.append(f"{label}: a hard negative needs a note saying why")
        grades = [j.get("grade") for j in judgments if isinstance(j, dict)]
        if q.get("kind") == "negative" and any(g in (1, 2) for g in grades):
            problems.append(f"{where}: a negative question cannot have relevant speeches")
        if q.get("kind") != "negative" and 2 not in grades:
            problems.append(f"{where}: needs at least one grade-2 speech")
    return problems


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def check_evidence(session, data: Mapping[str, Any]) -> list[str]:
    """Every judged speech is current and contains its evidence verbatim."""
    problems = []
    for q in data["questions"]:
        for j in q.get("judgments") or []:
            label = f"{q['id']} {j['speech']}"
            text = speech_text(session, j["speech"])
            if text is None:
                problems.append(f"{label}: no current speech with this catalog number")
            elif normalize(j["evidence"]) not in normalize(text):
                problems.append(f"{label}: evidence not found verbatim")
    return problems


def speech_text(session, slug: str) -> str | None:
    """Text of the speech's current revision, or None when there is none."""
    from sqlalchemy import select

    from rozprava import models
    from rozprava.queries import common

    parsed = parse_catalog(slug)
    assert parsed
    term_number, sitting, page, anchor = parsed
    term = common.terms(session).get(term_number)
    if term is None:
        return None
    revision = session.scalar(
        select(models.SpeechRevision)
        .join(models.Speech, models.Speech.current_revision_id == models.SpeechRevision.id)
        .where(
            models.Speech.term_id == term.id,
            models.Speech.sitting_number == sitting,
            models.Speech.page == page,
            models.Speech.anchor == anchor,
        )
    )
    return revision.text if revision else None


def recall_at(ranked: Sequence[str], grades: Mapping[str, int], k: int) -> float | None:
    relevant = {s for s, g in grades.items() if g > 0}
    if not relevant:
        return None
    return len(relevant.intersection(ranked[:k])) / len(relevant)


def ndcg_at(ranked: Sequence[str], grades: Mapping[str, int], k: int) -> float | None:
    def dcg(gains: Sequence[int]) -> float:
        return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(gains))

    ideal = dcg(sorted((g for g in grades.values() if g > 0), reverse=True)[:k])
    if ideal == 0:
        return None
    return dcg([max(grades.get(s, 0), 0) for s in ranked[:k]]) / ideal


def reciprocal_rank(ranked: Sequence[str], grades: Mapping[str, int]) -> float:
    return next((1 / (i + 1) for i, s in enumerate(ranked) if grades.get(s) == 2), 0.0)


def hard_negatives_at(ranked: Sequence[str], grades: Mapping[str, int], k: int) -> int:
    return sum(1 for s in ranked[:k] if grades.get(s) == 0)


def score(ranked: Sequence[str], grades: Mapping[str, int]) -> dict[str, float | None]:
    return {
        "recall@20": recall_at(ranked, grades, 20),
        "ndcg@10": ndcg_at(ranked, grades, 10),
        "rr": reciprocal_rank(ranked, grades) if 2 in grades.values() else None,
        "neg@10": hard_negatives_at(ranked, grades, 10),
    }


def run_keyword(session, data: Mapping[str, Any]) -> None:
    from rozprava.queries import search

    by_kind: dict[str, list[dict]] = defaultdict(list)
    print(f"{'id':5} {'kind':10} {'hits':>6} {'R@20':>5} {'nDCG10':>6} {'RR':>5} {'neg':>3}")
    for q in data["questions"]:
        filters, errors = SearchFilters.parse(filter_params(q, q["keywords"]))
        page = search.search(session, filters, errors)
        ranked = [r["catalog_slug"] for r in page.results]
        grades = {j["speech"]: j["grade"] for j in q.get("judgments") or []}
        scores = score(ranked, grades)
        by_kind[q["kind"]].append(scores)
        by_kind["all"].append(scores)
        cells = [f"{v:5.2f}" if isinstance(v, float) else f"{'-':>5}" for v in scores.values()]
        print(
            f"{q['id']:5} {q['kind']:10} {page.total:6} {cells[0]} {cells[1]:>6} {cells[2]} "
            f"{scores['neg@10']:3}"
        )
    print("\nmeans (questions with a defined score)")
    for kind, rows in sorted(by_kind.items(), key=lambda kv: kv[0] != "all"):
        means = []
        for metric in ("recall@20", "ndcg@10", "rr", "neg@10"):
            values = [r[metric] for r in rows if r[metric] is not None]
            means.append(f"{metric} {sum(values) / len(values):.2f}" if values else f"{metric} -")
        print(f"  {kind:10} n={len(rows):2}  " + "  ".join(means))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("command", choices=["check", "keyword"])
    parser.add_argument("--file", type=Path, default=QUESTIONS)
    args = parser.parse_args(argv)
    data = load(args.file)
    problems = validate(data)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    from rozprava.db import get_session_factory

    with get_session_factory()() as session:
        if args.command == "check":
            problems = check_evidence(session, data)
            judged = sum(len(q.get("judgments") or []) for q in data["questions"])
            print(f"{len(data['questions'])} questions, {judged} judgments")
            if problems:
                print("\n".join(problems), file=sys.stderr)
                return 1
            print("all evidence found verbatim in current speeches")
        else:
            run_keyword(session, data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
