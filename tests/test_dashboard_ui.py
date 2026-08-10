from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.base import Base
from app.iam.repository import IAMRepository
from app.iam.seed import DEMO_INITIAL_PASSWORD, seed_iam
from app.iam.service import IAMService
from app.main import create_app
from app.workflow.repository import WorkflowRepository
from app.workflow.seed import seed_workflow


@pytest.fixture()
def ui_client(tmp_path) -> Iterator[TestClient]:
    database_path = tmp_path / "ui.sqlite3"
    settings = Settings(
        app_name="I10 UI 回归",
        environment="test",
        database_url=f"sqlite:///{database_path.as_posix()}",
    )
    application = create_app(settings)
    with TestClient(application) as client:
        database = application.state.database
        Base.metadata.create_all(database.engine)
        with database.session_factory() as session:
            seed_iam(IAMService(IAMRepository(session)))
            seed_workflow(WorkflowRepository(session))
        yield client


def _login(client: TestClient, username: str) -> dict:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": DEMO_INITIAL_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()


def test_login_and_authentication_redirect(ui_client: TestClient) -> None:
    response = ui_client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=/dashboard"
    login = ui_client.get("/login")
    assert login.status_code == 200
    assert "登录协同中枢" in login.text


def test_admin_can_open_all_ten_core_views(ui_client: TestClient) -> None:
    _login(ui_client, "admin")
    paths = (
        "/login",
        "/dashboard",
        "/iam/organizations",
        "/iam/users",
        "/iam/roles",
        "/iam/positions",
        "/iam/permissions",
        "/workorders",
        "/tasks/mine",
    )
    for path in paths:
        response = ui_client.get(path)
        assert response.status_code == 200, path

    created = ui_client.post(
        "/ui/workorders",
        data={"title": "页面详情验收", "type": "REPAIR", "priority": "NORMAL"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    detail = ui_client.get(created.headers["location"])
    assert detail.status_code == 200
    assert "页面详情验收" in detail.text


def test_navigation_and_buttons_follow_effective_permissions(
    ui_client: TestClient,
) -> None:
    admin = _login(ui_client, "admin")
    assert "system:user:view" in admin["permission_codes"]
    admin_page = ui_client.get("/dashboard")
    assert "/iam/users" in admin_page.text

    lisi = _login(ui_client, "lisi")
    assert "system:user:view" not in lisi["permission_codes"]
    lisi_page = ui_client.get("/dashboard")
    assert "/iam/users" not in lisi_page.text
    work_orders = ui_client.get("/workorders")
    assert 'data-testid="create-workorder"' not in work_orders.text
    forbidden = ui_client.get("/iam/users")
    assert forbidden.status_code == 403
    assert "没有访问权限" in forbidden.text
    rejected_create = ui_client.post(
        "/ui/workorders",
        data={"title": "越权建单", "type": "REPAIR"},
    )
    assert rejected_create.status_code == 403
    assert "没有访问权限" in rejected_create.text
    rejected_user = ui_client.post(
        "/ui/users",
        data={
            "username": "ui.denied",
            "display_name": "越权用户",
            "password": "Initial@123",
        },
    )
    assert rejected_user.status_code == 403


def test_ui_completes_standard_dma_work_order_flow(ui_client: TestClient) -> None:
    wangwu = _login(ui_client, "wangwu")
    pipe_org_id = next(
        org["id"] for org in wangwu["organizations"] if org["org_code"] == "PIPE_OPERATION"
    )

    response = ui_client.post(
        "/ui/workorders",
        data={
            "title": "DMA10 压力异常",
            "type": "DMA_PRESSURE_ANOMALY",
            "priority": "HIGH",
            "location": "DMA10 分区",
            "description": "夜间压力持续偏低",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail_path = response.headers["location"]
    work_order_id = int(detail_path.rsplit("/", 1)[-1])
    assert 'data-testid="action-submit"' in ui_client.get(detail_path).text

    response = ui_client.post(
        f"/ui/workorders/{work_order_id}/submit",
        data={"comment": "提交调度"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    dispatch_page = ui_client.get(detail_path)
    assert 'data-testid="action-dispatch"' in dispatch_page.text
    response = ui_client.post(
        f"/ui/workorders/{work_order_id}/dispatch",
        data={"target_org_id": str(pipe_org_id), "comment": "派往管网运行部"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    _login(ui_client, "lisi")
    tasks = ui_client.get("/tasks/mine")
    assert f"工单 #{work_order_id}" in tasks.text
    assert 'data-testid="action-claim"' in tasks.text
    response = ui_client.post(
        f"/ui/workorders/{work_order_id}/claim",
        data={"next": "/tasks/mine"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert 'data-testid="action-result"' in ui_client.get(detail_path).text
    response = ui_client.post(
        f"/ui/workorders/{work_order_id}/result",
        data={"result": "定位漏点并完成修复", "comment": "压力恢复正常"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    _login(ui_client, "wangwu")
    assert 'data-testid="action-review"' in ui_client.get(detail_path).text
    response = ui_client.post(
        f"/ui/workorders/{work_order_id}/review",
        data={"decision": "APPROVE", "comment": "复核通过"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert 'data-testid="action-close"' in ui_client.get(detail_path).text
    response = ui_client.post(
        f"/ui/workorders/{work_order_id}/close",
        data={"comment": "DMA10 异常闭环"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    closed = ui_client.get(detail_path)
    assert "已关闭" in closed.text
    for action in ("CREATE", "SUBMIT", "DISPATCH", "CLAIM", "SUBMIT_RESULT", "APPROVE", "CLOSE"):
        assert action in closed.text


def test_templates_do_not_encode_stable_permission_codes() -> None:
    from pathlib import Path

    template_root = Path(__file__).resolve().parents[1] / "app" / "templates"
    source = "\n".join(path.read_text(encoding="utf-8") for path in template_root.glob("*.html"))
    assert "workorder:" not in source
    assert "system:" not in source


def test_organization_page_crud_and_permission_boundary(
    ui_client: TestClient,
) -> None:
    _login(ui_client, "admin")
    page = ui_client.get("/iam/organizations")
    assert 'data-testid="create-organization"' in page.text
    created = ui_client.post(
        "/ui/organizations",
        data={
            "org_code": "UI_TEAM",
            "org_name": "页面验收班组",
            "org_type": "TEAM",
            "parent_code": "PIPE_OPERATION",
            "sort_no": "88",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    organizations = ui_client.get("/api/orgs").json()
    organization_id = next(item["id"] for item in organizations if item["org_code"] == "UI_TEAM")
    updated = ui_client.post(
        f"/ui/organizations/{organization_id}/update",
        data={
            "org_name": "页面验收班组（更新）",
            "org_type": "TEAM",
            "parent_code": "GROUP",
            "sort_no": "89",
        },
        follow_redirects=False,
    )
    assert updated.status_code == 303
    assert "页面验收班组（更新）" in ui_client.get("/iam/organizations").text
    assert ui_client.post(
        f"/ui/organizations/{organization_id}/status",
        data={"is_active": "false"},
        follow_redirects=False,
    ).status_code == 303
    assert ui_client.post(
        f"/ui/organizations/{organization_id}/delete",
        follow_redirects=False,
    ).status_code == 303

    _login(ui_client, "lisi")
    assert ui_client.get("/iam/organizations").status_code == 403
    forbidden = ui_client.post(
        "/ui/organizations",
        data={"org_code": "UI_FORBIDDEN", "org_name": "越权组织"},
    )
    assert forbidden.status_code == 403


def test_user_page_lifecycle_and_membership_configuration(
    ui_client: TestClient,
) -> None:
    _login(ui_client, "admin")
    page = ui_client.get("/iam/users")
    assert 'data-testid="create-user"' in page.text
    created = ui_client.post(
        "/ui/users",
        data={
            "username": "ui.user",
            "display_name": "页面用户",
            "password": "Initial@123",
            "phone": "13900000000",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    users = ui_client.get("/api/users").json()
    user_id = next(item["id"] for item in users if item["username"] == "ui.user")
    organizations = ui_client.get("/api/orgs").json()
    dispatch_id = next(
        item["id"] for item in organizations if item["org_code"] == "DISPATCH_CENTER"
    )
    pipe_id = next(
        item["id"] for item in organizations if item["org_code"] == "PIPE_OPERATION"
    )
    configured = ui_client.post(
        f"/ui/users/{user_id}/memberships",
        data={
            "member_org_id": [str(dispatch_id), str(pipe_id)],
            "primary_org_id": str(dispatch_id),
            f"active_org_{dispatch_id}": "true",
            f"active_org_{pipe_id}": "true",
            f"role_{dispatch_id}": ["DISPATCHER"],
            f"position_{dispatch_id}": ["DISPATCHER"],
            f"role_{pipe_id}": ["REPAIRER"],
            f"position_{pipe_id}": ["REPAIRER"],
        },
        follow_redirects=False,
    )
    assert configured.status_code == 303
    updated = ui_client.post(
        f"/ui/users/{user_id}/update",
        data={"display_name": "页面用户（更新）", "phone": "13700000000"},
        follow_redirects=False,
    )
    assert updated.status_code == 303
    result_page = ui_client.get("/iam/users")
    assert "页面用户（更新）" in result_page.text
    assert "调度员" in result_page.text
    assert "抢修人员" in result_page.text
    assert ui_client.post(
        f"/ui/users/{user_id}/password",
        data={"new_password": "Changed@123"},
        follow_redirects=False,
    ).status_code == 303
    assert ui_client.post(
        f"/ui/users/{user_id}/status",
        data={"is_active": "false"},
        follow_redirects=False,
    ).status_code == 303
    disabled_login = ui_client.post(
        "/auth/login",
        json={"username": "ui.user", "password": "Changed@123"},
    )
    assert disabled_login.status_code == 401


def test_role_page_lifecycle_and_authorization_matrix(
    ui_client: TestClient,
) -> None:
    _login(ui_client, "admin")
    page = ui_client.get("/iam/roles")
    assert page.status_code == 200
    assert 'data-testid="create-role"' in page.text
    assert 'data-testid="save-role-authorization"' in page.text
    created = ui_client.post(
        "/ui/roles",
        data={
            "role_code": "UI_ROLE",
            "role_name": "页面角色",
            "role_type": "BUSINESS",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    roles = ui_client.get("/api/roles").json()
    role_id = next(item["id"] for item in roles if item["role_code"] == "UI_ROLE")
    with ui_client.app.state.database.session_factory() as session:
        repository = IAMRepository(session)
        permission = repository.get_permission_by_code("workorder:view")
        team = repository.get_organization_by_code("INSPECTION_TEAM_1")
        assert permission is not None and team is not None
        permission_id = permission.id
        team_id = team.id
    authorized = ui_client.post(
        f"/ui/roles/{role_id}/authorization",
        data={
            "permission_code": "workorder:view",
            f"scope_{permission_id}": "CUSTOM",
            f"custom_org_{permission_id}": str(team_id),
        },
        follow_redirects=False,
    )
    assert authorized.status_code == 303
    role = ui_client.get(f"/api/roles/{role_id}").json()
    assert role["authorization"][0]["scope_type"] == "CUSTOM"
    assert role["authorization"][0]["custom_org_codes"] == [
        "INSPECTION_TEAM_1"
    ]
    assert ui_client.post(
        f"/ui/roles/{role_id}/update",
        data={"role_name": "页面角色（更新）", "role_type": "FIELD"},
        follow_redirects=False,
    ).status_code == 303
    assert "页面角色（更新）" in ui_client.get("/iam/roles").text
    assert ui_client.post(
        f"/ui/roles/{role_id}/status",
        data={"is_active": "false"},
        follow_redirects=False,
    ).status_code == 303

    _login(ui_client, "lisi")
    assert ui_client.get("/iam/roles").status_code == 403
    forbidden = ui_client.post(
        "/ui/roles",
        data={"role_code": "UI_FORBIDDEN", "role_name": "越权角色"},
    )
    assert forbidden.status_code == 403
