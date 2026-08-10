"""Persistent in-app notification and delivery state."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import IdTimestampMixin


class Notification(IdTimestampMixin, Base):
    __tablename__ = "sys_notification"
    __table_args__ = (
        Index("ix_sys_notification_user_status", "user_id", "status"),
        Index("ix_sys_notification_work_order_id", "work_order_id"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    work_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("wo_work_order.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="UNREAD",
        server_default=text("'UNREAD'"),
    )
    delivery_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    last_error: Mapped[str | None] = mapped_column(String(500))
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
