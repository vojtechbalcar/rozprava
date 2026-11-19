# Rozprava

Search and read Czech parliamentary transcripts. The local app uses PostgreSQL
for keyword/phrase search, transcript reading, MP profiles, activity and voting
participation, and sitting archives for the 9th and 10th terms.

```sh
uv sync
uv run python scripts/local_db.py init
uv run python scripts/local_db.py start
uv run alembic upgrade head
uv run uvicorn rozprava.main:app --host 127.0.0.1 --port 8000 --reload
```

Open [the app](http://127.0.0.1:8000/). Initial setup requires Homebrew PostgreSQL
18; see [local environment](docs/dev-environment.md). Database credentials stay
in the ignored `.env`; the cluster and download cache live outside the checkout.

```sh
uv run python -m rozprava.ingest metadata
uv run python -m rozprava.ingest votes
uv run python -m rozprava.ingest backfill
uv run python -m rozprava.ingest status
```

Backfill is resumable and can take hours. Coverage and incomplete statistics are
shown in the app. Subsequent `update` runs refresh metadata/votes and fetch new or
non-final pages. Web requests read the database only. No paid APIs or AI summaries
are used. Quick search finds MPs, bills and sittings. Select “Vytvořit kartu” on a result
or select text in a transcript to export a quotation PNG. Quotation links retain
the stored version, selection and image dimensions.

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run python scripts/build_tokens.py --check
```

The separate static design preview still uses cached PSP excerpts:

```sh
uv run python scripts/render_preview.py
python3 -m http.server 8001 --bind 127.0.0.1 --directory preview/site
```

Design: [DESIGN.md](DESIGN.md). Progress: [implementation plan](docs/functional-app-plan.md).
