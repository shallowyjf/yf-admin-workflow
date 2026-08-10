"""In-app notification staging, read receipt, and retry use cases."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from .models import Notification
from .repository import NotificationRepository


class NotificationNotFound(Exception):
    """Raised when a recipient cannot access a notification."""


class NotificationService:
    def __init__(
        self,
        repository: NotificationRepository,
        *,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.repository = repository
        self.clock = clock

    def stage_work_order(
        self,
        user_id: int,
        work_order_id: int,
        event_type: str,
        title: str,
        content: str,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            work_order_id=work_order_id,
            event_type=event_type,
            title=title,
            content=content,
            status="UNREAD",
            delivery_attempts=1,
        )
        self.repository.add(notification)
        return notification

    def list_for_user(self, user_id: int) -> list[Notification]:
        return self.repository.list_for_user(user_id)

    def mark_read(self, notification_id: int, user_id: int) -> Notification:
        notification = self._owned(notification_id, user_id)
        if notification.status != "READ":
            notification.status = "READ"
            notification.read_at = self.clock()
            notification.last_error = None
            self.repository.commit()
            self.repository.refresh(notification)
        return notification

    def retry_failed(self, notification_id: int, user_id: int) -> Notification:
        notification = self._owned(notification_id, user_id)
        if notification.status != "FAILED":
            return notification
        notification.status = "UNREAD"
        notification.delivery_attempts += 1
        notification.last_error = None
        self.repository.commit()
        self.repository.refresh(notification)
        return notification

    def _owned(self, notification_id: int, user_id: int) -> Notification:
        notification = self.repository.get(notification_id)
        if notification is None or notification.user_id != user_id:
            raise NotificationNotFound(
                f"notification not found: {notification_id}"
            )
        return notification
