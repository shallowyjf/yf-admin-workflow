"""Workflow instance and human-task use cases."""

from collections.abc import Callable
from datetime import datetime

from .access import TaskAccessService
from .candidate import CandidateResolverRegistry, CandidateRule, CandidateType
from .domain import (
    InvalidWorkflowTaskState,
    NoWorkflowCandidates,
    TaskAlreadyClaimed,
    WorkflowDefinitionNotFound,
    WorkflowInstanceConflict,
    WorkflowInstanceNotFound,
    WorkflowInstanceStatus,
    WorkflowTaskNotFound,
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
        task_access: TaskAccessService | None = None,
        candidate_filter: Callable[[int, set[int], str], set[int]] | None = None,
        *,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.repository = repository
        self.candidate_resolvers = candidate_resolvers
        self.task_access = task_access or TaskAccessService()
        self.candidate_filter = candidate_filter
        self.clock = clock

    def start_for_workorder(
        self,
        workorder_id: int,
        initiator_id: int,
        tenant_id: int = 1,
        application_id: int = 1,
        project_id: int = 1,
    ) -> WorkflowInstance:
        instance = self._new_instance(
            workorder_id, initiator_id, tenant_id, application_id, project_id
        )
        self.repository.commit()
        self.repository.refresh(instance)
        return instance

    def start_submitted_workorder(
        self,
        work_order_id: int,
        initiator_id: int,
        tenant_id: int = 1,
        application_id: int = 1,
        project_id: int = 1,
    ) -> WorkflowInstance:
        """Atomically start a submitted work order and create its dispatch task."""
        try:
            instance = self._new_instance(
                work_order_id, initiator_id, tenant_id, application_id, project_id
            )
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

    def list_my_tasks(
        self, user_id: int, tenant_id: int | None = None,
        application_id: int | None = None, project_id: int | None = None,
    ) -> list[WorkflowTask]:
        return self.repository.list_my_tasks(
            user_id, tenant_id=tenant_id,
            application_id=application_id, project_id=project_id,
        )

    def dispatch_workorder(
        self,
        work_order_id: int,
        operator_id: int,
        target_org_id: int,
    ) -> WorkflowTask:
        try:
            current_task = self._current_task(work_order_id, "DISPATCH")
            self.task_access.require_candidate_or_assignee(
                current_task,
                operator_id,
            )
            self._finish_task(current_task, operator_id, "COMPLETE")
            current_task.instance.current_node = "HANDLE"
            next_task = self._new_task(
                current_task.instance,
                "HANDLE",
                CandidateRule(
                    CandidateType.ORG_ROLE,
                    org_id=target_org_id,
                    role_code="REPAIRER",
                ),
                operator_id=operator_id,
            )
            self.repository.commit()
            self.repository.refresh(next_task)
            return next_task
        except Exception:
            self.repository.rollback()
            raise

    def claim_workorder(
        self,
        work_order_id: int,
        user_id: int,
    ) -> WorkflowTask:
        try:
            task = self._current_task(work_order_id, "HANDLE")
            self.task_access.require_candidate(task, user_id)
            claimed_at = self.clock()
            if not self.repository.claim_if_unassigned(
                task.id,
                user_id,
                claimed_at,
            ):
                raise TaskAlreadyClaimed(f"task already claimed: {task.id}")
            self.repository.add(
                WorkflowTaskHistory(
                    task_id=task.id,
                    action="CLAIM",
                    operator_id=user_id,
                    payload_json={"assignee_id": user_id},
                )
            )
            self.repository.commit()
            self.repository.refresh(task)
            return task
        except Exception:
            self.repository.rollback()
            raise

    def submit_workorder_result(
        self,
        work_order_id: int,
        operator_id: int,
        review_org_id: int,
        payload: dict | None = None,
    ) -> WorkflowTask:
        try:
            current_task = self._current_task(work_order_id, "HANDLE")
            self.task_access.require_assignee(current_task, operator_id)
            self._finish_task(
                current_task,
                operator_id,
                "COMPLETE",
                payload,
            )
            current_task.instance.current_node = "REVIEW"
            next_task = self._new_task(
                current_task.instance,
                "REVIEW",
                CandidateRule(
                    CandidateType.ORG_ROLE,
                    org_id=review_org_id,
                    role_code="REVIEWER",
                ),
                operator_id=operator_id,
            )
            self.repository.commit()
            self.repository.refresh(next_task)
            return next_task
        except Exception:
            self.repository.rollback()
            raise

    def transfer_workorder(
        self,
        work_order_id: int,
        operator_id: int,
        target_user_id: int,
    ) -> WorkflowTask:
        """Atomically replace the assignee of the active handle task."""

        try:
            task = self._current_task(work_order_id, "HANDLE")
            if (
                task.status != WorkflowTaskStatus.CLAIMED.value
                or task.assignee_id is None
            ):
                raise InvalidWorkflowTaskState(
                    f"cannot transfer unclaimed task: {task.id}"
                )
            if task.assignee_id == target_user_id:
                raise InvalidWorkflowTaskState(
                    f"target user already owns task: {task.id}"
                )
            previous_assignee_id = task.assignee_id
            task.assignee_id = target_user_id
            task.claimed_at = self.clock()
            task.candidate_rule_json = {
                "candidate_type": CandidateType.USER.value,
                "user_id": target_user_id,
            }
            self.repository.add(
                WorkflowTaskHistory(
                    task_id=task.id,
                    action="TRANSFER",
                    operator_id=operator_id,
                    payload_json={
                        "previous_assignee_id": previous_assignee_id,
                        "target_assignee_id": target_user_id,
                    },
                )
            )
            self.repository.commit()
            self.repository.refresh(task)
            return task
        except Exception:
            self.repository.rollback()
            raise

    def review_workorder(
        self,
        work_order_id: int,
        operator_id: int,
        decision: str,
        original_assignee_id: int | None,
    ) -> WorkflowTask | None:
        try:
            current_task = self._current_task(work_order_id, "REVIEW")
            self.task_access.require_candidate_or_assignee(
                current_task,
                operator_id,
            )
            normalized_decision = decision.strip().upper()
            if normalized_decision == "APPROVE":
                self._finish_task(
                    current_task,
                    operator_id,
                    "COMPLETE",
                    {"decision": normalized_decision},
                )
                current_task.instance.status = WorkflowInstanceStatus.COMPLETED.value
                current_task.instance.current_node = "END"
                current_task.instance.completed_at = self.clock()
                next_task = None
            elif normalized_decision == "REJECT":
                if original_assignee_id is None:
                    raise InvalidWorkflowTaskState(
                        "cannot return work order without original assignee"
                    )
                self._finish_task(
                    current_task,
                    operator_id,
                    "RETURN",
                    {"decision": normalized_decision},
                )
                current_task.instance.current_node = "HANDLE"
                next_task = self._new_assigned_task(
                    current_task.instance,
                    "HANDLE",
                    original_assignee_id,
                    operator_id,
                )
            else:
                raise InvalidWorkflowTaskState(
                    f"unsupported review decision: {decision}"
                )
            self.repository.commit()
            if next_task is not None:
                self.repository.refresh(next_task)
            return next_task
        except Exception:
            self.repository.rollback()
            raise

    def _current_task(
        self,
        work_order_id: int,
        task_type: str,
    ) -> WorkflowTask:
        task = self.repository.get_current_task_for_business(
            self.BUSINESS_TYPE,
            work_order_id,
            task_type,
        )
        if task is None:
            raise WorkflowTaskNotFound(
                f"active {task_type} task not found for work order: {work_order_id}"
            )
        return task

    def _finish_task(
        self,
        task: WorkflowTask,
        operator_id: int,
        history_action: str,
        payload: dict | None = None,
    ) -> None:
        if task.status not in {
            WorkflowTaskStatus.PENDING.value,
            WorkflowTaskStatus.CLAIMED.value,
        }:
            raise InvalidWorkflowTaskState(
                f"cannot finish task {task.id} from status {task.status}"
            )
        task.status = WorkflowTaskStatus.COMPLETED.value
        task.completed_at = self.clock()
        self.repository.add(
            WorkflowTaskHistory(
                task_id=task.id,
                action=history_action,
                operator_id=operator_id,
                payload_json=payload,
            )
        )

    def _new_assigned_task(
        self,
        instance: WorkflowInstance,
        task_type: str,
        assignee_id: int,
        operator_id: int,
    ) -> WorkflowTask:
        task = self._new_task(
            instance,
            task_type,
            CandidateRule(CandidateType.USER, user_id=assignee_id),
            operator_id=operator_id,
        )
        task.status = WorkflowTaskStatus.CLAIMED.value
        task.assignee_id = assignee_id
        task.claimed_at = self.clock()
        self.repository.add(
            WorkflowTaskHistory(
                task_id=task.id,
                action="ASSIGN",
                operator_id=operator_id,
                payload_json={"assignee_id": assignee_id},
            )
        )
        return task

    def _new_instance(
        self,
        work_order_id: int,
        initiator_id: int,
        tenant_id: int = 1,
        application_id: int = 1,
        project_id: int = 1,
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
            tenant_id=tenant_id,
            application_id=application_id,
            project_id=project_id,
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
        if self.candidate_filter is not None:
            permission_code = {
                "DISPATCH": "workorder:dispatch",
                "HANDLE": "workorder:handle",
                "REVIEW": "workorder:review",
            }.get(normalized_task_type, "workorder:view")
            candidate_ids = self.candidate_filter(
                instance.project_id, set(candidate_ids), permission_code
            )
        if not candidate_ids:
            raise NoWorkflowCandidates(
                f"candidate rule resolved no users: {candidate_rule.candidate_type}"
            )
        rule_payload = self._candidate_rule_payload(candidate_rule)
        task = WorkflowTask(
            instance_id=instance.id,
            tenant_id=instance.tenant_id,
            application_id=instance.application_id,
            project_id=instance.project_id,
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
        ):
            value = getattr(candidate_rule, field_name)
            if value is not None:
                payload[field_name] = value
        return payload
