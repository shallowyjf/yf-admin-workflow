from fastapi.testclient import TestClient
import pytest

from app.data import DemoRepository
from app.main import create_app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app(DemoRepository()))


def test_health_reports_iteration_and_version(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0", "iteration": "01"}


def test_dashboard_page_contains_iteration_one_workbench(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "澄川智慧供水运营平台" in response.text
    assert "供水管网运行一张图" in response.text
    assert "告警事件工作台" in response.text
    assert '/static/app.js' in response.text


@pytest.mark.parametrize(
    ("path", "content_type"),
    [("/static/styles.css", "text/css"), ("/static/app.js", "application/javascript")],
)
def test_frontend_assets_are_served(client: TestClient, path: str, content_type: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert content_type in response.headers["content-type"]
    assert len(response.content) > 1_000


def test_overview_returns_expected_operational_contract(client: TestClient) -> None:
    response = client.get("/api/overview")
    payload = response.json()

    assert response.status_code == 200
    assert payload["scope"] == {"id": "all", "name": "全域供水"}
    assert payload["metrics"]["supply"]["value"] == 18.42
    assert payload["metrics"]["alarms"]["value"] == 5
    assert 7.0 < payload["metrics"]["leakage"]["value"] < 9.0
    assert len(payload["trend"]["labels"]) == len(payload["trend"]["flow"]) == 8
    assert len(payload["zones"]) == 4


def test_zone_filter_changes_metrics_and_events(client: TestClient) -> None:
    response = client.get("/api/overview?zone=east")
    payload = response.json()

    assert response.status_code == 200
    assert payload["scope"]["name"] == "东城 DMA"
    assert payload["metrics"]["supply"]["value"] == 4.76
    assert payload["metrics"]["leakage"]["value"] == 10.8
    assert payload["events"]
    assert {item["zone_id"] for item in payload["events"]} == {"east"}


@pytest.mark.parametrize("endpoint", ["/api/overview?zone=missing", "/api/events?zone=missing"])
def test_unknown_zone_returns_404(client: TestClient, endpoint: str) -> None:
    response = client.get(endpoint)

    assert response.status_code == 404
    assert response.json()["detail"] == "DMA 分区不存在"


def test_pending_event_can_enter_processing_workflow(client: TestClient) -> None:
    response = client.post(
        "/api/events/EVT-260807-01/acknowledge",
        json={"operator": "回归测试员"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "processing"
    assert payload["status_text"] == "处理中"
    assert payload["ack_by"] == "回归测试员"
    assert payload["updated_at"]

    overview = client.get("/api/overview?zone=east").json()
    assert overview["summary"]["pending"] == 0
    assert overview["summary"]["processing"] == 1


def test_acknowledgement_is_idempotent_and_missing_event_is_404(client: TestClient) -> None:
    first = client.post(
        "/api/events/EVT-260807-01/acknowledge",
        json={"operator": "首次确认人"},
    ).json()
    second = client.post(
        "/api/events/EVT-260807-01/acknowledge",
        json={"operator": "重复确认人"},
    ).json()

    assert second["status"] == "processing"
    assert second["ack_by"] == first["ack_by"] == "首次确认人"
    assert client.post(
        "/api/events/NOT-FOUND/acknowledge",
        json={"operator": "回归测试员"},
    ).status_code == 404


def test_acknowledgement_validates_operator(client: TestClient) -> None:
    response = client.post(
        "/api/events/EVT-260807-01/acknowledge",
        json={"operator": "A"},
    )

    assert response.status_code == 422
