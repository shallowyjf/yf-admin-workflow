from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.base import Base
from app.db.session import Database
from app.iam.repository import IAMRepository
from app.iam.seed import DEMO_INITIAL_PASSWORD, seed_iam
from app.iam.service import IAMService
from app.main import create_app
from app.project.repository import ProjectRepository
from app.project.seed import seed_projects


@pytest.fixture()
def i23_clients(tmp_path: Path) -> Iterator[tuple[TestClient, TestClient]]:
    database_url = f"sqlite:///{(tmp_path / 'i23.db').as_posix()}"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    with database.session_factory() as session:
        iam_service = IAMService(IAMRepository(session))
        seed_iam(iam_service)
        seed_projects(ProjectRepository(session, 1), iam_service)
    database.dispose()
    settings = Settings(
        app_name="I23 demo progress dashboard",
        environment="test",
        database_url=database_url,
        auth_cookie_secure=False,
    )
    with (
        TestClient(create_app(settings)) as first,
        TestClient(create_app(settings)) as second,
    ):
        yield first, second


def _login(client: TestClient, username: str) -> dict:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": DEMO_INITIAL_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()


def test_owner_leader_sees_cross_system_demo_progress_but_cannot_edit(
    i23_clients: tuple[TestClient, TestClient],
) -> None:
    leader_client, _ = i23_clients
    _login(leader_client, "owner_leader")
    response = leader_client.get("/api/lifeline/progress")
    assert response.status_code == 200
    payload = response.json()
    assert payload["can_view_all_projects"] is True
    assert payload["summary"]["project_count"] == 5
    assert payload["summary"]["system_count"] == 5
    assert payload["summary"]["delayed_projects"] >= 1
    assert all(len(item["milestones"]) == 4 for item in payload["projects"])
    assert all(item["can_update"] is False for item in payload["projects"])

    project = payload["projects"][0]
    milestone = project["milestones"][0]
    forbidden = leader_client.put(
        f"/api/lifeline/projects/{project['project_id']}/milestones/{milestone['id']}",
        json={"actual_percent": 100, "status": "COMPLETED"},
    )
    assert forbidden.status_code == 403


def test_admin_can_update_milestone_and_page_reflects_weighted_progress(
    i23_clients: tuple[TestClient, TestClient],
) -> None:
    admin_client, _ = i23_clients
    _login(admin_client, "admin")
    before = admin_client.get("/api/lifeline/progress").json()
    project = before["projects"][1]
    milestone = next(
        item for item in project["milestones"] if item["milestone_code"] == "CONSTRUCTION"
    )
    updated = admin_client.put(
        f"/api/lifeline/projects/{project['project_id']}/milestones/{milestone['id']}",
        json={"actual_percent": 100, "status": "IN_PROGRESS"},
    )
    assert updated.status_code == 200
    payload = updated.json()
    changed = next(
        item for item in payload["milestones"] if item["id"] == milestone["id"]
    )
    assert changed["actual_percent"] == 100
    assert changed["status"] == "COMPLETED"
    assert payload["actual_percent"] > project["actual_percent"]

    page = admin_client.get("/project-progress")
    assert page.status_code == 200
    assert "城市生命线工程项目进度总览" in page.text
    assert project["project_name"] in page.text
    assert "演示操作" in page.text
    audit = admin_client.get("/api/iam/audit-logs").json()
    assert any(item["entity_type"] == "PROJECT_MILESTONE" for item in audit)


def test_project_member_view_excludes_unassigned_new_project(
    i23_clients: tuple[TestClient, TestClient],
) -> None:
    admin_client, manager_client = i23_clients
    admin = _login(admin_client, "admin")
    water_application_id = next(
        item["id"]
        for item in admin["applications"]
        if item["application_code"] == "WATER_SUPPLY"
    )
    created = admin_client.post(
        "/api/lifeline/projects",
        json={
            "application_id": water_application_id,
            "project_code": "I23_LEADER_ONLY",
            "project_name": "领导可见未配置成员项目",
        },
    )
    assert created.status_code == 201
    assert admin_client.get("/api/lifeline/progress").json()["summary"]["project_count"] == 6

    _login(manager_client, "zhangsan")
    manager_progress = manager_client.get("/api/lifeline/progress")
    assert manager_progress.status_code == 200
    assert manager_progress.json()["summary"]["project_count"] == 5
    assert "I23_LEADER_ONLY" not in {
        item["project_code"] for item in manager_progress.json()["projects"]
    }
