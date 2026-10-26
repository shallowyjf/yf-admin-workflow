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
from app.workflow.repository import WorkflowRepository
from app.workflow.seed import seed_workflow


@pytest.fixture()
def operations_client(tmp_path: Path) -> Iterator[TestClient]:
    database_url = f"sqlite:///{(tmp_path / 'i18.db').as_posix()}"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    with database.session_factory() as session:
        seed_iam(IAMService(IAMRepository(session)))
        seed_workflow(WorkflowRepository(session))
    database.dispose()
    settings = Settings(
        app_name="I18 operations",
        environment="test",
        database_url=database_url,
        auth_cookie_secure=False,
    )
    with TestClient(create_app(settings)) as client:
        yield client


def _login(client: TestClient, username: str) -> dict:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": DEMO_INITIAL_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()


def _create(client: TestClient, title: str) -> dict:
    response = client.post(
        "/api/workorders",
        json={"title": title, "type": "REPAIR", "priority": "HIGH"},
    )
    assert response.status_code == 201
    return response.json()


def test_paged_work_order_search_and_saved_view_ownership(
    operations_client: TestClient,
) -> None:
    _login(operations_client, "wangwu")
    _create(operations_client, "I18 东区压力")
    _create(operations_client, "I18 西区压力")
    _create(operations_client, "其他任务")

    page = operations_client.get(
        "/api/workorders/search",
        params={
            "keyword": "I18",
            "priority": "HIGH",
            "sort_by": "work_order_no",
            "sort_direction": "asc",
            "page_size": 1,
            "page": 2,
        },
    )
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert page.json()["page"] == 2
    assert len(page.json()["items"]) == 1

    saved = operations_client.post(
        "/api/saved-views",
        json={
            "module": "WORKORDERS",
            "name": "高优先级 I18",
            "filters": {"keyword": "I18", "priority": ["HIGH"]},
            "is_default": True,
        },
    )
    assert saved.status_code == 200
    assert operations_client.get(
        "/api/saved-views", params={"module": "WORKORDERS"}
    ).json()[0]["name"] == "高优先级 I18"

    _login(operations_client, "admin")
    assert operations_client.get(
        "/api/saved-views", params={"module": "WORKORDERS"}
    ).json() == []
    assert operations_client.delete(
        f"/api/saved-views/{saved.json()['id']}"
    ).status_code == 404


def test_batch_dispatch_and_urge_report_partial_success(
    operations_client: TestClient,
) -> None:
    profile = _login(operations_client, "wangwu")
    pipe_org_id = next(
        item["id"]
        for item in profile["organizations"]
        if item["org_code"] == "PIPE_OPERATION"
    )
    ready = _create(operations_client, "批量派单可处理")
    draft = _create(operations_client, "批量派单状态不符")
    assert operations_client.post(
        f"/api/workorders/{ready['id']}/submit", json={}
    ).status_code == 200

    dispatched = operations_client.post(
        "/api/workorders/batch/dispatch",
        json={
            "work_order_ids": [ready["id"], draft["id"]],
            "target_org_id": pipe_org_id,
            "comment": "I18 批量派单",
        },
    )
    assert dispatched.status_code == 200
    assert (dispatched.json()["succeeded"], dispatched.json()["failed"]) == (1, 1)

    urged = operations_client.post(
        "/api/workorders/batch/urge",
        json={
            "work_order_ids": [ready["id"], draft["id"]],
            "comment": "I18 批量催办",
        },
    )
    assert urged.status_code == 200
    assert (urged.json()["succeeded"], urged.json()["failed"]) == (1, 1)


def test_iam_paging_export_and_row_level_import_report(
    operations_client: TestClient,
) -> None:
    _login(operations_client, "admin")
    users = operations_client.get(
        "/api/iam/batch/search",
        params={"entity": "USERS", "keyword": "a", "page_size": 2},
    )
    assert users.status_code == 200
    assert users.json()["page_size"] == 2
    assert len(users.json()["items"]) <= 2

    exported = operations_client.get(
        "/api/iam/batch/export", params={"entity": "ROLES"}
    )
    assert exported.status_code == 200
    assert any(
        item["role_code"] == "SYSTEM_ADMIN"
        for item in exported.json()["records"]
    )

    organizations = operations_client.post(
        "/api/iam/batch/import",
        json={
            "entity": "ORGANIZATIONS",
            "records": [
                {
                    "org_code": "I18_TEAM",
                    "org_name": "I18 导入班组",
                    "org_type": "TEAM",
                    "parent_code": "PIPE_OPERATION",
                    "sort_no": 88,
                },
                {"org_code": "bad code", "org_name": "错误行"},
            ],
        },
    )
    assert organizations.status_code == 200
    assert (organizations.json()["succeeded"], organizations.json()["failed"]) == (1, 1)

    roles = operations_client.post(
        "/api/iam/batch/import",
        json={
            "entity": "ROLES",
            "records": [
                {
                    "role_code": "I18_OPERATOR",
                    "role_name": "I18 运营角色",
                    "role_type": "CUSTOM",
                    "authorization": [
                        {
                            "permission_code": "workorder:view",
                            "scope_type": "ORG",
                        }
                    ],
                }
            ],
        },
    )
    assert roles.json()["succeeded"] == 1

    users_import = operations_client.post(
        "/api/iam/batch/import",
        json={
            "entity": "USERS",
            "records": [
                {
                    "username": "i18.operator",
                    "display_name": "I18 导入用户",
                    "password": "I18@Demo123",
                    "memberships": [
                        {
                            "org_code": "I18_TEAM",
                            "is_primary": True,
                            "role_codes": ["I18_OPERATOR"],
                        }
                    ],
                }
            ],
        },
    )
    assert users_import.json()["succeeded"] == 1
