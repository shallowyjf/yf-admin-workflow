"""Authenticated work-order use-case endpoints."""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.router import get_request_context
from app.auth.service import RequestContext
from app.db.dependencies import get_db_session
from app.iam.authorization import PermissionService
from app.iam.repository import IAMRepository
from app.notification.repository import NotificationRepository
from app.notification.service import NotificationService
from app.workflow.domain import TaskAccessDenied, WorkflowError
from app.workflow.factory import build_workflow_service

from .attachment_service import WorkOrderAttachmentService
from .batch_service import WorkOrderBatchService
from .domain import (
    InvalidWorkOrderTransition,
    WorkOrderError,
    WorkOrderNotFound,
    WorkOrderNumberExhausted,
    WorkOrderPermissionDenied,
    WorkOrderValidationError,
)
from .models import WorkOrder, WorkOrderAction
from .repository import WorkOrderListQuery, WorkOrderRepository
from .schemas import (
    BatchActionResponse,
    BatchDispatchRequest,
    BatchUrgeRequest,
    CreateWorkOrderRequest,
    DispatchWorkOrderRequest,
    ReviewWorkOrderRequest,
    SlaEvaluationResponse,
    SubmitResultRequest,
    SubmitWorkOrderRequest,
    TransferWorkOrderRequest,
    WorkOrderActionRequest,
    WorkOrderActionResponse,
    WorkOrderAttachmentResponse,
    WorkOrderCommentRequest,
    WorkOrderPageResponse,
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
        build_workflow_service(session),
        NotificationService(NotificationRepository(session)),
    )


def get_attachment_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> WorkOrderAttachmentService:
    return WorkOrderAttachmentService(
        WorkOrderRepository(session),
        PermissionService(IAMRepository(session)),
    )


def get_batch_service(
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderBatchService:
    return WorkOrderBatchService(service)


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
        response_due_at=work_order.response_due_at,
        responded_at=work_order.responded_at,
        sla_status=work_order.sla_status,
        completed_at=work_order.completed_at,
        closed_at=work_order.closed_at,
        created_by=work_order.created_by,
        created_at=work_order.created_at,
        updated_at=work_order.updated_at,
    )


def _action_response(action: WorkOrderAction) -> WorkOrderActionResponse:
    return WorkOrderActionResponse.model_validate(action, from_attributes=True)


def _raise_http(error: Exception) -> None:
    if isinstance(error, (TaskAccessDenied, WorkOrderPermissionDenied)):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(error, WorkOrderNotFound):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, WorkOrderValidationError):
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
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
        WorkflowError,
    ) as error:
        _raise_http(error)
    return _order_response(work_order)


