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


def test_i08_task_actions_enforce_access_and_state_transitions(
    work_order_client: TestClient,
) -> None:
    regulator_profile = _login(work_order_client, "regulator")
    regulator_org_id = _org_id(regulator_profile, "REGULATOR")
    wangwu_profile = _login(work_order_client, "wangwu")
    pipe_org_id = _org_id(wangwu_profile, "PIPE_OPERATION")
    created = _create(work_order_client, "I08 任务动作").json()
    work_order_id = created["id"]
    assert (
        work_order_client.post(
            f"/api/workorders/{work_order_id}/submit",
            json={},
        ).status_code
        == 200
    )

    _login(work_order_client, "admin")
    assert (
        work_order_client.post(
            f"/api/workorders/{work_order_id}/dispatch",
            json={"target_org_id": pipe_org_id},
        ).status_code
        == 403
    )

    _login(work_order_client, "wangwu")
    dispatched = work_order_client.post(
        f"/api/workorders/{work_order_id}/dispatch",
        json={"target_org_id": pipe_org_id, "comment": "派给管网运行部"},
    )
    assert dispatched.status_code == 200
    assert dispatched.json()["status"] == "PENDING_CLAIM"
    assert dispatched.json()["current_org_id"] == pipe_org_id

    _login(work_order_client, "admin")
    assert (
        work_order_client.post(
            f"/api/workorders/{work_order_id}/claim",
            json={},
        ).status_code
        == 403
    )

    lisi_profile = _login(work_order_client, "lisi")
    lisi_id = lisi_profile["user_id"]
    claimed = work_order_client.post(
        f"/api/workorders/{work_order_id}/claim",
        json={"comment": "李四认领"},
    )
    assert claimed.status_code == 200
    assert claimed.json()["status"] == "PROCESSING"
    assert claimed.json()["current_assignee_id"] == lisi_id

    _login(work_order_client, "zhaoliu")
    assert work_order_client.get("/api/tasks/mine").json() == []
    assert (
        work_order_client.post(
            f"/api/workorders/{work_order_id}/claim",
            json={},
        ).status_code
        == 409
    )
    assert (
        work_order_client.post(
            f"/api/workorders/{work_order_id}/result",
            json={"result": "非办理人提交"},
        ).status_code
        == 403
    )

    _login(work_order_client, "lisi")
    submitted_result = work_order_client.post(
        f"/api/workorders/{work_order_id}/result",
        json={
            "result": "已修复漏点",
            "comment": "等待复核",
            "review_org_id": regulator_org_id,
        },
    )
    assert submitted_result.status_code == 200
    assert submitted_result.json()["status"] == "PENDING_REVIEW"
    assert submitted_result.json()["current_org_id"] == regulator_org_id

    _login(work_order_client, "admin")
    assert (
        work_order_client.post(
            f"/api/workorders/{work_order_id}/review",
            json={"decision": "APPROVE"},
        ).status_code
        == 403
    )

    _login(work_order_client, "regulator")
    review_tasks = work_order_client.get("/api/tasks/mine").json()
    assert len(review_tasks) == 1
    assert review_tasks[0]["business_id"] == work_order_id
    assert review_tasks[0]["task_type"] == "REVIEW"
    assert work_order_client.get(f"/api/workorders/{work_order_id}").status_code == 200
    rejected = work_order_client.post(
        f"/api/workorders/{work_order_id}/review",
        json={"decision": "REJECT", "comment": "补充处理结果"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "PROCESSING"
    assert rejected.json()["current_org_id"] == pipe_org_id

    _login(work_order_client, "lisi")
    returned_tasks = work_order_client.get("/api/tasks/mine").json()
    assert len(returned_tasks) == 1
    assert returned_tasks[0]["status"] == "CLAIMED"
    assert returned_tasks[0]["assignee_id"] == lisi_id
    assert (
        work_order_client.post(
            f"/api/workorders/{work_order_id}/result",
            json={
                "result": "已补充现场照片",
                "review_org_id": regulator_org_id,
            },
        ).status_code
        == 200
    )

    _login(work_order_client, "regulator")
    approved = work_order_client.post(
        f"/api/workorders/{work_order_id}/review",
        json={"decision": "APPROVE"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "COMPLETED"
    _login(work_order_client, "wangwu")
    closed = work_order_client.post(
        f"/api/workorders/{work_order_id}/close",
        json={"comment": "关闭工单"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"
    assert closed.json()["completed_at"] is not None
    assert closed.json()["closed_at"] is not None


def test_i16_transfer_comment_and_urge_keep_workflow_and_timeline_consistent(
    work_order_client: TestClient,
) -> None:
    regulator = _login(work_order_client, "regulator")
    regulator_org_id = _org_id(regulator, "REGULATOR")
    wangwu = _login(work_order_client, "wangwu")
    pipe_org_id = _org_id(wangwu, "PIPE_OPERATION")
    work_order_id = _create(work_order_client, "I16 协作工单").json()["id"]
    work_order_client.post(f"/api/workorders/{work_order_id}/submit", json={})
    work_order_client.post(
        f"/api/workorders/{work_order_id}/dispatch",
        json={"target_org_id": pipe_org_id},
    )

    lisi = _login(work_order_client, "lisi")
    lisi_id = lisi["user_id"]
    claimed = work_order_client.post(
        f"/api/workorders/{work_order_id}/claim",
        json={"comment": "李四认领"},
    )
    assert claimed.status_code == 200

    zhaoliu = _login(work_order_client, "zhaoliu")
    zhaoliu_id = zhaoliu["user_id"]
    admin = _login(work_order_client, "admin")
    admin_id = admin["user_id"]

    _login(work_order_client, "zhangsan")
    comment = work_order_client.post(
        f"/api/workorders/{work_order_id}/comments",
        json={"comment": "  阀门间钥匙已交接  "},
    )
    assert comment.status_code == 201
    assert comment.json()["action_type"] == "COMMENT"
    assert comment.json()["comment"] == "阀门间钥匙已交接"
    urged = work_order_client.post(
        f"/api/workorders/{work_order_id}/urge",
        json={"comment": "请在 30 分钟内反馈"},
    )
    assert urged.status_code == 201
    assert urged.json()["payload_json"] == {
        "current_org_id": pipe_org_id,
        "current_assignee_id": lisi_id,
    }
    invalid_target = work_order_client.post(
        f"/api/workorders/{work_order_id}/transfer",
        json={"target_user_id": admin_id},
    )
    assert invalid_target.status_code == 422

    transferred = work_order_client.post(
        f"/api/workorders/{work_order_id}/transfer",
        json={
            "target_user_id": zhaoliu_id,
            "comment": "李四交班，转赵六",
        },
    )
    assert transferred.status_code == 200
    assert transferred.json()["status"] == "PROCESSING"
    assert transferred.json()["current_assignee_id"] == zhaoliu_id

    _login(work_order_client, "lisi")
    assert work_order_client.get("/api/tasks/mine").json() == []
    assert (
        work_order_client.post(
            f"/api/workorders/{work_order_id}/comments",
            json={"comment": "已转出"},
        ).status_code
        == 404
    )

    _login(work_order_client, "zhaoliu")
    tasks = work_order_client.get("/api/tasks/mine").json()
    assert len(tasks) == 1
    assert tasks[0]["status"] == "CLAIMED"
    assert tasks[0]["assignee_id"] == zhaoliu_id
    assert (
        work_order_client.post(
            f"/api/workorders/{work_order_id}/result",
            json={
                "result": "赵六完成现场处理",
                "review_org_id": regulator_org_id,
            },
        ).status_code
        == 200
    )

    _login(work_order_client, "regulator")
    timeline = work_order_client.get(
        f"/api/workorders/{work_order_id}/timeline"
    ).json()
    assert [item["action_type"] for item in timeline] == [
        "CREATE",
        "SUBMIT",
        "DISPATCH",
        "CLAIM",
        "COMMENT",
        "URGE",
        "TRANSFER",
        "SUBMIT_RESULT",
    ]
    assert timeline[-2]["payload_json"] == {
        "previous_assignee_id": lisi_id,
        "target_assignee_id": zhaoliu_id,
    }


def test_i17_urge_notification_is_recipient_owned_and_can_be_read(
    work_order_client: TestClient,
) -> None:
    wangwu = _login(work_order_client, "wangwu")
    pipe_org_id = _org_id(wangwu, "PIPE_OPERATION")
    work_order_id = _create(work_order_client, "I17 通知工单").json()["id"]
    work_order_client.post(f"/api/workorders/{work_order_id}/submit", json={})
    work_order_client.post(
        f"/api/workorders/{work_order_id}/dispatch",
        json={"target_org_id": pipe_org_id},
    )
    _login(work_order_client, "lisi")
    work_order_client.post(f"/api/workorders/{work_order_id}/claim", json={})

    _login(work_order_client, "zhangsan")
    urged = work_order_client.post(
        f"/api/workorders/{work_order_id}/urge",
        json={"comment": "请在今天完成"},
    )
    assert urged.status_code == 201

    _login(work_order_client, "lisi")
    inbox = work_order_client.get("/api/notifications")
    assert inbox.status_code == 200
    assert len(inbox.json()) == 1
    notification = inbox.json()[0]
    assert notification["event_type"] == "WORKORDER_URGED"
    assert notification["status"] == "UNREAD"

    _login(work_order_client, "zhaoliu")
    assert (
        work_order_client.post(
            f"/api/notifications/{notification['id']}/read"
        ).status_code
        == 404
    )
    _login(work_order_client, "lisi")
    read = work_order_client.post(
        f"/api/notifications/{notification['id']}/read"
    )
    assert read.status_code == 200
    assert read.json()["status"] == "READ"
    assert read.json()["read_at"] is not None
