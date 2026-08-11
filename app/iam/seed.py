"""Idempotent IAM and authorization demo seed data."""

from dataclasses import dataclass

from app.auth.security import PasswordHasher
from app.core.config import get_settings
from app.db.session import Database

from .authorization import DataScopeType
from .permission_catalog import PERMISSIONS
from .repository import IAMRepository
from .service import IAMService

DEFAULT_TENANT_CODE = "DEMO"
DEFAULT_TENANT_NAME = "某市城市生命线演示租户"
ORGANIZATIONS = (
    ("GROUP", "某市城市生命线建设运营中心（甲方）", "OWNER", None, 10),
    ("DISPATCH_CENTER", "甲方项目调度中心", "OWNER_DEPARTMENT", "GROUP", 20),
    ("REGULATOR", "某市住房和城乡建设局（监管方）", "REGULATOR", None, 30),
    (
        "REGULATOR_CENTER",
        "城市生命线监管中心",
        "REGULATOR_DEPARTMENT",
        "REGULATOR",
        40,
    ),
    ("CONTRACTOR", "城市生命线工程联合体（施工方）", "CONTRACTOR", None, 50),
    ("PIPE_OPERATION", "联合施工项目部", "PROJECT_DEPARTMENT", "CONTRACTOR", 60),
    ("INSPECTION_TEAM_1", "现场施工一班", "TEAM", "PIPE_OPERATION", 70),
    ("INSPECTION_TEAM_2", "现场施工二班", "TEAM", "PIPE_OPERATION", 80),
    ("PLATFORM", "智慧城市软件平台公司（平台方）", "PLATFORM", None, 90),
    (
        "PLATFORM_DELIVERY",
        "生命线平台交付运维部",
        "PLATFORM_DEPARTMENT",
        "PLATFORM",
        100,
    ),
)
USERS = (
    ("admin", "系统管理员"),
    ("owner_leader", "甲方领导"),
    ("wangwu", "甲方调度管理员"),
    ("regulator", "监管复核人员"),
    ("zhangsan", "施工项目经理"),
    ("lisi", "现场施工人员"),
    ("zhaoliu", "现场施工人员"),
    ("platform_ops", "平台运维人员"),
)
ROLES = (
    ("SYSTEM_ADMIN", "系统管理员"),
    ("OWNER_LEADER", "甲方领导"),
    ("DISPATCHER", "甲方调度员"),
    ("WORKORDER_MANAGER", "施工项目经理"),
    ("REPAIRER", "施工处置人员"),
    ("REVIEWER", "监管复核人员"),
    ("PLATFORM_OPERATOR", "平台运维人员"),
)
POSITIONS = (
    ("TENANT_LEADER", "甲方负责人"),
    ("DEPT_MANAGER", "施工项目经理"),
    ("SUPERVISOR", "监管人员"),
    ("DISPATCHER", "项目调度员"),
    ("REPAIRER", "现场施工人员"),
    ("PLATFORM_ENGINEER", "平台运维工程师"),
)
DEMO_INITIAL_PASSWORD = "Demo@123456"
ROLE_POLICIES = {
    "SYSTEM_ADMIN": (
        tuple(code for code, _, _ in PERMISSIONS),
        DataScopeType.ALL,
    ),
    "OWNER_LEADER": (
        (
            "system:application:view",
            "project:view",
            "project:progress:view",
            "project:progress:view-all",
            "workorder:view",
        ),
        DataScopeType.ALL,
    ),
    "DISPATCHER": (
        (
            "system:application:view",
            "project:view",
            "project:progress:view",
            "workorder:view",
            "workorder:create",
            "workorder:dispatch",
            "workorder:comment",
            "workorder:urge",
            "workorder:attachment",
            "workorder:sla:evaluate",
            "workorder:review",
            "workorder:close",
        ),
        DataScopeType.ORG_AND_CHILD,
    ),
    "WORKORDER_MANAGER": (
        (
            "system:application:view",
            "project:view",
            "project:update",
            "project:organization:manage",
            "project:member:manage",
            "project:progress:view",
            "workorder:view",
            "workorder:create",
            "workorder:dispatch",
            "workorder:transfer",
            "workorder:comment",
            "workorder:urge",
            "workorder:attachment",
            "workorder:sla:evaluate",
            "workorder:close",
        ),
        DataScopeType.ORG_AND_CHILD,
    ),
    "REPAIRER": (
        (
            "system:application:view",
            "project:view",
            "workorder:view",
            "workorder:claim",
            "workorder:handle",
            "workorder:transfer",
            "workorder:comment",
            "workorder:attachment",
        ),
        DataScopeType.SELF,
    ),
    "REVIEWER": (
        (
            "system:application:view",
            "project:view",
            "project:progress:view",
            "workorder:view",
            "workorder:comment",
            "workorder:urge",
            "workorder:attachment",
            "workorder:sla:evaluate",
            "workorder:review",
            "workorder:close",
        ),
        DataScopeType.ORG,
    ),
    "PLATFORM_OPERATOR": (
        (
            "system:application:view",
            "project:view",
            "project:progress:view",
            "workorder:view",
            "workorder:comment",
            "workorder:attachment",
            "system:audit:view",
        ),
        DataScopeType.ALL,
    ),
}


