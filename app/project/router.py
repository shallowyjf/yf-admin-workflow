"""Authenticated API for the city lifeline permission demonstration."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.router import get_request_context
from app.auth.service import RequestContext
from app.db.dependencies import get_db_session
from app.iam.authorization import PermissionService
from app.iam.repository import IAMRepository

from .repository import ProjectRepository
from .schemas import LifelineStructureResponse
from .service import ProjectActor, ProjectPermissionDenied, ProjectService

router = APIRouter(prefix="/api/lifeline", tags=["city-lifeline"])


def get_project_service(
    session: Annotated[Session, Depends(get_db_session)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> ProjectService:
    iam_repository = IAMRepository(session, context.tenant_id)
    return ProjectService(
        ProjectRepository(session, context.tenant_id),
        PermissionService(iam_repository),
    )


@router.get("/structure", response_model=LifelineStructureResponse)
def lifeline_structure(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> LifelineStructureResponse:
    try:
        structure = service.structure(
            ProjectActor(context.current_user_id, context.active_org_id)
        )
    except ProjectPermissionDenied as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(error)
        ) from error
    return LifelineStructureResponse.model_validate(structure)
