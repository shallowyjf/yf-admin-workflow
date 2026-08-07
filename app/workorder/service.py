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


class WorkflowActionPort(Protocol):
    def start_submitted_workorder(
        self,
        work_order_id: int,
        initiator_id: int,
    ) -> object: ...

    def dispatch_workorder(
        self,
        work_order_id: int,
        operator_id: int,
        target_org_id: int,
    ) -> object: ...

    def claim_workorder(
        self,
        work_order_id: int,
        user_id: int,
    ) -> object: ...

    def submit_workorder_result(
        self,
        work_order_id: int,
        operator_id: int,
        review_org_id: int,
        payload: dict | None = None,
    ) -> object: ...

    def review_workorder(
        self,
        work_order_id: int,
        operator_id: int,
        decision: str,
        original_assignee_id: int | None,
    ) -> object: ...


class WorkOrderService:
    VIEW_PERMISSION = "workorder:view"
    CREATE_PERMISSION = "workorder:create"

    def __init__(
        self,
        repository: WorkOrderRepository,
        permission_service: PermissionService,
        workflow_actions: WorkflowActionPort | None = None,
        *,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.repository = repository
        self.permission_service = permission_service
        self.workflow_actions = workflow_actions
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
        if self.workflow_actions is None:
            self.repository.commit()
        else:
            self.workflow_actions.start_submitted_workorder(
                work_order.id,
                actor.user_id,
            )
        self.repository.refresh(work_order)
        return work_order

    def list_visible(self, actor: WorkOrderActor) -> list[WorkOrder]:
        return self.repository.list_visible(self._view_scope(actor))

    def dispatch(
        self,
        work_order_id: int,
        target_org_id: int,
        actor: WorkOrderActor,
        comment: str | None = None,
    ) -> WorkOrder:
        work_order = self._get_for_action(
            work_order_id,
            actor,
            "workorder:dispatch",
        )
        from_status, to_status = work_order.dispatch(target_org_id)
        self._record_action(
            work_order,
            WorkOrderActionType.DISPATCH,
            actor.user_id,
            from_status,
            to_status,
            comment=comment,
            payload={"target_org_id": target_org_id},
        )
        if self.workflow_actions is None:
            self.repository.commit()
        else:
            self.workflow_actions.dispatch_workorder(
                work_order.id,
                actor.user_id,
                target_org_id,
            )
        self.repository.refresh(work_order)
        return work_order

    def claim(
        self,
        work_order_id: int,
        actor: WorkOrderActor,
        comment: str | None = None,
    ) -> WorkOrder:
        self._require_permission(actor, "workorder:claim")
        work_order = self._get(work_order_id)
        from_status, to_status = work_order.claim(actor.user_id)
        self._record_action(
            work_order,
            WorkOrderActionType.CLAIM,
            actor.user_id,
            from_status,
            to_status,
            comment=comment,
        )
        if self.workflow_actions is None:
            self.repository.commit()
        else:
            self.workflow_actions.claim_workorder(
                work_order.id,
                actor.user_id,
            )
        self.repository.refresh(work_order)
        return work_order

    def submit_result(
        self,
        work_order_id: int,
        actor: WorkOrderActor,
        result: str,
        comment: str | None = None,
    ) -> WorkOrder:
        self._require_permission(actor, "workorder:handle")
        normalized_result = result.strip()
        if not normalized_result:
            raise WorkOrderValidationError("result must not be blank")
        work_order = self._get(work_order_id)
        from_status, to_status = work_order.submit_result()
        payload = {"result": normalized_result}
        self._record_action(
            work_order,
            WorkOrderActionType.SUBMIT_RESULT,
            actor.user_id,
            from_status,
            to_status,
            comment=comment,
            payload=payload,
        )
        if self.workflow_actions is None:
            self.repository.commit()
        else:
            self.workflow_actions.submit_workorder_result(
                work_order.id,
                actor.user_id,
                work_order.owner_org_id,
                payload,
            )
        self.repository.refresh(work_order)
        return work_order

    def review(
        self,
        work_order_id: int,
        actor: WorkOrderActor,
        decision: str,
        comment: str | None = None,
    ) -> WorkOrder:
        self._require_permission(actor, "workorder:review")
        normalized_decision = decision.strip().upper()
        work_order = self._get(work_order_id)
        if normalized_decision == WorkOrderActionType.APPROVE.value:
            from_status, to_status = work_order.approve(self.clock())
            action_type = WorkOrderActionType.APPROVE
        elif normalized_decision == WorkOrderActionType.REJECT.value:
            from_status, to_status = work_order.reject()
            action_type = WorkOrderActionType.REJECT
        else:
            raise WorkOrderValidationError(
                "review decision must be APPROVE or REJECT"
            )
        self._record_action(
            work_order,
            action_type,
            actor.user_id,
            from_status,
            to_status,
            comment=comment,
            payload={"decision": normalized_decision},
        )
        if self.workflow_actions is None:
            self.repository.commit()
        else:
            self.workflow_actions.review_workorder(
                work_order.id,
                actor.user_id,
                normalized_decision,
                work_order.current_assignee_id,
            )
        self.repository.refresh(work_order)
        return work_order

    def close(
        self,
        work_order_id: int,
        actor: WorkOrderActor,
        comment: str | None = None,
    ) -> WorkOrder:
        work_order = self._get_for_action(
            work_order_id,
            actor,
            "workorder:close",
            include_owner_org=True,
        )
        from_status, to_status = work_order.close(self.clock())
        self._record_action(
            work_order,
            WorkOrderActionType.CLOSE,
            actor.user_id,
            from_status,
            to_status,
            comment=comment,
        )
        self.repository.commit()
        self.repository.refresh(work_order)
        return work_order

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

    def _get(self, work_order_id: int) -> WorkOrder:
        work_order = self.repository.get(work_order_id)
        if work_order is None:
            raise WorkOrderNotFound(f"work order not found: {work_order_id}")
        return work_order

    def _get_for_action(
        self,
        work_order_id: int,
        actor: WorkOrderActor,
        permission_code: str,
        *,
        include_owner_org: bool = False,
    ) -> WorkOrder:
        self._require_permission(actor, permission_code)
        scope = self.permission_service.work_order_scope(
            actor.user_id,
            permission_code,
            actor.active_org_id,
        )
        work_order = self.repository.get_visible(
            work_order_id,
            scope,
            include_owner_org=include_owner_org,
        )
        if work_order is None:
            raise WorkOrderNotFound(f"work order not found: {work_order_id}")
        return work_order

    def _record_action(
        self,
        work_order: WorkOrder,
        action_type: WorkOrderActionType,
        operator_id: int,
        from_status: str,
        to_status: str,
        *,
        comment: str | None = None,
        payload: dict | None = None,
    ) -> None:
        self.repository.add(
            WorkOrderAction(
                work_order_id=work_order.id,
                action_type=action_type.value,
                operator_id=operator_id,
                from_status=from_status,
                to_status=to_status,
                comment=comment,
                payload_json=payload,
            )
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
