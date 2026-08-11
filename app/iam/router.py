"""Authenticated IAM organization administration endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth.router import get_request_context
from app.auth.service import RequestContext
from app.db.dependencies import get_db_session

from .admin_service import (
    CreateOrganizationCommand,
    IAMAdministrationActor,
    IAMAdministrationConflict,
    IAMAdministrationPermissionDenied,
    IAMAdministrationValidationError,
    OrganizationAdministrationService,
    UpdateOrganizationCommand,
)
from .authorization import PermissionService
from .models import Organization
from .repository import IAMRepository
from .schemas import (
    CreateOrganizationRequest,
    OrganizationResponse,
    OrganizationStatusRequest,
    OrganizationTreeResponse,
    UpdateOrganizationRequest,
)
from .service import DuplicateIAMCode, IAMEntityNotFound

router = APIRouter(prefix="/api/orgs", tags=["iam-organizations"])


def get_organization_administration_service(
    session: Annotated[Session, Depends(get_db_session)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> OrganizationAdministrationService:
    repository = IAMRepository(session, context.tenant_id)
    return OrganizationAdministrationService(
        repository,
        PermissionService(repository),
    )


def _actor(context: RequestContext) -> IAMAdministrationActor:
    return IAMAdministrationActor(context.current_user_id, context.active_org_id)


def _response(organization: Organization) -> OrganizationResponse:
    return OrganizationResponse.model_validate(organization, from_attributes=True)


def _raise_http(error: Exception) -> None:
    if isinstance(error, IAMAdministrationPermissionDenied):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(error, IAMEntityNotFound):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, IAMAdministrationValidationError):
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        status_code = status.HTTP_409_CONFLICT
    raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.get("", response_model=list[OrganizationResponse])
def list_organizations(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        OrganizationAdministrationService,
        Depends(get_organization_administration_service),
    ],
) -> list[OrganizationResponse]:
    try:
        organizations = service.list_organizations(_actor(context))
    except IAMAdministrationPermissionDenied as error:
        _raise_http(error)
    return [_response(organization) for organization in organizations]


@router.get("/tree", response_model=list[OrganizationTreeResponse])
def organization_tree(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        OrganizationAdministrationService,
        Depends(get_organization_administration_service),
    ],
) -> list[OrganizationTreeResponse]:
    try:
        organizations = service.list_organizations(_actor(context))
    except IAMAdministrationPermissionDenied as error:
        _raise_http(error)
    nodes = {
        item.id: OrganizationTreeResponse(
            **_response(item).model_dump(),
            children=[],
        )
        for item in organizations
    }
    roots = []
    for organization in organizations:
        node = nodes[organization.id]
        if organization.parent_id is None:
            roots.append(node)
        else:
            nodes[organization.parent_id].children.append(node)
    return roots


@router.get("/{organization_id}", response_model=OrganizationResponse)
def get_organization(
    organization_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        OrganizationAdministrationService,
        Depends(get_organization_administration_service),
    ],
) -> OrganizationResponse:
    try:
        organization = service.get_organization(organization_id, _actor(context))
    except (IAMAdministrationPermissionDenied, IAMEntityNotFound) as error:
        _raise_http(error)
    return _response(organization)


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    command: CreateOrganizationRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        OrganizationAdministrationService,
        Depends(get_organization_administration_service),
    ],
) -> OrganizationResponse:
    try:
        organization = service.create(
            CreateOrganizationCommand(**command.model_dump()),
            _actor(context),
        )
    except (
        DuplicateIAMCode,
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
    ) as error:
        _raise_http(error)
    return _response(organization)


@router.put("/{organization_id}", response_model=OrganizationResponse)
def update_organization(
    organization_id: int,
    command: UpdateOrganizationRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        OrganizationAdministrationService,
        Depends(get_organization_administration_service),
    ],
) -> OrganizationResponse:
    try:
        organization = service.update(
            organization_id,
            UpdateOrganizationCommand(**command.model_dump()),
            _actor(context),
        )
    except (
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
    ) as error:
        _raise_http(error)
    return _response(organization)


@router.post("/{organization_id}/status", response_model=OrganizationResponse)
def set_organization_status(
    organization_id: int,
    command: OrganizationStatusRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        OrganizationAdministrationService,
        Depends(get_organization_administration_service),
    ],
) -> OrganizationResponse:
    try:
        organization = service.set_active(
            organization_id,
            command.is_active,
            _actor(context),
        )
    except (
        IAMAdministrationConflict,
        IAMAdministrationPermissionDenied,
        IAMEntityNotFound,
    ) as error:
        _raise_http(error)
    return _response(organization)


@router.delete("/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(
    organization_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        OrganizationAdministrationService,
        Depends(get_organization_administration_service),
    ],
) -> Response:
    try:
        service.delete(organization_id, _actor(context))
    except (
        IAMAdministrationConflict,
        IAMAdministrationPermissionDenied,
        IAMEntityNotFound,
    ) as error:
        _raise_http(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
