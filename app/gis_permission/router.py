"""GIS query, export, and policy administration APIs."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.router import get_request_context
from app.auth.service import RequestContext
from app.data_permission.repository import DataPermissionRepository
from app.data_permission.service import (
    DataActor,
    DataPermissionDenied,
    DataPermissionService,
    DataResourceNotFound,
)
from app.db.dependencies import get_db_session
from app.iam.authorization import PermissionService
from app.iam.repository import IAMRepository

from .models import ResourceField
from .repository import GISPermissionRepository
from .schemas import (
    CreateResourceFieldRequest,
    CreateSpatialScopeRequest,
    GISExportRequest,
    GISExportResponse,
    GISQueryResponse,
    SetFieldPolicyRequest,
)
from .service import GISPermissionService, GISValidationError

router = APIRouter(prefix="/api/gis", tags=["gis-permissions"])


def get_gis_permission_service(
    session: Annotated[Session, Depends(get_db_session)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> GISPermissionService:
    data_repository = DataPermissionRepository(session, context.tenant_id)
    return GISPermissionService(
        GISPermissionRepository(session, context.tenant_id),
        data_repository,
        DataPermissionService(
            data_repository,
            PermissionService(IAMRepository(session, context.tenant_id)),
        ),
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


def _export_item(job) -> dict:
    return {
        "id": job.id,
        "resource_id": job.resource_id,
        "resource_name": job.resource.resource_name,
        "export_format": job.export_format,
        "status": job.status,
        "row_count": job.row_count,
        "field_codes": job.field_codes_json,
        "spatial_scopes": job.spatial_scope_json,
        "file_name": job.file_name,
        "created_at": job.created_at,
    }


@router.get("/resources/{resource_id}/features", response_model=GISQueryResponse)
def query_features(
    resource_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[GISPermissionService, Depends(get_gis_permission_service)],
) -> GISQueryResponse:
    try:
        result = service.query_features(resource_id, _actor(context))
    except (DataPermissionDenied, DataResourceNotFound) as error:
        _raise_http(error)
    return GISQueryResponse.model_validate(result, from_attributes=True)


@router.post(
    "/resources/{resource_id}/exports",
    response_model=GISExportResponse,
    status_code=201,
)
def request_export(
    resource_id: int,
    command: GISExportRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[GISPermissionService, Depends(get_gis_permission_service)],
) -> GISExportResponse:
    try:
        job = service.request_export(
            resource_id,
            _actor(context),
            tuple(command.field_codes),
            command.export_format,
        )
        job = service.repository.list_export_jobs(context.current_user_id)[0]
    except (
        DataPermissionDenied,
        DataResourceNotFound,
        GISValidationError,
    ) as error:
        _raise_http(error)
    return GISExportResponse.model_validate(_export_item(job))


@router.get("/exports", response_model=list[GISExportResponse])
def list_exports(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[GISPermissionService, Depends(get_gis_permission_service)],
) -> list[GISExportResponse]:
    return [
        GISExportResponse.model_validate(_export_item(item))
        for item in service.list_exports(_actor(context))
    ]


@router.post("/resources/{resource_id}/fields", status_code=204)
def create_field(
    resource_id: int,
    command: CreateResourceFieldRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[GISPermissionService, Depends(get_gis_permission_service)],
) -> None:
    try:
        service.create_field(
            resource_id,
            ResourceField(
                tenant_id=context.tenant_id,
                resource_id=resource_id,
                **command.model_dump(),
            ),
            _actor(context),
        )
    except (DataPermissionDenied, DataResourceNotFound, GISValidationError) as error:
        _raise_http(error)


@router.put("/fields/{field_id}/policy", status_code=204)
def set_field_policy(
    field_id: int,
    command: SetFieldPolicyRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[GISPermissionService, Depends(get_gis_permission_service)],
) -> None:
    try:
        service.set_field_policy(
            field_id,
            command.role_code,
            command.access_mode,
            _actor(context),
        )
    except (DataPermissionDenied, GISValidationError) as error:
        _raise_http(error)


@router.post("/resources/{resource_id}/spatial-scopes", status_code=204)
def create_spatial_scope(
    resource_id: int,
    command: CreateSpatialScopeRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[GISPermissionService, Depends(get_gis_permission_service)],
) -> None:
    try:
        service.set_spatial_scope(
            resource_id,
            command.role_code,
            command.scope_type,
            command.scope_value,
            command.coordinate_precision,
            _actor(context),
        )
    except (DataPermissionDenied, GISValidationError) as error:
        _raise_http(error)
