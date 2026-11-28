---
type: decision
updated: 2026-11-28
status: deployed 28 Nov; daily import being verified
---

# Production deployment: Cloudflare and Neon

Related: [[related-search]], [[dev-environment]], [[feasibility-research]],
[[stack-decision]], [[transcript-import]]

## Decisions (user, 28 Nov 2026)

The local app works end to end (keyword, word forms, meaning search, cited
summaries; archive current to 26 Nov). The user decided to move it to a public
production setup with daily updates, hosted on Cloudflare, with the database and
AI keys no longer on the Mac. This supersedes "run locally on this Mac" from
17 Nov.

| Question | Chosen | Rejected |
| --- | --- | --- |
| Database | **Neon** (EU, Frankfurt): usage-based, pauses when idle, pgvector and unaccent | Supabase Pro ($25/month flat, 8 GB); PlanetScale Postgres through Cloudflare (single bill, but its $5 node was "coming soon" and the price for 2.3 GB unclear) |
| Web runtime | **Cloudflare Containers** running the existing FastAPI image behind a Worker | Python Workers: GA with FastAPI, but Pyodide with async drivers (asyncpg); our sync SQLAlchemy + compiled psycopg would need rewriting |
| Daily update | **Cloudflare cron trigger** starting a container that runs `ingest update` | GitHub Actions schedule (simpler to debug, but outside Cloudflare) |
| AI cost on a public site | **Per-visitor rate limit** on summaries in the Worker, the $5 monthly cap stays | Summaries only after a click; a higher cap |
| Address | **`*.workers.dev`** first; a custom domain later | Buying a domain now |

## What is moving (28 Nov)

Database 2,290 MB: `speech_revision` 851 MB, `speech_chunk` 443 MB (vectors and
HNSW), `vote_record` 342 MB, `apology` 170 MB, `speech_paragraph` 166 MB.
Extensions `unaccent` 1.1 and `vector` 0.8.7. The Czech tagger model is 26 MB
(CC BY-NC-SA, fine for a non-commercial public site; credited on the
methodology page). The local HTTP cache (818 MB) is not needed in production.

## Platform facts used (Cloudflare docs read 28 Nov 2026)

- Containers use the Durable Object Container API: a Durable Object starts its
  container with `ctx.container.start({ image, instance, enableInternet, env,
  entrypoint })`, reaches it with `getTcpPort(port).fetch()`, and keeps it alive
  with `setInactivityTimeout()`. Wrangler: `containers[]` with
  `scheduling_policy: "durable_object"` and `images.base.dockerfile`.
- Instance types: lite (1/16 vCPU, 256 MiB), basic (1/4, 1 GiB), standard-1
  (1/2, 4 GiB), standard-2 (1, 6 GiB) and larger. Images up to the instance disk.
- Pricing on Workers Paid ($5/month): 25 GiB-hours memory, 375 vCPU-minutes and
  200 GB-hours disk included; then $0.0000025/GiB-s, $0.000020/vCPU-s (active
  only), $0.00000007/GB-s. Billing stops when a container sleeps.
- `enableInternet: true` lets the container reach any host (Neon on 5432,
  psp.cz, Voyage, Anthropic). Worker secrets are passed in `env` at start.
- Placement follows the Durable Object namespace's jurisdiction: `eu` keeps
  containers in Europe, near the Frankfurt database.
- Cron triggers run in UTC; the `scheduled()` handler waits at most 15 minutes,
  so the job container is started and left to finish on its own.
- Rate limiting binding (`ratelimits`, period 10 or 60 s, per Cloudflare
  location) works in the Worker on workers.dev; zone WAF rules would need a
  custom domain.

## Plan

1. **Image.** One Dockerfile for web and job (Python, uv, MorphoDiTa model
   baked in); web runs uvicorn on 8080, the job overrides the entrypoint.
2. **Worker** (`deploy/cloudflare/`): `Web` Durable Object (basic instance,
   15-minute inactivity timeout, EU jurisdiction) for all requests; `Update`
   Durable Object (standard-1) started by a daily cron; rate limits on
   `/api/shrnuti` and search; a token-protected manual trigger for the job.
