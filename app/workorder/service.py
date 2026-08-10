"""Work-order use cases and transaction boundaries."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.iam.authorization import PermissionService, WorkOrderScopeFilter

from .domain import (
    InvalidWorkOrderTransition,
    WorkOrderActionType,
    WorkOrderNotFound,
    WorkOrderPermissionDenied,
    WorkOrderStatus,
    WorkOrderValidationError,
)
from .models import WorkOrder, WorkOrderAction
from .numbering import WorkOrderNumberService
from .repository import WorkOrderRepository
from .sla import DEFAULT_SLA_POLICIES, SlaCalendar


@dataclass(frozen=True)
class WorkOrderActor:
    user_id: int
    active_org_id: int


@dataclass(frozen=True)
class SlaEvaluationResult:
    evaluated: int
    response_breaches: int
    resolution_breaches: int


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

    def transfer_workorder(
        self,
        work_order_id: int,
        operator_id: int,
        target_user_id: int,
    ) -> object: ...

    def review_workorder(
        self,
        work_order_id: int,
        operator_id: int,
        decision: str,
        original_assignee_id: int | None,
    ) -> object: ...


class NotificationPort(Protocol):
    def stage_work_order(
        self,
        user_id: int,
        work_order_id: int,
        event_type: str,
        title: str,
        content: str,
    ) -> object: ...


class WorkOrderService:
    VIEW_PERMISSION = "workorder:view"
    CREATE_PERMISSION = "workorder:create"
    COLLABORATION_STATUSES = frozenset(
        {
            WorkOrderStatus.PENDING_DISPATCH.value,
            WorkOrderStatus.PENDING_CLAIM.value,
            WorkOrderStatus.PROCESSING.value,
            WorkOrderStatus.PENDING_REVIEW.value,
        }
    )

    def __init__(
        self,
        repository: WorkOrderRepository,
        permission_service: PermissionService,
        workflow_actions: WorkflowActionPort | None = None,
        notification_service: NotificationPort | None = None,
        *,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.repository = repository
        self.permission_service = permission_service
        self.workflow_actions = workflow_actions
        self.notification_service = notification_service
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
        sla_policy = self.repository.get_sla_policy(priority)
        if sla_policy is None:
            default_policy = next(
                (
                    item
                    for item in DEFAULT_SLA_POLICIES
                    if item.priority == priority
                ),
                next(
                    item
                    for item in DEFAULT_SLA_POLICIES
                    if item.priority == "NORMAL"
                ),
            )
            response_due_at = SlaCalendar.add_minutes(
                now,
                default_policy.response_minutes,
                default_policy.calendar_code,
            )
            resolution_due_at = SlaCalendar.add_minutes(
                now,
                default_policy.resolve_minutes,
                default_policy.calendar_code,
            )
        else:
            response_due_at = SlaCalendar.add_minutes(
                now,
                sla_policy.response_minutes,
                sla_policy.calendar_code,
            )
            resolution_due_at = SlaCalendar.add_minutes(
                now,
                sla_policy.resolve_minutes,
                sla_policy.calendar_code,
            )
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
            due_at=command.due_at or resolution_due_at,
            response_due_at=response_due_at,
            sla_status="ON_TRACK",
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
        occurred_at = self.clock()
        from_status, to_status = work_order.claim(actor.user_id)
        work_order.mark_responded(occurred_at)
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

    def transfer(
        self,
        work_order_id: int,
        target_user_id: int,
        actor: WorkOrderActor,
        comment: str | None = None,
    ) -> WorkOrder:
        if target_user_id <= 0:
            raise WorkOrderValidationError("target_user_id must be positive")
        work_order = self._get_for_action(
            work_order_id,
            actor,
            "workorder:transfer",
        )
        if not self.permission_service.has_permission(
            target_user_id,
            "workorder:handle",
            work_order.current_org_id,
        ):
            raise WorkOrderValidationError(
                "target user must be an active handler in the current organization"
            )
        previous_assignee_id = work_order.transfer(target_user_id)
        normalized_comment = self._optional_comment(comment)
        self._record_action(
            work_order,
            WorkOrderActionType.TRANSFER,
            actor.user_id,
            work_order.status,
            work_order.status,
            comment=normalized_comment,
            payload={
                "previous_assignee_id": previous_assignee_id,
                "target_assignee_id": target_user_id,
            },
        )
        self._stage_notification(
            target_user_id,
            work_order,
            "WORKORDER_TRANSFERRED",
            "工单已转派给你",
            normalized_comment or f"工单 {work_order.work_order_no} 已转派",
        )
        if self.workflow_actions is None:
            self.repository.commit()
        else:
            self.workflow_actions.transfer_workorder(
                work_order.id,
                actor.user_id,
                target_user_id,
            )
        self.repository.refresh(work_order)
        return work_order

    def add_comment(
        self,
        work_order_id: int,
        actor: WorkOrderActor,
        comment: str,
    ) -> WorkOrderAction:
        work_order = self._get_for_action(
            work_order_id,
            actor,
            "workorder:comment",
            include_owner_org=True,
        )
        normalized_comment = self._required_comment(comment)
        self._record_action(
            work_order,
            WorkOrderActionType.COMMENT,
            actor.user_id,
            work_order.status,
            work_order.status,
            comment=normalized_comment,
        )
        self.repository.commit()
        return self.repository.list_actions(work_order.id)[-1]

    def urge(
        self,
        work_order_id: int,
        actor: WorkOrderActor,
        comment: str,
    ) -> WorkOrderAction:
        work_order = self._get_for_action(
            work_order_id,
            actor,
            "workorder:urge",
            include_owner_org=True,
        )
        if work_order.status not in self.COLLABORATION_STATUSES:
            raise InvalidWorkOrderTransition(
                f"cannot URGE work order from {work_order.status}"
            )
        normalized_comment = self._required_comment(comment)
        self._record_action(
            work_order,
            WorkOrderActionType.URGE,
            actor.user_id,
            work_order.status,
            work_order.status,
            comment=normalized_comment,
            payload={
                "current_org_id": work_order.current_org_id,
                "current_assignee_id": work_order.current_assignee_id,
            },
        )
        if work_order.current_assignee_id is not None:
            self._stage_notification(
                work_order.current_assignee_id,
                work_order,
                "WORKORDER_URGED",
                "工单收到催办",
                normalized_comment,
            )
        self.repository.commit()
        return self.repository.list_actions(work_order.id)[-1]

    def evaluate_sla(
        self,
        actor: WorkOrderActor,
    ) -> SlaEvaluationResult:
        permission_code = "workorder:sla:evaluate"
        self._require_permission(actor, permission_code)
        scope = self.permission_service.work_order_scope(
            actor.user_id,
            permission_code,
            actor.active_org_id,
        )
        work_orders = self.repository.list_visible(scope)
        now = self.clock()
        response_breaches = 0
        resolution_breaches = 0
        terminal_statuses = {
            WorkOrderStatus.COMPLETED.value,
            WorkOrderStatus.CLOSED.value,
        }
        for work_order in work_orders:
            if (
                work_order.status not in terminal_statuses
                and work_order.due_at is not None
                and now > work_order.due_at
                and work_order.sla_status != "RESOLUTION_BREACHED"
            ):
                work_order.sla_status = "RESOLUTION_BREACHED"
                resolution_breaches += 1
                self._record_action(
                    work_order,
                    WorkOrderActionType.SLA_RESOLUTION_BREACH,
                    actor.user_id,
                    work_order.status,
                    work_order.status,
                    comment="解决时限已超时",
                    payload={"due_at": work_order.due_at.isoformat()},
                )
                self._stage_sla_notification(
                    work_order,
                    "SLA_RESOLUTION_BREACH",
                    "工单解决时限已超时",
                )
            elif (
                work_order.status not in terminal_statuses
                and work_order.responded_at is None
                and work_order.response_due_at is not None
                and now > work_order.response_due_at
                and work_order.sla_status == "ON_TRACK"
            ):
                work_order.sla_status = "RESPONSE_BREACHED"
                response_breaches += 1
                self._record_action(
                    work_order,
                    WorkOrderActionType.SLA_RESPONSE_BREACH,
                    actor.user_id,
                    work_order.status,
                    work_order.status,
                    comment="响应时限已超时",
                    payload={
                        "response_due_at": work_order.response_due_at.isoformat()
                    },
                )
                self._stage_sla_notification(
                    work_order,
                    "SLA_RESPONSE_BREACH",
                    "工单响应时限已超时",
                )
        if response_breaches or resolution_breaches:
            self.repository.commit()
        return SlaEvaluationResult(
            evaluated=len(work_orders),
            response_breaches=response_breaches,
            resolution_breaches=resolution_breaches,
        )

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

    @staticmethod
    def _optional_comment(comment: str | None) -> str | None:
        if comment is None:
            return None
        normalized = comment.strip()
        if len(normalized) > 1000:
            raise WorkOrderValidationError("comment must not exceed 1000 characters")
        return normalized or None

    @classmethod
    def _required_comment(cls, comment: str) -> str:
        normalized = cls._optional_comment(comment)
        if normalized is None:
            raise WorkOrderValidationError("comment must not be blank")
        return normalized

    def _stage_sla_notification(
        self,
        work_order: WorkOrder,
        event_type: str,
        title: str,
    ) -> None:
        recipient_id = work_order.current_assignee_id or work_order.created_by
        self._stage_notification(
            recipient_id,
            work_order,
            event_type,
            title,
            f"{work_order.work_order_no} · {work_order.title}",
        )

    def _stage_notification(
        self,
        user_id: int,
        work_order: WorkOrder,
        event_type: str,
        title: str,
        content: str,
    ) -> None:
        if self.notification_service is not None:
            self.notification_service.stage_work_order(
                user_id,
                work_order.id,
                event_type,
                title,
                content,
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
