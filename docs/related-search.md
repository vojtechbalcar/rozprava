---
type: decision
updated: 2026-11-26
status: built, awaiting API keys
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

## Step 2: meaning search (built 26 Nov, waiting for the Voyage key)

- **Setup.** pgvector 0.8.7 in the `extensions` schema; see [[dev-environment]].
  Migration 0005: `speech_chunk` (halfvec(1024), HNSW cosine index),
  `query_embedding` (cache) and `ai_usage` (every paid request at list price).
  The live database was backed up before migrating
  (`backups/rozprava-20261126T112831899002Z.dump`).
- **One AI module** (`ai.py`): the Voyage client (retries 429/5xx, honours
  `retry-after`), usage records, the token limit and the query cache. Keys come
  from `.env` (`VOYAGE_API_KEY`); without one, nothing changes.
- **Passages** (`ingest/embed.py`). Speeches of 40+ words by a speaker; chair
  remarks are procedural (median 72 words: "Děkuji. S faktickou poznámkou…"), so
  they are skipped. Consecutive paragraphs are packed to about 250 words (at most
  400; a longer paragraph is cut between sentences). Each passage is embedded
  with a header "speaker. agenda short title". Dry run on the archive:
  38,021 speeches, 77,327 passages (median 269 words), at most 59 M tokens by a
  deliberately high estimate (characters / 2), inside the 190 M limit.
  A passage with the same text and model reuses its vector; retired revisions'
  passages are deleted at the end of a run, after their successors could reuse
  them (deleting them first, as written at first, made reuse impossible).
- **Search** (`queries/search.py`). Only plain queries (no quotes, OR or minus)
  use meaning. The 400 nearest passages under the same filters (HNSW with
  pgvector's iterative scan) are grouped by speech; up to 100 speeches within
  cosine distance 0.6 are kept. Those without the query's words join the match
  set, so counts and facets include them; they are labelled "Podobný význam".
  Relevance order: reciprocal rank fusion (k = 60) of the top 200 keyword results
  and the meaning results, then the keyword ranking. If Voyage fails, the page
  says so and shows keyword results.
- **Not yet calibrated.** `MAX_DISTANCE` and the fusion weights are guesses until
  real vectors exist; check them with the evaluation set.

To run, once the key is in `.env`:

```sh
caffeinate -i uv run python -m rozprava.ingest embed --limit 200   # first, check
caffeinate -i uv run python -m rozprava.ingest embed               # the rest
uv run python -m rozprava.ingest status    # speeches embedded, tokens used
```

## Step 3: cited summaries (built 26 Nov, waiting for the Anthropic key)

- **Model and price.** `claude-haiku-5-5` ($0.10 / $0.50 per million input /
  output tokens up to 100K-token prompts; Sonnet 5.5 is $2 / $10), adaptive
  thinking (on by default) at effort `medium`. Citations on custom-content
  documents: one document per result, one content block per paragraph, so
  Claude cites by block index (0-based, end exclusive). `cited_text` is not
  billed. Citations cannot be combined with structured outputs. Facts from the
  claude-api skill and the live citations page, 26 Nov 2026.
- **Sources** (`queries/summary.py`). The first 8 results of page one by
  relevance (so `[n]` matches the page). A speech under 600 words is sent whole;
  of a longer one, the paragraph its result shows and up to 3 others with the
  query's words. Title "[n] name (party), date"; agenda and sitting go in the
  document `context`, which Claude cannot cite.
- **Hard rules in code, not just the prompt.** The answer's text blocks are
  joined and split into sentences (not after "55.", "12. 3." or abbreviations
  such as "Sb.", "č."); a sentence without a citation is dropped, and so is one
  whose quotation marks hold text that is not verbatim in the paragraphs it
  cites (an ellipsis may shorten). The prompt asks for attribution, neutrality,
  no quotation marks, no outside knowledge, and `NENALEZENO` when nothing is
  relevant, which the page reports as such.
- **Spending.** Before each request, `ai.write_summary` adds this calendar
  month's recorded Claude cost to the worst case (estimated input plus the full
  4,000-token output) and refuses past `ROZPRAVA_AI_MONTHLY_LIMIT_USD` ($5).
  Usage is committed even for a refusal. About $0.002–0.005 per summary, so
  roughly 1,000–2,500 new summaries a month; repeats come from the `summary`
  table (migration 0006), keyed by model, prompt version, query, revisions and
  paragraphs. No prompt caching: the system prompt is below the minimum
  cacheable size and the documents differ per query.
- **Page.** The results render at once; a loading block (dot-matrix shimmer,
  DESIGN.md §7.8) fetches `/api/shrnuti` with the same parameters and is
  replaced by the summary, a note (nothing relevant, limit reached, Claude
  unavailable) or nothing. Citation chips reuse the §7.7 popovers.
- **Not yet measured.** Quality on real searches, Haiku 5.5 against Sonnet 5.5
  on the evaluation set, and the actual cost per summary.

## Next

1. Add `VOYAGE_API_KEY` and `ANTHROPIC_API_KEY` to `.env`, then run `ingest embed`
   and restart the server.
2. Calibrate `MAX_DISTANCE`, fusion and the summary prompt on the evaluation set
   (branch `feature/ai-evaluation-set`), and compare Haiku 5.5 with Sonnet 5.5.
3. Automatic daily updates (owned by the other session, see [[czech-word-forms]]).
