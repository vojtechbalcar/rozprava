# Rozprava

Search what Czech MPs actually said in parliament. Search by meaning across the
Chamber of Deputies' transcripts, filter by MP, party and date, and get short
summaries where every claim links back to the speech it came from.

"Rozprava" is a working name.

## Stack

- Python 3.12+, managed with `uv`
- FastAPI, server-rendered Jinja2 templates, HTMX for interactive parts
  (search-as-you-type, filters, loading more results)
- Postgres with `pgvector`, SQLAlchemy 2 + Alembic
- Plain CSS with custom properties generated from `DESIGN.md` tokens; no CSS
  framework
- Claude API for summaries; embedding model still to be chosen (it must handle
  Czech well)

Why this stack: see [[stack-decision]] in `docs/`.

## Commands

- Test: `uv run pytest`
- Lint: `uv run ruff check .` (and `uv run ruff format .`)
- Typecheck: `uv run pyright`
- Design preview: `uv run python scripts/render_preview.py`, then open
  `preview/site/index.html`. It renders the real templates with
  `preview/data.json` (real psp.cz excerpts).
- Design tokens: `uv run python scripts/build_tokens.py` after editing the
  `DESIGN.md` specification tables or §14.1 CSS block; a test fails if `tokens.css` is stale.
- Fonts: `uv run python scripts/fetch_fonts.py`

Intended, not built yet; update when they exist:

- Dev: `uv run fastapi dev src/rozprava/main.py`
- Migrate: `uv run alembic upgrade head`
- Ingest: `uv run python -m rozprava.ingest`

The project lives on an iCloud-synced Desktop. iCloud marks dot-folders hidden,
and Python 3.14 skips hidden `.pth` files, which breaks the editable install. So
`.venv` is a symlink to `~/.local/share/venvs/rozprava`. See [[dev-environment]].

## Hard rules

- **Quotes are verbatim.** Text in quotation marks or in the quote serif is
  exactly what was said in the transcript. Shorten only with "…", never reword.
- **No uncited claims.** Every sentence in an AI summary cites at least one
  stored speech. A summary sentence that can't be cited is dropped. If nothing
  relevant is found, say so; don't fall back to the model's own knowledge.
- **AI text never looks like a quote.** Summaries are in the sans in the answer
  panel; quotes are in the serif in quote cards. See `DESIGN.md`.
- **Non-partisan.** Follow DESIGN.md §3.4: verified party colours appear only as
  equally weighted OKLCH swatches and transcript rails. Until verified, use the
  same neutral swatch for every party. Rank by date/relevance, never by judgment.
- **Data flow.** Only the ingest job fetches from psp.cz. Web requests read
  Postgres only. All LLM and embedding calls go through one module with
  caching and a spending limit.
- **Design.** Follow the replacement `DESIGN.md` (17 November 2026): museum
  collection, archival paper and ink, square shapes, yellow matches, Cooper Hewitt
  UI / Source Serif 4 quotes / IBM Plex Mono provenance, SVG dot-matrix numbers.
  It supersedes the former teal/Newsreader direction. Preserve Czech typography.
- Never use Anthropic's logo, fonts, colours or page copy. Only the layout and
  typographic structure are inspired by anthropic.com.

## Open decisions

Confirmed by the user on 17 November 2026:

- Load the current and previous terms, beginning in 2021 (9th and 10th terms).
- Build database-backed search first; add AI afterward. No paid APIs, embeddings
  or generated summaries in the first functional version.
- Run locally on this Mac, with PostgreSQL set up here.

Keep the existing Czech interface. The detailed implementation proposal is in
[[functional-app-design]] and is awaiting review. The stack above describes the
longer-term direction; pgvector and the Claude API are deferred for this phase.
Embedding model, AI provider and eventual public hosting remain open.

## Memory

Your memory files live in `docs/`, which is an Obsidian vault. Write them as
proper Obsidian notes: link related notes with [[wikilinks]], kebab-case
filenames. Index each note in `docs/MEMORY.md`.

Save a memory when:
- I correct you
- We make an architectural or product decision (include what we rejected)
- Something takes more than 30 minutes to solve (symptom, cause, fix, and what
  I tried first that didn't work)

When I say "checkpoint", save the current state: what works, what's broken,
what's next.

## Git workflow

- Commit after each completed, verified, coherent change; do not leave finished
  work uncommitted until the end of a session.
- Use focused commits and descriptive messages. Check the diff and run checks
  appropriate to the change before committing.
- Update the Obsidian notes when the memory rules above apply, and commit those
  updates too.
- Preserve unrelated user changes; stage only the files belonging to the change
  being committed.
- Once a GitHub remote exists, push each completed, verified commit on the
  current branch after committing; set the upstream when needed and verify the
  push succeeded. Never force-push without explicit authorization.
