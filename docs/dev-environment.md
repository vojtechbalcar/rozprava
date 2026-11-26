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

The functional build is on `feature/functional-local-app`. It started on 17 Nov in the
worktree `~/.local/share/rozprava-worktrees/functional-app` on this Mac. The 18–19 Nov
implementation and its verified archive were built on another machine (checkout
`~/WebstormProjects/rozprava` there) and pushed; that database never existed here.
On 21 Nov this Mac's worktree was realigned with `origin` and its archive rebuilt
from scratch; see [[parallel-worktree-divergence]] and [[transcript-import]].

On this Mac the dev server and backfill run detached so they outlive a terminal or
agent session. Their PIDs are in `~/.local/share/rozprava/server.pid` and
`backfill.pid`, their output in `~/.local/share/rozprava/log/`. Stop them with
`kill "$(cat ~/.local/share/rozprava/server.pid)"` (likewise `backfill.pid`; the
backfill resumes safely). Start the server detached with:

```sh
nohup uv run uvicorn rozprava.main:app --host 127.0.0.1 --port 8000 \
  > ~/.local/share/rozprava/log/server.out 2>&1 < /dev/null &
echo $! > ~/.local/share/rozprava/server.pid
```

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

## pgvector for meaning search (26 Nov 2026)

`brew install pgvector` (0.8.7, bottled for PostgreSQL 18 and 19; postgres is only a
build dependency) puts the extension in `/opt/homebrew/{lib,share}/postgresql@18`,
which survives PostgreSQL patch upgrades. pgvector is not a *trusted* extension, so
the application role, which is not a superuser, cannot create it, and the test
fixture's `DROP SCHEMA public CASCADE` would drop it from `public`.
`scripts/local_db.py vectors` (also run by `init` and `test-db`) therefore connects as
the cluster administrator and, in both databases, creates the `extensions` schema,
installs `vector` there, grants the app role usage and sets the database search path
to `"$user", public, extensions`. Migration 0005 stops with these instructions when
the extension is missing. On another Mac: install pgvector, run `vectors`, then migrate.

## Czech morphology build and locale (19 Nov 2026)

See [[czech-word-forms]].

**`ufal.morphodita` does not build.** Symptom: `uv add ufal.morphodita` fails with
`fatal error: 'algorithm' file not found`. Cause: the package has wheels only up to
CPython 3.14 and the venv runs 3.15.2, so it compiles from source. This Mac's Command
Line Tools 26.0 have no `usr/include/c++/v1`, and clang does not search the SDK's
copy. Even `#include <algorithm>` fails. Tried first: `SDKROOT=$(xcrun --show-sdk-path)`
and `CXXFLAGS=-isysroot …`; neither helped. Fix: `pyproject.toml` sets
`[tool.uv.extra-build-variables]` so `ufal-morphodita` builds with
`CPLUS_INCLUDE_PATH=/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/c++/v1`.
`uv sync --no-cache` then builds it cleanly. Reinstalling the Command Line Tools
would fix the toolchain itself (needs sudo; not done).

**PostgreSQL will not start without a locale.** Symptom: `pg_ctl` fails, and the
server log says `postmaster became multithreaded during startup` and suggests
setting `LC_ALL`. Seen when a shell had `LANG` empty (C locale); the running
cluster was unaffected because it was started from a normal terminal. Run local
database commands and tests with `LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8`. Launch
agents need the same in their environment.

The tagger model lives in `~/.local/share/rozprava/models/` (26 MB), installed by
`uv run python scripts/fetch_morphology.py`.

**Long jobs and sleep.** On battery the Mac goes into idle sleep while a
terminal job runs, and the job stalls (seen 19 Nov from 13:03 to 14:02 during
word-form tagging). Run long imports as `caffeinate -i uv run python -m
rozprava.ingest …`; that prevents idle sleep only for the command's duration.
