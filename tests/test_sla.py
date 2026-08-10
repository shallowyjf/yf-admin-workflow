from datetime import datetime

from sqlalchemy.orm import Session

from app.iam.authorization import PermissionService
from app.iam.repository import IAMRepository
from app.iam.seed import seed_iam
from app.iam.service import IAMService
from app.notification.repository import NotificationRepository
from app.notification.service import NotificationService
from app.workorder.repository import WorkOrderRepository
from app.workorder.seed import seed_workorder
from app.workorder.service import (
    CreateWorkOrderCommand,
    WorkOrderActor,
    WorkOrderService,
)
from app.workorder.sla import SlaCalendar


def test_business_calendar_skips_nights_and_weekends() -> None:
    friday = datetime(2026, 8, 7, 17, 50)

    assert SlaCalendar.add_minutes(friday, 30, "BUSINESS_HOURS") == datetime(
        2026, 8, 10, 9, 20
    )
    assert SlaCalendar.add_minutes(friday, 240, "BUSINESS_HOURS") == datetime(
        2026, 8, 10, 12, 50
    )
    assert SlaCalendar.add_minutes(friday, 60, "24X7") == datetime(
        2026, 8, 7, 18, 50
    )


def test_sla_evaluation_is_idempotent_and_generates_notifications(
    db_session: Session,
) -> None:
    iam_repository = IAMRepository(db_session)
    iam = IAMService(iam_repository)
    seed_iam(iam)
    repository = WorkOrderRepository(db_session)
    seed_workorder(repository)
    notification_service = NotificationService(NotificationRepository(db_session))
    now = [datetime(2026, 8, 10, 10, 0)]
    service = WorkOrderService(
        repository,
        PermissionService(iam_repository),
        notification_service=notification_service,
        clock=lambda: now[0],
    )
    manager = iam.get_user("zhangsan")
    pipe_org = iam.get_organization("PIPE_OPERATION")
    assert manager is not None and pipe_org is not None
    actor = WorkOrderActor(manager.id, pipe_org.id)

    work_order = service.create(
        CreateWorkOrderCommand(
            title="SLA 验收",
            work_order_type="REPAIR",
            priority="HIGH",
        ),
        actor,
    )
    assert work_order.response_due_at == datetime(2026, 8, 10, 10, 30)
    assert work_order.due_at == datetime(2026, 8, 10, 14, 0)
    assert work_order.sla_status == "ON_TRACK"

    now[0] = datetime(2026, 8, 10, 10, 31)
    first = service.evaluate_sla(actor)
    second = service.evaluate_sla(actor)
    assert first.response_breaches == 1
    assert second.response_breaches == 0
    assert work_order.sla_status == "RESPONSE_BREACHED"

    now[0] = datetime(2026, 8, 10, 14, 1)
    resolution = service.evaluate_sla(actor)
    assert resolution.resolution_breaches == 1
    assert work_order.sla_status == "RESOLUTION_BREACHED"
    assert [
        action.action_type for action in repository.list_actions(work_order.id)
    ] == [
        "CREATE",
        "SLA_RESPONSE_BREACH",
        "SLA_RESOLUTION_BREACH",
    ]
    notifications = notification_service.list_for_user(manager.id)
    assert [item.event_type for item in notifications] == [
        "SLA_RESOLUTION_BREACH",
        "SLA_RESPONSE_BREACH",
    ]
