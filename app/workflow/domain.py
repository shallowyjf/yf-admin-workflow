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


class NoWorkflowCandidates(WorkflowError):
    """Raised when a task rule resolves to no active users."""
