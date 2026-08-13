"""Persistence operations for authentication sessions and user context."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from app.iam.models import (
    Organization,
    Permission,
    Role,
    RolePermission,
    Tenant,
    User,
    UserOrganization,
    UserOrganizationRole,
)
from app.project.models import (
    Application,
    Project,
    ProjectMember,
    TenantApplication,
    UserApplicationAccess,
)

from .models import AuthSession, PlatformSession, PlatformUser


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_tenant_by_code(self, tenant_code: str) -> Tenant | None:
        return self.session.scalar(
            select(Tenant).where(Tenant.tenant_code == tenant_code)
        )

    def get_tenant(self, tenant_id: int) -> Tenant | None:
        return self.session.get(Tenant, tenant_id)

    def get_user(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def list_active_tenants(self) -> list[Tenant]:
        return list(
            self.session.scalars(
                select(Tenant).where(Tenant.is_active.is_(True)).order_by(Tenant.id)
            )
        )

    def get_platform_user(self, username: str) -> PlatformUser | None:
        return self.session.scalar(
            select(PlatformUser).where(PlatformUser.username == username)
        )

    def get_platform_session(self, token_hash: str) -> PlatformSession | None:
        return self.session.scalar(
            select(PlatformSession)
            .where(PlatformSession.token_hash == token_hash)
            .options(joinedload(PlatformSession.platform_user))
        )

    def get_user_by_username(self, username: str, tenant_id: int) -> User | None:
        return self.session.scalar(
            select(User).where(
                User.username == username,
                User.tenant_id == tenant_id,
            )
        )

    def list_active_memberships(
        self,
        user_id: int,
        tenant_id: int,
    ) -> list[UserOrganization]:
        return list(
            self.session.scalars(
                select(UserOrganization)
                .join(Organization, Organization.id == UserOrganization.org_id)
                .where(
                    UserOrganization.user_id == user_id,
                    Organization.tenant_id == tenant_id,
                    UserOrganization.is_active.is_(True),
                    Organization.is_active.is_(True),
                )
                .options(
                    joinedload(UserOrganization.organization),
                    selectinload(UserOrganization.role_links).joinedload(
                        UserOrganizationRole.role
                    ),
                )
                .order_by(
                    UserOrganization.is_primary.desc(),
                    Organization.sort_no,
                    UserOrganization.id,
                )
            ).unique()
        )

    def get_active_membership(
        self,
        user_id: int,
        org_id: int,
        tenant_id: int,
    ) -> UserOrganization | None:
        return self.session.scalar(
            select(UserOrganization)
            .join(Organization, Organization.id == UserOrganization.org_id)
            .where(
                UserOrganization.user_id == user_id,
                UserOrganization.org_id == org_id,
                Organization.tenant_id == tenant_id,
                UserOrganization.is_active.is_(True),
                Organization.is_active.is_(True),
            )
        )

    def get_session_by_token_hash(self, token_hash: str) -> AuthSession | None:
        return self.session.scalar(
            select(AuthSession)
            .where(AuthSession.token_hash == token_hash)
            .options(
                joinedload(AuthSession.user),
                joinedload(AuthSession.tenant),
                joinedload(AuthSession.active_organization),
            )
        )

    def list_user_applications(
        self, user_id: int, tenant_id: int
    ) -> list[Application]:
        return list(
            self.session.scalars(
                select(Application)
                .join(TenantApplication)
                .join(UserApplicationAccess)
                .where(
                    TenantApplication.tenant_id == tenant_id,
                    TenantApplication.is_active.is_(True),
                    UserApplicationAccess.user_id == user_id,
                    UserApplicationAccess.is_active.is_(True),
                    Application.is_active.is_(True),
                )
                .order_by(Application.id)
            )
        )

    def list_accessible_projects(
        self,
        user_id: int,
        tenant_id: int,
        *,
        include_all: bool,
    ) -> list[Project]:
        application_ids = {
            application.id
            for application in self.list_user_applications(user_id, tenant_id)
        }
        if not application_ids:
            return []
        statement = (
            select(Project)
            .where(
                Project.tenant_id == tenant_id,
                Project.application_id.in_(application_ids),
            )
            .options(joinedload(Project.application))
            .order_by(Project.application_id, Project.id)
        )
        if include_all:
            return list(self.session.scalars(statement))
        return list(
            self.session.scalars(
                statement
                .join(ProjectMember)
                .join(UserOrganization)
                .join(Organization, Organization.id == UserOrganization.org_id)
                .join(User, User.id == UserOrganization.user_id)
                .join(Role, Role.id == ProjectMember.role_id)
                .join(RolePermission, RolePermission.role_id == Role.id)
                .join(Permission, Permission.id == RolePermission.permission_id)
                .where(
                    ProjectMember.is_active.is_(True),
                    UserOrganization.user_id == user_id,
                    UserOrganization.is_active.is_(True),
                    Organization.tenant_id == tenant_id,
                    Organization.is_active.is_(True),
                    User.tenant_id == tenant_id,
                    User.is_active.is_(True),
                    Role.tenant_id == tenant_id,
                    Role.is_active.is_(True),
                    Permission.permission_code == "project:view",
                )
                .distinct()
            )
        )

    def save(self, entity: object) -> None:
        self.session.add(entity)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def refresh(self, entity: object) -> None:
        self.session.refresh(entity)

    def revoke_user_sessions(self, user_id: int, revoked_at: datetime) -> None:
        self.session.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
