"""I20 city lifeline systems and engineering project authorization spaces.

Revision ID: 0011_i20
Revises: 0010_i19
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_i20"
down_revision: str | None = "0010_i19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column, sa.Column, sa.Column]:
    return (
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
    )


def upgrade() -> None:
    op.create_table(
        "sys_application",
        sa.Column("application_code", sa.String(length=80), nullable=False),
        sa.Column("application_name", sa.String(length=160), nullable=False),
        sa.Column("domain_type", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_code"),
    )
    op.create_table(
        "sys_tenant_application",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["application_id"], ["sys_application.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["sys_tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "application_id", name="uq_tenant_application_tenant_app"
        ),
    )
    op.create_index(
        "ix_tenant_application_tenant_id", "sys_tenant_application", ["tenant_id"]
    )
    op.create_table(
        "pm_project",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("project_code", sa.String(length=80), nullable=False),
        sa.Column("project_name", sa.String(length=200), nullable=False),
        sa.Column(
            "project_status", sa.String(length=40), server_default="ACTIVE", nullable=False
        ),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["application_id"], ["sys_application.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["sys_tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "project_code", name="uq_project_tenant_code"),
    )
    op.create_index(
        "ix_project_tenant_application",
        "pm_project",
        ["tenant_id", "application_id"],
    )
    op.create_index("ix_project_status", "pm_project", ["project_status"])
    op.create_table(
        "pm_project_org",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("party_type", sa.String(length=40), nullable=False),
        sa.Column("is_lead", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["org_id"], ["sys_org.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["pm_project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "org_id", "party_type", name="uq_project_org_party"),
    )
    op.create_index("ix_project_org_org_id", "pm_project_org", ["org_id"])
    op.create_table(
        "pm_project_member",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("user_org_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["pm_project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["sys_role.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_org_id"], ["sys_user_org.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "user_org_id", "role_id", name="uq_project_member_role"
        ),
    )
    op.create_index(
        "ix_project_member_user_org_id", "pm_project_member", ["user_org_id"]
    )
    op.create_index("ix_project_member_role_id", "pm_project_member", ["role_id"])


def downgrade() -> None:
    op.drop_index("ix_project_member_role_id", table_name="pm_project_member")
    op.drop_index("ix_project_member_user_org_id", table_name="pm_project_member")
    op.drop_table("pm_project_member")
    op.drop_index("ix_project_org_org_id", table_name="pm_project_org")
    op.drop_table("pm_project_org")
    op.drop_index("ix_project_status", table_name="pm_project")
    op.drop_index("ix_project_tenant_application", table_name="pm_project")
    op.drop_table("pm_project")
    op.drop_index(
        "ix_tenant_application_tenant_id", table_name="sys_tenant_application"
    )
    op.drop_table("sys_tenant_application")
    op.drop_table("sys_application")
