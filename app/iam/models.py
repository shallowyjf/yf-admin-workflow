"""IAM and authorization persistence models.

Roles deliberately bind to UserOrganization rather than User so one user can
carry different responsibilities in different organizations.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
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


class Tenant(IdTimestampMixin, Base):
    __tablename__ = "sys_tenant"

    tenant_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    tenant_name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )


class User(IdTimestampMixin, Base):
    __tablename__ = "sys_user"
    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="uq_sys_user_tenant_username"),
        Index("ix_sys_user_tenant_id", "tenant_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant.id", ondelete="RESTRICT"),
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    username: Mapped[str] = mapped_column(String(80), nullable=False)
    login_name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )

    memberships: Mapped[list[UserOrganization]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    tenant: Mapped[Tenant] = relationship()


class Organization(IdTimestampMixin, Base):
    __tablename__ = "sys_org"
    __table_args__ = (
        UniqueConstraint("tenant_id", "org_code", name="uq_sys_org_tenant_code"),
        Index("ix_sys_org_tenant_id", "tenant_id"),
        Index("ix_sys_org_parent_id", "parent_id"),
        Index("ix_sys_org_org_path", "org_path"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant.id", ondelete="RESTRICT"),
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("sys_org.id", ondelete="RESTRICT")
    )
    org_code: Mapped[str] = mapped_column(String(80), nullable=False)
    org_name: Mapped[str] = mapped_column(String(160), nullable=False)
    org_type: Mapped[str | None] = mapped_column(String(40))
    org_path: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_no: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )

    parent: Mapped[Organization | None] = relationship(
        remote_side="Organization.id",
        back_populates="children",
    )
    children: Mapped[list[Organization]] = relationship(back_populates="parent")
    memberships: Mapped[list[UserOrganization]] = relationship(
        back_populates="organization"
    )
    tenant: Mapped[Tenant] = relationship()


class IAMAuditLog(IdTimestampMixin, Base):
    __tablename__ = "sys_iam_audit_log"
    __table_args__ = (
        Index("ix_sys_iam_audit_log_tenant_id", "tenant_id"),
        Index("ix_sys_iam_audit_entity", "entity_type", "entity_id"),
        Index("ix_sys_iam_audit_operator_id", "operator_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant.id", ondelete="RESTRICT"),
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    operator_id: Mapped[int | None] = mapped_column(
        ForeignKey("sys_user.id", ondelete="SET NULL")
    )
    payload_json: Mapped[dict | None] = mapped_column(JSON)

    operator: Mapped[User | None] = relationship()


class Role(IdTimestampMixin, Base):
    __tablename__ = "sys_role"
    __table_args__ = (
        UniqueConstraint("tenant_id", "role_code", name="uq_sys_role_tenant_code"),
        Index("ix_sys_role_tenant_id", "tenant_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant.id", ondelete="RESTRICT"),
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    role_code: Mapped[str] = mapped_column(String(80), nullable=False)
    role_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role_type: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )

    membership_links: Mapped[list[UserOrganizationRole]] = relationship(
        back_populates="role"
    )
    permission_links: Mapped[list[RolePermission]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
    )
    data_scopes: Mapped[list[RoleDataScope]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
    )
    tenant: Mapped[Tenant] = relationship()


class Permission(IdTimestampMixin, Base):
    __tablename__ = "sys_permission"

    permission_code: Mapped[str] = mapped_column(
        String(120), unique=True, nullable=False
    )
    permission_name: Mapped[str] = mapped_column(String(160), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(String)

    role_links: Mapped[list[RolePermission]] = relationship(
        back_populates="permission",
        cascade="all, delete-orphan",
    )


class RolePermission(IdTimestampMixin, Base):
    __tablename__ = "sys_role_permission"
    __table_args__ = (
        UniqueConstraint(
            "role_id",
            "permission_id",
            name="uq_sys_role_permission_role_permission",
        ),
        Index("ix_sys_role_permission_permission_id", "permission_id"),
    )

    role_id: Mapped[int] = mapped_column(
        ForeignKey("sys_role.id", ondelete="CASCADE"),
        nullable=False,
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("sys_permission.id", ondelete="CASCADE"),
        nullable=False,
    )

    role: Mapped[Role] = relationship(back_populates="permission_links")
    permission: Mapped[Permission] = relationship(back_populates="role_links")


class RoleDataScope(IdTimestampMixin, Base):
    __tablename__ = "sys_role_data_scope"
    __table_args__ = (
        UniqueConstraint(
            "role_id",
            "permission_code",
            name="uq_sys_role_data_scope_role_permission",
        ),
    )

    role_id: Mapped[int] = mapped_column(
        ForeignKey("sys_role.id", ondelete="CASCADE"),
        nullable=False,
    )
    permission_code: Mapped[str] = mapped_column(String(120), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_config: Mapped[dict | None] = mapped_column(JSON)

    role: Mapped[Role] = relationship(back_populates="data_scopes")


class UserOrganization(IdTimestampMixin, Base):
    __tablename__ = "sys_user_org"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_sys_user_org_user_org"),
        Index("ix_sys_user_org_org_id", "org_id"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_id: Mapped[int] = mapped_column(
        ForeignKey("sys_org.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )
    joined_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="memberships")
    role_links: Mapped[list[UserOrganizationRole]] = relationship(
        back_populates="membership",
        cascade="all, delete-orphan",
    )


class UserOrganizationRole(IdTimestampMixin, Base):
    __tablename__ = "sys_user_org_role"
    __table_args__ = (
        UniqueConstraint(
            "user_org_id",
            "role_id",
            name="uq_sys_user_org_role_membership_role",
        ),
        Index("ix_sys_user_org_role_role_id", "role_id"),
    )

    user_org_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user_org.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("sys_role.id", ondelete="CASCADE"),
        nullable=False,
    )

    membership: Mapped[UserOrganization] = relationship(back_populates="role_links")
    role: Mapped[Role] = relationship(back_populates="membership_links")
