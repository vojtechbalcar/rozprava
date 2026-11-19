---
type: decision
updated: 2026-11-19
status: current
---

# Czech word forms in search

Related: [[functional-app-design]], [[local-app-verification]], [[feasibility-research]],
[[dev-environment]], [[stack-decision]]

## Decision and scope

On 19 November 2026, after the functional phase was finished and opened as PR #1,
the user chose the next work, in this order: Czech word forms in search, then AI
meaning search with cited summaries, then automatic daily updates. A parallel
session reported the user's split of that work: this thread owns word forms, and
the other session owns the AI evaluation set and daily updates. Neither starts
the other's work without checking first.

**Problem.** Search matched exact word forms only, and Czech inflects heavily.
On the full archive, "důchod" found 867 speeches, but 3,668 contain some form of
it. For "Ukrajina" the figures were 615 and 2,882, and for "rozpočet" 3,283 and 8,243.

**Decision.** Tag every stored speech at import with **MorphoDiTa** and the
**MorfFlex CZ 2.1 + PDT-C 2.0** model (`czech-morfflex2.1-pdtc2.0-250909`, ÚFAL MFF
UK, CC BY-NC-SA 4.0). An unquoted query word matches its exact form *and* every
form of the lemma it usually stands for. Quoted text stays exact.

**Licence consequence.** The model's licence is non-commercial share-alike.
That is fine for this non-commercial civic and portfolio project. A commercial
use would need a different model and a re-tag. The methodology page credits the
tool, model, institute and licence.

## Options compared

On 19 Nov the options were run over the archive vocabulary (234,029 forms, 20.4 M
tokens) for 40 typical queries. Tokens matched, in total:

| Method | Tokens matched | Main failures |
| --- | ---: | --- |
| Exact form (before) | 148,812 | Misses every other case form |
| Light stemmer (Lucene `CzechStemmer`) | 403,239 | Misses stem changes (rozpočet/rozpočtu, obec/obce, daň/daně, dítě/děti). Merges unrelated words: kraj→krajina, válka→MP Válková, Rusko→ruský/růst |
| simplemma (MIT code, mixed data licences) | 493,351 | Fails on declined names: "Babiš" misses Babiše (3,719) and Babišovi; "Fiala" misses Fialu/Fialou; all exekuce forms missed |
| MorphoDiTa, all possible lemmas | 472,497 | Ambiguity noise: stát picks up stav, plus guessed junk (dezolátů) |
| **MorphoDiTa tagger in context (chosen)** | — | Picks one lemma per word from its sentence |

