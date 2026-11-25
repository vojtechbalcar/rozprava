"""Alembic environment: migrate the configured database, or a connection passed in."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine

from rozprava.models import Base
from rozprava.settings import get_settings

config = context.config
if config.config_file_name and not config.attributes.get("connection"):
    fileConfig(config.config_file_name)


def run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def main() -> None:
    if context.is_offline_mode():
        raise SystemExit("Offline SQL generation is not supported; run against a database.")
    connection = config.attributes.get("connection")
    if connection is not None:
        run(connection)
        return
    url = get_settings().database_url
    if not url:
        raise SystemExit("DATABASE_URL is missing; run uv run python scripts/local_db.py init")
    with create_engine(url).connect() as connection:
        run(connection)


main()
