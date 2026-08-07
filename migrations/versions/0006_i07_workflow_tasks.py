"""I07 workflow instances and human tasks.

Revision ID: 0006_i07
Revises: 0005_i06
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_i07"
down_revision: str | None = "0005_i06"
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
        "wf_definition",
        *_common_columns(),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition_json", sa.JSON(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "code",
            "version",
            name="uq_wf_definition_code_version",
        ),
    )
    op.create_table(
        "wf_instance",
        *_common_columns(),
        sa.Column("definition_id", sa.Integer(), nullable=False),
        sa.Column("business_type", sa.String(length=60), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("current_node", sa.String(length=80), nullable=False),
        sa.Column("initiator_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["definition_id"],
            ["wf_definition.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["initiator_id"],
            ["sys_user.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "business_type",
            "business_id",
            name="uq_wf_instance_business",
        ),
    )
    op.create_index(
        "ix_wf_instance_definition_id",
        "wf_instance",
        ["definition_id"],
    )
    op.create_table(
        "wf_task",
        *_common_columns(),
        sa.Column("instance_id", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("assignee_id", sa.Integer(), nullable=True),
        sa.Column("candidate_rule_json", sa.JSON(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["assignee_id"],
            ["sys_user.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["instance_id"],
            ["wf_instance.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_wf_task_instance_id",
        "wf_task",
        ["instance_id"],
    )
    op.create_index(
        "ix_wf_task_status_assignee_id",
        "wf_task",
        ["status", "assignee_id"],
    )
    op.create_table(
        "wf_task_candidate",
        *_common_columns(),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("candidate_type", sa.String(length=40), nullable=False),
        sa.Column("candidate_value", sa.JSON(), nullable=False),
        sa.Column("resolved_user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["resolved_user_id"],
            ["sys_user.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["wf_task.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "task_id",
            "resolved_user_id",
            name="uq_wf_task_candidate_user",
        ),
    )
    op.create_index(
        "ix_wf_task_candidate_task_user",
        "wf_task_candidate",
        ["task_id", "resolved_user_id"],
    )
    op.create_table(
        "wf_task_history",
        *_common_columns(),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("operator_id", sa.Integer(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["sys_user.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["wf_task.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_wf_task_history_task_id",
        "wf_task_history",
        ["task_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wf_task_history_task_id",
        table_name="wf_task_history",
    )
    op.drop_table("wf_task_history")
    op.drop_index(
        "ix_wf_task_candidate_task_user",
        table_name="wf_task_candidate",
    )
    op.drop_table("wf_task_candidate")
    op.drop_index("ix_wf_task_status_assignee_id", table_name="wf_task")
    op.drop_index("ix_wf_task_instance_id", table_name="wf_task")
    op.drop_table("wf_task")
    op.drop_index(
        "ix_wf_instance_definition_id",
        table_name="wf_instance",
    )
    op.drop_table("wf_instance")
    op.drop_table("wf_definition")
