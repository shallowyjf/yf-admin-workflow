from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.iam.admin_service import (
    IAMAdministrationActor,
    IAMAdministrationConflict,
    IAMAdministrationPermissionDenied,
    IAMAdministrationValidationError,
)
from app.iam.authorization import DataScopeType, PermissionService
from app.iam.identity import IdentityQueryService
from app.iam.repository import IAMRepository
from app.iam.role_admin_service import (
    CreateRoleCommand,
    PermissionScopeConfiguration,
    RoleAdministrationService,
    UpdateRoleCommand,
)
from app.iam.seed import DEMO_INITIAL_PASSWORD, seed_iam
from app.iam.service import IAMEntityNotFound, IAMService
from app.main import create_app


def _service(
    session: Session,
) -> tuple[RoleAdministrationService, IAMAdministrationActor, IAMRepository]:
    repository = IAMRepository(session)
    iam_service = IAMService(repository)
    seed_iam(iam_service)
    admin = iam_service.get_user("admin")
    group = iam_service.get_organization("GROUP")
    assert admin is not None and group is not None
    return (
        RoleAdministrationService(repository, PermissionService(repository)),
        IAMAdministrationActor(admin.id, group.id),
        repository,
    )


def test_role_lifecycle_atomic_authorization_and_immediate_effect(
    db_session: Session,
) -> None:
    service, actor, repository = _service(db_session)
    role = service.create(
        CreateRoleCommand("FIELD_MANAGER", "现场主管", "BUSINESS"),
        actor,
    )
    role = service.update(
        role.id,
        UpdateRoleCommand("现场管理主管", "FIELD"),
        actor,
    )
    assert role.role_code == "FIELD_MANAGER"
    assert role.role_name == "现场管理主管"

    service.replace_authorization(
        role.id,
        (
            PermissionScopeConfiguration(
                "workorder:create",
                DataScopeType.CUSTOM,
                ("INSPECTION_TEAM_1", "INSPECTION_TEAM_2"),
            ),
        ),
        actor,
    )
    iam_service = IAMService(repository)
    iam_service.assign_role("lisi", "PIPE_OPERATION", "FIELD_MANAGER")
    user = iam_service.get_user("lisi")
    pipe = iam_service.get_organization("PIPE_OPERATION")
    team_1 = iam_service.get_organization("INSPECTION_TEAM_1")
    team_2 = iam_service.get_organization("INSPECTION_TEAM_2")
    assert user is not None and pipe is not None
    assert team_1 is not None and team_2 is not None
    permissions = PermissionService(repository)
    assert permissions.has_permission(user.id, "workorder:create", pipe.id)
    scope = permissions.work_order_scope(user.id, "workorder:create", pipe.id)
    assert scope.org_ids == {team_1.id, team_2.id}
    assert not scope.all_data and scope.self_user_id is None

    service.replace_authorization(
        role.id,
        (
            PermissionScopeConfiguration(
                "workorder:dispatch",
                DataScopeType.ORG,
            ),
        ),
        actor,
    )
    assert not permissions.has_permission(user.id, "workorder:create", pipe.id)
    assert repository.get_role_data_scope(role.id, "workorder:create") is None
    assert permissions.has_permission(user.id, "workorder:dispatch", pipe.id)

    service.set_active(role.id, False, actor)
    assert not permissions.has_permission(user.id, "workorder:dispatch", pipe.id)
    assert user.id not in IdentityQueryService(repository).users_by_role(
        "FIELD_MANAGER",
        pipe.id,
    )
    assert [
        item.action for item in repository.list_iam_audit_logs("ROLE", role.id)
    ] == [
        "CREATE",
        "UPDATE",
        "REPLACE_AUTHORIZATION",
        "REPLACE_AUTHORIZATION",
        "DISABLE",
    ]


def test_custom_scope_requires_unique_active_existing_organizations(
    db_session: Session,
) -> None:
    service, actor, repository = _service(db_session)
    role = service.create(CreateRoleCommand("CUSTOM_SCOPE", "自定义范围"), actor)
    with pytest.raises(IAMAdministrationValidationError, match="至少需要一个组织"):
        service.replace_authorization(
            role.id,
            (
                PermissionScopeConfiguration(
                    "workorder:view",
                    DataScopeType.CUSTOM,
                ),
            ),
            actor,
        )
    with pytest.raises(IAMEntityNotFound, match="MISSING_ORG"):
        service.replace_authorization(
            role.id,
            (
                PermissionScopeConfiguration(
                    "workorder:view",
                    DataScopeType.CUSTOM,
                    ("MISSING_ORG",),
                ),
            ),
            actor,
        )
    team = repository.get_organization_by_code("INSPECTION_TEAM_1")
    assert team is not None
    team.is_active = False
    repository.commit()
    with pytest.raises(IAMAdministrationValidationError, match="启用状态"):
        service.replace_authorization(
            role.id,
            (
                PermissionScopeConfiguration(
                    "workorder:view",
                    DataScopeType.CUSTOM,
                    (team.org_code,),
                ),
            ),
            actor,
        )
    with pytest.raises(IAMAdministrationValidationError, match="只有 CUSTOM"):
        service.replace_authorization(
            role.id,
            (
                PermissionScopeConfiguration(
                    "workorder:view",
                    DataScopeType.ORG,
                    ("PIPE_OPERATION",),
                ),
            ),
            actor,
        )


