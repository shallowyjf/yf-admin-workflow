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
    User,
)
from app.iam.repository import IAMRepository
from app.iam.seed import DEMO_INITIAL_PASSWORD, seed_iam
from app.iam.service import IAMService


def test_seed_is_idempotent_and_creates_required_relationships(
    db_session: Session,
) -> None:
    service = IAMService(IAMRepository(db_session))

    seed_iam(service)
    seed_iam(service)

    assert db_session.scalar(select(func.count()).select_from(Organization)) == 5
    assert db_session.scalar(select(func.count()).select_from(User)) == 5
    assert db_session.scalar(select(func.count()).select_from(Role)) == 5
    assert db_session.scalar(select(func.count()).select_from(Position)) == 3
    assert db_session.scalar(select(func.count()).select_from(Permission)) == 13
    assert db_session.scalar(select(func.count()).select_from(RolePermission)) == 30
    assert db_session.scalar(select(func.count()).select_from(RoleDataScope)) == 30

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