A parallel evaluation scored 44 queries against MorfFlex paradigms (so it
favours MorphoDiTa's recall), weighted by frequency. Recall: exact 33 %, light
stemmer 86 %, simplemma 97 % (Babiš 50 %, Okamura 60 %), hunspell 99 %,
MorphoDiTa 99 %. Hunspell drops negation, merges válka with Válková and misses
děti. It would also have needed dictionary files installed in Homebrew's
PostgreSQL share directory, which is lost on upgrade, and loaded per connection.

Rejected: hunspell inside PostgreSQL, simplemma and the light stemmer, for the
reasons above. Query-time tagging was also rejected: the model takes about
390 MB of RAM and 1.8 s to load, so only ingest loads it.

The 2.1 model (Sep 2025) agreed with the earlier 2.0 model (`220710`) on 97.5 %
of 245,000 sample tokens. Most differences were sense numbers on particles. Speed
was equal. The newer one is used.

## How it works

- **Lemma keys** (`morphology.lemma_key`). The MorfFlex lemma keeps its sense
  number and drops its comments: `stát-1` (state), `stát-2` (become) and `stát-3`
  (stand, cost) stay apart. A possessive adjective leads to its noun (`Fialův_;Y_^(*2a)` →
  `fiala`), so "Fiala" finds "Fialova vláda". MorfFlex puts negation in tag
  position 11, so negated forms get a separate `ne…` key: "státní" does not find
  "nestátní". The party ANO gets its own sense (`ano-88`), distinct from "ano" (yes).
- **Storage.** `speech_revision.forms` holds `~lemma` lexemes with word positions.
  The generated `search` column is now `to_tsvector('rozprava', text) ||
  coalesce(forms, '')`, so one GIN index and one ranking cover both. The
  text-search parser never produces a lexeme starting with `~`, so exact phrases
  cannot match a lemma. `forms_model` records which model tagged the revision.
- **Statistics.** `word_form(form, lemma, folded, count)` records how often each
  lowercase written form stood for each lemma. Web requests expand query words
  through it and never load the model.
- **Query expansion** (`queries/search.py`). A typed word keeps its exact form
  when that form accounts for at least 1 % of the uses of its accent-free
  spelling. So "byt" stays byt, not být, while "duchodu" and a rare misspelling
  "duchod" resolve to důchod. The word then stands for lemmas with at least 20 %
  of its uses (at most three), so "stát" means stát-1. The exact form is always
  ORed in, so a query never finds less than before. Forms are highlighted only
  for a lemma they mostly (≥ 50 %) stand for. Exclusions remove every form; OR
  and phrases follow websearch syntax, parsed in Python and combined with
  `tsquery_and/or/not`.
- **Interface.** Under the query, a meta line lists the forms included. While
  any current speech is untagged, the search page says how many match only as
  typed. The methodology page explains the rules and limits.

## Operation

```sh
uv run python scripts/fetch_morphology.py     # once: 103 MB download, keeps the 26 MB tagger
caffeinate -i uv run python -m rozprava.ingest forms   # tag untagged speeches (resumable, batches of 500)
caffeinate -i uv run python -m rozprava.ingest forms --rebuild  # re-tag all, recount statistics
```

A full tagging run takes about 20 minutes and rewrites every speech row.
Afterwards, reclaim the space with `VACUUM (FULL, ANALYZE) speech_revision` (see Results).

`backfill`, `update`, `refresh` and `assemble` tag new revisions automatically
when the model is installed. Otherwise they log a warning and the speeches match
only exact words until `forms` runs. `status` reports tagged and waiting speeches.
`word_form` counts only grow between rebuilds; retired revisions are not
subtracted. A different model name makes every revision pending again.

## Limits

- A word that never occurs in the archive is matched only as typed. The web
  process has no model to analyse it.
- Query words have no sentence context: a homonym means its most common sense
  in the archive. Case is folded, so "ANO" expands like "ano" (yes). The exact
  form still matches as before.
- The tagger errs on rare names and unusual forms. Results remain verbatim
  speeches; only matching and highlighting are affected.

## Problem: the first full tagging run slowed down and stalled

**Symptom.** It began at about 79 s per 5,000 speeches. After 60,000 it had
slowed to about 6 minutes per 5,000. It then stopped advancing and was killed
by the session's one-hour limit at 62,400 of 93,738. The import run record
stayed "running"; it was marked interrupted by hand.

**Causes.** There were two.

1. *Bloat.* Every batch of 200 upserted `word_form` counts for the same common
   pairs (je → být, a → a-1 …). Autovacuum's default 20 % threshold could not
   keep up: 175,000 live rows carried 2.3 million dead ones (233 MB). Every
   non-HOT update added entries to all three indexes. The upsert grew from 0.7
   to 4.8 s per batch.
2. *Sleep.* The Mac, on battery at 28 %, went into idle sleep from 13:03 to
   14:02 (`pmset -g log`), so the job made no progress until its limit.

**Tried first.** Suspected the import-lock connection, which sits idle in a
transaction, of holding back vacuum's horizon. It does not: `backend_xmin` is
NULL in read committed. A rolled-back comparison of fillfactors was
inconclusive, because dead rows inside one open transaction cannot be pruned.

**Fix.** `VACUUM FULL word_form` brought it to 26 MB and the upsert back to
0.7 s. Migration 0004 sets `fillfactor=50`, so count updates stay on their page
(HOT, as count is not indexed), and vacuums at 2 % dead rows. Batches are now
500 revisions. Long imports run under `caffeinate -i`, which prevents idle
sleep only while the command runs. Each batch commits its vectors and counts
together, so the killed run lost nothing; the next `forms` run continued from
62,400.

## Results (19 Nov 2026, live archive)

All 93,738 current speeches are tagged (`status`: 0 waiting). Run 8 stopped at
62,400, as described above. Run 9 tagged the remaining 31,338 (7.1 M words) in
8 minutes, at a steady 60–75 s per 5,000. `word_form` holds 212,118 form/lemma
pairs covering 20.4 M words.

Speeches found, exact form (`"…"`) vs all forms; median of three warm runs,
including counts, facets and the ranked first page:

| Query | Exact | All forms | ms |
| --- | ---: | ---: | ---: |
| důchod | 867 | 2,613 | 89 |
| duchodu (no accents) | 1,868 | 2,613 | 82 |
| Ukrajina | 615 | 2,490 | 84 |
| penze | 233 | 423 | 64 |
| daň | 1,378 | 3,876 | 203 |
| exekuce | 165 | 420 | 30 |
| zemědělec | 96 | 569 | 38 |
| nájem | 226 | 456 | 45 |
| Babiš | 2,495 | 4,033 | 148 |
| Fiala | 2,051 | 3,778 | 114 |
| rozpočet | 3,282 | 6,889 | 132–608 |
| vláda | — | 17,220 | 415 |

"penze" in term 9 for ANO: 37 ms. The phrase `"duchodova reforma"`: 51 ms.
Browsing newest: 169 ms. The untagged count on the search page: 21 ms, cached
for 60 s.

**Storage.** `speech_revision` went from 395 to 809 MB after `VACUUM FULL`. The
search vector grew from 177 to 341 MB, and the separate `forms` column is
166 MB. The GIN index went from 55 to 119 MB; the database from 1,022 to
1,550 MB. Tagging rewrites every row, so compact afterwards
(`VACUUM (FULL, ANALYZE) speech_revision`, 63 s). Keeping `forms` beside the
generated column costs 166 MB. In exchange, no trigger or insert path can
forget to update `search`.

**Slow broad queries.** Ranking reads each match's search vector
(`ts_rank_cd`), and these are now twice as large. Very common words are slow:
`pan` (62,663 speeches) takes 3.5 s and exact `"pan"` 2.1 s. Exact broad
queries were already slow before; this made them slower. Possible fixes,
not done: a RUM index (ranking from the index), capping the ranked candidate
set, or a larger `shared_buffers` (default 128 MB) so vectors stay cached.
