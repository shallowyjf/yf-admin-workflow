"""I23 demo project milestones and progress dashboard.

Revision ID: 0014_i23
Revises: 0013_i22
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_i23"
down_revision: str | None = "0013_i22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pm_project_milestone",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("milestone_code", sa.String(length=80), nullable=False),
        sa.Column("milestone_name", sa.String(length=160), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("planned_percent", sa.Integer(), nullable=False),
        sa.Column("actual_percent", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
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
        sa.ForeignKeyConstraint(["project_id"], ["pm_project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "milestone_code", name="uq_project_milestone_code"
        ),
    )
    op.create_index(
        "ix_project_milestone_project_status",
        "pm_project_milestone",
        ["project_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_milestone_project_status",
        table_name="pm_project_milestone",
    )
    op.drop_table("pm_project_milestone")
