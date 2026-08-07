"""I04 server-side authentication sessions.

Revision ID: 0004_i04
Revises: 0003_i03
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_i04"
down_revision: str | None = "0003_i03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sys_auth_session",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("active_org_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
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
        sa.ForeignKeyConstraint(["active_org_id"], ["sys_org.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["sys_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_sys_auth_session_expires_at",
        "sys_auth_session",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sys_auth_session_expires_at",
        table_name="sys_auth_session",
    )
    op.drop_table("sys_auth_session")
