"""Partial-success batch work-order orchestration."""

from dataclasses import dataclass

from app.workflow.domain import WorkflowError

from .domain import WorkOrderError
from .service import WorkOrderActor, WorkOrderService


@dataclass(frozen=True)
class BatchItemResult:
    work_order_id: int
    success: bool
    detail: str


@dataclass(frozen=True)
class BatchActionResult:
    items: list[BatchItemResult]

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def succeeded(self) -> int:
        return sum(item.success for item in self.items)

    @property
    def failed(self) -> int:
        return self.total - self.succeeded


class WorkOrderBatchService:
    MAX_ITEMS = 100

    def __init__(self, work_order_service: WorkOrderService) -> None:
        self.work_order_service = work_order_service

    def dispatch(
        self,
        work_order_ids: list[int],
        target_org_id: int,
        actor: WorkOrderActor,
        comment: str | None = None,
    ) -> BatchActionResult:
        return self._run(
            work_order_ids,
            lambda work_order_id: self.work_order_service.dispatch(
                work_order_id,
                target_org_id,
                actor,
                comment,
            ),
        )

    def urge(
        self,
        work_order_ids: list[int],
        actor: WorkOrderActor,
        comment: str,
    ) -> BatchActionResult:
        return self._run(
            work_order_ids,
            lambda work_order_id: self.work_order_service.urge(
                work_order_id,
                actor,
                comment,
            ),
        )

    def _run(self, work_order_ids: list[int], operation) -> BatchActionResult:
        normalized = list(dict.fromkeys(work_order_ids))
        if not normalized or len(normalized) > self.MAX_ITEMS:
            raise ValueError("batch must contain 1..100 unique work orders")
        results: list[BatchItemResult] = []
        for work_order_id in normalized:
            try:
                operation(work_order_id)
            except (WorkOrderError, WorkflowError, ValueError) as error:
                results.append(BatchItemResult(work_order_id, False, str(error)))
            else:
                results.append(BatchItemResult(work_order_id, True, "OK"))
        return BatchActionResult(results)
