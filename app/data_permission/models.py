"""Persistence models for application roles, data spaces, resources, and policies."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import IdTimestampMixin
from app.iam.models import Organization, Role, Tenant, UserOrganization
from app.project.models import Application, Project, TenantApplication


class ApplicationRoleGrant(IdTimestampMixin, Base):
    """Bind one organization membership and role inside one tenant application."""

    __tablename__ = "iam_application_role_grant"
    __table_args__ = (
        UniqueConstraint(
            "tenant_application_id",
            "user_org_id",
            "role_id",
            name="uq_application_role_grant",
        ),
        Index("ix_app_role_grant_tenant_app", "tenant_id", "tenant_application_id"),
        Index("ix_app_role_grant_membership", "user_org_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant.id", ondelete="CASCADE"), nullable=False
    )
    tenant_application_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant_application.id", ondelete="CASCADE"), nullable=False
    )
    user_org_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user_org.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("sys_role.id", ondelete="RESTRICT"), nullable=False
    )
    valid_from: Mapped[datetime | None] = mapped_column(DateTime)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime)
    grant_source: Mapped[str] = mapped_column(
        String(40), nullable=False, default="ADMIN", server_default="ADMIN"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )

    tenant: Mapped[Tenant] = relationship()
    tenant_application: Mapped[TenantApplication] = relationship()
    membership: Mapped[UserOrganization] = relationship()
    role: Mapped[Role] = relationship()


class DataSpace(IdTimestampMixin, Base):
    """A governed data boundary such as an application-private or model space."""

    __tablename__ = "dc_data_space"
    __table_args__ = (
        UniqueConstraint("tenant_id", "space_code", name="uq_data_space_tenant_code"),
        Index("ix_data_space_tenant_application", "tenant_id", "application_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant.id", ondelete="CASCADE"), nullable=False
    )
    space_code: Mapped[str] = mapped_column(String(80), nullable=False)
    space_name: Mapped[str] = mapped_column(String(160), nullable=False)
    space_type: Mapped[str] = mapped_column(String(40), nullable=False)
    domain_type: Mapped[str | None] = mapped_column(String(40))
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("sys_application.id", ondelete="RESTRICT")
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("pm_project.id", ondelete="SET NULL")
    )
    owner_org_id: Mapped[int] = mapped_column(
        ForeignKey("sys_org.id", ondelete="RESTRICT"), nullable=False
    )
    sensitivity_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="INTERNAL", server_default="INTERNAL"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )

    application: Mapped[Application | None] = relationship()
    project: Mapped[Project | None] = relationship()
    owner_organization: Mapped[Organization] = relationship()
    resources: Mapped[list[BusinessResource]] = relationship(
        back_populates="data_space", cascade="all, delete-orphan"
    )


class BusinessResource(IdTimestampMixin, Base):
    """A governed dataset, GIS layer, model, or derived result."""

    __tablename__ = "dc_business_resource"
    __table_args__ = (
        UniqueConstraint("tenant_id", "resource_key", name="uq_resource_tenant_key"),
        Index("ix_resource_tenant_application", "tenant_id", "application_id"),
        Index("ix_resource_space_stage", "data_space_id", "derivation_stage"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant.id", ondelete="CASCADE"), nullable=False
    )
    data_space_id: Mapped[int] = mapped_column(
        ForeignKey("dc_data_space.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[int] = mapped_column(
        ForeignKey("sys_application.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("pm_project.id", ondelete="SET NULL")
    )
    owner_org_id: Mapped[int] = mapped_column(
        ForeignKey("sys_org.id", ondelete="RESTRICT"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_key: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_resource_id: Mapped[int | None] = mapped_column(
        ForeignKey("dc_business_resource.id", ondelete="SET NULL")
    )
    derivation_stage: Mapped[str] = mapped_column(String(40), nullable=False)
    sensitivity_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="INTERNAL", server_default="INTERNAL"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )

    data_space: Mapped[DataSpace] = relationship(back_populates="resources")
    application: Mapped[Application] = relationship()
    project: Mapped[Project | None] = relationship()
    owner_organization: Mapped[Organization] = relationship()
    parent: Mapped[BusinessResource | None] = relationship(remote_side="BusinessResource.id")


class ResourcePolicy(IdTimestampMixin, Base):
    """Explicit allow/deny rule; DENY wins during evaluation."""

    __tablename__ = "auth_resource_policy"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "subject_type",
            "subject_id",
            "resource_id",
            "action_code",
            "effect",
            name="uq_resource_policy_rule",
        ),
        Index("ix_resource_policy_resource_action", "resource_id", "action_code"),
        Index("ix_resource_policy_subject", "tenant_id", "subject_type", "subject_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant.id", ondelete="CASCADE"), nullable=False
    )
    subject_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ROLE", server_default="ROLE"
    )
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False)
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("dc_business_resource.id", ondelete="CASCADE"), nullable=False
    )
    action_code: Mapped[str] = mapped_column(String(120), nullable=False)
    effect: Mapped[str] = mapped_column(String(10), nullable=False)
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    valid_from: Mapped[datetime | None] = mapped_column(DateTime)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )

    resource: Mapped[BusinessResource] = relationship()
