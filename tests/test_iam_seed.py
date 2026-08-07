from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.iam.models import Organization, Position, Role, User
from app.iam.repository import IAMRepository
from app.iam.seed import seed_iam
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
