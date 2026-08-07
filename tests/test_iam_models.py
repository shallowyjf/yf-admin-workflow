import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.iam.models import User, UserOrganization
from app.iam.repository import IAMRepository
from app.iam.service import DuplicateIAMRelation, IAMService


@pytest.fixture()
def service(db_session: Session) -> IAMService:
    return IAMService(IAMRepository(db_session))


def test_user_can_join_two_organizations_with_independent_roles(
    service: IAMService,
) -> None:
    service.create_organization("GROUP", "XX水务集团", "GROUP")
    service.create_organization("ORG_A", "组织A", "DEPARTMENT", "GROUP")
    service.create_organization("ORG_B", "组织B", "DEPARTMENT", "GROUP")
    service.create_user("multi", "多组织用户", "!test")
    service.create_role("REPAIRER", "抢修人员")

    service.add_user_to_organization("multi", "ORG_A", is_primary=True)
    service.add_user_to_organization("multi", "ORG_B")
    service.assign_role("multi", "ORG_A", "REPAIRER")

    membership_a = service.get_membership("multi", "ORG_A")
    membership_b = service.get_membership("multi", "ORG_B")
    assert membership_a is not None and membership_b is not None
    assert {link.role.role_code for link in membership_a.role_links} == {"REPAIRER"}
    assert membership_b.role_links == []
    assert not hasattr(User, "org_id")
    assert not hasattr(User, "role_id")


def test_service_and_database_reject_duplicate_membership(
    service: IAMService,
    db_session: Session,
) -> None:
    organization = service.create_organization("GROUP", "XX水务集团")
    user = service.create_user("duplicate", "重复成员", "!test")
    service.add_user_to_organization("duplicate", "GROUP")

    with pytest.raises(DuplicateIAMRelation):
        service.add_user_to_organization("duplicate", "GROUP")

    db_session.add(UserOrganization(user_id=user.id, org_id=organization.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_organization_tree_preserves_hierarchy_and_sorting(service: IAMService) -> None:
    service.create_organization("GROUP", "XX水务集团", "GROUP")
    service.create_organization("PIPE", "管网运行部", "DEPARTMENT", "GROUP", 20)
    service.create_organization("DISPATCH", "调度中心", "DEPARTMENT", "GROUP", 10)
    service.create_organization("TEAM", "巡检一组", "TEAM", "PIPE", 10)

    tree = service.organization_tree()

    assert [node.org_code for node in tree] == ["GROUP"]
    assert [node.org_code for node in tree[0].children] == ["DISPATCH", "PIPE"]
    assert [node.org_code for node in tree[0].children[1].children] == ["TEAM"]
