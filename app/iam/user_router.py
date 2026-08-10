"""Authenticated user lifecycle and organization membership endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth.repository import AuthRepository
from app.auth.router import get_request_context
from app.auth.service import AuthSessionRevocationService, RequestContext
from app.db.dependencies import get_db_session

from .admin_service import (
    IAMAdministrationActor,
    IAMAdministrationConflict,
    IAMAdministrationPermissionDenied,
    IAMAdministrationValidationError,
)
from .authorization import PermissionService
from .models import User
from .repository import IAMRepository
from .schemas import (
    CreateUserRequest,
    ReplaceUserMembershipsRequest,
    ResetUserPasswordRequest,
    UpdateUserRequest,
    UserMembershipResponse,
    UserResponse,
    UserStatusRequest,
)
from .service import DuplicateIAMCode, IAMEntityNotFound
from .user_admin_service import (
    CreateUserCommand,
    MembershipConfiguration,
    UpdateUserCommand,
    UserAdministrationService,
)

router = APIRouter(prefix="/api/users", tags=["iam-users"])


def get_user_administration_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> UserAdministrationService:
    repository = IAMRepository(session)
    return UserAdministrationService(
        repository,
        PermissionService(repository),
        AuthSessionRevocationService(AuthRepository(session)),
    )


def _actor(context: RequestContext) -> IAMAdministrationActor:
    return IAMAdministrationActor(context.current_user_id, context.active_org_id)


def _response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        phone=user.phone,
        is_active=user.is_active,
        memberships=[
            UserMembershipResponse(
                id=membership.id,
                org_id=membership.org_id,
                org_code=membership.organization.org_code,
                org_name=membership.organization.org_name,
                is_primary=membership.is_primary,
                is_active=membership.is_active,
                role_codes=sorted(
                    link.role.role_code for link in membership.role_links
                ),
                position_codes=sorted(
                    link.position.position_code
                    for link in membership.position_links
                ),
            )
            for membership in sorted(
                user.memberships,
                key=lambda item: (
                    not item.is_primary,
                    item.organization.sort_no,
                    item.id,
                ),
            )
        ],
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


@router.get("", response_model=list[UserResponse])
def list_users(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        UserAdministrationService,
        Depends(get_user_administration_service),
    ],
) -> list[UserResponse]:
    try:
        users = service.list_users(_actor(context))
    except IAMAdministrationPermissionDenied as error:
        _raise_http(error)
    return [_response(user) for user in users]


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        UserAdministrationService,
        Depends(get_user_administration_service),
    ],
) -> UserResponse:
    try:
        user = service.get_user(user_id, _actor(context))
    except (IAMAdministrationPermissionDenied, IAMEntityNotFound) as error:
        _raise_http(error)
    return _response(user)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    command: CreateUserRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        UserAdministrationService,
        Depends(get_user_administration_service),
    ],
) -> UserResponse:
    try:
        user = service.create(
            CreateUserCommand(**command.model_dump()),
            _actor(context),
        )
    except (
        DuplicateIAMCode,
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
    ) as error:
        _raise_http(error)
    return _response(user)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    command: UpdateUserRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        UserAdministrationService,
        Depends(get_user_administration_service),
    ],
) -> UserResponse:
    try:
        user = service.update(
            user_id,
            UpdateUserCommand(**command.model_dump()),
            _actor(context),
        )
    except (
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
    ) as error:
        _raise_http(error)
    return _response(user)


@router.post("/{user_id}/status", response_model=UserResponse)
def set_user_status(
    user_id: int,
    command: UserStatusRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        UserAdministrationService,
        Depends(get_user_administration_service),
    ],
) -> UserResponse:
    try:
        user = service.set_active(user_id, command.is_active, _actor(context))
    except (
        IAMAdministrationConflict,
        IAMAdministrationPermissionDenied,
        IAMEntityNotFound,
    ) as error:
        _raise_http(error)
    return _response(user)


@router.post("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def reset_user_password(
    user_id: int,
    command: ResetUserPasswordRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        UserAdministrationService,
        Depends(get_user_administration_service),
    ],
) -> Response:
    try:
        service.reset_password(user_id, command.new_password, _actor(context))
    except (
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
    ) as error:
        _raise_http(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{user_id}/memberships", response_model=UserResponse)
def replace_user_memberships(
    user_id: int,
    command: ReplaceUserMembershipsRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        UserAdministrationService,
        Depends(get_user_administration_service),
    ],
) -> UserResponse:
    configurations = tuple(
        MembershipConfiguration(
            org_code=item.org_code,
            is_primary=item.is_primary,
            is_active=item.is_active,
            role_codes=tuple(item.role_codes),
            position_codes=tuple(item.position_codes),
        )
        for item in command.memberships
    )
    try:
        user = service.replace_memberships(
            user_id,
            configurations,
            _actor(context),
        )
    except (
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
    ) as error:
        _raise_http(error)
    return _response(user)
