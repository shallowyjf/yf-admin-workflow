from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.db.base import Base


def test_shared_declarative_base_is_empty_in_i01() -> None:
    assert list(Base.metadata.tables) == []


def test_database_migration_can_be_created_and_destroyed(tmp_path: Path) -> None:
    database_path = tmp_path / "missing-parent" / "i01.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")
    assert database_path.parent.exists()
    engine = create_engine(database_url)
    assert inspect(engine).get_table_names() == ["alembic_version"]

    command.downgrade(config, "base")
    engine.dispose()
    database_path.unlink()
    assert not database_path.exists()
