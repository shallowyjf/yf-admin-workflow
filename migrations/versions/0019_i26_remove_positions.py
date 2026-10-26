"""Remove the redundant position authorization dimension.

Revision ID: 0019_i26_remove_positions
Revises: 0018_i25_gis_permissions
Create Date: 2026-08-31
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_i26_remove_positions"
down_revision: str | None = "0018_i25_gis_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POSITION_PERMISSION_CODES = (
    "system:position:view",
    "system:position:create",
    "system:position:update",
    "system:position:status",
    "system:position:delete",
)

POSITION_TO_ROLE = {
    "TENANT_LEADER": "OWNER_LEADER",
    "DEPT_MANAGER": "WORKORDER_MANAGER",
    "SUPERVISOR": "REVIEWER",
    "DISPATCHER": "DISPATCHER",
    "REPAIRER": "REPAIRER",
    "PLATFORM_ENGINEER": "PLATFORM_OPERATOR",
    "BUSINESS_DIRECTOR": "BUSINESS_LEADER",
    "SYSTEM_OWNER": "SYSTEM_SPECIALIST",
    "OWNER_PROJECT_MANAGER": "OWNER_PROJECT_MANAGER",
    "SUPERVISOR_ENGINEER": "SUPERVISOR_ENGINEER",
    "DELIVERY_ENGINEER": "SOFTWARE_DELIVERY",
}


def _replace_position_rules(value: object) -> object:
    if isinstance(value, dict):
        converted = {
            key: _replace_position_rules(item)
            for key, item in value.items()
            if key != "position_code"
        }
        if value.get("candidate_type") == "ORG_POSITION":
            position_code = str(value.get("position_code") or "").strip()
            converted["candidate_type"] = "ORG_ROLE"
            converted["role_code"] = POSITION_TO_ROLE.get(
                position_code,
                position_code,
            )
        return converted
    if isinstance(value, list):
        return [_replace_position_rules(item) for item in value]
    return value


def _migrate_json_column(table_name: str, column_name: str) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f"SELECT id, {column_name} FROM {table_name}")
    ).mappings()
    for row in rows:
        raw_value = row[column_name]
        if raw_value is None:
            continue
        parsed = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
        converted = _replace_position_rules(parsed)
        if converted == parsed:
            continue
        bind.execute(
            sa.text(
                f"UPDATE {table_name} SET {column_name} = :payload WHERE id = :id"
            ),
            {"payload": json.dumps(converted, ensure_ascii=False), "id": row["id"]},
        )


def upgrade() -> None:
    _migrate_json_column("wf_definition", "definition_json")
    _migrate_json_column("wf_task", "candidate_rule_json")
    _migrate_json_column("wf_task_candidate", "candidate_value")

    bind = op.get_bind()
    placeholders = ", ".join(f":code_{index}" for index, _ in enumerate(POSITION_PERMISSION_CODES))
    parameters = {
        f"code_{index}": code for index, code in enumerate(POSITION_PERMISSION_CODES)
    }
    bind.execute(
        sa.text(
            f"DELETE FROM sys_role_data_scope WHERE permission_code IN ({placeholders})"
        ),
        parameters,
    )
    bind.execute(
        sa.text(
            "DELETE FROM sys_role_permission WHERE permission_id IN "
            f"(SELECT id FROM sys_permission WHERE permission_code IN ({placeholders}))"
        ),
        parameters,
    )
    bind.execute(
        sa.text(
            f"DELETE FROM sys_permission WHERE permission_code IN ({placeholders})"
        ),
        parameters,
    )

    op.drop_table("sys_user_org_position")
    op.drop_table("sys_position")


def downgrade() -> None:
    op.create_table(
        "sys_position",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("tenant_id", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("position_code", sa.String(length=80), nullable=False),
        sa.Column("position_name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.ForeignKeyConstraint(["tenant_id"], ["sys_tenant.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "position_code", name="uq_sys_position_tenant_code"),
    )
    op.create_index("ix_sys_position_tenant_id", "sys_position", ["tenant_id"])
    op.create_table(
        "sys_user_org_position",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("user_org_id", sa.Integer(), nullable=False),
        sa.Column("position_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_org_id"], ["sys_user_org.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["position_id"], ["sys_position.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_org_id",
            "position_id",
            name="uq_sys_user_org_position_membership_position",
        ),
    )
    op.create_index(
        "ix_sys_user_org_position_position_id",
        "sys_user_org_position",
        ["position_id"],
    )

    permission_table = sa.table(
        "sys_permission",
        sa.column("permission_code", sa.String),
        sa.column("permission_name", sa.String),
        sa.column("resource_type", sa.String),
    )
    op.bulk_insert(
        permission_table,
        [
            {
                "permission_code": code,
                "permission_name": name,
                "resource_type": "SYSTEM",
            }
            for code, name in (
                ("system:position:view", "查看岗位"),
                ("system:position:create", "新增岗位"),
                ("system:position:update", "编辑岗位"),
                ("system:position:status", "启停岗位"),
                ("system:position:delete", "删除岗位"),
            )
        ],
    )
