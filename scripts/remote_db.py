#!/usr/bin/env python3
"""Manage the production database (Neon): load the local archive and apply migrations.

The connection string lives in the private, git-ignored `.env.production` as
DATABASE_URL (Neon's direct, unpooled URL); no command prints it. See
docs/production-deployment.md.

    uv run python scripts/remote_db.py check            # server, extensions, search path
    uv run python scripts/remote_db.py restore DUMP     # load a local_db.py backup (once)
    uv run python scripts/remote_db.py migrate          # alembic upgrade head
    uv run python scripts/remote_db.py compare          # row counts: local vs production
    uv run python scripts/remote_db.py status           # `ingest status` for production

`restore` refuses a database that already holds an archive.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg import sql
from sqlalchemy.engine import make_url

from rozprava.settings import Settings

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env.production"
PG_BIN = Path("/opt/homebrew/opt/postgresql@18/bin")
SEARCH_PATH = '"$user", public, extensions'
COUNTED = ("speech_revision", "speech_paragraph", "speech_chunk", "word_form", "vote_record")


def production_url() -> str:
    value = dotenv_values(ENV_FILE).get("DATABASE_URL") if ENV_FILE.exists() else None
    if not value:
        raise SystemExit(f"Put the Neon DATABASE_URL in {ENV_FILE.name} first.")
    # Settings normalises postgresql:// and checks the scheme.
    url = Settings(database_url=value, _env_file=None).database_url
    assert url is not None
    return url


def libpq(url: str) -> str:
    """The same URL for libpq tools (psycopg, pg_restore), without the SQLAlchemy driver."""
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(libpq(url), autocommit=True, connect_timeout=20)


def check(url: str) -> None:
    with connect(url) as db:
        version = db.execute("SHOW server_version").fetchone()
        print(f"server: PostgreSQL {version[0] if version else '?'}")
        available = dict(
            db.execute(
                "SELECT name, default_version FROM pg_available_extensions "
                "WHERE name IN ('vector', 'unaccent')"
            ).fetchall()
        )
        for name in ("vector", "unaccent"):
            print(f"{name}: {'available ' + available[name] if name in available else 'MISSING'}")
        installed = db.execute("SELECT extname, extversion FROM pg_extension").fetchall()
        print("installed:", ", ".join(f"{n} {v}" for n, v in installed))
        path = db.execute("SHOW search_path").fetchone()
        print(f"search_path: {path[0] if path else '?'}")


def restore(url: str, dump: Path) -> None:
    if not dump.is_file():
        raise SystemExit(f"No such dump: {dump}")
    with connect(url) as db:
        if db.execute("SELECT to_regclass('public.speech_revision')").fetchone() != (None,):
            raise SystemExit("This database already holds an archive; nothing was restored.")
        name = db.execute("SELECT current_database()").fetchone()
        assert name is not None
        # pgvector's types and operators live in the extensions schema, as locally
        # (scripts/local_db.py); new sessions must find them without qualification.
        db.execute(
            sql.SQL("ALTER DATABASE {} SET search_path = " + SEARCH_PATH).format(
                sql.Identifier(name[0])
            )
        )
    tool = PG_BIN / "pg_restore" if (PG_BIN / "pg_restore").exists() else shutil.which("pg_restore")
    if not tool:
        raise SystemExit("pg_restore (PostgreSQL 18) is not installed.")
    print(f"Restoring {dump.name} ({dump.stat().st_size / 1e6:.0f} MB); this takes a while.")
    environment = os.environ | {"PGCONNECT_TIMEOUT": "20"}
    result = subprocess.run(
        [
            str(tool),
            "--no-owner",
            "--no-privileges",
            "--exit-on-error",
            "--jobs=4",
            f"--dbname={libpq(url)}",
            str(dump),
        ],
        env=environment,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Error text from pg_restore names objects, not the connection string.
        print(result.stderr[-3000:], file=sys.stderr)
        raise SystemExit("pg_restore failed; see the messages above.")
    print("Restored. Next: compare, then migrate.")


def migrate(url: str) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    engine = create_engine(url)
    with engine.begin() as connection:
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    engine.dispose()
    print("Production schema is at the latest migration.")


def compare(url: str) -> None:
    local = Settings().database_url
    if not local:
        raise SystemExit("No local DATABASE_URL in .env.")
    counts = {}
    for label, target in (("local", local), ("production", url)):
        with connect(target) as db:
            counts[label] = [
                db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # type: ignore[index]
                for table in COUNTED
            ]
            version = db.execute("SELECT version_num FROM alembic_version").fetchone()
            counts[label].append(version[0] if version else "-")
    print(f"{'table':<18}{'local':>14}{'production':>14}")
    for i, table in enumerate((*COUNTED, "migration")):
        mark = "" if counts["local"][i] == counts["production"][i] else "  differs"
        print(f"{table:<18}{counts['local'][i]!s:>14}{counts['production'][i]!s:>14}{mark}")


def status(url: str) -> None:
    os.environ["DATABASE_URL"] = url  # read by the settings the importer uses
    from rozprava.ingest.__main__ import print_status

    print_status()


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("command", choices=["check", "restore", "migrate", "compare", "status"])
    parser.add_argument("dump", nargs="?", type=Path, help="custom-format dump for restore")
    args = parser.parse_args()
    url = production_url()
    try:
        if args.command == "check":
            check(url)
        elif args.command == "restore":
            if args.dump is None:
                parser.error("restore needs a dump (uv run python scripts/local_db.py backup)")
            restore(url, args.dump)
        elif args.command == "migrate":
            migrate(url)
        elif args.command == "status":
            status(url)
        else:
            compare(url)
    except psycopg.Error as error:
        # Driver messages describe the failure without the password.
        message = str(error).strip()[:300]
        print(f"Database error: {type(error).__name__}: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
