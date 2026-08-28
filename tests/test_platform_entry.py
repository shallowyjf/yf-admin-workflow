from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.platform_seed import PLATFORM_ROOT_PASSWORD, seed_platform_root
from app.auth.repository import AuthRepository
from app.core.config import Settings
from app.db.base import Base
from app.iam.repository import IAMRepository
from app.iam.seed import DEMO_INITIAL_PASSWORD, seed_city_tenants
from app.iam.service import IAMService
from app.main import create_app
from app.project.repository import ProjectRepository
from app.project.seed import seed_projects


@pytest.fixture(scope="module")
def platform_environment(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[TestClient, dict[str, int]]]:
    database_path: Path = tmp_path_factory.mktemp("platform-entry") / "demo.sqlite3"
    settings = Settings(
        app_name="平台入口回归",
        environment="test",
        database_url=f"sqlite:///{database_path.as_posix()}",
    )
    application = create_app(settings)
    with TestClient(application) as client:
        database = application.state.database
        Base.metadata.create_all(database.engine)
        with database.session_factory() as session:
            seed_city_tenants(session)
            repository = IAMRepository(session)
            tenants = repository.list_tenants()
            tenant_ids = {tenant.tenant_code: tenant.id for tenant in tenants}
            for tenant in tenants:
                seed_projects(
                    ProjectRepository(session, tenant.id),
                    IAMService(IAMRepository(session, tenant.id)),
                )
            seed_platform_root(AuthRepository(session))
        yield client, tenant_ids


@pytest.fixture(autouse=True)
def clear_browser_cookies(
    platform_environment: tuple[TestClient, dict[str, int]],
) -> None:
    platform_environment[0].cookies.clear()


