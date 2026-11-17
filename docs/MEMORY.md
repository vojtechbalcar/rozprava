# Rozprava memory

## Decisions

- [[project-choice]] — why this project was picked as the next one after Watchlist, and what was rejected.
- [[design-direction]] — anthropic.com's layout and type with our own archive palette (petrol accent), the correction that dropped Anthropic's colours, and no party colours.
- [[stack-decision]] — FastAPI + Jinja2 + HTMX + Postgres/pgvector, and the alternatives considered.
- [[design-preview]] — static preview of all screens from the real templates and real psp.cz excerpts; layout and typesetting decisions made while building it.

## Research

- [[feasibility-research]] — psp.cz transcripts are scrapable with stable speaker IDs; verdict: build with a reduced scope (2021– first), plus competitors, legal, embedding and hosting findings.

## Problems solved

- [[dev-environment]] — iCloud hides `.venv`, Python 3.14 skips hidden `.pth` files; the venv now lives outside iCloud behind a symlink.
