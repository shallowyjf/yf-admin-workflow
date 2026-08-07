"""I03 functional permissions and data scopes.

Revision ID: 0003_i03
Revises: 0002_i02
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_i03"
down_revision: str | None = "0002_i02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _common_columns() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "sys_permission",
        *_common_columns(),
        sa.Column("permission_code", sa.String(length=120), nullable=False),
        sa.Column("permission_name", sa.String(length=160), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.UniqueConstraint("permission_code"),
    )
    op.create_table(
        "sys_role_permission",
        *_common_columns(),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["sys_permission.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["sys_role.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "role_id",
            "permission_id",
            name="uq_sys_role_permission_role_permission",
        ),
    )
    op.create_index(
        "ix_sys_role_permission_permission_id",
        "sys_role_permission",
        ["permission_id"],
    )
    op.create_table(
        "sys_role_data_scope",
        *_common_columns(),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_code", sa.String(length=120), nullable=False),
        sa.Column("scope_type", sa.String(length=40), nullable=False),
        sa.Column("scope_config", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["role_id"], ["sys_role.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "role_id",
            "permission_code",
            name="uq_sys_role_data_scope_role_permission",
        ),
    )


def downgrade() -> None:
    op.drop_table("sys_role_data_scope")
    op.drop_index(
        "ix_sys_role_permission_permission_id",
        table_name="sys_role_permission",
    )
    op.drop_table("sys_role_permission")
    op.drop_table("sys_permission")
