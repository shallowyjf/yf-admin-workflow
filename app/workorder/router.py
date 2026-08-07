"""Authenticated work-order use-case endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.router import get_request_context
from app.auth.service import RequestContext
from app.db.dependencies import get_db_session
from app.iam.authorization import PermissionService
from app.iam.repository import IAMRepository

from .domain import (
    InvalidWorkOrderTransition,
    WorkOrderNotFound,
    WorkOrderNumberExhausted,
    WorkOrderPermissionDenied,
    WorkOrderValidationError,
)
from .models import WorkOrder, WorkOrderAction
from .repository import WorkOrderRepository
from .schemas import (
    CreateWorkOrderRequest,
    SubmitWorkOrderRequest,
    WorkOrderActionResponse,
    WorkOrderResponse,
)
from .service import CreateWorkOrderCommand, WorkOrderActor, WorkOrderService

router = APIRouter(prefix="/api/workorders", tags=["workorders"])


def get_work_order_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> WorkOrderService:
    return WorkOrderService(
        WorkOrderRepository(session),
        PermissionService(IAMRepository(session)),
    )


def _actor(context: RequestContext) -> WorkOrderActor:
    return WorkOrderActor(context.current_user_id, context.active_org_id)


def _order_response(work_order: WorkOrder) -> WorkOrderResponse:
    return WorkOrderResponse(
        id=work_order.id,
        work_order_no=work_order.work_order_no,
        title=work_order.title,
        type=work_order.work_order_type,
        source_type=work_order.source_type,
        source_id=work_order.source_id,
        priority=work_order.priority,
        owner_org_id=work_order.owner_org_id,
        current_org_id=work_order.current_org_id,
        current_assignee_id=work_order.current_assignee_id,
        status=work_order.status,
        asset_type=work_order.asset_type,
        asset_id=work_order.asset_id,
        location=work_order.location,
        longitude=work_order.longitude,
        latitude=work_order.latitude,
        description=work_order.description,
        due_at=work_order.due_at,
        completed_at=work_order.completed_at,
        closed_at=work_order.closed_at,
        created_by=work_order.created_by,
        created_at=work_order.created_at,
        updated_at=work_order.updated_at,
    )


def _action_response(action: WorkOrderAction) -> WorkOrderActionResponse:
    return WorkOrderActionResponse.model_validate(action, from_attributes=True)


def _raise_http(error: Exception) -> None:
    if isinstance(error, WorkOrderPermissionDenied):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(error, WorkOrderNotFound):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, WorkOrderValidationError):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        status_code = status.HTTP_409_CONFLICT
    raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.post("", response_model=WorkOrderResponse, status_code=status.HTTP_201_CREATED)
def create_work_order(
    command: CreateWorkOrderRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderResponse:
    try:
        work_order = service.create(
            CreateWorkOrderCommand(
                title=command.title,
                work_order_type=command.type,
                source_type=command.source_type,
                source_id=command.source_id,
                priority=command.priority,
                asset_type=command.asset_type,
                asset_id=command.asset_id,
                location=command.location,
                longitude=command.longitude,
                latitude=command.latitude,
                description=command.description,
                due_at=command.due_at,
            ),
            _actor(context),
        )
    except (
        WorkOrderNumberExhausted,
        WorkOrderPermissionDenied,
        WorkOrderValidationError,
    ) as error:
        _raise_http(error)
    return _order_response(work_order)


@router.post("/{work_order_id}/submit", response_model=WorkOrderResponse)
def submit_work_order(
    work_order_id: int,
    command: SubmitWorkOrderRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderResponse:
    try:
        work_order = service.submit(
            work_order_id,
            _actor(context),
            command.comment,
        )
    except (
        InvalidWorkOrderTransition,
        WorkOrderNotFound,
        WorkOrderPermissionDenied,
    ) as error:
        _raise_http(error)
    return _order_response(work_order)


@router.get("", response_model=list[WorkOrderResponse])
def list_work_orders(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> list[WorkOrderResponse]:
    try:
        work_orders = service.list_visible(_actor(context))
    except WorkOrderPermissionDenied as error:
        _raise_http(error)
    return [_order_response(work_order) for work_order in work_orders]


@router.get("/{work_order_id}", response_model=WorkOrderResponse)
def get_work_order(
    work_order_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderResponse:
    try:
        work_order = service.get_visible(work_order_id, _actor(context))
    except (WorkOrderNotFound, WorkOrderPermissionDenied) as error:
        _raise_http(error)
    return _order_response(work_order)


@router.get("/{work_order_id}/timeline", response_model=list[WorkOrderActionResponse])
def work_order_timeline(
    work_order_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> list[WorkOrderActionResponse]:
    try:
        actions = service.timeline(work_order_id, _actor(context))
    except (WorkOrderNotFound, WorkOrderPermissionDenied) as error:
        _raise_http(error)
    return [_action_response(action) for action in actions]
