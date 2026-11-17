---
type: decision
updated: 2026-11-17
status: phased
---

# Stack decision

Related: [[project-choice]], [[design-direction]], [[functional-app-design]]

Originally proposed on 12 November 2026 while writing `CLAUDE.md`. The design
preview now uses FastAPI's Python environment, Jinja templates and plain CSS.

**Implementation direction:** Python with `uv`, FastAPI, server-rendered Jinja2
with small interactive enhancements, PostgreSQL, SQLAlchemy 2 + Alembic, and
plain CSS from `DESIGN.md` tokens.

**Confirmed scope on 17 November:** the user chose the 9th and 10th parliamentary
terms (from 2021), database-backed search before AI, and local PostgreSQL on this
Mac. Preserve the existing Czech interface. The detailed proposal in
[[functional-app-design]] was approved on 17 November; [[functional-app-plan]] tracks implementation.

**Deferred:** pgvector, embedding-model selection and generated summaries. The
earlier Claude API proposal is a future option, not a dependency or approved API
spend for this phase.

**Why:** the user wanted to step outside Next.js. The work is mostly data ingest, embeddings and search, where Python's tooling is strongest. The pages are reading pages that should render on the server and be linkable (each speech and MP gets a URL), and HTMX covers the little interactivity they need without a separate frontend app.

**Considered:**
- FastAPI JSON API + SvelteKit or Astro frontend: more to show on the frontend, but two apps to build and deploy. A fallback if HTMX feels limiting.
- Next.js: rejected as too close to Watchlist.
- Django: viable, but FastAPI fits an API-and-search-first app better and is the more common pairing for AI work.

**Open for later:** embedding model and AI provider (must handle Czech), and
public hosting.
