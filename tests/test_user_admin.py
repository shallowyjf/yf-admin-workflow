from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.repository import AuthRepository
from app.auth.service import AuthSessionRevocationService
from app.core.config import Settings
from app.db.base import Base
from app.iam.admin_service import (
    IAMAdministrationActor,
    IAMAdministrationConflict,
    IAMAdministrationPermissionDenied,
    IAMAdministrationValidationError,
)
from app.iam.authorization import PermissionService
from app.iam.identity import IdentityQueryService
from app.iam.repository import IAMRepository
from app.iam.seed import DEMO_INITIAL_PASSWORD, seed_iam
from app.iam.service import IAMService
from app.iam.user_admin_service import (
    CreateUserCommand,
    MembershipConfiguration,
    UserAdministrationService,
)
from app.main import create_app
from app.workflow.candidate import CandidateResolverRegistry, CandidateRule, CandidateType


def _service(
    session: Session,
) -> tuple[UserAdministrationService, IAMAdministrationActor, IAMRepository]:
    repository = IAMRepository(session)
    iam_service = IAMService(repository)
    seed_iam(iam_service)
    admin = iam_service.get_user("admin")
    group = iam_service.get_organization("GROUP")
    assert admin is not None and group is not None
    return (
        UserAdministrationService(
            repository,
            PermissionService(repository),
            AuthSessionRevocationService(AuthRepository(session)),
        ),
        IAMAdministrationActor(admin.id, group.id),
        repository,
    )


def test_user_memberships_keep_roles_and_positions_organization_scoped(
    db_session: Session,
) -> None:
    service, actor, repository = _service(db_session)
    user = service.create(
        CreateUserCommand("field.tech", "现场人员", "Initial@123"),
        actor,
    )
    configured = service.replace_memberships(
        user.id,
        (
            MembershipConfiguration(
                "DISPATCH_CENTER",
                True,
                role_codes=("DISPATCHER",),
                position_codes=("DISPATCHER",),
            ),
            MembershipConfiguration(
                "PIPE_OPERATION",
                False,
                role_codes=("REPAIRER",),
                position_codes=("REPAIRER",),
            ),
        ),
        actor,
    )

    memberships = {item.organization.org_code: item for item in configured.memberships}
    assert memberships["DISPATCH_CENTER"].is_primary
    assert {link.role.role_code for link in memberships["DISPATCH_CENTER"].role_links} == {
        "DISPATCHER"
    }
    assert {link.role.role_code for link in memberships["PIPE_OPERATION"].role_links} == {
        "REPAIRER"
    }
    dispatch = repository.get_organization_by_code("DISPATCH_CENTER")
    pipe = repository.get_organization_by_code("PIPE_OPERATION")
    assert dispatch is not None and pipe is not None
    permissions = PermissionService(repository)
    assert permissions.has_permission(user.id, "workorder:dispatch", dispatch.id)
    assert not permissions.has_permission(user.id, "workorder:dispatch", pipe.id)
    assert permissions.has_permission(user.id, "workorder:claim", pipe.id)

    candidates = CandidateResolverRegistry.default(
        IdentityQueryService(repository)
    ).resolve(
        CandidateRule(
            CandidateType.ORG_ROLE,
            org_id=pipe.id,
            role_code="REPAIRER",
        )
    )
    assert user.id in candidates
    service.set_active(user.id, False, actor)
    assert user.id not in IdentityQueryService(repository).users_by_role(
        "REPAIRER", pipe.id
    )
    logs = repository.list_iam_audit_logs("USER", user.id)
    assert [log.action for log in logs] == [
        "CREATE",
        "REPLACE_MEMBERSHIPS",
        "DISABLE",
    ]


def test_inactive_membership_stops_permission_and_candidate_resolution(
    db_session: Session,
) -> None:
    service, actor, repository = _service(db_session)
    user = service.create(
        CreateUserCommand("inactive.tech", "停用成员", "Initial@123"),
        actor,
    )
    service.replace_memberships(
        user.id,
        (
            MembershipConfiguration(
                "DISPATCH_CENTER",
                True,
                role_codes=("DISPATCHER",),
            ),
            MembershipConfiguration(
                "PIPE_OPERATION",
                False,
                False,
                role_codes=("REPAIRER",),
            ),
        ),
        actor,
    )
    pipe = repository.get_organization_by_code("PIPE_OPERATION")
    assert pipe is not None
    assert not PermissionService(repository).has_permission(
        user.id, "workorder:claim", pipe.id
    )
    assert user.id not in IdentityQueryService(repository).users_by_role(
        "REPAIRER", pipe.id
    )


def test_memberships_require_exactly_one_active_primary(db_session: Session) -> None:
    service, actor, _ = _service(db_session)
    user = service.create(
        CreateUserCommand("invalid.primary", "主组织校验", "Initial@123"),
        actor,
    )
    with pytest.raises(IAMAdministrationValidationError, match="一个启用的主组织"):
        service.replace_memberships(
            user.id,
            (
                MembershipConfiguration("DISPATCH_CENTER", False),
                MembershipConfiguration("PIPE_OPERATION", False),
            ),
            actor,
        )


