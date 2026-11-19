# Evaluation set

`questions.yaml` holds Czech questions about the 9th and 10th terms, with graded
judgments of speeches in the local archive. It is the yardstick for search
changes (word forms, semantic search) and later for cited AI summaries.

```sh
uv run python scripts/evaluate.py check     # format, catalog numbers, verbatim evidence
uv run python scripts/evaluate.py keyword   # score today's keyword search
uv run pytest tests/test_evaluation_set.py  # offline format and metric checks
```

## What a question contains

- `question`: phrased the way a journalist, student or citizen might ask it.
- `kind`: `event`, `topic`, `stance` (a side's position), `person` (one MP),
  `paraphrase` (the transcripts use different words), `cross-term`, or
  `negative` (the archive cannot answer it; a good system says so).
- `filters`: the `/hledat` URL parameters a person would set (`obdobi`, `klub`,
  `poslanec`, `od`, `do`, `tisk`).
- `keywords`: what the same person would type into today's keyword search.
- `judgments`: catalog numbers with grade 2 (answers the question), 1 (related
  or partial) or 0 (a hard negative: looks relevant but is not, with a `note`).
  Each has a verbatim `evidence` excerpt from one paragraph.

Hard negatives cover the risks named in [[feasibility-research]]: speakers who
quote or paraphrase an opponent, coalition rebuttals mistaken for the
opposition's reasons, two MPs with the same surname (Petr and Radim Fiala),
and passing mentions in unrelated debates. Notes flag quoted words, so a
summary that attributes them to the speaker can be marked wrong.

## How the judgments were made

Claude drafted the questions on 19 November 2026 and judged candidates found
by several keyword searches per question (pooling), reading the matching
passages in the stored transcripts. The judgments are therefore incomplete:
an unjudged speech is unknown, not irrelevant, and keyword-findable speeches
are over-represented. Scores are lower bounds and only comparable between
systems run on the same version of the file.

When a new retrieval method is evaluated, judge its top unjudged results and
add them (pool expansion) before comparing it with keyword search. A person
should review the questions and grades before they are used to choose a
model.

`check` fails when a transcript revision changes a judged passage or a speech
leaves the current transcript; update or remove the judgment.
