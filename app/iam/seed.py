"""Idempotent IAM and authorization demo seed data."""

from dataclasses import dataclass

from app.auth.security import PasswordHasher
from app.core.config import get_settings
from app.db.session import Database

from .authorization import DataScopeType
from .permission_catalog import PERMISSIONS
from .repository import IAMRepository
from .service import IAMService

ORGANIZATIONS = (
    ("GROUP", "XX水务集团", "GROUP", None, 10),
    ("DISPATCH_CENTER", "调度中心", "DEPARTMENT", "GROUP", 20),
    ("PIPE_OPERATION", "管网运行部", "DEPARTMENT", "GROUP", 30),
    ("INSPECTION_TEAM_1", "巡检一组", "TEAM", "PIPE_OPERATION", 40),
    ("INSPECTION_TEAM_2", "巡检二组", "TEAM", "PIPE_OPERATION", 50),
)
USERS = (
    ("admin", "系统管理员"),
    ("wangwu", "调度管理员"),
    ("zhangsan", "管网运行部负责人"),
    ("lisi", "抢修人员"),
    ("zhaoliu", "抢修人员"),
)
ROLES = (
    ("SYSTEM_ADMIN", "系统管理员"),
    ("DISPATCHER", "调度员"),
    ("WORKORDER_MANAGER", "工单管理员"),
    ("REPAIRER", "抢修人员"),
    ("REVIEWER", "复核人员"),
)
POSITIONS = (
    ("DEPT_MANAGER", "部门负责人"),
    ("DISPATCHER", "调度员"),
    ("REPAIRER", "抢修人员"),
)
DEMO_INITIAL_PASSWORD = "Demo@123456"
ROLE_POLICIES = {
    "SYSTEM_ADMIN": (
        tuple(code for code, _, _ in PERMISSIONS),
        DataScopeType.ALL,
    ),
    "DISPATCHER": (
        (
            "workorder:view",
            "workorder:create",
            "workorder:dispatch",
            "workorder:review",
            "workorder:close",
        ),
        DataScopeType.ORG_AND_CHILD,
    ),
    "WORKORDER_MANAGER": (
        (
            "workorder:view",
            "workorder:create",
            "workorder:dispatch",
            "workorder:transfer",
            "workorder:close",
        ),
        DataScopeType.ORG_AND_CHILD,
    ),
    "REPAIRER": (
        (
            "workorder:view",
            "workorder:claim",
            "workorder:handle",
            "workorder:transfer",
        ),
        DataScopeType.SELF,
    ),
    "REVIEWER": (
        ("workorder:view", "workorder:review", "workorder:close"),
        DataScopeType.ORG,
    ),
}


@dataclass(frozen=True)
class SeedSummary:
    organizations: int = 5
    users: int = 5
    roles: int = 5
    positions: int = 3
    permissions: int = 34
    role_permissions: int = 51
    data_scopes: int = 51


def seed_iam(service: IAMService) -> SeedSummary:
    password_hasher = PasswordHasher()
    for code, name, org_type, parent_code, sort_no in ORGANIZATIONS:
        if service.get_organization(code) is None:
            service.create_organization(code, name, org_type, parent_code, sort_no)

    for username, display_name in USERS:
        user = service.get_user(username)
        if user is None:
            service.create_user(
                username,
                display_name,
                password_hasher.hash(DEMO_INITIAL_PASSWORD),
            )
        elif user.password_hash == "!login-disabled-until-I04":
            service.set_password_hash(
                username,
                password_hasher.hash(DEMO_INITIAL_PASSWORD),
            )

    for code, name in ROLES:
        if service.get_role(code) is None:
            service.create_role(code, name, "SYSTEM" if code == "SYSTEM_ADMIN" else "BUSINESS")

    for code, name in POSITIONS:
        if service.get_position(code) is None:
            service.create_position(code, name)

    for code, name, resource_type in PERMISSIONS:
        if service.get_permission(code) is None:
            service.create_permission(code, name, resource_type)

    assignments = (
        ("admin", "GROUP", ("SYSTEM_ADMIN",), ()),
        ("wangwu", "DISPATCH_CENTER", ("DISPATCHER", "REVIEWER"), ("DISPATCHER",)),
        ("zhangsan", "PIPE_OPERATION", ("WORKORDER_MANAGER",), ("DEPT_MANAGER",)),
        ("lisi", "PIPE_OPERATION", ("REPAIRER",), ("REPAIRER",)),
        ("zhaoliu", "PIPE_OPERATION", ("REPAIRER",), ("REPAIRER",)),
    )
    for username, org_code, role_codes, position_codes in assignments:
        membership = service.get_membership(username, org_code)
        if membership is None:
            membership = service.add_user_to_organization(
                username,
                org_code,
                is_primary=True,
            )
        current_roles = {link.role.role_code for link in membership.role_links}
        for role_code in role_codes:
            if role_code not in current_roles:
                service.assign_role(username, org_code, role_code)
        membership = service.get_membership(username, org_code)
        assert membership is not None
        current_positions = {
            link.position.position_code for link in membership.position_links
        }
        for position_code in position_codes:
            if position_code not in current_positions:
                service.assign_position(username, org_code, position_code)

    if service.get_membership("wangwu", "PIPE_OPERATION") is None:
        service.add_user_to_organization("wangwu", "PIPE_OPERATION")

    for role_code, (permission_codes, scope_type) in ROLE_POLICIES.items():
        role = service.get_role(role_code)
        assert role is not None
        for permission_code in permission_codes:
            permission = service.get_permission(permission_code)
            assert permission is not None
            if service.repository.get_role_permission(role.id, permission.id) is None:
                service.grant_permission(role_code, permission_code)
            service.set_role_data_scope(role_code, permission_code, scope_type)

    return SeedSummary()


def main() -> None:
    database = Database(get_settings().database_url)
    try:
        with database.session_factory() as session:
            summary = seed_iam(IAMService(IAMRepository(session)))
        print(
            "IAM seed ready: "
            f"{summary.organizations} organizations, {summary.users} users, "
            f"{summary.roles} roles, {summary.positions} positions, "
            f"{summary.permissions} permissions"
        )
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
