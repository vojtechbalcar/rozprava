# Functional application implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Track completed steps below. User approved [[functional-app-design]] on 17 November 2026; no further design approval is needed.

**Goal:** Run the designed Czech parliamentary archive locally against PostgreSQL with real data from both terms beginning in 2021.

**Architecture:** An offline importer stores source metadata, immutable transcript revisions and searchable speeches. FastAPI renders existing Jinja components from database query results; normal GET navigation is the baseline. PostgreSQL stores ingestion coverage and powers accent-insensitive keyword/phrase search.

**Tech stack:** Python/uv, FastAPI/Jinja, SQLAlchemy 2, Alembic, psycopg 3, PostgreSQL 18, plain CSS/JavaScript.

Related: [[functional-app-design]], [[dev-environment]], [[feasibility-research]]

## Boundaries and files

- `scripts/local_db.py`: dedicated local cluster initialization/start/stop/status, database creation and backup; secrets are generated locally and never printed.
- `src/rozprava/settings.py`, `db.py`: configuration and database connections.
- `src/rozprava/models.py`, `alembic/`: schema, migrations, search configuration/indexes.
- `src/rozprava/ingest/{__main__,fetch,metadata,parser,store,runner}.py`: CLI, polite cached downloads, UNL parsing, pure transcript parsing, revision/identity reconciliation and resumable orchestration.
- `src/rozprava/queries/{search,archive,people,transcripts}.py`: database reads and explicit template view data.
- `src/rozprava/main.py`, `web.py`: FastAPI routes, validated query parameters, URL generation, common template context and errors.
- `src/rozprava/templates/`: adapt current pages and add shared pagination, coverage and error components without changing the design vocabulary.
- `src/rozprava/static/js/`: retain theme, dialogs and PNG composer; remove fixture-only filtering from live pages and load palette results from the server.
- `tests/fixtures/`, `tests/test_ingest_*.py`, `tests/test_database.py`, `tests/test_search.py`, `tests/test_web.py`: offline source fixtures and isolated database checks.

## 1. Workspace, dependencies and local database

- [x] Create `feature/functional-local-app` in a worktree outside iCloud using T3's worktree handoff; preserve the existing preview checkout. Run `uv sync` and `uv run pytest` there; baseline is 32 passing tests. *(Done 17 Nov in `~/.local/share/rozprava-worktrees/functional-app`; from 18 Nov work continues on the same branch in `~/Users/vojtechbalcar/WebstormProjects/rozprava`, which is not iCloud-synced.)*
- [x] Add `sqlalchemy>=2.0,<2.1`, `alembic>=1.14`, `psycopg[binary]>=3.2`, `httpx>=0.28`, `beautifulsoup4>=4.12` and `pydantic-settings>=2` through uv. Use the standard library for CLI and archive extraction.
- [x] Add ignored `.env` and `.env.example` with `DATABASE_URL`, `ROZPRAVA_DATA_DIR`, `ROZPRAVA_CACHE_DIR`. Defaults live under `~/.local/share/rozprava`, not Desktop. No credentials in tracked files.
- [x] Write configuration tests before implementing settings; reject non-PostgreSQL URLs and keep configuration import free of network/process side effects.

```python
def test_configuration_is_postgresql_only():
    with pytest.raises(ValueError):
        Settings(database_url="sqlite:///example.db")
```

- [x] Install Homebrew PostgreSQL 18. Implement `uv run python scripts/local_db.py init|start|stop|status|backup`. Initialize a dedicated UTF-8 cluster with peer/local administration and SCRAM host authentication, listen on `127.0.0.1:55432`, create a non-superuser app role, and write generated credentials to a private `.env` without printing them. Repeated init preserves existing data and credentials.
- [x] Verify start, readiness, stop/start persistence and application connection. Create a separate test database; it must be identified explicitly before any test cleanup. Commit and push the verified foundation.

## 2. Schema and database tests