@router.post("/{work_order_id:int}/dispatch", response_model=WorkOrderResponse)
def dispatch_work_order(
    work_order_id: int,
    command: DispatchWorkOrderRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderResponse:
    try:
        work_order = service.dispatch(
            work_order_id,
            command.target_org_id,
            _actor(context),
            command.comment,
        )
    except (WorkOrderError, WorkflowError) as error:
        _raise_http(error)
    return _order_response(work_order)


@router.post("/{work_order_id}/claim", response_model=WorkOrderResponse)
def claim_work_order(
    work_order_id: int,
    command: WorkOrderActionRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderResponse:
    try:
        work_order = service.claim(
            work_order_id,
            _actor(context),
            command.comment,
        )
    except (WorkOrderError, WorkflowError) as error:
        _raise_http(error)
    return _order_response(work_order)


@router.post("/{work_order_id}/result", response_model=WorkOrderResponse)
def submit_work_order_result(
    work_order_id: int,
    command: SubmitResultRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderResponse:
    try:
        work_order = service.submit_result(
            work_order_id,
            _actor(context),
            command.result,
            command.comment,
        )
    except (WorkOrderError, WorkflowError) as error:
        _raise_http(error)
    return _order_response(work_order)


@router.post("/{work_order_id}/transfer", response_model=WorkOrderResponse)
def transfer_work_order(
    work_order_id: int,
    command: TransferWorkOrderRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderResponse:
    try:
        work_order = service.transfer(
            work_order_id,
            command.target_user_id,
            _actor(context),
            command.comment,
        )
    except (WorkOrderError, WorkflowError) as error:
        _raise_http(error)
    return _order_response(work_order)


@router.post(
    "/{work_order_id}/comments",
    response_model=WorkOrderActionResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_work_order_comment(
    work_order_id: int,
    command: WorkOrderCommentRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderActionResponse:
    try:
        action = service.add_comment(
            work_order_id,
            _actor(context),
            command.comment,
        )
    except WorkOrderError as error:
        _raise_http(error)
    return _action_response(action)


@router.post(
    "/{work_order_id:int}/urge",
    response_model=WorkOrderActionResponse,
    status_code=status.HTTP_201_CREATED,
)
def urge_work_order(
    work_order_id: int,
    command: WorkOrderCommentRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderActionResponse:
    try:
        action = service.urge(
            work_order_id,
            _actor(context),
            command.comment,
        )
    except WorkOrderError as error:
        _raise_http(error)
    return _action_response(action)


@router.post("/sla/evaluate", response_model=SlaEvaluationResponse)
def evaluate_work_order_sla(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> SlaEvaluationResponse:
    try:
        result = service.evaluate_sla(_actor(context))
    except WorkOrderError as error:
        _raise_http(error)
    return SlaEvaluationResponse.model_validate(result, from_attributes=True)


@router.get("/search", response_model=WorkOrderPageResponse)
def search_work_orders(
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
    keyword: str | None = None,
    status_filter: list[str] | None = None,
    priority: list[str] | None = None,
    sla_status: list[str] | None = None,
    organization_id: int | None = None,
    assignee_id: int | None = None,
    sort_by: str = "created_at",
    sort_direction: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> WorkOrderPageResponse:
    try:
        result = service.search_visible(
            _actor(context),
            WorkOrderListQuery(
                keyword=keyword,
                statuses=tuple(status_filter or ()),
                priorities=tuple(priority or ()),
                sla_statuses=tuple(sla_status or ()),
                organization_id=organization_id,
                assignee_id=assignee_id,
                sort_by=sort_by,
                sort_direction=sort_direction,
                page=page,
                page_size=page_size,
            ),
        )
    except WorkOrderError as error:
        _raise_http(error)
    return WorkOrderPageResponse(
        items=[_order_response(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        pages=max(1, (result.total + result.page_size - 1) // result.page_size),
    )


@router.post("/batch/dispatch", response_model=BatchActionResponse)
def batch_dispatch_work_orders(
    command: BatchDispatchRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkOrderBatchService, Depends(get_batch_service)],
) -> BatchActionResponse:
    result = service.dispatch(
        command.work_order_ids,
        command.target_org_id,
        _actor(context),
        command.comment,
    )
    return BatchActionResponse.model_validate(result, from_attributes=True)


@router.post("/batch/urge", response_model=BatchActionResponse)
def batch_urge_work_orders(
    command: BatchUrgeRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkOrderBatchService, Depends(get_batch_service)],
) -> BatchActionResponse:
    result = service.urge(
        command.work_order_ids,
        _actor(context),
        command.comment,
    )
    return BatchActionResponse.model_validate(result, from_attributes=True)


@router.post(
    "/{work_order_id}/attachments",
    response_model=WorkOrderAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_work_order_attachment(
    work_order_id: int,
    file: Annotated[UploadFile, File()],
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        WorkOrderAttachmentService,
        Depends(get_attachment_service),
    ],
) -> WorkOrderAttachmentResponse:
    try:
        attachment = service.upload(
            work_order_id,
            _actor(context),
            file.filename or "",
            file.content_type or "application/octet-stream",
            await file.read(WorkOrderAttachmentService.MAX_SIZE_BYTES + 1),
        )
    except WorkOrderError as error:
        _raise_http(error)
    finally:
        await file.close()
    return WorkOrderAttachmentResponse.model_validate(
        attachment,
        from_attributes=True,
    )


@router.get(
    "/{work_order_id}/attachments",
    response_model=list[WorkOrderAttachmentResponse],
)
def list_work_order_attachments(
    work_order_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        WorkOrderAttachmentService,
        Depends(get_attachment_service),
    ],
) -> list[WorkOrderAttachmentResponse]:
    try:
        attachments = service.list_for_work_order(work_order_id, _actor(context))
    except WorkOrderError as error:
        _raise_http(error)
    return [
        WorkOrderAttachmentResponse.model_validate(item, from_attributes=True)
        for item in attachments
    ]


@router.get("/{work_order_id}/attachments/{attachment_id}/download")
def download_work_order_attachment(
    work_order_id: int,
    attachment_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        WorkOrderAttachmentService,
        Depends(get_attachment_service),
    ],
) -> Response:
    try:
        attachment = service.download(
            work_order_id,
            attachment_id,
            _actor(context),
        )
    except WorkOrderError as error:
        _raise_http(error)
    return Response(
        content=attachment.content_blob,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": (
                "attachment; filename=attachment; "
                f"filename*=UTF-8''{quote(attachment.filename)}"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{work_order_id}/review", response_model=WorkOrderResponse)
def review_work_order(
    work_order_id: int,
    command: ReviewWorkOrderRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderResponse:
    try:
        work_order = service.review(
            work_order_id,
            _actor(context),
            command.decision,
            command.comment,
        )
    except (WorkOrderError, WorkflowError) as error:
        _raise_http(error)
    return _order_response(work_order)


@router.post("/{work_order_id}/close", response_model=WorkOrderResponse)
def close_work_order(
    work_order_id: int,
    command: WorkOrderActionRequest,
    context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderResponse:
    try:
        work_order = service.close(
            work_order_id,
            _actor(context),
            command.comment,
        )
    except (WorkOrderError, WorkflowError) as error:
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
