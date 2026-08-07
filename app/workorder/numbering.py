"""Work-order business number generation."""

from datetime import datetime

from .domain import WorkOrderNumberExhausted
from .repository import WorkOrderRepository


class WorkOrderNumberService:
    def __init__(self, repository: WorkOrderRepository) -> None:
        self.repository = repository

    def next_number(self, now: datetime) -> str:
        prefix = f"WO{now:%Y%m%d}"
        latest = self.repository.latest_number_for_prefix(prefix)
        sequence = int(latest[-4:]) + 1 if latest else 1
        if sequence > 9999:
            raise WorkOrderNumberExhausted(f"daily sequence exhausted: {prefix}")
        return f"{prefix}{sequence:04d}"
