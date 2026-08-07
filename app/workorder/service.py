"""Work-order use cases and transaction boundaries."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.iam.authorization import PermissionService, WorkOrderScopeFilter

from .domain import (
    WorkOrderActionType,
    WorkOrderNotFound,
    WorkOrderPermissionDenied,
    WorkOrderStatus,
    WorkOrderValidationError,
)
from .models import WorkOrder, WorkOrderAction
from .numbering import WorkOrderNumberService
from .repository import WorkOrderRepository


@dataclass(frozen=True)
class WorkOrderActor:
    user_id: int
    active_org_id: int


@dataclass(frozen=True)
class CreateWorkOrderCommand:
    title: str
    work_order_type: str
    source_type: str | None = None
    source_id: str | None = None
    priority: str = "NORMAL"
    asset_type: str | None = None
    asset_id: str | None = None
    location: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    description: str | None = None
    due_at: datetime | None = None


class WorkflowSubmissionPort(Protocol):
    def start_submitted_workorder(
        self,
        work_order_id: int,
        initiator_id: int,
    ) -> object: ...


class WorkOrderService:
    VIEW_PERMISSION = "workorder:view"
    CREATE_PERMISSION = "workorder:create"

    def __init__(
        self,
        repository: WorkOrderRepository,
        permission_service: PermissionService,
        workflow_submission: WorkflowSubmissionPort | None = None,
        *,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.repository = repository
        self.permission_service = permission_service
        self.workflow_submission = workflow_submission
        self.number_service = WorkOrderNumberService(repository)
        self.clock = clock

    def create(
        self,
        command: CreateWorkOrderCommand,
        actor: WorkOrderActor,
    ) -> WorkOrder:
        self._require_permission(actor, self.CREATE_PERMISSION)
        title = command.title.strip()
        work_order_type = command.work_order_type.strip()
        priority = command.priority.strip().upper()
        if not title:
            raise WorkOrderValidationError("title must not be blank")
        if not work_order_type:
            raise WorkOrderValidationError("type must not be blank")
        if not priority:
            raise WorkOrderValidationError("priority must not be blank")
        now = self.clock()
        work_order = WorkOrder(
            work_order_no=self.number_service.next_number(now),
            title=title,
            work_order_type=work_order_type,
            source_type=command.source_type,
            source_id=command.source_id,
            priority=priority,
            owner_org_id=actor.active_org_id,
            current_org_id=actor.active_org_id,
            status=WorkOrderStatus.DRAFT.value,
            asset_type=command.asset_type,
            asset_id=command.asset_id,
            location=command.location,
            longitude=command.longitude,
            latitude=command.latitude,
            description=command.description,
            due_at=command.due_at,
            created_by=actor.user_id,
        )
        self.repository.add(work_order)
        self.repository.flush()
        self.repository.add(
            WorkOrderAction(
                work_order_id=work_order.id,
                action_type=WorkOrderActionType.CREATE.value,
                operator_id=actor.user_id,
                from_status=None,
                to_status=WorkOrderStatus.DRAFT.value,
            )
        )
        self.repository.commit()
        self.repository.refresh(work_order)
        return work_order

    def submit(
        self,
        work_order_id: int,
        actor: WorkOrderActor,
        comment: str | None = None,
    ) -> WorkOrder:
        self._require_permission(actor, self.CREATE_PERMISSION)
        work_order = self.repository.get(work_order_id)
        if work_order is None:
            raise WorkOrderNotFound(f"work order not found: {work_order_id}")
        if work_order.created_by != actor.user_id:
            raise WorkOrderPermissionDenied("only the creator can submit a draft")

        from_status, to_status = work_order.submit()
        self.repository.add(
            WorkOrderAction(
                work_order_id=work_order.id,
                action_type=WorkOrderActionType.SUBMIT.value,
                operator_id=actor.user_id,
                from_status=from_status,
                to_status=to_status,
                comment=comment,
            )
        )
        if self.workflow_submission is None:
            self.repository.commit()
        else:
            self.workflow_submission.start_submitted_workorder(
                work_order.id,
                actor.user_id,
            )
        self.repository.refresh(work_order)
        return work_order

    def list_visible(self, actor: WorkOrderActor) -> list[WorkOrder]:
        return self.repository.list_visible(self._view_scope(actor))

    def get_visible(self, work_order_id: int, actor: WorkOrderActor) -> WorkOrder:
        work_order = self.repository.get_visible(work_order_id, self._view_scope(actor))
        if work_order is None:
            raise WorkOrderNotFound(f"work order not found: {work_order_id}")
        return work_order

    def timeline(
        self,
        work_order_id: int,
        actor: WorkOrderActor,
    ) -> list[WorkOrderAction]:
        self.get_visible(work_order_id, actor)
        return self.repository.list_actions(work_order_id)

    def _view_scope(self, actor: WorkOrderActor) -> WorkOrderScopeFilter:
        self._require_permission(actor, self.VIEW_PERMISSION)
        return self.permission_service.work_order_scope(
            actor.user_id,
            self.VIEW_PERMISSION,
            actor.active_org_id,
        )

    def _require_permission(
        self,
        actor: WorkOrderActor,
        permission_code: str,
    ) -> None:
        if not self.permission_service.has_permission(
            actor.user_id,
            permission_code,
            actor.active_org_id,
        ):
            raise WorkOrderPermissionDenied(f"missing permission: {permission_code}")
