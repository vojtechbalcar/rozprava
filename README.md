# Rozprava

Search and read Czech parliamentary transcripts. The local app uses PostgreSQL
for keyword/phrase search, transcript reading, MP profiles, activity and voting
participation, and sitting archives for the 9th and 10th terms. A word finds its
other forms too ("důchod" also finds "důchodu"); quoted text matches exactly.

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
uv run python scripts/fetch_morphology.py   # Czech tagger model for word forms (once)
uv run python -m rozprava.ingest metadata
uv run python -m rozprava.ingest votes
uv run python -m rozprava.ingest backfill
uv run python -m rozprava.ingest forms      # tag speeches imported without the model
uv run python -m rozprava.ingest status
```

Word forms come from the MorphoDiTa tagger with the MorfFlex CZ 2.1 + PDT-C 2.0
model (ÚFAL MFF UK, CC BY-NC-SA 4.0, non-commercial); the import tags new speeches
automatically once the model is installed. See [word forms](docs/czech-word-forms.md).

Backfill is resumable and can take hours. Coverage and incomplete statistics are
shown in the app. Subsequent `update` runs refresh metadata/votes and fetch new or
non-final pages. Web requests read the database only. No paid APIs or AI summaries
are used. Quick search finds MPs, bills and sittings. Select “Vytvořit kartu” on a result
or select text in a transcript to export a quotation PNG. Quotation links retain
the stored version, selection and image dimensions.

For later refreshes and backups:

```sh
uv run python -m rozprava.ingest update
uv run python -m rozprava.ingest backfill  # also retries failed pages
uv run python scripts/local_db.py backup
```

Stop the dev server with Ctrl-C, then stop PostgreSQL with
`uv run python scripts/local_db.py stop`. Start the database and server again with
the commands above; imported data survives restarts. Updates are manual; there
is no background scheduler. `refresh --term 9` or `refresh --term 10` re-downloads
already imported pages to check later corrections, retaining old versions.

Each machine builds its own archive; the database is not in Git. On the machine
where the app was verified (19 November 2026) the archive held 93,738 speeches and
18,496 of 18,500 expected pages: term 10 complete, four term-9 pages in sitting 901
returning empty responses. A full backfill there took about 23 hours including
retries. See [import status](docs/transcript-import.md) and
[verification notes](docs/local-app-verification.md).

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
