from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.iam.authorization import PermissionService
from app.iam.identity import IdentityQueryService
from app.iam.repository import IAMRepository
from app.iam.seed import seed_iam
from app.iam.service import IAMService
from app.workflow.candidate import (
    CandidateResolverRegistry,
    CandidateRule,
    CandidateType,
)
from app.workflow.domain import (
    NoWorkflowCandidates,
    WorkflowDefinitionNotFound,
    WorkflowInstanceConflict,
)
from app.workflow.models import (
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowTask,
    WorkflowTaskCandidate,
    WorkflowTaskHistory,
)
from app.workflow.repository import WorkflowRepository
from app.workflow.seed import seed_workflow
from app.workflow.service import WorkflowService
from app.workorder.models import WorkOrder
from app.workorder.repository import WorkOrderRepository
from app.workorder.service import (
    CreateWorkOrderCommand,
    WorkOrderActor,
    WorkOrderService,
)


@pytest.fixture()
def workflow_environment(
    db_session: Session,
) -> tuple[IAMService, WorkflowService]:
    iam_repository = IAMRepository(db_session)
    iam_service = IAMService(iam_repository)
    seed_iam(iam_service)
    workflow_repository = WorkflowRepository(db_session)
    seed_workflow(workflow_repository)
    workflow_service = WorkflowService(
        workflow_repository,
        CandidateResolverRegistry.default(
            IdentityQueryService(iam_repository)
        ),
    )
    return iam_service, workflow_service


def _user_id(service: IAMService, username: str) -> int:
    user = service.get_user(username)
    assert user is not None
    return user.id


def _org_id(service: IAMService, org_code: str) -> int:
    organization = service.get_organization(org_code)
    assert organization is not None
    return organization.id


def test_start_for_workorder_is_one_to_one(
    workflow_environment: tuple[IAMService, WorkflowService],
    db_session: Session,
) -> None:
    iam_service, workflow_service = workflow_environment
    wangwu_id = _user_id(iam_service, "wangwu")

    instance = workflow_service.start_for_workorder(1001, wangwu_id)

    assert instance.business_type == "WORK_ORDER"
    assert instance.business_id == 1001
    assert instance.status == "RUNNING"
    assert instance.current_node == "DISPATCH"
    assert db_session.scalar(select(func.count(WorkflowInstance.id))) == 1
    with pytest.raises(WorkflowInstanceConflict):
        workflow_service.start_for_workorder(1001, wangwu_id)


def test_create_task_persists_rule_candidates_and_history(
    workflow_environment: tuple[IAMService, WorkflowService],
    db_session: Session,
) -> None:
    iam_service, workflow_service = workflow_environment
    wangwu_id = _user_id(iam_service, "wangwu")
    lisi_id = _user_id(iam_service, "lisi")
    zhaoliu_id = _user_id(iam_service, "zhaoliu")
    instance = workflow_service.start_for_workorder(1002, wangwu_id)

    task = workflow_service.create_task(
        instance.id,
        "handle",
        CandidateRule(
            CandidateType.ORG_ROLE,
            org_id=_org_id(iam_service, "PIPE_OPERATION"),
            role_code="REPAIRER",
        ),
        operator_id=wangwu_id,
    )

    assert task.task_type == "HANDLE"
    assert task.status == "PENDING"
    assert task.assignee_id is None
    assert task.candidate_rule_json["candidate_type"] == "ORG_ROLE"
    candidates = db_session.scalars(
        select(WorkflowTaskCandidate).where(
            WorkflowTaskCandidate.task_id == task.id
        )
    ).all()
    assert {candidate.resolved_user_id for candidate in candidates} == {
        lisi_id,
        zhaoliu_id,
    }
    history = db_session.scalar(
        select(WorkflowTaskHistory).where(
            WorkflowTaskHistory.task_id == task.id
        )
    )
    assert history is not None
    assert history.action == "CREATE"
    assert history.operator_id == wangwu_id


def test_empty_candidate_rule_does_not_create_task(
    workflow_environment: tuple[IAMService, WorkflowService],
    db_session: Session,
) -> None:
    iam_service, workflow_service = workflow_environment
    wangwu_id = _user_id(iam_service, "wangwu")
    instance = workflow_service.start_for_workorder(1003, wangwu_id)

    with pytest.raises(NoWorkflowCandidates):
        workflow_service.create_task(
            instance.id,
            "HANDLE",
            CandidateRule(
                CandidateType.ORG_ROLE,
                org_id=_org_id(iam_service, "DISPATCH_CENTER"),
                role_code="REPAIRER",
            ),
        )

    assert db_session.scalar(select(func.count(WorkflowTask.id))) == 0


def test_my_tasks_include_candidates_but_not_unrelated_users(
    workflow_environment: tuple[IAMService, WorkflowService],
) -> None:
    iam_service, workflow_service = workflow_environment
    wangwu_id = _user_id(iam_service, "wangwu")
    instance = workflow_service.start_for_workorder(1004, wangwu_id)
    workflow_service.create_task(
        instance.id,
        "HANDLE",
        CandidateRule(CandidateType.ROLE, role_code="REPAIRER"),
    )

    assert len(workflow_service.list_my_tasks(_user_id(iam_service, "lisi"))) == 1
    assert len(
        workflow_service.list_my_tasks(_user_id(iam_service, "zhaoliu"))
    ) == 1
    assert workflow_service.list_my_tasks(_user_id(iam_service, "admin")) == []


def test_workflow_seed_is_idempotent(
    workflow_environment: tuple[IAMService, WorkflowService],
    db_session: Session,
) -> None:
    del workflow_environment
    repository = WorkflowRepository(db_session)

    seed_workflow(repository)

    assert db_session.scalar(select(func.count(WorkflowDefinition.id))) == 1


def test_workflow_core_does_not_depend_on_iam_persistence() -> None:
    for filename in ("service.py", "repository.py"):
        source = Path(f"app/workflow/{filename}").read_text(encoding="utf-8")
        assert "app.iam.models" not in source
        assert "app.iam.repository" not in source


def test_submit_rolls_back_when_workflow_cannot_start(
    db_session: Session,
) -> None:
    iam_repository = IAMRepository(db_session)
    iam_service = IAMService(iam_repository)
    seed_iam(iam_service)
    work_order_repository = WorkOrderRepository(db_session)
    workflow_service = WorkflowService(
        WorkflowRepository(db_session),
        CandidateResolverRegistry.default(
            IdentityQueryService(iam_repository)
        ),
    )
    work_order_service = WorkOrderService(
        work_order_repository,
        PermissionService(iam_repository),
        workflow_service,
    )
    user = iam_service.get_user("wangwu")
    organization = iam_service.get_organization("DISPATCH_CENTER")
    assert user is not None and organization is not None
    actor = WorkOrderActor(user.id, organization.id)
    work_order = work_order_service.create(
        CreateWorkOrderCommand(title="事务回滚", work_order_type="REPAIR"),
        actor,
    )

    with pytest.raises(WorkflowDefinitionNotFound):
        work_order_service.submit(work_order.id, actor)

    db_session.expire_all()
    persisted = db_session.get(WorkOrder, work_order.id)
    assert persisted is not None
    assert persisted.status == "DRAFT"
    assert [
        action.action_type
        for action in work_order_repository.list_actions(work_order.id)
    ] == ["CREATE"]
