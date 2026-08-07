"""Central work-order status transition rules."""

from .domain import (
    InvalidWorkOrderTransition,
    WorkOrderActionType,
    WorkOrderStatus,
)


class WorkOrderStateMachine:
    TRANSITIONS = {
        (WorkOrderStatus.DRAFT, WorkOrderActionType.SUBMIT): (
            WorkOrderStatus.PENDING_DISPATCH
        ),
        (WorkOrderStatus.PENDING_DISPATCH, WorkOrderActionType.DISPATCH): (
            WorkOrderStatus.PENDING_CLAIM
        ),
        (WorkOrderStatus.PENDING_CLAIM, WorkOrderActionType.CLAIM): (
            WorkOrderStatus.PROCESSING
        ),
        (WorkOrderStatus.PROCESSING, WorkOrderActionType.SUBMIT_RESULT): (
            WorkOrderStatus.PENDING_REVIEW
        ),
        (WorkOrderStatus.PENDING_REVIEW, WorkOrderActionType.REJECT): (
            WorkOrderStatus.PROCESSING
        ),
        (WorkOrderStatus.PENDING_REVIEW, WorkOrderActionType.APPROVE): (
            WorkOrderStatus.COMPLETED
        ),
        (WorkOrderStatus.COMPLETED, WorkOrderActionType.CLOSE): (
            WorkOrderStatus.CLOSED
        ),
    }

    @classmethod
    def transition(
        cls,
        current_status: WorkOrderStatus | str,
        action: WorkOrderActionType | str,
    ) -> WorkOrderStatus:
        try:
            status = WorkOrderStatus(current_status)
            action_type = WorkOrderActionType(action)
            return cls.TRANSITIONS[(status, action_type)]
        except (ValueError, KeyError) as error:
            raise InvalidWorkOrderTransition(
                f"cannot {action} work order from status {current_status}"
            ) from error