- [x] Define SQLAlchemy tables with upstream/composite keys: term, person, mandate, organization, membership, sitting/day, bill/agenda, source page, page revision, speech revision/paragraphs, vote/per-person vote, import run. Allow unknown speaker, agenda, club and vote states.
- [x] Store current source-page revision separately from immutable revision content. An assembled speech revision records its constituent source revisions and original paragraph positions. Retired versions remain addressable for citations.
- [x] Add Alembic configuration and initial migration. Create `unaccent`, a `simple`-based search configuration with `unaccent,simple` mappings, and a GIN search-vector index. Keep migration operations explicit and repeatable.
- [x] Add an integration fixture that only resets a dedicated `_test` database. Test migration from empty, duplicate source keys, cross-term bill keys and normalized search.

```python
def test_search_dictionary_preserves_phrase_positions(db):
    row = db.execute(
        text("""
        SELECT to_tsvector('rozprava', 'důchodová reforma')
          @@ websearch_to_tsquery('rozprava', '"duchodova reforma"')
    """)
    ).scalar_one()
    assert row is True
```

- [x] Run `uv run alembic upgrade head`, database tests and lint/type checks. Commit and push the schema.

## 3. Source parsing and identity

- [x] Capture small representative HTML/UNL fixtures from existing cached sources in both terms, preserving provenance in a fixture README. Include stale `rec` attribution, a headerless continuation and unknown agenda. Tests never fetch live sources. *(18 Nov: the research cache was gone, so pages were fetched again through `ingest/fetch.py`; see `tests/fixtures/psp/README.md`.)*
- [x] Write tests for Windows-1250 decoding, paragraph preservation, role recognition, actual person links, publication status, empty/private pages and cross-page gaps before implementing `ingest/parser.py`.

```python
def test_missing_page_breaks_speech_continuation():
    pages = [
        page(1, speaker="Jan Novák", text="První část."),
        page(3, speaker=None, text="Neznámý začátek."),
    ]
    speeches = assemble(pages)
    assert speeches[0].text == "První část."
    assert speeches[1].speaker_id is None
    assert speeches[1].incomplete is True
```

- [x] Implement pure parser dataclasses and UNL helpers. Match names with whole normalized name boundaries and unique source evidence; never choose the first ambiguous person. Check HTML IDs/labels before accepting metadata IDs.
- [x] Add dated membership lookup tests around a club change; keep unknown distinct from independent. Change `titles.short_title` overrides to term-qualified keys and update preview callers/tests.
- [x] Run parser/title tests, review against real fixture paragraphs, lint and typecheck. Commit and push.

## 4. Metadata and resumable transcript ingestion

- [x] Implement `fetch.py` with allowlisted PSP source URLs, robots checks, at least one second between request starts, bounded timeout/retry/backoff, cache files written atomically and SHA-256 provenance. Validate ZIP paths rather than using unrestricted extraction. Do not classify transient errors as permanent unavailability.
- [x] Import people/organizations/mandates/dated memberships, sittings/agendas/bills, transcript pages and speech metadata from official dumps for organizations 173 and 174. Retain metadata-only pages as pending; record dump retrieval times separately from transcript import times.
- [x] Implement per-page persistence and an import lock. Atomically publish a parsed revision; source failure leaves the last good revision readable. Rebuild affected speech boundaries when neighboring pages arrive.
- [x] Implement `uv run python -m rozprava.ingest metadata`, `backfill --term 9|10 --limit N`, `update`, `refresh`, `status` and explicit retry controls. Default backfill covers both terms, can resume, reports counts/errors and never fetches from web routes.
- [x] Test the same fixture imported twice, changed source revision, interrupted/resumed import and repaired missing page.

```python
def test_unchanged_reimport_does_not_duplicate(db, source_page):
    first = ingest_page(db, source_page)
    second = ingest_page(db, source_page)
    assert first.revision_id == second.revision_id
    assert revision_count(db, source_page.id) == 1
```

- [ ] Import consecutive real pages from both terms, verify speaker/source links and quotations, then start the full backfill with a durable log and recorded process ID. Continue application work while the polite crawler runs. Commit and push importer code once checks pass.

## 5. Search and reader routes

