from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.core.config import Settings
from app.data_permission.models import ResourcePolicy
from app.data_permission.repository import DataPermissionRepository
from app.data_permission.seed import seed_data_permissions
from app.data_permission.service import DataActor, DataPermissionService
from app.db.base import Base
from app.db.session import Database
from app.iam.authorization import PermissionService
from app.iam.repository import IAMRepository
from app.iam.seed import DEMO_INITIAL_PASSWORD, seed_iam
from app.iam.service import IAMService
from app.main import create_app
from app.project.repository import ProjectRepository
from app.project.seed import seed_projects


@pytest.fixture()
def i24_context(tmp_path: Path) -> Iterator[tuple[TestClient, Database]]:
    database_url = f"sqlite:///{(tmp_path / 'i24.db').as_posix()}"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    with database.session_factory() as session:
        iam_service = IAMService(IAMRepository(session))
        seed_iam(iam_service)
        seed_projects(ProjectRepository(session, 1), iam_service)
        seed_data_permissions(DataPermissionRepository(session, 1), iam_service)
    settings = Settings(
        app_name="I24 data permissions",
        environment="test",
        database_url=database_url,
        auth_cookie_secure=False,
    )
    with TestClient(create_app(settings)) as client:
        yield client, database
    database.dispose()


def _login(client: TestClient, username: str) -> dict:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": DEMO_INITIAL_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()


def test_data_seed_is_idempotent_and_builds_expected_catalog(db_session) -> None:
    iam_service = IAMService(IAMRepository(db_session))
    seed_iam(iam_service)
    seed_projects(ProjectRepository(db_session, 1), iam_service)
    summary = seed_data_permissions(
        DataPermissionRepository(db_session, 1), iam_service
    )
    seed_data_permissions(DataPermissionRepository(db_session, 1), iam_service)

    repository = DataPermissionRepository(db_session, 1)
    assert summary.data_spaces == 6
    assert summary.resources == 10
    assert len(repository.list_spaces()) == 6
    assert len(repository.list_resources()) == 10
    assert len(repository.list_user_grants(iam_service.get_user("admin").id)) == 6


def test_data_steward_sees_processed_data_but_not_model_result(
    i24_context: tuple[TestClient, Database],
) -> None:
    client, _ = i24_context
    _login(client, "dma_specialist")

    response = client.get("/api/data-permissions/resources")
    assert response.status_code == 200
    keys = {item["resource_key"] for item in response.json()}
    assert {
        "WS_DMA_PRESSURE_RAW",
        "WS_DMA_PRESSURE_CLEAN",
        "WS_WATER_NETWORK_LAYER",
    } <= keys
    assert "WS_DMA_LEAK_PREDICTION" not in keys

    page = client.get("/data-resources")
    assert page.status_code == 200
    assert "采集处理数据专员" in page.text
    assert "DMA 压力清洗处理数据" in page.text
    assert "DMA 漏损模型计算结果" not in page.text


def test_explicit_deny_wins_even_when_allow_policy_also_matches(
    i24_context: tuple[TestClient, Database],
) -> None:
    client, database = i24_context
    profile = _login(client, "dma_specialist")
    with database.session_factory() as session:
        repository = DataPermissionRepository(session, profile["tenant_id"])
        resource = repository.get_resource_by_key("WS_DMA_LEAK_PREDICTION")
        role = repository.get_role("DATA_STEWARD")
        assert resource is not None and role is not None
        repository.add(
            ResourcePolicy(
                tenant_id=profile["tenant_id"],
                subject_type="ROLE",
                subject_id=role.id,
                resource_id=resource.id,
                action_code="data:resource:view",
                effect="ALLOW",
            )
        )
        repository.commit()
        service = DataPermissionService(
            repository,
            PermissionService(IAMRepository(session, profile["tenant_id"])),
        )
        explanation = service.explain(
            resource.id,
            "data:resource:view",
            DataActor(profile["user_id"], profile["active_org_id"]),
        )

    assert explanation["checks"]["matching_allow_policy"] is True
    assert explanation["checks"]["matching_deny_policy"] is True
    assert explanation["allowed"] is False
    assert "DENY" in explanation["decision_reason"]


def test_model_analyst_isolated_to_hydraulic_resources_and_revocation_is_immediate(
    i24_context: tuple[TestClient, Database],
) -> None:
    client, database = i24_context
    profile = _login(client, "hydraulic_specialist")
    first = client.get("/api/data-permissions/resources")
    assert {item["resource_key"] for item in first.json()} == {
        "WS_HYDRAULIC_MODEL",
        "WS_HYDRAULIC_RESULT_DETAIL",
    }

    resource_id = first.json()[0]["id"]
    explanation = client.get(
        f"/api/data-permissions/resources/{resource_id}/authorization-explain"
    )
    assert explanation.status_code == 200
    assert explanation.json()["allowed"] is True
    assert explanation.json()["matching_role_codes"] == ["MODEL_ANALYST"]

    with database.session_factory() as session:
        grants = DataPermissionRepository(session, profile["tenant_id"]).list_user_grants(
            profile["user_id"]
        )
        assert len(grants) == 1
        grants[0].is_active = False
        session.commit()

    assert client.get("/api/data-permissions/resources").json() == []


