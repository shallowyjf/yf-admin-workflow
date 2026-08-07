"""Repository for IAM and authorization entities."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import (
    Organization,
    Permission,
    Position,
    Role,
    RoleDataScope,
    RolePermission,
    User,
    UserOrganization,
    UserOrganizationPosition,
    UserOrganizationRole,
)


class IAMRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entity: object) -> None:
        self.session.add(entity)

    def commit(self) -> None:
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def refresh(self, entity: object) -> None:
        self.session.refresh(entity)

    def get_user_by_username(self, username: str) -> User | None:
        return self.session.scalar(select(User).where(User.username == username))

    def get_organization_by_code(self, org_code: str) -> Organization | None:
        return self.session.scalar(
            select(Organization).where(Organization.org_code == org_code)
        )

    def get_role_by_code(self, role_code: str) -> Role | None:
        return self.session.scalar(select(Role).where(Role.role_code == role_code))

    def get_position_by_code(self, position_code: str) -> Position | None:
        return self.session.scalar(
            select(Position).where(Position.position_code == position_code)
        )

    def get_permission_by_code(self, permission_code: str) -> Permission | None:
        return self.session.scalar(
            select(Permission).where(Permission.permission_code == permission_code)
        )

    def get_membership(self, user_id: int, org_id: int) -> UserOrganization | None:
        return self.session.scalar(
            select(UserOrganization)
            .where(
                UserOrganization.user_id == user_id,
                UserOrganization.org_id == org_id,
            )
            .options(
                selectinload(UserOrganization.role_links).selectinload(
                    UserOrganizationRole.role
                ),
                selectinload(UserOrganization.position_links).selectinload(
                    UserOrganizationPosition.position
                ),
            )
        )

    def get_role_link(
        self, membership_id: int, role_id: int
    ) -> UserOrganizationRole | None:
        return self.session.scalar(
            select(UserOrganizationRole).where(
                UserOrganizationRole.user_org_id == membership_id,
                UserOrganizationRole.role_id == role_id,
            )
        )

    def get_position_link(
        self, membership_id: int, position_id: int
    ) -> UserOrganizationPosition | None:
        return self.session.scalar(
            select(UserOrganizationPosition).where(
                UserOrganizationPosition.user_org_id == membership_id,
                UserOrganizationPosition.position_id == position_id,
            )
        )

    def get_role_permission(
        self, role_id: int, permission_id: int
    ) -> RolePermission | None:
        return self.session.scalar(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
            )
        )

    def get_role_data_scope(
        self, role_id: int, permission_code: str
    ) -> RoleDataScope | None:
        return self.session.scalar(
            select(RoleDataScope).where(
                RoleDataScope.role_id == role_id,
                RoleDataScope.permission_code == permission_code,
            )
        )

    def list_authorized_role_ids(
        self,
        user_id: int,
        permission_code: str,
        active_org_id: int,
    ) -> list[int]:
        statement = (
            select(Role.id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .join(UserOrganizationRole, UserOrganizationRole.role_id == Role.id)
            .join(
                UserOrganization,
                UserOrganization.id == UserOrganizationRole.user_org_id,
            )
            .join(User, User.id == UserOrganization.user_id)
            .join(Organization, Organization.id == UserOrganization.org_id)
            .where(
                User.id == user_id,
                User.is_active.is_(True),
                UserOrganization.org_id == active_org_id,
                UserOrganization.is_active.is_(True),
                Organization.is_active.is_(True),
                Role.is_active.is_(True),
                Permission.permission_code == permission_code,
            )
            .distinct()
        )
        return list(self.session.scalars(statement))

    def list_role_data_scopes(
        self,
        role_ids: list[int],
        permission_code: str,
    ) -> list[RoleDataScope]:
        if not role_ids:
            return []
        return list(
            self.session.scalars(
                select(RoleDataScope).where(
                    RoleDataScope.role_id.in_(role_ids),
                    RoleDataScope.permission_code == permission_code,
                )
            )
        )

    def list_active_descendant_org_ids(self, org_id: int) -> set[int]:
        organization = self.session.get(Organization, org_id)
        if organization is None or not organization.is_active:
            return set()
        descendant_path = f"{organization.org_path}/%"
        return set(
            self.session.scalars(
                select(Organization.id).where(
                    Organization.is_active.is_(True),
                    (
                        (Organization.id == org_id)
                        | Organization.org_path.like(descendant_path)
                    ),
                )
            )
        )

    def list_organizations(self) -> list[Organization]:
        return list(
            self.session.scalars(
                select(Organization).order_by(Organization.sort_no, Organization.id)
            )
        )
