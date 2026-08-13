from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.db.base import Base


def test_shared_declarative_base_contains_current_tables() -> None:
    assert set(Base.metadata.tables) == {
        "pm_project",
        "pm_project_member",
        "pm_project_milestone",
        "pm_project_org",
        "sys_application",
        "sys_auth_session",
        "sys_iam_audit_log",
            "sys_notification",
            "sys_platform_session",
            "sys_platform_user",
            "sys_saved_view",
        "sys_tenant",
        "sys_tenant_application",
        "sys_org",
        "sys_permission",
        "sys_position",
        "sys_role",
        "sys_role_data_scope",
        "sys_role_permission",
        "sys_user",
        "sys_user_application",
        "sys_user_org",
        "sys_user_org_position",
        "sys_user_org_role",
        "wf_definition",
        "wf_instance",
        "wf_task",
        "wf_task_candidate",
        "wf_task_history",
        "wo_action",
        "wo_attachment",
        "wo_work_order",
        "wo_sla_policy",
    }


def test_i18_migration_creates_and_removes_saved_views(tmp_path: Path) -> None:
    database_path = tmp_path / "i18.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "0009_i18")
    engine = create_engine(database_url)
    assert "sys_saved_view" in inspect(engine).get_table_names()

    command.downgrade(config, "0008_i17")
    assert "sys_saved_view" not in inspect(engine).get_table_names()
    engine.dispose()


def test_i19_migration_creates_tenant_scoped_iam(tmp_path: Path) -> None:
    database_path = tmp_path / "i19.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "0010_i19")
    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert "sys_tenant" in inspector.get_table_names()
    for table_name in (
        "sys_user",
        "sys_org",
        "sys_role",
        "sys_position",
        "sys_iam_audit_log",
        "sys_auth_session",
    ):
        assert "tenant_id" in {
            column["name"] for column in inspector.get_columns(table_name)
        }
    unique_columns = {
        tuple(item["column_names"])
        for item in inspector.get_unique_constraints("sys_user")
    }
    assert ("tenant_id", "username") in unique_columns

    command.downgrade(config, "0009_i18")
    inspector = inspect(engine)
    assert "sys_tenant" not in inspector.get_table_names()
    assert "tenant_id" not in {
        column["name"] for column in inspector.get_columns("sys_user")
    }
    engine.dispose()


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

    command.upgrade(config, "0002_i02")
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


def test_i03_migration_creates_and_removes_authorization_tables(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "i03.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "0003_i03")
    engine = create_engine(database_url)
    table_names = set(inspect(engine).get_table_names())
    assert {
        "sys_permission",
        "sys_role_data_scope",
        "sys_role_permission",
    } <= table_names

    command.downgrade(config, "0002_i02")
    assert not {
        "sys_permission",
        "sys_role_data_scope",
        "sys_role_permission",
    } & set(inspect(engine).get_table_names())
    engine.dispose()


def test_i04_migration_creates_and_removes_auth_session_table(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "i04.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "0004_i04")
    engine = create_engine(database_url)
    assert "sys_auth_session" in inspect(engine).get_table_names()

    command.downgrade(config, "0003_i03")
    assert "sys_auth_session" not in inspect(engine).get_table_names()
    engine.dispose()


def test_i06_migration_creates_and_removes_work_order_tables(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "i06.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "0005_i06")
    engine = create_engine(database_url)
    assert {"wo_work_order", "wo_action"} <= set(inspect(engine).get_table_names())

    command.downgrade(config, "0004_i04")
    assert not {"wo_work_order", "wo_action"} & set(inspect(engine).get_table_names())
    engine.dispose()


def test_i07_migration_creates_and_removes_workflow_tables(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "i07.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    workflow_tables = {
        "wf_definition",
        "wf_instance",
        "wf_task",
        "wf_task_candidate",
        "wf_task_history",
    }
    command.upgrade(config, "0006_i07")
    engine = create_engine(database_url)
    assert workflow_tables <= set(inspect(engine).get_table_names())

    command.downgrade(config, "0005_i06")
    assert not workflow_tables & set(inspect(engine).get_table_names())
    engine.dispose()


def test_i11_migration_creates_and_removes_iam_audit_table(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "i11.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "0007_i11")
    engine = create_engine(database_url)
    assert "sys_iam_audit_log" in inspect(engine).get_table_names()

    command.downgrade(config, "0006_i07")
    assert "sys_iam_audit_log" not in inspect(engine).get_table_names()
    engine.dispose()


def test_i17_migration_creates_sla_attachment_and_notification_schema(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "i17.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "0008_i17")
    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert {"wo_sla_policy", "wo_attachment", "sys_notification"} <= set(
        inspector.get_table_names()
    )
    work_order_columns = {
        column["name"] for column in inspector.get_columns("wo_work_order")
    }
    assert {"response_due_at", "responded_at", "sla_status"} <= work_order_columns

    command.downgrade(config, "0007_i11")
    inspector = inspect(engine)
    assert not {"wo_sla_policy", "wo_attachment", "sys_notification"} & set(
        inspector.get_table_names()
    )
    engine.dispose()
