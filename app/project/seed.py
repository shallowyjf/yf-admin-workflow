"""Idempotent city lifeline system and engineering-project demo seed."""

from dataclasses import dataclass
from datetime import date, timedelta

from app.core.config import get_settings
from app.db.session import Database
from app.iam.repository import IAMRepository
from app.iam.seed import CITY_TENANTS
from app.iam.service import IAMService

from .models import (
    Application,
    Project,
    ProjectMember,
    ProjectMilestone,
    ProjectOrganization,
    TenantApplication,
    UserApplicationAccess,
)
from .repository import ProjectRepository

APPLICATIONS = (
    ("WATER_SUPPLY", "供水 DMA 漏损管理系统", "WATER_SUPPLY"),
    ("WATER_HYDRAULIC", "供水水力模型管理系统", "WATER_SUPPLY"),
    ("DRAINAGE", "排水防涝管理系统", "DRAINAGE"),
    ("GAS", "燃气安全管理系统", "GAS"),
    ("HEATING", "供热管网管理系统", "HEATING"),
    ("ROAD", "道路桥梁管理系统", "ROAD"),
)

PROJECTS = (
    (
        "WS_NETWORK_RENEWAL",
        "WATER_SUPPLY",
        "供水管网更新改造工程",
        date(2026, 1, 10),
        date(2026, 12, 31),
    ),
    (
        "WS_HYDRAULIC_MODEL",
        "WATER_HYDRAULIC",
        "供水水力模型建设工程",
        date(2026, 2, 15),
        date(2027, 2, 28),
    ),
    (
        "DR_FLOOD_CONTROL",
        "DRAINAGE",
        "排水防涝能力提升工程",
        date(2026, 2, 1),
        date(2027, 3, 31),
    ),
    (
        "GAS_SAFETY_UPGRADE",
        "GAS",
        "燃气管网安全改造工程",
        date(2026, 3, 1),
        date(2027, 6, 30),
    ),
    (
        "HEAT_PIPE_RENOVATION",
        "HEATING",
        "供热老旧管网改造工程",
        date(2026, 4, 1),
        date(2027, 8, 31),
    ),
    (
        "ROAD_BRIDGE_MONITORING",
        "ROAD",
        "道路桥梁安全监测建设工程",
        date(2026, 5, 1),
        date(2027, 12, 31),
    ),
)

PROJECT_PARTIES = {
    "WATER_SUPPLY": (
        ("OWNER_WATER", "OWNER", True),
        ("GROUP", "OWNER", False),
        ("REGULATOR", "REGULATOR", False),
        ("SUPERVISOR", "SUPERVISOR", False),
        ("CONTRACTOR", "CONTRACTOR", False),
        ("PLATFORM", "SOFTWARE_VENDOR", False),
    ),
    "WATER_HYDRAULIC": (
        ("OWNER_WATER", "OWNER", True),
        ("GROUP", "OWNER", False),
        ("REGULATOR", "REGULATOR", False),
        ("SUPERVISOR", "SUPERVISOR", False),
        ("CONTRACTOR", "CONTRACTOR", False),
        ("PLATFORM", "SOFTWARE_VENDOR", False),
    ),
    "DRAINAGE": (
        ("OWNER_DRAINAGE", "OWNER", True),
        ("GROUP", "OWNER", False),
        ("REGULATOR", "REGULATOR", False),
        ("SUPERVISOR", "SUPERVISOR", False),
        ("CONTRACTOR", "CONTRACTOR", False),
        ("PLATFORM", "SOFTWARE_VENDOR", False),
    ),
    "GAS": (
        ("OWNER_GAS", "OWNER", True),
        ("GROUP", "OWNER", False),
        ("REGULATOR", "REGULATOR", False),
        ("SUPERVISOR", "SUPERVISOR", False),
        ("CONTRACTOR", "CONTRACTOR", False),
        ("PLATFORM", "SOFTWARE_VENDOR", False),
    ),
    "HEATING": (
        ("OWNER_HEATING", "OWNER", True),
        ("GROUP", "OWNER", False),
        ("REGULATOR", "REGULATOR", False),
        ("SUPERVISOR", "SUPERVISOR", False),
        ("CONTRACTOR", "CONTRACTOR", False),
        ("PLATFORM", "SOFTWARE_VENDOR", False),
    ),
    "ROAD": (
        ("OWNER_ROAD", "OWNER", True),
        ("GROUP", "OWNER", False),
        ("REGULATOR", "REGULATOR", False),
        ("SUPERVISOR", "SUPERVISOR", False),
        ("CONTRACTOR", "CONTRACTOR", False),
        ("PLATFORM", "SOFTWARE_VENDOR", False),
    ),
}

COMMON_MEMBERS = (
    ("admin", "GROUP", "SYSTEM_ADMIN"),
    ("owner_leader", "GROUP", "OWNER_LEADER"),
    ("wangwu", "DISPATCH_CENTER", "DISPATCHER"),
    ("regulator", "REGULATOR", "REVIEWER"),
    ("zhangsan", "PIPE_OPERATION", "WORKORDER_MANAGER"),
    ("platform_ops", "PLATFORM", "PLATFORM_OPERATOR"),
)

