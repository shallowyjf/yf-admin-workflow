"""Authenticated role lifecycle and atomic authorization endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.router import get_request_context
from app.auth.service import RequestContext
from app.db.dependencies import get_db_session

from .admin_service import (
    IAMAdministrationActor,
    IAMAdministrationConflict,
    IAMAdministrationPermissionDenied,
    IAMAdministrationValidationError,
)
from .authorization import DataScopeType, PermissionService
from .models import Role
from .repository import IAMRepository
from .role_admin_service import (
    CreateRoleCommand,
    PermissionScopeConfiguration,
    RoleAdministrationService,
    UpdateRoleCommand,
)
from .schemas import (
    CreateRoleRequest,
    ReplaceRoleAuthorizationRequest,
    RolePermissionScopeResponse,
    RoleResponse,
    RoleStatusRequest,
    UpdateRoleRequest,
)
from .service import DuplicateIAMCode, IAMEntityNotFound

router = APIRouter(prefix="/api/roles", tags=["iam-roles"])


def get_role_administration_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> RoleAdministrationService:
    repository = IAMRepository(session)
    return RoleAdministrationService(repository, PermissionService(repository))


def _actor(context: RequestContext) -> IAMAdministrationActor:
    return IAMAdministrationActor(context.current_user_id, context.active_org_id)


def _response(role: Role, repository: IAMRepository) -> RoleResponse:
    organizations = {
        item.id: item.org_code for item in repository.list_organizations()
    }
    scopes = {scope.permission_code: scope for scope in role.data_scopes}
    authorization: list[RolePermissionScopeResponse] = []
    for link in sorted(
        role.permission_links,
        key=lambda item: item.permission.permission_code,
    ):
        permission = link.permission
        scope = scopes.get(permission.permission_code)
        if scope is None:
            continue
        org_ids = (
            scope.scope_config.get("org_ids", [])
            if isinstance(scope.scope_config, dict)
            else []
        )
        authorization.append(
            RolePermissionScopeResponse(
                permission_code=permission.permission_code,
                permission_name=permission.permission_name,
                scope_type=DataScopeType(scope.scope_type),
                custom_org_codes=[
                    organizations[org_id]
                    for org_id in org_ids
                    if org_id in organizations
                ],
            )
        )
    return RoleResponse(
        id=role.id,
        role_code=role.role_code,
        role_name=role.role_name,
        role_type=role.role_type,
        is_active=role.is_active,
        authorization=authorization,
    )


def _raise_http(error: Exception) -> None:
    if isinstance(error, IAMAdministrationPermissionDenied):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(error, IAMEntityNotFound):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, IAMAdministrationValidationError):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        status_code = status.HTTP_409_CONFLICT
    raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.get("", response_model=list[RoleResponse])
def list_roles(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        RoleAdministrationService,
        Depends(get_role_administration_service),
    ],
) -> list[RoleResponse]:
    try:
        roles = service.list_roles(_actor(context))
    except IAMAdministrationPermissionDenied as error:
        _raise_http(error)
    return [_response(role, service.repository) for role in roles]


@router.get("/{role_id}", response_model=RoleResponse)
def get_role(
    role_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        RoleAdministrationService,
        Depends(get_role_administration_service),
    ],
) -> RoleResponse:
    try:
        role = service.get_role(role_id, _actor(context))
    except (IAMAdministrationPermissionDenied, IAMEntityNotFound) as error:
        _raise_http(error)
    return _response(role, service.repository)


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    command: CreateRoleRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        RoleAdministrationService,
        Depends(get_role_administration_service),
    ],
) -> RoleResponse:
    try:
        role = service.create(
            CreateRoleCommand(**command.model_dump()),
            _actor(context),
        )
    except (
        DuplicateIAMCode,
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
    ) as error:
        _raise_http(error)
    return _response(role, service.repository)


@router.put("/{role_id}", response_model=RoleResponse)
def update_role(
    role_id: int,
    command: UpdateRoleRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        RoleAdministrationService,
        Depends(get_role_administration_service),
    ],
) -> RoleResponse:
    try:
        role = service.update(
            role_id,
            UpdateRoleCommand(**command.model_dump()),
            _actor(context),
        )
    except (
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
    ) as error:
        _raise_http(error)
    return _response(role, service.repository)


@router.post("/{role_id}/status", response_model=RoleResponse)
def set_role_status(
    role_id: int,
    command: RoleStatusRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        RoleAdministrationService,
        Depends(get_role_administration_service),
    ],
) -> RoleResponse:
    try:
        role = service.set_active(role_id, command.is_active, _actor(context))
    except (
        IAMAdministrationConflict,
        IAMAdministrationPermissionDenied,
        IAMEntityNotFound,
    ) as error:
        _raise_http(error)
    return _response(role, service.repository)


@router.put("/{role_id}/authorization", response_model=RoleResponse)
def replace_role_authorization(
    role_id: int,
    command: ReplaceRoleAuthorizationRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        RoleAdministrationService,
        Depends(get_role_administration_service),
    ],
) -> RoleResponse:
    configurations = tuple(
        PermissionScopeConfiguration(
            permission_code=item.permission_code,
            scope_type=item.scope_type,
            custom_org_codes=tuple(item.custom_org_codes),
        )
        for item in command.permissions
    )
    try:
        role = service.replace_authorization(
            role_id,
            configurations,
            _actor(context),
        )
    except (
        IAMAdministrationConflict,
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
    ) as error:
        _raise_http(error)
    return _response(role, service.repository)
