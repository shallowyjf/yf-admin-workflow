from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.iam.admin_service import (
    CreateOrganizationCommand,
    IAMAdministrationActor,
    IAMAdministrationConflict,
    IAMAdministrationPermissionDenied,
    OrganizationAdministrationService,
    UpdateOrganizationCommand,
)
from app.iam.authorization import PermissionService
from app.iam.repository import IAMRepository
from app.iam.seed import DEMO_INITIAL_PASSWORD, seed_iam
from app.iam.service import IAMService
from app.main import create_app


def _admin_service(
    session: Session,
) -> tuple[OrganizationAdministrationService, IAMAdministrationActor]:
    repository = IAMRepository(session)
    iam_service = IAMService(repository)
    seed_iam(iam_service)
    admin = iam_service.get_user("admin")
    group = iam_service.get_organization("GROUP")
    assert admin is not None and group is not None
    return (
        OrganizationAdministrationService(
            repository,
            PermissionService(repository),
        ),
        IAMAdministrationActor(admin.id, group.id),
    )


def test_organization_crud_updates_descendant_paths_and_audit(
    db_session: Session,
) -> None:
    service, actor = _admin_service(db_session)
    parent = service.create(
        CreateOrganizationCommand("TEMP_AREA", "临时片区", "DEPARTMENT", "GROUP", 80),
        actor,
    )
    child = service.create(
        CreateOrganizationCommand("TEMP_TEAM", "临时班组", "TEAM", "TEMP_AREA", 10),
        actor,
    )

    updated = service.update(
        parent.id,
        UpdateOrganizationCommand("临时片区（调整）", "DEPARTMENT", "PIPE_OPERATION", 90),
        actor,
    )
    db_session.refresh(child)
    assert updated.org_path == "/GROUP/PIPE_OPERATION/TEMP_AREA"
    assert child.org_path == "/GROUP/PIPE_OPERATION/TEMP_AREA/TEMP_TEAM"

    service.delete(child.id, actor)
    service.delete(parent.id, actor)
    logs = IAMRepository(db_session).list_iam_audit_logs("ORGANIZATION", parent.id)
    assert [log.action for log in logs] == ["CREATE", "UPDATE", "DELETE"]
    assert logs[-1].operator_id == actor.user_id


def test_organization_status_and_delete_relationship_constraints(
    db_session: Session,
) -> None:
    service, actor = _admin_service(db_session)
    group = IAMRepository(db_session).get_organization_by_code("GROUP")
    dispatch = IAMRepository(db_session).get_organization_by_code("DISPATCH_CENTER")
    assert group is not None and dispatch is not None

    with pytest.raises(IAMAdministrationConflict, match="下级组织"):
        service.set_active(group.id, False, actor)
    with pytest.raises(IAMAdministrationConflict, match="成员关系"):
        service.delete(dispatch.id, actor)

    leaf = service.create(
        CreateOrganizationCommand("EMPTY_LEAF", "空组织", "TEAM", "PIPE_OPERATION"),
        actor,
    )
    assert not service.set_active(leaf.id, False, actor).is_active
    assert service.set_active(leaf.id, True, actor).is_active
    service.delete(leaf.id, actor)


def test_non_admin_cannot_manage_organizations(db_session: Session) -> None:
    service, _ = _admin_service(db_session)
    iam = IAMService(IAMRepository(db_session))
    lisi = iam.get_user("lisi")
    pipe = iam.get_organization("PIPE_OPERATION")
    assert lisi is not None and pipe is not None
    actor = IAMAdministrationActor(lisi.id, pipe.id)

    with pytest.raises(IAMAdministrationPermissionDenied):
        service.create(
            CreateOrganizationCommand("FORBIDDEN", "越权组织"),
            actor,
        )


@pytest.fixture()
def organization_client(tmp_path) -> Iterator[TestClient]:
    database_path = tmp_path / "organization-api.sqlite3"
    settings = Settings(
        app_name="I11 组织管理回归",
        environment="test",
        database_url=f"sqlite:///{database_path.as_posix()}",
    )
    application = create_app(settings)
    with TestClient(application) as client:
        database = application.state.database
        Base.metadata.create_all(database.engine)
        with database.session_factory() as session:
            seed_iam(IAMService(IAMRepository(session)))
        yield client


def _login(client: TestClient, username: str) -> None:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": DEMO_INITIAL_PASSWORD},
    )
    assert response.status_code == 200


def test_organization_rest_api_crud_and_tree(
    organization_client: TestClient,
) -> None:
    _login(organization_client, "admin")
    created = organization_client.post(
        "/api/orgs",
        json={
            "org_code": "API_TEAM",
            "org_name": "API 班组",
            "org_type": "TEAM",
            "parent_code": "PIPE_OPERATION",
            "sort_no": 70,
        },
    )
    assert created.status_code == 201
    organization_id = created.json()["id"]
    assert created.json()["org_path"] == "/GROUP/PIPE_OPERATION/API_TEAM"

    updated = organization_client.put(
        f"/api/orgs/{organization_id}",
        json={
            "org_name": "API 班组（更新）",
            "org_type": "TEAM",
            "parent_code": "GROUP",
            "sort_no": 75,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["org_path"] == "/GROUP/API_TEAM"
    assert organization_client.get("/api/orgs/tree").status_code == 200
    assert organization_client.post(
        f"/api/orgs/{organization_id}/status", json={"is_active": False}
    ).json()["is_active"] is False
    assert organization_client.delete(f"/api/orgs/{organization_id}").status_code == 204
    assert organization_client.get(f"/api/orgs/{organization_id}").status_code == 404


def test_organization_api_rejects_duplicate_and_non_admin(
    organization_client: TestClient,
) -> None:
    _login(organization_client, "admin")
    duplicate = organization_client.post(
        "/api/orgs",
        json={"org_code": "GROUP", "org_name": "重复集团"},
    )
    assert duplicate.status_code == 409

    _login(organization_client, "lisi")
    forbidden = organization_client.post(
        "/api/orgs",
        json={"org_code": "NO_ACCESS", "org_name": "越权组织"},
    )
    assert forbidden.status_code == 403
