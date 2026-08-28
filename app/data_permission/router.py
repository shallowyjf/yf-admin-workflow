"""Authenticated APIs for application roles and governed data resources."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.router import get_request_context
from app.auth.service import RequestContext
from app.db.dependencies import get_db_session
from app.iam.authorization import PermissionService
from app.iam.repository import IAMRepository

from .models import BusinessResource, DataSpace
from .repository import DataPermissionRepository
from .schemas import (
    AuthorizationExplanationResponse,
    CreateDataResourceRequest,
    CreateDataSpaceRequest,
    CreateResourcePolicyRequest,
    DataResourceResponse,
    DataSpaceResponse,
    GrantApplicationRoleRequest,
)
from .service import (
    DataActor,
    DataPermissionDenied,
    DataPermissionService,
    DataPermissionValidationError,
    DataResourceNotFound,
    resource_item,
)

router = APIRouter(prefix="/api/data-permissions", tags=["data-permissions"])


def get_data_permission_service(
    session: Annotated[Session, Depends(get_db_session)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> DataPermissionService:
    repository = DataPermissionRepository(session, context.tenant_id)
    return DataPermissionService(
        repository,
        PermissionService(IAMRepository(session, context.tenant_id)),
    )


def _actor(context: RequestContext) -> DataActor:
    return DataActor(context.current_user_id, context.active_org_id)


def _raise_http(error: Exception) -> None:
    if isinstance(error, DataPermissionDenied):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(error, DataResourceNotFound):
        status_code = status.HTTP_404_NOT_FOUND
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.get("/spaces", response_model=list[DataSpaceResponse])
def list_spaces(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[DataPermissionService, Depends(get_data_permission_service)],
    application_id: int | None = None,
) -> list[DataSpaceResponse]:
    spaces = service.list_visible_spaces(_actor(context), application_id)
    return [DataSpaceResponse.model_validate(item) for item in spaces]


@router.get("/resources", response_model=list[DataResourceResponse])
def list_resources(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[DataPermissionService, Depends(get_data_permission_service)],
    application_id: int | None = None,
    action_code: str = "data:resource:view",
) -> list[DataResourceResponse]:
    return [
        DataResourceResponse.model_validate(resource_item(item))
        for item in service.list_resources(
            _actor(context), application_id=application_id, action_code=action_code
        )
    ]


@router.get("/resources/{resource_id}", response_model=DataResourceResponse)
def get_resource(
    resource_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[DataPermissionService, Depends(get_data_permission_service)],
) -> DataResourceResponse:
    try:
        resource = service.get_resource(
            resource_id, "data:resource:view", _actor(context)
        )
    except (DataPermissionDenied, DataResourceNotFound) as error:
        _raise_http(error)
    return DataResourceResponse.model_validate(resource_item(resource))


@router.get(
    "/resources/{resource_id}/authorization-explain",
    response_model=AuthorizationExplanationResponse,
)
def explain_resource_authorization(
    resource_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[DataPermissionService, Depends(get_data_permission_service)],
    action_code: str = "data:resource:view",
) -> AuthorizationExplanationResponse:
    try:
        explanation = service.explain(resource_id, action_code, _actor(context))
    except DataResourceNotFound as error:
        _raise_http(error)
    return AuthorizationExplanationResponse.model_validate(explanation)


@router.post("/spaces", response_model=DataSpaceResponse, status_code=201)
def create_space(
    command: CreateDataSpaceRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[DataPermissionService, Depends(get_data_permission_service)],
) -> DataSpaceResponse:
    try:
        space = service.create_space(
            DataSpace(tenant_id=context.tenant_id, **command.model_dump()),
            _actor(context),
        )
    except (DataPermissionDenied, DataPermissionValidationError) as error:
        _raise_http(error)
    return DataSpaceResponse.model_validate(space)


@router.post("/resources", response_model=DataResourceResponse, status_code=201)
def create_resource(
    command: CreateDataResourceRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[DataPermissionService, Depends(get_data_permission_service)],
) -> DataResourceResponse:
    try:
        resource = service.create_resource(
            BusinessResource(tenant_id=context.tenant_id, **command.model_dump()),
            _actor(context),
        )
        resource = service.repository.get_resource(resource.id)
        assert resource is not None
    except (DataPermissionDenied, DataPermissionValidationError) as error:
        _raise_http(error)
    return DataResourceResponse.model_validate(resource_item(resource))


@router.put("/applications/{application_id}/roles", status_code=204)
def grant_application_role(
    application_id: int,
    command: GrantApplicationRoleRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[DataPermissionService, Depends(get_data_permission_service)],
) -> None:
    membership = service.repository.get_membership(command.user_org_id)
    role = service.repository.get_role(command.role_code)
    if membership is None or role is None:
        _raise_http(DataPermissionValidationError("成员关系或应用角色不存在"))
    try:
        service.grant_application_role(application_id, membership, role, _actor(context))
    except (DataPermissionDenied, DataPermissionValidationError) as error:
        _raise_http(error)


@router.post("/resources/{resource_id}/policies", status_code=204)
def create_policy(
    resource_id: int,
    command: CreateResourcePolicyRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[DataPermissionService, Depends(get_data_permission_service)],
) -> None:
    role = service.repository.get_role(command.role_code)
    if role is None:
        _raise_http(DataPermissionValidationError("应用角色不存在"))
    try:
        service.add_policy(
            resource_id,
            role,
            command.action_code,
            command.effect,
            _actor(context),
        )
    except (
        DataPermissionDenied,
        DataPermissionValidationError,
        DataResourceNotFound,
    ) as error:
        _raise_http(error)
