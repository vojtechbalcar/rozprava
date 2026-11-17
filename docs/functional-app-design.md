---
type: design
updated: 2026-11-17
status: approved
---

# First functional version

Related: [[stack-decision]], [[design-preview]], [[feasibility-research]], [[dev-environment]]

## Confirmed direction

The user approved the museum collection design and asked to make the application
functional. They selected both parliamentary terms beginning in 2021 (9th and
10th), database-backed search before AI, and local operation on this Mac with
PostgreSQL installed here. Keep the existing Czech interface and DESIGN.md styling.

The user approved this design on 17 November 2026. Implementation is tracked in
[[functional-app-plan]].

## Approach

Use the existing FastAPI/Jinja application structure, SQLAlchemy 2 and Alembic,
and PostgreSQL's indexed full-text search. Normal GET forms and links work without
JavaScript; small enhancements preserve the existing interactive controls.

Search options considered:

- **PostgreSQL full-text search with accent normalization — recommended.** Fits
  the selected local database, supports ranked keywords and quoted phrases, and
  keeps ingestion and search in one system. It will not understand synonyms or
  automatically match all Czech grammatical forms.
- Czech morphological dictionaries or a separate lemmatization step improve
  recall, but need retrieval evaluation and dictionary maintenance. Defer this
  until the basic search has real usage and an evaluation set.
- A separate search engine adds another local service and an index to synchronize.
  Defer until measured PostgreSQL performance or search quality warrants it.

AI summaries, embeddings, pgvector and paid API calls are deferred. Remove their
promises from the working application's copy and hide the summary panel. Keep
their design examples available in the component preview.

## What works in this version

| Area | Behavior |
| --- | --- |
| Home | Latest imported sitting day, real archive counts, a reproducibly selected source quotation, visible coverage and last successful import time. |
| Search | Keywords and quoted phrases; filters for term, speaker, historical parliamentary club, agenda/bill and dates; relevance or newest order; real pagination and result totals. |
| MP directory | Both terms, term selector, name/club/region filtering and sorting; each person opens their own profile. |
| MP profile | Term-specific mandate and club information, paginated speeches, activity calendar/table, supported voting participation figures, and agenda links. |
| Sittings | Term-specific sitting and day lists; each link opens the correct transcript. Days awaiting import have an explicit pending state. |
| Reader | Stored transcript text, speaker attribution, original source links, page/day navigation, paragraph links and publication status. |
| Quote composer | Select a contiguous passage from an imported transcript revision; retain the existing PNG sizes and theme controls; copy a reproducible citation link. |
| Quick search | Query stored MPs, bills and sittings, with term-qualified labels and a link to full speech search. |
| Methodology | Explain the actual search, coverage, source revisions, activity and voting formulas. |

Search defaults to both selected terms; directory and sitting views default to
the current term with an explicit selector. All result-affecting filters live in
the URL and survive reload, sharing, pagination and browser back/forward.

Club filtering uses membership on the date of the speech. Label it
“Poslanecký klub” so it is not confused with electoral party membership.
Unknown membership is distinct from a verified independent MP.

## Application and data boundaries

- `settings` and `db` own local configuration, database connections and sessions.
- `models` and Alembic migrations own schema and indexes.
- `ingest` owns downloading, cache validation, parsing, reconciliation and import
  checkpoints. Pure parsers accept bytes/text and do not use the network.
- Query modules own search, directory, profile, transcript and coverage queries.
  They return explicit view data for the existing templates.
- `main` and route handlers validate URL parameters and render pages/fragments.
  JavaScript enhances those pages without maintaining a second search index.

Only the ingest process contacts psp.cz. Web requests read PostgreSQL, including
coverage and revision information; they never fetch missing transcript pages on
demand. The static fixture renderer remains a separate design-review tool.

Main stored entities: terms; people; mandates; organizations and dated club
memberships; sittings and days; agenda items and bills; source pages and immutable
page revisions; speech segments, assembled speech revisions and paragraphs;
votes and per-MP vote records; import runs and per-page status/errors.

Use upstream IDs where available. Sitting numbers, bill numbers and shortened
bill-title overrides must include the term in their keys. A person's name is a
display label, not a database key. Store non-MP speakers without inventing mandates.

## Source import and historical accuracy

Import the official people, sitting, agenda, bill, transcript-index and voting
metadata for 2021 and 2025. Download live transcript HTML because archive ZIPs
have inconsistent availability and anchors; decode the source's encoding.

Use a single crawler with at least one second between request starts, bounded
timeouts, retries with backoff, and robots.txt handling. Identify it as Rozprava
with the repository URL. Cache original bytes with a content hash, URL, retrieval
time and publication status. Keep the cache and database outside iCloud.

Persist progress per source page. Repeating an import is idempotent; interruption
can resume without duplicating speeches or re-downloading unchanged cached work.
One failing page does not discard the rest of the import. Reprocess affected
speech boundaries when adjacent pages or revised metadata arrive.

HTML speaker IDs and labels must agree before attribution. Accept a `rec` match
only when it agrees with the page label; otherwise resolve a unique person from
available source evidence. Keep ambiguous speakers unresolved and report them.
Keep paragraphs in their original order and preserve transcript wording; remove
markup/navigation and decode entities without correcting the speech's language.

Join a speech across consecutive pages only when the continuation is supported.
Never stitch across a missing page or a sitting boundary. Retain unattached
fragments with an explicit incomplete-context state. Missing agenda information
remains unknown. Unknown gender uses neutral interface language.

