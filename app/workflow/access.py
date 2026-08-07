"""Object-level access rules for workflow tasks."""

from .domain import TaskAccessDenied
from .models import WorkflowTask


class TaskAccessService:
    @staticmethod
    def is_candidate(task: WorkflowTask, user_id: int) -> bool:
        return any(
            candidate.resolved_user_id == user_id
            for candidate in task.candidates
        )

    def require_candidate(self, task: WorkflowTask, user_id: int) -> None:
        if not self.is_candidate(task, user_id):
            raise TaskAccessDenied(
                f"user {user_id} is not a candidate for task {task.id}"
            )

    @staticmethod
    def require_assignee(task: WorkflowTask, user_id: int) -> None:
        if task.assignee_id != user_id:
            raise TaskAccessDenied(
                f"user {user_id} is not the assignee for task {task.id}"
            )

    def require_candidate_or_assignee(
        self,
        task: WorkflowTask,
        user_id: int,
    ) -> None:
        if task.assignee_id != user_id and not self.is_candidate(task, user_id):
            raise TaskAccessDenied(
                f"user {user_id} cannot execute task {task.id}"
            )
