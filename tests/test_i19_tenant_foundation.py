from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.base import Base
from app.db.session import Database
from app.iam.models import Organization, Tenant, User
from app.iam.repository import IAMRepository
from app.iam.seed import DEMO_INITIAL_PASSWORD, seed_iam
from app.iam.service import IAMService
from app.main import create_app


@pytest.fixture()
def tenant_client(tmp_path: Path) -> Iterator[tuple[TestClient, int, int]]:
    database_url = f"sqlite:///{(tmp_path / 'i19.db').as_posix()}"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    with database.session_factory() as session:
        seed_iam(IAMService(IAMRepository(session)))
        default_admin_id = session.scalar(
            select(User.id).where(User.tenant_id == 1, User.username == "admin")
        )
        default_group_id = session.scalar(
            select(Organization.id).where(
                Organization.tenant_id == 1,
                Organization.org_code == "GROUP",
            )
        )
        second_tenant = Tenant(
            tenant_code="CITY_B",
            tenant_name="B市智慧城市",
        )
        session.add(second_tenant)
        session.commit()
        session.refresh(second_tenant)
        seed_iam(IAMService(IAMRepository(session, second_tenant.id)))
        assert default_admin_id is not None
        assert default_group_id is not None
    database.dispose()

    settings = Settings(
        app_name="I19 tenant foundation",
        environment="test",
        database_url=database_url,
        auth_cookie_secure=False,
        default_tenant_code="DEMO",
    )
    with TestClient(create_app(settings)) as client:
        yield client, default_admin_id, default_group_id


def _login(client: TestClient, tenant_code: str | None = None):
    payload = {
        "username": "admin",
        "password": DEMO_INITIAL_PASSWORD,
    }
    if tenant_code is not None:
        payload["tenant_code"] = tenant_code
    return client.post("/auth/login", json=payload)


def test_same_identity_codes_are_isolated_by_tenant(
    tenant_client: tuple[TestClient, int, int],
) -> None:
    client, default_admin_id, default_group_id = tenant_client

    default_profile = _login(client).json()
    assert default_profile["tenant_code"] == "DEMO"
    assert default_profile["tenant_name"] == "某市城市生命线演示租户"
    assert default_profile["user_id"] == default_admin_id

    second_login = _login(client, "city_b")
    assert second_login.status_code == 200
    second_profile = second_login.json()
    assert second_profile["tenant_code"] == "CITY_B"
    assert second_profile["user_id"] != default_admin_id
    assert second_profile["active_org_id"] != default_group_id

    users = client.get("/api/users")
    assert users.status_code == 200
    assert {item["username"] for item in users.json()} == {
        "admin",
        "lisi",
        "owner_leader",
        "platform_ops",
        "regulator",
        "wangwu",
        "zhangsan",
        "zhaoliu",
    }
    assert client.get(f"/api/users/{default_admin_id}").status_code == 404
    assert client.post(
        "/auth/active-org",
        json={"org_id": default_group_id},
    ).status_code == 403


def test_login_rejects_unknown_tenant_without_leaking_identity(
    tenant_client: tuple[TestClient, int, int],
) -> None:
    client, _, _ = tenant_client

    response = _login(client, "NOT_EXISTS")

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid tenant or credentials"


def test_scoped_repositories_return_only_their_tenant_entities(
    db_session,
) -> None:
    seed_iam(IAMService(IAMRepository(db_session)))
    second_tenant = Tenant(tenant_code="CITY_C", tenant_name="C市智慧城市")
    db_session.add(second_tenant)
    db_session.commit()
    db_session.refresh(second_tenant)
    seed_iam(IAMService(IAMRepository(db_session, second_tenant.id)))

    default_repository = IAMRepository(db_session, 1)
    second_repository = IAMRepository(db_session, second_tenant.id)

    assert len(default_repository.list_users()) == 8
    assert len(second_repository.list_users()) == 8
    assert default_repository.get_user_by_username("admin").id != (
        second_repository.get_user_by_username("admin").id
    )
    assert all(item.tenant_id == 1 for item in default_repository.list_roles())
    assert all(
        item.tenant_id == second_tenant.id for item in second_repository.list_roles()
    )
    default_repairers = default_repository.list_active_user_ids_by_role("REPAIRER")
    second_repairers = second_repository.list_active_user_ids_by_role("REPAIRER")
    assert len(default_repairers) == 2
    assert len(second_repairers) == 2
    assert default_repairers.isdisjoint(second_repairers)
