import pytest

from app.workorder.domain import (
    InvalidWorkOrderTransition,
    WorkOrderActionType,
    WorkOrderStatus,
)
from app.workorder.state_machine import WorkOrderStateMachine


@pytest.mark.parametrize(
    ("from_status", "action", "to_status"),
    [
        ("DRAFT", "SUBMIT", "PENDING_DISPATCH"),
        ("PENDING_DISPATCH", "DISPATCH", "PENDING_CLAIM"),
        ("PENDING_CLAIM", "CLAIM", "PROCESSING"),
        ("PROCESSING", "SUBMIT_RESULT", "PENDING_REVIEW"),
        ("PENDING_REVIEW", "REJECT", "PROCESSING"),
        ("PENDING_REVIEW", "APPROVE", "COMPLETED"),
        ("COMPLETED", "CLOSE", "CLOSED"),
    ],
)
def test_state_machine_allows_only_declared_transitions(
    from_status: str,
    action: str,
    to_status: str,
) -> None:
    assert (
        WorkOrderStateMachine.transition(from_status, action).value == to_status
    )


@pytest.mark.parametrize(
    ("from_status", "action"),
    [
        (WorkOrderStatus.PENDING_DISPATCH, WorkOrderActionType.CLAIM),
        (WorkOrderStatus.PROCESSING, WorkOrderActionType.CLOSE),
        (WorkOrderStatus.CLOSED, WorkOrderActionType.SUBMIT),
    ],
)
def test_state_machine_rejects_illegal_transitions(
    from_status: WorkOrderStatus,
    action: WorkOrderActionType,
) -> None:
    with pytest.raises(InvalidWorkOrderTransition):
        WorkOrderStateMachine.transition(from_status, action)
