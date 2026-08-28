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
def i21_clients(tmp_path: Path) -> Iterator[tuple[TestClient, TestClient]]:
    database_url = f"sqlite:///{(tmp_path / 'i21.db').as_posix()}"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    with database.session_factory() as session:
        iam_service = IAMService(IAMRepository(session))
        seed_iam(iam_service)
        seed_projects(ProjectRepository(session, 1), iam_service)
    database.dispose()

    settings = Settings(
        app_name="I21 project authorization",
        environment="test",
        database_url=database_url,
        auth_cookie_secure=False,
    )
    with (
        TestClient(create_app(settings)) as first_client,
        TestClient(create_app(settings)) as second_client,
    ):
        yield first_client, second_client


def _login(client: TestClient, username: str):
    return client.post(
        "/auth/login",
        json={"username": username, "password": DEMO_INITIAL_PASSWORD},
    )


def _project(profile: dict, project_code: str) -> dict:
    return next(item for item in profile["projects"] if item["project_code"] == project_code)


def _application(profile: dict, application_code: str) -> dict:
    return next(
        item
        for item in profile["applications"]
        if item["application_code"] == application_code
    )


def test_session_switches_only_to_granted_systems_and_projects(
    i21_clients: tuple[TestClient, TestClient],
) -> None:
    lisi_client, admin_client = i21_clients
    lisi = _login(lisi_client, "lisi").json()
    admin = _login(admin_client, "admin").json()

    assert lisi["active_application_id"] == _application(
        lisi, "WATER_SUPPLY"
    )["id"]
    assert lisi["active_project_id"] == _project(
        lisi, "WS_NETWORK_RENEWAL"
    )["id"]
    assert {item["application_code"] for item in lisi["applications"]} == {
        "WATER_SUPPLY",
        "DRAINAGE",
        "HEATING",
    }

    drainage_id = _application(lisi, "DRAINAGE")["id"]
    switched = lisi_client.post(
        "/auth/active-application", json={"application_id": drainage_id}
    )
    assert switched.status_code == 200
    assert switched.json()["active_project_id"] == _project(
        lisi, "DR_FLOOD_CONTROL"
    )["id"]

    gas_application_id = _application(admin, "GAS")["id"]
    gas_project_id = _project(admin, "GAS_SAFETY_UPGRADE")["id"]
    assert lisi_client.post(
        "/auth/active-application", json={"application_id": gas_application_id}
    ).status_code == 403
    assert lisi_client.post(
        "/auth/active-project", json={"project_id": gas_project_id}
    ).status_code == 403


def test_admin_can_bootstrap_project_and_manage_parties_and_members(
    i21_clients: tuple[TestClient, TestClient],
) -> None:
    client, _ = i21_clients
    profile = _login(client, "admin").json()
    water_id = _application(profile, "WATER_SUPPLY")["id"]

    created = client.post(
        "/api/lifeline/projects",
        json={
            "application_id": water_id,
            "project_code": "WS_SECOND_PHASE",
            "project_name": "供水二期工程",
            "start_date": "2027-01-01",
            "end_date": "2027-12-31",
        },
    )
    assert created.status_code == 201
    project_id = created.json()["id"]
    assert created.json()["project_status"] == "PLANNED"

    updated = client.put(
        f"/api/lifeline/projects/{project_id}",
        json={
            "project_name": "供水二期更新工程",
            "project_status": "ACTIVE",
            "start_date": "2027-01-01",
            "end_date": "2027-12-31",
        },
    )
    assert updated.status_code == 200

    organizations = {
        item["org_code"]: item for item in client.get("/api/orgs").json()
    }
    party_response = client.put(
        f"/api/lifeline/projects/{project_id}/organizations",
        json={
            "organizations": [
                {
                    "org_id": organizations["GROUP"]["id"],
                    "party_type": "OWNER",
                    "is_lead": True,
                },
                {
                    "org_id": organizations["REGULATOR"]["id"],
                    "party_type": "REGULATOR",
                },
                {
                    "org_id": organizations["CONTRACTOR"]["id"],
                    "party_type": "CONTRACTOR",
                },
                {
                    "org_id": organizations["PLATFORM"]["id"],
                    "party_type": "PLATFORM",
                },
            ]
        },
    )
    assert party_response.status_code == 200

    users = client.get("/api/users").json()
    admin = next(item for item in users if item["username"] == "admin")
    admin_group_membership = next(
        item for item in admin["memberships"] if item["org_code"] == "GROUP"
    )
    member_response = client.put(
        f"/api/lifeline/projects/{project_id}/members",
        json={
            "members": [
                {
                    "user_org_id": admin_group_membership["id"],
                    "role_code": "SYSTEM_ADMIN",
                }
            ]
        },
    )
    assert member_response.status_code == 200
    assert member_response.json()["members"][0]["username"] == "admin"

    explanation = client.get(
        f"/api/lifeline/projects/{project_id}/authorization-explain",
        params={
            "subject_user_id": profile["user_id"],
            "permission_code": "project:update",
        },
    )
    assert explanation.status_code == 200
    assert explanation.json()["allowed"] is True
    assert explanation.json()["matching_role_codes"] == ["SYSTEM_ADMIN"]

    assert client.delete(f"/api/lifeline/projects/{project_id}").status_code == 409
    audit_entity_types = {
        item["entity_type"] for item in client.get("/api/iam/audit-logs").json()
    }
    assert {"PROJECT", "PROJECT_ORGANIZATION", "PROJECT_MEMBER"}.issubset(
        audit_entity_types
    )


