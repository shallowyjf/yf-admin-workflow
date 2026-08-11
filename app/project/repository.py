"""Tenant-scoped read/write repository for lifeline project structures."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.iam.models import Role, RolePermission, UserOrganization

from .models import (
    Application,
    Project,
    ProjectMember,
    ProjectOrganization,
    TenantApplication,
)


class ProjectRepository:
    def __init__(self, session: Session, tenant_id: int) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def add(self, entity):
        self.session.add(entity)
        return entity

    def commit(self) -> None:
        self.session.commit()

    def refresh(self, entity) -> None:
        self.session.refresh(entity)

    def get_application(self, application_code: str) -> Application | None:
        return self.session.scalar(
            select(Application).where(Application.application_code == application_code)
        )

    def get_subscription(self, application_id: int) -> TenantApplication | None:
        return self.session.scalar(
            select(TenantApplication).where(
                TenantApplication.tenant_id == self.tenant_id,
                TenantApplication.application_id == application_id,
            )
        )

    def get_project(self, project_code: str) -> Project | None:
        return self.session.scalar(
            select(Project).where(
                Project.tenant_id == self.tenant_id,
                Project.project_code == project_code,
            )
        )

    def get_project_organization(
        self, project_id: int, org_id: int, party_type: str
    ) -> ProjectOrganization | None:
        return self.session.scalar(
            select(ProjectOrganization).where(
                ProjectOrganization.project_id == project_id,
                ProjectOrganization.org_id == org_id,
                ProjectOrganization.party_type == party_type,
            )
        )

    def get_project_member(
        self, project_id: int, user_org_id: int, role_id: int
    ) -> ProjectMember | None:
        return self.session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_org_id == user_org_id,
                ProjectMember.role_id == role_id,
            )
        )

    def list_applications(self) -> list[Application]:
        return list(
            self.session.scalars(
                select(Application)
                .join(TenantApplication)
                .where(
                    TenantApplication.tenant_id == self.tenant_id,
                    TenantApplication.is_active.is_(True),
                    Application.is_active.is_(True),
                )
                .order_by(Application.id)
            )
        )

    def list_projects(self) -> list[Project]:
        return list(
            self.session.scalars(
                select(Project)
                .where(Project.tenant_id == self.tenant_id)
                .options(
                    selectinload(Project.application),
                    selectinload(Project.organization_links).selectinload(
                        ProjectOrganization.organization
                    ),
                    selectinload(Project.members)
                    .selectinload(ProjectMember.membership)
                    .selectinload(UserOrganization.user),
                    selectinload(Project.members)
                    .selectinload(ProjectMember.membership)
                    .selectinload(UserOrganization.organization),
                    selectinload(Project.members).selectinload(ProjectMember.role),
                )
                .order_by(Project.application_id, Project.id)
            )
        )

    def list_roles(self) -> list[Role]:
        return list(
            self.session.scalars(
                select(Role)
                .where(Role.tenant_id == self.tenant_id, Role.is_active.is_(True))
                .options(
                    selectinload(Role.permission_links).selectinload(
                        RolePermission.permission
                    ),
                    selectinload(Role.data_scopes),
                )
                .order_by(Role.id)
            )
        )
