"""Shared fixtures. Database tests run only against the dedicated *_test database.

The schema is rebuilt once per test session from the migrations; each test then
runs inside a transaction that is rolled back, so tests never see each other's rows.
"""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from rozprava.settings import Settings

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def no_paid_services(monkeypatch):
    """Tests never see the developer's API keys, so nothing can reach Voyage or Claude;
    tests that need AI install fakes themselves."""
    from rozprava import main
    from rozprava.settings import get_settings

    monkeypatch.setattr(get_settings(), "voyage_api_key", None)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    cached = (main.query_embedder, main.summary_writer)  # tests may swap these for fakes
    for function in cached:
        function.cache_clear()
    yield
    for function in cached:
        function.cache_clear()


def configured_test_database_url() -> str:
    url = Settings().test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured; run scripts/local_db.py init")
    name = make_url(url).database or ""
    # Only ever reset a database explicitly named as a test database.
    if not re.fullmatch(r"[a-z][a-z0-9_]*_test", name):
        pytest.fail(f"Refusing to reset {name!r}: test database names must end in _test")
    return url


def alembic_config(connection: Connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def reset_schema(connection: Connection) -> None:
    connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
    connection.execute(text("CREATE SCHEMA public"))


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    engine = create_engine(configured_test_database_url())
    with engine.begin() as connection:
        reset_schema(connection)
        command.upgrade(alembic_config(connection), "head")
    yield engine
    engine.dispose()


@pytest.fixture
def connection(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


@pytest.fixture
def db(connection: Connection) -> Iterator[Session]:
    """A session whose work is rolled back after the test, even if the code commits."""
    with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
        yield session


@pytest.fixture
def sessions(connection: Connection):
    """A session factory inside the test transaction, for code that opens its own sessions."""
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=connection, join_transaction_mode="create_savepoint")


@pytest.fixture
def corpus(sessions, tmp_path: Path):
    """Both terms' fixture pages imported and assembled; returns the fake source."""
    from rozprava.ingest.runner import Runner
    from tests.psp_source import TABLES, FakeSource

    source = FakeSource(tmp_path)
    runner = Runner(sessions, source)
    runner.metadata(lambda session: TABLES)
    runner.backfill()
    return runner, source


@pytest.fixture
def client(corpus, sessions):
    from fastapi.testclient import TestClient

    from rozprava import main
    from rozprava.web import SHARED

    def db():
        with sessions() as session:
            yield session

    SHARED.clear()
    main.app.dependency_overrides[main.get_db] = db
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()
    SHARED.clear()