- [ ] Add `SearchFilters` with bounded query/page length, ISO dates, term/ID validation and stable sort choices. Build parameterized SQL and 20-item pagination. Search full stored speech text; browse newest for an empty query. Include labeled chair contributions.
- [ ] Test accent-free keywords, quoted phrases, AND/OR/exclusions, all filters, count/facet consistency, deterministic pages and injection-like input against PostgreSQL.
- [ ] Build per-request view data and URL helper. Core routes: `/`, `/hledat`, `/poslanci`, `/poslanec/{id}`, `/schuze`, `/schuze/{term}/{sitting}`, `/prepis/{term}/{sitting}/{page}`, `/projev/{catalog}`, `/karta`, `/jak-to-funguje`, `/api/palette`, `/health`.
- [ ] Preserve revision parameters in result/citation/composer links; normal reader navigation shows page/day neighbors and explicit pending/missing states. Unknown IDs return 404; database outages return 503 and never fixture content.
- [ ] Adapt search and reader templates to real URL-backed GET controls. Escape excerpts before adding highlight spans. Keep safe back links within the app and do not render source HTML.
- [ ] Test route behavior and citations after a revision. Run the app on loopback, check real results from both terms in T3's browser, then commit and push.

## 6. Home, people, sittings and statistics

- [ ] Build common coverage context with expected/imported/pending/failed/unavailable counts per term and last successful import time. Represent no imported data with an empty state, never a fake latest day.
- [ ] Home uses imported data and a deterministic hourly sample of source speeches with at least 60 words. Directory and sessions default to term 10, search to both; every card/link carries real IDs.
- [ ] Build paginated MP profiles, dated club and mandate display, region/club filters, term-specific bill links and counts from assembled speeches. Extend activity rendering to unknown/missing data and two weekend sittings without cell overlap.
- [ ] Import vote and apology metadata for both terms. Test A/B/N/C/F/K registration, @/M absence, W ineligibility, invalidated/manual/technical votes, mandate dates and missing records. Suppress unsupported percentages and exclude unknown values from medians.
- [ ] Compute word-count activity quartiles across positive MP-days in the same term excluding known chair roles. Mark incomplete coverage and provisional aggregates on profile/calendar/table views.
- [ ] Test actual MP distinctions, identical bill numbers across terms, pending days and unknown attendance; check desktop/mobile pages. Commit and push.

## 7. Palette, quotation export and truthful copy

- [ ] Replace live palette fixture indexing with bounded server queries for MPs, term-qualified bills and sittings; preserve focus management and keyboard navigation, cancel stale responses, and include a normal speech-search link.
- [ ] Quote composer loads only a selected stored revision. Validate source ID and passage offsets on the server; preserve contiguous source text with ellipses for cuts and keep share URLs revision-pinned. Retain all three PNG sizes and image/font error handling.
- [ ] Disable fixture-only JS search/filter behavior on live pages. Preserve form filters during navigation and remove semantic-search/AI-summary claims from live home, search and methodology. Explain actual formulas and update cadence.
- [ ] Test invalid quotation offsets, forged source text, source revisions and empty/error responses. Browser-check copy link and PNG exports with Czech characters at all sizes. Commit and push.

## 8. Final verification and operation notes

- [ ] Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run pyright`, token freshness and JavaScript syntax checks. Re-render the static preview to protect design review mode.
- [ ] Review spec compliance and code quality, fix findings, rerun affected checks. Measure representative PostgreSQL query timings against the imported corpus.
- [ ] Exercise browser history, direct deep links, both terms, facets/date controls, directory/profile navigation, another sitting/day, quote exports, keyboard controls, responsive layouts and unavailable-data states.
- [ ] Inspect the full backfill: report exact term coverage and unresolved source failures, do not claim the archive is complete while pending work remains. Reconcile expected pages after a fresh metadata update.
- [ ] Update README, CLAUDE commands and Obsidian notes with actual setup/start/update/stop/backup behavior, data directories and known limitations. Keep credentials and caches ignored. Commit and push verified changes, leaving the working local app available.
