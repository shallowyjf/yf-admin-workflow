"""Tenant-safe queries for governed business data."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.iam.models import Permission, Role, RolePermission, User, UserOrganization
from app.project.models import TenantApplication, UserApplicationAccess

from .models import ApplicationRoleGrant, BusinessResource, DataSpace, ResourcePolicy


class DataPermissionRepository:
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

    def get_space_by_code(self, code: str) -> DataSpace | None:
        return self.session.scalar(
            select(DataSpace).where(
                DataSpace.tenant_id == self.tenant_id, DataSpace.space_code == code
            )
        )

    def get_resource_by_key(self, key: str) -> BusinessResource | None:
        return self.session.scalar(
            select(BusinessResource).where(
                BusinessResource.tenant_id == self.tenant_id,
                BusinessResource.resource_key == key,
            )
        )

    def get_resource(self, resource_id: int) -> BusinessResource | None:
        return self.session.scalar(
            select(BusinessResource)
            .where(
                BusinessResource.id == resource_id,
                BusinessResource.tenant_id == self.tenant_id,
            )
            .options(
                selectinload(BusinessResource.data_space),
                selectinload(BusinessResource.application),
                selectinload(BusinessResource.project),
                selectinload(BusinessResource.owner_organization),
            )
        )

    def list_spaces(self, application_id: int | None = None) -> list[DataSpace]:
        statement = select(DataSpace).where(
            DataSpace.tenant_id == self.tenant_id, DataSpace.is_active.is_(True)
        )
        if application_id is not None:
            statement = statement.where(DataSpace.application_id == application_id)
        return list(self.session.scalars(statement.order_by(DataSpace.id)))

    def list_resources(self, application_id: int | None = None) -> list[BusinessResource]:
        statement = (
            select(BusinessResource)
            .where(
                BusinessResource.tenant_id == self.tenant_id,
                BusinessResource.status == "ACTIVE",
            )
            .options(
                selectinload(BusinessResource.data_space),
                selectinload(BusinessResource.application),
                selectinload(BusinessResource.project),
                selectinload(BusinessResource.owner_organization),
            )
        )
        if application_id is not None:
            statement = statement.where(BusinessResource.application_id == application_id)
        return list(self.session.scalars(statement.order_by(BusinessResource.id)))

    def get_subscription(self, application_id: int) -> TenantApplication | None:
        return self.session.scalar(
            select(TenantApplication).where(
                TenantApplication.tenant_id == self.tenant_id,
                TenantApplication.application_id == application_id,
                TenantApplication.is_active.is_(True),
            )
        )

    def get_membership(self, membership_id: int) -> UserOrganization | None:
        return self.session.scalar(
            select(UserOrganization)
            .join(User)
            .where(
                UserOrganization.id == membership_id,
                User.tenant_id == self.tenant_id,
                UserOrganization.is_active.is_(True),
            )
        )

    def get_role(self, role_code: str) -> Role | None:
        return self.session.scalar(
            select(Role).where(
                Role.tenant_id == self.tenant_id,
                Role.role_code == role_code,
                Role.is_active.is_(True),
            )
        )

    def has_application_access(self, user_id: int, application_id: int) -> bool:
        return self.session.scalar(
            select(UserApplicationAccess.id)
            .join(TenantApplication)
            .where(
                TenantApplication.tenant_id == self.tenant_id,
                TenantApplication.application_id == application_id,
                TenantApplication.is_active.is_(True),
                UserApplicationAccess.user_id == user_id,
                UserApplicationAccess.is_active.is_(True),
            )
        ) is not None

    def get_grant(
        self, tenant_application_id: int, user_org_id: int, role_id: int
    ) -> ApplicationRoleGrant | None:
        return self.session.scalar(
            select(ApplicationRoleGrant).where(
                ApplicationRoleGrant.tenant_id == self.tenant_id,
                ApplicationRoleGrant.tenant_application_id == tenant_application_id,
                ApplicationRoleGrant.user_org_id == user_org_id,
                ApplicationRoleGrant.role_id == role_id,
            )
        )

    def list_user_grants(
        self, user_id: int, application_id: int | None = None
    ) -> list[ApplicationRoleGrant]:
        now = datetime.now(UTC).replace(tzinfo=None)
        statement = (
            select(ApplicationRoleGrant)
            .join(TenantApplication)
            .join(UserOrganization)
            .join(User, User.id == UserOrganization.user_id)
            .join(Role, Role.id == ApplicationRoleGrant.role_id)
            .where(
                ApplicationRoleGrant.tenant_id == self.tenant_id,
                ApplicationRoleGrant.is_active.is_(True),
                UserOrganization.user_id == user_id,
                UserOrganization.is_active.is_(True),
                User.tenant_id == self.tenant_id,
                User.is_active.is_(True),
                Role.tenant_id == self.tenant_id,
                Role.is_active.is_(True),
                TenantApplication.tenant_id == self.tenant_id,
                TenantApplication.is_active.is_(True),
                (ApplicationRoleGrant.valid_from.is_(None))
                | (ApplicationRoleGrant.valid_from <= now),
                (ApplicationRoleGrant.valid_to.is_(None))
                | (ApplicationRoleGrant.valid_to > now),
            )
            .options(
                selectinload(ApplicationRoleGrant.role),
                selectinload(ApplicationRoleGrant.membership).selectinload(
                    UserOrganization.organization
                ),
                selectinload(ApplicationRoleGrant.tenant_application).selectinload(
                    TenantApplication.application
                ),
            )
        )
        if application_id is not None:
            statement = statement.where(TenantApplication.application_id == application_id)
        return list(self.session.scalars(statement.order_by(ApplicationRoleGrant.id)))

    def role_has_permission(self, role_id: int, action_code: str) -> bool:
        return self.session.scalar(
            select(RolePermission.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(
                RolePermission.role_id == role_id,
                Permission.permission_code == action_code,
            )
        ) is not None

    def list_policies(
        self, resource_id: int, role_ids: set[int], action_code: str
    ) -> list[ResourcePolicy]:
        if not role_ids:
            return []
        now = datetime.now(UTC).replace(tzinfo=None)
        return list(
            self.session.scalars(
                select(ResourcePolicy)
                .where(
                    ResourcePolicy.tenant_id == self.tenant_id,
                    ResourcePolicy.subject_type == "ROLE",
                    ResourcePolicy.subject_id.in_(role_ids),
                    ResourcePolicy.resource_id == resource_id,
                    ResourcePolicy.action_code == action_code,
                    ResourcePolicy.is_active.is_(True),
                    (ResourcePolicy.valid_from.is_(None))
                    | (ResourcePolicy.valid_from <= now),
                    (ResourcePolicy.valid_to.is_(None))
                    | (ResourcePolicy.valid_to > now),
                ).order_by(ResourcePolicy.priority.desc(), ResourcePolicy.id)
            )
        )

    def get_policy(
        self, role_id: int, resource_id: int, action_code: str, effect: str
    ) -> ResourcePolicy | None:
        return self.session.scalar(
            select(ResourcePolicy).where(
                ResourcePolicy.tenant_id == self.tenant_id,
                ResourcePolicy.subject_type == "ROLE",
                ResourcePolicy.subject_id == role_id,
                ResourcePolicy.resource_id == resource_id,
                ResourcePolicy.action_code == action_code,
                ResourcePolicy.effect == effect,
            )
        )
