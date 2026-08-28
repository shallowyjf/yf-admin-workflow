"""Application-scoped roles and governed business resources.

Revision ID: 0017_i24_data_permissions
Revises: 0016_unified_login
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_i24_data_permissions"
down_revision: str | None = "0016_unified_login"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column, sa.Column, sa.Column]:
    return (
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )


def upgrade() -> None:
    op.create_table(
        "iam_application_role_grant",
        *_timestamps(),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("tenant_application_id", sa.Integer(), nullable=False),
        sa.Column("user_org_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.DateTime()),
        sa.Column("valid_to", sa.DateTime()),
        sa.Column("grant_source", sa.String(length=40), nullable=False, server_default="ADMIN"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.ForeignKeyConstraint(["tenant_id"], ["sys_tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_application_id"], ["sys_tenant_application.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_org_id"], ["sys_user_org.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["sys_role.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "tenant_application_id", "user_org_id", "role_id", name="uq_application_role_grant"
        ),
    )
    op.create_index(
        "ix_app_role_grant_tenant_app",
        "iam_application_role_grant",
        ["tenant_id", "tenant_application_id"],
    )
    op.create_index(
        "ix_app_role_grant_membership", "iam_application_role_grant", ["user_org_id"]
    )

    op.create_table(
        "dc_data_space",
        *_timestamps(),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("space_code", sa.String(length=80), nullable=False),
        sa.Column("space_name", sa.String(length=160), nullable=False),
        sa.Column("space_type", sa.String(length=40), nullable=False),
        sa.Column("domain_type", sa.String(length=40)),
        sa.Column("application_id", sa.Integer()),
        sa.Column("project_id", sa.Integer()),
        sa.Column("owner_org_id", sa.Integer(), nullable=False),
        sa.Column(
            "sensitivity_level", sa.String(length=20), nullable=False, server_default="INTERNAL"
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.ForeignKeyConstraint(["tenant_id"], ["sys_tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["sys_application.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["pm_project.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_org_id"], ["sys_org.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "space_code", name="uq_data_space_tenant_code"),
    )
    op.create_index(
        "ix_data_space_tenant_application", "dc_data_space", ["tenant_id", "application_id"]
    )

    op.create_table(
        "dc_business_resource",
        *_timestamps(),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("data_space_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer()),
        sa.Column("owner_org_id", sa.Integer(), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=False),
        sa.Column("resource_key", sa.String(length=120), nullable=False),
        sa.Column("resource_name", sa.String(length=200), nullable=False),
        sa.Column("parent_resource_id", sa.Integer()),
        sa.Column("derivation_stage", sa.String(length=40), nullable=False),
        sa.Column(
            "sensitivity_level", sa.String(length=20), nullable=False, server_default="INTERNAL"
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["sys_tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["data_space_id"], ["dc_data_space.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["sys_application.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["pm_project.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_org_id"], ["sys_org.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["parent_resource_id"], ["dc_business_resource.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("tenant_id", "resource_key", name="uq_resource_tenant_key"),
    )
    op.create_index(
        "ix_resource_tenant_application",
        "dc_business_resource",
        ["tenant_id", "application_id"],
    )
    op.create_index(
        "ix_resource_space_stage",
        "dc_business_resource",
        ["data_space_id", "derivation_stage"],
    )

    op.create_table(
        "auth_resource_policy",
        *_timestamps(),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(length=20), nullable=False, server_default="ROLE"),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("action_code", sa.String(length=120), nullable=False),
        sa.Column("effect", sa.String(length=10), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("valid_from", sa.DateTime()),
        sa.Column("valid_to", sa.DateTime()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.ForeignKeyConstraint(["tenant_id"], ["sys_tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["dc_business_resource.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id",
            "subject_type",
            "subject_id",
            "resource_id",
            "action_code",
            "effect",
            name="uq_resource_policy_rule",
        ),
    )
    op.create_index(
        "ix_resource_policy_resource_action",
        "auth_resource_policy",
        ["resource_id", "action_code"],
    )
    op.create_index(
        "ix_resource_policy_subject",
        "auth_resource_policy",
        ["tenant_id", "subject_type", "subject_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_resource_policy_subject", table_name="auth_resource_policy")
    op.drop_index("ix_resource_policy_resource_action", table_name="auth_resource_policy")
    op.drop_table("auth_resource_policy")
    op.drop_index("ix_resource_space_stage", table_name="dc_business_resource")
    op.drop_index("ix_resource_tenant_application", table_name="dc_business_resource")
    op.drop_table("dc_business_resource")
    op.drop_index("ix_data_space_tenant_application", table_name="dc_data_space")
    op.drop_table("dc_data_space")
    op.drop_index("ix_app_role_grant_membership", table_name="iam_application_role_grant")
    op.drop_index("ix_app_role_grant_tenant_app", table_name="iam_application_role_grant")
    op.drop_table("iam_application_role_grant")
