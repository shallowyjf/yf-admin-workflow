"""I11 IAM administration audit log.

Revision ID: 0007_i11
Revises: 0006_i07
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_i11"
down_revision: str | None = "0006_i07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sys_iam_audit_log",
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
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("operator_id", sa.Integer(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["sys_user.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sys_iam_audit_entity",
        "sys_iam_audit_log",
        ["entity_type", "entity_id"],
    )
    op.create_index(
        "ix_sys_iam_audit_operator_id",
        "sys_iam_audit_log",
        ["operator_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sys_iam_audit_operator_id",
        table_name="sys_iam_audit_log",
    )
    op.drop_index(
        "ix_sys_iam_audit_entity",
        table_name="sys_iam_audit_log",
    )
    op.drop_table("sys_iam_audit_log")
