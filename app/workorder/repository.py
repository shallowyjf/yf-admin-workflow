"""Persistence for work orders and their action timeline."""

from sqlalchemy import false, func, or_, select, true
from sqlalchemy.orm import Session

from app.iam.authorization import WorkOrderScopeFilter

from .models import WorkOrder, WorkOrderAction


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
        include_owner_org: bool = False,
    ) -> WorkOrder | None:
        return self.session.scalar(
            select(WorkOrder).where(
                WorkOrder.id == work_order_id,
                self._scope_condition(scope, include_owner_org=include_owner_org),
            )
        )

    def list_visible(self, scope: WorkOrderScopeFilter) -> list[WorkOrder]:
        return list(
            self.session.scalars(
                select(WorkOrder)
                .where(self._scope_condition(scope))
                .order_by(WorkOrder.created_at.desc(), WorkOrder.id.desc())
            )
        )

    def list_actions(self, work_order_id: int) -> list[WorkOrderAction]:
        return list(
            self.session.scalars(
                select(WorkOrderAction)
                .where(WorkOrderAction.work_order_id == work_order_id)
                .order_by(WorkOrderAction.created_at, WorkOrderAction.id)
            )
        )

    def latest_number_for_prefix(self, prefix: str) -> str | None:
        return self.session.scalar(
            select(func.max(WorkOrder.work_order_no)).where(
                WorkOrder.work_order_no.like(f"{prefix}%")
            )
        )

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