PROJECT_STAKEHOLDERS = {
    "WS_NETWORK_RENEWAL": (
        ("owner_pm", "OWNER_WATER", "OWNER_PROJECT_MANAGER"),
        ("supervisor_engineer", "WATER_SUPERVISION", "SUPERVISOR_ENGINEER"),
        ("software_delivery", "PLATFORM_DELIVERY", "SOFTWARE_DELIVERY"),
    ),
    "WS_HYDRAULIC_MODEL": (
        ("supervisor_engineer", "WATER_SUPERVISION", "SUPERVISOR_ENGINEER"),
        ("software_delivery", "PLATFORM_DELIVERY", "SOFTWARE_DELIVERY"),
    ),
    "DR_FLOOD_CONTROL": (
        ("software_delivery", "PLATFORM_DELIVERY", "SOFTWARE_DELIVERY"),
    ),
    "GAS_SAFETY_UPGRADE": (
        ("software_delivery", "PLATFORM_DELIVERY", "SOFTWARE_DELIVERY"),
    ),
    "HEAT_PIPE_RENOVATION": (
        ("software_delivery", "PLATFORM_DELIVERY", "SOFTWARE_DELIVERY"),
    ),
    "ROAD_BRIDGE_MONITORING": (
        ("software_delivery", "PLATFORM_DELIVERY", "SOFTWARE_DELIVERY"),
    ),
}

USER_APPLICATIONS = {
    "admin": tuple(code for code, _, _ in APPLICATIONS),
    "owner_leader": tuple(code for code, _, _ in APPLICATIONS),
    "wangwu": tuple(code for code, _, _ in APPLICATIONS),
    "regulator": tuple(code for code, _, _ in APPLICATIONS),
    "zhangsan": tuple(code for code, _, _ in APPLICATIONS),
    "platform_ops": tuple(code for code, _, _ in APPLICATIONS),
    "lisi": ("WATER_SUPPLY", "DRAINAGE", "HEATING"),
    "zhaoliu": ("WATER_SUPPLY", "GAS", "ROAD"),
    "water_drainage_leader": ("WATER_SUPPLY", "WATER_HYDRAULIC", "DRAINAGE"),
    "dma_specialist": ("WATER_SUPPLY",),
    "hydraulic_specialist": ("WATER_HYDRAULIC",),
    "owner_pm": ("WATER_SUPPLY",),
    "supervisor_engineer": ("WATER_SUPPLY", "WATER_HYDRAULIC"),
    "software_delivery": tuple(code for code, _, _ in APPLICATIONS),
}

PROJECT_WORKERS = {
    "WS_NETWORK_RENEWAL": ("lisi", "zhaoliu"),
    "WS_HYDRAULIC_MODEL": (),
    "DR_FLOOD_CONTROL": ("lisi",),
    "GAS_SAFETY_UPGRADE": ("zhaoliu",),
    "HEAT_PIPE_RENOVATION": ("lisi",),
    "ROAD_BRIDGE_MONITORING": ("zhaoliu",),
}

MILESTONES = (
    ("DESIGN", "方案设计与审批", 20, 100),
    ("CONSTRUCTION", "现场施工建设", 50, 75),
    ("INTEGRATION", "设备接入与联调", 20, 40),
    ("ACCEPTANCE", "项目验收与移交", 10, 0),
)
PROJECT_ACTUAL_PROGRESS = {
    "WS_NETWORK_RENEWAL": (100, 72, 35, 0),
    "WS_HYDRAULIC_MODEL": (100, 63, 50, 0),
    "DR_FLOOD_CONTROL": (100, 58, 20, 0),
    "GAS_SAFETY_UPGRADE": (100, 86, 65, 10),
    "HEAT_PIPE_RENOVATION": (100, 45, 15, 0),
    "ROAD_BRIDGE_MONITORING": (100, 68, 42, 0),
}


@dataclass(frozen=True)
class ProjectSeedSummary:
    applications: int = len(APPLICATIONS)
    projects: int = len(PROJECTS)
    project_organizations: int = sum(
        len(PROJECT_PARTIES[app_code]) for _, app_code, *_ in PROJECTS
    )
    project_members: int = len(PROJECTS) * len(COMMON_MEMBERS) + sum(
        len(workers) for workers in PROJECT_WORKERS.values()
    ) + sum(len(items) for items in PROJECT_STAKEHOLDERS.values())
    user_application_accesses: int = sum(
        len(application_codes)
        for application_codes in USER_APPLICATIONS.values()
    )
    milestones: int = len(PROJECTS) * len(MILESTONES)


