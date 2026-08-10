"""Idempotent default SLA policy seed."""

from dataclasses import dataclass

from app.core.config import get_settings
from app.db.session import Database

from .models import WorkOrderSlaPolicy
from .repository import WorkOrderRepository
from .sla import DEFAULT_SLA_POLICIES


@dataclass(frozen=True)
class WorkOrderSeedSummary:
    sla_policies: int = 3


def seed_workorder(repository: WorkOrderRepository) -> WorkOrderSeedSummary:
    for item in DEFAULT_SLA_POLICIES:
        policy = repository.get_sla_policy(item.priority, active_only=False)
        if policy is None:
            repository.add(
                WorkOrderSlaPolicy(
                    priority=item.priority,
                    response_minutes=item.response_minutes,
                    resolve_minutes=item.resolve_minutes,
                    calendar_code=item.calendar_code,
                )
            )
        else:
            policy.response_minutes = item.response_minutes
            policy.resolve_minutes = item.resolve_minutes
            policy.calendar_code = item.calendar_code
            policy.is_active = True
    repository.commit()
    return WorkOrderSeedSummary()


def main() -> None:
    database = Database(get_settings().database_url)
    try:
        with database.session_factory() as session:
            summary = seed_workorder(WorkOrderRepository(session))
        print(f"Work-order seed ready: {summary.sla_policies} SLA policies")
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
