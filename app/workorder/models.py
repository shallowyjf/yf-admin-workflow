"""Work-order aggregate and immutable action timeline records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import IdTimestampMixin

from .domain import InvalidWorkOrderTransition, WorkOrderActionType, WorkOrderStatus
from .state_machine import WorkOrderStateMachine


class WorkOrder(IdTimestampMixin, Base):
    __tablename__ = "wo_work_order"
    __table_args__ = (
        Index("ix_wo_work_order_context", "tenant_id", "application_id", "project_id"),
        Index("ix_wo_work_order_status", "status"),
        Index("ix_wo_work_order_current_org_id", "current_org_id"),
        Index("ix_wo_work_order_current_assignee_id", "current_assignee_id"),
        Index("ix_wo_work_order_created_at", "created_at"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("sys_tenant.id", ondelete="RESTRICT"), nullable=False,
        default=1, server_default=text("1"),
    )
    application_id: Mapped[int] = mapped_column(
        ForeignKey("sys_application.id", ondelete="RESTRICT"), nullable=False,
        default=1, server_default=text("1"),
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("pm_project.id", ondelete="RESTRICT"), nullable=False,
        default=1, server_default=text("1"),
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
    response_due_at: Mapped[datetime | None] = mapped_column(DateTime)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime)
    sla_status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="NOT_APPLICABLE",
        server_default=text("'NOT_APPLICABLE'"),
    )
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
    attachments: Mapped[list[WorkOrderAttachment]] = relationship(
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

    def mark_responded(self, occurred_at: datetime) -> None:
        if self.responded_at is None:
            self.responded_at = occurred_at
        if self.response_due_at is not None and occurred_at > self.response_due_at:
            self.sla_status = "RESPONSE_BREACHED"

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


class WorkOrderSlaPolicy(IdTimestampMixin, Base):
    __tablename__ = "wo_sla_policy"
    __table_args__ = (
        UniqueConstraint("priority", name="uq_wo_sla_policy_priority"),
    )

    priority: Mapped[str] = mapped_column(String(30), nullable=False)
    response_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    resolve_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    calendar_code: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )


class WorkOrderAttachment(IdTimestampMixin, Base):
    __tablename__ = "wo_attachment"
    __table_args__ = (
        Index("ix_wo_attachment_work_order_id", "work_order_id"),
        Index("ix_wo_attachment_sha256", "sha256"),
    )

    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("wo_work_order.id", ondelete="CASCADE"),
        nullable=False,
    )
    uploader_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="RESTRICT"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(20), nullable=False)
    content_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    work_order: Mapped[WorkOrder] = relationship(back_populates="attachments")
