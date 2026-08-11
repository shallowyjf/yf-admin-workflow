"""I19 SaaS tenant and real-organization foundation.

Revision ID: 0010_i19
Revises: 0009_i18
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_i19"
down_revision: str | None = "0009_i18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def _tenant_column() -> sa.Column:
    return sa.Column(
        "tenant_id",
        sa.Integer(),
        server_default=sa.text("1"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "sys_tenant",
        sa.Column("tenant_code", sa.String(length=80), nullable=False),
        sa.Column("tenant_name", sa.String(length=160), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_code"),
    )
    tenant_table = sa.table(
        "sys_tenant",
        sa.column("id", sa.Integer()),
        sa.column("tenant_code", sa.String()),
        sa.column("tenant_name", sa.String()),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        tenant_table,
        [
            {
                "id": 1,
                "tenant_code": "DEMO",
                "tenant_name": "智慧城市演示租户",
                "is_active": True,
            }
        ],
    )

    scoped_tables = (
        (
            "sys_user",
            "uq_sys_user_username",
            "username",
            "uq_sys_user_tenant_username",
        ),
        (
            "sys_org",
            "uq_sys_org_org_code",
            "org_code",
            "uq_sys_org_tenant_code",
        ),
        (
            "sys_role",
            "uq_sys_role_role_code",
            "role_code",
            "uq_sys_role_tenant_code",
        ),
        (
            "sys_position",
            "uq_sys_position_position_code",
            "position_code",
            "uq_sys_position_tenant_code",
        ),
    )
    for table_name, old_unique, code_column, new_unique in scoped_tables:
        with op.batch_alter_table(
            table_name,
            recreate="always",
            naming_convention=NAMING_CONVENTION,
        ) as batch_op:
            batch_op.add_column(_tenant_column())
            batch_op.create_foreign_key(
                f"fk_{table_name}_tenant_id_sys_tenant",
                "sys_tenant",
                ["tenant_id"],
                ["id"],
                ondelete="RESTRICT",
            )
            batch_op.drop_constraint(old_unique, type_="unique")
            batch_op.create_unique_constraint(
                new_unique,
                ["tenant_id", code_column],
            )
            batch_op.create_index(f"ix_{table_name}_tenant_id", ["tenant_id"])

    for table_name, delete_rule in (
        ("sys_iam_audit_log", "RESTRICT"),
        ("sys_auth_session", "CASCADE"),
    ):
        with op.batch_alter_table(
            table_name,
            recreate="always",
            naming_convention=NAMING_CONVENTION,
        ) as batch_op:
            batch_op.add_column(_tenant_column())
            batch_op.create_foreign_key(
                f"fk_{table_name}_tenant_id_sys_tenant",
                "sys_tenant",
                ["tenant_id"],
                ["id"],
                ondelete=delete_rule,
            )
            batch_op.create_index(f"ix_{table_name}_tenant_id", ["tenant_id"])


def downgrade() -> None:
    for table_name in ("sys_auth_session", "sys_iam_audit_log"):
        with op.batch_alter_table(
            table_name,
            recreate="always",
            naming_convention=NAMING_CONVENTION,
        ) as batch_op:
            batch_op.drop_index(f"ix_{table_name}_tenant_id")
            batch_op.drop_constraint(
                f"fk_{table_name}_tenant_id_sys_tenant",
                type_="foreignkey",
            )
            batch_op.drop_column("tenant_id")

    scoped_tables = (
        (
            "sys_position",
            "uq_sys_position_tenant_code",
            "position_code",
            "uq_sys_position_position_code",
        ),
        (
            "sys_role",
            "uq_sys_role_tenant_code",
            "role_code",
            "uq_sys_role_role_code",
        ),
        (
            "sys_org",
            "uq_sys_org_tenant_code",
            "org_code",
            "uq_sys_org_org_code",
        ),
        (
            "sys_user",
            "uq_sys_user_tenant_username",
            "username",
            "uq_sys_user_username",
        ),
    )
    for table_name, scoped_unique, code_column, old_unique in scoped_tables:
        with op.batch_alter_table(
            table_name,
            recreate="always",
            naming_convention=NAMING_CONVENTION,
        ) as batch_op:
            batch_op.drop_index(f"ix_{table_name}_tenant_id")
            batch_op.drop_constraint(scoped_unique, type_="unique")
            batch_op.drop_constraint(
                f"fk_{table_name}_tenant_id_sys_tenant",
                type_="foreignkey",
            )
            batch_op.drop_column("tenant_id")
            batch_op.create_unique_constraint(old_unique, [code_column])

    op.drop_table("sys_tenant")
