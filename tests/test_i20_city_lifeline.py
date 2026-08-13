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
    assert db_session.scalar(select(func.count()).select_from(Application)) == (
        summary.applications
    )
    assert db_session.scalar(select(func.count()).select_from(TenantApplication)) == (
        summary.applications
    )
    assert db_session.scalar(select(func.count()).select_from(Project)) == summary.projects
    assert db_session.scalar(select(func.count()).select_from(ProjectOrganization)) == (
        summary.project_organizations
    )
    assert db_session.scalar(select(func.count()).select_from(ProjectMember)) == (
        summary.project_members
    )
    assert db_session.scalar(select(func.count()).select_from(ProjectMilestone)) == (
        summary.milestones
    )
    assert (
        db_session.scalar(select(func.count()).select_from(UserApplicationAccess))
        == summary.user_application_accesses
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
        "WATER_HYDRAULIC",
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
    assert len(projects) == 6
    assert {party["party_type"] for party in projects[0]["organizations"]} == {
        "OWNER",
        "REGULATOR",
        "SUPERVISOR",
        "CONTRACTOR",
        "SOFTWARE_VENDOR",
    }
    assert {role["role_code"] for role in payload["role_matrix"]}.issuperset(
        {"OWNER_LEADER", "REVIEWER", "WORKORDER_MANAGER", "PLATFORM_OPERATOR"}
    )

    page = lifeline_client.get("/lifeline")
    assert page.status_code == 404
    dashboard = lifeline_client.get("/dashboard")
    assert "/lifeline" not in dashboard.text
    assert "/project-progress" in dashboard.text


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


@pytest.mark.parametrize(
    ("username", "application_codes", "project_codes"),
    (
        (
            "water_drainage_leader",
            {"WATER_SUPPLY", "WATER_HYDRAULIC", "DRAINAGE"},
            {"WS_NETWORK_RENEWAL", "WS_HYDRAULIC_MODEL", "DR_FLOOD_CONTROL"},
        ),
        (
            "dma_specialist",
            {"WATER_SUPPLY"},
            {"WS_NETWORK_RENEWAL"},
        ),
        (
            "hydraulic_specialist",
            {"WATER_HYDRAULIC"},
            {"WS_HYDRAULIC_MODEL"},
        ),
    ),
)
def test_system_grants_support_cross_domain_and_single_system_views(
    lifeline_client: TestClient,
    username: str,
    application_codes: set[str],
    project_codes: set[str],
) -> None:
    profile = _login(lifeline_client, username).json()

    assert {item["application_code"] for item in profile["applications"]} == (
        application_codes
    )
    assert {item["project_code"] for item in profile["projects"]} == project_codes
    response = lifeline_client.get("/api/lifeline/progress")
    assert response.status_code == 200
    assert {
        item["project_code"] for item in response.json()["projects"]
    } == project_codes


def test_same_domain_can_contain_multiple_independently_authorized_systems(
    lifeline_client: TestClient,
) -> None:
    profile = _login(lifeline_client, "water_drainage_leader").json()
    water_systems = [
        item
        for item in profile["applications"]
        if item["application_code"] in {"WATER_SUPPLY", "WATER_HYDRAULIC"}
    ]

    assert len(water_systems) == 2
    with lifeline_client.app.state.database.session_factory() as session:
        repository = ProjectRepository(session, profile["tenant_id"])
        assert {
            repository.get_application(item["application_code"]).domain_type
            for item in water_systems
        } == {"WATER_SUPPLY"}


def test_business_accounts_only_receive_their_scoped_organization_tree(
    lifeline_client: TestClient,
) -> None:
    _login(lifeline_client, "water_drainage_leader")
    tree = lifeline_client.get("/api/orgs/tree")
    assert tree.status_code == 200
    assert {item["org_code"] for item in tree.json()} == {"OWNER_WATER"}

    profile = _login(lifeline_client, "dma_specialist").json()
    page = lifeline_client.get("/iam/organizations")
    assert page.status_code == 200
    assert "供水业务管理部" in page.text
    assert "排水业务管理部" not in page.text
    assert "城市综合调度中心" not in page.text
    assert profile["applications"][0]["application_code"] == "WATER_SUPPLY"


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
    assert len(default_projects) == 6
    assert len(second_projects) == 6
    assert {project.tenant_id for project in default_projects} == {1}
    assert {project.tenant_id for project in second_projects} == {second_tenant.id}
    assert {project.id for project in default_projects}.isdisjoint(
        project.id for project in second_projects
    )
