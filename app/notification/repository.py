"""Notification persistence operations."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Notification


class NotificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, notification: Notification) -> None:
        self.session.add(notification)

    def get(self, notification_id: int) -> Notification | None:
        return self.session.get(Notification, notification_id)

    def list_for_user(self, user_id: int, limit: int = 100) -> list[Notification]:
        return list(
            self.session.scalars(
                select(Notification)
                .where(Notification.user_id == user_id)
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(limit)
            )
        )

    def commit(self) -> None:
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def refresh(self, notification: Notification) -> None:
        self.session.refresh(notification)