3. **App changes:** accept Neon's `postgresql://` URL, proxy headers.
4. **Database:** create the Neon project (EU, Postgres 18), prepare extensions
   in the `extensions` schema with the search path, restore the local dump
   (no re-embedding), verify counts and timings.
5. **Deploy:** secrets via `wrangler secret put`, migrations against Neon, then
   `wrangler deploy`; verify the site and one manual job run.
6. **Runbook** here and in CLAUDE.md.

The user provides: a Cloudflare account on Workers Paid, `wrangler login`, a Neon
account and project, and the connection string in a private file.

## Built (28 Nov, branch `feature/production`)

- `Dockerfile` (repository root): Python 3.14 slim, uv 0.13.7 from pip (the
  classic builder cannot export the multi-arch uv image used with `COPY --from`),
  dependencies from `uv.lock`, the tagger fetched at build. 682 MB for
  linux/amd64. Checked under emulation on the M2: the tagger loads and tags
  Czech, the compiled psycopg is used, the app starts, serves static files and
  answers `/health` with 503 without a database. Web runs uvicorn with proxy
  headers on 8080; the job overrides the entrypoint.
- `deploy/cloudflare/`: Wrangler 4.169 config and Worker (`src/index.ts`).
  `Web` (basic instance, 15-minute inactivity timeout) receives every request
  after one readiness check per container start; `Update` (standard-1) is started
  by the cron at 04:30 UTC or by `POST /_admin/update` with the admin token, runs
  `python -m rozprava.ingest update` and stops when it exits (at most 3 hours).
  Both in the `eu` jurisdiction. Rate limits: 10 summaries and 60 searches per
  visitor per minute; a limited summary request gets a Czech note in place of the
  summary. `npm run check` generates types and typechecks.
- `settings.py` accepts Neon's `postgresql://` and `postgres://` URLs.
- `scripts/remote_db.py check|restore|migrate|compare|status` and
  `scripts/cloudflare_secrets.py`; secrets are read from `.env` and
  `.env.production` and never printed.

## Runbook

First setup, in order:

1. **Neon:** create project `rozprava` in AWS Europe Central 1 (Frankfurt) with
   Postgres 18. The archive (2.3 GB) needs a paid plan. Copy the *direct*
   connection string (connection pooling off: the importer holds an advisory
   lock for the whole run, which a transaction pooler would break), then save it
   at a hidden prompt (works in zsh and bash):
   `printf 'Neon URL: '; read -rs key; echo; printf 'DATABASE_URL=%s\n' "$key" >> .env.production; unset key`
2. `uv run python scripts/remote_db.py check`: vector and unaccent available.
3. `uv run python scripts/local_db.py backup`, then
   `uv run python scripts/remote_db.py restore <dump>`, `compare`, `migrate`.
   The restore runs four parallel jobs for speed, so a failure can leave part of
   the archive behind; empty the database with
   `uv run python scripts/remote_db.py reset --confirm <database name>` and restore again.
4. **Cloudflare:** Workers Paid plan on the account Wrangler logs into;
   `(cd deploy/cloudflare && npm ci && npx wrangler login)`. Wrangler builds with
   `docker buildx` (`--load`): `brew install docker-buildx` and link it into
   `~/.docker/cli-plugins/`.
5. `uv run python scripts/cloudflare_secrets.py`.
6. `colima start`, then `(cd deploy/cloudflare && npx wrangler deploy)` (builds
   the linux/amd64 image with the local Docker).
7. Open `https://rozprava.<subdomain>.workers.dev`; the first request starts the
   container. Start one import by hand to check it:
   `curl -X POST -H "Authorization: Bearer <ADMIN_TOKEN from .env.production>" https://…/_admin/update`
   and follow it in the Cloudflare dashboard (Workers → rozprava → Logs) and with
   `uv run python scripts/remote_db.py status`.

Releasing a change: tests, then `remote_db.py migrate` when there is a new
migration, then `npx wrangler deploy`.

## First attempt (28 Nov): two plans missing

