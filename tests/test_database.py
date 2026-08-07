from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.db.base import Base


def test_shared_declarative_base_contains_only_i02_iam_tables() -> None:
    assert set(Base.metadata.tables) == {
        "sys_org",
        "sys_position",
        "sys_role",
        "sys_user",
        "sys_user_org",
        "sys_user_org_position",
        "sys_user_org_role",
    }


def test_database_migration_can_be_created_and_destroyed(tmp_path: Path) -> None:
    database_path = tmp_path / "missing-parent" / "i01.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "0001_i01")
    assert database_path.parent.exists()
    engine = create_engine(database_url)
    assert inspect(engine).get_table_names() == ["alembic_version"]

    command.downgrade(config, "base")
    engine.dispose()
    database_path.unlink()
    assert not database_path.exists()


def test_i02_migration_creates_and_removes_iam_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "i02.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    table_names = set(inspect(engine).get_table_names())
    assert table_names == {
        "alembic_version",
        "sys_org",
        "sys_position",
        "sys_role",
        "sys_user",
        "sys_user_org",
        "sys_user_org_position",
        "sys_user_org_role",
    }

    command.downgrade(config, "0001_i01")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()
