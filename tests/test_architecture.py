from pathlib import Path

from app.iam.models import User


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


def test_iam_router_delegates_persistence_and_authorization_to_services() -> None:
    router_source = Path("app/iam/router.py").read_text(encoding="utf-8")

    assert ".commit(" not in router_source
    assert "select(" not in router_source
    assert "OrganizationAdministrationService" in router_source


def test_user_router_delegates_persistence_and_authorization_to_services() -> None:
    router_source = Path("app/iam/user_router.py").read_text(encoding="utf-8")

    assert ".commit(" not in router_source
    assert "select(" not in router_source
    assert "UserAdministrationService" in router_source


def test_all_routers_delegate_database_work_to_services() -> None:
    forbidden_fragments = (".commit(", "select(", ".execute(", ".query(")

    for router_path in Path("app").rglob("*router.py"):
        source = router_path.read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            assert fragment not in source, f"{router_path} contains {fragment}"


def test_workflow_core_depends_on_ports_instead_of_iam() -> None:
    for path in Path("app/workflow").glob("*.py"):
        if path.name == "factory.py":
            continue
        source = path.read_text(encoding="utf-8")
        assert "app.iam" not in source, f"{path} bypasses the workflow port boundary"


def test_user_membership_remains_relational() -> None:
    for forbidden_attribute in ("org_id", "role_id", "position_id"):
        assert not hasattr(User, forbidden_attribute)


def test_work_order_state_changes_are_centralized_in_domain_model() -> None:
    model_source = Path("app/workorder/models.py").read_text(encoding="utf-8")
    assert "self.status = WorkOrderStateMachine.transition(" in model_source

    for path in Path("app/workorder").glob("*.py"):
        if path.name == "models.py":
            continue
        source = path.read_text(encoding="utf-8")
        assert ".status =" not in source, f"{path} mutates work-order state directly"
