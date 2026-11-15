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

The project isn't scaffolded yet. These are the intended commands; update this
section when they exist.

- Dev: `uv run fastapi dev src/rozprava/main.py`
- Test: `uv run pytest`
- Lint: `uv run ruff check .`
- Typecheck: `uv run pyright`
- Migrate: `uv run alembic upgrade head`
- Ingest: `uv run python -m rozprava.ingest`

## Hard rules

- **Quotes are verbatim.** Text in quotation marks or in the quote serif is
  exactly what was said in the transcript. Shorten only with "…", never reword.
- **No uncited claims.** Every sentence in an AI summary cites at least one
  stored speech. A summary sentence that can't be cited is dropped. If nothing
  relevant is found, say so; don't fall back to the model's own knowledge.
- **AI text never looks like a quote.** Summaries are in the sans in the answer
  panel; quotes are in the serif in quote cards. See `DESIGN.md`.
- **Non-partisan.** Parties never get colours. Petrol is the brand only and never
  marks a party, side or sentiment. Rank and sort by neutral measures (date,
  relevance), never by "who's right".
- **Data flow.** Only the ingest job fetches from psp.cz. Web requests read
  Postgres only. All LLM and embedding calls go through one module with
  caching and a spending limit.
- **Design.** Follow `DESIGN.md` for every UI change: the archive palette
  (grey-green paper, green-black ink, petrol accent), Newsreader
  serif for display and quotes, Inter for interface text, Czech typography („ “
  quotes, non-breaking spaces after one-letter prepositions).
- Never use Anthropic's logo, fonts, colours or page copy. Only the layout and
  typographic structure are inspired by anthropic.com.

## Open decisions

- Interface language: Czech, English, or both.
- Embedding model: hosted multilingual model vs. a local one (e.g. bge-m3).
- How far back to load: current term only, or every term with digital
  transcripts.
- Hosting.

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
