from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.security import PasswordHasher
from app.core.config import Settings
from app.db.base import Base
from app.db.session import Database
from app.iam.repository import IAMRepository
from app.iam.seed import DEMO_INITIAL_PASSWORD, seed_iam
from app.iam.service import IAMService
from app.main import create_app


@pytest.fixture()
def auth_client(tmp_path: Path) -> Iterator[TestClient]:
    database_url = f"sqlite:///{(tmp_path / 'auth.db').as_posix()}"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    with database.session_factory() as session:
        seed_iam(IAMService(IAMRepository(session)))
    database.dispose()

    settings = Settings(
        app_name="权限流程测试平台",
        environment="test",
        database_url=database_url,
        auth_cookie_secure=False,
        auth_session_hours=8,
    )
    with TestClient(create_app(settings)) as client:
        yield client


def _login(client: TestClient, username: str = "wangwu"):
    return client.post(
        "/auth/login",
        json={"username": username, "password": DEMO_INITIAL_PASSWORD},
    )


def test_password_hash_is_salted_and_verifiable() -> None:
    hasher = PasswordHasher()

    first = hasher.hash("correct horse battery staple")
    second = hasher.hash("correct horse battery staple")

    assert first != second
    assert "correct horse battery staple" not in first
    assert hasher.verify("correct horse battery staple", first)
    assert not hasher.verify("wrong", first)
    assert not hasher.verify("wrong", "not-a-supported-hash")


def test_protected_auth_endpoints_return_401_without_session(
    auth_client: TestClient,
) -> None:
    assert auth_client.get("/auth/me").status_code == 401
    assert auth_client.post("/auth/logout").status_code == 401
    assert auth_client.post("/auth/active-org", json={"org_id": 1}).status_code == 401


def test_login_sets_secure_cookie_and_me_returns_permission_summary(
    auth_client: TestClient,
) -> None:
    response = _login(auth_client)

    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    profile = response.json()
    assert profile["tenant_code"] == "DEMO"
    assert profile["tenant_name"] == "智慧城市演示租户"
    assert profile["username"] == "wangwu"
    assert profile["role_codes"] == ["DISPATCHER", "REVIEWER"]
    assert "workorder:dispatch" in profile["permission_codes"]
    assert {org["org_code"] for org in profile["organizations"]} == {
        "DISPATCH_CENTER",
        "PIPE_OPERATION",
    }
    assert auth_client.get("/auth/me").json() == profile


def test_active_org_switch_recalculates_roles_and_permissions(
    auth_client: TestClient,
) -> None:
    profile = _login(auth_client).json()
    pipe_org_id = next(
        org["id"]
        for org in profile["organizations"]
        if org["org_code"] == "PIPE_OPERATION"
    )

    response = auth_client.post("/auth/active-org", json={"org_id": pipe_org_id})

    assert response.status_code == 200
    switched = response.json()
    assert switched["active_org_id"] == pipe_org_id
    assert switched["role_codes"] == []
    assert switched["permission_codes"] == []
    assert auth_client.get("/auth/me").json()["active_org_id"] == pipe_org_id


def test_active_org_switch_rejects_non_membership_and_keeps_context(
    auth_client: TestClient,
) -> None:
    original = _login(auth_client).json()

    response = auth_client.post("/auth/active-org", json={"org_id": 999999})

    assert response.status_code == 403
    assert auth_client.get("/auth/me").json()["active_org_id"] == original[
        "active_org_id"
    ]


def test_invalid_password_and_logout_revocation(auth_client: TestClient) -> None:
    invalid = auth_client.post(
        "/auth/login",
        json={"username": "wangwu", "password": "wrong-password"},
    )
    assert invalid.status_code == 401

    assert _login(auth_client).status_code == 200
    logout = auth_client.post("/auth/logout")
    assert logout.status_code == 204
    assert auth_client.get("/auth/me").status_code == 401
