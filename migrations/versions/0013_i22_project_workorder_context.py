"""I22 bind work orders and workflow runtime to project context.

Revision ID: 0013_i22
Revises: 0012_i21
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_i22"
down_revision: str | None = "0012_i21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _default_context() -> tuple[int, int, int]:
    connection = op.get_bind()
    tenant_id = connection.scalar(sa.text("SELECT id FROM sys_tenant ORDER BY id LIMIT 1"))
    if tenant_id is None:
        raise RuntimeError("I22 migration requires one tenant")
    application_id = connection.scalar(
        sa.text("SELECT id FROM sys_application WHERE application_code = 'WATER_SUPPLY'")
    )
    if application_id is None:
        connection.execute(
            sa.text(
                "INSERT INTO sys_application "
                "(application_code, application_name, domain_type, is_active) "
                "VALUES ('WATER_SUPPLY', '供水系统', 'WATER_SUPPLY', 1)"
            )
        )
        application_id = connection.scalar(
            sa.text("SELECT id FROM sys_application WHERE application_code = 'WATER_SUPPLY'")
        )
    subscription_id = connection.scalar(
        sa.text(
            "SELECT id FROM sys_tenant_application "
            "WHERE tenant_id = :tenant_id AND application_id = :application_id"
        ),
        {"tenant_id": tenant_id, "application_id": application_id},
    )
    if subscription_id is None:
        connection.execute(
            sa.text(
                "INSERT INTO sys_tenant_application "
                "(tenant_id, application_id, is_active) "
                "VALUES (:tenant_id, :application_id, 1)"
            ),
            {"tenant_id": tenant_id, "application_id": application_id},
        )
    project_id = connection.scalar(
        sa.text(
            "SELECT id FROM pm_project "
            "WHERE tenant_id = :tenant_id AND project_code = 'WS_NETWORK_RENEWAL'"
        ),
        {"tenant_id": tenant_id},
    )
    if project_id is None:
        connection.execute(
            sa.text(
                "INSERT INTO pm_project "
                "(tenant_id, application_id, project_code, project_name, "
                "project_status, start_date, end_date) "
                "VALUES (:tenant_id, :application_id, 'WS_NETWORK_RENEWAL', "
                "'供水管网更新改造工程', 'ACTIVE', '2026-01-01', '2026-12-31')"
            ),
            {"tenant_id": tenant_id, "application_id": application_id},
        )
        project_id = connection.scalar(
            sa.text(
                "SELECT id FROM pm_project "
                "WHERE tenant_id = :tenant_id "
                "AND project_code = 'WS_NETWORK_RENEWAL'"
            ),
            {"tenant_id": tenant_id},
        )
    return int(tenant_id), int(application_id), int(project_id)


def _add_context_columns(table_name: str) -> None:
    with op.batch_alter_table(table_name, recreate="always") as batch_op:
        batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("application_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("project_id", sa.Integer(), nullable=True))


def _constrain_context_columns(table_name: str) -> None:
    with op.batch_alter_table(table_name, recreate="always") as batch_op:
        for column_name in ("tenant_id", "application_id", "project_id"):
            batch_op.alter_column(
                column_name,
                existing_type=sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            )
        batch_op.create_foreign_key(
            f"fk_{table_name}_tenant",
            "sys_tenant",
            ["tenant_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            f"fk_{table_name}_application",
            "sys_application",
            ["application_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            f"fk_{table_name}_project",
            "pm_project",
            ["project_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def upgrade() -> None:
    tenant_id, application_id, project_id = _default_context()
    for table_name in ("wo_work_order", "wf_instance", "wf_task"):
        _add_context_columns(table_name)
    connection = op.get_bind()
    context = {
        "tenant_id": tenant_id,
        "application_id": application_id,
        "project_id": project_id,
    }
    connection.execute(
        sa.text(
            "UPDATE wo_work_order SET tenant_id=:tenant_id, "
            "application_id=:application_id, project_id=:project_id"
        ),
        context,
    )
    connection.execute(
        sa.text(
            "UPDATE wf_instance SET "
            "tenant_id=COALESCE((SELECT tenant_id FROM wo_work_order "
            "WHERE wo_work_order.id=wf_instance.business_id "
            "AND wf_instance.business_type='WORK_ORDER'), :tenant_id), "
            "application_id=COALESCE((SELECT application_id FROM wo_work_order "
            "WHERE wo_work_order.id=wf_instance.business_id "
            "AND wf_instance.business_type='WORK_ORDER'), :application_id), "
            "project_id=COALESCE((SELECT project_id FROM wo_work_order "
            "WHERE wo_work_order.id=wf_instance.business_id "
            "AND wf_instance.business_type='WORK_ORDER'), :project_id)"
        ),
        context,
    )
    connection.execute(
        sa.text(
            "UPDATE wf_task SET "
            "tenant_id=(SELECT tenant_id FROM wf_instance "
            "WHERE wf_instance.id=wf_task.instance_id), "
            "application_id=(SELECT application_id FROM wf_instance "
            "WHERE wf_instance.id=wf_task.instance_id), "
            "project_id=(SELECT project_id FROM wf_instance "
            "WHERE wf_instance.id=wf_task.instance_id)"
        )
    )
    for table_name in ("wo_work_order", "wf_instance", "wf_task"):
        _constrain_context_columns(table_name)
    op.create_index(
        "ix_wo_work_order_context",
        "wo_work_order",
        ["tenant_id", "application_id", "project_id"],
    )
    op.create_index(
        "ix_wf_instance_context",
        "wf_instance",
        ["tenant_id", "application_id", "project_id"],
    )
    op.create_index(
        "ix_wf_task_context_status",
        "wf_task",
        ["tenant_id", "application_id", "project_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_wf_task_context_status", table_name="wf_task")
    op.drop_index("ix_wf_instance_context", table_name="wf_instance")
    op.drop_index("ix_wo_work_order_context", table_name="wo_work_order")
    for table_name in ("wf_task", "wf_instance", "wo_work_order"):
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            batch_op.drop_column("project_id")
            batch_op.drop_column("application_id")
            batch_op.drop_column("tenant_id")
