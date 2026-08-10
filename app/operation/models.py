"""User-owned operational saved views."""

from sqlalchemy import JSON, Boolean, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import IdTimestampMixin


class SavedView(IdTimestampMixin, Base):
    __tablename__ = "sys_saved_view"
    __table_args__ = (
        UniqueConstraint("user_id", "module", "name", name="uq_saved_view_owner_name"),
        Index("ix_saved_view_user_module", "user_id", "module"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="CASCADE"), nullable=False
    )
    module: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    filters_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
