"""GIS authorization persistence models."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data_permission.models import BusinessResource
from app.db.base import Base
from app.db.mixins import IdTimestampMixin
from app.iam.models import Role, User


class ResourceField(IdTimestampMixin, Base):
    """A governed attribute exposed by one GIS layer resource."""

    __tablename__ = "dc_resource_field"
    __table_args__ = (
        UniqueConstraint("resource_id", "field_code", name="uq_resource_field_code"),
        Index("ix_resource_field_tenant_resource", "tenant_id", "resource_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant.id", ondelete="CASCADE"), nullable=False
    )
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("dc_business_resource.id", ondelete="CASCADE"), nullable=False
    )
    field_code: Mapped[str] = mapped_column(String(80), nullable=False)
    field_name: Mapped[str] = mapped_column(String(120), nullable=False)
    data_type: Mapped[str] = mapped_column(String(40), nullable=False)
    sensitivity_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="INTERNAL", server_default="INTERNAL"
    )
    mask_rule: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )

    resource: Mapped[BusinessResource] = relationship()


class ResourceFieldPolicy(IdTimestampMixin, Base):
    """Role-specific VISIBLE, MASKED, or HIDDEN field decision."""

    __tablename__ = "auth_resource_field_policy"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "role_id",
            "resource_field_id",
            name="uq_resource_field_policy",
        ),
        Index("ix_field_policy_role", "tenant_id", "role_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("sys_role.id", ondelete="CASCADE"), nullable=False
    )
    resource_field_id: Mapped[int] = mapped_column(
        ForeignKey("dc_resource_field.id", ondelete="CASCADE"), nullable=False
    )
    access_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )

    role: Mapped[Role] = relationship()
    resource_field: Mapped[ResourceField] = relationship()


class SpatialScopeGrant(IdTimestampMixin, Base):
    """A role's allowed region/DMA/project boundary for one GIS resource."""

    __tablename__ = "auth_spatial_scope_grant"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "role_id",
            "resource_id",
            "scope_type",
            "scope_value",
            name="uq_spatial_scope_grant",
        ),
        Index("ix_spatial_scope_resource_role", "resource_id", "role_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("sys_role.id", ondelete="CASCADE"), nullable=False
    )
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("dc_business_resource.id", ondelete="CASCADE"), nullable=False
    )
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_value: Mapped[str] = mapped_column(String(120), nullable=False)
    coordinate_precision: Mapped[str] = mapped_column(
        String(20), nullable=False, default="REGION_ONLY", server_default="REGION_ONLY"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )

    role: Mapped[Role] = relationship()
    resource: Mapped[BusinessResource] = relationship()


class GISFeature(IdTimestampMixin, Base):
    """Small simulated feature dataset used to prove server-side filtering."""

    __tablename__ = "dc_gis_feature"
    __table_args__ = (
        UniqueConstraint("resource_id", "feature_key", name="uq_gis_feature_key"),
        Index("ix_gis_feature_scope", "resource_id", "scope_type", "scope_value"),
        Index("ix_gis_feature_tenant", "tenant_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant.id", ondelete="CASCADE"), nullable=False
    )
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("dc_business_resource.id", ondelete="CASCADE"), nullable=False
    )
    feature_key: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_name: Mapped[str] = mapped_column(String(160), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_value: Mapped[str] = mapped_column(String(120), nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    properties_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )

    resource: Mapped[BusinessResource] = relationship()


class GISExportJob(IdTimestampMixin, Base):
    """Auditable simulated GIS export; no real file is generated in I25."""

    __tablename__ = "dc_gis_export_job"
    __table_args__ = (
        Index("ix_gis_export_tenant_user", "tenant_id", "requested_by"),
        Index("ix_gis_export_resource", "resource_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant.id", ondelete="CASCADE"), nullable=False
    )
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("dc_business_resource.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="RESTRICT"), nullable=False
    )
    export_format: Mapped[str] = mapped_column(
        String(20), nullable=False, default="CSV", server_default="CSV"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="COMPLETED", server_default="COMPLETED"
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    field_codes_json: Mapped[list] = mapped_column(JSON, nullable=False)
    spatial_scope_json: Mapped[list] = mapped_column(JSON, nullable=False)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)

    resource: Mapped[BusinessResource] = relationship()
    requester: Mapped[User] = relationship()
