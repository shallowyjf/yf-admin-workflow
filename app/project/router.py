"""Authenticated project administration and authorization APIs."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth.router import get_request_context
from app.auth.service import RequestContext
from app.db.dependencies import get_db_session
from app.iam.authorization import PermissionService
from app.iam.repository import IAMRepository

from .repository import ProjectRepository
from .schemas import (
    AuthorizationExplanationResponse,
    CreateProjectRequest,
    LifelineStructureResponse,
    ProjectResponse,
    ReplaceProjectMembersRequest,
    ReplaceProjectOrganizationsRequest,
    ReplaceUserApplicationsRequest,
    UpdateProjectRequest,
    UserApplicationAccessResponse,
)
from .service import (
    CreateProjectCommand,
    ProjectActor,
    ProjectConflict,
    ProjectMemberConfiguration,
    ProjectNotFound,
    ProjectOrganizationConfiguration,
    ProjectPermissionDenied,
    ProjectService,
    ProjectValidationError,
    UpdateProjectCommand,
)

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


def _actor(context: RequestContext) -> ProjectActor:
    return ProjectActor(context.current_user_id, context.active_org_id)


def _project_response(service: ProjectService, project) -> ProjectResponse:
    return ProjectResponse.model_validate(service.project_item(project))


def _raise_http(error: Exception) -> None:
    if isinstance(error, ProjectPermissionDenied):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(error, ProjectNotFound):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, ProjectValidationError):
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        status_code = status.HTTP_409_CONFLICT
    raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.get("/structure", response_model=LifelineStructureResponse)
def lifeline_structure(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> LifelineStructureResponse:
    try:
        structure = service.structure(_actor(context))
    except ProjectPermissionDenied as error:
        _raise_http(error)
    return LifelineStructureResponse.model_validate(structure)


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> list[ProjectResponse]:
    try:
        projects = service.list_projects(_actor(context))
    except ProjectPermissionDenied as error:
        _raise_http(error)
    return [_project_response(service, project) for project in projects]


@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    command: CreateProjectRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    try:
        project = service.create(
            CreateProjectCommand(**command.model_dump()), _actor(context)
        )
    except (ProjectPermissionDenied, ProjectValidationError, ProjectConflict) as error:
        _raise_http(error)
    return _project_response(service, project)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    try:
        project = service.get_project(project_id, _actor(context))
    except (ProjectPermissionDenied, ProjectNotFound) as error:
        _raise_http(error)
    return _project_response(service, project)


@router.put("/projects/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int,
    command: UpdateProjectRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    try:
        project = service.update(
            project_id,
            UpdateProjectCommand(**command.model_dump()),
            _actor(context),
        )
    except (ProjectPermissionDenied, ProjectNotFound, ProjectValidationError) as error:
        _raise_http(error)
    return _project_response(service, project)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> Response:
    try:
        service.delete(project_id, _actor(context))
    except (ProjectPermissionDenied, ProjectNotFound, ProjectConflict) as error:
        _raise_http(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/projects/{project_id}/organizations", response_model=ProjectResponse)
def replace_project_organizations(
    project_id: int,
    command: ReplaceProjectOrganizationsRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    configurations = tuple(
        ProjectOrganizationConfiguration(**item.model_dump())
        for item in command.organizations
    )
    try:
        project = service.replace_organizations(
            project_id, configurations, _actor(context)
        )
    except (
        ProjectPermissionDenied,
        ProjectNotFound,
        ProjectValidationError,
        ProjectConflict,
    ) as error:
        _raise_http(error)
    return _project_response(service, project)


@router.put("/projects/{project_id}/members", response_model=ProjectResponse)
def replace_project_members(
    project_id: int,
    command: ReplaceProjectMembersRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    configurations = tuple(
        ProjectMemberConfiguration(**item.model_dump()) for item in command.members
    )
    try:
        project = service.replace_members(
            project_id, configurations, _actor(context)
        )
    except (
        ProjectPermissionDenied,
        ProjectNotFound,
        ProjectValidationError,
    ) as error:
        _raise_http(error)
    return _project_response(service, project)


@router.get(
    "/projects/{project_id}/authorization-explain",
    response_model=AuthorizationExplanationResponse,
)
def explain_project_authorization(
    project_id: int,
    subject_user_id: int,
    permission_code: str,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> AuthorizationExplanationResponse:
    try:
        explanation = service.explain_authorization(
            project_id,
            subject_user_id,
            permission_code,
            _actor(context),
        )
    except (
        ProjectPermissionDenied,
        ProjectNotFound,
        ProjectValidationError,
    ) as error:
        _raise_http(error)
    return AuthorizationExplanationResponse.model_validate(explanation)


@router.put(
    "/users/{user_id}/applications",
    response_model=list[UserApplicationAccessResponse],
)
def replace_user_application_accesses(
    user_id: int,
    command: ReplaceUserApplicationsRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> list[UserApplicationAccessResponse]:
    try:
        applications = service.replace_user_application_accesses(
            user_id,
            tuple(command.application_ids),
            _actor(context),
        )
    except (ProjectPermissionDenied, ProjectValidationError) as error:
        _raise_http(error)
    return [
        UserApplicationAccessResponse(
            id=application.id,
            application_code=application.application_code,
            application_name=application.application_name,
        )
        for application in applications
    ]
