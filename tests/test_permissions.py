from sqlalchemy.orm import Session

from app.iam.authorization import DataScopeType, PermissionService
from app.iam.repository import IAMRepository
from app.iam.service import IAMService


def _authorization_services(
    db_session: Session,
) -> tuple[IAMService, PermissionService]:
    repository = IAMRepository(db_session)
    return IAMService(repository), PermissionService(repository)


def _create_org_tree(service: IAMService) -> dict[str, int]:
    service.create_organization("ROOT", "集团", "GROUP")
    service.create_organization("DEPT", "运行部", "DEPARTMENT", "ROOT")
    service.create_organization("TEAM", "抢修班", "TEAM", "DEPT")
    service.create_organization("SIBLING", "调度部", "DEPARTMENT", "ROOT")
    return {
        code: service.get_organization(code).id  # type: ignore[union-attr]
        for code in ("ROOT", "DEPT", "TEAM", "SIBLING")
    }


def _grant_view(
    service: IAMService,
    scope_type: DataScopeType,
    *,
    custom_org_codes: tuple[str, ...] = (),
) -> tuple[int, int]:
    service.create_user("operator", "操作员", "!test")
    service.create_role("OPERATOR", "操作角色")
    service.create_permission("workorder:view", "查看工单", "WORKORDER")
    membership = service.add_user_to_organization("operator", "DEPT", is_primary=True)
    service.assign_role("operator", "DEPT", "OPERATOR")
    service.grant_permission("OPERATOR", "workorder:view")
    service.set_role_data_scope(
        "OPERATOR",
        "workorder:view",
        scope_type,
        custom_org_codes=custom_org_codes,
    )
    user = service.get_user("operator")
    assert user is not None
    return user.id, membership.org_id


def test_permission_is_resolved_only_in_the_active_organization(
    db_session: Session,
) -> None:
    service, permissions = _authorization_services(db_session)
    org_ids = _create_org_tree(service)
    user_id, active_org_id = _grant_view(service, DataScopeType.ORG)
    service.add_user_to_organization("operator", "SIBLING")

    assert permissions.has_permission(user_id, "workorder:view", active_org_id)
    assert not permissions.has_permission(
        user_id,
        "workorder:view",
        org_ids["SIBLING"],
    )


def test_org_scope_contains_only_the_active_organization(db_session: Session) -> None:
    service, permissions = _authorization_services(db_session)
    org_ids = _create_org_tree(service)
    user_id, active_org_id = _grant_view(service, DataScopeType.ORG)

    scope = permissions.work_order_scope(user_id, "workorder:view", active_org_id)

    assert scope.org_ids == {org_ids["DEPT"]}
    assert org_ids["TEAM"] not in scope.org_ids
    assert not scope.all_data


def test_org_and_child_scope_includes_descendants_but_not_siblings(
    db_session: Session,
) -> None:
    service, permissions = _authorization_services(db_session)
    org_ids = _create_org_tree(service)
    user_id, active_org_id = _grant_view(service, DataScopeType.ORG_AND_CHILD)

    scope = permissions.work_order_scope(user_id, "workorder:view", active_org_id)

    assert scope.org_ids == {org_ids["DEPT"], org_ids["TEAM"]}
    assert org_ids["ROOT"] not in scope.org_ids
    assert org_ids["SIBLING"] not in scope.org_ids


def test_self_scope_contains_only_the_current_user(db_session: Session) -> None:
    service, permissions = _authorization_services(db_session)
    _create_org_tree(service)
    user_id, active_org_id = _grant_view(service, DataScopeType.SELF)

    scope = permissions.work_order_scope(user_id, "workorder:view", active_org_id)

    assert scope.self_user_id == user_id
    assert scope.org_ids == set()
    assert not scope.all_data


def test_custom_scope_resolves_configured_organization_ids(db_session: Session) -> None:
    service, permissions = _authorization_services(db_session)
    org_ids = _create_org_tree(service)
    user_id, active_org_id = _grant_view(
        service,
        DataScopeType.CUSTOM,
        custom_org_codes=("TEAM", "SIBLING"),
    )

    scope = permissions.work_order_scope(user_id, "workorder:view", active_org_id)

    assert scope.org_ids == {org_ids["TEAM"], org_ids["SIBLING"]}


def test_visible_work_order_does_not_imply_dispatch_permission(
    db_session: Session,
) -> None:
    service, permissions = _authorization_services(db_session)
    _create_org_tree(service)
    user_id, active_org_id = _grant_view(service, DataScopeType.ORG)
    service.create_permission("workorder:dispatch", "派单", "WORKORDER")

    view_scope = permissions.work_order_scope(
        user_id,
        "workorder:view",
        active_org_id,
    )

    assert not view_scope.is_empty
    assert not permissions.has_permission(
        user_id,
        "workorder:dispatch",
        active_org_id,
    )
    assert permissions.work_order_scope(
        user_id,
        "workorder:dispatch",
        active_org_id,
    ).is_empty
