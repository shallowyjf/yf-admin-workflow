"""Persistence for work orders and their action timeline."""

from dataclasses import dataclass

from sqlalchemy import asc, desc, false, func, or_, select, true
from sqlalchemy.orm import Session

from app.iam.authorization import WorkOrderScopeFilter

from .models import (
    WorkOrder,
    WorkOrderAction,
    WorkOrderAttachment,
    WorkOrderSlaPolicy,
)


@dataclass(frozen=True)
class WorkOrderListQuery:
    keyword: str | None = None
    statuses: tuple[str, ...] = ()
    priorities: tuple[str, ...] = ()
    sla_statuses: tuple[str, ...] = ()
    organization_id: int | None = None
    assignee_id: int | None = None
    sort_by: str = "created_at"
    sort_direction: str = "desc"
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class WorkOrderPage:
    items: list[WorkOrder]
    total: int
    page: int
    page_size: int


class WorkOrderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entity: object) -> None:
        self.session.add(entity)

    def flush(self) -> None:
        self.session.flush()

    def commit(self) -> None:
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def refresh(self, entity: object) -> None:
        self.session.refresh(entity)

    def get(self, work_order_id: int) -> WorkOrder | None:
        return self.session.get(WorkOrder, work_order_id)

    def get_visible(
        self,
        work_order_id: int,
        scope: WorkOrderScopeFilter,
        *,
        include_owner_org: bool = True,
        tenant_id: int | None = None,
        application_id: int | None = None,
        project_id: int | None = None,
    ) -> WorkOrder | None:
        conditions = [
            WorkOrder.id == work_order_id,
            self._scope_condition(scope, include_owner_org=include_owner_org),
        ]
        conditions.extend(self._context_conditions(tenant_id, application_id, project_id))
        return self.session.scalar(
            select(WorkOrder).where(*conditions)
        )

    def list_visible(
        self, scope: WorkOrderScopeFilter, *, tenant_id: int | None = None,
        application_id: int | None = None, project_id: int | None = None,
    ) -> list[WorkOrder]:
        conditions = [self._scope_condition(scope, include_owner_org=True)]
        conditions.extend(self._context_conditions(tenant_id, application_id, project_id))
        return list(
            self.session.scalars(
                select(WorkOrder)
                .where(*conditions)
                .order_by(WorkOrder.created_at.desc(), WorkOrder.id.desc())
            )
        )

    def search_visible(
        self,
        scope: WorkOrderScopeFilter,
        query: WorkOrderListQuery,
        *,
        tenant_id: int | None = None,
        application_id: int | None = None,
        project_id: int | None = None,
    ) -> WorkOrderPage:
        conditions = [self._scope_condition(scope, include_owner_org=True)]
        conditions.extend(self._context_conditions(tenant_id, application_id, project_id))
        keyword = (query.keyword or "").strip()
        if keyword:
            pattern = f"%{keyword}%"
            conditions.append(
                or_(
                    WorkOrder.work_order_no.ilike(pattern),
                    WorkOrder.title.ilike(pattern),
                    WorkOrder.location.ilike(pattern),
                )
            )
        if query.statuses:
            conditions.append(WorkOrder.status.in_(query.statuses))
        if query.priorities:
            conditions.append(WorkOrder.priority.in_(query.priorities))
        if query.sla_statuses:
            conditions.append(WorkOrder.sla_status.in_(query.sla_statuses))
        if query.organization_id is not None:
            conditions.append(
                or_(
                    WorkOrder.owner_org_id == query.organization_id,
                    WorkOrder.current_org_id == query.organization_id,
                )
            )
        if query.assignee_id is not None:
            conditions.append(WorkOrder.current_assignee_id == query.assignee_id)

        sort_columns = {
            "created_at": WorkOrder.created_at,
            "due_at": WorkOrder.due_at,
            "priority": WorkOrder.priority,
            "status": WorkOrder.status,
            "work_order_no": WorkOrder.work_order_no,
        }
        sort_column = sort_columns.get(query.sort_by, WorkOrder.created_at)
        order = asc(sort_column) if query.sort_direction == "asc" else desc(sort_column)
        total = self.session.scalar(
            select(func.count(WorkOrder.id)).where(*conditions)
        ) or 0
        items = list(
            self.session.scalars(
                select(WorkOrder)
                .where(*conditions)
                .order_by(order, WorkOrder.id.desc())
                .offset((query.page - 1) * query.page_size)
                .limit(query.page_size)
            )
        )
        return WorkOrderPage(items, total, query.page, query.page_size)

    def list_actions(self, work_order_id: int) -> list[WorkOrderAction]:
        return list(
            self.session.scalars(
                select(WorkOrderAction)
                .where(WorkOrderAction.work_order_id == work_order_id)
                .order_by(WorkOrderAction.created_at, WorkOrderAction.id)
            )
        )

    def get_sla_policy(
        self,
        priority: str,
        *,
        active_only: bool = True,
    ) -> WorkOrderSlaPolicy | None:
        statement = select(WorkOrderSlaPolicy).where(
            WorkOrderSlaPolicy.priority == priority
        )
        if active_only:
            statement = statement.where(WorkOrderSlaPolicy.is_active.is_(True))
        return self.session.scalar(statement)

    def get_attachment(self, attachment_id: int) -> WorkOrderAttachment | None:
        return self.session.get(WorkOrderAttachment, attachment_id)

    def list_attachments(self, work_order_id: int) -> list[WorkOrderAttachment]:
        return list(
            self.session.scalars(
                select(WorkOrderAttachment)
                .where(WorkOrderAttachment.work_order_id == work_order_id)
                .order_by(
                    WorkOrderAttachment.created_at.desc(),
                    WorkOrderAttachment.id.desc(),
                )
            )
        )

    def latest_number_for_prefix(self, prefix: str) -> str | None:
        return self.session.scalar(
            select(func.max(WorkOrder.work_order_no)).where(
                WorkOrder.work_order_no.like(f"{prefix}%")
            )
        )

    @staticmethod
    def _context_conditions(
        tenant_id: int | None,
        application_id: int | None,
        project_id: int | None,
    ) -> list:
        conditions = []
        if tenant_id is not None:
            conditions.append(WorkOrder.tenant_id == tenant_id)
        if application_id is not None:
            conditions.append(WorkOrder.application_id == application_id)
        if project_id is not None:
            conditions.append(WorkOrder.project_id == project_id)
        return conditions

    @staticmethod
    def _scope_condition(
        scope: WorkOrderScopeFilter,
        *,
        include_owner_org: bool = False,
    ):
        if scope.all_data:
            return true()
        conditions = []
        if scope.org_ids:
            organization_conditions = [
                WorkOrder.current_org_id.in_(scope.org_ids)
            ]
            if include_owner_org:
                organization_conditions.append(
                    WorkOrder.owner_org_id.in_(scope.org_ids)
                )
            conditions.append(or_(*organization_conditions))
        if scope.self_user_id is not None:
            conditions.append(
                or_(
                    WorkOrder.created_by == scope.self_user_id,
                    WorkOrder.current_assignee_id == scope.self_user_id,
                )
            )
        return or_(*conditions) if conditions else false()
