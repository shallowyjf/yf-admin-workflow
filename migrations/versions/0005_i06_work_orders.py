"""I06 work orders and action timeline.

Revision ID: 0005_i06
Revises: 0004_i04
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_i06"
down_revision: str | None = "0004_i04"
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
        "wo_work_order",
        *_common_columns(),
        sa.Column("work_order_no", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("type", sa.String(length=60), nullable=False),
        sa.Column("source_type", sa.String(length=60), nullable=True),
        sa.Column("source_id", sa.String(length=120), nullable=True),
        sa.Column("priority", sa.String(length=30), nullable=False),
        sa.Column("owner_org_id", sa.Integer(), nullable=False),
        sa.Column("current_org_id", sa.Integer(), nullable=False),
        sa.Column("current_assignee_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("asset_type", sa.String(length=60), nullable=True),
        sa.Column("asset_id", sa.String(length=120), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["sys_user.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["current_assignee_id"],
            ["sys_user.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["current_org_id"],
            ["sys_org.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_org_id"],
            ["sys_org.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("work_order_no"),
    )
    op.create_index("ix_wo_work_order_status", "wo_work_order", ["status"])
    op.create_index(
        "ix_wo_work_order_current_org_id",
        "wo_work_order",
        ["current_org_id"],
    )
    op.create_index(
        "ix_wo_work_order_current_assignee_id",
        "wo_work_order",
        ["current_assignee_id"],
    )
    op.create_index(
        "ix_wo_work_order_created_at",
        "wo_work_order",
        ["created_at"],
    )
    op.create_table(
        "wo_action",
        *_common_columns(),
        sa.Column("work_order_id", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=60), nullable=False),
        sa.Column("operator_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(length=40), nullable=True),
        sa.Column("to_status", sa.String(length=40), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["sys_user.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["wo_work_order.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_wo_action_work_order_id",
        "wo_action",
        ["work_order_id"],
    )
    op.create_index("ix_wo_action_created_at", "wo_action", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_wo_action_created_at", table_name="wo_action")
    op.drop_index("ix_wo_action_work_order_id", table_name="wo_action")
    op.drop_table("wo_action")
    op.drop_index("ix_wo_work_order_created_at", table_name="wo_work_order")
    op.drop_index(
        "ix_wo_work_order_current_assignee_id",
        table_name="wo_work_order",
    )
    op.drop_index("ix_wo_work_order_current_org_id", table_name="wo_work_order")
    op.drop_index("ix_wo_work_order_status", table_name="wo_work_order")
    op.drop_table("wo_work_order")
