from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.iam.repository import IAMRepository
from app.iam.seed import seed_iam
from app.iam.service import IAMService
from app.notification.models import Notification
from app.notification.repository import NotificationRepository
from app.notification.service import NotificationNotFound, NotificationService
from app.workorder.models import WorkOrder


def test_notification_read_receipt_retry_and_ownership(db_session: Session) -> None:
    iam = IAMService(IAMRepository(db_session))
    seed_iam(iam)
    lisi = iam.get_user("lisi")
    zhaoliu = iam.get_user("zhaoliu")
    assert lisi is not None and zhaoliu is not None
    pipe_org = iam.get_organization("PIPE_OPERATION")
    assert pipe_org is not None
    work_order = WorkOrder(
        work_order_no="WO202608109901",
        title="通知测试工单",
        work_order_type="REPAIR",
        priority="NORMAL",
        owner_org_id=pipe_org.id,
        current_org_id=pipe_org.id,
        current_assignee_id=lisi.id,
        status="PROCESSING",
        created_by=lisi.id,
    )
    db_session.add(work_order)
    db_session.flush()
    repository = NotificationRepository(db_session)
    service = NotificationService(
        repository,
        clock=lambda: datetime(2026, 8, 10, 15, 0),
    )
    notification = service.stage_work_order(
        lisi.id,
        work_order.id,
        "WORKORDER_URGED",
        "工单收到催办",
        "请尽快处理",
    )
    repository.commit()
    repository.refresh(notification)

    with pytest.raises(NotificationNotFound):
        service.mark_read(notification.id, zhaoliu.id)
    read = service.mark_read(notification.id, lisi.id)
    assert read.status == "READ"
    assert read.read_at == datetime(2026, 8, 10, 15, 0)

    failed = Notification(
        user_id=lisi.id,
        event_type="DELIVERY_TEST",
        title="失败通知",
        content="等待重试",
        status="FAILED",
        delivery_attempts=1,
        last_error="temporary failure",
    )
    repository.add(failed)
    repository.commit()
    repository.refresh(failed)
    retried = service.retry_failed(failed.id, lisi.id)
    assert retried.status == "UNREAD"
    assert retried.delivery_attempts == 2
    assert retried.last_error is None