- **Neon free plan.** The restore stopped at `word_form` with "could not extend
  file because project size limit (1024 MB) has been exceeded". The free plan
  allows 1 GB per project and counts the change history too, so it filled at
  183 MB of restored data. The archive needs a paid plan. The partial copy was
  emptied with `remote_db.py reset --confirm neondb`, added for this; `restore`
  refuses a database that already holds tables and points to it.
- **Workers Paid not active.** The image built (buildx installed for it), then
  the push failed with 401 on `/containers/me`; `wrangler containers list` gave
  the reason: "You do not have access to Cloudflare Containers. Deploying
  containers requires the Workers Paid plan." Wrangler was logged in as
  vojtech.balcar@sbid.cz, whose account does not have the plan.
- Also: Colima failed to start on a missing `user-v2` network socket after the
  previous session ended abruptly; `colima stop --force` then `colima start` fixed
  it. The dump now skips comments (`--no-comments`): commenting on an extension
  needs its owner, which on Neon is not our role.

## First deployment attempt (28 Nov)

- **Neon restore, try 1:** pg_restore with four parallel jobs failed on
  `CREATE SCHEMA extensions` ("already exists"), although the dump creates it once,
  and the workers kept loading for a while after the error, leaving a partial copy.
  Now `remote_db.py restore` creates the schema itself and leaves the dump's entry
  out with a filtered table of contents (`--use-list`). `--no-comments` (added
  alongside) skips comments on extensions, which need the extension's owner.
- **Credentials on a command line.** The first version passed the Neon URL to
  `pg_restore --dbname=…`, so the password was visible in the process list, and a
  `pgrep -fl` printed it into the session. The script now passes libpq settings
  through environment variables (`PGPASSWORD` and the rest). The Neon password
  must be reset after this.
- **Neon restore, try 2:** stopped at "project size limit (1024 MB) has been
  exceeded": the project was on Neon's Free plan, capped at 1 GB, and the archive
  is 2.3 GB. Needs a paid Neon plan. The partial copy was removed both times
  (only after checking that `alembic_version` was empty, i.e. the restore never
  completed).
- **Image build for Wrangler:** `wrangler deploy` runs `docker build --load`,
  which needs BuildKit's buildx plugin. It was installed by Homebrew but not
  registered; `~/.docker/config.json` now lists `/opt/homebrew/lib/docker/cli-plugins`
  in `cliPluginsExtraDirs`. The image then built under Colima.
- **Cloudflare:** the push failed with "You do not have access to Cloudflare
  Containers. Deploying containers requires the Workers Paid plan." for the
  account Wrangler is logged into (vojtech.balcar@sbid.cz), although the token has
  `containers (write)`.

## Deployed (28 Nov 2026)

- **Neon** after the upgrade to a paid plan (`neon.max_cluster_size` 16 TB instead
  of 1 GB) and a password reset. `restore` failed once more at once: pg_restore 18
  requires `--dbname`, and the URL had been moved to environment variables; it now
  gets only the database name, which holds no secret. The process list showed no
  credentials during the run. The restore then loaded the 610 MB dump with four
  jobs; `compare` matched every table (96,731 speech revisions, 316,741
  paragraphs, 78,239 passages, 212,965 word forms, 2,376,200 vote records,
  migration 0006). 1,912 MB on Neon (2.3 GB locally, where indexes are older).
- **Cloudflare:** Wrangler was logged in to the account with Workers Paid;
  `wrangler deploy` built the image under Colima, pushed it (about 2.5 minutes) and
  created both Durable Objects, the two rate limits and the cron.
  Address: https://rozprava.vojtech-balcar.workers.dev. The four secrets were set
  before the first request.
- **First requests:** `/health` 200 after a 15-second cold start; home 1.0 s,
  "důchod" 1.6 s, "jak se změnily důchody" 0.7 s with 604 speeches and 48 related
  by meaning; a cached summary 0.7 s; `/poslanci` 3.1 s on first load. `/hledat/`
  now redirects to the public origin.
- **Manual import:** `POST /_admin/update` answered "Import started." and a wrong
  token 404; run 23 (metadata) appeared in Neon, running as PID 1 in the container.
