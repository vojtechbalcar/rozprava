# Rozprava memory

## Decisions

- [[project-choice]] — why this project was picked as the next one after Watchlist, and what was rejected.
- [[design-direction]] — the replacement DESIGN.md: museum collection, paper/ink, serif quotations and dot-matrix data; supersedes the earlier teal direction.
- [[stack-decision]] — FastAPI + Jinja2 + HTMX + Postgres/pgvector, and the alternatives considered.
- [[design-preview]] — static preview of all screens from the real templates and real psp.cz excerpts; layout and typesetting decisions made while building it.
- [[functional-app-design]] — approved backend scope: both terms from 2021, database search before AI, local PostgreSQL.
- [[quotation-export]] — live quick search and immutable quotation selections, Unicode offsets, PNG export validation.
- [[archive-views]] — database-backed home, directory/profiles and sittings; voting/activity rules, validation and remaining work.
- [[functional-app-plan]] — implementation tasks, source-accuracy checks and local delivery workflow.
- [[local-app-verification]] — completed local database phase, final browser/check results, corpus timings and operating limits.
- [[czech-word-forms]] — search finds every form of a word via the MorphoDiTa tagger (MorfFlex 2.1, CC BY-NC-SA); stemmer, simplemma and hunspell rejected; next phases and work split.

## Research

- [[feasibility-research]] — psp.cz transcripts are scrapable with stable speaker IDs; verdict: build with a reduced scope (2021– first), plus competitors, legal, embedding and hosting findings.

## Problems solved

- [[dev-environment]] — iCloud hides `.venv`, Python 3.14 skips hidden `.pth` files; the venv now lives outside iCloud behind a symlink. Also the local PostgreSQL 18 cluster, the MorphoDiTa C++ build fix and the locale needed to start PostgreSQL.
- [[transcript-import]] — source-page structure and attribution rules, completed backfill coverage and retry recovery.