@dataclass(frozen=True)
class SeedSummary:
    tenants: int = 1
    organizations: int = len(ORGANIZATIONS)
    users: int = len(USERS)
    roles: int = len(ROLES)
    positions: int = len(POSITIONS)
    permissions: int = len(PERMISSIONS)
    role_permissions: int = sum(
        len(permission_codes) for permission_codes, _ in ROLE_POLICIES.values()
    )
    data_scopes: int = sum(
        len(permission_codes) for permission_codes, _ in ROLE_POLICIES.values()
    )


def seed_iam(service: IAMService) -> SeedSummary:
    tenant = service.repository.get_tenant_by_code(DEFAULT_TENANT_CODE)
    if tenant is None:
        from .models import Tenant

        tenant = Tenant(
            tenant_code=DEFAULT_TENANT_CODE,
            tenant_name=DEFAULT_TENANT_NAME,
        )
        service.repository.add(tenant)
        service.repository.commit()
        service.repository.refresh(tenant)
    if service.repository.tenant_id is None:
        service.repository.tenant_id = tenant.id
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
        ("admin", "PLATFORM", (), ()),
        ("owner_leader", "GROUP", ("OWNER_LEADER",), ("TENANT_LEADER",)),
        ("wangwu", "DISPATCH_CENTER", ("DISPATCHER", "REVIEWER"), ("DISPATCHER",)),
        ("regulator", "REGULATOR", ("REVIEWER",), ("SUPERVISOR",)),
        ("zhangsan", "PIPE_OPERATION", ("WORKORDER_MANAGER",), ("DEPT_MANAGER",)),
        ("lisi", "PIPE_OPERATION", ("REPAIRER",), ("REPAIRER",)),
        ("zhaoliu", "PIPE_OPERATION", ("REPAIRER",), ("REPAIRER",)),
        (
            "platform_ops",
            "PLATFORM",
            ("PLATFORM_OPERATOR",),
            ("PLATFORM_ENGINEER",),
        ),
    )
    for username, org_code, role_codes, position_codes in assignments:
        membership = service.get_membership(username, org_code)
        if membership is None:
            membership = service.add_user_to_organization(
                username,
                org_code,
                is_primary=not (username == "admin" and org_code == "PLATFORM"),
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
            f"{summary.tenants} tenant, {summary.organizations} organizations, "
            f"{summary.users} users, "
            f"{summary.roles} roles, {summary.positions} positions, "
            f"{summary.permissions} permissions"
        )
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
