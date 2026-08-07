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
def work_order_client(tmp_path: Path) -> Iterator[TestClient]:
    database_url = f"sqlite:///{(tmp_path / 'workorders.db').as_posix()}"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    with database.session_factory() as session:
        seed_iam(IAMService(IAMRepository(session)))
        seed_workflow(WorkflowRepository(session))
    database.dispose()

    settings = Settings(
        app_name="权限流程测试平台",
        environment="test",
        database_url=database_url,
        auth_cookie_secure=False,
    )
    with TestClient(create_app(settings)) as client:
        yield client


def _login(client: TestClient, username: str) -> None:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": DEMO_INITIAL_PASSWORD},
    )
    assert response.status_code == 200


def _create(client: TestClient, title: str = "DMA 分区压力异常"):
    return client.post(
        "/api/workorders",
        json={
            "title": title,
            "type": "DMA_PRESSURE_ANOMALY",
            "priority": "HIGH",
            "location": "城北 DMA",
            "longitude": 116.4,
            "latitude": 39.9,
            "description": "夜间最小流量异常",
        },
    )


def test_work_order_api_requires_login(work_order_client: TestClient) -> None:
    assert work_order_client.get("/api/workorders").status_code == 401
    assert work_order_client.get("/api/tasks/mine").status_code == 401
    assert _create(work_order_client).status_code == 401


def test_create_submit_list_detail_and_timeline(work_order_client: TestClient) -> None:
    _login(work_order_client, "wangwu")

    created_response = _create(work_order_client)

    assert created_response.status_code == 201
    created = created_response.json()
    assert created["work_order_no"].startswith("WO")
    assert created["status"] == "DRAFT"
    work_order_id = created["id"]
    assert work_order_client.get("/api/workorders").json() == [created]
    assert work_order_client.get(f"/api/workorders/{work_order_id}").json() == created

    submitted_response = work_order_client.post(
        f"/api/workorders/{work_order_id}/submit",
        json={"comment": "提交调度"},
    )

    assert submitted_response.status_code == 200
    assert submitted_response.json()["status"] == "PENDING_DISPATCH"
    tasks = work_order_client.get("/api/tasks/mine").json()
    assert len(tasks) == 1
    assert tasks[0]["business_id"] == work_order_id
    assert tasks[0]["task_type"] == "DISPATCH"
    assert tasks[0]["status"] == "PENDING"
    assert tasks[0]["assignee_id"] is None
    assert tasks[0]["is_candidate"] is True
    timeline = work_order_client.get(
        f"/api/workorders/{work_order_id}/timeline"
    ).json()
    assert [item["action_type"] for item in timeline] == ["CREATE", "SUBMIT"]
    assert timeline[-1]["comment"] == "提交调度"
    assert (
        work_order_client.post(
            f"/api/workorders/{work_order_id}/submit",
            json={},
        ).status_code
        == 409
    )


def test_api_enforces_create_permission_and_view_data_scope(
    work_order_client: TestClient,
) -> None:
    _login(work_order_client, "wangwu")
    created = _create(work_order_client, "仅调度中心可见").json()

    _login(work_order_client, "lisi")
    assert _create(work_order_client).status_code == 403
    assert work_order_client.get("/api/workorders").json() == []
    assert work_order_client.get(f"/api/workorders/{created['id']}").status_code == 404

    _login(work_order_client, "admin")
    visible = work_order_client.get("/api/workorders")
    assert visible.status_code == 200
    assert [item["id"] for item in visible.json()] == [created["id"]]
