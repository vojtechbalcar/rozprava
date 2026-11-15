---
type: decision
updated: 2026-11-12
status: proposed
---

# Stack decision

Related: [[project-choice]], [[design-direction]]

Proposed on 12 November 2026 while writing `CLAUDE.md`; the user hasn't confirmed it yet.

**Chosen:** Python with `uv`, FastAPI, server-rendered Jinja2 + HTMX, Postgres with pgvector, SQLAlchemy 2 + Alembic, plain CSS from `DESIGN.md` tokens, Claude API for summaries.

**Why:** the user wanted to step outside Next.js. The work is mostly data ingest, embeddings and search, where Python's tooling is strongest. The pages are reading pages that should render on the server and be linkable (each speech and MP gets a URL), and HTMX covers the little interactivity they need without a separate frontend app.

**Considered:**
- FastAPI JSON API + SvelteKit or Astro frontend: more to show on the frontend, but two apps to build and deploy. A fallback if HTMX feels limiting.
- Next.js: rejected as too close to Watchlist.
- Django: viable, but FastAPI fits an API-and-search-first app better and is the more common pairing for AI work.

**Open:** embedding model (must handle Czech), interface language, how many parliamentary terms to load, hosting.
