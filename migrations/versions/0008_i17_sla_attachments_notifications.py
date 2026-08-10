"""I17 SLA, attachments, and in-app notifications.

Revision ID: 0008_i17
Revises: 0007_i11
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_i17"
down_revision: str | None = "0007_i11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "wo_work_order",
        sa.Column("response_due_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "wo_work_order",
        sa.Column("responded_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "wo_work_order",
        sa.Column(
            "sla_status",
            sa.String(length=40),
            server_default="NOT_APPLICABLE",
            nullable=False,
        ),
    )
    op.create_table(
        "wo_sla_policy",
        sa.Column("priority", sa.String(length=30), nullable=False),
        sa.Column("response_minutes", sa.Integer(), nullable=False),
        sa.Column("resolve_minutes", sa.Integer(), nullable=False),
        sa.Column("calendar_code", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
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
        sa.UniqueConstraint("priority", name="uq_wo_sla_policy_priority"),
    )
    op.create_table(
        "wo_attachment",
        sa.Column("work_order_id", sa.Integer(), nullable=False),
        sa.Column("uploader_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("scan_status", sa.String(length=20), nullable=False),
        sa.Column("content_blob", sa.LargeBinary(), nullable=False),
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
            ["uploader_id"],
            ["sys_user.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["wo_work_order.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wo_attachment_sha256",
        "wo_attachment",
        ["sha256"],
    )
    op.create_index(
        "ix_wo_attachment_work_order_id",
        "wo_attachment",
        ["work_order_id"],
    )
    op.create_table(
        "sys_notification",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("work_order_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="UNREAD",
            nullable=False,
        ),
        sa.Column("delivery_attempts", sa.Integer(), server_default="1", nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
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
            ["user_id"],
            ["sys_user.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["wo_work_order.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sys_notification_user_status",
        "sys_notification",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_sys_notification_work_order_id",
        "sys_notification",
        ["work_order_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sys_notification_work_order_id",
        table_name="sys_notification",
    )
    op.drop_index(
        "ix_sys_notification_user_status",
        table_name="sys_notification",
    )
    op.drop_table("sys_notification")
    op.drop_index("ix_wo_attachment_work_order_id", table_name="wo_attachment")
    op.drop_index("ix_wo_attachment_sha256", table_name="wo_attachment")
    op.drop_table("wo_attachment")
    op.drop_table("wo_sla_policy")
    op.drop_column("wo_work_order", "sla_status")
    op.drop_column("wo_work_order", "responded_at")
    op.drop_column("wo_work_order", "response_due_at")
