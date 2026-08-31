from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.core.config import Settings
from app.data_permission.repository import DataPermissionRepository
from app.data_permission.seed import seed_data_permissions
from app.db.base import Base
from app.db.session import Database
from app.gis_permission.repository import GISPermissionRepository
from app.gis_permission.seed import seed_gis_permissions
from app.iam.repository import IAMRepository
from app.iam.seed import DEMO_INITIAL_PASSWORD, seed_iam
from app.iam.service import IAMService
from app.main import create_app
from app.project.repository import ProjectRepository
from app.project.seed import seed_projects


@pytest.fixture()
def i25_context(tmp_path: Path) -> Iterator[tuple[TestClient, Database]]:
    database_url = f"sqlite:///{(tmp_path / 'i25.db').as_posix()}"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    with database.session_factory() as session:
        iam_service = IAMService(IAMRepository(session))
        seed_iam(iam_service)
        seed_projects(ProjectRepository(session, 1), iam_service)
        data_repository = DataPermissionRepository(session, 1)
        seed_data_permissions(data_repository, iam_service)
        seed_gis_permissions(
            GISPermissionRepository(session, 1), data_repository, iam_service
        )
    settings = Settings(
        app_name="I25 GIS permissions",
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


def _resource_id(database: Database, resource_key: str) -> int:
    with database.session_factory() as session:
        resource = DataPermissionRepository(session, 1).get_resource_by_key(resource_key)
        assert resource is not None
        return resource.id


def test_gis_seed_is_idempotent_and_builds_fields_scopes_and_features(db_session) -> None:
    iam_service = IAMService(IAMRepository(db_session))
    seed_iam(iam_service)
    seed_projects(ProjectRepository(db_session, 1), iam_service)
    data_repository = DataPermissionRepository(db_session, 1)
    seed_data_permissions(data_repository, iam_service)
    repository = GISPermissionRepository(db_session, 1)
    summary = seed_gis_permissions(repository, data_repository, iam_service)
    seed_gis_permissions(repository, data_repository, iam_service)
    water = data_repository.get_resource_by_key("WS_WATER_NETWORK_LAYER")
    assert water is not None
    assert summary.fields == 15
    assert summary.features == 9
    assert len(repository.list_fields(water.id)) == 5
    assert len(repository.list_features(water.id)) == 3


def test_data_steward_is_filtered_by_dma_fields_and_coordinate_precision(
    i25_context: tuple[TestClient, Database],
) -> None:
    client, database = i25_context
    _login(client, "dma_specialist")
    resource_id = _resource_id(database, "WS_WATER_NETWORK_LAYER")
    response = client.get(f"/api/gis/resources/{resource_id}/features")
    assert response.status_code == 200
    payload = response.json()
    assert payload["coordinate_precision"] == "GRID_1KM"
    assert {item["scope_value"] for item in payload["features"]} == {
        "DMA_07",
        "DMA_12",
    }
    assert {item["longitude"] for item in payload["features"]} == {118.78, 118.74}
    assert {item["field_code"] for item in payload["fields"]} == {
        "asset_code",
        "asset_type",
        "metric_value",
    }
    assert all(
        "owner_phone" not in item["properties"]
        and "exact_address" not in item["properties"]
        for item in payload["features"]
    )
    page = client.get(f"/gis-resources/{resource_id}")
    assert page.status_code == 200
    assert "服务端裁剪结果" in page.text
    assert "滨江路 DN600" in page.text
    assert "东湖路 DN800" not in page.text


def test_viewer_gets_region_only_coordinates_and_masked_sensitive_fields(
    i25_context: tuple[TestClient, Database],
) -> None:
    client, database = i25_context
    _login(client, "owner_leader")
    resource_id = _resource_id(database, "WS_WATER_NETWORK_LAYER")
    payload = client.get(f"/api/gis/resources/{resource_id}/features").json()
    assert payload["coordinate_precision"] == "REGION_ONLY"
    assert len(payload["features"]) == 3
    assert all(
        item["longitude"] is None and item["latitude"] is None
        for item in payload["features"]
    )
    first = payload["features"][0]["properties"]
    assert first["owner_phone"] == "138****0001"
    assert first["exact_address"].endswith("***")


def test_manager_can_export_normal_fields_but_not_sensitive_fields(
    i25_context: tuple[TestClient, Database],
) -> None:
    client, database = i25_context
    _login(client, "water_manager")
    resource_id = _resource_id(database, "WS_WATER_NETWORK_LAYER")
    query = client.get(f"/api/gis/resources/{resource_id}/features")
    assert query.status_code == 200
    assert query.json()["coordinate_precision"] == "EXACT"
    assert len(query.json()["features"]) == 3

    exported = client.post(
        f"/api/gis/resources/{resource_id}/exports",
        json={
            "field_codes": ["asset_code", "asset_type", "metric_value"],
            "export_format": "GEOJSON",
        },
    )
    assert exported.status_code == 201
    assert exported.json()["row_count"] == 3
    assert exported.json()["status"] == "COMPLETED"
    assert exported.json()["file_name"].endswith(".geojson")
    assert client.post(
        f"/api/gis/resources/{resource_id}/exports",
        json={"field_codes": ["asset_code", "owner_phone"]},
    ).status_code == 403
    assert len(client.get("/api/gis/exports").json()) == 1


def test_admin_sensitive_export_succeeds_and_other_systems_are_isolated(
    i25_context: tuple[TestClient, Database],
) -> None:
    client, database = i25_context
    _login(client, "admin")
    water_id = _resource_id(database, "WS_WATER_NETWORK_LAYER")
    gas_id = _resource_id(database, "GAS_PIPELINE_RISK_LAYER")
    assert client.post(
        f"/api/gis/resources/{water_id}/exports",
        json={"field_codes": ["asset_code", "owner_phone"]},
    ).status_code == 201
    client.post("/logout")
    _login(client, "water_manager")
    assert client.get(f"/api/gis/resources/{gas_id}/features").status_code == 404
    assert client.get(f"/api/gis/resources/{water_id + 999999}/features").status_code == 404


def test_admin_can_configure_fields_policies_and_spatial_scopes(
    i25_context: tuple[TestClient, Database],
) -> None:
    client, database = i25_context
    _login(client, "admin")
    resource_id = _resource_id(database, "WS_WATER_NETWORK_LAYER")
    created = client.post(
        f"/api/gis/resources/{resource_id}/fields",
        json={
            "field_code": "maintenance_level",
            "field_name": "养护等级",
            "data_type": "STRING",
        },
    )
    assert created.status_code == 204
    assert client.post(
        f"/api/gis/resources/{resource_id}/fields",
        json={
            "field_code": "maintenance_level",
            "field_name": "重复字段",
            "data_type": "STRING",
        },
    ).status_code == 422
    with database.session_factory() as session:
        field = GISPermissionRepository(session, 1).get_field(
            resource_id, "maintenance_level"
        )
        assert field is not None
        field_id = field.id
    assert client.put(
        f"/api/gis/fields/{field_id}/policy",
        json={"role_code": "DATA_STEWARD", "access_mode": "VISIBLE"},
    ).status_code == 204
    scope_body = {
        "role_code": "DATA_STEWARD",
        "scope_type": "DMA",
        "scope_value": "DMA_19",
        "coordinate_precision": "GRID_100M",
    }
    assert client.post(
        f"/api/gis/resources/{resource_id}/spatial-scopes", json=scope_body
    ).status_code == 204
    assert client.post(
        f"/api/gis/resources/{resource_id}/spatial-scopes", json=scope_body
    ).status_code == 204


def test_i25_migration_creates_and_removes_gis_permission_tables(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "0018_i25_gis_permissions")
    engine = create_engine(database_url)
    expected = {
        "dc_resource_field",
        "auth_resource_field_policy",
        "auth_spatial_scope_grant",
        "dc_gis_feature",
        "dc_gis_export_job",
    }
    assert expected <= set(inspect(engine).get_table_names())
    command.downgrade(config, "0017_i24_data_permissions")
    assert not expected & set(inspect(engine).get_table_names())
    engine.dispose()
