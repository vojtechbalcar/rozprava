---
type: decision
updated: 2026-11-26
status: in progress
---

# Related search and cited summaries

Related: [[czech-word-forms]], [[feasibility-research]], [[functional-app-design]],
[[stack-decision]], [[local-app-verification]]

## Where things stood (26 Nov 2026)

`main` had word forms (PRs #1 and #2): "důchod" finds 2,613 speeches, the exact
form only 867. Longer queries already ignored word order, but every word was
required, filler words included. "jak se změnily důchody" found 489 speeches,
"změnily důchody" 552 and "valorizace důchodů" 883. Search did not know that
penze and důchod mean the same thing. The 19 Nov evaluation set (branch
`feature/ai-evaluation-set`, unmerged) had questions and graded judgments but no
retrieval to score beyond keywords.

## Decisions (user, 26 Nov 2026)

1. **Keyword fix and meaning search, both.** Ignore Czech filler words and let a
   longer query match a speech that lacks one of its words, ranking the ones that
   have all of them first. Then add meaning search.
   Rejected: keyword fix only (still blind to synonyms), and skipping straight
   to summaries.
2. **Embeddings from Voyage** (voyage-4 series). Rejected: OpenAI
   text-embedding-3-large, which had the best Czech scores in
   [[feasibility-research]] but costs money and a second provider, and local
   bge-m3, which needs about 3–4 GB of disk (8.3 GB free on this M2 with 8 GB RAM)
   and keeps a 2 GB model in the web process. Voyage's Czech quality is
   unverified, so it is measured on the evaluation set before being relied on.
3. **Claude summaries capped at $5 a month**, starting on Haiku 5.5 and
   compared with Sonnet 5.5 on the evaluation set. The key goes in the private
   `.env`, never in chat. Rejected: $20 a month, and building without a key.

## Voyage facts used (docs read 26 Nov 2026)

- voyage-4-large, voyage-4 and voyage-4-lite share one embedding space, so
  documents and queries may use different models of the series. 32,000-token
  context, 1024 dimensions by default (2048/512/256 available).
- The first 200 M tokens per model are free for every account, also after a
  payment method is added, but not through the Batch API. Then $0.12 / $0.06 /
  $0.02 per million tokens (large / standard / lite).
- With a payment method (tier 1): 3 M tokens and 2,000 requests a minute for
  voyage-4-large, 8 M for voyage-4. Limits without one are not published.
- At most 1,000 texts and 120 K tokens (large) or 320 K (standard) per request.
- voyage-context-4 embeds chunks with their document's context ($0.12, also
  200 M free); a candidate to compare later.

The archive is about 20 M words, roughly 40–65 M tokens, so embedding it fits in
the free allowance. The import stops before spending past it.

## Step 1: keyword fix (done 26 Nov)

`queries/search.py`:

- **Filler words.** 201 Czech function words (pronouns, prepositions,
  conjunctions, particles, forms of "být"), compared accent-free, are dropped from
  an alternative that asks for anything else. A query of nothing but filler
  ("co je to") is searched as typed. Kept on purpose: "byt" (a flat), "moc"
  (power) and "ano" (the party ANO). Phrases and exclusions are never touched.
- **Partial matches only when complete ones are scarce.** A first version
  always let a query of 3+ words lack one word. "pan předseda vláda" then grew
  from 3,994 to 21,018 speeches and from 287 ms to 6.4 s, because ranking reads
  every match's search vector (see "Slow broad queries" in [[czech-word-forms]]).
  Complete matches rank first anyway, so relaxing only helps when they are few.
  Now a query is relaxed only when fewer than 100 speeches (`RELAX_BELOW`)
  contain every word. A speech may then lack one word, or a quarter of a long
  query, at most 64 word combinations (`MAX_COMBINATIONS`). Ranking: number of
  query words present, then `ts_rank_cd`.
- The tsquery is now built once per request and sent back as a literal, so
  combinations are not rebuilt per row.
- The search page lists the dropped words and explains a relaxed result; the
  methodology page describes both rules.

Live archive, warm, over HTTP:

| Query | Before | After | ms |
| --- | ---: | ---: | ---: |
| jak se změnily důchody | 489 | 552 | 107 |
| jak se změnil věk odchodu do důchodu pro ženy | — | 266 (60 complete) | 166 |
| kdo kritizoval zdanění výsluh vojáků | — | 15 (2 complete) | 90 |
| pan předseda vláda | 3,994 | 3,994 | 184 |

## Next

2. Meaning search: pgvector, a `speech_chunk` table, an `ingest embed` command
   with Voyage, and hybrid ranking (reciprocal rank fusion) of keyword and
   meaning results, with meaning-only results labelled.
3. Summaries: one AI module for Voyage and Claude with caching, usage records
   and the $5 monthly cap; the summary block (DESIGN.md §7.8) loads after the
   results; uncited sentences are dropped.