def _tenant_login(client: TestClient, login_name: str) -> dict:
    response = client.post(
        "/auth/login",
        json={
            "username": login_name,
            "password": DEMO_INITIAL_PASSWORD,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_platform_root_selects_city_before_getting_tenant_session(
    platform_environment: tuple[TestClient, dict[str, int]],
) -> None:
    client, tenant_ids = platform_environment
    login = client.post(
        "/auth/unified-login",
        json={"username": "root", "password": PLATFORM_ROOT_PASSWORD},
    )
    assert login.status_code == 200
    assert login.json() == {
        "identity_type": "PLATFORM_ROOT",
        "next_path": "/platform/tenants",
    }

    # 平台身份和租户身份分离：选城市之前不能调用租户业务 API。
    assert client.get("/auth/me").status_code == 401
    selector = client.get("/platform/tenants")
    assert selector.status_code == 200
    assert all(city in selector.text for city in ("江城市", "海州市", "云州市"))

    entered = client.post(
        f"/platform/tenants/{tenant_ids['CITY_HAIZHOU']}/enter",
        follow_redirects=False,
    )
    assert entered.status_code == 303
    assert entered.headers["location"] == "/portal"
    profile = client.get("/auth/me").json()
    assert profile["tenant_code"] == "CITY_HAIZHOU"
    assert profile["username"] == "admin"

    portal = client.get("/portal")
    assert portal.status_code == 200
    assert 'data-testid="current-login-user"' in portal.text
    assert "@haizhou.admin" in portal.text
    assert 'id="active-application"' not in portal.text
    assert 'id="active-project"' not in portal.text
    assert 'id="active-org"' not in portal.text
    assert "返回城市选择" in portal.text
    assert "权限管理中心" in portal.text
    assert "工单中心" in portal.text
    assert all(
        f"{domain}业务驾驶舱" in portal.text or f"{domain} GIS 驾驶舱" in portal.text
        for domain in ("供水", "排水", "燃气", "供热", "道路")
    )


def test_tenant_admin_uses_portal_and_field_worker_goes_to_workorders(
    platform_environment: tuple[TestClient, dict[str, int]],
) -> None:
    client, _ = platform_environment
    admin = _tenant_login(client, "admin")
    assert {item["domain_type"] for item in admin["applications"]} == {
        "WATER_SUPPLY",
        "DRAINAGE",
        "GAS",
        "HEATING",
        "ROAD",
    }
    admin_entry = client.get("/entry", follow_redirects=False)
    assert admin_entry.headers["location"] == "/portal"

    client.cookies.clear()
    _tenant_login(client, "lisi")
    worker_entry = client.get("/entry", follow_redirects=False)
    assert worker_entry.status_code == 303
    assert worker_entry.headers["location"] == "/workorders"


def test_specialist_portal_and_static_dashboard_follow_real_system_grants(
    platform_environment: tuple[TestClient, dict[str, int]],
) -> None:
    client, _ = platform_environment
    _tenant_login(client, "dma_specialist")
    assert client.get("/entry", follow_redirects=False).headers["location"] == "/portal"

    portal = client.get("/portal")
    assert "供水 GIS 驾驶舱" in portal.text
    assert "排水 GIS 驾驶舱" not in portal.text
    assert "燃气 GIS 驾驶舱" not in portal.text

    water = client.get("/business-dashboard/WATER_SUPPLY")
    assert water.status_code == 200
    assert "静态演示" in water.text
    assert "供水 DMA 漏损管理系统" in water.text
    denied = client.get("/business-dashboard/GAS")
    assert denied.status_code == 403


@pytest.mark.parametrize(
    ("login_name", "domain", "expected_applications", "denied_domain"),
    (
        ("water_manager", "WATER_SUPPLY", {"WATER_SUPPLY", "WATER_HYDRAULIC"}, "GAS"),
        ("drainage_manager", "DRAINAGE", {"DRAINAGE"}, "WATER_SUPPLY"),
        ("gas_manager", "GAS", {"GAS"}, "HEATING"),
        ("heating_manager", "HEATING", {"HEATING"}, "DRAINAGE"),
        ("road_manager", "ROAD", {"ROAD"}, "GAS"),
    ),
)
def test_business_manager_goes_directly_to_own_isolated_gis_dashboard(
    platform_environment: tuple[TestClient, dict[str, int]],
    login_name: str,
    domain: str,
    expected_applications: set[str],
    denied_domain: str,
) -> None:
    client, _ = platform_environment
    profile = _tenant_login(client, login_name)
    assert {item["application_code"] for item in profile["applications"]} == (expected_applications)
    entry = client.get("/entry", follow_redirects=False)
    assert entry.status_code == 303
    assert entry.headers["location"] == f"/business-dashboard/{domain}"
    dashboard = client.get(entry.headers["location"])
    assert dashboard.status_code == 200
    assert "GIS 管理系统驾驶舱" in dashboard.text
    assert "设施一张图" in dashboard.text
    assert client.get(f"/business-dashboard/{denied_domain}").status_code == 403


def test_tenant_entry_requires_platform_root_session(
    platform_environment: tuple[TestClient, dict[str, int]],
) -> None:
    client, tenant_ids = platform_environment
    response = client.post(
        f"/platform/tenants/{tenant_ids['DEMO']}/enter",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_unified_login_auto_resolves_city_and_role_landing(
    platform_environment: tuple[TestClient, dict[str, int]],
) -> None:
    client, _ = platform_environment
    login = client.post(
        "/auth/unified-login",
        json={"username": "haizhou.admin", "password": DEMO_INITIAL_PASSWORD},
    )
    assert login.status_code == 200
    assert login.json() == {"identity_type": "TENANT_USER", "next_path": "/entry"}
    assert client.get("/auth/me").json()["tenant_code"] == "CITY_HAIZHOU"
    assert client.get("/entry", follow_redirects=False).headers["location"] == "/portal"

    client.cookies.clear()
    worker = client.post(
        "/auth/unified-login",
        json={"username": "yunzhou.lisi", "password": DEMO_INITIAL_PASSWORD},
    )
    assert worker.status_code == 200
    assert client.get("/auth/me").json()["tenant_code"] == "CITY_YUNZHOU"
    assert client.get("/entry", follow_redirects=False).headers["location"] == "/workorders"
