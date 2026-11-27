#!/usr/bin/env python3
"""Manage only Rozprava's private PostgreSQL cluster; never a system service.

Run with ``uv run python scripts/local_db.py init``. Credentials are retained in
private files; no command prints them. No operation deletes or resets a cluster.
"""

import argparse
import getpass
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg import sql
from sqlalchemy import URL
from sqlalchemy.engine import make_url

from rozprava.settings import Settings

ROLE = "rozprava"
DATABASE = "rozprava"
TEST_DATABASE = "rozprava_test"
DEFAULT_PORT = 55432
VECTOR_SCHEMA = "extensions"  # pgvector (meaning search); see docs/related-search.md


class MissingExtension(Exception):
    """pgvector is not installed for this PostgreSQL."""


def validate_test_database_url(value: str) -> str:
    """Require an explicit, simple test database name before test-only operations."""
    url = make_url(value)
    name = url.database or ""
    if url.drivername != "postgresql+psycopg" or not re.fullmatch(r"[a-z][a-z0-9_]*_test", name):
        raise ValueError("An explicit PostgreSQL database with a name ending in _test is required")
    return name


def private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def write_env(path: Path, values: dict[str, str]) -> None:
    """Append missing configuration, retaining all existing values and comments."""
    existing = dotenv_values(path) if path.exists() else {}
    for key, value in values.items():
        if key in existing and existing[key] != value:
            raise ValueError(f"To preserve existing {key}, refusing to replace its value in {path}")
    content = path.read_text() if path.exists() else ""
    additions = "".join(
        f"{key}={json.dumps(value, ensure_ascii=False)}\n"
        for key, value in values.items()
        if key not in existing
    )
    if content and not content.endswith("\n"):
        content += "\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(content + additions)


def postgres_bin() -> Path:
    for prefix in (Path("/opt/homebrew"), Path("/usr/local")):
        candidate = prefix / "opt/postgresql@18/bin"
        if (candidate / "pg_ctl").is_file():
            return candidate
    raise ValueError("PostgreSQL 18 is missing; install it with brew install postgresql@18")


