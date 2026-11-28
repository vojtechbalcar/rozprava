"""Configuration safety: importing code never creates a database connection."""

import importlib
from pathlib import Path

import pytest
from pydantic import ValidationError


def test_configuration_is_postgresql_only():
    from rozprava.settings import Settings

    with pytest.raises(ValidationError, match="postgresql\\+psycopg"):
        Settings(database_url="sqlite:///example.db", _env_file=None)


def test_hosted_postgresql_urls_use_psycopg():
    from rozprava.settings import Settings

    neon = "postgresql://owner:secret@ep-1.eu-central-1.aws.neon.tech/neondb?sslmode=require"
    url = Settings(database_url=neon, _env_file=None).database_url
    assert url == neon.replace("postgresql://", "postgresql+psycopg://", 1)
    short = Settings(database_url="postgres://u:p@host/db", _env_file=None).database_url
    assert short == "postgresql+psycopg://u:p@host/db"


def test_settings_reads_dotenv_without_requiring_a_database(tmp_path, monkeypatch):
    from rozprava.settings import Settings

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ROZPRAVA_DATA_DIR", raising=False)
    monkeypatch.delenv("ROZPRAVA_CACHE_DIR", raising=False)
    settings = Settings(_env_file=None)
    assert settings.database_url is None
    assert settings.data_dir == Path.home() / ".local/share/rozprava"
    assert settings.cache_dir == settings.data_dir / "cache"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql+psycopg://u:secret@127.0.0.1:55432/rozprava\n"
        f"ROZPRAVA_DATA_DIR={tmp_path}/data\n"
        "UNRELATED_KEY=preserved\n"
    )
    configured = Settings(_env_file=env_file)
    assert configured.database_url is not None
    assert configured.data_dir == tmp_path / "data"
    assert configured.cache_dir == tmp_path / "data/cache"


def test_database_import_and_engine_creation_do_not_connect(monkeypatch):
    import sqlalchemy

    def forbidden(*args, **kwargs):
        pytest.fail("Import/configuration must not connect to PostgreSQL")

    monkeypatch.setattr(sqlalchemy.engine.Engine, "connect", forbidden)
    module = importlib.import_module("rozprava.db")
    importlib.reload(module)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1:55432/rozprava")
    module.clear_caches()
    assert module.get_engine().url.database == "rozprava"
    assert module.get_session_factory().kw["bind"] is module.get_engine()
    module.clear_caches()
