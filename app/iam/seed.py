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
DEFAULT_TENANT_NAME = "江城市城市生命线租户"
CITY_TENANTS = (
    (DEFAULT_TENANT_CODE, DEFAULT_TENANT_NAME, "江城市"),
    ("CITY_HAIZHOU", "海州市城市生命线租户", "海州市"),
    ("CITY_YUNZHOU", "云州市城市生命线租户", "云州市"),
)
ORGANIZATIONS = (
    ("GROUP", "{city}城市生命线建设运营中心（总体甲方）", "OWNER", None, 10),
    ("DISPATCH_CENTER", "城市综合调度中心", "OWNER_DEPARTMENT", "GROUP", 20),
    ("OWNER_WATER", "供水业务管理部", "OWNER_DEPARTMENT", "GROUP", 21),
    ("OWNER_DRAINAGE", "排水业务管理部", "OWNER_DEPARTMENT", "GROUP", 22),
    ("OWNER_GAS", "燃气业务管理部", "OWNER_DEPARTMENT", "GROUP", 23),
    ("OWNER_HEATING", "供热业务管理部", "OWNER_DEPARTMENT", "GROUP", 24),
    ("OWNER_ROAD", "道路业务管理部", "OWNER_DEPARTMENT", "GROUP", 25),
    ("REGULATOR", "{city}住房和城乡建设局（监管方）", "REGULATOR", None, 30),
    (
        "REGULATOR_CENTER",
        "城市生命线监管中心",
        "REGULATOR_DEPARTMENT",
        "REGULATOR",
        40,
    ),
    ("SUPERVISOR", "{city}城市生命线工程监理公司", "SUPERVISOR", None, 41),
    (
        "WATER_SUPERVISION",
        "供水工程监理部",
        "SUPERVISOR_DEPARTMENT",
        "SUPERVISOR",
        42,
    ),
    (
        "MUNICIPAL_SUPERVISION",
        "市政工程监理部",
        "SUPERVISOR_DEPARTMENT",
        "SUPERVISOR",
        43,
    ),
    ("CONTRACTOR", "城市生命线工程联合体（施工方）", "CONTRACTOR", None, 50),
    ("PIPE_OPERATION", "供水施工项目部", "PROJECT_DEPARTMENT", "CONTRACTOR", 60),
    (
        "MUNICIPAL_CONSTRUCTION",
        "市政施工项目部",
        "PROJECT_DEPARTMENT",
        "CONTRACTOR",
        61,
    ),
    ("INSPECTION_TEAM_1", "现场施工一班", "TEAM", "PIPE_OPERATION", 70),
    ("INSPECTION_TEAM_2", "现场施工二班", "TEAM", "PIPE_OPERATION", 80),
    ("PLATFORM", "智慧城市软件供应商", "PLATFORM", None, 90),
    (
        "PLATFORM_DELIVERY",
        "生命线产品交付部",
        "PLATFORM_DEPARTMENT",
        "PLATFORM",
        100,
    ),
    (
        "PLATFORM_OPERATIONS",
        "生命线平台运维部",
        "PLATFORM_DEPARTMENT",
        "PLATFORM",
        101,
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
    ("water_drainage_leader", "供排水业务负责人"),
    ("water_manager", "供水 GIS 系统管理员"),
    ("drainage_manager", "排水 GIS 系统管理员"),
    ("gas_manager", "燃气 GIS 系统管理员"),
    ("heating_manager", "供热 GIS 系统管理员"),
    ("road_manager", "道路 GIS 系统管理员"),
    ("dma_specialist", "DMA 业务专员"),
    ("hydraulic_specialist", "水力模型业务专员"),
    ("owner_pm", "供水甲方项目经理"),
    ("supervisor_engineer", "供水监理工程师"),
    ("software_delivery", "软件交付工程师"),
)
ROLES = (
    ("SYSTEM_ADMIN", "系统管理员"),
    ("OWNER_LEADER", "甲方领导"),
    ("DISPATCHER", "甲方调度员"),
    ("WORKORDER_MANAGER", "施工项目经理"),
    ("REPAIRER", "施工处置人员"),
    ("REVIEWER", "监管复核人员"),
    ("PLATFORM_OPERATOR", "平台运维人员"),
    ("BUSINESS_LEADER", "业务方向负责人"),
    ("SYSTEM_SPECIALIST", "单系统业务专员"),
    ("OWNER_PROJECT_MANAGER", "业务甲方项目经理"),
    ("SUPERVISOR_ENGINEER", "工程监理工程师"),
    ("SOFTWARE_DELIVERY", "软件交付工程师"),
    ("DATA_MANAGER", "应用数据管理员"),
    ("DATA_VIEWER", "应用数据查看者"),
    ("DATA_STEWARD", "采集处理数据专员"),
    ("MODEL_ANALYST", "模型分析人员"),
)
POSITIONS = (
    ("TENANT_LEADER", "甲方负责人"),
    ("DEPT_MANAGER", "施工项目经理"),
    ("SUPERVISOR", "监管人员"),
    ("DISPATCHER", "项目调度员"),
    ("REPAIRER", "现场施工人员"),
    ("PLATFORM_ENGINEER", "平台运维工程师"),
    ("BUSINESS_DIRECTOR", "业务方向负责人"),
    ("SYSTEM_OWNER", "业务系统负责人"),
    ("OWNER_PROJECT_MANAGER", "甲方项目经理"),
    ("SUPERVISOR_ENGINEER", "监理工程师"),
    ("DELIVERY_ENGINEER", "软件交付工程师"),
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
            "project:authorization:explain",
            "workorder:view",
        ),
        DataScopeType.ALL,
    ),
    "DISPATCHER": (
        (
            "system:application:view",
            "project:view",
            "project:progress:view",
            "project:authorization:explain",
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
            "project:authorization:explain",
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
            "project:authorization:explain",
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
    "BUSINESS_LEADER": (
        (
            "system:org:view",
            "system:application:view",
            "project:view",
            "project:progress:view",
            "project:progress:view-all",
            "project:authorization:explain",
            "workorder:view",
        ),
        DataScopeType.ORG_AND_CHILD,
    ),
    "SYSTEM_SPECIALIST": (
        (
            "system:org:view",
            "system:application:view",
            "project:view",
            "project:progress:view",
            "project:progress:view-all",
            "workorder:view",
        ),
        DataScopeType.ORG,
    ),
    "OWNER_PROJECT_MANAGER": (
        (
            "system:org:view",
            "system:application:view",
            "project:view",
            "project:update",
            "project:progress:view",
            "project:authorization:explain",
            "workorder:view",
            "workorder:create",
            "workorder:dispatch",
            "workorder:comment",
            "workorder:urge",
            "workorder:review",
        ),
        DataScopeType.ORG_AND_CHILD,
    ),
    "SUPERVISOR_ENGINEER": (
        (
            "system:org:view",
            "system:application:view",
            "project:view",
            "project:progress:view",
            "project:authorization:explain",
            "workorder:view",
            "workorder:comment",
            "workorder:review",
        ),
        DataScopeType.ORG_AND_CHILD,
    ),
    "SOFTWARE_DELIVERY": (
        (
            "system:org:view",
            "system:application:view",
            "project:view",
            "project:progress:view",
            "workorder:view",
            "workorder:comment",
            "workorder:attachment",
        ),
        DataScopeType.ORG_AND_CHILD,
    ),
    "DATA_MANAGER": (
        (
            "data:space:view",
            "data:space:manage",
            "data:resource:view",
            "data:resource:manage",
            "data:resource:query",
            "data:authorization:explain",
            "gis:feature:view",
            "gis:feature:edit",
            "gis:spatial:query",
            "gis:coordinate:exact",
            "gis:field:sensitive:view",
            "gis:export",
        ),
        DataScopeType.ORG,
    ),
    "DATA_VIEWER": (
        (
            "data:space:view",
            "data:resource:view",
            "data:resource:query",
            "data:authorization:explain",
            "gis:feature:view",
            "gis:spatial:query",
        ),
        DataScopeType.ORG,
    ),
    "DATA_STEWARD": (
        (
            "data:space:view",
            "data:resource:view",
            "data:resource:query",
            "data:authorization:explain",
            "gis:feature:view",
            "gis:spatial:query",
        ),
        DataScopeType.ORG,
    ),
    "MODEL_ANALYST": (
        (
            "data:space:view",
            "data:resource:view",
            "data:resource:query",
            "data:authorization:explain",
        ),
        DataScopeType.ORG,
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


def seed_iam(
    service: IAMService,
    *,
    city_name: str = "江城市",
    tenant_name: str | None = None,
) -> SeedSummary:
    tenant = (
        service.repository.get_tenant(service.repository.tenant_id)
        if service.repository.tenant_id is not None
        else service.repository.get_tenant_by_code(DEFAULT_TENANT_CODE)
    )
    if tenant is None:
        from .models import Tenant

        tenant = Tenant(
            tenant_code=DEFAULT_TENANT_CODE,
            tenant_name=DEFAULT_TENANT_NAME,
        )
        service.repository.add(tenant)
        service.repository.commit()
        service.repository.refresh(tenant)
    desired_tenant_name = tenant_name
    if desired_tenant_name is None and tenant.tenant_code == DEFAULT_TENANT_CODE:
        desired_tenant_name = DEFAULT_TENANT_NAME
    if desired_tenant_name and tenant.tenant_name != desired_tenant_name:
        tenant.tenant_name = desired_tenant_name
        service.repository.commit()
        service.repository.refresh(tenant)
    if service.repository.tenant_id is None:
        service.repository.tenant_id = tenant.id
    password_hasher = PasswordHasher()
    for code, name, org_type, parent_code, sort_no in ORGANIZATIONS:
        if service.get_organization(code) is None:
            service.create_organization(
                code,
                name.format(city=city_name),
                org_type,
                parent_code,
                sort_no,
            )

    for username, display_name in USERS:
        user = service.get_user(username)
        if user is None:
            service.create_user(
                username,
                display_name,
                password_hasher.hash(DEMO_INITIAL_PASSWORD),
                login_name=service.default_login_name(username),
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
        (
            "water_drainage_leader",
            "OWNER_WATER",
            ("BUSINESS_LEADER",),
            ("BUSINESS_DIRECTOR",),
        ),
        (
            "water_manager",
            "OWNER_WATER",
            ("BUSINESS_LEADER",),
            ("BUSINESS_DIRECTOR",),
        ),
        (
            "drainage_manager",
            "OWNER_DRAINAGE",
            ("BUSINESS_LEADER",),
            ("BUSINESS_DIRECTOR",),
        ),
        (
            "gas_manager",
            "OWNER_GAS",
            ("BUSINESS_LEADER",),
            ("BUSINESS_DIRECTOR",),
        ),
        (
            "heating_manager",
            "OWNER_HEATING",
            ("BUSINESS_LEADER",),
            ("BUSINESS_DIRECTOR",),
        ),
        (
            "road_manager",
            "OWNER_ROAD",
            ("BUSINESS_LEADER",),
            ("BUSINESS_DIRECTOR",),
        ),
        (
            "water_drainage_leader",
            "OWNER_DRAINAGE",
            ("BUSINESS_LEADER",),
            ("BUSINESS_DIRECTOR",),
        ),
        (
            "dma_specialist",
            "OWNER_WATER",
            ("SYSTEM_SPECIALIST",),
            ("SYSTEM_OWNER",),
        ),
        (
            "hydraulic_specialist",
            "OWNER_WATER",
            ("SYSTEM_SPECIALIST",),
            ("SYSTEM_OWNER",),
        ),
        (
            "owner_pm",
            "OWNER_WATER",
            ("OWNER_PROJECT_MANAGER",),
            ("OWNER_PROJECT_MANAGER",),
        ),
        (
            "supervisor_engineer",
            "WATER_SUPERVISION",
            ("SUPERVISOR_ENGINEER",),
            ("SUPERVISOR_ENGINEER",),
        ),
        (
            "software_delivery",
            "PLATFORM_DELIVERY",
            ("SOFTWARE_DELIVERY",),
            ("DELIVERY_ENGINEER",),
        ),
    )
    for username, org_code, role_codes, position_codes in assignments:
        membership = service.get_membership(username, org_code)
        if membership is None:
            secondary_memberships = {
                ("admin", "PLATFORM"),
                ("water_drainage_leader", "OWNER_DRAINAGE"),
            }
            membership = service.add_user_to_organization(
                username,
                org_code,
                is_primary=(username, org_code) not in secondary_memberships,
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


def seed_city_tenants(session) -> tuple[SeedSummary, ...]:
    """Seed three city tenants with an identical, tenant-local IAM template."""
    from .models import Tenant

    summaries = []
    catalog = IAMRepository(session)
    for tenant_code, tenant_name, city_name in CITY_TENANTS:
        tenant = catalog.get_tenant_by_code(tenant_code)
        if tenant is None:
            tenant = Tenant(tenant_code=tenant_code, tenant_name=tenant_name)
            catalog.add(tenant)
            catalog.commit()
            catalog.refresh(tenant)
        summaries.append(
            seed_iam(
                IAMService(IAMRepository(session, tenant.id)),
                city_name=city_name,
                tenant_name=tenant_name,
            )
        )
    return tuple(summaries)


def main() -> None:
    database = Database(get_settings().database_url)
    try:
        with database.session_factory() as session:
            summaries = seed_city_tenants(session)
            summary = summaries[0]
        print(
            "IAM seed ready: "
            f"{len(summaries)} city tenants, "
            f"{sum(item.organizations for item in summaries)} organizations, "
            f"{sum(item.users for item in summaries)} users, "
            f"{summary.roles} roles/tenant, {summary.positions} positions/tenant, "
            f"{summary.permissions} permissions"
        )
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
