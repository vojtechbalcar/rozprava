---
type: verification
updated: 2026-11-19
status: current
---

# Local application verification

Related: [[functional-app-plan]], [[dev-environment]], [[transcript-import]],
[[archive-views]], [[quotation-export]]

The approved database-backed phase runs locally on `feature/functional-local-app`.
Search, home, MP directory/profiles, sitting archives, transcript reading, quick
navigation and quotation export use stored data from both terms. No paid APIs,
embeddings or AI summaries are enabled.

## Checks

- 181 tests pass, including isolated PostgreSQL migration/import/query/route
  checks. Tests use `rozprava_test`; the real archive is not reset.
- Ruff lint and formatting, Pyright, design token freshness and syntax checks
  for all three JavaScript files pass. The static design preview renders.
- Browser interactions pass for term/club/date filters, sorting and pagination,
  Back/Forward history, MP filtering/profile links in both terms, sitting/day
  links, reader pagination, mobile layouts and the mobile filter drawer.
- Quick search preserves term identity, keyboard focus and response order;
  request failures retain an ordinary speech-search link. Quote links restore
  immutable text selections; all three PNG sizes export with Czech characters.
  Font and validation failures produce visible errors. See [[quotation-export]].
- The live unresolved-page state and invalid deep links were checked. Existing
  database-outage tests assert 503 responses without sample content.
- T3's preview initially supported DOM interaction but screenshots failed; later
  `preview_open` explicitly reported no automation host. Final browser checks
  used an isolated Playwright invocation and the already installed Chromium.

Final review found and fixed cached parse failures being replayed indefinitely
on retry, and oversized numeric links reaching PostgreSQL integer casts. Search
also rejects non-ASCII numeric filters and excessive integer lengths without
crashing. Regression tests cover these cases.

## Corpus and timings

Fresh metadata at 08:24 CET confirmed 18,500 expected pages. Imported counts are
13,922/13,926 for term 9 and 4,574/4,574 for term 10, with 93,738 current speeches
and no pending assembly. Four term-9 sitting-901 pages still return empty
responses and remain retryable failures. This is not a claim of complete term-9
coverage. Votes were last imported on 18 November.

Measured locally against this corpus, three sequential calls per operation,
including SQLAlchemy query execution and view-data construction. These are not
network timings or a concurrent-load benchmark. First-call overhead reached
308 ms; the table gives medians.

| Operation | Median |
| --- | ---: |
| Search `penze`, both terms | 48 ms |
| Phrase `"duchodova reforma"`, both terms | 39 ms |
| `penze`, term 9, ANO | 39 ms |
| Browse newest speeches | 149 ms |
| Quick-search MP name | 6 ms |
| Quick-search bill number | 3 ms |
| Transcript page with day navigation | 208 ms |
| Term-9 sitting archive | 84 ms |

## Operation and limits

The app remains available at `http://127.0.0.1:8000/`. Setup, start, stop, manual
update and backup commands are in the README and [[dev-environment]]. Backfill
can resume safely; source revisions remain addressable after corrections.
A private 168.4 MiB custom-format database backup was created on 19 November at
08:27 CET. `pg_restore --list` successfully read its 163 archive entries; no
restore into the working database was performed.

Search matched whole words and phrases with accent folding, without stemming
or semantic expansion. Since 19 November, unquoted words also match their other
forms; see [[czech-word-forms]]. Unknown speakers, roles, clubs and participation remain
explicitly unknown. Counts can change after source corrections or additional
imports. Hosting, AI features and automatic scheduling remain future work.