def test_admin_can_create_catalog_items_and_configure_policy(
    i24_context: tuple[TestClient, Database],
) -> None:
    client, _ = i24_context
    profile = _login(client, "admin")
    organizations = client.get("/api/orgs").json()
    group_id = next(item["id"] for item in organizations if item["org_code"] == "GROUP")
    water_id = next(
        item["id"]
        for item in profile["applications"]
        if item["application_code"] == "WATER_SUPPLY"
    )
    space = client.post(
        "/api/data-permissions/spaces",
        json={
            "space_code": "WS_TEST_SPACE",
            "space_name": "供水测试数据空间",
            "space_type": "APPLICATION_PRIVATE",
            "domain_type": "WATER_SUPPLY",
            "application_id": water_id,
            "owner_org_id": group_id,
        },
    )
    assert space.status_code == 201
    resource = client.post(
        "/api/data-permissions/resources",
        json={
            "data_space_id": space.json()["id"],
            "application_id": water_id,
            "owner_org_id": group_id,
            "resource_type": "DATASET",
            "resource_key": "WS_TEST_DATASET",
            "resource_name": "供水测试数据集",
            "derivation_stage": "PROCESSED",
        },
    )
    assert resource.status_code == 201
    policy = client.post(
        f"/api/data-permissions/resources/{resource.json()['id']}/policies",
        json={
            "role_code": "SYSTEM_ADMIN",
            "action_code": "data:resource:view",
            "effect": "ALLOW",
        },
    )
    assert policy.status_code == 204
    visible = client.get("/api/data-permissions/resources").json()
    assert "WS_TEST_DATASET" in {item["resource_key"] for item in visible}


def test_data_permission_api_rejects_incomplete_or_unauthorized_configuration(
    i24_context: tuple[TestClient, Database],
) -> None:
    client, _ = i24_context
    specialist = _login(client, "dma_specialist")
    resources = client.get("/api/data-permissions/resources").json()
    visible_resource_id = resources[0]["id"]

    denied_result = client.get(
        "/api/data-permissions/resources",
        params={"action_code": "data:resource:manage"},
    )
    assert denied_result.status_code == 200
    assert denied_result.json() == []
    assert client.get("/api/data-permissions/resources/999999").status_code == 404
    assert client.get(
        "/api/data-permissions/resources/999999/authorization-explain"
    ).status_code == 404
    assert client.post(
        "/api/data-permissions/spaces",
        json={
            "space_code": "DENIED_SPACE",
            "space_name": "无权创建",
            "space_type": "APPLICATION_PRIVATE",
            "application_id": specialist["applications"][0]["id"],
            "owner_org_id": specialist["active_org_id"],
        },
    ).status_code == 403
    assert client.post(
        f"/api/data-permissions/resources/{visible_resource_id}/policies",
        json={
            "role_code": "MISSING_ROLE",
            "action_code": "data:resource:view",
            "effect": "ALLOW",
        },
    ).status_code == 422

    client.post("/logout")
    admin = _login(client, "admin")
    water_id = next(
        item["id"]
        for item in admin["applications"]
        if item["application_code"] == "WATER_SUPPLY"
    )
    assert client.put(
        f"/api/data-permissions/applications/{water_id}/roles",
        json={"user_org_id": 999999, "role_code": "DATA_VIEWER"},
    ).status_code == 422
    assert client.post(
        "/api/data-permissions/resources",
        json={
            "data_space_id": 999999,
            "application_id": water_id,
            "owner_org_id": admin["active_org_id"],
            "resource_type": "DATASET",
            "resource_key": "INVALID_SPACE_RESOURCE",
            "resource_name": "错误空间资源",
            "derivation_stage": "PROCESSED",
        },
    ).status_code == 422


def test_admin_can_grant_application_role_and_default_deny_still_applies(
    i24_context: tuple[TestClient, Database],
) -> None:
    client, _ = i24_context
    profile = _login(client, "admin")
    water_id = next(
        item["id"]
        for item in profile["applications"]
        if item["application_code"] == "WATER_SUPPLY"
    )
    users = client.get("/api/users").json()
    specialist = next(item for item in users if item["username"] == "dma_specialist")
    membership_id = next(
        item["id"]
        for item in specialist["memberships"]
        if item["org_code"] == "OWNER_WATER"
    )
    request_body = {"user_org_id": membership_id, "role_code": "DATA_VIEWER"}
    first = client.put(
        f"/api/data-permissions/applications/{water_id}/roles", json=request_body
    )
    second = client.put(
        f"/api/data-permissions/applications/{water_id}/roles", json=request_body
    )
    assert first.status_code == second.status_code == 204

    group_id = profile["active_org_id"]
    space = client.post(
        "/api/data-permissions/spaces",
        json={
            "space_code": "DEFAULT_DENY_SPACE",
            "space_name": "默认拒绝验证空间",
            "space_type": "APPLICATION_PRIVATE",
            "application_id": water_id,
            "owner_org_id": group_id,
        },
    ).json()
    resource = client.post(
        "/api/data-permissions/resources",
        json={
            "data_space_id": space["id"],
            "application_id": water_id,
            "owner_org_id": group_id,
            "resource_type": "DATASET",
            "resource_key": "DEFAULT_DENY_DATASET",
            "resource_name": "默认拒绝验证数据集",
            "derivation_stage": "PROCESSED",
        },
    ).json()
    explanation = client.get(
        f"/api/data-permissions/resources/{resource['id']}/authorization-explain"
    ).json()
    assert explanation["allowed"] is False
    assert "默认拒绝" in explanation["decision_reason"]


def test_i24_migration_creates_and_removes_data_permission_tables(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "0017_i24_data_permissions")
    engine = create_engine(database_url)
    expected = {
        "iam_application_role_grant",
        "dc_data_space",
        "dc_business_resource",
        "auth_resource_policy",
    }
    assert expected <= set(inspect(engine).get_table_names())
    command.downgrade(config, "0016_unified_login")
    assert not expected & set(inspect(engine).get_table_names())
    engine.dispose()
