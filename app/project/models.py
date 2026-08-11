"""Persistence models for city lifeline systems and engineering projects."""

from __future__ import annotations

from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
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
from app.iam.models import Organization, Role, Tenant, User, UserOrganization


class Application(IdTimestampMixin, Base):
    """Stable platform product/system catalog shared by all tenants."""

    __tablename__ = "sys_application"

    application_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    application_name: Mapped[str] = mapped_column(String(160), nullable=False)
    domain_type: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )


class TenantApplication(IdTimestampMixin, Base):
    """A tenant subscription/entrance to one lifeline system."""

    __tablename__ = "sys_tenant_application"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "application_id", name="uq_tenant_application_tenant_app"
        ),
        Index("ix_tenant_application_tenant_id", "tenant_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[int] = mapped_column(
        ForeignKey("sys_application.id", ondelete="RESTRICT"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )

    tenant: Mapped[Tenant] = relationship()
    application: Mapped[Application] = relationship()


class UserApplicationAccess(IdTimestampMixin, Base):
    """Explicit per-user entrance grant to a tenant's lifeline system."""

    __tablename__ = "sys_user_application"
    __table_args__ = (
        UniqueConstraint(
            "tenant_application_id",
            "user_id",
            name="uq_user_application_subscription_user",
        ),
        Index("ix_user_application_user_id", "user_id"),
    )

    tenant_application_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant_application.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="CASCADE"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )

    tenant_application: Mapped[TenantApplication] = relationship()
    user: Mapped[User] = relationship()


class Project(IdTimestampMixin, Base):
    """Engineering project used as the primary data-authorization carrier."""

    __tablename__ = "pm_project"
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_code", name="uq_project_tenant_code"),
        Index("ix_project_tenant_application", "tenant_id", "application_id"),
        Index("ix_project_status", "project_status"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[int] = mapped_column(
        ForeignKey("sys_application.id", ondelete="RESTRICT"), nullable=False
    )
    project_code: Mapped[str] = mapped_column(String(80), nullable=False)
    project_name: Mapped[str] = mapped_column(String(200), nullable=False)
    project_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)

    tenant: Mapped[Tenant] = relationship()
    application: Mapped[Application] = relationship()
    organization_links: Mapped[list[ProjectOrganization]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    members: Mapped[list[ProjectMember]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    milestones: Mapped[list[ProjectMilestone]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectMilestone(IdTimestampMixin, Base):
    """Demo-level weighted milestone used by the I23 progress dashboard."""

    __tablename__ = "pm_project_milestone"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "milestone_code", name="uq_project_milestone_code"
        ),
        Index("ix_project_milestone_project_status", "project_id", "status"),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("pm_project.id", ondelete="CASCADE"), nullable=False
    )
    milestone_code: Mapped[str] = mapped_column(String(80), nullable=False)
    milestone_name: Mapped[str] = mapped_column(String(160), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)

    project: Mapped[Project] = relationship(back_populates="milestones")


class ProjectOrganization(IdTimestampMixin, Base):
    """One real organization participating in a project with a party identity."""

    __tablename__ = "pm_project_org"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "org_id", "party_type", name="uq_project_org_party"
        ),
        Index("ix_project_org_org_id", "org_id"),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("pm_project.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[int] = mapped_column(
        ForeignKey("sys_org.id", ondelete="RESTRICT"), nullable=False
    )
    party_type: Mapped[str] = mapped_column(String(40), nullable=False)
    is_lead: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )

    project: Mapped[Project] = relationship(back_populates="organization_links")
    organization: Mapped[Organization] = relationship()


class ProjectMember(IdTimestampMixin, Base):
    """Project-specific role binding based on a real organization membership."""

    __tablename__ = "pm_project_member"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "user_org_id", "role_id", name="uq_project_member_role"
        ),
        Index("ix_project_member_user_org_id", "user_org_id"),
        Index("ix_project_member_role_id", "role_id"),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("pm_project.id", ondelete="CASCADE"), nullable=False
    )
    user_org_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user_org.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("sys_role.id", ondelete="RESTRICT"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )

    project: Mapped[Project] = relationship(back_populates="members")
    membership: Mapped[UserOrganization] = relationship()
    role: Mapped[Role] = relationship()
