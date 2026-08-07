"""Workflow persistence operations."""

from datetime import datetime

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from .domain import WorkflowTaskStatus
from .models import (
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowTask,
    WorkflowTaskCandidate,
)


class WorkflowRepository:
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

    def rollback(self) -> None:
        self.session.rollback()

    def get_active_definition(self, code: str) -> WorkflowDefinition | None:
        return self.session.scalar(
            select(WorkflowDefinition)
            .where(
                WorkflowDefinition.code == code,
                WorkflowDefinition.is_active.is_(True),
            )
            .order_by(WorkflowDefinition.version.desc())
        )

    def get_definition(
        self,
        code: str,
        version: int,
    ) -> WorkflowDefinition | None:
        return self.session.scalar(
            select(WorkflowDefinition).where(
                WorkflowDefinition.code == code,
                WorkflowDefinition.version == version,
            )
        )

    def get_instance_for_business(
        self,
        business_type: str,
        business_id: int,
    ) -> WorkflowInstance | None:
        return self.session.scalar(
            select(WorkflowInstance).where(
                WorkflowInstance.business_type == business_type,
                WorkflowInstance.business_id == business_id,
            )
        )

    def get_instance(self, instance_id: int) -> WorkflowInstance | None:
        return self.session.get(WorkflowInstance, instance_id)

    def get_current_task_for_business(
        self,
        business_type: str,
        business_id: int,
        task_type: str,
    ) -> WorkflowTask | None:
        return self.session.scalar(
            select(WorkflowTask)
            .join(
                WorkflowInstance,
                WorkflowInstance.id == WorkflowTask.instance_id,
            )
            .where(
                WorkflowInstance.business_type == business_type,
                WorkflowInstance.business_id == business_id,
                WorkflowTask.task_type == task_type,
                WorkflowTask.status.in_(
                    [
                        WorkflowTaskStatus.PENDING.value,
                        WorkflowTaskStatus.CLAIMED.value,
                    ]
                ),
            )
            .options(
                joinedload(WorkflowTask.instance),
                selectinload(WorkflowTask.candidates),
            )
            .order_by(WorkflowTask.id.desc())
        )

    def claim_if_unassigned(
        self,
        task_id: int,
        user_id: int,
        claimed_at: datetime,
    ) -> bool:
        result = self.session.execute(
            update(WorkflowTask)
            .where(
                WorkflowTask.id == task_id,
                WorkflowTask.status == WorkflowTaskStatus.PENDING.value,
                WorkflowTask.assignee_id.is_(None),
            )
            .values(
                status=WorkflowTaskStatus.CLAIMED.value,
                assignee_id=user_id,
                claimed_at=claimed_at,
            )
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    def list_my_tasks(self, user_id: int) -> list[WorkflowTask]:
        statement = (
            select(WorkflowTask)
            .join(WorkflowInstance, WorkflowInstance.id == WorkflowTask.instance_id)
            .outerjoin(
                WorkflowTaskCandidate,
                WorkflowTaskCandidate.task_id == WorkflowTask.id,
            )
            .where(
                or_(
                    and_(
                        WorkflowTask.status == WorkflowTaskStatus.PENDING.value,
                        WorkflowTaskCandidate.resolved_user_id == user_id,
                    ),
                    and_(
                        WorkflowTask.status == WorkflowTaskStatus.CLAIMED.value,
                        WorkflowTask.assignee_id == user_id,
                    ),
                )
            )
            .options(
                joinedload(WorkflowTask.instance),
                selectinload(WorkflowTask.candidates),
            )
            .order_by(WorkflowTask.created_at.desc(), WorkflowTask.id.desc())
        )
        return list(self.session.scalars(statement).unique())
