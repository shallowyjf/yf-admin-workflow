"""Workflow definition, instance, task, candidate, and history models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import IdTimestampMixin

from .domain import WorkflowInstanceStatus, WorkflowTaskStatus


class WorkflowDefinition(IdTimestampMixin, Base):
    __tablename__ = "wf_definition"
    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_wf_definition_code_version"),
    )

    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )


class WorkflowInstance(IdTimestampMixin, Base):
    __tablename__ = "wf_instance"
    __table_args__ = (
        UniqueConstraint("business_type", "business_id", name="uq_wf_instance_business"),
        Index("ix_wf_instance_definition_id", "definition_id"),
        Index("ix_wf_instance_context", "tenant_id", "application_id", "project_id"),
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
    definition_id: Mapped[int] = mapped_column(
        ForeignKey("wf_definition.id", ondelete="RESTRICT"),
        nullable=False,
    )
    business_type: Mapped[str] = mapped_column(String(60), nullable=False)
    business_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=WorkflowInstanceStatus.RUNNING.value,
    )
    current_node: Mapped[str] = mapped_column(String(80), nullable=False)
    initiator_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="RESTRICT"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    tasks: Mapped[list[WorkflowTask]] = relationship(
        back_populates="instance",
        cascade="all, delete-orphan",
    )


class WorkflowTask(IdTimestampMixin, Base):
    __tablename__ = "wf_task"
    __table_args__ = (
        Index("ix_wf_task_status_assignee_id", "status", "assignee_id"),
        Index("ix_wf_task_instance_id", "instance_id"),
        Index(
            "ix_wf_task_context_status",
            "tenant_id", "application_id", "project_id", "status",
        ),
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
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("wf_instance.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=WorkflowTaskStatus.PENDING.value,
    )
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("sys_user.id", ondelete="SET NULL")
    )
    candidate_rule_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    instance: Mapped[WorkflowInstance] = relationship(back_populates="tasks")
    candidates: Mapped[list[WorkflowTaskCandidate]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    history: Mapped[list[WorkflowTaskHistory]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )


class WorkflowTaskCandidate(IdTimestampMixin, Base):
    __tablename__ = "wf_task_candidate"
    __table_args__ = (
        UniqueConstraint("task_id", "resolved_user_id", name="uq_wf_task_candidate_user"),
        Index("ix_wf_task_candidate_task_user", "task_id", "resolved_user_id"),
    )

    task_id: Mapped[int] = mapped_column(
        ForeignKey("wf_task.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_type: Mapped[str] = mapped_column(String(40), nullable=False)
    candidate_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    resolved_user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="CASCADE"),
        nullable=False,
    )

    task: Mapped[WorkflowTask] = relationship(back_populates="candidates")


class WorkflowTaskHistory(IdTimestampMixin, Base):
    __tablename__ = "wf_task_history"
    __table_args__ = (Index("ix_wf_task_history_task_id", "task_id"),)

    task_id: Mapped[int] = mapped_column(
        ForeignKey("wf_task.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("sys_user.id", ondelete="SET NULL"))
    payload_json: Mapped[dict | None] = mapped_column(JSON)

    task: Mapped[WorkflowTask] = relationship(back_populates="history")
