from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import Settings
from app.db.base import Base
from app.db.session import Database
from app.iam.repository import IAMRepository
from app.iam.seed import DEMO_INITIAL_PASSWORD, seed_iam
from app.iam.service import IAMService
from app.project.models import Project, ProjectMember
from app.project.repository import ProjectRepository
from app.project.seed import seed_projects
from app.workflow.models import WorkflowTask, WorkflowTaskCandidate
from app.workflow.repository import WorkflowRepository
from app.workflow.seed import seed_workflow


@pytest.fixture()
def i22_environment(tmp_path: Path) -> Iterator[tuple[TestClient, str]]:
    database_url = f"sqlite:///{(tmp_path / 'i22.db').as_posix()}"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    with database.session_factory() as session:
        iam_service = IAMService(IAMRepository(session))
        seed_iam(iam_service)
        seed_projects(ProjectRepository(session, 1), iam_service)
        seed_workflow(WorkflowRepository(session))
    database.dispose()
    settings = Settings(
        app_name="I22 project work-order context",
        environment="test",
        database_url=database_url,
        auth_cookie_secure=False,
    )
    with TestClient(create_app(settings)) as client:
        yield client, database_url


def create_app(settings: Settings):
    # Local import keeps model registration complete before create_all above.
    from app.main import create_app as application_factory

    return application_factory(settings)


def _login(client: TestClient, username: str) -> dict:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": DEMO_INITIAL_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()


def test_work_order_queries_and_mutations_are_isolated_by_active_project(
    i22_environment: tuple[TestClient, str],
) -> None:
    client, _ = i22_environment
    profile = _login(client, "wangwu")
    created = client.post("/api/workorders", json={"title": "供水项目工单", "type": "REPAIR"})
    assert created.status_code == 201
    payload = created.json()
    assert payload["tenant_id"] == profile["tenant_id"]
    assert payload["application_id"] == profile["active_application_id"]
    assert payload["project_id"] == profile["active_project_id"]

    drainage_project = next(
        item for item in profile["projects"] if item["project_code"] == "DR_FLOOD_CONTROL"
    )
    assert (
        client.post("/auth/active-project", json={"project_id": drainage_project["id"]}).status_code
        == 200
    )
    assert client.get("/api/workorders").json() == []
    assert client.get(f"/api/workorders/{payload['id']}").status_code == 404
    assert client.post(f"/api/workorders/{payload['id']}/submit", json={}).status_code == 403


def test_workflow_candidates_are_intersected_with_project_members(
    i22_environment: tuple[TestClient, str],
) -> None:
    client, database_url = i22_environment
    database = Database(database_url)
    with database.session_factory() as session:
        project = session.scalar(
            select(Project).where(Project.project_code == "WS_NETWORK_RENEWAL")
        )
        zhaoliu = IAMService(IAMRepository(session)).get_user("zhaoliu")
        assert project is not None and zhaoliu is not None
        membership_ids = [item.id for item in zhaoliu.memberships]
        session.execute(
            delete(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_org_id.in_(membership_ids),
            )
        )
        session.commit()
    database.dispose()
    profile = _login(client, "wangwu")
    pipe_org_id = next(
        item["id"] for item in profile["organizations"] if item["org_code"] == "PIPE_OPERATION"
    )
    created = client.post(
        "/api/workorders", json={"title": "候选人项目过滤", "type": "REPAIR"}
    ).json()
    assert client.post(f"/api/workorders/{created['id']}/submit", json={}).status_code == 200
    assert (
        client.post(
            f"/api/workorders/{created['id']}/dispatch",
            json={"target_org_id": pipe_org_id},
        ).status_code
        == 200
    )

    database = Database(database_url)
    with database.session_factory() as session:
        task = session.scalar(
            select(WorkflowTask)
            .where(WorkflowTask.task_type == "HANDLE")
            .order_by(WorkflowTask.id.desc())
        )
        assert task is not None
        candidates = set(
            session.scalars(
                select(WorkflowTaskCandidate.resolved_user_id).where(
                    WorkflowTaskCandidate.task_id == task.id
                )
            )
        )
        lisi = IAMService(IAMRepository(session)).get_user("lisi")
        zhaoliu = IAMService(IAMRepository(session)).get_user("zhaoliu")
        assert lisi is not None and zhaoliu is not None
        assert candidates == {lisi.id}
        assert zhaoliu.id not in candidates
        assert (task.tenant_id, task.application_id, task.project_id) == (
            profile["tenant_id"],
            profile["active_application_id"],
            profile["active_project_id"],
        )
    database.dispose()


def test_review_task_moves_to_project_reviewer_and_reject_returns_to_handler(
    i22_environment: tuple[TestClient, str],
) -> None:
    client, _ = i22_environment
    regulator = _login(client, "regulator")
    regulator_org_id = regulator["active_org_id"]
    wangwu = _login(client, "wangwu")
    pipe_org_id = next(
        item["id"]
        for item in wangwu["organizations"]
        if item["org_code"] == "PIPE_OPERATION"
    )
    created = client.post(
        "/api/workorders", json={"title": "监管复核组织联动", "type": "REPAIR"}
    ).json()
    assert client.post(
        f"/api/workorders/{created['id']}/submit", json={}
    ).status_code == 200
    assert client.post(
        f"/api/workorders/{created['id']}/dispatch",
        json={"target_org_id": pipe_org_id},
    ).status_code == 200

    _login(client, "lisi")
    assert client.post(
        f"/api/workorders/{created['id']}/claim", json={}
    ).status_code == 200
    result = client.post(
        f"/api/workorders/{created['id']}/result",
        json={"result": "处理完成，提交监管复核"},
    )
    assert result.status_code == 200
    assert result.json()["status"] == "PENDING_REVIEW"
    assert result.json()["current_org_id"] == regulator_org_id

    _login(client, "regulator")
    tasks = client.get("/api/tasks/mine").json()
    review_task = next(
        item
        for item in tasks
        if item["business_id"] == created["id"] and item["task_type"] == "REVIEW"
    )
    assert review_task["is_candidate"] is True
    assert client.get(f"/api/workorders/{created['id']}").status_code == 200
    rejected = client.post(
        f"/api/workorders/{created['id']}/review",
        json={"decision": "REJECT", "comment": "补充现场照片"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "PROCESSING"
    assert rejected.json()["current_org_id"] == pipe_org_id


def test_archived_project_is_read_only_for_existing_work_orders(
    i22_environment: tuple[TestClient, str],
) -> None:
    client, database_url = i22_environment
    profile = _login(client, "admin")
    created = client.post(
        "/api/workorders", json={"title": "归档项目只读", "type": "INSPECTION"}
    ).json()
    database = Database(database_url)
    with database.session_factory() as session:
        project = session.get(Project, profile["active_project_id"])
        assert project is not None
        project.project_status = "ARCHIVED"
        session.commit()
    database.dispose()

    assert client.get(f"/api/workorders/{created['id']}").status_code == 200
    forbidden = client.post(f"/api/workorders/{created['id']}/submit", json={})
    assert forbidden.status_code == 403
    assert "仅允许只读" in forbidden.json()["detail"]
