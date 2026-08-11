"""Tenant-scoped read/write repository for lifeline project structures."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.iam.models import (
    IAMAuditLog,
    Organization,
    Permission,
    Role,
    RolePermission,
    User,
    UserOrganization,
)

from .models import (
    Application,
    Project,
    ProjectMember,
    ProjectMilestone,
    ProjectOrganization,
    TenantApplication,
    UserApplicationAccess,
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

    def flush(self) -> None:
        self.session.flush()

    def refresh(self, entity) -> None:
        self.session.refresh(entity)

    def expire_all(self) -> None:
        self.session.expire_all()

    def delete(self, entity) -> None:
        self.session.delete(entity)

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

    def get_subscription_by_id(self, subscription_id: int) -> TenantApplication | None:
        return self.session.scalar(
            select(TenantApplication).where(
                TenantApplication.id == subscription_id,
                TenantApplication.tenant_id == self.tenant_id,
            )
        )

    def get_user_application_access(
        self, tenant_application_id: int, user_id: int
    ) -> UserApplicationAccess | None:
        return self.session.scalar(
            select(UserApplicationAccess).where(
                UserApplicationAccess.tenant_application_id
                == tenant_application_id,
                UserApplicationAccess.user_id == user_id,
            )
        )

    def get_project(self, project_code: str) -> Project | None:
        return self.session.scalar(
            select(Project).where(
                Project.tenant_id == self.tenant_id,
                Project.project_code == project_code,
            )
        )

    def get_project_by_id(self, project_id: int) -> Project | None:
        return self.session.scalar(
            select(Project)
            .where(Project.id == project_id, Project.tenant_id == self.tenant_id)
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
                selectinload(Project.milestones),
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

    def get_milestone(
        self, project_id: int, milestone_id: int
    ) -> ProjectMilestone | None:
        return self.session.scalar(
            select(ProjectMilestone).where(
                ProjectMilestone.id == milestone_id,
                ProjectMilestone.project_id == project_id,
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

    def list_user_applications(self, user_id: int) -> list[Application]:
        return list(
            self.session.scalars(
                select(Application)
                .join(TenantApplication)
                .join(UserApplicationAccess)
                .join(User, User.id == UserApplicationAccess.user_id)
                .where(
                    TenantApplication.tenant_id == self.tenant_id,
                    TenantApplication.is_active.is_(True),
                    UserApplicationAccess.user_id == user_id,
                    UserApplicationAccess.is_active.is_(True),
                    User.tenant_id == self.tenant_id,
                    User.is_active.is_(True),
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
                    selectinload(Project.milestones),
                )
                .order_by(Project.application_id, Project.id)
            )
        )

    def list_accessible_projects(
        self,
        user_id: int,
        *,
        include_all: bool = False,
    ) -> list[Project]:
        accessible_application_ids = {
            application.id for application in self.list_user_applications(user_id)
        }
        if not accessible_application_ids:
            return []
        projects = self.list_projects()
        projects = [
            project
            for project in projects
            if project.application_id in accessible_application_ids
        ]
        if include_all:
            return projects
        return [
            project
            for project in projects
            if any(
                member.is_active
                and member.role.is_active
                and member.membership.is_active
                and member.membership.user.is_active
                and member.membership.organization.is_active
                and member.membership.user_id == user_id
                and self.role_has_permission(member.role_id, "project:view")
                for member in project.members
            )
        ]

    def list_project_members_for_user(
        self, project_id: int, user_id: int
    ) -> list[ProjectMember]:
        return list(
            self.session.scalars(
                select(ProjectMember)
                .join(UserOrganization)
                .join(User, User.id == UserOrganization.user_id)
                .join(Organization, Organization.id == UserOrganization.org_id)
                .join(Role, Role.id == ProjectMember.role_id)
                .where(
                    ProjectMember.project_id == project_id,
                    ProjectMember.is_active.is_(True),
                    UserOrganization.user_id == user_id,
                    UserOrganization.is_active.is_(True),
                    User.is_active.is_(True),
                    User.tenant_id == self.tenant_id,
                    Organization.is_active.is_(True),
                    Organization.tenant_id == self.tenant_id,
                    Role.is_active.is_(True),
                    Role.tenant_id == self.tenant_id,
                )
                .options(
                    selectinload(ProjectMember.membership).selectinload(
                        UserOrganization.user
                    ),
                    selectinload(ProjectMember.membership).selectinload(
                        UserOrganization.organization
                    ),
                    selectinload(ProjectMember.role),
                )
            )
        )

    def role_has_permission(self, role_id: int, permission_code: str) -> bool:
        return (
            self.session.scalar(
                select(RolePermission.id)
                .join(Permission, Permission.id == RolePermission.permission_id)
                .where(
                    RolePermission.role_id == role_id,
                    Permission.permission_code == permission_code,
                )
            )
            is not None
        )

    def get_organization(self, org_id: int) -> Organization | None:
        return self.session.scalar(
            select(Organization).where(
                Organization.id == org_id,
                Organization.tenant_id == self.tenant_id,
            )
        )

    def get_membership(self, user_org_id: int) -> UserOrganization | None:
        return self.session.scalar(
            select(UserOrganization)
            .join(User, User.id == UserOrganization.user_id)
            .join(Organization, Organization.id == UserOrganization.org_id)
            .where(
                UserOrganization.id == user_org_id,
                User.tenant_id == self.tenant_id,
                Organization.tenant_id == self.tenant_id,
            )
            .options(
                selectinload(UserOrganization.user),
                selectinload(UserOrganization.organization),
            )
        )

    def get_user(self, user_id: int) -> User | None:
        return self.session.scalar(
            select(User).where(User.id == user_id, User.tenant_id == self.tenant_id)
        )

    def list_subscriptions(self) -> list[TenantApplication]:
        return list(
            self.session.scalars(
                select(TenantApplication)
                .where(
                    TenantApplication.tenant_id == self.tenant_id,
                    TenantApplication.is_active.is_(True),
                )
                .options(selectinload(TenantApplication.application))
                .order_by(TenantApplication.application_id)
            )
        )

    def get_role(self, role_code: str) -> Role | None:
        return self.session.scalar(
            select(Role).where(
                Role.tenant_id == self.tenant_id,
                Role.role_code == role_code,
            )
        )

    def replace_project_organizations(
        self, project_id: int, links: list[ProjectOrganization]
    ) -> None:
        self.session.execute(
            delete(ProjectOrganization).where(
                ProjectOrganization.project_id == project_id
            )
        )
        self.session.add_all(links)

    def replace_project_members(
        self, project_id: int, members: list[ProjectMember]
    ) -> None:
        self.session.execute(
            delete(ProjectMember).where(ProjectMember.project_id == project_id)
        )
        self.session.add_all(members)

    def replace_user_application_accesses(
        self, user_id: int, accesses: list[UserApplicationAccess]
    ) -> None:
        subscription_ids = [item.id for item in self.list_subscriptions()]
        if subscription_ids:
            self.session.execute(
                delete(UserApplicationAccess).where(
                    UserApplicationAccess.user_id == user_id,
                    UserApplicationAccess.tenant_application_id.in_(
                        subscription_ids
                    ),
                )
            )
        self.session.add_all(accesses)

    def add_audit(
        self,
        entity_type: str,
        entity_id: int,
        action: str,
        operator_id: int,
        payload: dict,
    ) -> None:
        self.session.add(
            IAMAuditLog(
                tenant_id=self.tenant_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                operator_id=operator_id,
                payload_json=payload,
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
