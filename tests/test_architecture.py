from pathlib import Path


def test_system_router_does_not_access_sqlalchemy_or_commit() -> None:
    router_source = Path("app/system/router.py").read_text(encoding="utf-8")

    assert "sqlalchemy" not in router_source
    assert ".commit(" not in router_source
    assert "HealthService" in router_source


def test_authorization_uses_stable_codes_not_display_names() -> None:
    authorization_source = Path("app/iam/authorization.py").read_text(encoding="utf-8")

    assert "permission_code" in authorization_source
    assert "role_name" not in authorization_source
    assert "org_name" not in authorization_source
    assert "sqlalchemy" not in authorization_source


def test_auth_router_delegates_persistence_to_services() -> None:
    router_source = Path("app/auth/router.py").read_text(encoding="utf-8")

    assert ".commit(" not in router_source
    assert "select(" not in router_source
    assert "AuthService" in router_source
