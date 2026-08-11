from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.base import Base
from app.db.session import Database
from app.iam.models import Tenant
from app.iam.repository import IAMRepository
from app.iam.seed import DEMO_INITIAL_PASSWORD, seed_iam
from app.iam.service import IAMService
from app.main import create_app
from app.project.models import (
    Application,
    Project,
    ProjectMember,
    ProjectMilestone,
    ProjectOrganization,
    TenantApplication,
    UserApplicationAccess,
)
from app.project.repository import ProjectRepository
from app.project.seed import ProjectSeedSummary, seed_projects


@pytest.fixture()
def lifeline_client(tmp_path: Path) -> Iterator[TestClient]:
    database_url = f"sqlite:///{(tmp_path / 'i20.db').as_posix()}"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    with database.session_factory() as session:
        iam_service = IAMService(IAMRepository(session))
        seed_iam(iam_service)
        seed_projects(ProjectRepository(session, 1), iam_service)
    database.dispose()

    settings = Settings(
        app_name="I20 city lifeline",
        environment="test",
        database_url=database_url,
        auth_cookie_secure=False,
    )
    with TestClient(create_app(settings)) as client:
        yield client


def _login(client: TestClient, username: str):
    return client.post(
        "/auth/login",
        json={"username": username, "password": DEMO_INITIAL_PASSWORD},
    )


def test_project_seed_is_idempotent_and_builds_default_structure(db_session) -> None:
    iam_service = IAMService(IAMRepository(db_session))
    seed_iam(iam_service)
    repository = ProjectRepository(db_session, 1)

    summary = seed_projects(repository, iam_service)
    seed_projects(repository, iam_service)

    assert summary == ProjectSeedSummary()
    assert db_session.scalar(select(func.count()).select_from(Application)) == 5
    assert db_session.scalar(select(func.count()).select_from(TenantApplication)) == 5
    assert db_session.scalar(select(func.count()).select_from(Project)) == 5
    assert db_session.scalar(select(func.count()).select_from(ProjectOrganization)) == 20
    assert db_session.scalar(select(func.count()).select_from(ProjectMember)) == 36
    assert db_session.scalar(select(func.count()).select_from(ProjectMilestone)) == 20
    assert (
        db_session.scalar(select(func.count()).select_from(UserApplicationAccess))
        == 36
    )


def test_admin_can_view_all_lifeline_systems_projects_and_roles(
    lifeline_client: TestClient,
) -> None:
    assert _login(lifeline_client, "admin").status_code == 200

    response = lifeline_client.get("/api/lifeline/structure")

    assert response.status_code == 200
    payload = response.json()
    assert payload["can_view_all_projects"] is True
    assert {item["application_code"] for item in payload["applications"]} == {
        "WATER_SUPPLY",
        "DRAINAGE",
        "GAS",
        "HEATING",
        "ROAD",
    }
    projects = [
        project
        for application in payload["applications"]
        for project in application["projects"]
    ]
    assert len(projects) == 5
    assert {party["party_type"] for party in projects[0]["organizations"]} == {
        "OWNER",
        "REGULATOR",
        "CONTRACTOR",
        "PLATFORM",
    }
    assert {role["role_code"] for role in payload["role_matrix"]}.issuperset(
        {"OWNER_LEADER", "REVIEWER", "WORKORDER_MANAGER", "PLATFORM_OPERATOR"}
    )

    page = lifeline_client.get("/lifeline")
    assert page.status_code == 200
    assert "城市生命线权限结构" in page.text
    assert "供水管网更新改造工程" in page.text
    assert "默认角色权限矩阵" in page.text


def test_project_member_only_sees_assigned_projects(
    lifeline_client: TestClient,
) -> None:
    profile = _login(lifeline_client, "lisi")
    assert profile.status_code == 200

    response = lifeline_client.get("/api/lifeline/structure")

    assert response.status_code == 200
    payload = response.json()
    assert payload["can_view_all_projects"] is False
    visible_codes = {
        project["project_code"]
        for application in payload["applications"]
        for project in application["projects"]
    }
    assert visible_codes == {
        "WS_NETWORK_RENEWAL",
        "DR_FLOOD_CONTROL",
        "HEAT_PIPE_RENOVATION",
    }


def test_project_structures_are_isolated_by_tenant(db_session) -> None:
    default_iam = IAMService(IAMRepository(db_session))
    seed_iam(default_iam)
    default_repository = ProjectRepository(db_session, 1)
    seed_projects(default_repository, default_iam)

    second_tenant = Tenant(tenant_code="CITY_B", tenant_name="B 市生命线租户")
    db_session.add(second_tenant)
    db_session.commit()
    db_session.refresh(second_tenant)
    second_iam = IAMService(IAMRepository(db_session, second_tenant.id))
    seed_iam(second_iam)
    second_repository = ProjectRepository(db_session, second_tenant.id)
    seed_projects(second_repository, second_iam)

    default_projects = default_repository.list_projects()
    second_projects = second_repository.list_projects()
    assert len(default_projects) == 5
    assert len(second_projects) == 5
    assert {project.tenant_id for project in default_projects} == {1}
    assert {project.tenant_id for project in second_projects} == {second_tenant.id}
    assert {project.id for project in default_projects}.isdisjoint(
        project.id for project in second_projects
    )
