"""Position, permission dictionary, and IAM audit HTTP endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.auth.router import get_request_context
from app.auth.service import RequestContext
from app.db.dependencies import get_db_session
from app.workflow.repository import WorkflowRepository

from .admin_service import (
    IAMAdministrationActor,
    IAMAdministrationConflict,
    IAMAdministrationPermissionDenied,
    IAMAdministrationValidationError,
)
from .authorization import PermissionService
from .dictionary_admin_service import (
    CreatePermissionCommand,
    CreatePositionCommand,
    IAMAuditFilter,
    IAMAuditQueryService,
    PermissionDictionaryService,
    PositionAdministrationService,
    UpdatePermissionCommand,
    UpdatePositionCommand,
)
from .models import IAMAuditLog, Permission, Position
from .repository import IAMRepository
from .schemas import (
    CreatePermissionRequest,
    CreatePositionRequest,
    IAMAuditLogResponse,
    PermissionResponse,
    PositionResponse,
    PositionStatusRequest,
    UpdatePermissionRequest,
    UpdatePositionRequest,
)
from .service import DuplicateIAMCode, IAMEntityNotFound

router = APIRouter(tags=["iam-dictionaries"])


def get_position_administration_service(
    session: Annotated[Session, Depends(get_db_session)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> PositionAdministrationService:
    repository = IAMRepository(session, context.tenant_id)
    return PositionAdministrationService(
        repository,
        PermissionService(repository),
        WorkflowRepository(session),
    )


def get_permission_dictionary_service(
    session: Annotated[Session, Depends(get_db_session)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> PermissionDictionaryService:
    repository = IAMRepository(session, context.tenant_id)
    return PermissionDictionaryService(repository, PermissionService(repository))


def get_iam_audit_query_service(
    session: Annotated[Session, Depends(get_db_session)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> IAMAuditQueryService:
    repository = IAMRepository(session, context.tenant_id)
    return IAMAuditQueryService(repository, PermissionService(repository))


def _actor(context: RequestContext) -> IAMAdministrationActor:
    return IAMAdministrationActor(context.current_user_id, context.active_org_id)


def _position_response(position: Position) -> PositionResponse:
    return PositionResponse(
        id=position.id,
        position_code=position.position_code,
        position_name=position.position_name,
        is_active=position.is_active,
        membership_count=len(position.membership_links),
    )


def _permission_response(permission: Permission) -> PermissionResponse:
    return PermissionResponse(
        id=permission.id,
        permission_code=permission.permission_code,
        permission_name=permission.permission_name,
        resource_type=permission.resource_type,
        description=permission.description,
        role_count=len(permission.role_links),
    )


def _audit_response(log: IAMAuditLog) -> IAMAuditLogResponse:
    return IAMAuditLogResponse(
        id=log.id,
        entity_type=log.entity_type,
        entity_id=log.entity_id,
        action=log.action,
        operator_id=log.operator_id,
        operator_username=log.operator.username if log.operator else None,
        operator_display_name=log.operator.display_name if log.operator else None,
        payload=log.payload_json,
        created_at=log.created_at,
    )


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


@router.get("/api/positions", response_model=list[PositionResponse])
def list_positions(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        PositionAdministrationService,
        Depends(get_position_administration_service),
    ],
) -> list[PositionResponse]:
    try:
        positions = service.list_positions(_actor(context))
    except IAMAdministrationPermissionDenied as error:
        _raise_http(error)
    return [_position_response(position) for position in positions]


@router.get("/api/positions/{position_id}", response_model=PositionResponse)
def get_position(
    position_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        PositionAdministrationService,
        Depends(get_position_administration_service),
    ],
) -> PositionResponse:
    try:
        position = service.get_position(position_id, _actor(context))
    except (IAMAdministrationPermissionDenied, IAMEntityNotFound) as error:
        _raise_http(error)
    return _position_response(position)


@router.post(
    "/api/positions",
    response_model=PositionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_position(
    command: CreatePositionRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        PositionAdministrationService,
        Depends(get_position_administration_service),
    ],
) -> PositionResponse:
    try:
        position = service.create(
            CreatePositionCommand(**command.model_dump()),
            _actor(context),
        )
    except (
        DuplicateIAMCode,
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
    ) as error:
        _raise_http(error)
    return _position_response(position)


@router.put("/api/positions/{position_id}", response_model=PositionResponse)
def update_position(
    position_id: int,
    command: UpdatePositionRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        PositionAdministrationService,
        Depends(get_position_administration_service),
    ],
) -> PositionResponse:
    try:
        position = service.update(
            position_id,
            UpdatePositionCommand(**command.model_dump()),
            _actor(context),
        )
    except (
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
    ) as error:
        _raise_http(error)
    return _position_response(position)


@router.post(
    "/api/positions/{position_id}/status",
    response_model=PositionResponse,
)
def set_position_status(
    position_id: int,
    command: PositionStatusRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        PositionAdministrationService,
        Depends(get_position_administration_service),
    ],
) -> PositionResponse:
    try:
        position = service.set_active(
            position_id,
            command.is_active,
            _actor(context),
        )
    except (
        IAMAdministrationPermissionDenied,
        IAMEntityNotFound,
    ) as error:
        _raise_http(error)
    return _position_response(position)


@router.delete(
    "/api/positions/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_position(
    position_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        PositionAdministrationService,
        Depends(get_position_administration_service),
    ],
) -> Response:
    try:
        service.delete(position_id, _actor(context))
    except (
        IAMAdministrationConflict,
        IAMAdministrationPermissionDenied,
        IAMEntityNotFound,
    ) as error:
        _raise_http(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/permissions", response_model=list[PermissionResponse])
def list_permissions(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        PermissionDictionaryService,
        Depends(get_permission_dictionary_service),
    ],
) -> list[PermissionResponse]:
    try:
        permissions = service.list_permissions(_actor(context))
    except IAMAdministrationPermissionDenied as error:
        _raise_http(error)
    return [_permission_response(permission) for permission in permissions]


@router.get("/api/permissions/{permission_id}", response_model=PermissionResponse)
def get_permission(
    permission_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        PermissionDictionaryService,
        Depends(get_permission_dictionary_service),
    ],
) -> PermissionResponse:
    try:
        permission = service.get_permission(permission_id, _actor(context))
    except (IAMAdministrationPermissionDenied, IAMEntityNotFound) as error:
        _raise_http(error)
    return _permission_response(permission)


@router.post(
    "/api/permissions",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_permission(
    command: CreatePermissionRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        PermissionDictionaryService,
        Depends(get_permission_dictionary_service),
    ],
) -> PermissionResponse:
    try:
        permission = service.create(
            CreatePermissionCommand(**command.model_dump()),
            _actor(context),
        )
    except (
        DuplicateIAMCode,
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
    ) as error:
        _raise_http(error)
    return _permission_response(permission)


@router.put("/api/permissions/{permission_id}", response_model=PermissionResponse)
def update_permission(
    permission_id: int,
    command: UpdatePermissionRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        PermissionDictionaryService,
        Depends(get_permission_dictionary_service),
    ],
) -> PermissionResponse:
    try:
        permission = service.update(
            permission_id,
            UpdatePermissionCommand(**command.model_dump()),
            _actor(context),
        )
    except (
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
        IAMEntityNotFound,
    ) as error:
        _raise_http(error)
    return _permission_response(permission)


@router.delete(
    "/api/permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_permission(
    permission_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        PermissionDictionaryService,
        Depends(get_permission_dictionary_service),
    ],
) -> Response:
    try:
        service.delete(permission_id, _actor(context))
    except (
        IAMAdministrationConflict,
        IAMAdministrationPermissionDenied,
        IAMEntityNotFound,
    ) as error:
        _raise_http(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/iam/audit-logs", response_model=list[IAMAuditLogResponse])
def list_iam_audit_logs(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        IAMAuditQueryService,
        Depends(get_iam_audit_query_service),
    ],
    entity_type: Annotated[str | None, Query(max_length=40)] = None,
    entity_id: Annotated[int | None, Query(gt=0)] = None,
    action: Annotated[str | None, Query(max_length=40)] = None,
    operator_username: Annotated[str | None, Query(max_length=80)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[IAMAuditLogResponse]:
    try:
        logs = service.list_logs(
            IAMAuditFilter(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                operator_username=operator_username,
                offset=offset,
                limit=limit,
            ),
            _actor(context),
        )
    except (
        IAMAdministrationPermissionDenied,
        IAMAdministrationValidationError,
    ) as error:
        _raise_http(error)
    return [_audit_response(log) for log in logs]
