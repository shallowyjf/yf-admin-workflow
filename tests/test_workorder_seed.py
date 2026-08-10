from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.workorder.models import WorkOrderSlaPolicy
from app.workorder.repository import WorkOrderRepository
from app.workorder.seed import seed_workorder


def test_workorder_seed_is_idempotent_and_creates_default_sla_policies(
    db_session: Session,
) -> None:
    repository = WorkOrderRepository(db_session)

    seed_workorder(repository)
    seed_workorder(repository)

    assert (
        db_session.scalar(select(func.count()).select_from(WorkOrderSlaPolicy))
        == 3
    )
    urgent = repository.get_sla_policy("URGENT")
    high = repository.get_sla_policy("HIGH")
    normal = repository.get_sla_policy("NORMAL")
    assert urgent is not None and high is not None and normal is not None
    assert (urgent.response_minutes, urgent.resolve_minutes, urgent.calendar_code) == (
        10,
        60,
        "24X7",
    )
    assert high.calendar_code == "BUSINESS_HOURS"
    assert normal.resolve_minutes == 480