def seed_projects(
    repository: ProjectRepository,
    iam_service: IAMService,
) -> ProjectSeedSummary:
    application_by_code: dict[str, Application] = {}
    subscription_by_code: dict[str, TenantApplication] = {}
    for code, name, domain_type in APPLICATIONS:
        application = repository.get_application(code)
        if application is None:
            application = Application(
                application_code=code,
                application_name=name,
                domain_type=domain_type,
            )
            repository.add(application)
            repository.commit()
            repository.refresh(application)
        application_by_code[code] = application
        subscription = repository.get_subscription(application.id)
        if subscription is None:
            subscription = TenantApplication(
                tenant_id=repository.tenant_id,
                application_id=application.id,
            )
            repository.add(subscription)
            repository.commit()
            repository.refresh(subscription)
        subscription_by_code[code] = subscription

    for username, application_codes in USER_APPLICATIONS.items():
        user = iam_service.get_user(username)
        if user is None:
            raise RuntimeError(f"IAM seed missing system user: {username}")
        for application_code in application_codes:
            subscription = subscription_by_code[application_code]
            if repository.get_user_application_access(subscription.id, user.id) is None:
                repository.add(
                    UserApplicationAccess(
                        tenant_application_id=subscription.id,
                        user_id=user.id,
                    )
                )
        repository.commit()

    for project_code, app_code, name, start_date, end_date in PROJECTS:
        project = repository.get_project(project_code)
        if project is None:
            project = Project(
                tenant_id=repository.tenant_id,
                application_id=application_by_code[app_code].id,
                project_code=project_code,
                project_name=name,
                start_date=start_date,
                end_date=end_date,
            )
            repository.add(project)
            repository.commit()
            repository.refresh(project)

        for org_code, party_type, is_lead in PROJECT_PARTIES[app_code]:
            organization = iam_service.get_organization(org_code)
            if organization is None:
                raise RuntimeError(f"IAM seed missing organization: {org_code}")
            if (
                repository.get_project_organization(
                    project.id, organization.id, party_type
                )
                is None
            ):
                repository.add(
                    ProjectOrganization(
                        project_id=project.id,
                        org_id=organization.id,
                        party_type=party_type,
                        is_lead=is_lead,
                    )
                )

        members = list(COMMON_MEMBERS) + list(PROJECT_STAKEHOLDERS[project_code]) + [
            (username, "PIPE_OPERATION", "REPAIRER")
            for username in PROJECT_WORKERS[project_code]
        ]
        for username, org_code, role_code in members:
            membership = iam_service.get_membership(username, org_code)
            role = iam_service.get_role(role_code)
            if membership is None or role is None:
                raise RuntimeError(
                    f"IAM seed missing project member binding: "
                    f"{username}/{org_code}/{role_code}"
                )
            if repository.get_project_member(project.id, membership.id, role.id) is None:
                repository.add(
                    ProjectMember(
                        project_id=project.id,
                        user_org_id=membership.id,
                        role_id=role.id,
                    )
                )
        duration_days = max((end_date - start_date).days, 1)
        actual_values = PROJECT_ACTUAL_PROGRESS[project_code]
        for index, ((code, milestone_name, weight, planned), actual) in enumerate(
            zip(MILESTONES, actual_values, strict=True), start=1
        ):
            if not any(item.milestone_code == code for item in project.milestones):
                if actual >= 100:
                    milestone_status = "COMPLETED"
                elif planned == 0:
                    milestone_status = "NOT_STARTED"
                elif actual + 10 < planned:
                    milestone_status = "DELAYED"
                else:
                    milestone_status = "IN_PROGRESS"
                repository.add(
                    ProjectMilestone(
                        project_id=project.id,
                        milestone_code=code,
                        milestone_name=milestone_name,
                        weight=weight,
                        planned_percent=planned,
                        actual_percent=actual,
                        status=milestone_status,
                        due_date=start_date
                        + timedelta(days=duration_days * index // len(MILESTONES)),
                    )
                )
        repository.commit()

    return ProjectSeedSummary()


def main() -> None:
    database = Database(get_settings().database_url)
    try:
        with database.session_factory() as session:
            summaries = []
            for tenant_code, _, _ in CITY_TENANTS:
                tenant = IAMRepository(session).get_tenant_by_code(tenant_code)
                if tenant is None:
                    raise RuntimeError(
                        f"IAM city tenant missing: {tenant_code}; run app.iam.seed first"
                    )
                iam_service = IAMService(IAMRepository(session, tenant.id))
                summaries.append(
                    seed_projects(ProjectRepository(session, tenant.id), iam_service)
                )
            summary = summaries[0]
        print(
            "City lifeline seed ready: "
            f"{len(summaries)} cities, {summary.applications} shared system definitions, "
            f"{sum(item.projects for item in summaries)} tenant projects, "
            f"{sum(item.project_organizations for item in summaries)} party links, "
            f"{sum(item.project_members for item in summaries)} member-role links, "
            f"{sum(item.user_application_accesses for item in summaries)} "
            f"user-system grants, {sum(item.milestones for item in summaries)} milestones"
        )
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
