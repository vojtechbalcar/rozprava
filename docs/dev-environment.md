---
type: problem
updated: 2026-11-19
status: current
---

# Dev environment: iCloud hides the venv

Related: [[stack-decision]], [[design-preview]]

**Symptom.** After `uv sync`, `import rozprava` failed with `ModuleNotFoundError`, even though the editable install's `rozprava.pth` was in site-packages and pointed at `src/`.

**Cause.** The repo lives on the Desktop, which syncs to iCloud Drive. iCloud sets the macOS `hidden` flag on dot-files and dot-folders and on everything inside them, including `.venv`. Python 3.14 skips `.pth` files that carry the hidden flag, so the editable install was ignored.

**Tried first.** `chflags nohidden` on the `.pth` file worked, but iCloud set the flag again within minutes.

**Fix.** The virtualenv lives outside iCloud at `~/.local/share/venvs/rozprava`, and `.venv` in the repo is a symlink to it. `uv` follows the symlink. To recreate it:

```sh
rm -rf .venv
UV_PROJECT_ENVIRONMENT="$HOME/.local/share/venvs/rozprava" uv sync
ln -s "$HOME/.local/share/venvs/rozprava" .venv
```

Also on this machine: `uv` came from Homebrew (`brew install uv`) on 17 Nov 2026.

## Functional application checkout and PostgreSQL

The functional build is on `feature/functional-local-app`. It started on 17 Nov in a
worktree at `~/.local/share/rozprava-worktrees/functional-app`, which no longer
exists; since 18 Nov it continues in `~/Users/vojtechbalcar/WebstormProjects/rozprava`.
That folder isn't iCloud-synced, but it still uses the venv symlink above.

PostgreSQL 18 is installed through Homebrew. Rozprava uses its own cluster at
`~/.local/share/rozprava/postgres` and loopback port 55432; it does not use the
Homebrew default cluster or a login service. Local configuration and generated
credentials are private and ignored by Git.

```sh
uv run python scripts/local_db.py init
uv run python scripts/local_db.py status
uv run python scripts/local_db.py start
uv run python scripts/local_db.py stop
uv run python scripts/local_db.py backup
```

Repeated initialization retains credentials and data. Backups go to the private
`~/.local/share/rozprava/backups` directory. `test-db` creates the dedicated
`rozprava_test` database; integration tests refuse to reset a database whose name
does not end in `_test`.

The local app is implemented; see [[local-app-verification]] and
[[functional-app-plan]]. Start the database first, then run:

```sh
uv run uvicorn rozprava.main:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000/`. Stop the server with Ctrl-C before stopping the
database. No launch agent or background update scheduler is installed. Run
`uv run python -m rozprava.ingest update` manually for fresh metadata/votes and
new or non-final transcript pages. Run `backfill` to resume or retry failures,
and `refresh --term 9|10` to check final pages for later corrections (choose one
term number). All source fetching happens in these commands, never web requests.

Runtime directories under `~/.local/share/rozprava/`: `postgres/` holds the
cluster, `cache/http/` holds downloaded response bodies and metadata, `log/`
holds ingestion logs, and `backups/` holds private PostgreSQL custom-format
dumps. The download cache is not a database backup. Keep the ignored `.env` and
local credentials private; neither is needed in Git.
