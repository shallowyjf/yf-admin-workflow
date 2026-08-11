from fastapi.testclient import TestClient


def test_health_returns_current_iteration_and_database_connectivity(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "iteration": "I21",
        "version": "0.1.0",
    }


def test_openapi_uses_configured_application_name(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "权限流程测试平台"
    assert response.json()["info"]["version"] == "0.1.0"
