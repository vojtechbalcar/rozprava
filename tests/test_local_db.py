"""Local cluster guardrails; PostgreSQL lifecycle is exercised separately."""

import importlib.util
import os
import sys
from pathlib import Path

import pytest


def load_local_db():
    spec = importlib.util.spec_from_file_location(
        "local_db", Path(__file__).parents[1] / "scripts/local_db.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_database_names_are_explicit_test_databases():
    local_db = load_local_db()
    assert (
        local_db.validate_test_database_url(
            "postgresql+psycopg://u:p@127.0.0.1:55432/rozprava_test"
        )
        == "rozprava_test"
    )
    for name in ["rozprava", "postgres", "x_test;DROP TABLE speech", "x-test", ""]:
        with pytest.raises(ValueError):
            local_db.validate_test_database_url(f"postgresql+psycopg://u:p@127.0.0.1:55432/{name}")


def test_env_preserves_existing_values_and_uses_private_permissions(tmp_path):
    local_db = load_local_db()
    env_file = tmp_path / ".env"
    env_file.write_text("# User config\nUNRELATED_KEY=keep\nROZPRAVA_DATA_DIR=/existing\n")
    os.chmod(env_file, 0o644)
    additions = {"DATABASE_URL": "postgresql+psycopg://u:p@127.0.0.1:55432/rozprava"}
    local_db.write_env(env_file, additions)
    local_db.write_env(env_file, additions)
    contents = env_file.read_text()
    assert contents.count("DATABASE_URL=") == 1
    assert "UNRELATED_KEY=keep\nROZPRAVA_DATA_DIR=/existing\n" in contents
    assert env_file.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="preserve"):
        local_db.write_env(env_file, {"DATABASE_URL": "postgresql+psycopg://different/db"})
    assert env_file.read_text() == contents


@pytest.mark.parametrize(
    "value",
    [
        "/tmp/rozpráva",
        '/tmp/rozpráva/"quoted"/back\\slash',
        "/tmp/rozpráva/O'Brien/back\\slash",
        "/tmp/rozpráva/line\nbreak/with\ttab",
    ],
)
def test_env_paths_round_trip_unicode_quotes_and_backslashes(tmp_path, value):
    from dotenv import dotenv_values

    from rozprava.settings import Settings

    local_db = load_local_db()
    env_file = tmp_path / ".env"
    local_db.write_env(env_file, {"ROZPRAVA_DATA_DIR": value})
    assert dotenv_values(env_file)["ROZPRAVA_DATA_DIR"] == value
    assert Settings(_env_file=env_file).data_dir == Path(value)
    saved = env_file.read_bytes()
    local_db.write_env(env_file, {"ROZPRAVA_DATA_DIR": value})
    assert env_file.read_bytes() == saved


def test_existing_cluster_without_credentials_is_never_reinitialized(tmp_path):
    local_db = load_local_db()
    cluster = tmp_path / "postgres"
    cluster.mkdir()
    (cluster / "PG_VERSION").write_text("18\n")
    sentinel = cluster / "keep-me"
    sentinel.write_text("retained")
    manager = local_db.LocalDatabase(tmp_path, tmp_path / ".env", 55432)
    with pytest.raises(ValueError, match="credentials"):
        manager.init()
    assert sentinel.read_text() == "retained"


def test_private_cluster_lifecycle_retains_data_and_credentials():
    import socket
    import tempfile
    from typing import Any

    import psycopg
    from sqlalchemy.engine import make_url

    local_db = load_local_db()
    try:
        local_db.postgres_bin()
    except ValueError:
        pytest.skip("Homebrew PostgreSQL 18 is not installed")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    # macOS limits Unix socket paths; pytest's deeply nested temp path is too long.
    with tempfile.TemporaryDirectory(prefix="rz-", dir="/tmp") as directory:
        data_dir = Path(directory)
        manager = local_db.LocalDatabase(data_dir, data_dir / ".env", port)
        try:
            manager.init()
            saved_credentials = manager.credentials_file.read_bytes()
            saved_env = manager.env_file.read_bytes()
            url = make_url(manager.url())
            params: dict[str, Any] = dict(
                host=url.host,
                port=url.port,
                dbname=url.database,
                user=url.username,
                password=url.password,
            )
            with psycopg.connect(**params) as connection:
                flags = connection.execute(
                    "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles "
                    "WHERE rolname=current_user"
                ).fetchone()
                assert flags == (False, False, False)
                assert connection.execute("SHOW listen_addresses").fetchone() == ("127.0.0.1",)
                connection.execute("CREATE TABLE persistence_check (value text)")
                connection.execute("INSERT INTO persistence_check VALUES ('retained')")
            manager.init()
            assert manager.credentials_file.read_bytes() == saved_credentials
            assert manager.env_file.read_bytes() == saved_env
            manager.stop()
            assert not manager.running()
            manager.start()
            with psycopg.connect(**params) as connection:
                assert connection.execute("SELECT value FROM persistence_check").fetchone() == (
                    "retained",
                )
            test_params: dict[str, Any] = dict(params, dbname="rozprava_test")
            with psycopg.connect(**test_params) as connection:
                assert connection.execute(
                    "SELECT to_regclass('public.persistence_check')"
                ).fetchone() == (None,)
            backup = manager.backup()
            assert backup.read_bytes().startswith(b"PGDMP")
            for private_file in [manager.env_file, manager.credentials_file, backup]:
                assert private_file.stat().st_mode & 0o777 == 0o600
        finally:
            if manager.credentials_file.exists():
                manager.stop()
