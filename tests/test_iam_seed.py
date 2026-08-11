from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.security import PasswordHasher
from app.iam.models import (
    Organization,
    Permission,
    Position,
    Role,
    RoleDataScope,
    RolePermission,
    Tenant,
    User,
)
from app.iam.repository import IAMRepository
from app.iam.seed import DEMO_INITIAL_PASSWORD, seed_iam
from app.iam.service import IAMService


def test_seed_is_idempotent_and_creates_required_relationships(
    db_session: Session,
) -> None:
    service = IAMService(IAMRepository(db_session))

    summary = seed_iam(service)
    seed_iam(service)

    assert db_session.scalar(select(func.count()).select_from(Tenant)) == 1
    assert db_session.scalar(select(func.count()).select_from(Organization)) == (
        summary.organizations
    )
    assert db_session.scalar(select(func.count()).select_from(User)) == summary.users
    assert db_session.scalar(select(func.count()).select_from(Role)) == summary.roles
    assert db_session.scalar(select(func.count()).select_from(Position)) == summary.positions
    assert db_session.scalar(select(func.count()).select_from(Permission)) == (
        summary.permissions
    )
    assert db_session.scalar(select(func.count()).select_from(RolePermission)) == (
        summary.role_permissions
    )
    assert db_session.scalar(select(func.count()).select_from(RoleDataScope)) == (
        summary.data_scopes
    )

    assert {
        organization.org_type for organization in service.list_organizations()
    }.issuperset({"OWNER", "REGULATOR", "CONTRACTOR", "PLATFORM"})

    repairers = set()
    for username in ("lisi", "zhaoliu"):
        membership = service.get_membership(username, "PIPE_OPERATION")
        assert membership is not None
        assert {link.role.role_code for link in membership.role_links} == {"REPAIRER"}
        repairers.add(username)
    assert repairers == {"lisi", "zhaoliu"}

    manager = service.get_membership("zhangsan", "PIPE_OPERATION")
    assert manager is not None
    assert {link.position.position_code for link in manager.position_links} == {
        "DEPT_MANAGER"
    }

    repairer_role = service.get_role("REPAIRER")
    assert repairer_role is not None
    assert {scope.scope_type for scope in repairer_role.data_scopes} == {"SELF"}

    wangwu_secondary = service.get_membership("wangwu", "PIPE_OPERATION")
    assert wangwu_secondary is not None
    assert not wangwu_secondary.is_primary
    assert wangwu_secondary.role_links == []

    wangwu = service.get_user("wangwu")
    assert wangwu is not None
    assert wangwu.password_hash != DEMO_INITIAL_PASSWORD
    assert PasswordHasher().verify(DEMO_INITIAL_PASSWORD, wangwu.password_hash)

    leader = service.get_membership("owner_leader", "GROUP")
    regulator = service.get_membership("regulator", "REGULATOR")
    platform_operator = service.get_membership("platform_ops", "PLATFORM")
    assert leader is not None and regulator is not None and platform_operator is not None
    assert {link.role.role_code for link in leader.role_links} == {"OWNER_LEADER"}
    assert {link.role.role_code for link in regulator.role_links} == {"REVIEWER"}
    assert {link.role.role_code for link in platform_operator.role_links} == {
        "PLATFORM_OPERATOR"
    }
