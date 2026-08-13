"""Server-side authentication session model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import IdTimestampMixin
from app.iam.models import Organization, Tenant, User


class PlatformUser(IdTimestampMixin, Base):
    """Platform-level identity that can select a city tenant."""

    __tablename__ = "sys_platform_user"

    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )


class PlatformSession(IdTimestampMixin, Base):
    """Independent root session; it never carries tenant business permissions."""

    __tablename__ = "sys_platform_session"
    __table_args__ = (
        Index("ix_platform_session_expires_at", "expires_at"),
    )

    platform_user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_platform_user.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)

    platform_user: Mapped[PlatformUser] = relationship()


class AuthSession(IdTimestampMixin, Base):
    __tablename__ = "sys_auth_session"
    __table_args__ = (
        Index("ix_sys_auth_session_expires_at", "expires_at"),
        Index("ix_sys_auth_session_tenant_id", "tenant_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant.id", ondelete="CASCADE"),
        nullable=False,
        default=1,
        server_default="1",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    active_org_id: Mapped[int] = mapped_column(
        ForeignKey("sys_org.id", ondelete="RESTRICT"),
        nullable=False,
    )
    active_application_id: Mapped[int | None] = mapped_column(
        ForeignKey("sys_application.id", ondelete="SET NULL")
    )
    active_project_id: Mapped[int | None] = mapped_column(
        ForeignKey("pm_project.id", ondelete="SET NULL")
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped[User] = relationship()
    tenant: Mapped[Tenant] = relationship()
    active_organization: Mapped[Organization] = relationship()
