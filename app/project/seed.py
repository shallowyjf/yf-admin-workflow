"""Idempotent city lifeline system and engineering-project demo seed."""

from dataclasses import dataclass
from datetime import date

from app.core.config import get_settings
from app.db.session import Database
from app.iam.repository import IAMRepository
from app.iam.service import IAMService

from .models import (
    Application,
    Project,
    ProjectMember,
    ProjectOrganization,
    TenantApplication,
)
from .repository import ProjectRepository

APPLICATIONS = (
    ("WATER_SUPPLY", "供水生命线系统", "WATER_SUPPLY"),
    ("DRAINAGE", "排水生命线系统", "DRAINAGE"),
    ("GAS", "燃气生命线系统", "GAS"),
    ("HEATING", "供热生命线系统", "HEATING"),
    ("ROAD", "道路生命线系统", "ROAD"),
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

PROJECT_PARTIES = (
    ("GROUP", "OWNER", True),
    ("REGULATOR", "REGULATOR", False),
    ("CONTRACTOR", "CONTRACTOR", False),
    ("PLATFORM", "PLATFORM", False),
)

COMMON_MEMBERS = (
    ("owner_leader", "GROUP", "OWNER_LEADER"),
    ("wangwu", "DISPATCH_CENTER", "DISPATCHER"),
    ("regulator", "REGULATOR", "REVIEWER"),
    ("zhangsan", "PIPE_OPERATION", "WORKORDER_MANAGER"),
    ("platform_ops", "PLATFORM", "PLATFORM_OPERATOR"),
)

PROJECT_WORKERS = {
    "WS_NETWORK_RENEWAL": ("lisi", "zhaoliu"),
    "DR_FLOOD_CONTROL": ("lisi",),
    "GAS_SAFETY_UPGRADE": ("zhaoliu",),
    "HEAT_PIPE_RENOVATION": ("lisi",),
    "ROAD_BRIDGE_MONITORING": ("zhaoliu",),
}


@dataclass(frozen=True)
class ProjectSeedSummary:
    applications: int = len(APPLICATIONS)
    projects: int = len(PROJECTS)
    project_organizations: int = len(PROJECTS) * len(PROJECT_PARTIES)
    project_members: int = len(PROJECTS) * len(COMMON_MEMBERS) + sum(
        len(workers) for workers in PROJECT_WORKERS.values()
    )


def seed_projects(
    repository: ProjectRepository,
    iam_service: IAMService,
) -> ProjectSeedSummary:
    application_by_code: dict[str, Application] = {}
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
        if repository.get_subscription(application.id) is None:
            repository.add(
                TenantApplication(
                    tenant_id=repository.tenant_id,
                    application_id=application.id,
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

        for org_code, party_type, is_lead in PROJECT_PARTIES:
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

        members = list(COMMON_MEMBERS) + [
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
        repository.commit()

    return ProjectSeedSummary()


def main() -> None:
    database = Database(get_settings().database_url)
    try:
        with database.session_factory() as session:
            tenant_id = IAMRepository(session).require_tenant_id()
            iam_service = IAMService(IAMRepository(session, tenant_id))
            summary = seed_projects(
                ProjectRepository(session, tenant_id), iam_service
            )
        print(
            "City lifeline seed ready: "
            f"{summary.applications} systems, {summary.projects} projects, "
            f"{summary.project_organizations} party links, "
            f"{summary.project_members} member-role links"
        )
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
