"""Authenticated notification inbox endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.router import get_request_context
from app.auth.service import RequestContext
from app.db.dependencies import get_db_session

from .repository import NotificationRepository
from .schemas import NotificationResponse
from .service import NotificationNotFound, NotificationService

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def get_notification_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> NotificationService:
    return NotificationService(NotificationRepository(session))


@router.get("", response_model=list[NotificationResponse])
def list_notifications(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> list[NotificationResponse]:
    return [
        NotificationResponse.model_validate(item, from_attributes=True)
        for item in service.list_for_user(context.current_user_id)
    ]


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(
    notification_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> NotificationResponse:
    try:
        notification = service.mark_read(notification_id, context.current_user_id)
    except NotificationNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    return NotificationResponse.model_validate(notification, from_attributes=True)
