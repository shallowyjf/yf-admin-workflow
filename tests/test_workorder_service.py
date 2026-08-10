from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.iam.authorization import PermissionService, WorkOrderScopeFilter
from app.iam.repository import IAMRepository
from app.iam.seed import seed_iam
from app.iam.service import IAMService
from app.workorder.domain import (
    InvalidWorkOrderTransition,
    WorkOrderNotFound,
    WorkOrderPermissionDenied,
    WorkOrderValidationError,
)
from app.workorder.models import WorkOrder
from app.workorder.repository import WorkOrderRepository
from app.workorder.service import (
    CreateWorkOrderCommand,
    WorkOrderActor,
    WorkOrderService,
)

FIXED_NOW = datetime(2026, 8, 7, 9, 30)


@pytest.fixture()
def work_order_environment(
    db_session: Session,
) -> tuple[IAMService, WorkOrderService, WorkOrderRepository]:
    iam_repository = IAMRepository(db_session)
    iam = IAMService(iam_repository)
    seed_iam(iam)
    repository = WorkOrderRepository(db_session)
    service = WorkOrderService(
        repository,
        PermissionService(iam_repository),
        clock=lambda: FIXED_NOW,
    )
    return iam, service, repository


def _actor(iam: IAMService, username: str, org_code: str) -> WorkOrderActor:
    user = iam.get_user(username)
    organization = iam.get_organization(org_code)
    assert user is not None and organization is not None
    return WorkOrderActor(user.id, organization.id)


def _command(title: str = "DMA 分区压力异常") -> CreateWorkOrderCommand:
    return CreateWorkOrderCommand(
        title=title,
        work_order_type="DMA_PRESSURE_ANOMALY",
        priority="HIGH",
        location="城北 DMA",
        description="夜间最小流量异常",
    )


def test_create_generates_daily_number_and_create_action(
    work_order_environment: tuple[IAMService, WorkOrderService, WorkOrderRepository],
) -> None:
    iam, service, repository = work_order_environment
    actor = _actor(iam, "wangwu", "DISPATCH_CENTER")

    first = service.create(_command(), actor)
    second = service.create(_command("第二张工单"), actor)

    assert first.work_order_no == "WO202608070001"
    assert second.work_order_no == "WO202608070002"
    assert first.status == "DRAFT"
    assert first.owner_org_id == actor.active_org_id
    assert first.current_org_id == actor.active_org_id
    actions = repository.list_actions(first.id)
    assert [(item.action_type, item.from_status, item.to_status) for item in actions] == [
        ("CREATE", None, "DRAFT")
    ]


def test_submit_is_creator_only_and_records_transition(
    work_order_environment: tuple[IAMService, WorkOrderService, WorkOrderRepository],
) -> None:
    iam, service, repository = work_order_environment
    creator = _actor(iam, "wangwu", "DISPATCH_CENTER")
    other_creator = _actor(iam, "zhangsan", "PIPE_OPERATION")
    work_order = service.create(_command(), creator)

    with pytest.raises(WorkOrderPermissionDenied):
        service.submit(work_order.id, other_creator)

    submitted = service.submit(work_order.id, creator, "提交调度")

    assert submitted.status == "PENDING_DISPATCH"
    actions = repository.list_actions(work_order.id)
    assert [action.action_type for action in actions] == ["CREATE", "SUBMIT"]
    assert actions[-1].from_status == "DRAFT"
    assert actions[-1].to_status == "PENDING_DISPATCH"
    assert actions[-1].comment == "提交调度"

    with pytest.raises(InvalidWorkOrderTransition):
        service.submit(work_order.id, creator)


def test_create_requires_stable_permission_code(
    work_order_environment: tuple[IAMService, WorkOrderService, WorkOrderRepository],
) -> None:
    iam, service, _ = work_order_environment

    with pytest.raises(WorkOrderPermissionDenied):
        service.create(_command(), _actor(iam, "lisi", "PIPE_OPERATION"))

    with pytest.raises(WorkOrderValidationError):
        service.create(_command("   "), _actor(iam, "wangwu", "DISPATCH_CENTER"))


