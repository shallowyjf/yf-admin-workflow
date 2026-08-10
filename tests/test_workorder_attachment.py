from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.base import Base
from app.db.session import Database
from app.iam.repository import IAMRepository
from app.iam.seed import seed_iam
from app.iam.service import IAMService
from app.main import create_app
from app.workflow.repository import WorkflowRepository
from app.workflow.seed import seed_workflow
from app.workorder.repository import WorkOrderRepository
from app.workorder.seed import seed_workorder


@pytest.fixture()
def work_order_client(tmp_path: Path) -> Iterator[TestClient]:
    database_url = f"sqlite:///{(tmp_path / 'attachments.db').as_posix()}"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    with database.session_factory() as session:
        seed_iam(IAMService(IAMRepository(session)))
        seed_workflow(WorkflowRepository(session))
        seed_workorder(WorkOrderRepository(session))
    database.dispose()
    settings = Settings(environment="test", database_url=database_url)
    with TestClient(create_app(settings)) as client:
        yield client


def test_attachment_upload_list_download_and_security_boundaries(
    work_order_client: TestClient,
) -> None:
    login = work_order_client.post(
        "/auth/login",
        json={"username": "zhangsan", "password": "Demo@123456"},
    )
    assert login.status_code == 200
    created = work_order_client.post(
        "/api/workorders",
        json={"title": "附件验收", "type": "REPAIR"},
    ).json()
    work_order_id = created["id"]

    uploaded = work_order_client.post(
        f"/api/workorders/{work_order_id}/attachments",
        files={"file": ("现场记录.txt", "阀门已关闭".encode(), "text/plain")},
    )
    assert uploaded.status_code == 201
    attachment = uploaded.json()
    assert attachment["filename"] == "现场记录.txt"
    assert attachment["scan_status"] == "CLEAN"
    assert attachment["size_bytes"] == len("阀门已关闭".encode())
    assert len(attachment["sha256"]) == 64

    listed = work_order_client.get(
        f"/api/workorders/{work_order_id}/attachments"
    )
    assert listed.status_code == 200
    assert listed.json() == [attachment]
    downloaded = work_order_client.get(
        f"/api/workorders/{work_order_id}/attachments/{attachment['id']}/download"
    )
    assert downloaded.status_code == 200
    assert downloaded.content == "阀门已关闭".encode()
    assert downloaded.headers["x-content-type-options"] == "nosniff"

    executable = work_order_client.post(
        f"/api/workorders/{work_order_id}/attachments",
        files={"file": ("伪装.txt", b"MZ unsafe", "text/plain")},
    )
    assert executable.status_code == 422
    disallowed = work_order_client.post(
        f"/api/workorders/{work_order_id}/attachments",
        files={"file": ("payload.exe", b"unsafe", "application/octet-stream")},
    )
    assert disallowed.status_code == 422

    work_order_client.post(
        "/auth/login",
        json={"username": "lisi", "password": "Demo@123456"},
    )
    assert (
        work_order_client.get(
            f"/api/workorders/{work_order_id}/attachments/{attachment['id']}/download"
        ).status_code
        == 404
    )

    work_order_client.post(
        "/auth/login",
        json={"username": "zhangsan", "password": "Demo@123456"},
    )
    timeline = work_order_client.get(
        f"/api/workorders/{work_order_id}/timeline"
    ).json()
    assert [item["action_type"] for item in timeline] == [
        "CREATE",
        "ATTACHMENT_UPLOAD",
    ]
