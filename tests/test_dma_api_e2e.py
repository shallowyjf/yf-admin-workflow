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
def dma_client(tmp_path: Path) -> Iterator[TestClient]:
    database_url = f"sqlite:///{(tmp_path / 'dma-e2e.db').as_posix()}"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    with database.session_factory() as session:
        seed_iam(IAMService(IAMRepository(session)))
        seed_workflow(WorkflowRepository(session))
    database.dispose()
    settings = Settings(
        app_name="DMA E2E",
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


def _org_id(profile: dict, org_code: str) -> int:
    return next(
        organization["id"]
        for organization in profile["organizations"]
        if organization["org_code"] == org_code
    )


def _matching_task(client: TestClient, work_order_id: int) -> dict:
    tasks = client.get("/api/tasks/mine")
    assert tasks.status_code == 200
    matches = [
        task
        for task in tasks.json()
        if task["business_id"] == work_order_id
        and task["task_type"] == "HANDLE"
    ]
    assert len(matches) == 1
    return matches[0]


def test_standard_dma_api_e2e_has_exact_candidates_and_timeline(
    dma_client: TestClient,
) -> None:
    regulator_profile = _login(dma_client, "regulator")
    regulator_org_id = _org_id(regulator_profile, "REGULATOR")
    wangwu_profile = _login(dma_client, "wangwu")
    pipe_org_id = _org_id(wangwu_profile, "PIPE_OPERATION")
    created_response = dma_client.post(
        "/api/workorders",
        json={
            "title": "DMA07 压力异常",
            "type": "DMA_PRESSURE_ANOMALY",
            "source_type": "DMA_MONITORING",
            "source_id": "DMA07",
            "priority": "HIGH",
            "asset_type": "DMA_ZONE",
            "asset_id": "DMA07",
            "location": "DMA07 分区",
            "description": "夜间最小流量和压力曲线异常",
        },
    )
    assert created_response.status_code == 201
    work_order_id = created_response.json()["id"]
    assert created_response.json()["status"] == "DRAFT"
    assert (
        dma_client.post(
            f"/api/workorders/{work_order_id}/submit",
            json={"comment": "提交调度处置"},
        ).json()["status"]
        == "PENDING_DISPATCH"
    )
    assert (
        dma_client.post(
            f"/api/workorders/{work_order_id}/dispatch",
            json={
                "target_org_id": pipe_org_id,
                "comment": "派给管网运行部抢修人员",
            },
        ).json()["status"]
        == "PENDING_CLAIM"
    )

    lisi_profile = _login(dma_client, "lisi")
    lisi_task = _matching_task(dma_client, work_order_id)
    zhaoliu_profile = _login(dma_client, "zhaoliu")
    zhaoliu_task = _matching_task(dma_client, work_order_id)
    expected_candidates = {
        lisi_profile["user_id"],
        zhaoliu_profile["user_id"],
    }
    assert set(lisi_task["candidate_user_ids"]) == expected_candidates
    assert set(zhaoliu_task["candidate_user_ids"]) == expected_candidates
    assert lisi_task["id"] == zhaoliu_task["id"]

    _login(dma_client, "lisi")
    claimed = dma_client.post(
        f"/api/workorders/{work_order_id}/claim",
        json={"comment": "李四认领"},
    )
    assert claimed.status_code == 200
    assert claimed.json()["status"] == "PROCESSING"
    assert claimed.json()["current_assignee_id"] == lisi_profile["user_id"]

    _login(dma_client, "zhaoliu")
    second_claim = dma_client.post(
        f"/api/workorders/{work_order_id}/claim",
        json={"comment": "赵六竞争认领"},
    )
    assert second_claim.status_code == 409

    _login(dma_client, "lisi")
    result = dma_client.post(
        f"/api/workorders/{work_order_id}/result",
        json={
            "result": "已定位并修复 DMA07 漏点，压力恢复正常",
            "comment": "提交处理结果",
            "review_org_id": regulator_org_id,
        },
    )
    assert result.status_code == 200
    assert result.json()["status"] == "PENDING_REVIEW"

    _login(dma_client, "regulator")
    review_task = dma_client.get("/api/tasks/mine").json()
    assert len(review_task) == 1
    assert review_task[0]["business_id"] == work_order_id
    assert review_task[0]["task_type"] == "REVIEW"
    approved = dma_client.post(
        f"/api/workorders/{work_order_id}/review",
        json={"decision": "APPROVE", "comment": "复核通过"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "COMPLETED"
    _login(dma_client, "wangwu")
    closed = dma_client.post(
        f"/api/workorders/{work_order_id}/close",
        json={"comment": "DMA07 异常闭环"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"

    detail = dma_client.get(f"/api/workorders/{work_order_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "CLOSED"
    visible_ids = {
        item["id"] for item in dma_client.get("/api/workorders").json()
    }
    assert work_order_id in visible_ids
    timeline = dma_client.get(
        f"/api/workorders/{work_order_id}/timeline"
    )
    assert timeline.status_code == 200
    assert [item["action_type"] for item in timeline.json()] == [
        "CREATE",
        "SUBMIT",
        "DISPATCH",
        "CLAIM",
        "SUBMIT_RESULT",
        "APPROVE",
        "CLOSE",
    ]
