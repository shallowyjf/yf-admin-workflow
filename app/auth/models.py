"""Server-side authentication session model."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import IdTimestampMixin
from app.iam.models import Organization, User


class AuthSession(IdTimestampMixin, Base):
    __tablename__ = "sys_auth_session"
    __table_args__ = (Index("ix_sys_auth_session_expires_at", "expires_at"),)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    active_org_id: Mapped[int] = mapped_column(
        ForeignKey("sys_org.id", ondelete="RESTRICT"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped[User] = relationship()
    active_organization: Mapped[Organization] = relationship()
