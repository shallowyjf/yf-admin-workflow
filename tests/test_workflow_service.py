from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import Database
from app.iam.authorization import PermissionService
from app.iam.identity import IdentityQueryService
from app.iam.repository import IAMRepository
from app.iam.seed import seed_iam
from app.iam.service import IAMService
from app.workflow.access import TaskAccessService
from app.workflow.candidate import (
    CandidateResolverRegistry,
    CandidateRule,
    CandidateType,
)
from app.workflow.domain import (
    NoWorkflowCandidates,
    TaskAccessDenied,
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


def test_task_access_separates_candidate_and_assignee_rules(
    workflow_environment: tuple[IAMService, WorkflowService],
) -> None:
    iam_service, workflow_service = workflow_environment
    wangwu_id = _user_id(iam_service, "wangwu")
    lisi_id = _user_id(iam_service, "lisi")
    instance = workflow_service.start_for_workorder(2001, wangwu_id)
    task = workflow_service.create_task(
        instance.id,
        "HANDLE",
        CandidateRule(CandidateType.USER, user_id=lisi_id),
    )
    task = workflow_service.repository.get_current_task_for_business(
        "WORK_ORDER",
        2001,
        "HANDLE",
    )
    assert task is not None
    access = TaskAccessService()

    access.require_candidate(task, lisi_id)
    with pytest.raises(TaskAccessDenied):
        access.require_candidate(task, wangwu_id)
    with pytest.raises(TaskAccessDenied):
        access.require_assignee(task, lisi_id)


def test_atomic_claim_allows_only_one_preloaded_candidate(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'claim.db').as_posix()}")
    Base.metadata.create_all(database.engine)
    try:
        with database.session_factory() as setup_session:
            iam_repository = IAMRepository(setup_session)
            iam_service = IAMService(iam_repository)
            seed_iam(iam_service)
            workflow_repository = WorkflowRepository(setup_session)
            seed_workflow(workflow_repository)
            workflow_service = WorkflowService(
                workflow_repository,
                CandidateResolverRegistry.default(
                    IdentityQueryService(iam_repository)
                ),
            )
            wangwu_id = _user_id(iam_service, "wangwu")
            pipe_org_id = _org_id(iam_service, "PIPE_OPERATION")
            lisi_id = _user_id(iam_service, "lisi")
            zhaoliu_id = _user_id(iam_service, "zhaoliu")
            workflow_service.start_submitted_workorder(2002, wangwu_id)
            workflow_service.dispatch_workorder(
                2002,
                wangwu_id,
                pipe_org_id,
            )

        with (
            database.session_factory() as first_session,
            database.session_factory() as second_session,
        ):
            first_repository = WorkflowRepository(first_session)
            second_repository = WorkflowRepository(second_session)
            first_task = first_repository.get_current_task_for_business(
                "WORK_ORDER",
                2002,
                "HANDLE",
            )
            second_task = second_repository.get_current_task_for_business(
                "WORK_ORDER",
                2002,
                "HANDLE",
            )
            assert first_task is not None and second_task is not None
            assert first_task.id == second_task.id

            assert first_repository.claim_if_unassigned(
                first_task.id,
                lisi_id,
                datetime(2026, 8, 7, 12, 0),
            )
            first_repository.commit()
            assert not second_repository.claim_if_unassigned(
                second_task.id,
                zhaoliu_id,
                datetime(2026, 8, 7, 12, 0),
            )
            second_repository.rollback()
    finally:
        database.dispose()


def test_task_actions_record_claim_complete_return_and_assignment_history(
    workflow_environment: tuple[IAMService, WorkflowService],
    db_session: Session,
) -> None:
    iam_service, workflow_service = workflow_environment
    wangwu_id = _user_id(iam_service, "wangwu")
    lisi_id = _user_id(iam_service, "lisi")
    pipe_org_id = _org_id(iam_service, "PIPE_OPERATION")
    dispatch_org_id = _org_id(iam_service, "DISPATCH_CENTER")
    workflow_service.start_submitted_workorder(2003, wangwu_id)
    workflow_service.dispatch_workorder(2003, wangwu_id, pipe_org_id)
    workflow_service.claim_workorder(2003, lisi_id)
    workflow_service.submit_workorder_result(
        2003,
        lisi_id,
        dispatch_org_id,
        {"result": "fixed"},
    )

    returned_task = workflow_service.review_workorder(
        2003,
        wangwu_id,
        "REJECT",
        lisi_id,
    )

    assert returned_task is not None
    assert returned_task.status == "CLAIMED"
    assert returned_task.assignee_id == lisi_id
    actions = db_session.scalars(
        select(WorkflowTaskHistory.action).order_by(WorkflowTaskHistory.id)
    ).all()
    assert actions == [
        "CREATE",
        "COMPLETE",
        "CREATE",
        "CLAIM",
        "COMPLETE",
        "CREATE",
        "RETURN",
        "CREATE",
        "ASSIGN",
    ]


def test_transfer_reassigns_claimed_handle_task_and_records_history(
    workflow_environment: tuple[IAMService, WorkflowService],
    db_session: Session,
) -> None:
    iam_service, workflow_service = workflow_environment
    wangwu_id = _user_id(iam_service, "wangwu")
    lisi_id = _user_id(iam_service, "lisi")
    zhaoliu_id = _user_id(iam_service, "zhaoliu")
    pipe_org_id = _org_id(iam_service, "PIPE_OPERATION")
    workflow_service.start_submitted_workorder(2004, wangwu_id)
    workflow_service.dispatch_workorder(2004, wangwu_id, pipe_org_id)
    workflow_service.claim_workorder(2004, lisi_id)

    transferred = workflow_service.transfer_workorder(
        2004,
        wangwu_id,
        zhaoliu_id,
    )

    assert transferred.status == "CLAIMED"
    assert transferred.assignee_id == zhaoliu_id
    assert transferred.candidate_rule_json == {
        "candidate_type": "USER",
        "user_id": zhaoliu_id,
    }
    transfer_history = db_session.scalars(
        select(WorkflowTaskHistory)
        .where(WorkflowTaskHistory.action == "TRANSFER")
        .order_by(WorkflowTaskHistory.id)
    ).one()
    assert transfer_history.operator_id == wangwu_id
    assert transfer_history.payload_json == {
        "previous_assignee_id": lisi_id,
        "target_assignee_id": zhaoliu_id,
    }
