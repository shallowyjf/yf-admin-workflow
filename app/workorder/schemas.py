"""HTTP schemas for work-order use cases."""

from datetime import datetime

from pydantic import BaseModel, Field


class CreateWorkOrderRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    type: str = Field(min_length=1, max_length=60)
    source_type: str | None = Field(default=None, max_length=60)
    source_id: str | None = Field(default=None, max_length=120)
    priority: str = Field(default="NORMAL", min_length=1, max_length=30)
    asset_type: str | None = Field(default=None, max_length=60)
    asset_id: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=500)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    description: str | None = None
    due_at: datetime | None = None


class SubmitWorkOrderRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=1000)


class DispatchWorkOrderRequest(BaseModel):
    target_org_id: int = Field(gt=0)
    comment: str | None = Field(default=None, max_length=1000)


class WorkOrderActionRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=1000)


class WorkOrderCommentRequest(BaseModel):
    comment: str = Field(min_length=1, max_length=1000)


class TransferWorkOrderRequest(BaseModel):
    target_user_id: int = Field(gt=0)
    comment: str | None = Field(default=None, max_length=1000)


class SubmitResultRequest(BaseModel):
    result: str = Field(min_length=1, max_length=4000)
    comment: str | None = Field(default=None, max_length=1000)
    review_org_id: int | None = Field(default=None, gt=0)


class ReviewWorkOrderRequest(BaseModel):
    decision: str = Field(min_length=1, max_length=20)
    comment: str | None = Field(default=None, max_length=1000)


class WorkOrderResponse(BaseModel):
    id: int
    tenant_id: int
    application_id: int
    project_id: int
    work_order_no: str
    title: str
    type: str
    source_type: str | None
    source_id: str | None
    priority: str
    owner_org_id: int
    current_org_id: int
    current_assignee_id: int | None
    status: str
    asset_type: str | None
    asset_id: str | None
    location: str | None
    longitude: float | None
    latitude: float | None
    description: str | None
    due_at: datetime | None
    response_due_at: datetime | None
    responded_at: datetime | None
    sla_status: str
    completed_at: datetime | None
    closed_at: datetime | None
    created_by: int
    created_at: datetime
    updated_at: datetime


class WorkOrderActionResponse(BaseModel):
    id: int
    action_type: str
    operator_id: int
    from_status: str | None
    to_status: str
    comment: str | None
    payload_json: dict | None
    created_at: datetime


class WorkOrderAttachmentResponse(BaseModel):
    id: int
    work_order_id: int
    uploader_id: int
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    scan_status: str
    created_at: datetime


class SlaEvaluationResponse(BaseModel):
    evaluated: int
    response_breaches: int
    resolution_breaches: int


class WorkOrderPageResponse(BaseModel):
    items: list[WorkOrderResponse]
    total: int
    page: int
    page_size: int
    pages: int


class BatchDispatchRequest(BaseModel):
    work_order_ids: list[int] = Field(min_length=1, max_length=100)
    target_org_id: int = Field(gt=0)
    comment: str | None = Field(default=None, max_length=1000)


class BatchUrgeRequest(BaseModel):
    work_order_ids: list[int] = Field(min_length=1, max_length=100)
    comment: str = Field(min_length=1, max_length=1000)


class BatchItemResponse(BaseModel):
    work_order_id: int
    success: bool
    detail: str


class BatchActionResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    items: list[BatchItemResponse]