def test_non_admin_cannot_create_users(db_session: Session) -> None:
    service, _, repository = _service(db_session)
    lisi = repository.get_user_by_username("lisi")
    pipe = repository.get_organization_by_code("PIPE_OPERATION")
    assert lisi is not None and pipe is not None
    with pytest.raises(IAMAdministrationPermissionDenied):
        service.create(
            CreateUserCommand("forbidden.user", "越权用户", "Initial@123"),
            IAMAdministrationActor(lisi.id, pipe.id),
        )


def test_admin_cannot_disable_current_account(db_session: Session) -> None:
    service, actor, _ = _service(db_session)
    with pytest.raises(IAMAdministrationConflict, match="当前登录账号"):
        service.set_active(actor.user_id, False, actor)


@pytest.fixture()
def user_client(tmp_path) -> Iterator[TestClient]:
    database_path = tmp_path / "user-api.sqlite3"
    settings = Settings(
        app_name="I12 用户管理回归",
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


def _login(client: TestClient, username: str, password: str = DEMO_INITIAL_PASSWORD):
    return client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )


def _use_session(client: TestClient, token: str) -> None:
    client.cookies.clear()
    client.cookies.set("yf_session", token, domain="testserver.local", path="/")


def test_user_api_lifecycle_active_org_and_session_revocation(
    user_client: TestClient,
) -> None:
    admin_login = _login(user_client, "admin")
    assert admin_login.status_code == 200
    admin_token = user_client.cookies.get("yf_session")
    organizations = user_client.get("/api/orgs").json()
    pipe_id = next(item["id"] for item in organizations if item["org_code"] == "PIPE_OPERATION")
    created = user_client.post(
        "/api/users",
        json={
            "username": "api.user",
            "display_name": "API 用户",
            "password": "Initial@123",
            "phone": "13800000000",
        },
    )
    assert created.status_code == 201
    user_id = created.json()["id"]
    assert _login(user_client, "api.user", "Initial@123").status_code == 403
    assert admin_token is not None
    _use_session(user_client, admin_token)

    configured = user_client.put(
        f"/api/users/{user_id}/memberships",
        json={
            "memberships": [
                {
                    "org_code": "DISPATCH_CENTER",
                    "is_primary": True,
                    "role_codes": ["DISPATCHER"],
                    "position_codes": ["DISPATCHER"],
                },
                {
                    "org_code": "PIPE_OPERATION",
                    "is_primary": False,
                    "role_codes": ["REPAIRER"],
                    "position_codes": ["REPAIRER"],
                },
            ]
        },
    )
    assert configured.status_code == 200
    profile = _login(user_client, "api.user", "Initial@123")
    assert profile.status_code == 200
    assert "workorder:dispatch" in profile.json()["permission_codes"]
    switched = user_client.post("/auth/active-org", json={"org_id": pipe_id})
    assert switched.status_code == 200
    assert "workorder:claim" in switched.json()["permission_codes"]
    user_token = user_client.cookies.get("yf_session")

    assert user_token is not None
    _use_session(user_client, admin_token)
    reconfigured = user_client.put(
        f"/api/users/{user_id}/memberships",
        json={
            "memberships": [
                {
                    "org_code": "DISPATCH_CENTER",
                    "is_primary": True,
                    "role_codes": ["DISPATCHER"],
                    "position_codes": ["DISPATCHER"],
                },
                {
                    "org_code": "PIPE_OPERATION",
                    "is_primary": False,
                    "role_codes": ["REPAIRER"],
                    "position_codes": ["REPAIRER"],
                },
            ]
        },
    )
    assert reconfigured.status_code == 200
    _use_session(user_client, user_token)
    assert user_client.get("/auth/me").status_code == 401
    assert _login(user_client, "api.user", "Initial@123").status_code == 200
    user_token = user_client.cookies.get("yf_session")
    assert user_token is not None
    _use_session(user_client, admin_token)
    reset = user_client.post(
        f"/api/users/{user_id}/password",
        json={"new_password": "Changed@123"},
    )
    assert reset.status_code == 204
    _use_session(user_client, user_token)
    assert user_client.get("/auth/me").status_code == 401
    assert _login(user_client, "api.user", "Initial@123").status_code == 401
    assert _login(user_client, "api.user", "Changed@123").status_code == 200

    _use_session(user_client, admin_token)
    disabled = user_client.post(
        f"/api/users/{user_id}/status",
        json={"is_active": False},
    )
    assert disabled.status_code == 200
    assert _login(user_client, "api.user", "Changed@123").status_code == 401
    _use_session(user_client, admin_token)
    assert user_client.post(
        f"/api/users/{user_id}/status",
        json={"is_active": True},
    ).status_code == 200


def test_user_api_rejects_non_admin(user_client: TestClient) -> None:
    assert _login(user_client, "lisi").status_code == 200
    forbidden = user_client.post(
        "/api/users",
        json={
            "username": "denied.user",
            "display_name": "越权用户",
            "password": "Initial@123",
        },
    )
    assert forbidden.status_code == 403
