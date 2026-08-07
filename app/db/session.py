"""Database engine and session lifecycle."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def prepare_database_directory(database_url: str) -> None:
    """Create the parent directory required by a file-based SQLite URL."""
    url = make_url(database_url)
    if url.drivername != "sqlite" or not url.database or url.database == ":memory:":
        return
    database_path = Path(url.database)
    database_path.parent.mkdir(parents=True, exist_ok=True)


class Database:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        prepare_database_directory(database_url)
        engine_options: dict = {"pool_pre_ping": True}
        if database_url in {"sqlite://", "sqlite:///:memory:"}:
            engine_options.update(
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        elif database_url.startswith("sqlite"):
            engine_options["connect_args"] = {"check_same_thread": False}

        self.engine: Engine = create_engine(database_url, **engine_options)
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
            class_=Session,
        )

    def session(self) -> Iterator[Session]:
        with self.session_factory() as db_session:
            yield db_session

    def dispose(self) -> None:
        self.engine.dispose()
