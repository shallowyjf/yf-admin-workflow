from pathlib import Path


def test_system_router_does_not_access_sqlalchemy_or_commit() -> None:
    router_source = Path("app/system/router.py").read_text(encoding="utf-8")

    assert "sqlalchemy" not in router_source
    assert ".commit(" not in router_source
    assert "HealthService" in router_source
