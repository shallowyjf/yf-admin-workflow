"""Notification HTTP response schemas."""

from datetime import datetime

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: int
    work_order_id: int | None
    event_type: str
    title: str
    content: str
    status: str
    delivery_attempts: int
    last_error: str | None
    read_at: datetime | None
    created_at: datetime
