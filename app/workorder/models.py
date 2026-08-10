"""Work-order aggregate and immutable action timeline records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import IdTimestampMixin

from .domain import InvalidWorkOrderTransition, WorkOrderActionType, WorkOrderStatus
from .state_machine import WorkOrderStateMachine


class WorkOrder(IdTimestampMixin, Base):
    __tablename__ = "wo_work_order"
    __table_args__ = (
        Index("ix_wo_work_order_status", "status"),
        Index("ix_wo_work_order_current_org_id", "current_org_id"),
        Index("ix_wo_work_order_current_assignee_id", "current_assignee_id"),
        Index("ix_wo_work_order_created_at", "created_at"),
    )

    work_order_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    work_order_type: Mapped[str] = mapped_column("type", String(60), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(60))
    source_id: Mapped[str | None] = mapped_column(String(120))
    priority: Mapped[str] = mapped_column(String(30), nullable=False, default="NORMAL")
    owner_org_id: Mapped[int] = mapped_column(
        ForeignKey("sys_org.id", ondelete="RESTRICT"),
        nullable=False,
    )
    current_org_id: Mapped[int] = mapped_column(
        ForeignKey("sys_org.id", ondelete="RESTRICT"),
        nullable=False,
    )
    current_assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("sys_user.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=WorkOrderStatus.DRAFT.value,
    )
    asset_type: Mapped[str | None] = mapped_column(String(60))
    asset_id: Mapped[str | None] = mapped_column(String(120))
    location: Mapped[str | None] = mapped_column(String(500))
    longitude: Mapped[float | None] = mapped_column(Float)
    latitude: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="RESTRICT"),
        nullable=False,
    )

    actions: Mapped[list[WorkOrderAction]] = relationship(
        back_populates="work_order",
        cascade="all, delete-orphan",
    )

    def submit(self) -> tuple[str, str]:
        return self._transition(WorkOrderActionType.SUBMIT)

    def dispatch(self, target_org_id: int) -> tuple[str, str]:
        transition = self._transition(WorkOrderActionType.DISPATCH)
        self.current_org_id = target_org_id
        self.current_assignee_id = None
        return transition

    def claim(self, user_id: int) -> tuple[str, str]:
        transition = self._transition(WorkOrderActionType.CLAIM)
        self.current_assignee_id = user_id
        return transition

    def submit_result(self) -> tuple[str, str]:
        return self._transition(WorkOrderActionType.SUBMIT_RESULT)

    def transfer(self, target_user_id: int) -> int:
        if (
            self.status != WorkOrderStatus.PROCESSING.value
            or self.current_assignee_id is None
        ):
            raise InvalidWorkOrderTransition(
                f"cannot TRANSFER work order from {self.status}"
            )
        if self.current_assignee_id == target_user_id:
            raise InvalidWorkOrderTransition("target user is already the assignee")
        previous_assignee_id = self.current_assignee_id
        self.current_assignee_id = target_user_id
        return previous_assignee_id

    def reject(self) -> tuple[str, str]:
        return self._transition(WorkOrderActionType.REJECT)

    def approve(self, occurred_at: datetime) -> tuple[str, str]:
        transition = self._transition(WorkOrderActionType.APPROVE)
        self.completed_at = occurred_at
        return transition

    def close(self, occurred_at: datetime) -> tuple[str, str]:
        transition = self._transition(WorkOrderActionType.CLOSE)
        self.closed_at = occurred_at
        return transition

    def _transition(
        self,
        action: WorkOrderActionType,
    ) -> tuple[str, str]:
        previous_status = self.status
        self.status = WorkOrderStateMachine.transition(self.status, action).value
        return previous_status, self.status


class WorkOrderAction(IdTimestampMixin, Base):
    __tablename__ = "wo_action"
    __table_args__ = (
        Index("ix_wo_action_work_order_id", "work_order_id"),
        Index("ix_wo_action_created_at", "created_at"),
    )

    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("wo_work_order.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(String(60), nullable=False)
    operator_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="RESTRICT"),
        nullable=False,
    )
    from_status: Mapped[str | None] = mapped_column(String(40))
    to_status: Mapped[str] = mapped_column(String(40), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    payload_json: Mapped[dict | None] = mapped_column(JSON)

    work_order: Mapped[WorkOrder] = relationship(back_populates="actions")
