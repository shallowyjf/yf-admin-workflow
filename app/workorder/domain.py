"""Work-order domain values and errors."""

from enum import StrEnum


class WorkOrderStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_DISPATCH = "PENDING_DISPATCH"
    PENDING_CLAIM = "PENDING_CLAIM"
    PROCESSING = "PROCESSING"
    PENDING_REVIEW = "PENDING_REVIEW"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"


class WorkOrderActionType(StrEnum):
    CREATE = "CREATE"
    SUBMIT = "SUBMIT"
    DISPATCH = "DISPATCH"
    CLAIM = "CLAIM"
    SUBMIT_RESULT = "SUBMIT_RESULT"
    REJECT = "REJECT"
    APPROVE = "APPROVE"
    CLOSE = "CLOSE"


class WorkOrderError(Exception):
    """Base class for work-order use-case errors."""


class WorkOrderNotFound(WorkOrderError):
    """Raised when a visible work order does not exist."""


class WorkOrderPermissionDenied(WorkOrderError):
    """Raised when functional or object-level permission is missing."""


class InvalidWorkOrderTransition(WorkOrderError):
    """Raised when an action is not valid for the current status."""


class WorkOrderNumberExhausted(WorkOrderError):
    """Raised when the four-digit daily sequence is exhausted."""


class WorkOrderValidationError(WorkOrderError):
    """Raised when a service command contains invalid business data."""