def test_role_permission_boundary_and_system_admin_protection(
    db_session: Session,
) -> None:
    service, actor, repository = _service(db_session)
    system_admin = repository.get_role_by_code("SYSTEM_ADMIN")
    lisi = repository.get_user_by_username("lisi")
    pipe = repository.get_organization_by_code("PIPE_OPERATION")
    assert system_admin is not None and lisi is not None and pipe is not None
    with pytest.raises(IAMAdministrationConflict, match="不能停用"):
        service.set_active(system_admin.id, False, actor)
    with pytest.raises(IAMAdministrationConflict, match="核心权限"):
        service.replace_authorization(system_admin.id, (), actor)
    with pytest.raises(IAMAdministrationPermissionDenied):
        service.create(
            CreateRoleCommand("FORBIDDEN_ROLE", "越权角色"),
            IAMAdministrationActor(lisi.id, pipe.id),
        )


@pytest.fixture()
def role_client(tmp_path) -> Iterator[TestClient]:
    database_path = tmp_path / "role-api.sqlite3"
    settings = Settings(
        app_name="I13 角色管理回归",
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


def _login(
    client: TestClient,
    username: str,
    password: str = DEMO_INITIAL_PASSWORD,
):
    return client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )


def _use_session(client: TestClient, token: str) -> None:
    client.cookies.clear()
    client.cookies.set("yf_session", token, domain="testserver.local", path="/")


def test_role_api_changes_existing_login_on_next_request(
    role_client: TestClient,
) -> None:
    assert _login(role_client, "admin").status_code == 200
    admin_token = role_client.cookies.get("yf_session")
    assert admin_token is not None
    created_role = role_client.post(
        "/api/roles",
        json={
            "role_code": "API_OPERATOR",
            "role_name": "API 操作员",
            "role_type": "BUSINESS",
        },
    )
    assert created_role.status_code == 201
    role_id = created_role.json()["id"]
    created_user = role_client.post(
        "/api/users",
        json={
            "username": "role.api",
            "display_name": "角色 API 用户",
            "password": "Initial@123",
        },
    )
    assert created_user.status_code == 201
    user_id = created_user.json()["id"]
    membership = role_client.put(
        f"/api/users/{user_id}/memberships",
        json={
            "memberships": [
                {
                    "org_code": "PIPE_OPERATION",
                    "is_primary": True,
                    "role_codes": ["API_OPERATOR"],
                }
            ]
        },
    )
    assert membership.status_code == 200
    user_login = _login(role_client, "role.api", "Initial@123")
    assert user_login.status_code == 200
    assert "workorder:create" not in user_login.json()["permission_codes"]
    user_token = role_client.cookies.get("yf_session")
    assert user_token is not None

    _use_session(role_client, admin_token)
    granted = role_client.put(
        f"/api/roles/{role_id}/authorization",
        json={
            "permissions": [
                {
                    "permission_code": "workorder:create",
                    "scope_type": "CUSTOM",
                    "custom_org_codes": [
                        "INSPECTION_TEAM_1",
                        "INSPECTION_TEAM_2",
                    ],
                }
            ]
        },
    )
    assert granted.status_code == 200
    assert granted.json()["authorization"] == [
        {
            "permission_code": "workorder:create",
            "permission_name": "创建工单",
            "scope_type": "CUSTOM",
            "custom_org_codes": ["INSPECTION_TEAM_1", "INSPECTION_TEAM_2"],
        }
    ]

    _use_session(role_client, user_token)
    profile = role_client.get("/auth/me")
    assert profile.status_code == 200
    assert "workorder:create" in profile.json()["permission_codes"]

    _use_session(role_client, admin_token)
    disabled = role_client.post(
        f"/api/roles/{role_id}/status",
        json={"is_active": False},
    )
    assert disabled.status_code == 200
    _use_session(role_client, user_token)
    profile = role_client.get("/auth/me")
    assert profile.status_code == 200
    assert "workorder:create" not in profile.json()["permission_codes"]

    assert _login(role_client, "lisi").status_code == 200
    assert role_client.get("/api/roles").status_code == 403
