"""Database access setup.

DATABASE_URL selects the storage backend:

    sqlite:///./careeragent.db                      (default, zero-config dev)
    postgresql+psycopg://user:pass@host:5432/db    (docker compose / production)

Alembic owns the schema: the FastAPI lifespan applies pending migrations
on startup, and `make migrate` runs the same migrations from the CLI.
"""

import os
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
DEFAULT_DATABASE_URL = "sqlite:///./careeragent.db"


def database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


@lru_cache
def get_engine():
    url = database_url()
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url)


@lru_cache
def get_session_factory() -> sessionmaker:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    with get_session_factory()() as session:
        yield session


def run_migrations(database_url_override: str | None = None) -> None:
    """Apply all pending Alembic migrations to the configured database."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", database_url_override or database_url())
    command.upgrade(config, "head")
