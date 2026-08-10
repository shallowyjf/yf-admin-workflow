"""Paged IAM search and JSON batch import/export endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.repository import AuthRepository
from app.auth.router import get_request_context
from app.auth.service import AuthSessionRevocationService, RequestContext
from app.db.dependencies import get_db_session

from .admin_service import (
    IAMAdministrationActor,
    IAMAdministrationPermissionDenied,
    IAMAdministrationValidationError,
    OrganizationAdministrationService,
)
from .authorization import PermissionService
from .bulk_service import IAMBulkService
from .repository import IAMListQuery, IAMRepository
from .role_admin_service import RoleAdministrationService
from .user_admin_service import UserAdministrationService

router = APIRouter(prefix="/api/iam/batch", tags=["iam-operations"])


class IAMPageResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    pages: int


class IAMExportResponse(BaseModel):
    entity: str
    records: list[dict[str, Any]]


class IAMImportRequest(BaseModel):
    entity: str = Field(min_length=1, max_length=40)
    records: list[dict[str, Any]] = Field(min_length=1, max_length=500)


class IAMImportItemResponse(BaseModel):
    row: int
    key: str
    success: bool
    detail: str


class IAMImportResponse(BaseModel):
    entity: str
    total: int
    succeeded: int
    failed: int
    items: list[IAMImportItemResponse]


def get_iam_bulk_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> IAMBulkService:
    repository = IAMRepository(session)
    permissions = PermissionService(repository)
    return IAMBulkService(
        repository,
        permissions,
        OrganizationAdministrationService(repository, permissions),
        UserAdministrationService(
            repository,
            permissions,
            AuthSessionRevocationService(AuthRepository(session)),
        ),
        RoleAdministrationService(repository, permissions),
    )


def _actor(context: RequestContext) -> IAMAdministrationActor:
    return IAMAdministrationActor(context.current_user_id, context.active_org_id)


def _raise_http(error: Exception) -> None:
    code = (
        status.HTTP_403_FORBIDDEN
        if isinstance(error, IAMAdministrationPermissionDenied)
        else status.HTTP_422_UNPROCESSABLE_CONTENT
    )
    raise HTTPException(code, str(error)) from error


@router.get("/search", response_model=IAMPageResponse)
def search_iam(
    entity: str,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[IAMBulkService, Depends(get_iam_bulk_service)],
    keyword: str | None = None,
    is_active: bool | None = None,
    sort_by: str = "code",
    sort_direction: str = "asc",
    page: int = 1,
    page_size: int = 20,
) -> IAMPageResponse:
    try:
        result = service.search(
            entity,
            IAMListQuery(
                keyword=keyword,
                is_active=is_active,
                sort_by=sort_by,
                sort_direction=sort_direction,
                page=page,
                page_size=page_size,
            ),
            _actor(context),
        )
    except (IAMAdministrationPermissionDenied, IAMAdministrationValidationError) as error:
        _raise_http(error)
    return IAMPageResponse(
        items=result.items,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        pages=result.pages,
    )


@router.get("/export", response_model=IAMExportResponse)
def export_iam(
    entity: str,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[IAMBulkService, Depends(get_iam_bulk_service)],
) -> IAMExportResponse:
    try:
        records = service.export(entity, _actor(context))
    except (IAMAdministrationPermissionDenied, IAMAdministrationValidationError) as error:
        _raise_http(error)
    return IAMExportResponse(entity=entity.upper(), records=records)


@router.post("/import", response_model=IAMImportResponse)
def import_iam_records(
    command: IAMImportRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[IAMBulkService, Depends(get_iam_bulk_service)],
) -> IAMImportResponse:
    try:
        result = service.import_records(
            command.entity, command.records, _actor(context)
        )
    except (IAMAdministrationPermissionDenied, IAMAdministrationValidationError) as error:
        _raise_http(error)
    return IAMImportResponse.model_validate(result, from_attributes=True)
