"""Workflow instance and human-task use cases."""

from collections.abc import Callable
from datetime import datetime

from .candidate import CandidateResolverRegistry, CandidateRule, CandidateType
from .domain import (
    NoWorkflowCandidates,
    WorkflowDefinitionNotFound,
    WorkflowInstanceConflict,
    WorkflowInstanceNotFound,
    WorkflowInstanceStatus,
    WorkflowTaskStatus,
)
from .models import (
    WorkflowInstance,
    WorkflowTask,
    WorkflowTaskCandidate,
    WorkflowTaskHistory,
)
from .repository import WorkflowRepository


class WorkflowService:
    DEFINITION_CODE = "WORK_ORDER_STANDARD"
    BUSINESS_TYPE = "WORK_ORDER"
    FIRST_TASK_TYPE = "DISPATCH"

    def __init__(
        self,
        repository: WorkflowRepository,
        candidate_resolvers: CandidateResolverRegistry,
        *,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.repository = repository
        self.candidate_resolvers = candidate_resolvers
        self.clock = clock

    def start_for_workorder(
        self,
        workorder_id: int,
        initiator_id: int,
    ) -> WorkflowInstance:
        instance = self._new_instance(workorder_id, initiator_id)
        self.repository.commit()
        self.repository.refresh(instance)
        return instance

    def start_submitted_workorder(
        self,
        work_order_id: int,
        initiator_id: int,
    ) -> WorkflowInstance:
        """Atomically start a submitted work order and create its dispatch task."""
        try:
            instance = self._new_instance(work_order_id, initiator_id)
            self._new_task(
                instance,
                self.FIRST_TASK_TYPE,
                CandidateRule(CandidateType.USER, user_id=initiator_id),
                operator_id=initiator_id,
            )
            self.repository.commit()
            self.repository.refresh(instance)
            return instance
        except Exception:
            self.repository.rollback()
            raise

    def create_task(
        self,
        instance_id: int,
        task_type: str,
        candidate_rule: CandidateRule,
        *,
        operator_id: int | None = None,
    ) -> WorkflowTask:
        instance = self.repository.get_instance(instance_id)
        if instance is None:
            raise WorkflowInstanceNotFound(
                f"workflow instance not found: {instance_id}"
            )
        task = self._new_task(
            instance,
            task_type,
            candidate_rule,
            operator_id=operator_id,
        )
        self.repository.commit()
        self.repository.refresh(task)
        return task

    def list_my_tasks(self, user_id: int) -> list[WorkflowTask]:
        return self.repository.list_my_tasks(user_id)

    def _new_instance(
        self,
        work_order_id: int,
        initiator_id: int,
    ) -> WorkflowInstance:
        if self.repository.get_instance_for_business(
            self.BUSINESS_TYPE,
            work_order_id,
        ):
            raise WorkflowInstanceConflict(
                f"workflow already exists for work order: {work_order_id}"
            )
        definition = self.repository.get_active_definition(self.DEFINITION_CODE)
        if definition is None:
            raise WorkflowDefinitionNotFound(
                f"active workflow definition not found: {self.DEFINITION_CODE}"
            )
        instance = WorkflowInstance(
            definition_id=definition.id,
            business_type=self.BUSINESS_TYPE,
            business_id=work_order_id,
            status=WorkflowInstanceStatus.RUNNING.value,
            current_node=self.FIRST_TASK_TYPE,
            initiator_id=initiator_id,
            started_at=self.clock(),
        )
        self.repository.add(instance)
        self.repository.flush()
        return instance

    def _new_task(
        self,
        instance: WorkflowInstance,
        task_type: str,
        candidate_rule: CandidateRule,
        *,
        operator_id: int | None,
    ) -> WorkflowTask:
        if instance.status != WorkflowInstanceStatus.RUNNING.value:
            raise WorkflowInstanceConflict(
                f"workflow instance is not running: {instance.id}"
            )
        normalized_task_type = task_type.strip().upper()
        if not normalized_task_type:
            raise ValueError("task_type must not be blank")
        candidate_ids = self.candidate_resolvers.resolve(candidate_rule)
        if not candidate_ids:
            raise NoWorkflowCandidates(
                f"candidate rule resolved no users: {candidate_rule.candidate_type}"
            )
        rule_payload = self._candidate_rule_payload(candidate_rule)
        task = WorkflowTask(
            instance_id=instance.id,
            task_type=normalized_task_type,
            status=WorkflowTaskStatus.PENDING.value,
            candidate_rule_json=rule_payload,
        )
        self.repository.add(task)
        self.repository.flush()
        candidate_type = CandidateType(candidate_rule.candidate_type).value
        for user_id in sorted(candidate_ids):
            self.repository.add(
                WorkflowTaskCandidate(
                    task_id=task.id,
                    candidate_type=candidate_type,
                    candidate_value=rule_payload,
                    resolved_user_id=user_id,
                )
            )
        self.repository.add(
            WorkflowTaskHistory(
                task_id=task.id,
                action="CREATE",
                operator_id=operator_id,
                payload_json={
                    "task_type": normalized_task_type,
                    "candidate_user_ids": sorted(candidate_ids),
                },
            )
        )
        return task

    @staticmethod
    def _candidate_rule_payload(candidate_rule: CandidateRule) -> dict:
        payload: dict[str, str | int] = {
            "candidate_type": CandidateType(candidate_rule.candidate_type).value
        }
        for field_name in (
            "user_id",
            "org_id",
            "role_code",
            "position_code",
        ):
            value = getattr(candidate_rule, field_name)
            if value is not None:
                payload[field_name] = value
        return payload
