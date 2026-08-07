"""Idempotent I02 seed data."""

from dataclasses import dataclass

from app.core.config import get_settings
from app.db.session import Database

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


@dataclass(frozen=True)
class SeedSummary:
    organizations: int = 5
    users: int = 5
    roles: int = 5
    positions: int = 3


def seed_iam(service: IAMService) -> SeedSummary:
    for code, name, org_type, parent_code, sort_no in ORGANIZATIONS:
        if service.get_organization(code) is None:
            service.create_organization(code, name, org_type, parent_code, sort_no)

    for username, display_name in USERS:
        if service.get_user(username) is None:
            service.create_user(username, display_name, "!login-disabled-until-I04")

    for code, name in ROLES:
        if service.get_role(code) is None:
            service.create_role(code, name, "SYSTEM" if code == "SYSTEM_ADMIN" else "BUSINESS")

    for code, name in POSITIONS:
        if service.get_position(code) is None:
            service.create_position(code, name)

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

    return SeedSummary()


def main() -> None:
    database = Database(get_settings().database_url)
    try:
        with database.session_factory() as session:
            summary = seed_iam(IAMService(IAMRepository(session)))
        print(
            "IAM seed ready: "
            f"{summary.organizations} organizations, {summary.users} users, "
            f"{summary.roles} roles, {summary.positions} positions"
        )
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