def test_repository_applies_org_and_self_scope_as_sql_filters(
    work_order_environment: tuple[IAMService, WorkOrderService, WorkOrderRepository],
    db_session: Session,
) -> None:
    iam, _, repository = work_order_environment
    pipe_org = iam.get_organization("PIPE_OPERATION")
    team_org = iam.get_organization("INSPECTION_TEAM_1")
    wangwu = iam.get_user("wangwu")
    lisi = iam.get_user("lisi")
    assert pipe_org is not None and team_org is not None
    assert wangwu is not None and lisi is not None

    pipe_order = WorkOrder(
        work_order_no="WO202608079001",
        title="管网运行部工单",
        work_order_type="REPAIR",
        priority="NORMAL",
        owner_org_id=pipe_org.id,
        current_org_id=pipe_org.id,
        status="DRAFT",
        created_by=wangwu.id,
    )
    team_order = WorkOrder(
        work_order_no="WO202608079002",
        title="巡检一组工单",
        work_order_type="INSPECTION",
        priority="NORMAL",
        owner_org_id=team_org.id,
        current_org_id=team_org.id,
        current_assignee_id=lisi.id,
        status="DRAFT",
        created_by=wangwu.id,
    )
    db_session.add_all([pipe_order, team_order])
    db_session.commit()

    assert repository.list_visible(WorkOrderScopeFilter(org_ids={pipe_org.id})) == [
        pipe_order
    ]
    assert set(
        repository.list_visible(
            WorkOrderScopeFilter(org_ids={pipe_org.id, team_org.id})
        )
    ) == {pipe_order, team_order}
    assert repository.list_visible(WorkOrderScopeFilter(self_user_id=lisi.id)) == [
        team_order
    ]


def test_service_list_and_detail_use_real_data_scope(
    work_order_environment: tuple[IAMService, WorkOrderService, WorkOrderRepository],
) -> None:
    iam, service, _ = work_order_environment
    dispatch_actor = _actor(iam, "wangwu", "DISPATCH_CENTER")
    pipe_actor = _actor(iam, "zhangsan", "PIPE_OPERATION")
    admin_actor = _actor(iam, "admin", "GROUP")
    repairer_actor = _actor(iam, "lisi", "PIPE_OPERATION")
    dispatch_order = service.create(_command("调度中心工单"), dispatch_actor)
    pipe_order = service.create(_command("管网运行部工单"), pipe_actor)

    assert service.list_visible(dispatch_actor) == [dispatch_order]
    assert service.list_visible(pipe_actor) == [pipe_order]
    assert set(service.list_visible(admin_actor)) == {dispatch_order, pipe_order}
    assert service.list_visible(repairer_actor) == []
    with pytest.raises(WorkOrderNotFound, match="not found"):
        service.get_visible(dispatch_order.id, repairer_actor)


def test_service_and_router_do_not_assign_status_directly() -> None:
    for path in (
        Path("app/workorder/service.py"),
        Path("app/workorder/router.py"),
        Path("app/workorder/repository.py"),
    ):
        assert ".status =" not in path.read_text(encoding="utf-8")


def test_transfer_comment_and_urge_are_permission_checked_and_audited(
    work_order_environment: tuple[IAMService, WorkOrderService, WorkOrderRepository],
) -> None:
    iam, service, repository = work_order_environment
    manager = _actor(iam, "zhangsan", "PIPE_OPERATION")
    lisi = _actor(iam, "lisi", "PIPE_OPERATION")
    zhaoliu = _actor(iam, "zhaoliu", "PIPE_OPERATION")
    wangwu = iam.get_user("wangwu")
    assert wangwu is not None

    work_order = service.create(_command("协作能力验收"), manager)
    service.add_comment(work_order.id, manager, "  建单后补充现场联系人  ")
    with pytest.raises(InvalidWorkOrderTransition):
        service.urge(work_order.id, manager, "草稿不能催办")

    service.submit(work_order.id, manager)
    service.dispatch(work_order.id, manager.active_org_id, manager)
    service.claim(work_order.id, lisi)
    service.urge(work_order.id, manager, "请在 30 分钟内反馈")

    with pytest.raises(WorkOrderValidationError, match="active handler"):
        service.transfer(work_order.id, wangwu.id, manager)
    transferred = service.transfer(
        work_order.id,
        zhaoliu.user_id,
        manager,
        "李四下班，转赵六继续处理",
    )

    assert transferred.current_assignee_id == zhaoliu.user_id
    with pytest.raises(WorkOrderNotFound):
        service.add_comment(work_order.id, lisi, "转派后不再可见")
    comment = service.add_comment(work_order.id, zhaoliu, "已接手处理")
    assert comment.comment == "已接手处理"
    actions = repository.list_actions(work_order.id)
    assert [item.action_type for item in actions] == [
        "CREATE",
        "COMMENT",
        "SUBMIT",
        "DISPATCH",
        "CLAIM",
        "URGE",
        "TRANSFER",
        "COMMENT",
    ]
    assert actions[1].comment == "建单后补充现场联系人"
    assert actions[-2].payload_json == {
        "previous_assignee_id": lisi.user_id,
        "target_assignee_id": zhaoliu.user_id,
    }


def test_comment_validation_rejects_blank_and_oversized_text(
    work_order_environment: tuple[IAMService, WorkOrderService, WorkOrderRepository],
) -> None:
    iam, service, _ = work_order_environment
    manager = _actor(iam, "zhangsan", "PIPE_OPERATION")
    work_order = service.create(_command("评论校验"), manager)

    with pytest.raises(WorkOrderValidationError, match="blank"):
        service.add_comment(work_order.id, manager, "   ")
    with pytest.raises(WorkOrderValidationError, match="1000"):
        service.add_comment(work_order.id, manager, "x" * 1001)