Store each changed source revision without overwriting old quotation text.
Search uses the latest successfully parsed version. Citations and quote cards
pin the relevant stored speech/page revision; if the source changes, their text
stays reproducible. Catalog URLs such as `/projev/10-034-0644-2` resolve the
current source position; a revision parameter pins an exact historical version.
Do not assume that an anchor still denotes the same speech after source edits.

## Search contract

Maintain a GIN-indexed search vector with a custom `simple` + `unaccent`
configuration. Apply the same configuration to queries. Use parameterized
`websearch_to_tsquery` for ordinary words, quoted phrases, OR and exclusions;
explain these capabilities in Czech. Search normalization never changes the
stored quotation text. No semantic-search or Czech-stemming claims.

Rank speech text by PostgreSQL relevance, with date and stable ID tie-breakers.
Newest order uses date and stable ID. An empty query browses the selected corpus
by date. Include chair contributions in search and label their role; do not
silently assume that every contribution by a chair is procedural.

Return 20 results per page. Facet counts and the date histogram use the complete
filtered match set, not just the visible page. Selected filters remain removable
at zero results. Use escaped text and safe highlight spans for snippets; never
render source HTML or raw headline output as trusted markup.

Validate dates, enums, IDs and bounded query/page sizes. Invalid filters show a
clear Czech explanation. Out-of-range pages offer navigation to valid results.
Unknown entities return 404; an unavailable database returns a useful 503 state.
Neither case falls back to fixture data.

## Activity and voting figures

Display imported speech counts and word counts with their coverage. Count
continuous speeches once, even if they cross pages. Separate known chair roles
from substantive-speech activity totals; document that unknown roles remain
included. Compute activity quartiles across positive MP-day word counts within
the selected term, on a common scale, excluding known chair contributions.
While transcript coverage is incomplete, label the scale and totals provisional.

Voting participation means registration at eligible recorded votes, not physical
presence in the building. Registered codes are A/B/N/C/F/K; @ and M are absence;
W is before oath and excluded from the eligible denominator. Exclude invalidated
votes, manual votes and votes with incomplete technical data from the metric.
Apply the person's mandate dates. A missing per-MP vote record is unknown, never
an assumed absence. Suppress aggregate percentages if the required vote records
are incomplete, and show the reason and known record counts.

A day with any registered vote is “recorded at voting”; an entirely known day
with none is “not registered”. A day without usable voting evidence is unknown.
Speaking activity and voting evidence remain separate. Medians use comparable
members of the selected term and exclude unknown values. Explain the exact
included-vote and cohort rules on the methodology page.

## Local operation and import completion

Install Homebrew PostgreSQL 18 and use a dedicated Rozprava cluster outside
iCloud, on loopback port 55432. Use a dedicated database and local application
role, private local credentials/configuration, and no external listener. Keep
`.env`, data files and caches out of Git. Provide `.env.example`, migrations and
repeatable start, stop, ingest, status and backup instructions. Do not change
unrelated database services or register an unattended scheduled job in this phase.

First validate an end-to-end import with real consecutive pages from each term,
including a cross-page speech, then run the full resumable backfill. The cached
index inspected on 17 November contains 13,926 pages for term 9 and 4,574 for term
10; it must be refreshed before the final import. At one request per second,
18,500 requests have a lower bound of roughly 5.1 hours, before latency/retries.

The app is usable during import. Show imported/expected pages per term and
pending/failed/unavailable counts; never describe a partial corpus as complete.
Unknown transcript days are distinct from zero-speech days. Full backfill is
finished only when all indexed pages are imported or explicitly classified as
unavailable with a reason, and retryable failures are resolved or reported.
The final handoff records exact coverage and any still-running job.

An explicit update command refreshes metadata, downloads new pages and revisits
non-final revisions. A separate full refresh can revisit final pages for later
corrections. Display the last successful update time without claiming nightly
automation before such automation exists.

## Verification and delivery order

1. Establish the local database, migrations, configuration and lifecycle commands.
2. Implement and test metadata/transcript import, revision retention and coverage.
3. Connect search and the reader; start the full backfill once the parser passes
   representative checks from both terms.
4. Connect home, directories, profiles, sittings, quick search and quote export;
   update working-app copy and methodology.
5. Verify end to end, inspect backfill results, document operation, commit and push
   coherent verified changes according to the repository workflow.

Use captured source fixtures for parsing edge cases and a separate PostgreSQL
test database for migrations, idempotency, revisions, historical memberships,
search and pagination. Test accent-free/quoted queries, injection-like input,
unknown attendance, missing pages, cross-term bill collisions and retained
citations after a source revision. Tests must not depend on live psp.cz.

Run the existing lint, format, type and unit checks. Exercise both terms through
the native browser: home → search → actual result → correct speaker → another
sitting/day → quote export. Verify URL state, back/forward, empty/error states,
keyboard controls, a mobile layout and exported PNGs. Measure representative
queries against the loaded database before claiming search performance.

## References

- [Official transcript metadata](https://www.psp.cz/sqw/hp.sqw?k=1310): page,
  speech, role and missing-agenda semantics.
- [Official voting metadata](https://www.psp.cz/sqw/hp.sqw?k=1302): participation
  codes, manual/technical votes and invalidations.
- [PostgreSQL text-search controls](https://www.postgresql.org/docs/current/textsearch-controls.html)
  and [unaccent](https://www.postgresql.org/docs/current/unaccent.html): query
  parsing and accent normalization.
- [Homebrew PostgreSQL 18](https://formulae.brew.sh/formula/postgresql@18): local
  installation and binary availability.
