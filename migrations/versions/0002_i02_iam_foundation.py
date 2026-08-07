"""I02 IAM foundation.

Revision ID: 0002_i02
Revises: 0001_i01
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_i02"
down_revision: str | None = "0001_i01"
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
        "sys_user",
        *_common_columns(),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "sys_org",
        *_common_columns(),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("org_code", sa.String(length=80), nullable=False),
        sa.Column("org_name", sa.String(length=160), nullable=False),
        sa.Column("org_type", sa.String(length=40), nullable=True),
        sa.Column("org_path", sa.String(length=500), nullable=False),
        sa.Column("sort_no", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["sys_org.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("org_code"),
    )
    op.create_index("ix_sys_org_parent_id", "sys_org", ["parent_id"])
    op.create_index("ix_sys_org_org_path", "sys_org", ["org_path"])
    op.create_table(
        "sys_role",
        *_common_columns(),
        sa.Column("role_code", sa.String(length=80), nullable=False),
        sa.Column("role_name", sa.String(length=120), nullable=False),
        sa.Column("role_type", sa.String(length=40), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.UniqueConstraint("role_code"),
    )
    op.create_table(
        "sys_position",
        *_common_columns(),
        sa.Column("position_code", sa.String(length=80), nullable=False),
        sa.Column("position_name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.UniqueConstraint("position_code"),
    )
    op.create_table(
        "sys_user_org",
        *_common_columns(),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["sys_org.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["sys_user.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "org_id", name="uq_sys_user_org_user_org"),
    )
    op.create_index("ix_sys_user_org_org_id", "sys_user_org", ["org_id"])
    op.create_table(
        "sys_user_org_role",
        *_common_columns(),
        sa.Column("user_org_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["sys_role.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_org_id"], ["sys_user_org.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "user_org_id",
            "role_id",
            name="uq_sys_user_org_role_membership_role",
        ),
    )
    op.create_index("ix_sys_user_org_role_role_id", "sys_user_org_role", ["role_id"])
    op.create_table(
        "sys_user_org_position",
        *_common_columns(),
        sa.Column("user_org_id", sa.Integer(), nullable=False),
        sa.Column("position_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["position_id"], ["sys_position.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_org_id"], ["sys_user_org.id"], ondelete="CASCADE"
        ),
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


def downgrade() -> None:
    op.drop_index(
        "ix_sys_user_org_position_position_id", table_name="sys_user_org_position"
    )
    op.drop_table("sys_user_org_position")
    op.drop_index("ix_sys_user_org_role_role_id", table_name="sys_user_org_role")
    op.drop_table("sys_user_org_role")
    op.drop_index("ix_sys_user_org_org_id", table_name="sys_user_org")
    op.drop_table("sys_user_org")
    op.drop_table("sys_position")
    op.drop_table("sys_role")
    op.drop_index("ix_sys_org_org_path", table_name="sys_org")
    op.drop_index("ix_sys_org_parent_id", table_name="sys_org")
    op.drop_table("sys_org")
    op.drop_table("sys_user")
