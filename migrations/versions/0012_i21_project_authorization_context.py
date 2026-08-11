"""I21 user application access and active project session context.

Revision ID: 0012_i21
Revises: 0011_i20
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_i21"
down_revision: str | None = "0011_i20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sys_user_application",
        sa.Column("tenant_application_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["tenant_application_id"],
            ["sys_tenant_application.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["sys_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_application_id",
            "user_id",
            name="uq_user_application_subscription_user",
        ),
    )
    op.create_index(
        "ix_user_application_user_id", "sys_user_application", ["user_id"]
    )
    with op.batch_alter_table("sys_auth_session", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("active_application_id", sa.Integer()))
        batch_op.add_column(sa.Column("active_project_id", sa.Integer()))
        batch_op.create_foreign_key(
            "fk_auth_session_active_application",
            "sys_application",
            ["active_application_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_auth_session_active_project",
            "pm_project",
            ["active_project_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("sys_auth_session", recreate="always") as batch_op:
        batch_op.drop_constraint(
            "fk_auth_session_active_project", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_auth_session_active_application", type_="foreignkey"
        )
        batch_op.drop_column("active_project_id")
        batch_op.drop_column("active_application_id")
    op.drop_index("ix_user_application_user_id", table_name="sys_user_application")
    op.drop_table("sys_user_application")
