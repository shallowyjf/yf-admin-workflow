"""I18 operational efficiency and saved views.

Revision ID: 0009_i18
Revises: 0008_i17
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_i18"
down_revision: str | None = "0008_i17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sys_saved_view",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("module", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("filters_json", sa.JSON(), nullable=False),
        sa.Column(
            "is_default",
            sa.Boolean(),
            server_default=sa.text("0"),
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
        sa.ForeignKeyConstraint(
            ["user_id"], ["sys_user.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "module", "name", name="uq_saved_view_owner_name"
        ),
    )
    op.create_index(
        "ix_saved_view_user_module",
        "sys_saved_view",
        ["user_id", "module"],
    )


def downgrade() -> None:
    op.drop_index("ix_saved_view_user_module", table_name="sys_saved_view")
    op.drop_table("sys_saved_view")
