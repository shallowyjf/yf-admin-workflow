"""Authenticated saved-view endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth.router import get_request_context
from app.auth.service import RequestContext
from app.db.dependencies import get_db_session

from .repository import SavedViewRepository
from .schemas import SavedViewResponse, SaveViewRequest
from .service import SavedViewError, SavedViewService

router = APIRouter(prefix="/api/saved-views", tags=["operations"])


def get_saved_view_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> SavedViewService:
    return SavedViewService(SavedViewRepository(session))


@router.get("", response_model=list[SavedViewResponse])
def list_saved_views(
    module: str,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[SavedViewService, Depends(get_saved_view_service)],
) -> list[SavedViewResponse]:
    try:
        views = service.list(context.current_user_id, module)
    except SavedViewError as error:
        raise HTTPException(422, str(error)) from error
    return [SavedViewResponse.model_validate(item, from_attributes=True) for item in views]


@router.post("", response_model=SavedViewResponse)
def save_view(
    command: SaveViewRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[SavedViewService, Depends(get_saved_view_service)],
) -> SavedViewResponse:
    try:
        view = service.save(
            context.current_user_id,
            command.module,
            command.name,
            command.filters,
            command.is_default,
        )
    except SavedViewError as error:
        raise HTTPException(422, str(error)) from error
    return SavedViewResponse.model_validate(view, from_attributes=True)


@router.delete("/{saved_view_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_view(
    saved_view_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[SavedViewService, Depends(get_saved_view_service)],
) -> Response:
    try:
        service.delete(context.current_user_id, saved_view_id)
    except SavedViewError as error:
        raise HTTPException(404, str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