def test_member_removal_invalidates_existing_active_project_context(
    i21_clients: tuple[TestClient, TestClient],
) -> None:
    lisi_client, admin_client = i21_clients
    lisi = _login(lisi_client, "lisi").json()
    admin = _login(admin_client, "admin").json()
    water_project_id = _project(admin, "WS_NETWORK_RENEWAL")["id"]

    before = admin_client.get(
        f"/api/lifeline/projects/{water_project_id}/authorization-explain",
        params={
            "subject_user_id": lisi["user_id"],
            "permission_code": "workorder:handle",
        },
    )
    assert before.status_code == 200
    assert before.json()["allowed"] is True

    project = admin_client.get(
        f"/api/lifeline/projects/{water_project_id}"
    ).json()
    remaining_members = [
        {
            "user_org_id": member["user_org_id"],
            "role_code": member["role_code"],
        }
        for member in project["members"]
        if member["username"] != "lisi"
    ]
    replaced = admin_client.put(
        f"/api/lifeline/projects/{water_project_id}/members",
        json={"members": remaining_members},
    )
    assert replaced.status_code == 200
    assert lisi_client.get("/auth/me").status_code == 401


def test_system_entrance_revocation_invalidates_existing_session(
    i21_clients: tuple[TestClient, TestClient],
) -> None:
    lisi_client, admin_client = i21_clients
    lisi = _login(lisi_client, "lisi").json()
    _login(admin_client, "admin")
    remaining_application_ids = [
        item["id"]
        for item in lisi["applications"]
        if item["application_code"] != "WATER_SUPPLY"
    ]

    response = admin_client.put(
        f"/api/lifeline/users/{lisi['user_id']}/applications",
        json={"application_ids": remaining_application_ids},
    )

    assert response.status_code == 200
    assert {item["application_code"] for item in response.json()} == {
        "DRAINAGE",
        "HEATING",
    }
    assert lisi_client.get("/auth/me").status_code == 401
    audit_logs = admin_client.get("/api/iam/audit-logs").json()
    assert any(item["entity_type"] == "USER_APPLICATION" for item in audit_logs)


def test_lifeline_page_is_removed_and_project_actions_return_to_progress(
    i21_clients: tuple[TestClient, TestClient],
) -> None:
    client, _ = i21_clients
    profile = _login(client, "admin").json()
    page = client.get("/lifeline")
    assert page.status_code == 404
    progress_page = client.get("/project-progress")
    assert progress_page.status_code == 200
    assert 'id="active-application"' not in progress_page.text
    assert 'id="active-project"' not in progress_page.text
    assert "城市生命线工程项目进度总览" in progress_page.text

    response = client.post(
        "/ui/projects",
        data={
            "application_id": str(_application(profile, "ROAD")["id"]),
            "project_code": "ROAD_UI_ACCEPTANCE",
            "project_name": "道路页面验收工程",
            "start_date": "2027-03-01",
            "end_date": "2027-11-30",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/project-progress"
    assert "道路页面验收工程" in client.get("/project-progress").text


def test_project_validation_conflicts_and_empty_project_delete(
    i21_clients: tuple[TestClient, TestClient],
) -> None:
    client, _ = i21_clients
    profile = _login(client, "admin").json()
    water_id = _application(profile, "WATER_SUPPLY")["id"]
    water_project_id = _project(profile, "WS_NETWORK_RENEWAL")["id"]

    assert len(client.get("/api/lifeline/projects").json()) == 6
    assert client.get("/api/lifeline/projects/999999").status_code == 404
    invalid_code = client.post(
        "/api/lifeline/projects",
        json={
            "application_id": water_id,
            "project_code": "invalid-code",
            "project_name": "非法编码项目",
        },
    )
    assert invalid_code.status_code == 422
    duplicate = client.post(
        "/api/lifeline/projects",
        json={
            "application_id": water_id,
            "project_code": "WS_NETWORK_RENEWAL",
            "project_name": "重复项目",
        },
    )
    assert duplicate.status_code == 409
    invalid_status = client.put(
        f"/api/lifeline/projects/{water_project_id}",
        json={
            "project_name": "供水管网更新改造工程",
            "project_status": "UNKNOWN",
        },
    )
    assert invalid_status.status_code == 422

    created = client.post(
        "/api/lifeline/projects",
        json={
            "application_id": water_id,
            "project_code": "EMPTY_DELETE",
            "project_name": "可删除空项目",
        },
    ).json()
    assert client.put(
        f"/api/lifeline/projects/{created['id']}/members",
        json={"members": [{"user_org_id": 1, "role_code": "SYSTEM_ADMIN"}]},
    ).status_code == 422
    assert client.delete(
        f"/api/lifeline/projects/{created['id']}"
    ).status_code == 204

    group_id = next(
        item["id"]
        for item in client.get("/api/orgs").json()
        if item["org_code"] == "GROUP"
    )
    bad_lead = client.put(
        f"/api/lifeline/projects/{water_project_id}/organizations",
        json={
            "organizations": [
                {
                    "org_id": group_id,
                    "party_type": "REGULATOR",
                    "is_lead": True,
                }
            ]
        },
    )
    assert bad_lead.status_code == 422

    duplicate_access = client.put(
        f"/api/lifeline/users/{profile['user_id']}/applications",
        json={"application_ids": [water_id, water_id]},
    )
    assert duplicate_access.status_code == 422
    unknown_access = client.put(
        f"/api/lifeline/users/{profile['user_id']}/applications",
        json={"application_ids": [999999]},
    )
    assert unknown_access.status_code == 422
