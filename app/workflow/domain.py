"""Workflow domain values and errors."""

from enum import StrEnum


class WorkflowInstanceStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class WorkflowTaskStatus(StrEnum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class WorkflowError(Exception):
    """Base workflow error."""


class WorkflowDefinitionNotFound(WorkflowError):
    """Raised when the active standard definition is unavailable."""


class WorkflowInstanceConflict(WorkflowError):
    """Raised when a work order already has an instance."""


class WorkflowInstanceNotFound(WorkflowError):
    """Raised when a referenced instance does not exist."""


class WorkflowTaskNotFound(WorkflowError):
    """Raised when the active task for a business action is unavailable."""


class TaskAccessDenied(WorkflowError):
    """Raised when a user is neither the required candidate nor assignee."""


class TaskAlreadyClaimed(WorkflowError):
    """Raised when an atomic task claim loses to another request."""


class InvalidWorkflowTaskState(WorkflowError):
    """Raised when a task action is invalid for the current task status."""


class NoWorkflowCandidates(WorkflowError):
    """Raised when a task rule resolves to no active users."""