class LocalDatabase:
    def __init__(self, data_dir: Path, env_file: Path, port: int = DEFAULT_PORT):
        self.data_dir = data_dir.expanduser().resolve()
        self.env_file = env_file.expanduser().resolve()
        self.cluster = self.data_dir / "postgres"
        self.socket = self.data_dir / "socket"
        self.credentials_file = self.data_dir / "local-db.json"
        self.port = port

    def run(self, command: str, *arguments: str, allow_failure: bool = False) -> int:
        result = subprocess.run(
            [str(postgres_bin() / command), *arguments], capture_output=True, text=True
        )
        if result.returncode and not allow_failure:
            # PostgreSQL output may contain connection details. Keep it in the
            # private server log instead of echoing it to the terminal.
            raise ValueError(f"{command} failed; inspect {self.data_dir / 'postgres.log'}")
        return result.returncode

    def credentials(self) -> dict[str, str | int]:
        if not self.credentials_file.exists():
            raise ValueError("Local credentials are missing; run init for a new cluster")
        credentials = json.loads(self.credentials_file.read_text())
        if credentials.get("port") != self.port:
            raise ValueError("Port differs from the existing private cluster configuration")
        return credentials

    def url(self, database: str = DATABASE) -> str:
        return URL.create(
            "postgresql+psycopg",
            username=ROLE,
            password=str(self.credentials()["password"]),
            host="127.0.0.1",
            port=self.port,
            database=database,
        ).render_as_string(hide_password=False)

    def running(self) -> bool:
        if not (self.cluster / "PG_VERSION").exists():
            return False
        return self.run("pg_ctl", "-D", str(self.cluster), "status", allow_failure=True) == 0

    def start(self) -> None:
        self.credentials()
        if not (self.cluster / "PG_VERSION").exists():
            raise ValueError("Cluster is not initialized; run init")
        if self.running():
            return
        private_directory(self.socket)
        options = shlex.join(["-h", "127.0.0.1", "-p", str(self.port), "-k", str(self.socket)])
        self.run(
            "pg_ctl",
            "-D",
            str(self.cluster),
            "-l",
            str(self.data_dir / "postgres.log"),
            "-o",
            options,
            "-w",
            "start",
        )

    def stop(self) -> None:
        self.credentials()
        if self.running():
            self.run("pg_ctl", "-D", str(self.cluster), "-m", "fast", "-w", "stop")

    def admin_connection(self, database: str = "postgres"):
        return psycopg.connect(
            host=str(self.socket),
            port=self.port,
            dbname=database,
            user=getpass.getuser(),
            autocommit=True,
        )

    def create_database(self, name: str) -> None:
        # Identifiers never come from an interpolated SQL string.
        with self.admin_connection() as connection:
            if not connection.execute(
                "SELECT 1 FROM pg_database WHERE datname=%s", (name,)
            ).fetchone():
                connection.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(name), sql.Identifier(ROLE)
                    )
                )
        self.enable_vectors(name)

    def enable_vectors(self, name: str) -> None:
        """Install pgvector, which only a superuser may do, in its own schema.

        The schema survives the test suite's reset of `public`, and the database's
        search path lets the application role use its types and operators.
        """
        with self.admin_connection(name) as connection:
            if not connection.execute(
                "SELECT 1 FROM pg_available_extensions WHERE name='vector'"
            ).fetchone():
                raise MissingExtension
            connection.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(VECTOR_SCHEMA))
            )
            connection.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(VECTOR_SCHEMA), sql.Identifier(ROLE)
                )
            )
            connection.execute(
                sql.SQL("CREATE EXTENSION IF NOT EXISTS vector SCHEMA {}").format(
                    sql.Identifier(VECTOR_SCHEMA)
                )
            )
            connection.execute(
                sql.SQL('ALTER DATABASE {} SET search_path = "$user", public, {}').format(
                    sql.Identifier(name), sql.Identifier(VECTOR_SCHEMA)
                )
            )

    def init(self) -> None:
        existing_cluster = (self.cluster / "PG_VERSION").exists()
        if existing_cluster and not self.credentials_file.exists():
            raise ValueError("Existing cluster has no saved credentials; refusing to reinitialize")
        private_directory(self.data_dir)
        if not self.credentials_file.exists():
            descriptor = os.open(self.credentials_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as handle:
                json.dump({"password": secrets.token_urlsafe(36), "port": self.port}, handle)
        values = {
            "DATABASE_URL": self.url(),
            "TEST_DATABASE_URL": self.url(TEST_DATABASE),
            "ROZPRAVA_DATA_DIR": str(self.data_dir),
        }
        # Check configuration conflicts before touching the cluster.
        write_env(self.env_file, values)
        if not existing_cluster:
            self.run(
                "initdb",
                "-D",
                str(self.cluster),
                "-U",
                getpass.getuser(),
                "--encoding=UTF8",
                "--locale=C",
                "--auth-local=peer",
                "--auth-host=scram-sha-256",
            )
        self.start()
        with self.admin_connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname=%s", (ROLE,)
            ).fetchone()
            if not exists:
                connection.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}"
                    ).format(sql.Identifier(ROLE), sql.Literal(str(self.credentials()["password"])))
                )
        self.create_database(DATABASE)
        self.test_db()
        self.check_ready()

    def test_db(self) -> None:
        validate_test_database_url(self.url(TEST_DATABASE))
        self.start()
        self.create_database(TEST_DATABASE)

    def check_ready(self) -> None:
        url = make_url(self.url())
        with psycopg.connect(
            host=url.host,
            port=url.port,
            dbname=url.database,
            user=url.username,
            password=url.password,
            connect_timeout=5,
        ) as connection:
            connection.execute("SELECT 1").fetchone()

    def backup(self) -> Path:
        self.check_ready()
        directory = self.data_dir / "backups"
        private_directory(directory)
        destination = directory / f"rozprava-{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}.dump"
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        self.run(
            "pg_dump",
            "-h",
            str(self.socket),
            "-p",
            str(self.port),
            "-U",
            getpass.getuser(),
            "-d",
            DATABASE,
            "-Fc",
            "-f",
            str(destination),
        )
        return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["init", "start", "stop", "status", "backup", "test-db", "vectors"]
    )
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    try:
        if not 1024 <= args.port <= 65535:
            raise ValueError("Choose an unprivileged port between 1024 and 65535")
        settings = Settings(_env_file=args.env_file)
        manager = LocalDatabase(args.data_dir or settings.data_dir, args.env_file, args.port)
        match args.command:
            case "init":
                manager.init()
                print("Local PostgreSQL initialized and ready; private configuration saved.")
            case "start":
                manager.start()
                manager.check_ready()
                print("Local PostgreSQL is ready.")
            case "stop":
                manager.stop()
                print("Local PostgreSQL stopped.")
            case "status":
                if not manager.running():
                    print("Local PostgreSQL is stopped.")
                    return 1
                manager.check_ready()
                print("Local PostgreSQL is running and ready on loopback.")
            case "test-db":
                manager.test_db()
                print("Separate test database is ready; no existing data was reset.")
            case "vectors":
                manager.start()
                for name in (DATABASE, TEST_DATABASE):
                    manager.enable_vectors(name)
                print("pgvector is installed in both databases.")
            case "backup":
                print(f"Backup saved: {manager.backup()}")
    except MissingExtension:
        print(
            "pgvector is not installed for this PostgreSQL. Run `brew install pgvector`, "
            "then repeat this command.",
            file=sys.stderr,
        )
        return 1
    except (ValueError, OSError, psycopg.Error):
        # Exception strings from drivers/validation can contain URLs/passwords.
        print(
            "Database operation failed. Check PostgreSQL 18 installation, private configuration, "
            "port availability and the private postgres.log; existing data was retained.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
