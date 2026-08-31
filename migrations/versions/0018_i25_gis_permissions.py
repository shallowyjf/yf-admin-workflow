"""GIS field, spatial scope, feature, and export authorization.

Revision ID: 0018_i25_gis_permissions
Revises: 0017_i24_data_permissions
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_i25_gis_permissions"
down_revision: str | None = "0017_i24_data_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column, sa.Column, sa.Column]:
    return (
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def upgrade() -> None:
    op.create_table(
        "dc_resource_field",
        *_timestamps(),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("field_code", sa.String(length=80), nullable=False),
        sa.Column("field_name", sa.String(length=120), nullable=False),
        sa.Column("data_type", sa.String(length=40), nullable=False),
        sa.Column(
            "sensitivity_level",
            sa.String(length=20),
            nullable=False,
            server_default="INTERNAL",
        ),
        sa.Column("mask_rule", sa.String(length=40)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.ForeignKeyConstraint(["tenant_id"], ["sys_tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["dc_business_resource.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("resource_id", "field_code", name="uq_resource_field_code"),
    )
    op.create_index(
        "ix_resource_field_tenant_resource",
        "dc_resource_field",
        ["tenant_id", "resource_id"],
    )

    op.create_table(
        "auth_resource_field_policy",
        *_timestamps(),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("resource_field_id", sa.Integer(), nullable=False),
        sa.Column("access_mode", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.ForeignKeyConstraint(["tenant_id"], ["sys_tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["sys_role.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["resource_field_id"], ["dc_resource_field.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "tenant_id", "role_id", "resource_field_id", name="uq_resource_field_policy"
        ),
    )
    op.create_index(
        "ix_field_policy_role", "auth_resource_field_policy", ["tenant_id", "role_id"]
    )

    op.create_table(
        "auth_spatial_scope_grant",
        *_timestamps(),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(length=40), nullable=False),
        sa.Column("scope_value", sa.String(length=120), nullable=False),
        sa.Column(
            "coordinate_precision",
            sa.String(length=20),
            nullable=False,
            server_default="REGION_ONLY",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.ForeignKeyConstraint(["tenant_id"], ["sys_tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["sys_role.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["dc_business_resource.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id",
            "role_id",
            "resource_id",
            "scope_type",
            "scope_value",
            name="uq_spatial_scope_grant",
        ),
    )
    op.create_index(
        "ix_spatial_scope_resource_role",
        "auth_spatial_scope_grant",
        ["resource_id", "role_id"],
    )

    op.create_table(
        "dc_gis_feature",
        *_timestamps(),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("feature_key", sa.String(length=100), nullable=False),
        sa.Column("feature_name", sa.String(length=160), nullable=False),
        sa.Column("scope_type", sa.String(length=40), nullable=False),
        sa.Column("scope_value", sa.String(length=120), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("properties_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["sys_tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["dc_business_resource.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("resource_id", "feature_key", name="uq_gis_feature_key"),
    )
    op.create_index(
        "ix_gis_feature_scope",
        "dc_gis_feature",
        ["resource_id", "scope_type", "scope_value"],
    )
    op.create_index("ix_gis_feature_tenant", "dc_gis_feature", ["tenant_id"])

    op.create_table(
        "dc_gis_export_job",
        *_timestamps(),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("export_format", sa.String(length=20), nullable=False, server_default="CSV"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="COMPLETED"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("field_codes_json", sa.JSON(), nullable=False),
        sa.Column("spatial_scope_json", sa.JSON(), nullable=False),
        sa.Column("file_name", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["sys_tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["dc_business_resource.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by"], ["sys_user.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_gis_export_tenant_user", "dc_gis_export_job", ["tenant_id", "requested_by"]
    )
    op.create_index("ix_gis_export_resource", "dc_gis_export_job", ["resource_id"])


def downgrade() -> None:
    op.drop_index("ix_gis_export_resource", table_name="dc_gis_export_job")
    op.drop_index("ix_gis_export_tenant_user", table_name="dc_gis_export_job")
    op.drop_table("dc_gis_export_job")
    op.drop_index("ix_gis_feature_tenant", table_name="dc_gis_feature")
    op.drop_index("ix_gis_feature_scope", table_name="dc_gis_feature")
    op.drop_table("dc_gis_feature")
    op.drop_index("ix_spatial_scope_resource_role", table_name="auth_spatial_scope_grant")
    op.drop_table("auth_spatial_scope_grant")
    op.drop_index("ix_field_policy_role", table_name="auth_resource_field_policy")
    op.drop_table("auth_resource_field_policy")
    op.drop_index("ix_resource_field_tenant_resource", table_name="dc_resource_field")
    op.drop_table("dc_resource_field")
